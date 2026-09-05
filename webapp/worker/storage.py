"""Storage path layout, mirroring webapp/src/config.ts exactly.

Both halves of the seam must agree on these paths. The worker reads the
uploaded original from `originals/` and writes rendered page PNGs to
`pages/<document_id>/p<N>@<dpi>.png`, which Node serves back verbatim.
"""

from __future__ import annotations

import os
from pathlib import Path


def storage_root() -> Path:
    return Path(os.environ.get("STORAGE_ROOT", "./storage")).resolve()


def originals_dir() -> Path:
    return storage_root() / "originals"


def pages_dir() -> Path:
    return storage_root() / "pages"


def resolve_key(key: str) -> Path:
    """Absolute path for any storage_key / image_key stored in the DB."""
    return storage_root() / key


def page_image_key(document_id: str, page_number: int, dpi: int) -> str:
    """Relative image_key, matching config.ts `storage.pageImageKey`."""
    return os.path.join("pages", str(document_id), f"p{page_number}@{dpi}.png")


def page_image_path(document_id: str, page_number: int, dpi: int) -> Path:
    return storage_root() / page_image_key(document_id, page_number, dpi)


def ensure_dirs() -> None:
    for d in (originals_dir(), pages_dir(), storage_root() / "ocr", storage_root() / "tmp"):
        d.mkdir(parents=True, exist_ok=True)
