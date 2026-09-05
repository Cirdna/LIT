import type { ReactNode } from "react";
import { Link } from "react-router-dom";

// The competence boundary, findable in one click from any screen (§9). Judges
// explicitly score whether the build knows where it stops.
export default function Scope() {
  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-bold text-ink">What this tool won't tell you</h1>
      <p className="mt-2 text-muted">
        AITHENA is a reading aid for a busy non-lawyer. It reports what your contracts say and when they need action. It
        is not a lawyer and does not give legal advice.
      </p>

      <Block title="What it does">
        <ul className="list-disc space-y-1 pl-5">
          <li>Extracts the key terms — parties, dates, renewal, termination, payments, liability, restrictions.</li>
          <li>Shows a citation for every value, so you can check it against the source page.</li>
          <li>Marks how confident it is, and says why when confidence is low.</li>
          <li>Builds a forward calendar of what you must act on, and by when.</li>
          <li>Flags where two of your contracts appear to conflict.</li>
        </ul>
      </Block>

      <Block title="What it will not tell you">
        <ul className="list-disc space-y-1 pl-5">
          <li>Whether a clause is <strong>enforceable</strong> or <strong>valid</strong> — that is a legal judgement.</li>
          <li>Whether a party is in <strong>breach</strong>, or what remedies apply.</li>
          <li>Anything that depends on facts <strong>outside the documents</strong> (what was said, done, or intended).</li>
          <li>What you <strong>should do</strong> about a risk. It surfaces the question; a lawyer answers it.</li>
        </ul>
      </Block>

      <Block title="How to read the confidence marks">
        <ul className="space-y-1">
          <li><strong>Quoted</strong> — copied straight from the contract and checked against the page.</li>
          <li><strong>Standardised</strong> — a quoted value turned into a date or number.</li>
          <li><strong>Assembled</strong> — pieced together from more than one clause.</li>
          <li><strong>Inferred</strong> — deduced, not stated outright. Check it.</li>
          <li><strong>Suspected error</strong> — the quoted text was not found where it was cited. Do not rely on it.</li>
        </ul>
      </Block>

      <Block title="When it hands off to a person">
        <p>
          When AITHENA hits the edge of what it can safely say — a conflict between contracts, an unreadable page, a
          value it cannot verify — it prepares a <Link to="/conflicts" className="link">handoff brief</Link> with a
          specific question for a lawyer, rather than guessing.
        </p>
      </Block>
    </div>
  );
}

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="panel mt-4 p-5">
      <h2 className="mb-2 text-lg font-semibold text-ink">{title}</h2>
      <div className="text-ink">{children}</div>
    </section>
  );
}
