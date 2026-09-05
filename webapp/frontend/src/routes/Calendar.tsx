import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type CalendarEventDTO } from "../lib/api";
import { BAND_LABELS, BAND_ORDER, bandFor, formatDate, relativeDays, type Band } from "../lib/format";
import { ConfidenceBadge, tierRank } from "../lib/confidence";
import { EmptyState, ErrorState, Skeleton } from "../components/ui";

type Range = "90" | "180" | "all";

function addDays(iso: string, days: number): string {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export default function Calendar() {
  const qc = useQueryClient();
  const [range, setRange] = useState<Range>("90"); // default is what gets demoed
  const [confirmedOnly, setConfirmedOnly] = useState(false);
  const [showDismissed, setShowDismissed] = useState(false);

  // We fetch a wide window (all) and band client-side; the range control just
  // changes the horizon we display. Keeps optimistic updates on one cache key.
  const params = useMemo(() => {
    const p = new URLSearchParams();
    p.set("status", showDismissed ? "all" : "active");
    if (confirmedOnly) p.set("minConfidence", "normalised");
    p.set("to", "2999-01-01");
    return p;
  }, [confirmedOnly, showDismissed]);

  const key = ["calendar", params.toString()];
  const cal = useQuery({ queryKey: key, queryFn: () => api.calendar(params) });

  const mutate = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => api.patchEvent(id, status),
    onMutate: async ({ id, status }) => {
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<{ today: string; to: string; events: CalendarEventDTO[] }>(key);
      if (prev) {
        qc.setQueryData(key, {
          ...prev,
          events: prev.events.map((e) => (e.id === id ? { ...e, status } : e)),
        });
      }
      return { prev };
    },
    onError: (_e, _v, ctx) => ctx?.prev && qc.setQueryData(key, ctx.prev),
    onSettled: () => qc.invalidateQueries({ queryKey: ["calendar"] }),
  });

  if (cal.isLoading) return <CalendarSkeleton />;
  if (cal.isError) return <ErrorState message={(cal.error as Error).message} />;

  const { today, events } = cal.data!;
  const horizon = range === "all" ? "2999-01-01" : addDays(today, range === "90" ? 90 : 180);

  const visible = events.filter((e) => {
    if (!showDismissed && e.status === "dismissed") return false;
    const eff = e.actionByDate ?? e.eventDate;
    return eff <= horizon;
  });

  const byBand = new Map<Band, CalendarEventDTO[]>();
  for (const e of visible) {
    const b = bandFor(today, e.actionByDate ?? e.eventDate);
    if (range !== "all" && b === "later") continue;
    (byBand.get(b) ?? byBand.set(b, []).get(b)!).push(e);
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-ink">What's coming up</h1>
          <p className="text-muted">Sorted by the date you must act — the earlier date, not the event itself.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <div className="flex overflow-hidden rounded border border-rule">
            {(["90", "180", "all"] as Range[]).map((r) => (
              <button
                key={r}
                onClick={() => setRange(r)}
                className={`px-3 py-1.5 ${range === r ? "bg-navy text-white" : "bg-surface text-muted hover:bg-paper"}`}
              >
                {r === "all" ? "All" : `${r} days`}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-1.5 text-muted">
            <input type="checkbox" checked={confirmedOnly} onChange={(e) => setConfirmedOnly(e.target.checked)} />
            Confirmed dates only
          </label>
          <label className="flex items-center gap-1.5 text-muted">
            <input type="checkbox" checked={showDismissed} onChange={(e) => setShowDismissed(e.target.checked)} />
            Show dismissed
          </label>
        </div>
      </div>

      {visible.length === 0 ? (
        <EmptyState title="Nothing needs your attention in this window.">
          <p>Widen the range or turn off “confirmed dates only” to see less certain dates.</p>
        </EmptyState>
      ) : (
        <div className="space-y-6">
          {BAND_ORDER.map((band) => {
            const items = byBand.get(band);
            if (!items || items.length === 0) return null;
            return (
              <section key={band}>
                <h2
                  className={`mb-2 text-sm font-semibold uppercase tracking-wide ${
                    band === "overdue" ? "text-alert" : "text-muted"
                  }`}
                >
                  {BAND_LABELS[band]} · {items.length}
                </h2>
                <div className="space-y-2">
                  {items.map((e) => (
                    <EventRow
                      key={e.id}
                      event={e}
                      today={today}
                      overdue={band === "overdue"}
                      onAck={() => mutate.mutate({ id: e.id, status: e.status === "acknowledged" ? "open" : "acknowledged" })}
                      onDismiss={() => mutate.mutate({ id: e.id, status: "dismissed" })}
                    />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

function EventRow({
  event,
  today,
  overdue,
  onAck,
  onDismiss,
}: {
  event: CalendarEventDTO;
  today: string;
  overdue: boolean;
  onAck: () => void;
  onDismiss: () => void;
}) {
  const actionBy = event.actionByDate;
  // A date the system inferred is a different kind of object from one quoted from
  // a clause — mark it (§9).
  const lowConfidence = tierRank(event.confidenceTier) >= 2;

  return (
    <div
      className={`panel flex flex-wrap items-center gap-4 border-l-4 px-4 py-3 ${
        overdue ? "border-l-alert bg-alertbg" : lowConfidence ? "border-l-warn" : "border-l-ok"
      } ${event.status === "acknowledged" ? "opacity-70" : ""}`}
    >
      {/* Dominant: the action-by date. */}
      <div className="min-w-[10rem]">
        <div className="text-xs uppercase tracking-wide text-muted">Act by</div>
        <div className={`text-2xl font-bold tnum ${overdue ? "text-alert" : "text-ink"}`}>
          {formatDate(actionBy ?? event.eventDate)}
        </div>
        <div className={`text-sm font-medium ${overdue ? "text-alert" : "text-muted"}`}>
          {relativeDays(today, actionBy ?? event.eventDate)}
        </div>
      </div>

      {/* Secondary: what happens and when. */}
      <div className="min-w-[14rem] flex-1">
        <div className="font-medium text-ink">{event.title}</div>
        <div className="text-sm text-muted">
          {event.detail}
          {actionBy && actionBy !== event.eventDate && (
            <> · happens {formatDate(event.eventDate)}</>
          )}
        </div>
        <div className="mt-1 flex items-center gap-2">
          <ConfidenceBadge tier={event.confidenceTier} size="sm" />
          <Link to={`/documents/${event.documentId}`} className="link text-sm">
            View clause →
          </Link>
        </div>
      </div>

      {/* Actions: acknowledge / dismiss. */}
      <div className="flex items-center gap-2">
        <button className={`btn btn-sm ${event.status === "acknowledged" ? "btn-primary" : ""}`} onClick={onAck}>
          {event.status === "acknowledged" ? "Acknowledged" : "Acknowledge"}
        </button>
        <button className="btn btn-sm" onClick={onDismiss} title="Hide this — it won't be deleted">
          Dismiss
        </button>
      </div>
    </div>
  );
}

function CalendarSkeleton() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-8 w-64" />
      {[0, 1, 2, 3].map((i) => (
        <Skeleton key={i} className="h-20" />
      ))}
    </div>
  );
}
