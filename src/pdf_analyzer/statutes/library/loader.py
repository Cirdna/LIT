"""Loading the chunk store from disk.

Files live in `chunks/`. A filename ending `_draft.json` signals work in progress;
the Phase 2 instruction is to drop `_draft` (or move the file to `chunks/verified/`)
once every chunk in it is checked. The loader does NOT infer verification from the
filename — `verification_status` on each chunk is the only thing that counts, so a
half-verified file behaves correctly instead of being trusted wholesale.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .schema import StatuteChunk, VerificationStatus

CHUNKS_DIR = Path(__file__).with_name("chunks")


class ChunkStore:
    """Every chunk that was found on disk, valid and validated."""

    def __init__(self, chunks: Sequence[StatuteChunk]) -> None:
        self._chunks: List[StatuteChunk] = list(chunks)
        by_id: Dict[str, StatuteChunk] = {}
        for chunk in self._chunks:
            if chunk.id in by_id:
                raise ValueError(f"duplicate chunk id: {chunk.id}")
            by_id[chunk.id] = chunk
        self._by_id = by_id

    def __len__(self) -> int:
        return len(self._chunks)

    def __iter__(self):
        return iter(self._chunks)

    def get(self, chunk_id: str) -> StatuteChunk:
        if chunk_id not in self._by_id:
            raise KeyError(f"no such chunk: {chunk_id}")
        return self._by_id[chunk_id]

    @property
    def all(self) -> List[StatuteChunk]:
        return list(self._chunks)

    @property
    def verified(self) -> List[StatuteChunk]:
        return [c for c in self._chunks if c.is_verified]

    @property
    def unverified(self) -> List[StatuteChunk]:
        return [c for c in self._chunks if not c.is_verified]

    def by_source(self) -> Dict[str, List[StatuteChunk]]:
        out: Dict[str, List[StatuteChunk]] = {}
        for chunk in self._chunks:
            out.setdefault(chunk.source, []).append(chunk)
        return out

    def coverage(self) -> Dict[str, Dict[str, int]]:
        """Verified / total per Act — the Phase 2 progress report."""
        return {
            source: {
                "verified": sum(1 for c in group if c.is_verified),
                "total": len(group),
            }
            for source, group in sorted(self.by_source().items())
        }


def load_file(path: Path) -> List[StatuteChunk]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("chunks", [])
    if not isinstance(raw, list):
        raise ValueError(f"{path.name}: expected a list of chunks or {{'chunks': [...]}}")
    chunks: List[StatuteChunk] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(f"{path.name}: chunk entries must be objects")
        try:
            chunks.append(StatuteChunk.from_dict(entry))
        except (ValueError, KeyError) as err:
            raise ValueError(f"{path.name}: {err}") from err
    return chunks


def load_store(directory: Optional[Path] = None) -> ChunkStore:
    """Load every `*.json` under the chunks directory (recursively)."""
    root = directory or CHUNKS_DIR
    if not root.exists():
        return ChunkStore([])
    chunks: List[StatuteChunk] = []
    for path in sorted(root.rglob("*.json")):
        chunks.extend(load_file(path))
    return ChunkStore(chunks)


def verification_worklist(store: ChunkStore) -> List[Dict[str, str]]:
    """What a human still has to check, in a form that can be worked through.

    Ordered so that the provisions the product actually cites today come first —
    verifying a chunk nothing reads is not progress.
    """
    rows: List[Dict[str, str]] = []
    for chunk in store.unverified:
        rows.append(
            {
                "id": chunk.id,
                "source": chunk.source,
                "provision": chunk.provision,
                "url": chunk.provenance.retrieved_from,
                "targets": ", ".join(chunk.target_fields) or "-",
                "note": chunk.note or "",
            }
        )
    rows.sort(key=lambda r: (r["source"], r["provision"]))
    return rows


__all__ = [
    "CHUNKS_DIR",
    "ChunkStore",
    "load_file",
    "load_store",
    "verification_worklist",
    "VerificationStatus",
]
