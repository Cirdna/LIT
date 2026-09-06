import { useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type AnchorDTO, type FieldDTO, type BenchmarkDTO, type InvoiceDTO } from "../lib/api";
import { DOC_TYPE_LABELS, FIELD_GROUPS } from "../lib/domain";
import { formatDate } from "../lib/format";
import { ConfidenceBadge, ocrBand, coarseLabel, COARSE_LABELS, CoarseTag, type CoarseLabel } from "../lib/confidence";
import { FieldValue } from "../components/FieldValue";
import { PageViewer } from "../components/PageViewer";
import { ApplicableStatutes } from "../components/ApplicableStatutes";
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
  // Coarse-label filter (UI-2). Empty set = no filter, show everything.
  const [labelFilter, setLabelFilter] = useState<Set<CoarseLabel>>(new Set());
  function toggleLabel(l: CoarseLabel) {
    setLabelFilter((prev) => {
      const next = new Set(prev);
      if (next.has(l)) next.delete(l);
      else next.add(l);
      return next;
    });
  }

  const detail = useQuery({
    queryKey: ["document", id],
    queryFn: () => api.document(id),
    refetchInterval: (q) => (PROCESSING.has(q.state.data?.status ?? "") ? 2000 : false),
  });

  const benchmarks = useQuery({
    queryKey: ["benchmarks", id],
    queryFn: () => api.benchmarks(id),
    enabled:
      !!detail.data &&
      !PROCESSING.has(detail.data.status) &&
      detail.data.docType !== "not_a_contract",
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
  const isInvoice = doc.docType === "invoice" && !!doc.invoice;
  const notContract = doc.docType === "not_a_contract";

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
      ) : isInvoice ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <InvoicePanel invoice={doc.invoice!} />
          <div ref={viewerRef}>
            <PageViewer documentId={id} pages={doc.pages} currentPage={currentPage} onPageChange={setCurrentPage} highlights={[]} />
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
          </div>
          <div ref={viewerRef}>
            <PageViewer documentId={id} pages={doc.pages} currentPage={currentPage} onPageChange={setCurrentPage} highlights={[]} />
          </div>
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          {/* Left: field groups, with a coarse-label filter (UI-2). */}
          <div className="space-y-5">
            {benchmarks.data && benchmarks.data.benchmarks.length > 0 && (
              <section className="panel p-4">
                <h2 className="mb-1 text-base font-semibold text-ink">Portfolio benchmarks</h2>
                <p className="mb-3 text-xs text-muted">
                  How this contract compares to the live average across your active contracts. Risk is a
                  separate axis from how confident we are in the value.
                </p>
                <div className="space-y-2">
                  {benchmarks.data.benchmarks.map((b) => (
                    <BenchmarkRow key={b.category} b={b} />
                  ))}
                </div>
              </section>
            )}
            <div className="panel flex flex-wrap items-center gap-2 p-3 text-sm">
              <span className="font-medium text-muted">Filter by label:</span>
              {COARSE_LABELS.map((lbl) => {
                const on = labelFilter.has(lbl);
                return (
                  <button
                    key={lbl}
                    onClick={() => toggleLabel(lbl)}
                    aria-pressed={on}
                    className={`rounded border px-1.5 py-0.5 ${on ? "border-navy ring-1 ring-navy" : "border-rule opacity-70 hover:opacity-100"}`}
                  >
                    <CoarseTag label={lbl} />
                  </button>
                );
              })}
              {labelFilter.size > 0 ? (
                <button onClick={() => setLabelFilter(new Set())} className="ml-auto text-navy">
                  Clear filter
                </button>
              ) : (
                <span className="ml-auto text-faint">Showing all</span>
              )}
            </div>
            {FIELD_GROUPS.map((group) => {
              const active = labelFilter.size > 0;
              const rows = group.fields.map((def) => {
                const matches = doc.fields.filter((f) => f.fieldKey === def.key);
                const label: CoarseLabel = matches.length === 0 ? "NA" : coarseLabel(matches[0]);
                return { def, matches, label };
              });
              const shown = active ? rows.filter((r) => labelFilter.has(r.label)) : rows;
              const hidden = rows.length - shown.length;
              return (
                <section key={group.key} className="panel p-4">
                  <h2 className="mb-3 text-base font-semibold text-ink">{group.title}</h2>
                  <div className="space-y-2">
                    {shown.map(({ def, matches }) =>
                      matches.length === 0 ? (
                        <div key={def.key} className="rounded-r border-l-4 border-l-rule bg-surface px-3 py-2.5">
                          <span className="text-sm font-medium text-muted">{def.label}</span>
                          <p className="text-muted">Not extracted.</p>
                        </div>
                      ) : (
                        matches.map((field) => (
                          <FieldValue
                            key={field.id}
                            label={def.label}
                            field={field}
                            page={field.citationPage ?? null}
                            active={activeFieldId === field.id}
                            onCite={cite}
                          />
                        ))
                      ),
                    )}
                    {shown.length === 0 ? (
                      <p className="text-sm text-muted">All {rows.length} fields hidden by filter.</p>
                    ) : (
                      hidden > 0 && <p className="text-xs text-faint">{hidden} more hidden by filter.</p>
                    )}
                  </div>
                </section>
              );
            })}

            {/* Per-contract statutory overlay (Singapore statute knowledge store). */}
            <ApplicableStatutes documentId={id} />
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

// Risk is deliberately its own visual language (filled shapes + a word), so it
// never reads as a confidence tier. Colour still travels with a glyph.
const RISK_META: Record<BenchmarkDTO["risk"], { word: string; glyph: string; cls: string }> = {
  green: { word: "In line", glyph: "●", cls: "text-ok bg-okbg border-ok/40" },
  yellow: { word: "Caution", glyph: "▲", cls: "text-warn bg-warnbg border-warn/50" },
  red: { word: "Risk", glyph: "■", cls: "text-alert bg-alertbg border-alert/50" },
};

function RiskChip({ risk }: { risk: BenchmarkDTO["risk"] }) {
  const m = RISK_META[risk];
  return (
    <span className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-xs font-medium ${m.cls}`}>
      <span aria-hidden>{m.glyph}</span>
      {m.word}
    </span>
  );
}

function BenchmarkRow({ b }: { b: BenchmarkDTO }) {
  const rel =
    b.deviation === 0
      ? "at the portfolio average"
      : `${Math.abs(b.deviation)} ${b.unit} ${b.deviation < 0 ? "below" : "above"} portfolio average of ${b.average} ${b.unit}`;
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-rule bg-surface px-3 py-2">
      <div>
        <div className="text-sm font-medium text-ink">{b.label}</div>
        <div className="text-sm text-muted">
          <span className="font-semibold text-ink">
            {b.value} {b.unit}
          </span>{" "}
          · {rel}
          {b.sampleSize < 3 && <span className="text-faint"> · small sample ({b.sampleSize})</span>}
        </div>
      </div>
      <RiskChip risk={b.risk} />
    </div>
  );
}

// Invoice reconciliation result → a plain phrase + a tone. Green only for a
// confirmed in-window match; everything else routes to review.
const MATCH_META: Record<
  InvoiceDTO["match"] extends null ? never : NonNullable<InvoiceDTO["match"]>["status"],
  { title: string; cls: string; glyph: string }
> = {
  HIGH_CONFIDENCE_MATCH: { title: "High confidence match", cls: "border-ok/40 bg-okbg text-ok", glyph: "✓" },
  MISSING_CONTRACT_ROGUE: { title: "Missing contract — rogue invoice", cls: "border-alert/50 bg-alertbg text-alert", glyph: "!" },
  MULTIPLE_CONTRACTS_REVIEW: { title: "Multiple contracts — manual review required", cls: "border-warn/50 bg-warnbg text-warn", glyph: "?" },
  DATE_MISMATCH_REVIEW: { title: "Date mismatch — manual review required", cls: "border-warn/50 bg-warnbg text-warn", glyph: "~" },
};

function InvoicePanel({ invoice }: { invoice: InvoiceDTO }) {
  const { header, lineItems, match } = invoice;
  const money = (n: number | null) => (n == null ? "—" : `${header.currency ? header.currency + " " : ""}${n.toLocaleString()}`);

  return (
    <div className="space-y-5">
      {/* Reconciliation verdict first — it's the point of the feature. */}
      {match && (
        <section className={`panel border p-4 ${MATCH_META[match.status].cls}`}>
          <div className="flex items-center gap-2">
            <span aria-hidden className="grid h-5 w-5 place-items-center rounded border border-current font-bold">
              {MATCH_META[match.status].glyph}
            </span>
            <h2 className="text-base font-semibold">{MATCH_META[match.status].title}</h2>
          </div>
          {match.contract && (
            <p className="mt-2 text-sm text-ink">
              Matched to{" "}
              <Link to={`/documents/${match.contract.id}`} className="font-medium text-navy hover:underline">
                {match.contract.counterparty ?? match.contract.filename}
              </Link>
            </p>
          )}
          {match.reasons.length > 0 && (
            <ul className="mt-2 space-y-1 text-sm text-ink">
              {match.reasons.map((r, i) => (
                <li key={i} className="flex gap-1.5">
                  <span aria-hidden>•</span>
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <section className="panel p-4">
        <h2 className="mb-3 text-base font-semibold text-ink">Invoice</h2>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <Detail label="From (vendor)" value={header.billingFrom} />
          <Detail label="To (customer)" value={header.billingTo} />
          <Detail label="Invoice date" value={header.invoiceDate ? formatDate(header.invoiceDate) : null} />
          <Detail label="Invoice no." value={header.invoiceNumber} />
          <Detail label="Total" value={money(header.total)} />
          <div>
            <dt className="text-muted">Extraction</dt>
            <dd className="mt-0.5">
              <ConfidenceBadge tier={header.confidenceTier} size="sm" />
            </dd>
          </div>
        </dl>
      </section>

      {lineItems.length > 0 && (
        <section className="panel p-4">
          <h2 className="mb-3 text-base font-semibold text-ink">Line items</h2>
          <table className="w-full text-left text-sm">
            <thead className="text-muted">
              <tr>
                <th className="py-1 font-medium">Description</th>
                <th className="py-1 text-right font-medium">Qty</th>
                <th className="py-1 text-right font-medium">Amount</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {lineItems.map((li) => (
                <tr key={li.id}>
                  <td className="py-1.5 text-ink">{li.description}</td>
                  <td className="py-1.5 text-right tnum text-muted">{li.quantity ?? "—"}</td>
                  <td className="py-1.5 text-right tnum text-ink">{money(li.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt className="text-muted">{label}</dt>
      <dd className="mt-0.5 text-ink">{value ?? "—"}</dd>
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
