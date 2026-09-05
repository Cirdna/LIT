# Design plan

Checked against the brief before writing CSS. The subject is a small business
owner's contract obligations — the register is a **bank statement or a tax
notice**, not a startup marketing page. Sober, legible, dense where density
helps. Boldness is spent in exactly one place: the confidence encoding and the
calendar's action-by date.

## What this deliberately is NOT

The brief calls out the current generated-page defaults to avoid, and none of
them appear here:

- no cream background with a serif display and terracotta accent
- no near-black with one acid accent
- no identical rounded cards with the same soft shadow (we use ruled tables and
  left-rule panels instead)
- no all-caps tracked eyebrow labels as decoration
- no monospace for small data labels (tabular-nums instead, on a normal sans)
- no arrows appended to buttons for flourish

## Colour (6 named)

| Token | Hex | Use |
|---|---|---|
| `paper` | `#f3f4f5` | app background |
| `surface` | `#ffffff` | panels, rows |
| `ink` | `#181b20` | body text — well above the AA contrast minimum on white |
| `muted` | `#535a64` | secondary text |
| `rule` | `#d7dbe0` | borders, dividers |
| `navy` | `#1f3a5f` | primary — links, buttons, active nav, overlay boxes |

Plus three **semantic** confidence colours (`ok` green, `warn` amber, `alert`
red) with matching tint backgrounds. These are never used alone — see below.

## Type

One typeface: the system sans stack (fast, familiar, legible on a projector).
Base size **16.5px** so body text reads at 3 metres; a clear scale up to the
2xl headings and the calendar's action-by date. Numbers and dates use
`tabular-nums` so columns line up.

## Layout

A fixed top bar (wordmark · Portfolio · Calendar · Conflicts · the scope link,
which is reachable from every screen in one click). Content maxes at 1200px.
Document detail is a two-pane split: fields on the left, the page image on the
right, sticky so a citation stays visible while you read.

## Confidence encoding — the one non-negotiable

Every displayed value carries a confidence tier, and low-confidence values are
distinct from high-confidence ones **at a glance**. The encoding is never colour
alone (colour-blind users; projectors; photocopies). It combines **three**
independent cues:

1. **A verbal label** — “Quoted”, “Standardised”, “Assembled”, “Inferred —
   check this”, “Suspected error”.
2. **A glyph in a bordered box** — ✓ = + ~ ! — legible in monochrome.
3. **A left-rule treatment** — solid / solid-thin / solid-amber / **dashed** /
   **double-red** — a structural cue that survives greyscale.

And in lists, **position**: uncertain items sort upward, and the review queue
keys off the tier rank.

No percentages anywhere — non-experts systematically misread them. Scores
(`consistency_score`, `vlm_agreement`, OCR mean) are surfaced as **words and
plain-language reasons** (“Two extraction passes disagreed”, “OCR confidence on
this document is low”).

## Projector legibility

Generous base type, body contrast kept well above the minimum, and the
confidence distinction carried by shape + label so it does not vanish at 3
metres. Overdue calendar items are red + a heavy left rule + a large action-by
date — unmistakable from across a room.

## Quality floor

Responsive to mobile (the two-pane detail stacks), visible keyboard focus,
`prefers-reduced-motion` respected, loading skeletons rather than spinners,
optimistic UI on acknowledge/dismiss, and a print stylesheet for the handoff
brief.
