# AITHENA — Status update

Branch: `testing-branch` @ `62f3c6b` · local only · nothing merged, nothing pushed
Written for teammates who were not in this session. Companion documents:
`TEAM_SUMMARY.md` (who built what), `GAP_REPORT.md` (what is still missing).

---

## 1. What's new since the last update

### The four UI items are done — confirmed, not rebuilt

All four were checked against the running app rather than against memory, because
the statute-layer work in the previous session touched the same files. None
regressed.

| Item | Status | Evidence |
|---|---|---|
| Labels standardised to Quoted / Inferred / NA, green / yellow / red | PASS | `frontend/src/lib/confidence.tsx:93` — `LABEL_ORDER` is still exactly the three; one mapping function (`labelForField`) decides every badge |
| Filter within a contract by label | PASS | `routes/DocumentDetail.tsx:184`; live buttons read `✓ Quoted (12)`, `~ Inferred (4)`, `— NA (6)` |
| Date format "19 Nov 2026" | PASS | `frontend/src/lib/format.ts:19`; a page scrape found zero bare `YYYY-MM-DD` strings anywhere in the rendered UI |
| Calendar quick filters, 90 days default | PASS | `routes/Calendar.tsx:20` and `:29` (`DEFAULT_WINDOW = "90"`); live buttons read Today / This week / 30 days / 60 days / 90 days |

**One addition to flag, because it goes beyond the original three-label ask:**
there is now a **fourth badge, "Statute" (navy, `§`)**, added when the statute
layer was surfaced. It deliberately sits outside the green/yellow/red ramp. Those
three all answer "how well did we read the page?", and a statutory default has no
page to read — it is what the law supplies when the contract is silent. Calling it
Quoted would be a lie; Inferred or NA would both imply we looked in the document
and failed. So it has its own colour and glyph, and the meaning of the other three
is unchanged. Reasoning is in the header comment of `confidence.tsx`.

### Feature 1 — Ask the portfolio (new "Ask" tab)

A user can now type "which contracts have a notice period under 60 days?" and get
back the actual contracts, each with its quoted clause text, its Quoted/Inferred/NA
badge, and its clause citation — the same as on the document page.

The architecture is the important part, and it is deliberate: **the model never
writes an answer and never sees a contract.** It does exactly two things — decide
whether the question is specific enough to search, and translate it into a
structured filter (which fields, which duration/date comparison, which labels).
The filter then runs as an ordinary database query over `extracted_fields`. So the
worst a hallucination can do is produce a filter that matches nothing; it cannot
produce a sentence a contract never contained.

If the question is too vague, the tool asks **one** clarifying question and then
searches whatever it has. The one-question cap is enforced twice: the prompt for
the second call tells the model not to ask again, and the route refuses a second
question even if the model ignores that (`routes/chat.ts:295`).

Three things it says out loud rather than hiding: a field name the model invented
returns **zero** results and names the invented field (it does not silently widen
to the whole portfolio); rows whose quoted text held no readable number are
excluded **and counted** on screen; and the screen states that this searches
extracted values only, so "nothing matched" means "not extracted", not "not in
your contracts".

### Feature 2 — Portfolio benchmarking (on the document page)

Under any date or duration field with a value, a contract's term is now measured
against the rest of the portfolio, in the requested format:

> Notice Period: 30 days (38 days below portfolio average of 68 days) 🔴

Pure arithmetic — no model is involved. Green is at or better than average, yellow
up to 15% worse, red more than 15% worse. Two deliberate constraints:

- **Only fields with a defensible direction get a light.** "Below-average notice
  period" is worse for whoever has to react to it, so it scores. "Longer initial
  term" is security to one side and lock-in to the other, so it shows the deviation
  with a grey dot and says why it is not rated. Inventing a direction there would
  dress a preference up as a finding.
- **The sample is disclosed.** "How this was worked out" lists every contract in
  the average, which values were read from normalised data versus parsed out of
  quoted text, and which contracts were left out because their text held no
  readable number. The average also excludes the contract being measured — an
  average containing the value flatters every outlier.

### Feature 3 — Invoice check (on an invoice's page)

For a document classed as an invoice, there is now a **Check for a matching
contract** button that answers the AITHENA stretch question: is there a contract
behind this bill? Outcomes, all verified end to end:

- `MISSING CONTRACT - ROGUE INVOICE`
- `MULTIPLE CONTRACTS FOUND - MANUAL REVIEW REQUIRED`
- `HIGH CONFIDENCE MATCH`
- `DATE MISMATCH - MANUAL REVIEW REQUIRED`
- `DATE UNVERIFIABLE - MANUAL REVIEW REQUIRED` — **not one of the three in the
  brief.** It exists because a contract whose dates were never extracted cannot be
  called a date mismatch (that asserts a conflict we did not find) and must not be
  called a high-confidence match either. Please sanity-check that this fifth status
  is wanted.

Party matching **reuses Fix 2's rule** rather than adding a second one:
`webapp/src/lib/parties.ts` is a line-by-line port of `_exact_party_key` and
`_PARTY_SEPARATORS` from `src/pdf_analyzer/pipeline.py`, so "the same party" means
one thing in this product. It therefore inherits Fix 2's disclosed limit — exact
name only, no suffix normalisation, so `Acme Industries Pte Ltd` will never match
`Acme Industrial Ltd`. For invoices that is stricter than reality, since billers
abbreviate themselves; the response says so instead of quietly adding fuzzy logic
that would then disagree with the conflict engine.

Grounding is split cleanly down the middle of the panel. What the model read off
the invoice appears under "Read off the invoice by the model — not grounded, and
not quoted from any contract", with no confidence badge. What it was checked
*against* is listed as real contract fields with their own badges and clause
citations, naming the exact field. So a reader can always see which half to
distrust.

---

## 2. The `origin/main` conflict — needs a team decision before anyone merges

**Nothing was merged, fetched or pushed in this session. This is not a call to make
unilaterally, and no attempt was made to reconcile it.**

There are now **two incompatible workers**, and neither branch alone satisfies the
brief:

| | `origin/main` (`c50cab9`, teammate) | `testing-branch` (this line of work) |
|---|---|---|
| Extraction | Stronger | Weaker |
| Cross-contract conflict scan | Absent | Present (Fix 2) |
| Statute layer (defaults + flags) | Absent | Present |
| Field vocabulary | 41 CUAD category keys | 22 webapp keys |

**The merge hazard is concrete, not theoretical.** `main` rewrites `domain.ts` to
the 41 CUAD keys, and `webapp/scripts/lib/cuad-map.ts:160` *throws* on any field
key it does not recognise. Merging `main` as-is breaks the current Fix 1 mapping
outright, at runtime, unless the mapping layer is updated first.

The decisions the team needs to make, in order:

1. **Which worker wins**, or whether main's extraction is grafted onto our worker
   so the conflict scan and statute layer survive.
2. **How the field keys reconcile** — 22, 41, or a mapping between them. Everything
   in section 3 below hangs off this.

For the record on state: `refs/remotes/origin/main` already points at `c50cab9`
locally (that is how its contents are known), but `HEAD` has not moved from
`62f3c6b` since the clone and no merge has ever been attempted.

---

## 3. What Features 1–3 assume about today's 22-key vocabulary

Everything built this session was written against the **current** local vocabulary,
as instructed. Here is the full blast radius if the team adopts main's 41 keys, so
the cost is visible before the decision rather than after.

**Follows the change automatically — no rework:**

- `routes/chat.ts` validates field keys against `ALL_FIELD_KEYS` and builds the
  model's prompt from `FIELD_GROUPS`, both imported from `domain.ts`. Change
  `domain.ts` and both follow.
- `frontend/components/BenchmarkLine.tsx` asks the server which fields are
  benchmarkable instead of keeping its own list.

**Needs hand rework — each of these names a 22-key literal:**

| Place | Literals | What breaks |
|---|---|---|
| `webapp/src/routes/benchmark.ts:42` (`BENCHMARKABLE`) | `notice_period`, `cure_period`, `initial_term`, `renewal_term`, `effective_date`, `term_end`, `notice_deadline` | Re-key to CUAD names (`notice_period` → `notice_period_to_terminate_renewal`, `term_end` → `expiration_date`, …). Missed keys mean benchmarking silently renders nothing — it fails quiet, which is the dangerous direction. Also re-check each polarity: a CUAD category is not always the same concept as the webapp field it replaces. |
| `webapp/src/routes/invoices.ts:30` (`PARTY_FIELD_KEYS`) | `party_a`, `party_b` | Becomes `parties`. If missed, the party index is empty and **every invoice reports MISSING CONTRACT - ROGUE INVOICE** — a confident wrong answer, the worst failure shape in this product. |
| `webapp/src/routes/invoices.ts` temporal check | `effective_date`, `term_end` | If missed, every match degrades to `DATE UNVERIFIABLE`. Fails loudly, so lower risk. |
| `frontend/src/routes/Ask.tsx:16` (`EXAMPLES`) | example questions naming fields | Cosmetic only. |

**Separate from the vocabulary question — a duplication introduced this session,
deliberately and reluctantly:** `webapp/src/lib/labels.ts` mirrors
`labelForField` / `labelForTier` from `frontend/src/lib/confidence.tsx`. The
chatbot has to filter by label *server-side* (you cannot page through a whole
portfolio in the browser to find the unquoted values), and the frontend does not
import from `src/`. So the same two-line rule now exists twice. `confidence.tsx`
is authoritative if they ever disagree. This should be collapsed into one shared
module — but that is a structural change worth making *after* the worker decision,
not during it.

---

## 4. Blockers and things needing a team answer

1. **The Gemini model string is unresolved.** "Gemini Pro 3.10 preview" is not an
   OpenRouter model slug and could not be verified, so no literal was invented.
   The code defaults to the slug **already in use elsewhere in this repo**
   (`google/gemini-3.8-flash`, from `src/pdf_analyzer/stage2_vlm.py:48`) and is
   overridable with `OPENROUTER_MODEL`. **Please supply the exact slug** and it
   becomes a one-line env change.

2. **Rotate the OpenRouter key that was shared in chat.** A key pasted into a chat
   should be treated as compromised — please rotate it if that has not happened.
   For the record: no key is hardcoded anywhere, nothing is committed, and
   `webapp/.env` contains no `OPENROUTER_API_KEY` at all. The value currently in
   the shell is a 14-character placeholder left over from an earlier pipeline
   trace, which is why live calls return `401 Missing Authentication header`.

3. **Stage 3 (the "Extract" item in Althea's note) is intentionally deferred**, as
   agreed — the requirement was never clarified, so nothing was built for it.

4. **Confirm the fifth invoice status** (`DATE UNVERIFIABLE`) is wanted, per
   section 1.

---

## 5. Verification — what was actually run

**Deterministic cores, against the live database, with no model call.** This is
where the logic that decides outcomes was tested:

- Benchmarking over all 7 benchmarkable fields, every contract, including values
  parsed out of real pipeline output (`"Either party may terminate on ninety (90)
  days"` → 90 days). Traffic lights fire green / yellow / red / unrated correctly.
- Filter execution: duration comparison, date comparison, label filter including
  `na` (correctly found the one contract with no liability cap), and an invented
  field key returning zero rather than everything.
- Party matching: exact hit, rogue invoice, and a near-miss suffix pair confirmed
  **not** to match — the required behaviour, since merging them would invent a
  match.
- Temporal validation across four invoice dates on every contract that has dates.

**Full routes end to end, including the model step**, driven by a local stand-in
for OpenRouter (`OPENROUTER_BASE_URL`). Only the model's judgement was
substituted; the request shape, schema validation, filter execution, Prisma
queries, party matching, temporal checks and serialisation were all real code. All
five invoice statuses and the one-question clarification loop were reproduced this
way. **The live model call itself is unverified** — it needs a real key and the
confirmed model slug.

**In the running browser**, confirming what a judge would see: the Ask page with
badges and `Cited: Clause 3.2`; the traffic-light lines on the document page;
the invoice panel showing `MULTIPLE CONTRACTS FOUND - MANUAL REVIEW REQUIRED`
with three cited party fields; and the four Part 1 items above.

**Suites:** Python 137 passed. API and frontend typecheck clean. Both build clean.

---

## 6. Two known problems that were logged, not fixed

Both were flagged in `GAP_REPORT.md` and neither was made worse by this session.

1. **The second React app at `LIT/frontend/`** renders model text without grounding
   checks. Confirmed nothing from Features 1–3 was wired through it: it calls none
   of `/api/chat/query`, `/api/benchmark`, or `/api/invoices/*`. All new UI lives in
   `webapp/frontend/`.

2. **The demo `exclusivity_breach` conflict still sits in the `conflicts` table
   with no visual distinction** from the real `mfn_trigger` detection produced by
   Fix 2. Both are in the database right now, side by side, and a judge cannot tell
   them apart. Its source is `webapp/scripts/stub-worker.ts:604`.
   Feature 3 was built so as **not** to add to this: invoice findings are returned
   on their own channel (`resultChannel: "invoice_match"`), are never written to
   the `conflicts` table, are labelled *"invoice check · not a conflict"* on screen,
   and the word "invoice" does not appear anywhere on the Conflicts screen.

---

## 7. Git state

- Branch `testing-branch`, `HEAD` = `62f3c6b`, unchanged since the clone.
- **No merge, no fetch, no pull, no push in this session.** The reflog shows only
  the original clone and branch checkouts.
- Protected files untouched this session, confirmed by modification time — every
  edit in this session landed after 03:35, and `pipeline.py` (02:46),
  `real-worker.ts` (03:07), `cuad-map.ts` (01:54) and `tests/test_conflict_wiring.py`
  (01:52) all predate it. No Python file was changed at all.
- Everything is still local and safe to leave pending teammate review.

### Files added this session

```
webapp/src/lib/llm.ts                          OpenRouter client, scope-limited by design
webapp/src/lib/quantities.ts                   duration/date parsing out of quoted text
webapp/src/lib/labels.ts                       server mirror of the display labels (see §3)
webapp/src/lib/parties.ts                      port of Fix 2's exact-name rule
webapp/src/routes/chat.ts                      Feature 1
webapp/src/routes/benchmark.ts                 Feature 2
webapp/src/routes/invoices.ts                  Feature 3
webapp/frontend/src/routes/Ask.tsx             Feature 1 UI
webapp/frontend/src/components/BenchmarkLine.tsx   Feature 2 UI
webapp/frontend/src/components/InvoiceMatch.tsx    Feature 3 UI
```

### Files modified this session

```
webapp/src/server.ts                  +3 route registrations
webapp/frontend/src/lib/api.ts        types + client methods for the three features
webapp/frontend/src/App.tsx           /ask route
webapp/frontend/src/components/Layout.tsx    "Ask" nav link
webapp/frontend/src/routes/DocumentDetail.tsx    BenchmarkLine under fields, InvoiceMatch on invoices
```

`DocumentDetail.tsx` is the only shared file with real merge exposure — it was
already flagged for a second reviewer in `TEAM_SUMMARY.md` and this session added
two more insertion points to it.
