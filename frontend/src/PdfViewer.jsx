import React, { useRef, useState, useCallback } from "react";
import { Document, Page, pdfjs } from "react-pdf";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

/**
 * Stage 5: PDF viewer click-to-jump integration.
 *
 * Given a selected CUAD extraction (with source.page + location.bbox_1000),
 * jumps the viewer to that page and draws a glowing SVG overlay over the
 * exact supporting text, scaling the normalized 0-1000 bbox to the page's
 * currently-rendered pixel dimensions (per gameplan Stage 5 / Technical
 * Conversion Specifications #3).
 */
export default function PdfViewer({ pdfUrl, selectedExtraction }) {
  const [numPages, setNumPages] = useState(null);
  const pageRefs = useRef({});
  const [renderedSize, setRenderedSize] = useState({});

  const targetPage = selectedExtraction?.source?.page ?? null;

  const onDocumentLoadSuccess = useCallback(({ numPages }) => {
    setNumPages(numPages);
  }, []);

  const onPageRenderSuccess = useCallback((pageNumber, page) => {
    const canvas = pageRefs.current[pageNumber]?.querySelector("canvas");
    if (canvas) {
      setRenderedSize((prev) => ({
        ...prev,
        [pageNumber]: { width: canvas.width, height: canvas.height },
      }));
    }
  }, []);

  React.useEffect(() => {
    if (targetPage != null) {
      const el = pageRefs.current[targetPage];
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [targetPage, selectedExtraction]);

  if (!pdfUrl) return <div className="pdf-viewer-empty">No document loaded.</div>;

  return (
    <div className="pdf-viewer">
      <Document file={pdfUrl} onLoadSuccess={onDocumentLoadSuccess} loading="Loading PDF...">
        {Array.from({ length: numPages || 0 }, (_, i) => i + 1).map((pageNumber) => (
          <div
            key={pageNumber}
            ref={(el) => (pageRefs.current[pageNumber] = el)}
            style={{ position: "relative", marginBottom: 16 }}
          >
            <Page
              pageNumber={pageNumber}
              width={900}
              onRenderSuccess={(page) => onPageRenderSuccess(pageNumber, page)}
            />
            {targetPage === pageNumber && renderedSize[pageNumber] && (
              <HighlightOverlay
                bbox1000={selectedExtraction.location.bbox_1000}
                canvasSize={renderedSize[pageNumber]}
              />
            )}
          </div>
        ))}
      </Document>
    </div>
  );
}

/**
 * Scales a normalized [x_min, y_min, x_max, y_max] (0-1000 grid) bbox to the
 * page's current rendered canvas dimensions and renders a glowing SVG box
 * over it. Mirrors drawHighlightOverlay() from the gameplan's technical spec.
 */
function HighlightOverlay({ bbox1000, canvasSize }) {
  const [xMin, yMin, xMax, yMax] = bbox1000;

  const scaleX = canvasSize.width / 1000;
  const scaleY = canvasSize.height / 1000;

  const left = xMin * scaleX;
  const top = yMin * scaleY;
  const width = (xMax - xMin) * scaleX;
  const height = (yMax - yMin) * scaleY;

  return (
    <svg
      style={{
        position: "absolute",
        left: 0,
        top: 0,
        width: canvasSize.width,
        height: canvasSize.height,
        pointerEvents: "none",
      }}
    >
      <defs>
        <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="4" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <rect
        x={left}
        y={top}
        width={width}
        height={height}
        fill="rgba(255, 200, 0, 0.18)"
        stroke="#ffb300"
        strokeWidth={2}
        filter="url(#glow)"
        rx={3}
      />
    </svg>
  );
}
