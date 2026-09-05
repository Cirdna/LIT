// Exact-name party matching, for the Node side.
//
// THIS IS A PORT, NOT A NEW MATCHER. Every rule below is transcribed from
// src/pdf_analyzer/pipeline.py (`_PARTY_SEPARATORS`, `_PARTY_EDGE_CHARS`,
// `_exact_party_key`), which is what Fix 2's conflict detection already uses to
// build counterparty join keys. Invoice matching deliberately reuses it so that
// "the same party" means one thing in this product rather than two.
//
// It inherits Fix 2's disclosed limitation as well: exact name only, no fuzzy
// matching, no suffix normalisation. "Acme Industries Pte Ltd" and "Acme
// Industrial Ltd" produce different keys and never match. For invoices that is
// stricter than reality — a biller often abbreviates itself — and the honest
// consequence is more MISSING CONTRACT results than a fuzzy matcher would give.
// That limitation is reported to the user in the response rather than papered
// over here, because introducing fuzzy matching on this side only would mean the
// invoice feature and the conflict engine disagreed about identity.

/** pipeline.py:_PARTY_SEPARATORS — "and" or ";" only. Commas are NOT separators. */
const PARTY_SEPARATORS = /\s+and\s+|;/i;

/** pipeline.py:_PARTY_EDGE_CHARS — quotes, brackets, trailing punctuation. */
const PARTY_EDGE_CHARS = new Set([...'"“”\'()[] \t\n.,:;']);

function stripEdges(raw: string): string {
  let start = 0;
  let end = raw.length;
  while (start < end && PARTY_EDGE_CHARS.has(raw[start]!)) start += 1;
  while (end > start && PARTY_EDGE_CHARS.has(raw[end - 1]!)) end -= 1;
  return raw.slice(start, end);
}

/**
 * pipeline.py:_exact_party_key — collapse whitespace, case-fold, minimum length 3.
 * No suffix is ever removed, so two spellings of one company stay unmerged.
 */
export function exactPartyKey(raw: string): string | null {
  const cleaned = stripEdges(raw).split(/\s+/).filter(Boolean).join(" ");
  if (cleaned.length < 3) return null;
  return `party:${cleaned.toLowerCase()}`;
}

/**
 * Every party key a quoted span yields. The split is deliberately dumb, exactly
 * as in the Python: a prose span produces one usable name and some junk, and junk
 * keys are harmless because they match nothing.
 */
export function partyKeysFrom(text: string): { key: string; raw: string }[] {
  const out: { key: string; raw: string }[] = [];
  const seen = new Set<string>();
  for (const part of text.split(PARTY_SEPARATORS)) {
    const key = exactPartyKey(part);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push({ key, raw: stripEdges(part) });
  }
  return out;
}
