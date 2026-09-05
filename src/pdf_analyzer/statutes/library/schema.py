"""The provision-level statute chunk, and the gate that keeps quotations honest.

WHY THIS EXISTS
Until now every statutory `effect` in this package was a hand-written paraphrase
and `verbatim_text` was deliberately always None (see statutes/_catalogue.py).
That was the right call while there was no verified source of statutory wording:
a paraphrase presented as a paraphrase is honest, a paraphrase presented as a
quotation is a fabricated citation.

This module is what makes real quotation possible without giving up that
guarantee. A chunk carries the provision's wording AND a verification stamp, and
the only accessor that returns wording for display refuses to do so until a human
has checked it character-for-character against Singapore Statutes Online.

THE ONE RULE
`quotable_wording()` is the only way to get text for a user. It raises unless
`verification_status == VERIFIED`. Reaching past it to `draft_wording` is
possible — the field is named so that doing so is visibly a choice, and so that
it shows up in review — but nothing in the rendering path may do it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


class VerificationStatus(str, Enum):
    """Whether a human has checked the wording against the official text."""

    UNVERIFIED_DRAFT = "unverified_draft"
    VERIFIED = "verified"


class RoleType(str, Enum):
    ROLE_A_DEFAULT = "role_a_default"
    ROLE_B_VALIDATOR = "role_b_validator"


class AuthorityBasis(str, Enum):
    """What the citation actually rests on (spec v2.1 §3).

    `CASE_LAW_GLOSS` matters: a chunk whose real authority is a judicial
    interpretation must cite the case, not just the section. Misrepresentation
    Act s.3 catching non-reliance clauses is the worked example — the bare
    section does not say so.
    """

    STATUTE_TEXT = "statute_text"
    CASE_LAW_GLOSS = "case_law_gloss"


class UnverifiedQuotationError(RuntimeError):
    """Raised when unverified statutory wording is asked for as a quotation."""


@dataclass(frozen=True)
class Provenance:
    """Where the draft wording came from, so Phase 2 can retrace it.

    `transcription` records HOW the draft was produced. `machine_assisted_from_source`
    means a model transcribed it from the official page — the Phase 1 process.
    Anything recalled from model memory rather than read from source would be
    `model_recall`, which is not an accepted value for a shipped draft: it is the
    fabrication risk the whole scheme exists to prevent, so the loader rejects it.
    """

    retrieved_from: str
    retrieved_at: str
    revised_edition: str
    transcription: str = "machine_assisted_from_source"

    ACCEPTED_TRANSCRIPTION = ("machine_assisted_from_source", "human_transcribed")

    def validate(self, chunk_id: str) -> None:
        if self.transcription not in self.ACCEPTED_TRANSCRIPTION:
            raise ValueError(
                f"{chunk_id}: transcription={self.transcription!r} is not an accepted "
                f"provenance. Wording must be read from the official source, not recalled."
            )
        if not self.retrieved_from.startswith("https://sso.agc.gov.sg/"):
            raise ValueError(
                f"{chunk_id}: retrieved_from must be a Singapore Statutes Online URL, "
                f"got {self.retrieved_from!r}"
            )
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.retrieved_at):
            raise ValueError(f"{chunk_id}: retrieved_at must be YYYY-MM-DD")


@dataclass(frozen=True)
class StatuteChunk:
    """One provision, with everything needed to decide whether it may fire."""

    id: str
    source: str
    provision: str
    # NAMED `draft_` ON PURPOSE. This is the unchecked transcription. Use
    # `quotable_wording()` for anything a user will read.
    draft_wording: str
    summary: str
    role_type: RoleType
    target_fields: Tuple[str, ...]
    trigger_keywords: Tuple[str, ...]
    verification_status: VerificationStatus
    provenance: Provenance
    # v2.1 §2/§3: the predicate that must be independently satisfied. Field
    # presence alone is never enough — that was the "UCTA fires on every
    # populated liability field" bug.
    applicable_contract_types: Tuple[str, ...] = ()
    applicability_conditions: Tuple[str, ...] = ()
    authority_basis: AuthorityBasis = AuthorityBasis.STATUTE_TEXT
    category: str = "statute"
    # Legacy "Cap" citation, kept for cross-reference against older drafting.
    # Singapore renumbered in the 2020 Revised Edition; citing Cap numbers as
    # current is itself a (mild) citation error.
    legacy_citation: Optional[str] = None
    # Set only when verification_status is VERIFIED.
    verified_as_at: Optional[str] = None
    verified_by: Optional[str] = None
    # Phase 1 writes here whenever it is not fully confident the wording is
    # character-exact — typically where sub-paragraphs had to be reassembled.
    note: Optional[str] = None
    # A case-law-gloss chunk must name the authority it actually rests on.
    supporting_authority: Optional[str] = None

    @property
    def is_verified(self) -> bool:
        return self.verification_status is VerificationStatus.VERIFIED

    def quotable_wording(self) -> str:
        """The provision's wording, for display. THE GATE.

        Raises rather than returning a fallback. A caller that wanted a
        paraphrase can use `summary`; silently substituting one here would let an
        unverified quotation reach a user under a different label, which is the
        same defect wearing a disguise.
        """
        if not self.is_verified:
            raise UnverifiedQuotationError(
                f"{self.id} ({self.source}, {self.provision}) is "
                f"{self.verification_status.value}: its wording has not been checked "
                f"character-for-character against {self.provenance.retrieved_from}. "
                f"Verify it and set verification_status=verified before quoting it."
            )
        return self.draft_wording

    def citation(self) -> str:
        """How this provision should be cited, current edition first."""
        base = f"{self.source}, {self.provision}"
        if self.authority_basis is AuthorityBasis.CASE_LAW_GLOSS and self.supporting_authority:
            return f"{base}; as applied in {self.supporting_authority}"
        return base

    def validate(self) -> None:
        if not self.draft_wording.strip():
            raise ValueError(f"{self.id}: draft_wording is empty")
        if not self.summary.strip():
            raise ValueError(f"{self.id}: summary is empty")
        if not self.applicable_contract_types:
            raise ValueError(
                f"{self.id}: applicable_contract_types is empty. A chunk with no declared "
                f"scope would fire on every document, which is the failure v2.1 §2 fixes."
            )
        if self.role_type is RoleType.ROLE_B_VALIDATOR and not self.applicability_conditions:
            raise ValueError(
                f"{self.id}: a Role B validator must state applicability_conditions. "
                f"Firing on field presence alone is the defect v2.1 §3 names."
            )
        if self.authority_basis is AuthorityBasis.CASE_LAW_GLOSS and not self.supporting_authority:
            raise ValueError(
                f"{self.id}: authority_basis=case_law_gloss requires supporting_authority — "
                f"a citation whose real authority is a case must name the case."
            )
        if self.is_verified and not (self.verified_as_at and self.verified_by):
            raise ValueError(
                f"{self.id}: verified chunks must record verified_as_at and verified_by"
            )
        if not self.is_verified and (self.verified_as_at or self.verified_by):
            raise ValueError(
                f"{self.id}: an unverified chunk must not carry a verification stamp"
            )
        self.provenance.validate(self.id)

    # ---- serialisation -----------------------------------------------------
    # `exact_wording` is the on-disk key (the spec's name); `draft_wording` is the
    # in-memory name. The rename is deliberate: on disk it describes the intent,
    # in code it describes the trust level.

    @classmethod
    def from_dict(cls, raw: Dict[str, object]) -> "StatuteChunk":
        def req(key: str) -> object:
            if key not in raw:
                raise ValueError(f"chunk {raw.get('id', '<no id>')!r}: missing {key!r}")
            return raw[key]

        def strs(key: str) -> Tuple[str, ...]:
            value = raw.get(key) or ()
            if isinstance(value, str):
                raise ValueError(f"{raw.get('id')}: {key} must be a list, not a string")
            return tuple(str(v) for v in value)  # type: ignore[union-attr]

        prov_raw = req("provenance")
        if not isinstance(prov_raw, dict):
            raise ValueError(f"{raw.get('id')}: provenance must be an object")

        chunk = cls(
            id=str(req("id")),
            source=str(req("source")),
            provision=str(req("provision")),
            draft_wording=str(req("exact_wording")),
            summary=str(req("summary")),
            role_type=RoleType(str(req("role_type"))),
            target_fields=strs("target_fields"),
            trigger_keywords=strs("trigger_keywords"),
            verification_status=VerificationStatus(str(req("verification_status"))),
            provenance=Provenance(
                retrieved_from=str(prov_raw["retrieved_from"]),
                retrieved_at=str(prov_raw["retrieved_at"]),
                revised_edition=str(prov_raw["revised_edition"]),
                transcription=str(prov_raw.get("transcription", "machine_assisted_from_source")),
            ),
            applicable_contract_types=strs("applicable_contract_types"),
            applicability_conditions=strs("applicability_conditions"),
            authority_basis=AuthorityBasis(str(raw.get("authority_basis", "statute_text"))),
            category=str(raw.get("category", "statute")),
            legacy_citation=_opt_str(raw.get("legacy_citation")),
            verified_as_at=_opt_str(raw.get("verified_as_at")),
            verified_by=_opt_str(raw.get("verified_by")),
            note=_opt_str(raw.get("note")),
            supporting_authority=_opt_str(raw.get("supporting_authority")),
        )
        chunk.validate()
        return chunk

    def to_dict(self) -> Dict[str, object]:
        out: Dict[str, object] = {
            "id": self.id,
            "category": self.category,
            "source": self.source,
            "provision": self.provision,
            "exact_wording": self.draft_wording,
            "summary": self.summary,
            "role_type": self.role_type.value,
            "applicable_contract_types": list(self.applicable_contract_types),
            "applicability_conditions": list(self.applicability_conditions),
            "target_fields": list(self.target_fields),
            "trigger_keywords": list(self.trigger_keywords),
            "authority_basis": self.authority_basis.value,
            "verification_status": self.verification_status.value,
            "provenance": {
                "retrieved_from": self.provenance.retrieved_from,
                "retrieved_at": self.provenance.retrieved_at,
                "revised_edition": self.provenance.revised_edition,
                "transcription": self.provenance.transcription,
            },
        }
        for key, value in (
            ("legacy_citation", self.legacy_citation),
            ("supporting_authority", self.supporting_authority),
            ("verified_as_at", self.verified_as_at),
            ("verified_by", self.verified_by),
            ("note", self.note),
        ):
            if value is not None:
                out[key] = value
        return out


def _opt_str(value: object) -> Optional[str]:
    return None if value is None else str(value)


def keyword_hits(chunk: StatuteChunk, text: str) -> List[str]:
    """Which of the chunk's trigger keywords appear in a clause.

    Keyword presence is a NECESSARY-not-sufficient screen: it narrows which
    chunks are worth evaluating. `applicability_conditions` still has to be
    satisfied independently before anything fires.
    """
    lowered = text.casefold()
    return [kw for kw in chunk.trigger_keywords if kw.casefold() in lowered]


def eligible_for_contract_type(
    chunk: StatuteChunk, contract_type: Optional[str]
) -> bool:
    """The v2.1 §2 classification gate.

    An unclassified document (None) gets NO statutory overlay — not a guess, and
    not a permissive default. That is what stops Sale of Goods defaults appearing
    on an NDA.
    """
    if contract_type is None:
        return False
    if "all_commercial" in chunk.applicable_contract_types:
        return True
    return contract_type in chunk.applicable_contract_types


def select(
    chunks: Iterable[StatuteChunk],
    *,
    contract_type: Optional[str],
    role_type: Optional[RoleType] = None,
    field_name: Optional[str] = None,
    verified_only: bool = False,
) -> List[StatuteChunk]:
    """Candidate chunks for a document. Candidates only — nothing has fired yet."""
    out: List[StatuteChunk] = []
    for chunk in chunks:
        if not eligible_for_contract_type(chunk, contract_type):
            continue
        if role_type is not None and chunk.role_type is not role_type:
            continue
        if field_name is not None and field_name not in chunk.target_fields:
            continue
        if verified_only and not chunk.is_verified:
            continue
        out.append(chunk)
    return out


# The contract types the classification gate may produce. `other_unclassified`
# is present but is never eligible for anything (see `eligible_for_contract_type`
# — it is not a member of any chunk's scope), so it behaves as "no overlay".
CONTRACT_TYPES: Sequence[str] = (
    "sale_of_goods",
    "transfer_of_goods",
    "hire_of_goods",
    "hire_purchase",
    "services",
    "lease",
    "nda",
    "distribution",
    "employment",
    "other_commercial",
    "other_unclassified",
)
