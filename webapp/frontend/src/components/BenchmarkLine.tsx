// Feature 2 — one contract's value against the portfolio average.
//
// A traffic light is a judgement, so the two things that make it checkable are on
// screen next to it: HOW BIG the sample was, and WHAT was left out of it. A field
// with no defensible better/worse direction shows the deviation with a grey dot
// and says why it is not rated, rather than picking a direction to look decisive.
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { formatDatesInText } from "../lib/format";

const TONE: Record<string, string> = {
  green: "border-ok/40 bg-okbg text-ink",
  yellow: "border-warn/50 bg-warnbg text-ink",
  red: "border-alert/50 bg-alertbg text-ink",
  unrated: "border-rule bg-paper text-ink",
};

export function BenchmarkLine({ fieldKey, documentId }: { fieldKey: string; documentId: string }) {
  const [open, setOpen] = useState(false);

  // Which fields can be benchmarked is the server's decision, fetched once and
  // cached, so this component never keeps its own copy of that list to drift.
  const fields = useQuery({ queryKey: ["benchmark", "fields"], queryFn: api.benchmarkFields });
  const benchmarkable = !!fields.data?.fields.some((f) => f.fieldKey === fieldKey);

  const q = useQuery({
    queryKey: ["benchmark", fieldKey, documentId],
    queryFn: () => api.benchmark(fieldKey, documentId),
    enabled: benchmarkable,
    retry: false,
  });

  // Nothing is rendered unless there is a real comparison to show: no value, no
  // peers, or a field that is not benchmarkable all mean silence rather than a
  // placeholder that implies a measurement was taken.
  if (!benchmarkable || q.isLoading || q.isError || !q.data?.selected) return null;
  const b = q.data;
  const s = b.selected!;

  return (
    <div className={`mt-2 rounded border px-2.5 py-2 text-sm ${TONE[s.light] ?? TONE.unrated}`}>
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="font-medium">{formatDatesInText(s.summary)}</span>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="ml-auto text-muted underline decoration-rule underline-offset-2"
          aria-expanded={open}
        >
          {open ? "Hide" : "How this was worked out"}
        </button>
      </div>

      {s.note && <p className="mt-1 text-muted">{s.note}</p>}
      {b.polarity === "undefined" && b.polarityNote && (
        <p className="mt-1 text-muted">Not rated: {b.polarityNote}</p>
      )}

      {open && (
        <div className="mt-2 space-y-2 border-t border-rule pt-2">
          <p className="text-muted">{formatDatesInText(b.sampleNote)}</p>
          <p className="text-muted">
            Compared against {s.peerCount} other contract(s), excluding this one — an average that
            contains the value being measured flatters every outlier.
          </p>
          <ul className="space-y-1">
            {b.samples.map((sample) => (
              <li key={sample.fieldId} className="flex flex-wrap gap-x-2 text-muted">
                <span className="tnum w-24 text-ink">{formatDatesInText(sample.display)}</span>
                <span className={sample.documentId === documentId ? "font-medium text-ink" : ""}>
                  {sample.filename}
                </span>
                <span className="text-faint">
                  {sample.label}
                  {sample.readFrom === "parsed" && " · read from the quoted text"}
                  {sample.clauseLabel && ` · ${sample.clauseLabel}`}
                </span>
              </li>
            ))}
          </ul>
          {b.excluded.length > 0 && (
            <div>
              <p className="font-medium text-ink">Left out of the average</p>
              <ul className="mt-0.5 space-y-1">
                {b.excluded.map((e) => (
                  <li key={e.documentId + e.valueVerbatim} className="text-muted">
                    · {e.filename} — “{e.valueVerbatim.slice(0, 70)}” ({e.reason})
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="text-faint">
            Median {formatDatesInText(b.medianDisplay ?? "—")}. This is arithmetic over the values
            already extracted; no model was consulted.
          </p>
        </div>
      )}
    </div>
  );
}
