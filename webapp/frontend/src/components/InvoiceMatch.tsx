// Feature 3 — does this invoice have a contract behind it?
//
// The panel keeps the two sides visually apart, because they have different
// standing. What the model read off the INVOICE is shown under a "read by model"
// heading with no confidence badge. What it was checked AGAINST is shown as real
// contract fields with their own labels and clause citations. A reader can always
// see which half to distrust.
//
// This is NOT a conflict. It never appears on the Conflicts screen and says so, so
// it cannot be mistaken for a cross-contract detection.
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type InvoiceCitation, type InvoiceMatchResponse } from "../lib/api";
import { ConfidenceBadge } from "../lib/confidence";
import { formatDateValue, formatDatesInText } from "../lib/format";
import { SectionTitle } from "./ui";

const TONE: Record<string, string> = {
  "HIGH CONFIDENCE MATCH": "border-ok/40 bg-okbg",
  "MISSING CONTRACT - ROGUE INVOICE": "border-alert/50 bg-alertbg",
  "DATE MISMATCH - MANUAL REVIEW REQUIRED": "border-alert/50 bg-alertbg",
  "MULTIPLE CONTRACTS FOUND - MANUAL REVIEW REQUIRED": "border-warn/50 bg-warnbg",
  "DATE UNVERIFIABLE - MANUAL REVIEW REQUIRED": "border-warn/50 bg-warnbg",
  "NOT AN INVOICE - NOTHING CHECKED": "border-rule bg-paper",
};

function Citations({ items }: { items: InvoiceCitation[] }) {
  if (items.length === 0) return null;
  return (
    <div className="mt-2">
      <p className="text-sm font-medium text-ink">Checked against these contract fields</p>
      <ul className="mt-1 space-y-1.5">
        {items.map((c) => (
          <li key={c.fieldId} className="text-sm">
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-medium text-ink">{c.fieldKey}</span>
              {c.filename && (
                <Link to={`/documents/${c.documentId}`} className="link">
                  {c.filename}
                </Link>
              )}
              <ConfidenceBadge label={c.label} size="sm" />
            </div>
            <p className="text-muted">
              “{formatDateValue(c.valueVerbatim)}”
              {c.clauseLabel && ` — ${c.clauseLabel}`}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function InvoiceMatch({ documentId }: { documentId: string }) {
  const run = useMutation<InvoiceMatchResponse, Error>({
    mutationFn: () => api.matchInvoice(documentId),
  });
  const r = run.data;

  return (
    <section className="space-y-3">
      <SectionTitle
        right={
          <button
            type="button"
            onClick={() => run.mutate()}
            disabled={run.isPending}
            className="rounded bg-navy px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
          >
            {run.isPending ? "Checking…" : r ? "Check again" : "Check for a matching contract"}
          </button>
        }
      >
        Invoice check
      </SectionTitle>

      <p className="max-w-[70ch] text-sm text-muted">
        Reads the billing parties off this invoice and looks for a contract in the portfolio that
        names the same party, then checks the invoice date against that contract’s term. Findings
        appear here only — they are never added to the Conflicts screen.
      </p>

      {run.isError && (
        <div className="rounded border border-alert/50 bg-alertbg px-3 py-2 text-sm text-ink">
          {run.error.message}
        </div>
      )}

      {r && (
        <div className={`rounded border px-3 py-3 ${TONE[r.status] ?? "border-rule bg-paper"}`}>
          <div className="flex flex-wrap items-baseline gap-x-3">
            <span className="font-bold tracking-tight text-ink">{r.status}</span>
            <span className="rounded border border-rule bg-surface px-1.5 py-0.5 text-xs text-muted">
              invoice check · not a conflict
            </span>
          </div>
          <p className="mt-1 text-ink">{formatDatesInText(r.reason)}</p>

          {r.temporal && (
            <p className="mt-1 text-sm text-muted">
              Invoice date {r.temporal.invoiceDate ? formatDateValue(r.temporal.invoiceDate) : "not read"} ·
              contract term{" "}
              {formatDatesInText(
                `${r.temporal.window.from ?? "unknown start"} to ${r.temporal.window.to ?? "unknown end"}`,
              )}
              {r.temporal.partialWindow && " (one side of the term is unknown, so the check was one-sided)"}
            </p>
          )}

          {r.matches.length > 1 && (
            <ul className="mt-2 space-y-1 text-sm">
              {r.matches.map((m) => (
                <li key={m.documentId}>
                  <Link to={`/documents/${m.documentId}`} className="link">
                    {m.filename}
                  </Link>
                  <span className="text-muted"> — matched on “{m.matchedOn[0]?.contractParty}”</span>
                </li>
              ))}
            </ul>
          )}

          <Citations items={r.checkedAgainst} />

          {/* What the model read, kept visibly separate from the contract side. */}
          <div className="mt-3 border-t border-rule pt-2">
            <p className="text-sm font-medium text-ink">
              Read off the invoice by the model{" "}
              <span className="font-normal text-muted">
                — not grounded, and not quoted from any contract
              </span>
            </p>
            <dl className="mt-1 space-y-0.5 text-sm text-muted">
              <div>
                <dt className="inline font-medium">Billing parties: </dt>
                <dd className="inline">
                  {r.invoice.billingParties.map((p) => `${p.name} (${p.role})`).join("; ") || "none read"}
                </dd>
              </div>
              <div>
                <dt className="inline font-medium">Invoice date: </dt>
                <dd className="inline">
                  {r.invoice.dateIso ? formatDateValue(r.invoice.dateIso) : (r.invoice.dateRaw ?? "none read")}
                </dd>
              </div>
              <div>
                <dt className="inline font-medium">Line items: </dt>
                <dd className="inline">
                  {r.invoice.lineItems.length
                    ? r.invoice.lineItems
                        .map((l) => `${l.description}${l.amount != null ? ` — ${l.currency ?? ""}${l.amount}` : ""}`)
                        .join("; ")
                    : "none read"}
                </dd>
              </div>
            </dl>
          </div>

          <details className="mt-3">
            <summary className="cursor-pointer text-sm text-muted underline decoration-rule underline-offset-2">
              Known limits of this check
            </summary>
            <ul className="mt-1.5 space-y-1 text-sm text-muted">
              {r.limitations.map((l) => (
                <li key={l}>· {l}</li>
              ))}
            </ul>
          </details>
        </div>
      )}
    </section>
  );
}
