// Feature 2 — dynamic portfolio benchmarking & risk scoring.
//
// For a term/date category, compute the portfolio mean across ACTIVE contracts
// in real time (no cached constant), compare one contract's value, and grade the
// deviation with a traffic light. Risk is a DIFFERENT axis from confidence: a
// value can be confidently extracted yet risky. Only grounded, non-`unverified`
// values feed an average — a suspected error must never move the benchmark.
import { prisma } from "../db.js";

export type Direction = "higher_better" | "lower_better" | "neutral";
export type Risk = "green" | "yellow" | "red";

type CategoryConfig = { label: string; unit: string; direction: Direction };

// The categories with comparable numbers. Direction encodes what "worse" means;
// these defaults are documented in docs/ROADMAP.md §2.2 and are meant to be
// tuned to the portfolio's risk appetite.
export const BENCHMARK_CATEGORIES: Record<string, CategoryConfig> = {
  // Computed: months between effective_date and expiration_date.
  term_length: { label: "Effective term length", unit: "months", direction: "neutral" },
  renewal_term: { label: "Renewal term length", unit: "months", direction: "lower_better" },
  // Per the feature prompt's worked example, a below-average notice period is the
  // risky (red) case, i.e. more notice is treated as better.
  notice_period_to_terminate_renewal: {
    label: "Notice period to terminate renewal",
    unit: "days",
    direction: "higher_better",
  },
};

export type Benchmark = {
  category: string;
  label: string;
  unit: string;
  direction: Direction;
  value: number;
  average: number;
  deviation: number; // value − average (absolute, in `unit`)
  percentWorse: number; // 0 when matching/better; drives the traffic light
  sampleSize: number; // how many active contracts the average is over
  risk: Risk;
};

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function daysBetween(fromIso: string, toIso: string): number {
  const a = Date.parse(fromIso + "T00:00:00Z");
  const b = Date.parse(toIso + "T00:00:00Z");
  return Math.round((b - a) / 86_400_000);
}

function mean(xs: number[]): number {
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}

function riskFor(value: number, average: number, direction: Direction): { risk: Risk; percentWorse: number } {
  if (average <= 0 || direction === "neutral") return { risk: "green", percentWorse: 0 };
  const worseRaw =
    direction === "higher_better" ? (average - value) / average : (value - average) / average;
  const percentWorse = Math.max(0, Math.round(worseRaw * 100));
  const risk: Risk = percentWorse <= 0 ? "green" : percentWorse <= 15 ? "yellow" : "red";
  return { risk, percentWorse };
}

/** Active = a processed contract that has not already expired. */
async function activeContractIds(workspaceId: string): Promise<string[]> {
  const docs = await prisma.document.findMany({
    where: {
      workspaceId,
      status: { in: ["ready", "degraded"] },
      docType: { notIn: ["not_a_contract", "invoice"] },
    },
    select: { id: true },
  });
  const ids = docs.map((d) => d.id);
  if (ids.length === 0) return [];

  const today = todayIso();
  const expirations = await prisma.extractedField.findMany({
    where: { documentId: { in: ids }, fieldKey: "expiration_date", confidenceTier: { not: "unverified" } },
    select: { documentId: true, valueNormalized: true },
  });
  const expired = new Set<string>();
  for (const e of expirations) {
    const d = (e.valueNormalized as { date?: string } | null)?.date;
    if (d && d < today) expired.add(e.documentId);
  }
  return ids.filter((id) => !expired.has(id));
}

/** Per-document numeric value for a category, over the given document ids. */
async function valuesForCategory(category: string, docIds: string[]): Promise<Map<string, number>> {
  const out = new Map<string, number>();
  if (docIds.length === 0) return out;

  if (category === "term_length") {
    const fields = await prisma.extractedField.findMany({
      where: {
        documentId: { in: docIds },
        fieldKey: { in: ["effective_date", "expiration_date"] },
        confidenceTier: { not: "unverified" },
      },
      select: { documentId: true, fieldKey: true, valueNormalized: true },
    });
    const eff = new Map<string, string>();
    const exp = new Map<string, string>();
    for (const f of fields) {
      const d = (f.valueNormalized as { date?: string } | null)?.date;
      if (!d) continue;
      (f.fieldKey === "effective_date" ? eff : exp).set(f.documentId, d);
    }
    for (const id of docIds) {
      const a = eff.get(id);
      const b = exp.get(id);
      if (a && b) {
        const months = Math.round(daysBetween(a, b) / 30.44);
        if (months > 0) out.set(id, months);
      }
    }
    return out;
  }

  const numKey = category === "notice_period_to_terminate_renewal" ? "days" : "months";
  const fields = await prisma.extractedField.findMany({
    where: {
      documentId: { in: docIds },
      fieldKey: category,
      confidenceTier: { not: "unverified" },
      valueVerbatim: { not: null },
    },
    select: { documentId: true, valueNormalized: true },
  });
  for (const f of fields) {
    const n = (f.valueNormalized as Record<string, unknown> | null)?.[numKey];
    if (typeof n === "number" && Number.isFinite(n)) out.set(f.documentId, n);
  }
  return out;
}

/** All benchmarkable categories for which a given document has a value. */
export async function benchmarksForDocument(workspaceId: string, documentId: string): Promise<Benchmark[]> {
  const activeIds = await activeContractIds(workspaceId);
  const fetchIds = Array.from(new Set([...activeIds, documentId]));
  const out: Benchmark[] = [];

  for (const [category, cfg] of Object.entries(BENCHMARK_CATEGORIES)) {
    const values = await valuesForCategory(category, fetchIds);
    const target = values.get(documentId);
    if (target == null) continue;
    const activeNums = activeIds
      .map((id) => values.get(id))
      .filter((n): n is number => typeof n === "number");
    if (activeNums.length === 0) continue;

    const average = mean(activeNums);
    const { risk, percentWorse } = riskFor(target, average, cfg.direction);
    out.push({
      category,
      label: cfg.label,
      unit: cfg.unit,
      direction: cfg.direction,
      value: target,
      average: Math.round(average * 10) / 10,
      deviation: Math.round((target - average) * 10) / 10,
      percentWorse,
      sampleSize: activeNums.length,
      risk,
    });
  }
  return out;
}

/** Portfolio-wide stats for a single category (no specific contract). */
export async function portfolioStats(workspaceId: string, category: string) {
  const cfg = BENCHMARK_CATEGORIES[category];
  if (!cfg) return null;
  const activeIds = await activeContractIds(workspaceId);
  const values = await valuesForCategory(category, activeIds);
  const nums = [...values.values()];
  return {
    category,
    label: cfg.label,
    unit: cfg.unit,
    direction: cfg.direction,
    average: nums.length ? Math.round(mean(nums) * 10) / 10 : null,
    sampleSize: nums.length,
    min: nums.length ? Math.min(...nums) : null,
    max: nums.length ? Math.max(...nums) : null,
  };
}
