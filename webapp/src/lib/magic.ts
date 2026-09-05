// Validate uploads by magic bytes, not by file extension (§8). We only need to
// sniff the first few dozen bytes, so the upload handler passes us the opening
// chunk of the stream.
//
// Accepted set: .pdf .docx .png .jpg .tiff .txt

export const ACCEPTED_FORMATS = ".pdf, .docx, .png, .jpg/.jpeg, .tiff, .txt";

export type Sniffed = { mime: string; ext: string } | null;

function startsWith(buf: Buffer, sig: number[]): boolean {
  if (buf.length < sig.length) return false;
  return sig.every((b, i) => buf[i] === b);
}

/** OOXML (docx) is a ZIP whose first local entry is `[Content_Types].xml`. */
function isOoxml(buf: Buffer): boolean {
  if (!startsWith(buf, [0x50, 0x4b, 0x03, 0x04])) return false; // "PK\x03\x04"
  if (buf.length < 30) return false;
  const nameLen = buf.readUInt16LE(26);
  const name = buf.subarray(30, 30 + nameLen).toString("latin1");
  return name === "[Content_Types].xml";
}

/** Heuristic for plain text: decodes as UTF-8, no NULs, mostly printable. */
function looksLikeText(buf: Buffer): boolean {
  if (buf.length === 0) return true; // an empty .txt is still text
  if (buf.includes(0x00)) return false;
  const decoded = buf.toString("utf8");
  if (decoded.includes("�")) return false; // U+FFFD means invalid UTF-8
  let printable = 0;
  for (const ch of decoded) {
    const c = ch.codePointAt(0)!;
    if (c === 9 || c === 10 || c === 13 || c >= 32) printable++;
  }
  return printable / decoded.length > 0.95;
}

export function sniff(buf: Buffer): Sniffed {
  if (startsWith(buf, [0x25, 0x50, 0x44, 0x46])) return { mime: "application/pdf", ext: "pdf" }; // %PDF
  if (startsWith(buf, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))
    return { mime: "image/png", ext: "png" };
  if (startsWith(buf, [0xff, 0xd8, 0xff])) return { mime: "image/jpeg", ext: "jpg" };
  if (startsWith(buf, [0x49, 0x49, 0x2a, 0x00]) || startsWith(buf, [0x4d, 0x4d, 0x00, 0x2a]))
    return { mime: "image/tiff", ext: "tiff" };
  if (isOoxml(buf))
    return {
      mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      ext: "docx",
    };
  if (looksLikeText(buf)) return { mime: "text/plain", ext: "txt" };
  return null;
}
