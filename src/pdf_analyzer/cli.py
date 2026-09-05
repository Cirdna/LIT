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
from .stage2_vlm import DEFAULT_INTERNVL_MODEL_ID, DEFAULT_QWEN_MODEL_ID, build_vlm_backend
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
        "--backend", choices=["qwen", "internvl"], default="qwen", help="VLM backend to use."
    )
    analyze.add_argument(
        "--model-id",
        default=None,
        help=f"Override the VLM model id (defaults: qwen={DEFAULT_QWEN_MODEL_ID}, "
        f"internvl={DEFAULT_INTERNVL_MODEL_ID}).",
    )
    analyze.add_argument(
        "--device", default=None, help="Torch device for VLM inference (default: auto-detect)."
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

        backend_kwargs = {"device": args.device} if args.device else {}
        if args.model_id:
            backend_kwargs["model_id"] = args.model_id
        vlm_backend = build_vlm_backend(args.backend, **backend_kwargs)

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
