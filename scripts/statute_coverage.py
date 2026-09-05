"""Print the verification state of the statute chunk library.

Run this to see what Phase 2 still has to check:  python scripts/statute_coverage.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdf_analyzer.statutes.library import load_store, verification_worklist  # noqa: E402


def main() -> None:
    store = load_store()
    print(f"chunks on disk: {len(store)}")
    print(f"quotable to a user right now: {len(store.verified)}\n")
    for source, cov in store.coverage().items():
        print(f"  {cov['verified']:>2}/{cov['total']:<3} verified   {source}")
    stitched = [c for c in store if (c.note or "").startswith("STITCHED")]
    print(f"\nreassembled from sub-paragraphs (verify these first): {len(stitched)}")
    for chunk in stitched:
        print(f"  {chunk.source}, {chunk.provision}")
    print(f"\ntotal rows on the Phase 2 worklist: {len(verification_worklist(store))}")


if __name__ == "__main__":
    main()
