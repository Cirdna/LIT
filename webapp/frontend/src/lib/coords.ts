// THE coordinate transform. Getting this wrong is the most likely visual bug and
// it makes the extraction look broken, so it lives in exactly one place.
//
// Bounding boxes are stored in PDF POINTS with a TOP-LEFT origin. Page images are
// rendered at `image_dpi`. One point is 1/72 inch, so:
//
//     pixels = points * (dpi / 72)
//
// The overlay SVG uses the image's natural pixel size as its viewBox, so boxes
// map 1:1 onto the <img> at any display width.

export type Bbox = { x0: number; y0: number; x1: number; y1: number };

export function scaleFor(dpi: number | null): number {
  return (dpi ?? 72) / 72;
}

/** Natural pixel size of a rendered page image. */
export function imagePixelSize(widthPts: number, heightPts: number, dpi: number | null) {
  const s = scaleFor(dpi);
  return { width: widthPts * s, height: heightPts * s };
}

/** A bbox (PDF points) as an image-pixel rectangle. */
export function bboxToPixelRect(bbox: Bbox, dpi: number | null) {
  const s = scaleFor(dpi);
  return {
    x: bbox.x0 * s,
    y: bbox.y0 * s,
    width: (bbox.x1 - bbox.x0) * s,
    height: (bbox.y1 - bbox.y0) * s,
  };
}
