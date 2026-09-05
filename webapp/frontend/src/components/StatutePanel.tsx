// Role A statutory defaults: terms that apply because legislation supplies them,
// not because this contract says them.
//
// They get their own panel rather than a row inside a field group, and the
// Statute badge rather than one of the three confidence labels. The reason is the
// same in both cases: there is no clause to cite. Putting a default in the field
// list would put it one pixel away from values that ARE quoted from the page, and
// a reader skimming badges would come away believing the contract said it.
//
// Two states are shown, and the distinction is the whole point of the panel:
//
//   Standing  — the contract is silent, so the statutory term is what governs.
//   Displaced — an express clause was found that covers the same ground, so the
//               contract's own wording governs instead. The displacing clause is
//               named, because "we stopped applying this" is a claim that needs
//               its own evidence.
//
// `autoDisplacementSupported: false` is a deliberate admission: for those topics
// no extraction category reliably indicates that the parties contracted out, so
// AITHENA cannot tell silence from an express term it failed to spot.
import { useState } from "react";
import type { StatutoryDefaultDTO } from "../lib/api";
import { ConfidenceBadge } from "../lib/confidence";

function topicLabel(fieldName: string): string {
  const words = fieldName.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function DefaultRow({ d }: { d: StatutoryDefaultDTO }) {
  return (
    <div
      className={`rounded-r px-3 py-2.5 ${
        d.isDisplaced
          ? "border-l-4 border-l-rule bg-paper/60"
          : "border-l-4 border-l-navy border-double bg-surface"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <span className="text-sm font-medium text-muted">{topicLabel(d.fieldName)}</span>
        {d.isDisplaced ? (
          <span className="rounded border border-rule bg-surface px-1.5 py-0.5 text-xs font-medium text-faint">
            Displaced by the contract
          </span>
        ) : (
          <ConfidenceBadge label="statutory" size="sm" />
        )}
      </div>

      <p className={`mt-1 text-[1.02rem] ${d.isDisplaced ? "text-faint line-through decoration-faint/50" : "text-ink"}`}>
        {d.effect}
      </p>

      <p className="mt-1 text-sm text-muted">
        {d.statute} {d.citation} <span className="text-faint">· {d.jurisdiction}</span>
      </p>

      {d.isDisplaced ? (
        <p className="mt-1 text-sm text-muted">
          The contract addresses this at {d.displacedByClause ?? "an express clause"}
          {d.displacedByPage != null ? ` (page ${d.displacedByPage})` : ""}, so that wording governs instead of the
          statutory default.
        </p>
      ) : (
        <>
          <p className="mt-1 text-sm text-muted">Applies when: {d.appliesWhen}</p>
          {!d.autoDisplacementSupported && (
            <p className="mt-1 text-sm text-warn">
              AITHENA cannot detect whether this contract contracts out of this term, so check the document before
              relying on it.
            </p>
          )}
        </>
      )}
    </div>
  );
}

export function StatutePanel({ defaults }: { defaults: StatutoryDefaultDTO[] }) {
  const [showDisplaced, setShowDisplaced] = useState(false);
  if (defaults.length === 0) return null;

  const standing = defaults.filter((d) => !d.isDisplaced);
  const displaced = defaults.filter((d) => d.isDisplaced);

  return (
    <section className="panel border-navy/30 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-semibold text-ink">Supplied by statute</h2>
        <ConfidenceBadge label="statutory" size="sm" />
      </div>
      <p className="mt-1 text-sm text-muted">
        These terms are not quoted from your contract. They are what the law provides where the contract is silent, so
        they carry a statutory citation instead of a clause and page.
      </p>

      <div className="mt-3 space-y-2">
        {standing.map((d) => (
          <DefaultRow key={d.id} d={d} />
        ))}
      </div>

      {displaced.length > 0 && (
        <div className="mt-3 border-t border-rule pt-2">
          <button className="text-sm text-navy hover:underline" onClick={() => setShowDisplaced((v) => !v)}>
            {showDisplaced ? "Hide" : "Show"} {displaced.length} default
            {displaced.length === 1 ? "" : "s"} the contract has displaced
          </button>
          {showDisplaced && (
            <div className="mt-2 space-y-2">
              {displaced.map((d) => (
                <DefaultRow key={d.id} d={d} />
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
