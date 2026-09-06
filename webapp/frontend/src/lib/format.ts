// Dates as a person reads them, and the "how long until I must act" arithmetic
// the calendar is built around.

// Strict DD MMM YYYY, e.g. "01 Nov 2026". Native Intl — no date library is
// installed, and this is the single source of truth for dates across the UI.
const fmt = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric" });

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso + (iso.length === 10 ? "T00:00:00Z" : ""));
  if (Number.isNaN(d.getTime())) return iso;
  return fmt.format(d);
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

export type Band = "overdue" | "this_week" | "next_30" | "next_60" | "in_90" | "later";

export function bandFor(todayIso: string, effectiveIso: string): Band {
  const d = daysBetween(todayIso, effectiveIso);
  if (d < 0) return "overdue";
  if (d <= 7) return "this_week";
  if (d <= 30) return "next_30";
  if (d <= 60) return "next_60";
  if (d <= 90) return "in_90";
  return "later";
}

export const BAND_LABELS: Record<Band, string> = {
  overdue: "Overdue",
  this_week: "This week",
  next_30: "Next 30 days",
  next_60: "30–60 days",
  in_90: "60–90 days",
  later: "Later",
};

export const BAND_ORDER: Band[] = ["overdue", "this_week", "next_30", "next_60", "in_90", "later"];
