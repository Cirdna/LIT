"""Provision-level statute knowledge library.

The store holds curated chunks of Singapore legislation — not full Acts. A full
Act is mostly irrelevant to contract review (penalties, procedure, definitions of
things nobody cited) and putting one into a retrieval system buys noise.

Every chunk arrives `unverified_draft` and only a human can promote it. Read
`quotable_wording()` for anything a user will see; it refuses until that has
happened. `PHASE2_VERIFICATION.md` at the repo root is the worklist.
"""

from __future__ import annotations

from .loader import CHUNKS_DIR, ChunkStore, load_file, load_store, verification_worklist
from .schema import (
    CONTRACT_TYPES,
    AuthorityBasis,
    Provenance,
    RoleType,
    StatuteChunk,
    UnverifiedQuotationError,
    VerificationStatus,
    eligible_for_contract_type,
    keyword_hits,
    select,
)

__all__ = [
    "CHUNKS_DIR",
    "CONTRACT_TYPES",
    "AuthorityBasis",
    "ChunkStore",
    "Provenance",
    "RoleType",
    "StatuteChunk",
    "UnverifiedQuotationError",
    "VerificationStatus",
    "eligible_for_contract_type",
    "keyword_hits",
    "load_file",
    "load_store",
    "select",
    "verification_worklist",
]
