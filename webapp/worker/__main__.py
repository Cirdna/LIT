"""Run loop for the real worker.

    cd webapp
    python -m worker                 # poll forever, process ingest jobs
    python -m worker --once          # process one job then exit (for testing)
    python -m worker --prompt-mode granular   # accurate mode (41x calls; see HANDOFF §6.1)

Claims `queued` ingest jobs with FOR UPDATE SKIP LOCKED, runs the pipeline, and
writes pages / lines / fields / calendar events. It shares the `jobs` table with
the Node stub worker, so the two are interchangeable — run whichever suits the
moment (stub for a no-API-key demo, this one for real extraction).
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time

from pdf_analyzer.stage2_vlm import BACKENDS, OpenRouterError, build_vlm_backend

from . import db, storage
from .process import process_document

logger = logging.getLogger("worker")

_running = True


def _stop(_signum, _frame):
    global _running
    _running = False
    logger.info("stopping after the current job…")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="worker", description="AITHENA real ingestion worker.")
    p.add_argument("--backend", choices=list(BACKENDS),
                   default=os.environ.get("WORKER_BACKEND", "openrouter"),
                   help="VLM backend (default: openrouter).")
    p.add_argument("--prompt-mode", choices=["single", "granular"],
                   default=os.environ.get("WORKER_PROMPT_MODE", "single"),
                   help="OpenRouter prompt mode. 'granular' is more accurate at ~41x the API "
                        "calls (see HANDOFF.md §6.1); 'single' is the cheaper default.")
    p.add_argument("--model-id", default=os.environ.get("WORKER_MODEL_ID"),
                   help="Override the VLM model slug.")
    p.add_argument("--dpi", type=int, default=int(os.environ.get("WORKER_DPI", "150")),
                   help="Page render DPI for OCR + served images (default: 150).")
    p.add_argument("--granular-concurrency", type=int, default=None,
                   help="OpenRouter granular mode: category calls in parallel per page.")
    p.add_argument("--poll-interval", type=float, default=1.5,
                   help="Seconds to wait when the queue is empty (default: 1.5).")
    p.add_argument("--once", action="store_true",
                   help="Process a single job then exit (skips the poll loop).")
    p.add_argument("-v", "--verbose", action="store_true", help="Debug logging.")
    return p


def _build_backend(args):
    kwargs: dict = {}
    if args.model_id:
        kwargs["model_id"] = args.model_id
    if args.backend == "openrouter":
        kwargs["prompt_mode"] = args.prompt_mode
        if args.granular_concurrency:
            kwargs["granular_concurrency"] = args.granular_concurrency
    return build_vlm_backend(args.backend, **kwargs)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    db.load_env()
    storage.ensure_dirs()

    try:
        vlm_backend = _build_backend(args)
    except OpenRouterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            "\nThe real worker needs a VLM backend. Set OPENROUTER_API_KEY (in the repo-root "
            ".env), or run the Node stub worker instead for a no-key demo:\n"
            "    npm run stub",
            file=sys.stderr,
        )
        return 2

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    conn = db.connect()
    conn.autocommit = True  # each helper manages its own explicit transaction
    logger.info("real worker up (backend=%s, prompt-mode=%s, dpi=%d). polling jobs…",
                args.backend, getattr(args, "prompt_mode", "-"), args.dpi)

    processed = 0
    try:
        while _running:
            db.reap_stalled_jobs(conn)
            job = db.claim_next_job(conn)
            if not job:
                if args.once:
                    logger.info("no queued jobs; exiting (--once).")
                    break
                time.sleep(args.poll_interval)
                continue

            logger.info("job %s (%s) doc=%s", job["id"], job["job_type"], job["document_id"])
            try:
                if job["document_id"]:
                    process_document(conn, job, vlm_backend, dpi=args.dpi)
                db.finish_job(conn, job["id"])
                logger.info("done %s", job["id"])
            except Exception as exc:  # noqa: BLE001 — a failed doc must not kill the worker
                logger.exception("failed %s", job["id"])
                db.fail_job(conn, job["id"], job.get("document_id"), str(exc))

            processed += 1
            if args.once:
                break
    finally:
        conn.close()
        logger.info("stopped (processed %d job(s)).", processed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
