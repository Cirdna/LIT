# AITHENA web application

A contract-portfolio tool for a non-lawyer: upload contracts, see a portfolio,
read clause-level citations for every extracted value, and get a forward
calendar of deadlines. **Every displayed value carries a confidence tier and a
citation**, and low-confidence values are visually distinct at a glance — that
is the product's one non-negotiable requirement.

This is the **web application** half. OCR and field extraction are done by a
separate Python pipeline (the rest of this repo, under `../src/pdf_analyzer`).
The two halves talk **only** through the database and the `./storage` directory
— see [`docs/INTEGRATION.md`](docs/INTEGRATION.md).

There are **two interchangeable workers**, sharing the same `jobs` table:

- the **real worker** ([`worker/`](worker/), Python) drives the pipeline and
  produces genuine extractions — run it for real output;
- a Node **stub worker** ([`scripts/stub-worker.ts`](scripts/stub-worker.ts))
  produces realistic fake data across every confidence tier, so the whole
  frontend is buildable and demoable with **no API key**.

```
React SPA ──HTTP──▶ Node API (Fastify) ──SQL──▶ PostgreSQL ◀──SQL── Python worker
                                                    ▲                (or the stub)
                                                    └──── ./storage ─────┘
```

## Prerequisites

- **Node 20+**
- **PostgreSQL 16** — via Docker (below), or a free hosted DB on
  [Neon](https://neon.tech) / [Supabase](https://supabase.com) if the demo
  machine has no Docker. Paste its connection string into `.env` as
  `DATABASE_URL` and skip `docker compose`.

Why Postgres and not something lighter: the core product is date arithmetic over
renewal cycles (real `date`/`interval` types), the extraction payload churns
(`jsonb`), anchor line IDs are arrays, and the job queue uses
`SELECT … FOR UPDATE SKIP LOCKED` — none of which SQLite gives you. See §3 of the
build spec.

## Run it

From this `webapp/` directory:

```bash
# 1. Start Postgres (or point DATABASE_URL at a hosted DB and skip this)
docker compose up -d

# 2. Configure + install
cp .env.example .env
npm install

# 3. Create the schema and seed the workspace + demo corpus
npm run setup            # prisma generate + db push + seed

# 4. Terminal A — run a worker (processes queued documents)
npm run stub                       # no-key demo: realistic fake data
#   …or the REAL worker (genuine extraction; needs OPENROUTER_API_KEY):
#   pip install -e "..[dev,webapp]" && python -m worker   # see worker/README.md

# 5. Terminal B — run the API
npm run dev

# 6. Terminal C — run the frontend
cd frontend && npm install && npm run dev
```

Open **http://localhost:5173**. The stub worker takes ~1 minute to process the
eight seeded documents; you'll see live progress in the portfolio. The **real
worker** ([`worker/`](worker/)) is a drop-in replacement — it claims the same
jobs and writes the same tables, but runs the `pdf_analyzer` pipeline on real
uploads. Upload a PDF from the portfolio and it processes end to end.

> Using Prisma migrations instead of `db push`? Run
> `npm run migrate -- --name init` in place of step 3's `setup`, then
> `npm run seed`.

## What the demo corpus shows

The seed + stub worker produce a scenario that exercises every judged
requirement:

- **Overdue action** — the Northwind NDA auto-renews soon but its notice window
  already closed (top of the calendar, in red).
- **Cross-document conflict** — the Acme agreement grants *exclusive* Singapore
  rights; the later Borden agreement grants *overlapping* rights. Raises a
  conflict and an auto-generated handoff brief.
- **Scanned + illegible** — the Contoso lease is OCR'd with a low-confidence,
  unreadable page; a field on it reports `illegible`.
- **Fabrication signal** — the Globex MSA has an `unverified` value (quoted text
  not found in the cited clause) rendered as a suspected error, and an
  `assembled` liability cap.
- **Not a contract** — an invoice, visibly excluded from analysis.
- **All five confidence tiers** and **all seven field groups** on every contract.

## Commands

| Command | What it does |
|---|---|
| `npm run dev` | API with reload on :3001 |
| `npm run stub` | Stub worker: claims jobs, generates fake data |
| `npm run seed` | Workspace + demo corpus (queued jobs) |
| `npm run setup` | generate + `db push` + seed |
| `npm run typecheck` | Type-check API + worker + seed |
| `npm run db:reset` | Drop and recreate everything |
| `GET /api/integrity` | Reports dangling anchors / invariant violations (should be empty) |

## Layout

```
webapp/
  src/            Fastify API (routes/, lib/), config, Prisma client
  scripts/        stub-worker.ts, corpus.ts, png.ts (dependency-free PNG encoder)
  worker/         real Python worker: runs pdf_analyzer, writes the DB (mapping.py)
  prisma/         schema.prisma, seed.ts
  frontend/       React + Vite + TS + Tailwind, TanStack Query
  storage/        shared filesystem seam (originals, ocr, pages, tmp)
  docs/           INTEGRATION.md (Python contract), DESIGN.md
  docker-compose.yml
```

## Verified

Run end-to-end against a real PostgreSQL 16 (installed locally via Homebrew,
since the build machine had no Docker):

- Schema validates; `prisma db push` syncs it; the seed creates the workspace +
  8-document corpus.
- The stub worker claimed every job with `FOR UPDATE SKIP LOCKED` and produced
  **150 fields, 27 pages, 1016 anchor lines, 9 calendar events** across **all 5
  confidence tiers**, **all 3 absence reasons**, and **all 3 claim types**.
- `GET /api/integrity` returns `ok: true` with **zero dangling anchors** and no
  invariant violations.
- Upload behaviours: supported file → `queued` + `jobId`; identical re-upload →
  `duplicate: true` (no new row); unsupported/rejected file → `unsupported` with
  a readable message; a mixed batch does not let a bad file abort the others.
- Endpoints exercised: portfolio summary, documents list (with term-end /
  next-action / needs-review enrichment), document detail (fields grouped, tier
  + resolved citation page), anchors, page image (valid PNG, `image/png`,
  immutable cache), calendar (overdue item + bands), conflicts (paired clauses
  from two documents), the auto-generated handoff brief, and the calendar
  acknowledge PATCH.
- The frontend type-checks and builds (`cd frontend && npm run build`).

The type-check covers the API, the stub worker, and the seed (`npm run
typecheck`). Nothing is DB-mocked — the above ran the real Prisma queries.
