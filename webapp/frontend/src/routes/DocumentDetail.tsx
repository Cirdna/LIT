import { useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type AnchorDTO, type FieldDTO } from "../lib/api";
import { DOC_TYPE_LABELS, FIELD_GROUPS } from "../lib/domain";
import {
  ConfidenceBadge,
  LABEL_META,
  LABEL_ORDER,
  labelForField,
  ocrBand,
  type DisplayLabel,
} from "../lib/confidence";
import { BenchmarkLine } from "../components/BenchmarkLine";
import { FieldValue } from "../components/FieldValue";
import { InvoiceMatch } from "../components/InvoiceMatch";
import { PageViewer } from "../components/PageViewer";
import { StatuteFlagNote } from "../components/StatuteFlagNote";
import { StatutePanel } from "../components/StatutePanel";
import { ErrorState, Skeleton, StatusPill } from "../components/ui";

const PROCESSING = new Set(["queued", "processing"]);

export default function DocumentDetail() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const viewerRef = useRef<HTMLDivElement>(null);

  const [currentPage, setCurrentPage] = useState(1);
  const [highlights, setHighlights] = useState<AnchorDTO[]>([]);
  const [activeFieldId, setActiveFieldId] = useState<string | null>(null);
  // All three labels visible by default: hiding anything by default would quietly
  // shrink what the reader thinks the contract says.
  const [shown, setShown] = useState<DisplayLabel[]>([...LABEL_ORDER]);

  const detail = useQuery({
    queryKey: ["document", id],
    queryFn: () => api.document(id),
    refetchInterval: (q) => (PROCESSING.has(q.state.data?.status ?? "") ? 2000 : false),
  });

  if (detail.isLoading) return <DetailSkeleton />;
  if (detail.isError) return <ErrorState message={(detail.error as Error).message} />;
  const doc = detail.data!;

  async function cite(field: FieldDTO) {
    setActiveFieldId(field.id);
    if (field.anchorLineIds.length === 0) return;
    const anchors = await api.anchors(id, field.anchorLineIds);
    setHighlights(anchors);
    if (anchors[0]) setCurrentPage(anchors[0].page);
    viewerRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  const isProcessing = PROCESSING.has(doc.status);
  const notContract = doc.docType === "not_a_contract";

  // A field key with no row reads as NA — same as an empty value. The filter and
  // the counts must agree with what the rows themselves are badged, so both go
  // through labelForField / the NA default.
  const labelsForKey = (key: string): DisplayLabel[] => {
    const matches = doc.fields.filter((f) => f.fieldKey === key);
    return matches.length === 0 ? ["na"] : matches.map(labelForField);
  };
  const counts = LABEL_ORDER.reduce(
    (acc, l) => ({ ...acc, [l]: 0 }),
    {} as Record<DisplayLabel, number>,
  );
  for (const group of FIELD_GROUPS)
    for (const def of group.fields) for (const l of labelsForKey(def.key)) counts[l] += 1;

  const isShown = (l: DisplayLabel) => shown.includes(l);
  const toggle = (l: DisplayLabel) =>
    setShown((prev) => (prev.includes(l) ? prev.filter((x) => x !== l) : [...prev, l]));

  // Role B flags hang off the field whose clause triggered them. A flag whose
  // CUAD category has no field key in this UI's vocabulary would otherwise
  // vanish, so those are collected and shown in their own section below.
  const flagsFor = (key: string) => doc.statuteFlags.filter((f) => f.fieldKey === key);
  const shownFieldKeys = new Set(FIELD_GROUPS.flatMap((g) => g.fields.map((f) => f.key)));
  const unattachedFlags = doc.statuteFlags.filter((f) => f.fieldKey == null || !shownFieldKeys.has(f.fieldKey));

  // Source-quality header (§9): make must-have #1 demonstrable.
  const ocrMeans = doc.pages.map((p) => p.ocrConfMean).filter((x): x is number => x != null);
  const meanOcr = ocrMeans.length ? ocrMeans.reduce((a, b) => a + b, 0) / ocrMeans.length : null;
  const band = ocrBand(meanOcr);
  const provenance =
    doc.provenanceQuality === "degraded"
      ? "Scanned document, read by OCR"
      : doc.provenanceQuality === "text_only"
        ? "Plain-text / Word document"
        : "Born-digital PDF, text read directly";

  return (
    <div>
      <div className="mb-4">
        <Link to="/" className="text-sm text-muted hover:text-ink">
          ← Portfolio
        </Link>
        <div className="mt-1 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-ink">{doc.filename}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
              <StatusPill status={doc.status} />
              {doc.docType && <span>{DOC_TYPE_LABELS[doc.docType] ?? doc.docType}</span>}
              {doc.counterparty && <span>· {doc.counterparty}</span>}
              {doc.pageCount != null && <span>· {doc.pageCount} pages</span>}
            </div>
          </div>
          <button
            className="btn btn-sm"
            onClick={async () => {
              if (!confirm("Remove this document and its extracted data?")) return;
              await api.deleteDocument(id);
              qc.invalidateQueries({ queryKey: ["documents"] });
              navigate("/");
            }}
          >
            Remove
          </button>
        </div>

        {/* Source quality — primes the reader to expect lower certainty on scans. */}
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 rounded border border-rule bg-surface px-3 py-2 text-sm">
          <span className="font-medium text-ink">Source: {provenance}</span>
          {doc.ocrApplied && band && (
            <span className={band.tone}>OCR confidence on this document is {band.word}.</span>
          )}
          {doc.provenanceQuality === "degraded" && (
            <span className="text-muted">Values on scanned pages are less certain — verify against the image.</span>
          )}
        </div>

        {doc.warnings.length > 0 && (
          <ul className="mt-2 space-y-1">
            {doc.warnings.map((w, i) => (
              <li key={i} className="rounded border border-warn/30 bg-warnbg px-3 py-1.5 text-sm text-warn">
                {w}
              </li>
            ))}
          </ul>
        )}
      </div>

      {isProcessing ? (
        <div className="panel p-8 text-center">
          <p className="text-lg font-medium text-ink">Reading this document…</p>
          <p className="mt-1 text-muted">{doc.job?.stage ?? "queued"}</p>
          <div className="mx-auto mt-3 h-2 max-w-sm overflow-hidden rounded bg-rule">
            <div className="h-full bg-navy transition-all" style={{ width: `${Math.max(6, Math.round((doc.job?.progress ?? 0) * 100))}%` }} />
          </div>
        </div>
      ) : notContract ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="panel border-warn/40 bg-warnbg p-6">
            <h2 className="text-lg font-semibold text-warn">Not analysed</h2>
            <p className="mt-2 text-ink">
              This looks like an invoice, not an agreement. AITHENA does not extract contract terms from it, because doing
              so would invent obligations that are not there.
            </p>
            <p className="mt-2 text-sm text-muted">
              You can still read the pages on the right. If this really is a contract, re-upload a clearer copy.
            </p>

            {/* An invoice is not analysed as a contract, but it can still be asked
                the one question that matters about it: is there a contract behind
                it? Kept inside the "not analysed" panel so it never reads as
                contract extraction. */}
            <div className="mt-5 border-t border-warn/30 pt-4">
              <InvoiceMatch documentId={id} />
            </div>
          </div>
          <div ref={viewerRef}>
            <PageViewer documentId={id} pages={doc.pages} currentPage={currentPage} onPageChange={setCurrentPage} highlights={[]} />
          </div>
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          {/* Left: the seven field groups, always all shown unless filtered. */}
          <div className="space-y-5">
            <div className="panel flex flex-wrap items-center gap-2 px-4 py-3">
              <span className="text-sm font-medium text-muted">Show</span>
              {LABEL_ORDER.map((l) => {
                const m = LABEL_META[l];
                const on = isShown(l);
                return (
                  <button
                    key={l}
                    onClick={() => toggle(l)}
                    aria-pressed={on}
                    title={m.label}
                    className={`inline-flex items-center gap-1.5 rounded border px-2 py-1 text-sm font-medium transition-colors ${
                      on ? `${m.border} ${m.bg} ${m.text}` : "border-rule bg-surface text-faint line-through"
                    }`}
                  >
                    <span aria-hidden className="grid h-4 w-4 place-items-center rounded-sm border border-current font-bold leading-none">
                      {m.glyph}
                    </span>
                    {m.short}
                    <span className="tnum font-normal">({counts[l]})</span>
                  </button>
                );
              })}
              {shown.length === 0 && <span className="text-sm text-warn">Everything is hidden.</span>}
            </div>

            {FIELD_GROUPS.map((group) => {
              const visibleDefs = group.fields.filter((def) =>
                labelsForKey(def.key).some(isShown),
              );
              return (
                <section key={group.key} className="panel p-4">
                  <h2 className="mb-3 text-base font-semibold text-ink">{group.title}</h2>
                  {visibleDefs.length === 0 ? (
                    <p className="text-sm text-faint">
                      {group.fields.length} field{group.fields.length === 1 ? "" : "s"} hidden by the filter.
                    </p>
                  ) : (
                    <div className="space-y-2">
                      {visibleDefs.map((def) => {
                        const matches = doc.fields.filter((f) => f.fieldKey === def.key);
                        // Additive: the flag sits below the value, and the value
                        // keeps its own badge and wording either way.
                        const notes = flagsFor(def.key).map((f) => (
                          <StatuteFlagNote key={f.id} flag={f} />
                        ));
                        if (matches.length === 0) {
                          return (
                            <div key={def.key} className="space-y-2">
                              <div className={`rounded-r ${LABEL_META.na.barBorder} bg-surface px-3 py-2.5`}>
                                <div className="flex items-start justify-between gap-3">
                                  <span className="text-sm font-medium text-muted">{def.label}</span>
                                  <ConfidenceBadge label="na" size="sm" />
                                </div>
                                <p className="text-muted">Not extracted.</p>
                              </div>
                              {notes}
                            </div>
                          );
                        }
                        return (
                          <div key={def.key} className="space-y-2">
                            {matches
                              .filter((field) => isShown(labelForField(field)))
                              .map((field) => (
                                <div key={field.id}>
                                  <FieldValue
                                    label={def.label}
                                    field={field}
                                    page={field.citationPage ?? null}
                                    active={activeFieldId === field.id}
                                    onCite={cite}
                                  />
                                  {/* Additive, like the statute notes: the field keeps
                                      its own value and badge, and the comparison to the
                                      portfolio sits underneath it. Renders nothing
                                      unless there is a real average to compare against. */}
                                  {field.valueVerbatim && (
                                    <BenchmarkLine fieldKey={def.key} documentId={id} />
                                  )}
                                </div>
                              ))}
                            {notes}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </section>
              );
            })}

            {/* Not filtered by the three-label control: these are not extractions,
                so "Quoted / Inferred / NA" has no bearing on them. */}
            <StatutePanel defaults={doc.statutoryDefaults} />

            {unattachedFlags.length > 0 && (
              <section className="panel border-navy/30 p-4">
                <h2 className="text-base font-semibold text-ink">Other clauses a statute touches</h2>
                <p className="mt-1 text-sm text-muted">
                  These clauses engage legislation but do not correspond to any field above, so they are listed on their
                  own rather than dropped.
                </p>
                <div className="mt-3 space-y-2">
                  {unattachedFlags.map((f) => (
                    <StatuteFlagNote key={f.id} flag={f} />
                  ))}
                </div>
              </section>
            )}
          </div>

          {/* Right: page image + overlay, sticky so citations stay in view. */}
          <div ref={viewerRef} className="lg:sticky lg:top-4 lg:self-start">
            <p className="mb-2 text-sm text-muted">
              Click any value on the left to highlight the exact text it came from.
            </p>
            <PageViewer
              documentId={id}
              pages={doc.pages}
              currentPage={currentPage}
              onPageChange={setCurrentPage}
              highlights={highlights}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div>
      <Skeleton className="mb-2 h-8 w-96" />
      <Skeleton className="mb-6 h-10 w-full" />
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
        <Skeleton className="h-[36rem]" />
      </div>
    </div>
  );
}
