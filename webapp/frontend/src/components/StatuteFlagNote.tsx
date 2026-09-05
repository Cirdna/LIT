// A Role B statute flag, rendered UNDER the field whose clause triggered it.
//
// It is additive by construction: it never replaces the extracted value, never
// changes the field's badge, and never restates the clause in its own words. The
// value above it is still whatever the contract said; this only reports that the
// clause engages a statutory provision, and names what a person has to decide.
//
// What it must never do is state a conclusion. "This cap is unenforceable" is a
// legal opinion we are not entitled to. "This cap engages UCTA s.11(1), whose
// reasonableness test a lawyer must apply" is a trigger, which is true and
// checkable. The wording below comes from the statute modules; this component
// only lays it out.
import type { StatuteFlagDTO } from "../lib/api";

/** How much of the statutory reasonableness question is machine-answerable. */
function gateNote(flag: StatuteFlagDTO): string | null {
  if (flag.reasonablenessTestApplies === null) return null;
  return flag.reasonablenessTestApplies
    ? "A statutory reasonableness test applies. AITHENA does not attempt it — that judgement is a lawyer's."
    : "The Act allows no reasonableness escape for this, so the term's own wording is not the end of the question.";
}

export function StatuteFlagNote({ flag }: { flag: StatuteFlagDTO }) {
  const gate = gateNote(flag);
  return (
    <div className="ml-3 mt-1 rounded-r border-l-4 border-l-navy border-double bg-navybg/60 px-3 py-2">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="inline-flex items-center gap-1 text-sm font-semibold text-navy">
          <span aria-hidden className="grid h-4 w-4 place-items-center rounded-sm border border-current font-bold leading-none">
            §
          </span>
          {flag.statute} {flag.citation}
        </span>
        <span className="text-sm text-faint">{flag.jurisdiction}</span>
      </div>

      <p className="mt-1 text-[1.02rem] text-ink">{flag.trigger}</p>

      <p className="mt-1 text-sm font-medium text-navy">Needs a lawyer: {flag.reviewRequired}</p>

      {flag.factors.length > 0 && (
        <details className="mt-1 text-sm text-muted">
          <summary className="cursor-pointer text-navy">What that turns on ({flag.factors.length})</summary>
          <ul className="mt-1 space-y-0.5 pl-4">
            {flag.factors.map((f, i) => (
              <li key={i} className="list-disc">
                {f}
              </li>
            ))}
          </ul>
        </details>
      )}

      {gate && <p className="mt-1 text-sm text-muted">{gate}</p>}

      {/* The clause it fired on, so the trigger is checkable against the page. */}
      <p className="mt-1 text-sm text-faint">
        {flag.sourceClause ?? "clause not identified"}
        {flag.sourcePage != null ? ` · page ${flag.sourcePage}` : ""}
      </p>
    </div>
  );
}
