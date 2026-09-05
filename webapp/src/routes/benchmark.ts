// Feature 2 — portfolio benchmarking.
//
// No model is involved. This is arithmetic over values the extraction pipeline
// already produced, and every contract in the sample is returned alongside the
// average so a reader can check the sum.
//
// TWO HONESTY RULES ARE BUILT IN.
//
// 1. The sample is disclosed. A value whose quoted text holds no readable number
//    is excluded and counted (see lib/quantities.ts), and the response reports
//    `sampleSize` and `excluded` separately. An average over 3 of 11 contracts is
//    never presented as an average over the portfolio.
//
// 2. Only fields with a defensible direction get a traffic light. "Below average
//    notice period" is worse for whoever must react to it, so it scores. "Longer
//    initial term" is better or worse depending on which side of the deal you are
//    on, so it does NOT score: it reports the deviation and says the direction is
//    not defined. Inventing a polarity there would dress a preference up as a
//    finding.
import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { prisma } from "../db.js";
import { badRequest, notFound } from "../lib/errors.js";
import { labelForField } from "../lib/labels.js";
import { daysBetween, fieldDateIso, fieldDurationDays } from "../lib/quantities.js";
import { getWorkspaceId } from "../lib/workspace.js";

type Polarity = "higher_is_better" | "lower_is_better" | "undefined";

type Benchmarkable = {
  label: string;
  kind: "duration" | "date";
  polarity: Polarity;
  /** Shown to the user wherever the direction is not scored. */
  polarityNote?: string;
};

// FIELD VOCABULARY DEPENDENCY — these are the CURRENT 22 keys. If main's 41-key
// CUAD vocabulary is adopted, this table must be re-keyed (notice_period ->
// notice_period_to_terminate_renewal, term_end -> expiration_date, and so on).
// Tracked in STATUS_UPDATE.md.
export const BENCHMARKABLE: Record<string, Benchmarkable> = {
  notice_period: {
    label: "Notice Period",
    kind: "duration",
    polarity: "higher_is_better", // more warning before renewal is better for you
  },
  cure_period: {
    label: "Cure Period",
    kind: "duration",
    polarity: "higher_is_better", // more time to fix a breach is better for you
  },
  initial_term: {
    label: "Initial Term",
    kind: "duration",
    polarity: "undefined",
    polarityNote: "A longer initial term is security to one side and lock-in to the other, so it is reported without a rating.",
  },
  renewal_term: {
    label: "Renewal Term",
    kind: "duration",
    polarity: "undefined",
    polarityNote: "A longer auto-renewal can be continuity or an unwanted extension, so it is reported without a rating.",
  },
  effective_date: {
    label: "Effective Date",
    kind: "date",
    polarity: "undefined",
    polarityNote: "A start date is earlier or later, not better or worse.",
  },
  term_end: {
    label: "Term End",
    kind: "date",
    polarity: "undefined",
    polarityNote: "An end date is earlier or later, not better or worse.",
  },
  notice_deadline: {
    label: "Notice Deadline",
    kind: "date",
    polarity: "undefined",
    polarityNote: "A deadline is earlier or later, not better or worse.",
  },
};

const YELLOW_LIMIT_PCT = 15; // >15% worse is red; 1–15% worse is yellow

type Light = "green" | "yellow" | "red" | "unrated";

/**
 * The traffic light for a value against a mean.
 *
 * `worseBy` is a signed percentage in the "worse" direction, so the thresholds
 * read the same regardless of which way is better for the field.
 */
export function trafficLight(worsePct: number, polarity: Polarity): Light {
  if (polarity === "undefined") return "unrated";
  if (worsePct <= 0) return "green"; // at or better than average
  return worsePct <= YELLOW_LIMIT_PCT ? "yellow" : "red";
}

const GLYPH: Record<Light, string> = { green: "🟢", yellow: "🟡", red: "🔴", unrated: "⚪" };

function daysLabel(n: number): string {
  const r = Math.round(n);
  return `${r} ${Math.abs(r) === 1 ? "day" : "days"}`;
}

function epochDay(iso: string): number {
  return Math.round(Date.parse(iso + "T00:00:00Z") / 86_400_000);
}
function fromEpochDay(day: number): string {
  return new Date(Math.round(day) * 86_400_000).toISOString().slice(0, 10);
}

type Sample = {
  documentId: string;
  filename: string;
  counterparty: string | null;
  fieldId: string;
  /** Days for a duration field; epoch-day number for a date field. */
  value: number;
  /** What the reader sees: "90 days" or "2029-02-28". */
  display: string;
  valueVerbatim: string;
  clauseLabel: string | null;
  confidenceTier: string;
  label: ReturnType<typeof labelForField>;
  readFrom: "normalized" | "parsed";
};

export async function benchmarkField(workspaceId: string, fieldKey: string) {
  const spec = BENCHMARKABLE[fieldKey];
  if (!spec)
    throw badRequest(
      `"${fieldKey}" is not a benchmarkable field.`,
      { benchmarkable: Object.keys(BENCHMARKABLE) },
    );

  const rows = await prisma.extractedField.findMany({
    where: { fieldKey, document: { workspaceId }, valueVerbatim: { not: null } },
    include: { document: { select: { id: true, filename: true, counterparty: true } } },
  });

  const samples: Sample[] = [];
  const excluded: { documentId: string; filename: string; valueVerbatim: string; reason: string }[] = [];

  for (const row of rows) {
    const read =
      spec.kind === "duration"
        ? fieldDurationDays(row)
        : fieldDateIso(row);
    if (!read) {
      excluded.push({
        documentId: row.document.id,
        filename: row.document.filename,
        valueVerbatim: row.valueVerbatim!,
        reason: spec.kind === "duration" ? "no readable duration in the quoted text" : "no readable date in the quoted text",
      });
      continue;
    }
    const isDuration = "days" in read;
    samples.push({
      documentId: row.document.id,
      filename: row.document.filename,
      counterparty: row.document.counterparty,
      fieldId: row.id,
      value: isDuration ? read.days : epochDay(read.date),
      display: isDuration ? daysLabel(read.days) : read.date,
      valueVerbatim: row.valueVerbatim!,
      clauseLabel: row.clauseLabel,
      confidenceTier: row.confidenceTier,
      label: labelForField(row),
      readFrom: read.from,
    });
  }

  const mean = samples.length ? samples.reduce((a, s) => a + s.value, 0) / samples.length : null;
  const sorted = [...samples].map((s) => s.value).sort((a, b) => a - b);
  const median = sorted.length
    ? sorted.length % 2
      ? sorted[(sorted.length - 1) / 2]!
      : (sorted[sorted.length / 2 - 1]! + sorted[sorted.length / 2]!) / 2
    : null;

  return {
    fieldKey,
    fieldLabel: spec.label,
    kind: spec.kind,
    polarity: spec.polarity,
    polarityNote: spec.polarityNote ?? null,
    sampleSize: samples.length,
    mean,
    meanDisplay: mean == null ? null : spec.kind === "duration" ? daysLabel(mean) : fromEpochDay(mean),
    median,
    medianDisplay: median == null ? null : spec.kind === "duration" ? daysLabel(median) : fromEpochDay(median),
    samples,
    excluded,
    spec,
  };
}

/** One contract measured against the portfolio, with the sentence to display. */
export function compareToMean(
  bench: Awaited<ReturnType<typeof benchmarkField>>,
  documentId: string,
) {
  const mine = bench.samples.find((s) => s.documentId === documentId);
  if (!mine || bench.mean == null) return null;

  const peers = bench.samples.filter((s) => s.documentId !== documentId);
  // Compare against the portfolio EXCLUDING this contract. Measuring a value
  // against an average that contains it flatters every outlier.
  const peerMean = peers.length ? peers.reduce((a, s) => a + s.value, 0) / peers.length : null;
  if (peerMean == null)
    return {
      ...mine,
      peerMean: null,
      peerCount: 0,
      deviation: null,
      deviationDisplay: null,
      worsePct: null,
      light: "unrated" as Light,
      glyph: GLYPH.unrated,
      summary: `${bench.fieldLabel}: ${mine.display} (no other contract in the portfolio has this field extracted, so there is nothing to compare against)`,
      note: "A portfolio average needs at least two contracts with a readable value.",
    };

  const deviation = mine.value - peerMean; // positive = above the average
  const magnitude = Math.abs(deviation);
  const pctOfMean = peerMean === 0 ? 0 : (magnitude / Math.abs(peerMean)) * 100;

  // "Worse" depends on the field. For notice/cure periods, below average is worse.
  const worsePct =
    bench.spec.polarity === "higher_is_better" ? (deviation < 0 ? pctOfMean : -pctOfMean)
    : bench.spec.polarity === "lower_is_better" ? (deviation > 0 ? pctOfMean : -pctOfMean)
    : 0;

  const light = trafficLight(worsePct, bench.spec.polarity);

  const direction =
    bench.kind === "duration"
      ? deviation < 0 ? "below" : deviation > 0 ? "above" : "level with"
      : deviation < 0 ? "before" : deviation > 0 ? "after" : "level with";

  const meanDisplay = bench.kind === "duration" ? daysLabel(peerMean) : fromEpochDay(peerMean);
  const gap = daysLabel(magnitude);

  // Matches the requested format:
  // "Notice Period: 30 days (15 days below portfolio average of 45 days) 🔴"
  const summary =
    deviation === 0
      ? `${bench.fieldLabel}: ${mine.display} (level with portfolio average of ${meanDisplay}) ${GLYPH[light]}`
      : `${bench.fieldLabel}: ${mine.display} (${gap} ${direction} portfolio average of ${meanDisplay}) ${GLYPH[light]}`;

  return {
    ...mine,
    peerMean,
    peerCount: peers.length,
    deviation,
    deviationDisplay: `${gap} ${direction}`,
    worsePct: Math.round(worsePct * 10) / 10,
    light,
    glyph: GLYPH[light],
    summary,
    note: null as string | null,
  };
}

export async function registerBenchmarkRoutes(app: FastifyInstance) {
  app.get("/api/benchmark/fields", async () => ({
    fields: Object.entries(BENCHMARKABLE).map(([key, spec]) => ({
      fieldKey: key,
      label: spec.label,
      kind: spec.kind,
      polarity: spec.polarity,
      polarityNote: spec.polarityNote ?? null,
    })),
    thresholds: {
      green: "at or better than the portfolio average",
      yellow: `up to ${YELLOW_LIMIT_PCT}% worse than average`,
      red: `more than ${YELLOW_LIMIT_PCT}% worse than average`,
      unrated: "this field has no defensible better/worse direction",
    },
  }));

  const query = z.object({
    fieldKey: z.string().min(1),
    documentId: z.string().uuid().optional(),
  });

  app.get("/api/benchmark", async (req) => {
    const { fieldKey, documentId } = query.parse(req.query);
    const workspaceId = await getWorkspaceId();

    const bench = await benchmarkField(workspaceId, fieldKey);
    const { spec: _spec, ...publicBench } = bench;

    let selected: ReturnType<typeof compareToMean> = null;
    if (documentId) {
      const doc = await prisma.document.findFirst({ where: { id: documentId, workspaceId } });
      if (!doc) throw notFound("Document not found");
      selected = compareToMean(bench, documentId);
    }

    return {
      ...publicBench,
      selected,
      /** Why the sample is what it is — shown next to the average, not buried. */
      sampleNote:
        bench.excluded.length > 0
          ? `Averaged over ${bench.sampleSize} contract(s). ${bench.excluded.length} more had this field but no readable ${bench.kind === "duration" ? "duration" : "date"} in the quoted text and were left out.`
          : `Averaged over ${bench.sampleSize} contract(s) with a readable value.`,
    };
  });
}
