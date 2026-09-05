"""CLI entrypoint: run the full pipeline against a single input document.

Usage:
    python -m pdf_analyzer.cli analyze input.docx --output result.json
    python -m pdf_analyzer.cli analyze input.pdf --backend internvl --device cuda
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .pipeline import analyze_and_write
from .stage2_vlm import (
    BACKENDS,
    DEFAULT_INTERNVL_MODEL_ID,
    DEFAULT_OPENROUTER_MODEL_ID,
    DEFAULT_QWEN_MODEL_ID,
    OpenRouterError,
    build_vlm_backend,
)
from .stage3_reconcile import VERIFICATION_THRESHOLD


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pdf_analyzer", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="Run the full pipeline on one document.")
    analyze.add_argument("input", type=Path, help="Path to a DOCX/HTML/RTF/PDF contract.")
    analyze.add_argument(
        "--output", type=Path, default=Path("result.json"), help="Where to write the output JSON."
    )
    analyze.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Directory for intermediate PDFs/page images (default: <output>.work/).",
    )
    analyze.add_argument("--dpi", type=int, default=300, help="Page render DPI (default: 300).")
    analyze.add_argument(
        "--threshold",
        type=float,
        default=VERIFICATION_THRESHOLD,
        help=f"Verification match-score threshold, 0-100 (default: {VERIFICATION_THRESHOLD}).",
    )
    analyze.add_argument(
        "--backend",
        choices=list(BACKENDS),
        default="openrouter",
        help="VLM backend (default: openrouter, a hosted model; 'qwen'/'internvl' run locally).",
    )
    analyze.add_argument(
        "--model-id",
        default=None,
        help=f"Override the VLM model id (defaults: openrouter={DEFAULT_OPENROUTER_MODEL_ID}, "
        f"qwen={DEFAULT_QWEN_MODEL_ID}, internvl={DEFAULT_INTERNVL_MODEL_ID}). Any "
        "vision-capable slug from https://openrouter.ai/models works.",
    )
    analyze.add_argument(
        "--device",
        default=None,
        help="Local backends only: torch device for inference (default: auto-detect).",
    )
    analyze.add_argument(
        "--concurrency",
        type=int,
        default=None,
        help="OpenRouter only: pages processed in parallel (default: 4).",
    )
    analyze.add_argument(
        "--max-pixels",
        type=int,
        default=None,
        help="Qwen backend only: cap on per-image pixel count fed to the VLM (default: "
        "1280*28*28). Lower this if you hit an MPS/CPU out-of-memory error on generate(); "
        "raise it (e.g. on a CUDA GPU with flash-attention) for sharper reads of small print.",
    )
    analyze.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.command == "analyze":
        if not args.input.exists():
            print(f"error: input file not found: {args.input}", file=sys.stderr)
            return 1

        work_dir = args.work_dir or args.output.with_suffix("").with_name(args.output.stem + ".work")

        backend_kwargs = {}
        if args.model_id:
            backend_kwargs["model_id"] = args.model_id
        if args.backend == "openrouter":
            if args.concurrency:
                backend_kwargs["concurrency"] = args.concurrency
        else:
            if args.device:
                backend_kwargs["device"] = args.device
            if args.max_pixels and args.backend == "qwen":
                backend_kwargs["max_pixels"] = args.max_pixels

        try:
            vlm_backend = build_vlm_backend(args.backend, **backend_kwargs)
        except OpenRouterError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

        output_path = analyze_and_write(
            input_path=args.input,
            work_dir=work_dir,
            output_json=args.output,
            vlm_backend=vlm_backend,
            dpi=args.dpi,
            verification_threshold=args.threshold,
        )
        print(f"Wrote analysis to {output_path}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
