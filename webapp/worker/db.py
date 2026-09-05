"""Database access for the real worker.

Prisma owns the schema; this module treats it as read-only truth and talks to
it with psycopg + plain SQL, exactly as docs/INTEGRATION.md specifies. Nothing
here writes a table Node writes (uploads, acknowledgements, handoffs) — the
worker only writes facts about a document.

Two things worth knowing:

- The `DATABASE_URL` in webapp/.env is a *Prisma* connection string and carries
  a `?schema=public` query parameter that libpq does not understand. We rewrite
  it into a libpq URI (schema -> `options=-c search_path=...`) before handing it
  to psycopg.
- Job claiming uses `FOR UPDATE SKIP LOCKED` so multiple workers (and the stub)
  can run against the same queue with no external broker.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlsplit, urlunsplit

import psycopg
from psycopg.rows import dict_row

_WEBAPP_ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    """Load .env files into os.environ without adding a dotenv dependency.

    Reads webapp/.env (DATABASE_URL, STORAGE_ROOT) and the repo-root .env
    (OPENROUTER_API_KEY, per HANDOFF.md). Only sets keys not already present, so
    an explicit `DATABASE_URL=... python -m worker` still wins, and the first
    file to define a key wins over later ones.
    """
    candidates = [_WEBAPP_ROOT / ".env", _WEBAPP_ROOT.parent / ".env"]
    for env_path in candidates:
        if not env_path.exists():
            continue
        for raw in env_path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _sanitize_conninfo(database_url: str) -> tuple[str, dict[str, str]]:
    """Split a Prisma-style DATABASE_URL into a libpq URL + keyword params.

    Prisma appends `?schema=public`; libpq rejects an unknown `schema` query
    parameter. We translate it into a `search_path` via the libpq `options`
    param and pass it (plus any genuine libpq params) as keyword arguments
    rather than re-encoding them into the URL — URL-encoding the space in
    `-c search_path=...` as `+` is exactly what libpq then mis-parses. Prisma-only
    keys (connection_limit, pgbouncer, ...) are dropped.
    """
    parts = urlsplit(database_url)
    query = parse_qs(parts.query)

    extra: dict[str, str] = {}
    schema = query.pop("schema", [None])[0]
    if schema:
        extra["options"] = f"-c search_path={schema}"
    for libpq_key in ("sslmode", "connect_timeout", "application_name"):
        if libpq_key in query:
            extra[libpq_key] = query[libpq_key][0]

    clean_url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))
    return clean_url, extra


def connect() -> psycopg.Connection:
    """Open a connection. Caller manages transactions."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Run from webapp/ (so webapp/.env is found) "
            "or export it explicitly."
        )
    clean_url, extra = _sanitize_conninfo(database_url)
    conn = psycopg.connect(clean_url, row_factory=dict_row, **extra)
    return conn


# ---- Job queue -----------------------------------------------------------


def claim_next_job(conn: psycopg.Connection) -> Optional[dict[str, Any]]:
    """Claim exactly one queued job with FOR UPDATE SKIP LOCKED.

    Runs in its own committed transaction so the claim is durable before we
    start the (long) processing work.
    """
    with conn.transaction():
        row = conn.execute(
            """
            UPDATE jobs SET status='running', started_at=now(), attempts=attempts+1
            WHERE id = (
              SELECT id FROM jobs
              WHERE status='queued'
              ORDER BY created_at
              FOR UPDATE SKIP LOCKED
              LIMIT 1
            )
            RETURNING id, document_id, job_type, workspace_id
            """
        ).fetchone()
    return row


def reap_stalled_jobs(conn: psycopg.Connection) -> None:
    """Requeue jobs stuck 'running' > 15 min (up to 3 attempts), then fail them.

    A failed document must never block the batch. Mirrors the stub worker's
    reaper so behaviour is identical whichever worker is running.
    """
    with conn.transaction():
        conn.execute(
            """
            UPDATE jobs SET status='queued', started_at=NULL, stage='requeued after stall'
            WHERE status='running' AND started_at < now() - interval '15 minutes' AND attempts < 3
            """
        )
        conn.execute(
            """
            UPDATE jobs SET status='failed', finished_at=now(),
                           error='Exceeded max attempts after stalls'
            WHERE status='running' AND started_at < now() - interval '15 minutes' AND attempts >= 3
            """
        )
        conn.execute(
            """
            UPDATE documents SET status='failed', error='Processing stalled and exceeded retries'
            WHERE status='processing' AND id IN (
              SELECT document_id FROM jobs
              WHERE status='failed' AND error='Exceeded max attempts after stalls'
                AND document_id IS NOT NULL
            )
            """
        )


def set_progress(conn: psycopg.Connection, job_id: str, stage: str, progress: float) -> None:
    with conn.transaction():
        conn.execute(
            "UPDATE jobs SET stage=%s, progress=%s WHERE id=%s",
            (stage, progress, job_id),
        )


def finish_job(conn: psycopg.Connection, job_id: str) -> None:
    with conn.transaction():
        conn.execute(
            "UPDATE jobs SET status='done', progress=1, finished_at=now() WHERE id=%s",
            (job_id,),
        )


def fail_job(conn: psycopg.Connection, job_id: str, document_id: Optional[str], error: str) -> None:
    with conn.transaction():
        conn.execute(
            "UPDATE jobs SET status='failed', error=%s, finished_at=now() WHERE id=%s",
            (error[:2000], job_id),
        )
        if document_id:
            conn.execute(
                "UPDATE documents SET status='failed', error=%s WHERE id=%s",
                (error[:2000], document_id),
            )
