# Markdown Consolidation Plan

**Status: EXECUTED on 2026-09-06. Nothing was deleted.**

This file is itself now in `docs/session-log/`, which is what it proposed.

| Decision | Outcome |
|---|---|
| Archive moves (§3) | **Executed.** Five reports plus this plan moved to `docs/session-log/`. No deletions. |
| `HANDOFF.md` | **Stays at root** - cited as live evidence by `WIRING_STATUS.md`. |
| The three spec files | **Done** - recovered to `docs/spec/`. See §0. |
| Deletions | **None.** Nothing in this repo turned out to be genuinely redundant; see §2. `.pytest_cache/` was the only true junk and `.gitignore` already excludes it. |

Root now holds four markdown files: `MASTER_SUMMARY.md`, `PHASE2_VERIFICATION.md`,
`README.md`, `HANDOFF.md`.

Scope of the search: every `.md` file in the repository, excluding `node_modules`,
`.venv` and `.git`. Pre-existing versus session-created was determined with
`git ls-files "*.md"` (tracked = pre-existing, since no commit was made this session),
not by timestamp - all tracked files share a `09-06 01:20` mtime from the branch
checkout, so timestamps alone would be misleading.

---

## 0. Five files named in the brief were not in the repo - three are now recovered

None of these were in the repository. Two were found elsewhere on disk; one was recovered
from the chat transcript; two never existed.

| File | Status | Now at |
|---|---|---|
| `grounded_legal_engine_spec.md` | found in `~\Downloads\Telegram Desktop\` | `docs/spec/` - **copied byte-identical** (SHA-256 verified) |
| `grounded_legal_engine_spec_v2_1.md` | found in `~\Downloads\Telegram Desktop\` | `docs/spec/` - **copied byte-identical** (SHA-256 verified) |
| `grounded_legal_engine_spec_addendum.md` | never a file; pasted into chat 2026-09-06 04:02 | `docs/spec/` - **recovered verbatim from the transcript** |
| `RECONCILIATION_REPORT.md` | never written | - |
| `CLEANUP_CANDIDATES.md` | never written | - |

The originals in `Downloads\Telegram Desktop` were **copied, not moved**, so they remain
untouched where you left them.

The addendum needed different handling because it was only ever a chat message. Its
recovered file carries a provenance header stating that, and naming the two things dropped
(the `<user_query>` wrapper and a trailing attachment marker). One typo in the original -
an apostrophe where a `>` blockquote marker belongs - is preserved rather than silently
corrected.

**Why this mattered.** The code cites these documents constantly: `library/schema.py`
cites "spec v2.1 §2/§3", the chunk files cite "v2.1 §4", `PHASE2_VERIFICATION.md` cites
them throughout. Until now those citations pointed at nothing inside the repo.

**Two things fell out of reading the recovered v2.1 spec:**

1. All my code's spec citations check out. §2 is the Contract Classification Gate, §3 is
   the Knowledge Library Architecture (where `applicability_conditions` and the "UCTA fires
   on every populated liability field" fix are defined), §4 is Role A/B logic.
2. **The Supply of Goods Act scoping error originates in the spec itself.** §4 states
   `Supply of Goods Act (Cap 394): applicable_contract_types: [services, hire_purchase]`.
   That is wrong for Singapore on both counts, and the correction I made in the chunk
   library therefore contradicts the spec by design. §4 needs amending, not just the code -
   this is now item 1 of the three statute findings awaiting sign-off.

---

## 1. Every `.md` file, with what it contains

### Session-created (untracked - all six are new this session)

| File | Modified | Lines | What it contains |
|---|---|---|---|
| `AUDIT_REPORT.md` | 09-06 01:41 | 177 | Phase 1 audit. Scores six must-haves under a strict "live execution path" test. Its central finding: two disconnected stacks sharing no worker, schema or vocabulary, and `docs/INTEGRATION.md` describing a Python worker that did not exist. |
| `WIRING_STATUS.md` | 09-06 02:17 | 184 | Fix 1 and Fix 2 verification. Records both as PASS with the one necessary substitution (scripted Stage 2b reply, no API key) stated explicitly, plus a "still stub, still missing" list and demo instructions. |
| `TEAM_SUMMARY.md` | 09-06 03:29 | 247 | Written for teammates: what exists by feature area, who built what (Hannah 12 commits, andric 2), a merge risk map, a suggested merge order, and a deliberately-not-done list. |
| `GAP_REPORT.md` | 09-06 03:31 | 387 | The most thorough audit. Whole repo against eight requirements, with per-claim line citations, **including a separate checkout of `c50cab9` to audit teammate work**. Ends with a prioritised remaining-work list. |
| `STATUS_UPDATE.md` | 09-06 04:01 | 232 | Features 1-3 report. UI confirmations, the `origin/main` conflict, what Features 1-3 assume about the 22-key vocabulary, blockers, what was actually run, and two logged-not-fixed problems. |
| `PHASE2_VERIFICATION.md` | 09-06 04:18 | 152 | **Active checklist.** The human verification worklist for 34 unverified statute chunks: how to verify one, the 7 stitched chunks in priority order, 3 findings needing legal sign-off, known gaps, and the citation-format decision. |

Plus, written in this pass:

| File | What it contains |
|---|---|
| `MASTER_SUMMARY.md` | Timeline of all work with PASS/PARTIAL/NOT DONE, real-vs-stub list, open items, test count, and the `origin/main` situation. |
| `CONSOLIDATION_PLAN.md` | This file. |

### Pre-existing project documentation (tracked in git - do not touch)

| File | Lines | What it contains |
|---|---|---|
| `README.md` | 117 | Project readme for the Python pipeline. |
| `HANDOFF.md` | 325 | Prior session's change log, test results and known problems. Cited by `WIRING_STATUS.md` as the evidence for the live hosted VLM call (A2.5) - **still load-bearing**. |
| `webapp/README.md` | 108 | Webapp setup and run instructions. |
| `webapp/docs/DESIGN.md` | 63 | Webapp design notes. |
| `webapp/docs/INTEGRATION.md` | 117 | The DB + storage seam contract between Node and Python. |

### Generated - ignore

| File | Note |
|---|---|
| `.pytest_cache/README.md` | Pytest artifact. Should be gitignored, not archived. |

---

## 2. What is genuinely superseded

I applied a deliberately conservative test: a file is superseded only if
`MASTER_SUMMARY.md` contains **everything meaningful** in it, not merely the same topic.

**Nothing passes that test outright.** Every one of the five status reports contains at
least one thing `MASTER_SUMMARY.md` does not:

- `AUDIT_REPORT.md` - the original per-must-have scorecard and the "what would have to
  exist to flip this score" analysis. `MASTER_SUMMARY.md` reports the current state, not
  the scoring rubric that produced it.
- `WIRING_STATUS.md` - the step-by-step demo instructions for the real path, and the
  precise statement of which stages ran for real during the Fix 1/2 trace.
- `TEAM_SUMMARY.md` - **git attribution** (who wrote which commits) and the suggested merge
  order. Deliberately excluded from `MASTER_SUMMARY.md`; not recoverable from it.
- `GAP_REPORT.md` - **per-claim line-number citations**, and the audit of `c50cab9`
  performed by checking that commit out. `MASTER_SUMMARY.md` summarises the merge hazard
  but does not reproduce the file-by-file audit of teammate code.
- `STATUS_UPDATE.md` - the analysis of what Features 1-3 assume about the 22-key
  vocabulary, which is the thing that will matter most if `domain.ts` on main moved the
  vocabulary.

So the honest framing is **archive, not supersede**: `MASTER_SUMMARY.md` becomes the single
entry point, and these five stay reachable as the detailed record behind it. That matches
what the brief asked for (archive, don't delete) and I am not proposing any deletion.

---

## 3. Proposed moves

| File | Proposed fate | Reasoning |
|---|---|---|
| `MASTER_SUMMARY.md` | **keep at root** | The one file to read first. |
| `PHASE2_VERIFICATION.md` | **keep at root** | Explicitly protected by the brief. It is an active work checklist, not a status report - 34 chunks await human verification and it is the only place the procedure and priority order are written down. Must not be archived or folded in. |
| `README.md` | **keep at root** | Pre-existing project documentation. |
| `HANDOFF.md` | **keep at root** | Pre-existing, committed, and still cited as the evidence for the live hosted VLM call. Archiving it would break a live citation in `WIRING_STATUS.md`. |
| `webapp/README.md` | **leave in place** | Pre-existing. |
| `webapp/docs/DESIGN.md` | **leave in place** | Pre-existing. |
| `webapp/docs/INTEGRATION.md` | **leave in place** | Pre-existing, and the seam contract both worker designs are judged against - directly relevant to the `origin/main` decision. |
| `AUDIT_REPORT.md` | move to `docs/session-log/AUDIT_REPORT.md` | Point-in-time audit, superseded as a status report but valuable as the origin of the scoring. |
| `WIRING_STATUS.md` | move to `docs/session-log/WIRING_STATUS.md` | Fix 1/2 evidence record. |
| `TEAM_SUMMARY.md` | move to `docs/session-log/TEAM_SUMMARY.md` | Retains unique git attribution and merge-order advice. |
| `GAP_REPORT.md` | move to `docs/session-log/GAP_REPORT.md` | Retains unique per-line citations and the `c50cab9` audit. |
| `STATUS_UPDATE.md` | move to `docs/session-log/STATUS_UPDATE.md` | Retains the unique Features 1-3 vocabulary analysis. |
| `.pytest_cache/README.md` | **not a doc** | Add `.pytest_cache/` to `.gitignore` instead. |

Nothing is proposed for deletion.

Resulting root: `MASTER_SUMMARY.md`, `PHASE2_VERIFICATION.md`, `README.md`, `HANDOFF.md`.

### Suggested addition

A short `docs/session-log/README.md` saying these are point-in-time records superseded as
status by `MASTER_SUMMARY.md`, kept for their unique detail, and naming what each one
uniquely holds - so a future reader does not have to open five files to find out which is
worth reading.

---

## 4. Needs your call

Resolved:

- ~~The three spec files~~ - **done**, recovered to `docs/spec/` (§0).
- ~~`HANDOFF.md`~~ - **stays at root**, as it is cited as live evidence.

Still open:

1. **Committing before reorganising.** All session work is uncommitted. Moving files while
   in that state is safe in itself, but the underlying exposure is not: a stray checkout
   loses everything. My recommendation is to commit first, then move.
2. **Should the moves be `git mv`?** These files are untracked, so `git mv` will not work
   on them; a plain move is required unless they are staged first.
3. **Should `docs/spec/` be committed?** The two copied files are someone else's authored
   documents. Committing them puts the design authority under version control, which is the
   point - but confirm that is wanted rather than assumed.
4. **Spec §4 needs a correction** for the Supply of Goods Act scoping (§0). That is a spec
   edit, not a file move, and it needs whoever owns the spec to make it.

---

## 5. What was actually run

```powershell
# from repo root: c:\Users\USER\Documents\side_proj\LIT hackathon\LIT
New-Item -ItemType Directory -Force -Path docs\session-log | Out-Null
Move-Item AUDIT_REPORT.md      docs\session-log\
Move-Item WIRING_STATUS.md     docs\session-log\
Move-Item TEAM_SUMMARY.md      docs\session-log\
Move-Item GAP_REPORT.md        docs\session-log\
Move-Item STATUS_UPDATE.md     docs\session-log\
Move-Item CONSOLIDATION_PLAN.md docs\session-log\
```

Follow-ups completed: `MASTER_SUMMARY.md` gained a pointer to `docs/session-log/` and
`docs/spec/`; `docs/session-log/README.md` was added as an index naming what each archived
report uniquely holds.

Cross-references were checked afterwards. Every mention of a moved file is an inline code
span rather than a markdown hyperlink, so nothing dangles. The three cross-references
between archived files (`STATUS_UPDATE.md` and `TEAM_SUMMARY.md` to `GAP_REPORT.md`) still
resolve because those files moved together.
