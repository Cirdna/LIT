// AITHENA stub worker.
//
// This is NOT throwaway. It consumes the same `jobs` table the real Python
// worker will, using FOR UPDATE SKIP LOCKED, and produces realistic fake data
// spanning every confidence tier (including `unverified`), every boundary state,
// and calendar events across every time band. It lets the whole frontend be
// built and demo-rehearsed before the Python pipeline exists, and doubles as the
// fixture generator for tests.
//
// It talks to the DB and ./storage only — never to the Node API. Swapping in the
// real worker changes nothing above it.
//
//   npm run seed && npm run stub
//
// DEMO CORPUS ONLY. Every value this worker writes is fabricated from the
// filename, so it must never be the thing that answers for a document a user
// actually uploaded — a plausible invented liability cap is the worst possible
// output. It therefore processes only the seeded corpus (scripts/corpus.ts) and
// requeues anything else for the real worker (scripts/real-worker.ts). Set
// STUB_ALLOW_ANY=1 to fabricate data for arbitrary files anyway, which is useful
// for UI work and for nothing else.
//
import "../src/env.js"; // must run before anything reads process.env
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { Prisma } from "@prisma/client";
import { prisma } from "../src/db.js";
import { storage } from "../src/config.js";
import { getWorkspaceId } from "../src/lib/workspace.js";
import { ALL_FIELD_KEYS } from "../src/lib/domain.js";
import type { ConfidenceTier, ClaimType, AbsenceReason } from "../src/lib/domain.js";
import { buildBriefFromConflict } from "../src/lib/handoff.js";
import { CORPUS, profileForFilename, type CorpusProfile } from "./corpus.js";
import { encodePng, fillRect, makeCanvas, type Rgba } from "./png.js";

// See the file header: fabricated data is allowed to answer for the seeded demo
// corpus and, if you insist, for anything else.
const STUB_ALLOW_ANY = process.env.STUB_ALLOW_ANY === "1";
const DEMO_FILENAMES = new Set(CORPUS.map((c) => c.filename));

const PAGE_W = 612; // US Letter, PDF points
const PAGE_H = 792;
const DPI = 100;
const SCALE = DPI / 72;
const LEFT = 72;
const TOP = 90;
const LINE_H = 16;
const PIPELINE_VERSION = "stub-worker@0.1.0";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ---- date helpers (date-only, UTC) ---------------------------------------
function today(): Date {
  const n = new Date();
  return new Date(Date.UTC(n.getUTCFullYear(), n.getUTCMonth(), n.getUTCDate()));
}
function addDays(d: Date, days: number): Date {
  const c = new Date(d);
  c.setUTCDate(c.getUTCDate() + days);
  return c;
}
function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

const FILLER = [
  "The parties agree to the terms and conditions set forth in this Agreement.",
  "Each party represents that it has full authority to enter into this Agreement.",
  "This Agreement shall be governed by the laws of the Republic of Singapore.",
  "Neither party may assign its rights without the prior written consent of the other.",
  "All notices under this Agreement shall be given in writing to the address below.",
  "The Recipient shall keep the Confidential Information strictly confidential.",
  "Payment shall be made within thirty (30) days of receipt of a valid invoice.",
  "The failure to enforce any provision shall not constitute a waiver thereof.",
  "This Agreement constitutes the entire understanding between the parties.",
  "Any amendment must be in writing and signed by authorised representatives.",
];

// ---- per-profile metadata & scenario dates -------------------------------
type Meta = {
  docType: string;
  partyA: string;
  partyB: string;
  counterparty: string;
  provenance: "exact" | "degraded" | "text_only";
  ocrApplied: boolean;
  pageCount: number;
  status: "ready" | "degraded";
  // scenario-driving calendar values
  termEnd?: Date;
  autoRenews?: boolean;
  noticePeriodDays?: number;
  renewalDate?: Date;
  noticeDeadline?: Date;
  paymentDue?: Date;
};

function metaFor(profile: CorpusProfile): Meta {
  const t = today();
  const USER = "Meridian Retail Pte. Ltd.";
  switch (profile) {
    case "distribution_acme":
      return {
        docType: "distribution", partyA: USER, partyB: "Acme Distribution Corp.",
        counterparty: "Acme Distribution Corp.", provenance: "exact", ocrApplied: false,
        pageCount: 4, status: "ready", autoRenews: true, noticePeriodDays: 60,
        termEnd: addDays(t, 105), renewalDate: addDays(t, 105), noticeDeadline: addDays(t, 45),
      };
    case "distribution_borden":
      return {
        docType: "distribution", partyA: USER, partyB: "Borden Distribution LLC",
        counterparty: "Borden Distribution LLC", provenance: "exact", ocrApplied: false,
        pageCount: 4, status: "ready", autoRenews: true, noticePeriodDays: 90,
        termEnd: addDays(t, 165), renewalDate: addDays(t, 165), noticeDeadline: addDays(t, 75),
      };
    case "nda_overdue":
      return {
        docType: "nda", partyA: USER, partyB: "Northwind Systems Inc.",
        counterparty: "Northwind Systems Inc.", provenance: "exact", ocrApplied: false,
        pageCount: 3, status: "ready", autoRenews: true, noticePeriodDays: 60,
        // renewal soon, but notice window already closed -> OVERDUE
        termEnd: addDays(t, 20), renewalDate: addDays(t, 20), noticeDeadline: addDays(t, -40),
      };
    case "lease_scanned_illegible":
      return {
        docType: "lease", partyA: USER, partyB: "Contoso Property Management",
        counterparty: "Contoso Property Management", provenance: "degraded", ocrApplied: true,
        pageCount: 5, status: "degraded", autoRenews: false, noticePeriodDays: 90,
        termEnd: addDays(t, 250), noticeDeadline: addDays(t, 88), paymentDue: addDays(t, 8),
      };
    case "msa_unverified":
      return {
        docType: "msa", partyA: USER, partyB: "Globex Corporation",
        counterparty: "Globex Corporation", provenance: "exact", ocrApplied: false,
        pageCount: 4, status: "ready", autoRenews: false, noticePeriodDays: 30,
        termEnd: addDays(t, 400), paymentDue: addDays(t, 15),
      };
    case "employment_inferred":
      return {
        docType: "employment", partyA: USER, partyB: "Ada Lovelace",
        counterparty: "Ada Lovelace", provenance: "exact", ocrApplied: false,
        pageCount: 3, status: "ready", autoRenews: false, noticePeriodDays: 30,
        termEnd: addDays(t, 500),
      };
    case "services_docx":
      return {
        docType: "msa", partyA: USER, partyB: "Umbrella Services Ltd.",
        counterparty: "Umbrella Services Ltd.", provenance: "text_only", ocrApplied: false,
        pageCount: 3, status: "ready", autoRenews: true, noticePeriodDays: 60,
        // notice due THIS WEEK
        termEnd: addDays(t, 63), renewalDate: addDays(t, 63), noticeDeadline: addDays(t, 3),
      };
    case "invoice_not_contract":
      return {
        docType: "not_a_contract", partyA: "", partyB: "", counterparty: "",
        provenance: "exact", ocrApplied: false, pageCount: 1, status: "ready",
      };
    default:
      return {
        docType: "other", partyA: USER, partyB: "Counterparty Ltd.",
        counterparty: "Counterparty Ltd.", provenance: "exact", ocrApplied: false,
        pageCount: 3, status: "ready", autoRenews: false, noticePeriodDays: 30,
        termEnd: addDays(today(), 220), paymentDue: addDays(today(), 40),
      };
  }
}

// ---- geometry: pages, lines, page images ---------------------------------
type LineRow = {
  lineId: string;
  pageNumber: number;
  charStart: number;
  charEnd: number;
  bbox: { x0: number; y0: number; x1: number; y1: number };
  text: string;
};

type PageRow = {
  pageNumber: number;
  width: number;
  height: number;
  charStart: number;
  charEnd: number;
  extractionMethod: string;
  ocrConfMean: number | null;
  pageRole: string;
  imageKey: string;
  imageDpi: number;
  illegible: boolean;
  canvas: Rgba;
};

function pageRole(n: number, total: number): string {
  if (n === 1) return "cover";
  if (n === total) return "signature";
  return "operative";
}

function buildGeometry(documentId: string, meta: Meta) {
  const pages: PageRow[] = [];
  const lines: LineRow[] = [];
  const textParts: string[] = [];
  let charPos = 0;
  let lineNum = 0;

  const extractionMethod =
    meta.provenance === "degraded" ? "ocr" : meta.docType === "not_a_contract" ? "pdf_text" : "pdf_text";

  for (let p = 1; p <= meta.pageCount; p++) {
    // The lease has one deliberately illegible page (page 3) to exercise the
    // illegible boundary state.
    const illegible = meta.provenance === "degraded" && p === 3;
    const pageCharStart = charPos;
    const canvas = makeCanvas(Math.round(PAGE_W * SCALE), Math.round(PAGE_H * SCALE), [252, 252, 251]);
    // page border
    fillRect(canvas, 0, 0, canvas.width, 2, [225, 225, 228]);
    fillRect(canvas, 0, canvas.height - 2, canvas.width, canvas.height, [225, 225, 228]);
    fillRect(canvas, 0, 0, 2, canvas.height, [225, 225, 228]);
    fillRect(canvas, canvas.width - 2, 0, canvas.width, canvas.height, [225, 225, 228]);

    const perPage = 36 + (p % 4);
    for (let i = 0; i < perPage; i++) {
      const y0 = TOP + i * LINE_H;
      if (y0 + 11 > PAGE_H - 60) break;
      const isHeading = i === 0;
      const width = isHeading ? 260 : 180 + ((lineNum * 37) % 300);
      const x0 = LEFT;
      const y1 = y0 + (isHeading ? 13 : 10);
      const x1 = x0 + width;
      lineNum += 1;
      const text = isHeading ? `Section ${p}` : FILLER[lineNum % FILLER.length]!;
      const lineId = `L${String(lineNum).padStart(4, "0")}`;
      const cs = charPos;
      charPos += text.length + 1; // +1 for the newline join
      textParts.push(text);
      lines.push({ lineId, pageNumber: p, charStart: cs, charEnd: charPos - 1, bbox: { x0, y0, x1, y1 }, text });

      // Draw the "text" as a grey bar so overlays land on it. Illegible pages
      // get dense noisy bars that look unreadable.
      const grey: [number, number, number] = illegible
        ? [150 + ((i * 53) % 40), 148, 150]
        : isHeading
          ? [120, 122, 130]
          : [211, 214, 221];
      fillRect(canvas, x0 * SCALE, y0 * SCALE, x1 * SCALE, y1 * SCALE, grey);
      if (illegible) {
        // extra smudge
        fillRect(canvas, (x0 + 20) * SCALE, (y0 + 3) * SCALE, (x1 - 10) * SCALE, (y1 + 4) * SCALE, [170, 165, 168]);
      }
    }

    pages.push({
      pageNumber: p,
      width: PAGE_W,
      height: PAGE_H,
      charStart: pageCharStart,
      charEnd: charPos,
      extractionMethod,
      ocrConfMean: meta.provenance === "degraded" ? (illegible ? 0.41 : 0.72) : null,
      pageRole: pageRole(p, meta.pageCount),
      imageKey: storage.pageImageKey(documentId, p, DPI),
      imageDpi: DPI,
      illegible,
      canvas,
    });
  }

  return { pages, lines, text: textParts.join("\n") };
}

// ---- field plan ----------------------------------------------------------
type FieldSpec = {
  fieldKey: string;
  verbatim: string | null;
  normalized: unknown;
  tier: ConfidenceTier;
  claim?: ClaimType;
  absence?: AbsenceReason;
  clause?: string; // display label, e.g. "Clause 12.3"
  page?: number; // anchor page
  consistency?: number;
  vlmAgreement?: number;
  competing?: string[]; // for the "extraction passes disagree" boundary state
};

function fieldPlan(profile: CorpusProfile, meta: Meta): FieldSpec[] {
  const t = today();
  const effective = addDays(t, -300);
  const specs: FieldSpec[] = [];
  const add = (s: FieldSpec) => specs.push(s);

  // Parties (verbatim, high confidence)
  add({ fieldKey: "party_a", verbatim: meta.partyA, normalized: null, tier: "verbatim", clause: "Clause 1 (Parties)", page: 1 });
  add({ fieldKey: "party_b", verbatim: meta.partyB, normalized: null, tier: "verbatim", clause: "Clause 1 (Parties)", page: 1 });
  add({ fieldKey: "signatories", verbatim: null, normalized: null, tier: "verbatim", absence: "not_found", page: meta.pageCount });

  // Term
  add({ fieldKey: "effective_date", verbatim: iso(effective), normalized: { date: iso(effective) }, tier: "normalised", clause: "Clause 2.1", page: 1 });
  add({ fieldKey: "initial_term", verbatim: "twenty-four (24) months", normalized: { months: 24 }, tier: "normalised", clause: "Clause 2.2", page: 1 });
  if (meta.termEnd)
    add({ fieldKey: "term_end", verbatim: iso(meta.termEnd), normalized: { date: iso(meta.termEnd) }, tier: "normalised", clause: "Clause 2.3", page: 2 });

  // Renewal
  add({ fieldKey: "auto_renews", verbatim: meta.autoRenews ? "renews automatically for successive terms" : "does not renew automatically", normalized: { value: !!meta.autoRenews }, tier: meta.autoRenews ? "verbatim" : "inferred", clause: "Clause 3.1", page: 2 });
  if (meta.autoRenews)
    add({ fieldKey: "renewal_term", verbatim: "successive twelve (12) month terms", normalized: { months: 12 }, tier: "inferred", clause: "Clause 3.1", page: 2, vlmAgreement: 0.58 });
  if (meta.noticePeriodDays)
    add({ fieldKey: "notice_period", verbatim: `${meta.noticePeriodDays} days' prior written notice`, normalized: { days: meta.noticePeriodDays }, tier: "normalised", clause: "Clause 3.2", page: 2 });
  if (meta.noticeDeadline)
    add({ fieldKey: "notice_deadline", verbatim: iso(meta.noticeDeadline), normalized: { date: iso(meta.noticeDeadline) }, tier: "assembled", claim: "computed", clause: "Computed from Clause 3.1 + 3.2", page: 2 });

  // Termination
  add({ fieldKey: "termination_for_convenience", verbatim: "either party may terminate on 30 days' notice", normalized: { days: 30 }, tier: "verbatim", clause: "Clause 8.1", page: 3 });
  add({ fieldKey: "termination_for_cause", verbatim: "on material breach not cured within the cure period", normalized: null, tier: "verbatim", clause: "Clause 8.2", page: 3 });
  add({ fieldKey: "cure_period", verbatim: "thirty (30) days", normalized: { days: 30 }, tier: "normalised", clause: "Clause 8.2", page: 3 });

  // Payments
  add({ fieldKey: "payment_amount", verbatim: "S$50,000 per quarter", normalized: { amount: 50000, currency: "SGD" }, tier: "normalised", clause: "Clause 5.1", page: 2 });
  add({ fieldKey: "payment_schedule", verbatim: "quarterly in advance", normalized: null, tier: "verbatim", clause: "Clause 5.1", page: 2 });
  add({ fieldKey: "escalation", verbatim: null, normalized: null, tier: "inferred", absence: "not_present", page: 2 });

  // Liability
  add({ fieldKey: "liability_cap", verbatim: "aggregate liability shall not exceed S$50,000", normalized: { amount: 50000, currency: "SGD" }, tier: "verbatim", clause: "Clause 9.2", page: 3 });
  add({ fieldKey: "cap_carve_outs", verbatim: "excluding breaches of confidentiality and IP infringement", normalized: null, tier: "assembled", clause: "Clause 9.3", page: 3 });
  add({ fieldKey: "indemnities", verbatim: "mutual indemnity for third-party claims", normalized: null, tier: "verbatim", clause: "Clause 10.1", page: 3 });

  // Restrictions
  add({ fieldKey: "exclusivity", verbatim: null, normalized: null, tier: "inferred", absence: "not_present", page: 4 });
  add({ fieldKey: "non_compete", verbatim: null, normalized: null, tier: "inferred", absence: "not_present", page: 4 });
  add({ fieldKey: "non_solicit", verbatim: "no solicitation of employees for 12 months", normalized: { months: 12 }, tier: "normalised", clause: "Clause 11.2", page: 4 });

  // ---- profile-specific overrides -------------------------------------
  const set = (key: string, patch: Partial<FieldSpec>) => {
    const s = specs.find((x) => x.fieldKey === key);
    if (s) Object.assign(s, patch);
  };

  if (profile === "distribution_acme") {
    set("exclusivity", { verbatim: "Distributor is granted EXCLUSIVE rights to distribute the Products in Singapore", normalized: { territory: "Singapore", exclusive: true }, tier: "verbatim", absence: undefined, clause: "Clause 4.1", page: 2 });
    // A benchmark claim — explicitly OUR reference range, not a statement of law.
    add({ fieldKey: "notice_period", verbatim: null, normalized: { assessment: "within", reference_range: "30–90 days" }, tier: "inferred", claim: "benchmark", clause: undefined, page: 2 });
  }
  if (profile === "distribution_borden") {
    set("exclusivity", { verbatim: "Distributor may distribute the Products in Singapore and Malaysia on a non-exclusive basis", normalized: { territory: "Singapore", exclusive: false }, tier: "verbatim", absence: undefined, clause: "Clause 2.3", page: 2 });
  }
  if (profile === "nda_overdue") {
    set("payment_amount", { verbatim: null, normalized: null, tier: "inferred", absence: "not_present", clause: undefined });
    set("liability_cap", { verbatim: null, normalized: null, tier: "inferred", absence: "not_present", clause: undefined });
  }
  if (profile === "lease_scanned_illegible") {
    // A field on the illegible page — the value cannot be read.
    set("payment_amount", { verbatim: null, normalized: null, tier: "unverified", absence: "illegible", clause: "Clause 5.1 (page 3)", page: 3 });
    set("liability_cap", { verbatim: "S$??,000", normalized: null, tier: "unverified", clause: "Clause 9.2 (page 3)", page: 3, consistency: 0.3 });
  }
  if (profile === "msa_unverified") {
    // Assembled from two places, and one outright fabrication signal.
    set("liability_cap", { verbatim: "aggregate liability shall not exceed S$50,000", normalized: { amount: 50000, currency: "SGD" }, tier: "assembled", clause: "Clause 9.2 + Schedule 3", page: 3, consistency: 0.66 });
    set("cap_carve_outs", { verbatim: "unlimited liability for data breaches under Schedule 5", normalized: null, tier: "unverified", clause: "Clause 9.4", page: 3, consistency: 0.18, vlmAgreement: 0.2 });
    // extraction passes disagree materially
    set("payment_amount", { verbatim: "S$120,000 per annum", normalized: { amount: 120000, currency: "SGD" }, tier: "assembled", clause: "Clause 5.1", page: 2, consistency: 0.44, competing: ["S$120,000 per annum", "S$12,000 per month"] });
  }
  if (profile === "employment_inferred") {
    set("non_compete", { verbatim: "shall not engage in a competing business for 6 months post-termination", normalized: { months: 6 }, tier: "inferred", absence: undefined, clause: "Clause 11.1", page: 3, vlmAgreement: 0.55 });
    set("payment_amount", { verbatim: "S$8,500 gross per month", normalized: { amount: 8500, currency: "SGD" }, tier: "normalised", clause: "Clause 5.1", page: 2 });
  }

  return specs;
}

// ---- calendar plan -------------------------------------------------------
type EventSpec = {
  eventType: string;
  eventDate: Date;
  actionByDate: Date | null;
  title: string;
  detail: string;
  tier: ConfidenceTier;
};

function calendarPlan(meta: Meta): EventSpec[] {
  if (meta.docType === "not_a_contract") return [];
  const events: EventSpec[] = [];
  if (meta.autoRenews && meta.renewalDate && meta.noticeDeadline) {
    events.push({
      eventType: "auto_renewal",
      eventDate: meta.renewalDate,
      actionByDate: meta.noticeDeadline,
      title: `Auto-renews with ${meta.counterparty}`,
      detail: `Gives notice by ${iso(meta.noticeDeadline)} to prevent automatic renewal.`,
      tier: "assembled",
    });
  } else if (meta.termEnd) {
    events.push({
      eventType: "expiry",
      eventDate: meta.termEnd,
      actionByDate: meta.noticeDeadline ?? null,
      title: `Agreement with ${meta.counterparty} expires`,
      detail: `The term ends on ${iso(meta.termEnd)}.`,
      tier: "normalised",
    });
  }
  if (meta.paymentDue) {
    events.push({
      eventType: "payment_due",
      eventDate: meta.paymentDue,
      actionByDate: meta.paymentDue,
      title: `Payment due to ${meta.counterparty}`,
      detail: "A scheduled payment falls due.",
      tier: "normalised",
    });
  }
  return events;
}

// ---- job processing ------------------------------------------------------
async function setProgress(jobId: string, stage: string, progress: number) {
  await prisma.job.update({ where: { id: jobId }, data: { stage, progress } });
}

async function processDocument(jobId: string, documentId: string) {
  const doc = await prisma.document.findUnique({ where: { id: documentId } });
  if (!doc) throw new Error(`document ${documentId} not found`);

  // Refuse to invent an answer for a document nobody asked us to fake.
  if (!STUB_ALLOW_ANY && !DEMO_FILENAMES.has(doc.filename)) return { skipped: true } as const;

  const profile = profileForFilename(doc.filename);
  const meta = metaFor(profile);

  await prisma.document.update({ where: { id: documentId }, data: { status: "processing" } });
  await setProgress(jobId, "reading document", 0.05);

  // Clear any prior derived rows so re-runs are idempotent.
  await prisma.$transaction([
    prisma.textLine.deleteMany({ where: { documentId } }),
    prisma.documentPage.deleteMany({ where: { documentId } }),
    prisma.documentSegment.deleteMany({ where: { documentId } }),
    prisma.extractedField.deleteMany({ where: { documentId } }),
    prisma.calendarEvent.deleteMany({ where: { documentId } }),
    prisma.documentText.deleteMany({ where: { documentId } }),
  ]);

  const geo = buildGeometry(documentId, meta);

  // Render + persist page images, updating progress per page (exercises the UI).
  await mkdir(path.join(storage.pagesDir, documentId), { recursive: true });
  for (const pg of geo.pages) {
    await setProgress(jobId, `ocr page ${pg.pageNumber}/${geo.pages.length}`, 0.1 + 0.5 * (pg.pageNumber / geo.pages.length));
    await writeFile(storage.resolveKey(pg.imageKey), encodePng(pg.canvas));
    await sleep(600); // a few seconds per doc so the progress bar is real
  }

  // Persist pages, lines, text.
  await prisma.documentText.create({ data: { documentId, text: geo.text } });
  await prisma.documentPage.createMany({
    data: geo.pages.map((p) => ({
      documentId, pageNumber: p.pageNumber, width: p.width, height: p.height,
      charStart: p.charStart, charEnd: p.charEnd, extractionMethod: p.extractionMethod,
      ocrConfMean: p.ocrConfMean, pageRole: p.pageRole, imageKey: p.imageKey, imageDpi: p.imageDpi,
    })),
  });

  // Assign anchor lines to fields, overwriting a few line texts with the real
  // verbatim value so click-to-highlight lands on meaningful "words".
  const pageCursor = new Map<number, number>();
  const linesByPage = new Map<number, LineRow[]>();
  for (const l of geo.lines) {
    const arr = linesByPage.get(l.pageNumber) ?? [];
    arr.push(l);
    linesByPage.set(l.pageNumber, arr);
  }
  function anchor(page: number, verbatim: string | null): string[] {
    const arr = linesByPage.get(page);
    if (!arr || arr.length < 2) return [];
    const idx = pageCursor.get(page) ?? 1; // 0 is the heading
    const line = arr[idx % arr.length]!;
    if (verbatim) line.text = verbatim.slice(0, 90);
    pageCursor.set(page, idx + 1);
    return [line.lineId];
  }

  const specs = meta.docType === "not_a_contract" ? [] : fieldPlan(profile, meta);
  const fieldAnchors = new Map<string, string[]>();
  for (const s of specs) {
    const page = Math.min(s.page ?? 1, meta.pageCount);
    // Every value with a verbatim string gets an anchor unless the tier is
    // inferred (per the seam contract). Absent/illegible values may still point
    // at the page they should have been on.
    const wantsAnchor = s.tier !== "inferred" && (s.verbatim !== null || s.absence === "illegible");
    const ids = wantsAnchor ? anchor(page, s.verbatim) : [];
    fieldAnchors.set(s.fieldKey + ":" + specs.indexOf(s), ids);
  }

  await setProgress(jobId, "resolving line anchors", 0.7);
  await prisma.textLine.createMany({
    data: geo.lines.map((l) => ({
      documentId, lineId: l.lineId, pageNumber: l.pageNumber, charStart: l.charStart,
      charEnd: l.charEnd, bbox: l.bbox, text: l.text,
    })),
  });

  // Segments (clauses). A small, realistic set the fields cite into.
  const segDefs = [
    { key: "S0001", label: "1", heading: "Parties", page: 1, confidence: "structural" },
    { key: "S0002", label: "2", heading: "Term", page: 1, confidence: "structural" },
    { key: "S0003", label: "3", heading: "Renewal", page: 2, confidence: "structural" },
    { key: "S0004", label: "4", heading: "Territory & Exclusivity", page: 2, confidence: "heuristic" },
    { key: "S0005", label: "5", heading: "Fees", page: 2, confidence: "structural" },
    { key: "S0006", label: "8", heading: "Termination", page: 3, confidence: "structural" },
    { key: "S0007", label: "9", heading: "Limitation of Liability", page: 3, confidence: "structural" },
    { key: "S0008", label: "11", heading: "Restrictive Covenants", page: Math.min(4, meta.pageCount), confidence: "heuristic" },
  ];
  if (meta.docType !== "not_a_contract") {
    await prisma.documentSegment.createMany({
      data: segDefs.map((s, i) => ({
        documentId, segmentKey: s.key, level: 1, numberLabel: s.label, headingText: s.heading,
        charStart: i * 400, charEnd: i * 400 + 380, pageStart: Math.min(s.page, meta.pageCount),
        pageEnd: Math.min(s.page, meta.pageCount), parentKey: null, confidence: s.confidence,
      })),
    });
  }

  await setProgress(jobId, "extracting fields", 0.85);
  const createdFieldIds: Record<string, string> = {};
  for (let i = 0; i < specs.length; i++) {
    const s = specs[i]!;
    const anchors = fieldAnchors.get(s.fieldKey + ":" + i) ?? [];
    const norm = (s.normalized ?? null) as Record<string, unknown> | null;
    const normalizedValue: Prisma.InputJsonValue | undefined = s.competing
      ? ({ ...(norm ?? {}), competing: s.competing } as Prisma.InputJsonValue)
      : norm === null
        ? undefined
        : (norm as Prisma.InputJsonValue);
    const created = await prisma.extractedField.create({
      data: {
        documentId,
        fieldKey: s.fieldKey,
        valueVerbatim: s.verbatim,
        valueNormalized: normalizedValue,
        confidenceTier: s.tier,
        claimType: s.claim ?? "contract_text",
        // Invariant: a null value ALWAYS carries a non-null absence_reason.
        absenceReason: s.verbatim === null ? (s.absence ?? "not_present") : null,
        anchorLineIds: anchors,
        segmentKey: null,
        clauseLabel: s.clause ?? null,
        consistencyScore: s.consistency ?? (s.tier === "verbatim" ? 0.98 : s.tier === "normalised" ? 0.95 : null),
        vlmAgreement: s.vlmAgreement ?? (s.tier === "verbatim" ? 0.97 : null),
        modelVersion: PIPELINE_VERSION,
      },
    });
    // Remember the exclusivity field id for the cross-doc conflict.
    if (s.fieldKey === "exclusivity" && s.verbatim) createdFieldIds.exclusivity = created.id;
  }

  // Calendar events (link to the source fields where possible).
  const evSpecs = calendarPlan(meta);
  for (const e of evSpecs) {
    await prisma.calendarEvent.create({
      data: {
        workspaceId: doc.workspaceId,
        documentId,
        eventType: e.eventType,
        eventDate: new Date(iso(e.eventDate) + "T00:00:00Z"),
        actionByDate: e.actionByDate ? new Date(iso(e.actionByDate) + "T00:00:00Z") : null,
        title: e.title,
        detail: e.detail,
        confidenceTier: e.tier,
        sourceFieldIds: [],
        status: "open",
      },
    });
  }

  // Warnings surfaced in the portfolio header.
  const warnings: string[] = [];
  if (meta.provenance === "degraded") warnings.push("Scanned document — values read by OCR, expect lower certainty.");
  if (meta.docType === "not_a_contract") warnings.push("This looks like an invoice, not an agreement. Not analysed.");
  if (profile === "msa_unverified") warnings.push("One extracted value could not be verified against its cited clause.");

  await prisma.document.update({
    where: { id: documentId },
    data: {
      status: meta.status,
      provenanceQuality: meta.provenance,
      pageCount: meta.pageCount,
      ocrApplied: meta.ocrApplied,
      docType: meta.docType,
      docTypeConf: meta.docType === "not_a_contract" ? 0.94 : 0.9,
      counterparty: meta.counterparty || null,
      warnings,
      pipelineVersion: PIPELINE_VERSION,
      processedAt: new Date(),
    },
  });

  await setProgress(jobId, "done", 1);
  return { skipped: false, profile, exclusivityFieldId: createdFieldIds.exclusivity } as const;
}

// After both distribution agreements are ready, raise the exclusivity conflict
// and auto-generate the handoff brief (a boundary trip -> automatic escalation).
async function maybeRaiseExclusivityConflict(workspaceId: string) {
  const existing = await prisma.conflict.findFirst({ where: { workspaceId, conflictType: "exclusivity_breach" } });
  if (existing) return;

  const acme = await prisma.document.findFirst({ where: { workspaceId, filename: { contains: "Acme Distribution" }, status: { in: ["ready", "degraded"] } } });
  const borden = await prisma.document.findFirst({ where: { workspaceId, filename: { contains: "Borden Distribution" }, status: { in: ["ready", "degraded"] } } });
  if (!acme || !borden) return;

  const acmeExcl = await prisma.extractedField.findFirst({ where: { documentId: acme.id, fieldKey: "exclusivity" } });
  const bordenExcl = await prisma.extractedField.findFirst({ where: { documentId: borden.id, fieldKey: "exclusivity" } });
  if (!acmeExcl || !bordenExcl) return;

  const conflict = await prisma.conflict.create({
    data: {
      workspaceId,
      conflictType: "exclusivity_breach",
      severity: "high",
      summary:
        "Clause 4.1 of the Acme distribution agreement grants exclusive rights in Singapore; Clause 2.3 of the later Borden agreement grants overlapping rights in the same territory.",
      documentIds: [acme.id, borden.id],
      fieldIds: [acmeExcl.id, bordenExcl.id],
      confidenceTier: "verbatim",
    },
  });

  const brief = buildBriefFromConflict(conflict, [acme, borden], [acmeExcl, bordenExcl]);
  await prisma.handoffBrief.create({
    data: {
      workspaceId,
      trigger: brief.trigger,
      issue: brief.issue,
      established: brief.established as object,
      question: brief.question,
      documentIds: brief.documentIds,
    },
  });
  console.log("  ! raised exclusivity conflict + auto handoff brief");
}

// ---- main loop -----------------------------------------------------------
async function reap() {
  // Requeue jobs stuck 'running' longer than 15 minutes, up to 3 attempts, then
  // mark failed. A failed document must never block the batch.
  await prisma.$executeRaw`
    UPDATE jobs SET status='queued', started_at=NULL, stage='requeued after stall'
    WHERE status='running' AND started_at < now() - interval '15 minutes' AND attempts < 3`;
  await prisma.$executeRaw`
    UPDATE jobs SET status='failed', finished_at=now(), error='Exceeded max attempts after stalls'
    WHERE status='running' AND started_at < now() - interval '15 minutes' AND attempts >= 3`;
}

async function claimNext() {
  const rows = await prisma.$queryRaw<{ id: string; document_id: string | null; job_type: string }[]>`
    UPDATE jobs SET status='running', started_at=now(), attempts=attempts+1
    WHERE id = (
      SELECT id FROM jobs
      WHERE status='queued'
      ORDER BY created_at
      FOR UPDATE SKIP LOCKED
      LIMIT 1
    )
    RETURNING id, document_id, job_type`;
  return rows[0] ?? null;
}

let running = true;
process.on("SIGINT", () => { running = false; console.log("\nstopping after current job..."); });
process.on("SIGTERM", () => { running = false; });

async function main() {
  const workspaceId = await getWorkspaceId();
  console.log(`stub worker up. workspace=${workspaceId}. polling jobs...`);
  while (running) {
    await reap();
    const job = await claimNext();
    if (!job) {
      await sleep(1500);
      continue;
    }
    console.log(`> job ${job.id} (${job.job_type}) doc=${job.document_id}`);
    try {
      if (job.document_id) {
        const result = await processDocument(job.id, job.document_id);
        if (result.skipped) {
          // Hand it back rather than fabricating. `npm run worker` will read the
          // actual file; if nothing else is running, the job simply stays queued.
          await prisma.job.update({
            where: { id: job.id },
            data: { status: "queued", startedAt: null, stage: "not demo corpus — left for the real worker" },
          });
          console.log(`  skipped ${job.id}: not seeded demo corpus; requeued for the real worker`);
          await sleep(2500);
          continue;
        }
        await maybeRaiseExclusivityConflict(workspaceId);
      }
      await prisma.job.update({ where: { id: job.id }, data: { status: "done", progress: 1, finishedAt: new Date() } });
      console.log(`  done ${job.id}`);
    } catch (err) {
      console.error(`  failed ${job.id}:`, err);
      await prisma.job.update({ where: { id: job.id }, data: { status: "failed", error: String(err), finishedAt: new Date() } });
      if (job.document_id)
        await prisma.document.update({ where: { id: job.document_id }, data: { status: "failed", error: String(err) } }).catch(() => {});
    }
  }
  await prisma.$disconnect();
  console.log("stopped.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
