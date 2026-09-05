import { useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type AnchorDTO, type FieldDTO } from "../lib/api";
import { DOC_TYPE_LABELS, FIELD_GROUPS } from "../lib/domain";
import { ocrBand } from "../lib/confidence";
import { FieldValue } from "../components/FieldValue";
import { PageViewer } from "../components/PageViewer";
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
          </div>
          <div ref={viewerRef}>
            <PageViewer documentId={id} pages={doc.pages} currentPage={currentPage} onPageChange={setCurrentPage} highlights={[]} />
          </div>
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          {/* Left: the seven field groups, always all shown. */}
          <div className="space-y-5">
            {FIELD_GROUPS.map((group) => (
              <section key={group.key} className="panel p-4">
                <h2 className="mb-3 text-base font-semibold text-ink">{group.title}</h2>
                <div className="space-y-2">
                  {group.fields.map((def) => {
                    const matches = doc.fields.filter((f) => f.fieldKey === def.key);
                    if (matches.length === 0) {
                      return (
                        <div key={def.key} className="rounded-r border-l-4 border-l-rule bg-surface px-3 py-2.5">
                          <span className="text-sm font-medium text-muted">{def.label}</span>
                          <p className="text-muted">Not extracted.</p>
                        </div>
                      );
                    }
                    return matches.map((field) => (
                      <FieldValue
                        key={field.id}
                        label={def.label}
                        field={field}
                        page={field.citationPage ?? null}
                        active={activeFieldId === field.id}
                        onCite={cite}
                      />
                    ));
                  })}
                </div>
              </section>
            ))}
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
