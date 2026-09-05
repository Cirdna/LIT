// The seeded demo corpus. The seed writes these as `queued` documents + ingest
// jobs; the stub worker recognises each `profile` and produces tailored fake
// data. Between them these documents exercise every confidence tier, every
// boundary state, and every calendar time band the UI must render.

export type CorpusProfile =
  | "distribution_acme" // exclusivity in Singapore — conflict pair A
  | "distribution_borden" // overlapping rights in Singapore — conflict pair B
  | "nda_overdue" // a MISSED auto-renewal — the overdue calendar item
  | "lease_scanned_illegible" // scanned + OCR, low confidence, one illegible page
  | "msa_unverified" // an unverified (fabrication-signal) field + assembled field
  | "employment_inferred" // inferred fields, non-compete
  | "invoice_not_contract" // not_a_contract boundary state
  | "services_docx" // born-digital docx, notice deadline this week
  | "generic"; // fallback for real uploads

export type CorpusDoc = {
  filename: string;
  ext: string;
  mime: string;
  profile: CorpusProfile;
};

export const CORPUS: CorpusDoc[] = [
  { filename: "Acme Distribution Agreement.pdf", ext: "pdf", mime: "application/pdf", profile: "distribution_acme" },
  { filename: "Borden Distribution Agreement.pdf", ext: "pdf", mime: "application/pdf", profile: "distribution_borden" },
  { filename: "Northwind Mutual NDA.pdf", ext: "pdf", mime: "application/pdf", profile: "nda_overdue" },
  { filename: "Contoso Office Lease (scanned).pdf", ext: "pdf", mime: "application/pdf", profile: "lease_scanned_illegible" },
  { filename: "Globex Master Services Agreement.pdf", ext: "pdf", mime: "application/pdf", profile: "msa_unverified" },
  { filename: "Initech Employment Agreement.pdf", ext: "pdf", mime: "application/pdf", profile: "employment_inferred" },
  { filename: "Umbrella Services Agreement.docx", ext: "docx", mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", profile: "services_docx" },
  { filename: "Q3 Invoice 4471.pdf", ext: "pdf", mime: "application/pdf", profile: "invoice_not_contract" },
];

/** Map an arbitrary uploaded filename to a profile, so real uploads also demo
 *  the boundary states. Seeded filenames win; otherwise heuristics. */
export function profileForFilename(filename: string): CorpusProfile {
  const match = CORPUS.find((c) => c.filename === filename);
  if (match) return match.profile;
  const lower = filename.toLowerCase();
  if (/invoice|receipt|statement|packing/.test(lower)) return "invoice_not_contract";
  if (/scan/.test(lower)) return "lease_scanned_illegible";
  return "generic";
}
