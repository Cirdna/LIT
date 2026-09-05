// Dates as a person reads them, and the "how long until I must act" arithmetic
// the calendar is built around.
//
// ONE format everywhere: "8 Sep 2026". Every date the user sees goes through
// `formatDate`, `formatDateValue` or `formatDatesInText` — a screen that formats
// its own dates is how "2026-09-08" ends up next to "8 Sep 2026" in one view.
//
// The month table is explicit rather than delegated to Intl on purpose: en-GB
// renders September as "Sept", and the width of a date should not depend on
// which month it is or which ICU version the demo machine ships.
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// Dates are date-only and UTC throughout this product (see calendar.ts), so they
// are read back in UTC — a local-timezone read would shift a deadline by a day.
export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso + (iso.length === 10 ? "T00:00:00Z" : ""));
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

const BARE_ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const ISO_DATE_IN_TEXT = /\d{4}-\d{2}-\d{2}/g;

/**
 * A field value that IS a date, reformatted. Anything else is returned
 * untouched: a quoted clause is evidence, and rewriting the middle of it would
 * break the promise that the value is what the page says.
 */
export function formatDateValue(value: string): string {
  const trimmed = value.trim();
  return BARE_ISO_DATE.test(trimmed) ? formatDate(trimmed) : value;
}

/** Dates inside generated prose (calendar detail lines, conflict summaries). */
export function formatDatesInText(text: string | null): string {
  if (!text) return "";
  return text.replace(ISO_DATE_IN_TEXT, (iso) => formatDate(iso));
}

export function daysBetween(fromIso: string, toIso: string): number {
  const a = Date.parse(fromIso + "T00:00:00Z");
  const b = Date.parse(toIso + "T00:00:00Z");
  return Math.round((b - a) / 86_400_000);
}

/** "in 12 days" / "today" / "overdue by 3 days". */
export function relativeDays(todayIso: string, targetIso: string): string {
  const d = daysBetween(todayIso, targetIso);
  if (d === 0) return "today";
  if (d === 1) return "tomorrow";
  if (d === -1) return "overdue by 1 day";
  if (d < 0) return `overdue by ${-d} days`;
  return `in ${d} days`;
}

export type Band = "overdue" | "this_week" | "next_30" | "in_90" | "later";

export function bandFor(todayIso: string, effectiveIso: string): Band {
  const d = daysBetween(todayIso, effectiveIso);
  if (d < 0) return "overdue";
  if (d <= 7) return "this_week";
  if (d <= 30) return "next_30";
  if (d <= 90) return "in_90";
  return "later";
}

export const BAND_LABELS: Record<Band, string> = {
  overdue: "Overdue",
  this_week: "This week",
  next_30: "Next 30 days",
  in_90: "30–90 days",
  later: "Later",
};

export const BAND_ORDER: Band[] = ["overdue", "this_week", "next_30", "in_90", "later"];
