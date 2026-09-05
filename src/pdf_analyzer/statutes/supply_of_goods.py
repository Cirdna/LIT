"""Supply of Goods Act 1982 (2020 Rev Ed) — Singapore. ROLE A: supplies defaults.

The Sale of Goods Act only reaches contracts of sale. A great many commercial
agreements transfer or hire goods without selling them — equipment hire,
work-and-materials, supply arrangements — and this Act supplies the analogous
implied terms for those.

Which set applies turns on the kind of contract:

  * transfer of property in goods otherwise than by sale  -> the "transfer" set
  * hire (bailment) of goods                              -> the "hire" set

Nothing in the pipeline decides which, so both sets are offered and each states
its own precondition in `applies_when`. Offering both is honest; silently
picking one would be a legal characterisation this tool has no basis for.

Section numbers follow the Act's Part I (transfer) / Part II (hire) structure
and should be checked against the current Revised Edition before being relied
on. As elsewhere, `effect` is a paraphrase, not a quotation.
"""

from __future__ import annotations

from typing import Dict, Optional

from ..schema import StatutoryDefault
from ._catalogue import DefaultSpec, build_default

STATUTE = "Supply of Goods Act 1982 (2020 Rev Ed)"
MODULE = "statutes.supply_of_goods"

_TRANSFER = (
    "the contract transfers property in goods otherwise than by a sale of goods "
    "(e.g. work and materials, exchange)"
)
_HIRE = "the contract is a bailment of goods by way of hire"
_BUSINESS = "and the transferor/owner acts in the course of a business"

SPECS: Dict[str, DefaultSpec] = {
    # ---- Part I: transfer of property in goods ----------------------------
    "transfer_title": DefaultSpec(
        citation="s.3",
        effect=(
            "The transferor is taken to promise that it has the right to transfer the "
            "property in the goods."
        ),
        applies_when=_TRANSFER,
        displaced_by_categories=(),
    ),
    "transfer_correspondence_with_description": DefaultSpec(
        citation="s.4",
        effect=(
            "Where goods are transferred by description, the transferor is taken to promise "
            "that the goods will correspond with that description."
        ),
        applies_when=f"{_TRANSFER} and the transfer is by description",
        displaced_by_categories=(),
    ),
    "transfer_quality_and_fitness": DefaultSpec(
        citation="s.5",
        effect=(
            "The transferor is taken to promise that the goods are of satisfactory quality "
            "and, where a particular purpose is made known, reasonably fit for that purpose."
        ),
        applies_when=f"{_TRANSFER} {_BUSINESS}",
        displaced_by_categories=("warranty_duration",),
    ),
    "transfer_sample": DefaultSpec(
        citation="s.6",
        effect=(
            "Where goods are transferred by reference to a sample, the transferor is taken to "
            "promise that the bulk will correspond with the sample and be free from defects "
            "not apparent on reasonable examination of it."
        ),
        applies_when=f"{_TRANSFER} and the transfer is by sample",
        displaced_by_categories=(),
    ),
    # ---- Part II: hire of goods -------------------------------------------
    "hire_right_to_transfer_possession": DefaultSpec(
        citation="s.7",
        effect=(
            "The owner is taken to promise that it has the right to transfer possession of "
            "the goods for the period of the hire, and that the hirer will enjoy quiet "
            "possession for that period."
        ),
        applies_when=_HIRE,
        displaced_by_categories=(),
    ),
    "hire_correspondence_with_description": DefaultSpec(
        citation="s.8",
        effect=(
            "Where goods are hired by description, the owner is taken to promise that the "
            "goods will correspond with that description."
        ),
        applies_when=f"{_HIRE} and the hire is by description",
        displaced_by_categories=(),
    ),
    "hire_quality_and_fitness": DefaultSpec(
        citation="s.9",
        effect=(
            "The owner is taken to promise that the goods are of satisfactory quality and, "
            "where a particular purpose is made known, reasonably fit for that purpose."
        ),
        applies_when=f"{_HIRE} {_BUSINESS}",
        displaced_by_categories=("warranty_duration",),
    ),
    "hire_sample": DefaultSpec(
        citation="s.10",
        effect=(
            "Where goods are hired by reference to a sample, the owner is taken to promise "
            "that the bulk will correspond with the sample and be free from defects not "
            "apparent on reasonable examination of it."
        ),
        applies_when=f"{_HIRE} and the hire is by sample",
        displaced_by_categories=(),
    ),
}


def field_names() -> tuple:
    return tuple(SPECS)


def default_value(field_name: str) -> Optional[StatutoryDefault]:
    spec = SPECS.get(field_name)
    if spec is None:
        return None
    return build_default(field_name=field_name, statute=STATUTE, spec=spec, raised_by=MODULE)
