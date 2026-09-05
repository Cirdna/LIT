"""Shared plumbing for the Role A modules.

The legal content lives in the statute modules; this file only turns a module's
declaration into a schema object, so that three statutes cannot drift into three
different shapes of the same idea.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from ..schema import StatutoryDefault


@dataclass(frozen=True)
class DefaultSpec:
    """One statutory default, as a statute module declares it."""

    citation: str
    effect: str
    applies_when: str
    # Extracted categories whose presence shows the contract addressed the topic.
    # Empty means: no extraction category corresponds, so displacement cannot be
    # detected automatically. That is recorded, never quietly assumed either way.
    displaced_by_categories: Tuple[str, ...] = field(default=())
    jurisdiction: str = "Singapore"


def build_default(
    *, field_name: str, statute: str, spec: DefaultSpec, raised_by: str
) -> StatutoryDefault:
    return StatutoryDefault(
        field_name=field_name,
        statute=statute,
        citation=spec.citation,
        jurisdiction=spec.jurisdiction,
        effect=spec.effect,
        verbatim_text=None,  # never reconstructed from memory
        applies_when=spec.applies_when,
        displaced_by_categories=list(spec.displaced_by_categories),
        auto_displacement_supported=bool(spec.displaced_by_categories),
        is_displaced=False,
        raised_by=raised_by,
    )
