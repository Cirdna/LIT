// Seeds the statute-review datapoints from the pipeline's knowledge store:
//   src/pdf_analyzer/files/*.json  (the single source of truth — read, not copied)
//
// Each "chunk" becomes a StatuteClause with one of the four AI statuses the
// human-review workflow flags on:
//   Quoted | Inferred | Evaluation Required | NA
// derived deterministically from the chunk's own metadata. Idempotent by
// (workspaceId, clauseKey).
//
//   npm run seed:statutes
import "../src/env.js"; // load .env first
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { prisma } from "../src/db.js";
import { getWorkspaceId } from "../src/lib/workspace.js";

type EssEntry = { status?: string };
type Chunk = {
  id: string;
  source?: string;
  provision?: string;
  exact_wording?: string;
  summary?: string | null;
  authority_basis?: string;
  case_citation?: string | null;
  engine_status?: string;
  extraction_schema_status?: EssEntry[];
  jurisdiction_gate?: { na_reason?: string };
  target_fields?: string[];
  applicable_contract_types?: string[];
};

export type AiStatus = "Quoted" | "Inferred" | "Evaluation Required" | "NA";

// Faithful to the knowledge store's own fields (see statute_json_changelog_v2.md):
//   - a chunk that cannot run (hire-purchase limb) -> NA
//   - a case-law gloss or a partial CUAD proxy is an interpretation -> Inferred
//   - verbatim statute text wired to a real CUAD field -> Quoted
//   - everything else (all target fields are cuad_gap) needs a human -> Evaluation Required
export function deriveStatus(chunk: Chunk): AiStatus {
  if (chunk.engine_status === "dependency_unavailable") return "NA";
  const statuses = new Set((chunk.extraction_schema_status ?? []).map((e) => e.status));
  if (chunk.authority_basis === "case_law_gloss" || statuses.has("cuad_partial_proxy")) return "Inferred";
  if (statuses.has("cuad_native") && chunk.authority_basis === "statute_text") return "Quoted";
  return "Evaluation Required";
}

async function main() {
  const workspaceId = await getWorkspaceId();
  const dir = fileURLToPath(new URL("../../src/pdf_analyzer/files/", import.meta.url));
  const jsonFiles = readdirSync(dir).filter((f) => f.endsWith(".json"));

  let created = 0;
  let updated = 0;
  const byStatus: Record<string, number> = {};

  for (const file of jsonFiles) {
    const chunks = JSON.parse(readFileSync(dir + file, "utf8")) as Chunk[];
    if (!Array.isArray(chunks)) continue;
    for (const c of chunks) {
      if (!c.id) continue;
      const aiStatus = deriveStatus(c);
      byStatus[aiStatus] = (byStatus[aiStatus] ?? 0) + 1;
      const naReason =
        aiStatus === "NA"
          ? c.engine_status === "dependency_unavailable"
            ? "dependency_unavailable"
            : (c.jurisdiction_gate?.na_reason ?? null)
          : null;

      const data = {
        source: c.source ?? file.replace(/\.json$/, ""),
        provision: c.provision ?? "—",
        exactWording: c.exact_wording ?? "",
        summary: c.summary ?? null,
        aiStatus,
        authorityBasis: c.authority_basis ?? null,
        caseCitation: c.case_citation ?? null,
        naReason,
        targetFields: c.target_fields ?? [],
        applicableContractTypes: c.applicable_contract_types ?? [],
      };

      const existing = await prisma.statuteClause.findUnique({
        where: { workspaceId_clauseKey: { workspaceId, clauseKey: c.id } },
      });
      if (existing) {
        // Refresh the AI-side fields; leave reviewStatus + annotations alone.
        await prisma.statuteClause.update({ where: { id: existing.id }, data });
        updated += 1;
      } else {
        await prisma.statuteClause.create({ data: { workspaceId, clauseKey: c.id, ...data } });
        created += 1;
      }
    }
  }

  console.log(`statute clauses: +${created} created, ${updated} updated`);
  console.log("by AI status:", byStatus);
}

main()
  .catch((err) => {
    console.error(err);
    process.exitCode = 1;
  })
  .finally(() => prisma.$disconnect());
