import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type DocumentSummary } from "../lib/api";
import { DOC_TYPE_LABELS } from "../lib/domain";
import { formatDate, relativeDays } from "../lib/format";
import { Uploader } from "../components/Uploader";
import { EmptyState, ErrorState, Skeleton, StatusPill, SummaryStat } from "../components/ui";

const PROCESSING = new Set(["queued", "processing"]);

type Filter = "all" | "processing" | "review" | "unsupported";

export default function Portfolio() {
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");

  const params = useMemo(() => {
    const p = new URLSearchParams();
    if (search.trim()) p.set("q", search.trim());
    if (filter === "processing") p.set("status", "queued,processing");
    if (filter === "unsupported") p.set("status", "unsupported");
    return p;
  }, [filter, search]);

  const docsQuery = useQuery({
    queryKey: ["documents", params.toString()],
    queryFn: () => api.documents(params),
    refetchInterval: (q) =>
      (q.state.data?.documents ?? []).some((d) => PROCESSING.has(d.status)) ? 2000 : false,
  });

  const summaryQuery = useQuery({
    queryKey: ["portfolio"],
    queryFn: () => api.portfolio(),
    refetchInterval: (q) => ((q.state.data?.processing ?? 0) > 0 ? 2000 : false),
  });

  if (docsQuery.isLoading) return <PortfolioSkeleton />;
  if (docsQuery.isError) return <ErrorState message={(docsQuery.error as Error).message} />;

  const data = docsQuery.data!;
  const summary = summaryQuery.data;

  if (data.total === 0 && !search && filter === "all") {
    return (
      <div className="mx-auto max-w-3xl">
        <h1 className="mb-1 text-2xl font-bold text-ink">Your contracts, read for you.</h1>
        <p className="mb-6 text-muted">
          Upload the agreements you are responsible for. AITHENA extracts the dates and obligations and flags what you
          must act on — always with a citation and a confidence level you can trust.
        </p>
        <Uploader variant="hero" />
      </div>
    );
  }

  let docs = data.documents;
  if (filter === "review") {
    docs = docs
      .filter((d) => d.needsReview)
      // urgency × uncertainty: soonest action first
      .sort((a, b) => (a.nextActionDate ?? "9999").localeCompare(b.nextActionDate ?? "9999"));
  }

  const today = summary?.today ?? new Date().toISOString().slice(0, 10);

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-ink">Portfolio</h1>
        <Uploader variant="compact" />
      </div>

      <div className="mb-6 grid gap-4 lg:grid-cols-[1fr_20rem]">
        {summary ? (
          <div className="grid grid-cols-2 gap-3 self-start md:grid-cols-4 lg:grid-cols-2 xl:grid-cols-4">
            <SummaryStat label="Contracts tracked" value={summary.contractsTracked} />
            <SummaryStat
              label="Actions in 90 days"
              value={summary.actionsNext90}
              tone={summary.overdue > 0 ? "alert" : "default"}
              hint={summary.overdue > 0 ? `${summary.overdue} overdue` : undefined}
            />
            <SummaryStat
              label="Conflicts found"
              value={summary.conflictsFound}
              tone={summary.conflictsFound > 0 ? "warn" : "default"}
            />
            <SummaryStat
              label="Need review"
              value={summary.documentsNeedingReview}
              tone={summary.documentsNeedingReview > 0 ? "warn" : "default"}
            />
          </div>
        ) : (
          <div />
        )}
        <UpcomingActions today={today} />
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <FilterChip on={filter === "all"} onClick={() => setFilter("all")}>
          All ({data.total})
        </FilterChip>
        <FilterChip on={filter === "processing"} onClick={() => setFilter("processing")}>
          Processing ({(data.counts.queued ?? 0) + (data.counts.processing ?? 0)})
        </FilterChip>
        <FilterChip on={filter === "review"} onClick={() => setFilter("review")}>
          Needs review
        </FilterChip>
        {(data.counts.unsupported ?? 0) > 0 && (
          <FilterChip on={filter === "unsupported"} onClick={() => setFilter("unsupported")}>
            Not supported ({data.counts.unsupported})
          </FilterChip>
        )}
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name or party…"
          className="ml-auto w-56 rounded border border-rule px-3 py-1.5 text-sm"
        />
      </div>

      {docs.length === 0 ? (
        <EmptyState title="Nothing here yet.">
          <p>No documents match this filter.</p>
        </EmptyState>
      ) : (
        <div className="panel overflow-hidden">
          <table className="w-full text-left">
            <thead className="border-b border-rule bg-paper text-sm text-muted">
              <tr>
                <th className="px-4 py-2.5 font-medium">Document</th>
                <th className="px-4 py-2.5 font-medium">Counterparty</th>
                <th className="px-4 py-2.5 font-medium">Type</th>
                <th className="px-4 py-2.5 font-medium">Term end</th>
                <th className="px-4 py-2.5 font-medium">Next action</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {docs.map((d) => (
                <DocRow key={d.id} doc={d} today={today} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function DocRow({ doc, today }: { doc: DocumentSummary; today: string }) {
  const isProcessing = PROCESSING.has(doc.status);
  const notContract = doc.docType === "not_a_contract";
  const linkable = doc.status !== "unsupported";

  return (
    <tr className={`text-[0.98rem] ${notContract ? "bg-paper/60" : ""}`}>
      <td className="px-4 py-3">
        {linkable ? (
          <Link to={`/documents/${doc.id}`} className="font-medium text-navy hover:underline">
            {doc.filename}
          </Link>
        ) : (
          <span className="font-medium text-ink">{doc.filename}</span>
        )}
        {notContract && (
          <div className="mt-0.5 text-sm text-muted">Not a contract — no terms were extracted.</div>
        )}
        {doc.status === "unsupported" && doc.error && (
          <div className="mt-0.5 text-sm text-alert">{doc.error}</div>
        )}
        {doc.needsReview && !notContract && (
          <span className="mt-1 inline-block rounded border border-warn/40 bg-warnbg px-1.5 py-0.5 text-xs font-medium text-warn">
            Needs review
          </span>
        )}
      </td>
      <td className="px-4 py-3 text-ink">{doc.counterparty ?? "—"}</td>
      <td className="px-4 py-3 text-muted">{doc.docType ? (DOC_TYPE_LABELS[doc.docType] ?? doc.docType) : "—"}</td>
      <td className="px-4 py-3 tnum text-ink">{notContract ? "—" : formatDate(doc.termEnd ?? null)}</td>
      <td className="px-4 py-3 tnum">
        {doc.nextActionDate ? (
          <span className={doc.nextActionDate < today ? "font-semibold text-alert" : "text-ink"}>
            {formatDate(doc.nextActionDate)}
            <span className="ml-1 text-sm text-faint">{relativeDays(today, doc.nextActionDate)}</span>
          </span>
        ) : (
          "—"
        )}
      </td>
      <td className="px-4 py-3">
        {isProcessing ? <ProcessingCell docId={doc.id} /> : <StatusPill status={doc.status} />}
      </td>
    </tr>
  );
}

// Polls the lightweight status endpoint every 2s and renders the stage string
// (§6). When the document reaches a terminal state, refresh the list.
function ProcessingCell({ docId }: { docId: string }) {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["docStatus", docId],
    queryFn: () => api.documentStatus(docId),
    refetchInterval: (q) => (PROCESSING.has(q.state.data?.status ?? "processing") ? 2000 : false),
  });

  // When the document reaches a terminal state, refresh the list + summary.
  useEffect(() => {
    if (data && !PROCESSING.has(data.status)) {
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["portfolio"] });
    }
  }, [data?.status, qc]);

  const pct = Math.round((data?.progress ?? 0) * 100);
  return (
    <div className="min-w-[9rem]">
      <div className="mb-1 flex items-center justify-between text-xs text-muted">
        <span>{(data?.stage as string) ?? "queued"}</span>
        <span className="tnum">{pct}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded bg-rule">
        <div className="h-full bg-navy transition-all" style={{ width: `${Math.max(6, pct)}%` }} />
      </div>
    </div>
  );
}

// Forward-looking action widget (UI-4): the "top right corner" dashboard piece.
// Surfaces what expires / auto-renews / needs notice, by the date action is due,
// with the exact quick-filter horizons the spec calls for.
const WIDGET_HORIZONS: { key: string; label: string; days: number }[] = [
  { key: "today", label: "Today", days: 0 },
  { key: "week", label: "This week", days: 7 },
  { key: "30", label: "30d", days: 30 },
  { key: "60", label: "60d", days: 60 },
  { key: "90", label: "90d", days: 90 },
];

function widgetAddDays(iso: string, days: number): string {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function UpcomingActions({ today }: { today: string }) {
  const [days, setDays] = useState(90);
  const params = useMemo(() => {
    const p = new URLSearchParams();
    p.set("status", "active");
    p.set("to", "2999-01-01");
    return p;
  }, []);
  const cal = useQuery({ queryKey: ["calendar", params.toString()], queryFn: () => api.calendar(params) });

  const events = cal.data?.events ?? [];
  const horizonIso = widgetAddDays(today, days); // strictly forward: today → today + N
  const upcoming = events
    .filter((e) => e.status !== "dismissed")
    .map((e) => ({ e, eff: e.actionByDate ?? e.eventDate }))
    .filter((x) => x.eff <= horizonIso)
    .sort((a, b) => a.eff.localeCompare(b.eff));
  const overdue = upcoming.filter((x) => x.eff < today).length;

  return (
    <aside className="panel self-start p-3">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Upcoming actions</h2>
        <Link to="/calendar" className="text-xs text-navy hover:underline">
          View all →
        </Link>
      </div>
      <div className="mb-2 flex flex-wrap gap-1">
        {WIDGET_HORIZONS.map((h) => (
          <button
            key={h.key}
            onClick={() => setDays(h.days)}
            className={`rounded border px-1.5 py-0.5 text-xs ${
              days === h.days ? "border-navy bg-navy text-white" : "border-rule bg-surface text-muted hover:bg-paper"
            }`}
          >
            {h.label}
          </button>
        ))}
      </div>
      {overdue > 0 && (
        <div className="mb-2 rounded border border-alert/40 bg-alertbg px-2 py-1 text-xs font-medium text-alert">
          {overdue} overdue
        </div>
      )}
      {upcoming.length === 0 ? (
        <p className="py-2 text-sm text-muted">Nothing due in this window.</p>
      ) : (
        <ul className="space-y-1.5">
          {upcoming.slice(0, 6).map(({ e, eff }) => (
            <li key={e.id} className="flex items-baseline justify-between gap-2 text-sm">
              <Link to={`/documents/${e.documentId}`} className="min-w-0 flex-1 truncate text-ink hover:underline" title={e.title}>
                {e.title}
              </Link>
              <span className={`tnum whitespace-nowrap text-xs ${eff < today ? "font-semibold text-alert" : "text-muted"}`}>
                {formatDate(eff)}
              </span>
            </li>
          ))}
          {upcoming.length > 6 && (
            <li className="pt-1 text-xs text-faint">+{upcoming.length - 6} more</li>
          )}
        </ul>
      )}
    </aside>
  );
}

function FilterChip({ on, onClick, children }: { on: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-sm font-medium ${
        on ? "border-navy bg-navy text-white" : "border-rule bg-surface text-muted hover:bg-paper"
      }`}
    >
      {children}
    </button>
  );
}

function PortfolioSkeleton() {
  return (
    <div>
      <Skeleton className="mb-5 h-8 w-40" />
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
      <Skeleton className="h-64" />
    </div>
  );
}
