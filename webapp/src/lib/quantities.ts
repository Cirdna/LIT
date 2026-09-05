// Turning quoted contract text into numbers, for filtering and benchmarking.
//
// WHY THIS EXISTS. The real extraction path writes `value_normalized: undefined`
// (scripts/real-worker.ts:139), so there are no machine-readable dates or
// durations in the database for documents it processed. Benchmarking and date
// filtering need numbers. The choice is therefore between parsing the quoted text
// and not shipping the feature.
//
// THE RULE THAT KEEPS THIS HONEST: a value that cannot be parsed is EXCLUDED and
// COUNTED, never guessed. Callers must report the excluded count, so an average
// computed from 3 of 11 contracts can never masquerade as an average over the
// portfolio. `value_normalized` is always preferred when a worker did supply it.
import type { ExtractedField } from "@prisma/client";

/** Months are converted at 30 days — the contract convention, not a calendar one. */
export const DAYS_PER_MONTH = 30;
/** Years at 365; no leap-year handling, because notice periods are not astronomy. */
export const DAYS_PER_YEAR = 365;

const NUMBER_WORDS: Record<string, number> = {
  one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9,
  ten: 10, eleven: 11, twelve: 12, fifteen: 15, twenty: 20, thirty: 30, forty: 40,
  fortyfive: 45, sixty: 60, ninety: 90,
};

const MONTH_NAMES: Record<string, number> = {
  jan: 1, january: 1, feb: 2, february: 2, mar: 3, march: 3, apr: 4, april: 4,
  may: 5, jun: 6, june: 6, jul: 7, july: 7, aug: 8, august: 8, sep: 9, sept: 9,
  september: 9, oct: 10, october: 10, nov: 11, november: 11, dec: 12, december: 12,
};

/**
 * A duration in days, or null.
 *
 * Contract drafting habitually writes the number twice — "ninety (90) days" — so
 * a parenthesised digit is preferred when present and the word form is the
 * fallback. Anything with no recognisable unit returns null.
 */
export function parseDurationDays(text: string): number | null {
  const t = text.toLowerCase();

  // "(90) days", "90 days", "ninety (90) days"
  const unit = /(day|week|month|year)s?\b/.exec(t);
  if (!unit) return null;

  // Prefer a digit that appears before the unit; parenthesised form wins.
  const before = t.slice(0, unit.index);
  const paren = [...before.matchAll(/\((\d{1,4})\)/g)].pop();
  const plain = [...before.matchAll(/(\d{1,4})/g)].pop();
  let n: number | null = paren ? Number(paren[1]) : plain ? Number(plain[1]) : null;

  if (n == null) {
    const word = [...before.matchAll(/([a-z]+)/g)].map((m) => m[1]!).reverse()
      .find((w) => w in NUMBER_WORDS);
    if (word) n = NUMBER_WORDS[word]!;
  }
  if (n == null || !Number.isFinite(n) || n <= 0) return null;

  switch (unit[1]) {
    case "day": return n;
    case "week": return n * 7;
    case "month": return n * DAYS_PER_MONTH;
    case "year": return n * DAYS_PER_YEAR;
    default: return null;
  }
}

/** An ISO date (YYYY-MM-DD), or null. Handles ISO, "1 March 2026", "March 1, 2026". */
export function parseIsoDate(text: string): string | null {
  const iso = /\b(\d{4})-(\d{1,2})-(\d{1,2})\b/.exec(text);
  if (iso) return pad(Number(iso[1]), Number(iso[2]), Number(iso[3]));

  const dmy = /\b(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b/.exec(text);
  if (dmy) {
    const m = MONTH_NAMES[dmy[2]!.toLowerCase()];
    if (m) return pad(Number(dmy[3]), m, Number(dmy[1]));
  }

  const mdy = /\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b/.exec(text);
  if (mdy) {
    const m = MONTH_NAMES[mdy[1]!.toLowerCase()];
    if (m) return pad(Number(mdy[3]), m, Number(mdy[2]));
  }
  return null;
}

function pad(y: number, m: number, d: number): string | null {
  if (m < 1 || m > 12 || d < 1 || d > 31) return null;
  return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

export function daysBetween(fromIso: string, toIso: string): number {
  const a = Date.parse(fromIso + "T00:00:00Z");
  const b = Date.parse(toIso + "T00:00:00Z");
  return Math.round((b - a) / 86_400_000);
}

type Normalized = { days?: unknown; months?: unknown; date?: unknown } | null;

/**
 * The duration of a field in days, preferring a worker-supplied normalised value
 * over parsing. Returns the source so a caller can tell the reader which it was.
 */
export function fieldDurationDays(
  f: Pick<ExtractedField, "valueVerbatim" | "valueNormalized">,
): { days: number; from: "normalized" | "parsed" } | null {
  const n = f.valueNormalized as Normalized;
  if (n && typeof n === "object") {
    if (typeof n.days === "number") return { days: n.days, from: "normalized" };
    if (typeof n.months === "number") return { days: n.months * DAYS_PER_MONTH, from: "normalized" };
  }
  if (!f.valueVerbatim) return null;
  const parsed = parseDurationDays(f.valueVerbatim);
  return parsed == null ? null : { days: parsed, from: "parsed" };
}

/** The date of a field as ISO, preferring a worker-supplied normalised value. */
export function fieldDateIso(
  f: Pick<ExtractedField, "valueVerbatim" | "valueNormalized">,
): { date: string; from: "normalized" | "parsed" } | null {
  const n = f.valueNormalized as Normalized;
  if (n && typeof n === "object" && typeof n.date === "string") {
    const d = parseIsoDate(n.date);
    if (d) return { date: d, from: "normalized" };
  }
  if (!f.valueVerbatim) return null;
  const parsed = parseIsoDate(f.valueVerbatim);
  return parsed == null ? null : { date: parsed, from: "parsed" };
}
