"""CLI entrypoint: run the full pipeline against a single input document, or
scan already-analyzed documents for cross-contract conflicts.

Usage:
    python -m pdf_analyzer.cli analyze input.docx --output result.json
    python -m pdf_analyzer.cli analyze input.pdf --backend internvl --device cuda
    python -m pdf_analyzer.cli conflicts ./analysis --output queue.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .pipeline import analyze_and_write, load_analysis, scan_for_conflicts
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
        help="OpenRouter only: pages processed in parallel (default: 4 for --prompt-mode single, "
        "1 for granular, since granular already parallelizes within a page).",
    )
    analyze.add_argument(
        "--prompt-mode",
        choices=["single", "granular"],
        default="single",
        help="OpenRouter only: 'single' asks about all 41 CUAD categories in one call per page "
        "(fast, cheap, but a clause satisfying multiple categories at once gets forced into just "
        "one). 'granular' asks about each category separately (41 calls/page) so the same clause "
        "can correctly match several categories, at ~41x the request volume and cost.",
    )
    analyze.add_argument(
        "--granular-concurrency",
        type=int,
        default=None,
        help="OpenRouter granular mode only: category calls processed in parallel per page "
        "(default: 8).",
    )
    analyze.add_argument(
        "--max-pixels",
        type=int,
        default=None,
        help="Qwen backend only: cap on per-image pixel count fed to the VLM (default: "
        "1280*28*28). Lower this if you hit an MPS/CPU out-of-memory error on generate(); "
        "raise it (e.g. on a CUDA GPU with flash-attention) for sharper reads of small print.",
    )
    analyze.add_argument(
        "--contract-id",
        default=None,
        help="Identifier this contract is reported under (default: the input filename stem). "
        "Set it to the caller's own document ID so a flagged conflict names something "
        "the caller can resolve.",
    )
    analyze.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")

    conflicts = sub.add_parser(
        "conflicts",
        help="Scan analysis JSON files for cross-contract conflicts (no model calls).",
    )
    conflicts.add_argument(
        "inputs",
        type=Path,
        nargs="+",
        help="Analysis JSON files produced by `analyze`, and/or directories containing them.",
    )
    conflicts.add_argument(
        "--output", type=Path, default=Path("conflicts.json"), help="Where to write the review queue."
    )
    conflicts.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")

    return parser


def _collect_analysis_files(inputs: list[Path]) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        if item.is_dir():
            files.extend(sorted(item.glob("*.json")))
        elif item.exists():
            files.append(item)
    # Same document analyzed twice would pair with itself; dedupe by path.
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in files:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


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
            backend_kwargs["prompt_mode"] = args.prompt_mode
            if args.concurrency:
                backend_kwargs["concurrency"] = args.concurrency
            if args.granular_concurrency:
                backend_kwargs["granular_concurrency"] = args.granular_concurrency
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
            contract_id=args.contract_id,
        )
        print(f"Wrote analysis to {output_path}")
        return 0

    if args.command == "conflicts":
        files = _collect_analysis_files(args.inputs)
        if not files:
            print("error: no analysis JSON files found in the given paths", file=sys.stderr)
            return 1

        analyses = []
        for path in files:
            try:
                analyses.append(load_analysis(path))
            except Exception as exc:  # a half-written or foreign JSON must not abort the scan
                print(f"warning: skipping {path}: {exc}", file=sys.stderr)

        if not analyses:
            print("error: none of the given files parsed as an analysis", file=sys.stderr)
            return 1

        queue = scan_for_conflicts(analyses)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(queue.to_json_dict(), indent=2))
        print(
            f"Scanned {len(analyses)} analyses "
            f"({queue.party_pass_groups} party groups, {queue.asset_pass_groups} asset groups); "
            f"flagged {len(queue.conflicts)} conflict(s) -> {args.output}"
        )
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
