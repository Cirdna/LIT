// AITHENA real worker — the same `jobs` table the stub worker consumes, but the
// fields it writes come from the Python pipeline reading the uploaded file.
//
// It is the seam described in docs/INTEGRATION.md, implemented by shelling out
// to the CLI rather than by embedding psycopg in Python: Node still owns the DB,
// Python still owns the document, and they exchange one JSON file per document.
//
//   npm run worker
//
// Requirements:
//   - OPENROUTER_API_KEY in the environment (Stage 2b calls a hosted VLM).
//   - Python able to import pdf_analyzer (PYTHONPATH is set to ../src below).
//
// Config:
//   PYTHON_BIN                 python executable (default "python")
//   PDF_ANALYZER_ROOT          repo root holding src/pdf_analyzer (default "..")
//   PDF_ANALYZER_PROMPT_MODE   "single" (default) or "granular" (41 calls/page,
//                              more accurate, ~41x the cost — see HANDOFF.md §6.1)
//
// What it deliberately does NOT write: page images, text_lines, document_segments,
// calendar_events, normalised values. Those need work this pass did not do, and
// an invented value is worse than a missing one. Prior rows from a stub run are
// deleted so nothing fabricated survives alongside real extraction.
import "../src/env.js"; // must run before anything reads process.env
import { spawn } from "node:child_process";
import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";
import { prisma } from "../src/db.js";
import { storage } from "../src/config.js";
import { getWorkspaceId } from "../src/lib/workspace.js";
import type { ConfidenceTier } from "../src/lib/domain.js";
import {
  counterpartyLabel,
  CUAD_FIELD_MAP,
  FIELDS_WITHOUT_CUAD_SOURCE,
  mapAnalysisToFields,
  type ContractAnalysisJson,
} from "./lib/cuad-map.js";

const PIPELINE_VERSION = "pdf_analyzer.cli@0.1.0";

const pythonBin = process.env.PYTHON_BIN ?? "python";
const analyzerRoot = path.resolve(process.env.PDF_ANALYZER_ROOT ?? path.join(process.cwd(), ".."));
const promptMode = process.env.PDF_ANALYZER_PROMPT_MODE ?? "single";

// Worker-owned area of the shared storage root: one analysis JSON per document.
// It is also the input set for the cross-contract scan, which is why it persists
// rather than living in tmp.
const analysisDir = path.join(storage.root, "analysis");
const queuePath = path.join(storage.tmpDir, "conflict-queue.json");

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ---- python bridge --------------------------------------------------------

function runPython(args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(pythonBin, args, {
      cwd: analyzerRoot,
      env: {
        ...process.env,
        // Works whether or not the package was pip-installed into this interpreter.
        PYTHONPATH: [path.join(analyzerRoot, "src"), process.env.PYTHONPATH]
          .filter(Boolean)
          .join(path.delimiter),
      },
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => (stdout += String(d)));
    child.stderr.on("data", (d) => (stderr += String(d)));
    child.on("error", (err) => reject(new Error(`could not start ${pythonBin}: ${err.message}`)));
    child.on("close", (code) => {
      if (code === 0) return resolve(stdout);
      // The CLI's own message is the useful part; keep it on the job row.
      const detail = (stderr.trim() || stdout.trim()).split("\n").slice(-6).join("\n");
      reject(new Error(`python ${args[1] ?? ""} ${args[2] ?? ""} exited ${code}: ${detail}`));
    });
  });
}

async function setProgress(jobId: string, stage: string, progress: number) {
  await prisma.job.update({ where: { id: jobId }, data: { stage, progress } });
}

// ---- statute layer (Role A defaults / Role B flags) -----------------------
// Read from the same analysis JSON, written to their OWN tables. Nothing below
// touches the extraction mapping above: a statutory default has no citation in
// the contract, and a flag is an annotation on a clause rather than a value, so
// neither belongs in extracted_fields.

type StatutoryDefaultJson = {
  field_name: string;
  statute: string;
  citation: string;
  jurisdiction: string;
  effect: string;
  applies_when: string;
  displaced_by_categories: string[];
  auto_displacement_supported: boolean;
  is_displaced: boolean;
  displaced_by: { page: number; clause: string } | null;
  raised_by: string;
};

type StatuteFlagJson = {
  flag_id: string;
  statute: string;
  citation: string;
  jurisdiction: string;
  field_name: string; // a CUAD category
  trigger: string;
  review_required: string;
  factors: string[];
  excerpt: string;
  source: { page: number; clause: string } | null;
  reasonableness_test_applies: boolean | null;
  requires_human_review: boolean;
  raised_by: string;
};

// CUAD category -> the webapp field key it should render beside. Built by
// reversing the existing map rather than restating it, so the two cannot drift.
const FIELD_KEY_BY_CUAD_CATEGORY = new Map<string, string>();
for (const entry of CUAD_FIELD_MAP)
  for (const cuadKey of entry.cuadKeys)
    if (!FIELD_KEY_BY_CUAD_CATEGORY.has(cuadKey)) FIELD_KEY_BY_CUAD_CATEGORY.set(cuadKey, entry.fieldKey);

/**
 * Where a flag should appear in the UI.
 *
 * Falls back to the CUAD category itself, which is deliberate: the webapp field
 * vocabulary is moving to the CUAD category keys (origin/main c50cab9), and on
 * that vocabulary the fallback IS the correct answer. Until then an unmapped
 * category yields a key no field group contains, and the UI shows the flag in
 * its document-level section instead of dropping it.
 */
function fieldKeyForCategory(category: string): string {
  return FIELD_KEY_BY_CUAD_CATEGORY.get(category) ?? category;
}

async function writeStatuteLayer(documentId: string, analysis: ContractAnalysisJson) {
  const defaults = Object.values(
    (analysis as { statutory_defaults?: Record<string, StatutoryDefaultJson> }).statutory_defaults ?? {},
  );
  const flags = (analysis as { flags?: StatuteFlagJson[] }).flags ?? [];

  await prisma.$transaction([
    prisma.statutoryDefault.deleteMany({ where: { documentId } }),
    prisma.statuteFlag.deleteMany({ where: { documentId } }),
  ]);

  for (const d of defaults) {
    await prisma.statutoryDefault.create({
      data: {
        documentId,
        fieldName: d.field_name,
        statute: d.statute,
        citation: d.citation,
        jurisdiction: d.jurisdiction,
        effect: d.effect,
        appliesWhen: d.applies_when,
        displacedByCategories: d.displaced_by_categories,
        autoDisplacementSupported: d.auto_displacement_supported,
        isDisplaced: d.is_displaced,
        displacedByClause: d.displaced_by?.clause ?? null,
        displacedByPage: d.displaced_by?.page ?? null,
        raisedBy: d.raised_by,
      },
    });
  }

  for (const f of flags) {
    await prisma.statuteFlag.create({
      data: {
        documentId,
        flagId: f.flag_id,
        statute: f.statute,
        citation: f.citation,
        jurisdiction: f.jurisdiction,
        cuadCategory: f.field_name,
        fieldKey: fieldKeyForCategory(f.field_name),
        trigger: f.trigger,
        reviewRequired: f.review_required,
        factors: f.factors,
        excerpt: f.excerpt,
        sourceClause: f.source?.clause ?? null,
        sourcePage: f.source?.page ?? null,
        reasonablenessTestApplies: f.reasonableness_test_applies,
        requiresHumanReview: f.requires_human_review,
        raisedBy: f.raised_by,
      },
    });
  }

  const standing = defaults.filter((d) => !d.is_displaced).length;
  return { defaults: defaults.length, standing, flags: flags.length };
}

// ---- one document ---------------------------------------------------------

async function processDocument(jobId: string, documentId: string) {
  const doc = await prisma.document.findUnique({ where: { id: documentId } });
  if (!doc) throw new Error(`document ${documentId} not found`);
  if (!doc.storageKey) throw new Error(`document ${documentId} has no stored original`);

  const inputPath = storage.resolveKey(doc.storageKey);
  const analysisPath = path.join(analysisDir, `${documentId}.json`);
  const workDir = path.join(storage.tmpDir, `analyze-${documentId}`);
  await mkdir(analysisDir, { recursive: true });
  await mkdir(storage.tmpDir, { recursive: true });

  await prisma.document.update({ where: { id: documentId }, data: { status: "processing", error: null } });
  await setProgress(jobId, `running pdf_analyzer (${promptMode} mode)`, 0.1);

  // `--contract-id` is what makes the conflict scan speak in document UUIDs, so
  // a flagged pair maps straight back to rows in this database.
  await runPython([
    "-m",
    "pdf_analyzer.cli",
    "analyze",
    inputPath,
    "--output",
    analysisPath,
    "--work-dir",
    workDir,
    "--contract-id",
    documentId,
    "--prompt-mode",
    promptMode,
  ]);

  await setProgress(jobId, "mapping extractions to fields", 0.75);
  const analysis = JSON.parse(await readFile(analysisPath, "utf8")) as ContractAnalysisJson;
  const rows = mapAnalysisToFields(analysis);

  // Idempotent re-run, and a hard guarantee that stub geometry/fields from an
  // earlier run cannot sit next to real extraction on the same document.
  await prisma.$transaction([
    prisma.textLine.deleteMany({ where: { documentId } }),
    prisma.documentPage.deleteMany({ where: { documentId } }),
    prisma.documentSegment.deleteMany({ where: { documentId } }),
    prisma.extractedField.deleteMany({ where: { documentId } }),
    prisma.calendarEvent.deleteMany({ where: { documentId } }),
    prisma.documentText.deleteMany({ where: { documentId } }),
  ]);

  for (const row of rows) {
    await prisma.extractedField.create({
      data: {
        documentId,
        fieldKey: row.fieldKey,
        valueVerbatim: row.valueVerbatim,
        valueNormalized: undefined, // no date/amount parsing on this path yet
        confidenceTier: row.confidenceTier,
        claimType: row.claimType,
        absenceReason: row.absenceReason,
        anchorLineIds: [], // no text_lines written -> no dangling anchors either
        segmentKey: null,
        clauseLabel: row.clauseLabel,
        consistencyScore: null, // there is no second extraction pass to compare
        vlmAgreement: row.vlmAgreement, // real Stage 3 match score
        modelVersion: PIPELINE_VERSION,
      },
    });
  }

  // Additive: the statute layer reads the same JSON and writes its own tables.
  const statute = await writeStatuteLayer(documentId, analysis);

  const unverified = rows.filter((r) => r.confidenceTier === "unverified").length;
  const warnings = [
    "Read by the real extraction pipeline. Page images, highlights and calendar dates are not produced on this path yet, so citations show a clause and page number instead.",
    `No extractor exists for: ${FIELDS_WITHOUT_CUAD_SOURCE.join(", ")}. Those are reported as not extracted rather than guessed.`,
  ];
  if (unverified > 0)
    warnings.push(
      `${unverified} value(s) could not be found in the cited clause and are marked as suspected errors.`,
    );
  if (statute.flags > 0)
    warnings.push(
      `${statute.flags} clause(s) engage a statutory provision that needs a lawyer's review. These are triggers, not conclusions.`,
    );

  await prisma.document.update({
    where: { id: documentId },
    data: {
      status: "ready",
      pageCount: analysis.document_metadata.total_pages,
      counterparty: counterpartyLabel(analysis),
      warnings,
      pipelineVersion: PIPELINE_VERSION,
      processedAt: new Date(),
      // Left unset on purpose: the analysis JSON does not report per-page
      // extraction method, so claiming `exact` or `ocr_applied` would be a guess.
    },
  });

  await setProgress(jobId, "done", 1);
  console.log(`  fields: ${rows.length} real (${unverified} unverified), counterparty=${counterpartyLabel(analysis) ?? "unresolved"}`);
  console.log(
    `  statute: ${statute.defaults} default(s) (${statute.standing} standing), ${statute.flags} flag(s)`,
  );
  return rows.length;
}

// ---- cross-contract scan --------------------------------------------------

// The library carries no notion of severity (FlaggedConflict deliberately does
// not adjudicate). What it does carry is the weakest join key the pairing rests
// on, so that is what we surface: a pair matched on a low-tier link must not
// read as loudly as one matched on an exact name.
const SEVERITY_BY_TIER: Record<string, string> = { high: "high", medium: "medium", low: "low" };
const FIELD_TIER_BY_TIER: Record<string, ConfidenceTier> = {
  high: "verbatim",
  medium: "assembled",
  low: "inferred",
};

type FlaggedConflictJson = {
  conflict_id: string;
  conflict_class: string;
  detected_by: string;
  provenance: string;
  rule_id: string | null;
  left: { contract_id: string; clause: string; page: number; excerpt: string };
  right: { contract_id: string; clause: string; page: number; excerpt: string };
  relationship_ids: { canonical_id: string | null; raw_value: string }[];
  lowest_confidence_tier: string;
  requires_human_review: boolean;
  explanation: string;
};

type ReviewQueueJson = {
  conflicts: FlaggedConflictJson[];
  contracts_examined: string[];
  party_pass_groups: number;
  asset_pass_groups: number;
};

async function scanForConflicts(workspaceId: string) {
  const out = await runPython([
    "-m",
    "pdf_analyzer.cli",
    "conflicts",
    analysisDir,
    "--output",
    queuePath,
  ]);
  console.log(`  ${out.trim().split("\n").slice(-1)[0] ?? ""}`);

  const queue = JSON.parse(await readFile(queuePath, "utf8")) as ReviewQueueJson;
  if (queue.conflicts.length === 0) return 0;

  // Only pairs whose contract_ids are documents in this workspace. A stale
  // analysis file (document deleted, or a CLI run of your own) must not create
  // a conflict pointing at nothing.
  const ids = [...new Set(queue.conflicts.flatMap((c) => [c.left.contract_id, c.right.contract_id]))];
  const docs = await prisma.document.findMany({
    where: { workspaceId, id: { in: ids } },
    select: { id: true, filename: true },
  });
  const known = new Map(docs.map((d) => [d.id, d.filename]));

  // The library speaks in contract IDs and canonical join keys, which are the
  // right thing for a rule to compare and the wrong thing to show a reader.
  const readable = (conflict: FlaggedConflictJson): string => {
    let text = conflict.explanation;
    for (const [id, filename] of known) text = text.split(id).join(filename);
    for (const link of conflict.relationship_ids)
      if (link.canonical_id) text = text.split(link.canonical_id).join(link.raw_value);
    return text;
  };

  const existing = await prisma.conflict.findMany({ where: { workspaceId } });
  const seen = new Set(
    existing.map((c) => `${c.conflictType}|${[...c.documentIds].sort().join(",")}`),
  );

  let created = 0;
  for (const c of queue.conflicts) {
    const documentIds = [c.left.contract_id, c.right.contract_id];
    if (!documentIds.every((id) => known.has(id))) continue;


    // The party pass reports one pair per shared counterparty, so the same two
    // clauses can arrive twice. One row per (type, document pair) is enough for
    // a reviewer; the full detail stays in the queue JSON.
    const key = `${c.conflict_class}|${[...documentIds].sort().join(",")}`;
    if (seen.has(key)) continue;
    seen.add(key);

    await prisma.conflict.create({
      data: {
        workspaceId,
        conflictType: c.conflict_class,
        severity: SEVERITY_BY_TIER[c.lowest_confidence_tier] ?? "medium",
        summary: `${readable(c)} (${c.rule_id ?? c.detected_by}, ${c.provenance}; ${c.left.clause} p${c.left.page} vs ${c.right.clause} p${c.right.page})`,
        documentIds,
        fieldIds: [], // conflict evidence is clause-level; it does not map 1:1 to a field row
        confidenceTier: FIELD_TIER_BY_TIER[c.lowest_confidence_tier] ?? "inferred",
      },
    });
    created += 1;
  }
  if (created > 0) console.log(`  ! wrote ${created} real conflict row(s) from the library path`);
  return created;
}

// ---- main loop ------------------------------------------------------------
// Identical claim/reap semantics to the stub worker (docs/INTEGRATION.md §3), so
// either can drive the same queue — but run only ONE of them at a time, or they
// race for jobs.

async function reap() {
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
process.on("SIGINT", () => {
  running = false;
  console.log("\nstopping after current job...");
});
process.on("SIGTERM", () => {
  running = false;
});

async function main() {
  const workspaceId = await getWorkspaceId();
  if (!process.env.OPENROUTER_API_KEY)
    console.warn("warning: OPENROUTER_API_KEY is not set — Stage 2b will fail for every document.");
  console.log(
    `real worker up. workspace=${workspaceId} python=${pythonBin} root=${analyzerRoot} mode=${promptMode}`,
  );

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
        await processDocument(job.id, job.document_id);
        await scanForConflicts(workspaceId);
      }
      await prisma.job.update({
        where: { id: job.id },
        data: { status: "done", progress: 1, finishedAt: new Date() },
      });
      console.log(`  done ${job.id}`);
    } catch (err) {
      console.error(`  failed ${job.id}:`, err);
      await prisma.job.update({
        where: { id: job.id },
        data: { status: "failed", error: String(err), finishedAt: new Date() },
      });
      if (job.document_id)
        await prisma.document
          .update({ where: { id: job.document_id }, data: { status: "failed", error: String(err) } })
          .catch(() => {});
    }
  }
  await prisma.$disconnect();
  console.log("stopped.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
