import type { AnchorDTO, PageDTO } from "../lib/api";
import { pageImageUrl } from "../lib/api";
import { bboxToPixelRect, imagePixelSize } from "../lib/coords";

// Right pane of the document detail: the rendered page with a bounding-box
// overlay. The SVG viewBox is the image's natural pixel size, so highlight rects
// (computed by the ONE coordinate transform in lib/coords) sit exactly on the
// words at any display width.
export function PageViewer({
  documentId,
  pages,
  currentPage,
  onPageChange,
  highlights,
}: {
  documentId: string;
  pages: PageDTO[];
  currentPage: number;
  onPageChange: (p: number) => void;
  highlights: AnchorDTO[];
}) {
  const page = pages.find((p) => p.pageNumber === currentPage) ?? pages[0];
  if (!page) {
    return (
      <div className="panel grid h-64 place-items-center text-muted">
        Page images are not ready yet.
      </div>
    );
  }

  const dpi = page.imageDpi;
  const size = imagePixelSize(page.width, page.height, dpi);
  const onThisPage = highlights.filter((h) => h.page === currentPage);

  return (
    <div className="panel overflow-hidden">
      <div className="flex items-center justify-between border-b border-rule bg-paper px-3 py-2 text-sm">
        <button
          className="btn btn-sm"
          onClick={() => onPageChange(Math.max(1, currentPage - 1))}
          disabled={currentPage <= 1}
        >
          ← Prev
        </button>
        <span className="tnum text-muted">
          Page {currentPage} of {pages.length}
          {page.pageRole && page.pageRole !== "operative" ? ` · ${page.pageRole}` : ""}
        </span>
        <button
          className="btn btn-sm"
          onClick={() => onPageChange(Math.min(pages.length, currentPage + 1))}
          disabled={currentPage >= pages.length}
        >
          Next →
        </button>
      </div>

      <div className="relative bg-[#e9eaec] p-3">
        <div className="relative mx-auto" style={{ maxWidth: size.width }}>
          {page.hasImage ? (
            <img
              src={pageImageUrl(documentId, currentPage)}
              alt={`Page ${currentPage}`}
              className="block w-full border border-rule"
              width={size.width}
              height={size.height}
            />
          ) : (
            <div className="grid aspect-[8.5/11] w-full place-items-center border border-rule bg-surface text-muted">
              Image not available
            </div>
          )}

          <svg
            className="pointer-events-none absolute inset-0 h-full w-full"
            viewBox={`0 0 ${size.width} ${size.height}`}
            preserveAspectRatio="none"
          >
            {onThisPage.map((h) => {
              const r = bboxToPixelRect(h.bbox, dpi);
              return (
                <rect
                  key={h.lineId}
                  x={r.x - 2}
                  y={r.y - 2}
                  width={r.width + 4}
                  height={r.height + 4}
                  rx={2}
                  fill="rgba(31,58,95,0.18)"
                  stroke="#1f3a5f"
                  strokeWidth={2}
                />
              );
            })}
          </svg>
        </div>
      </div>
    </div>
  );
}
