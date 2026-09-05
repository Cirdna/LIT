"""Sale of Goods Act 1979 (2020 Rev Ed) — Singapore. ROLE A: supplies defaults.

Where a contract for the sale of goods says nothing, the Act still says
something. Those implied terms are what this module supplies, so that a reader
is not left believing the contract is silent on quality, title or description
when the law has already filled the gap.

Two limits are structural, not oversights:

  * Every default here presupposes a CONTRACT FOR THE SALE OF GOODS (s.2(1)).
    Nothing in the pipeline classifies contract type, so `applies_when` states
    the precondition and leaves it to a human. Applying these defaults to an
    employment agreement would be nonsense, and the tool cannot yet tell.
  * `effect` is a paraphrase. Verbatim statutory text is left unset rather than
    reconstructed from memory — see StatutoryDefault.verbatim_text.
"""

from __future__ import annotations

from typing import Dict, Optional

from ..schema import StatutoryDefault
from ._catalogue import DefaultSpec, build_default

STATUTE = "Sale of Goods Act 1979 (2020 Rev Ed)"
MODULE = "statutes.sale_of_goods"

# A sale of goods is the precondition for the whole Act.
_SALE = "the contract is one for the sale of goods (s.2(1))"
_BUSINESS_SELLER = f"{_SALE} and the seller sells in the course of a business"

# Keyed by the topic the default speaks to. These are statute topics, not
# extraction categories: the two vocabularies are related but not the same, and
# collapsing them would hide which fields the pipeline cannot actually check.
SPECS: Dict[str, DefaultSpec] = {
    "title": DefaultSpec(
        citation="s.12(1)",
        effect=(
            "The seller is taken to promise that it has the right to sell the goods. "
            "This promise cannot be excluded by any contract term (see s.6(1) UCTA)."
        ),
        applies_when=_SALE,
        # No extracted category corresponds to a title warranty, so the tool
        # cannot see whether the contract addressed it.
        displaced_by_categories=(),
    ),
    "correspondence_with_description": DefaultSpec(
        citation="s.13(1)",
        effect=(
            "Where goods are sold by description, the seller is taken to promise that "
            "the goods will correspond with that description."
        ),
        applies_when=f"{_SALE} and the sale is by description",
        displaced_by_categories=(),
    ),
    "satisfactory_quality": DefaultSpec(
        citation="s.14(2)",
        effect=(
            "The seller is taken to promise that the goods are of satisfactory quality — "
            "the standard a reasonable person would regard as satisfactory, taking account "
            "of any description, the price and the other circumstances. It does not extend "
            "to defects drawn to the buyer's attention before the contract, or which an "
            "actual examination ought to have revealed (s.14(2C))."
        ),
        applies_when=_BUSINESS_SELLER,
        displaced_by_categories=("warranty_duration",),
    ),
    "fitness_for_particular_purpose": DefaultSpec(
        citation="s.14(3)",
        effect=(
            "Where the buyer makes known a particular purpose for the goods, the seller is "
            "taken to promise that the goods are reasonably fit for that purpose, unless the "
            "circumstances show the buyer did not rely, or it was unreasonable to rely, on "
            "the seller's skill or judgement."
        ),
        applies_when=_BUSINESS_SELLER,
        displaced_by_categories=("warranty_duration",),
    ),
    "sale_by_sample": DefaultSpec(
        citation="s.15(2)",
        effect=(
            "In a sale by sample, the seller is taken to promise that the bulk will "
            "correspond with the sample in quality and that the goods will be free from any "
            "defect making their quality unsatisfactory which would not be apparent on a "
            "reasonable examination of the sample."
        ),
        applies_when=f"{_SALE} and the sale is by sample",
        displaced_by_categories=(),
    ),
    "passing_of_risk": DefaultSpec(
        citation="s.20(1)",
        effect=(
            "Risk passes with property in the goods, whether or not delivery has been made — "
            "unless the parties agree otherwise."
        ),
        applies_when=_SALE,
        displaced_by_categories=(),
    ),
    "time_of_payment": DefaultSpec(
        citation="s.10(1)",
        effect=(
            "Stipulations about the time of payment are not treated as conditions of the "
            "contract unless a different intention appears from its terms."
        ),
        applies_when=_SALE,
        # No extracted category speaks to whether time of payment was intended
        # to be of the essence. A minimum commitment or a price restriction is
        # not that, so this stays unverifiable rather than loosely matched.
        displaced_by_categories=(),
    ),
}


def field_names() -> tuple:
    """Topics this statute can supply, in a stable order."""
    return tuple(SPECS)


def default_value(field_name: str) -> Optional[StatutoryDefault]:
    """The default this Act supplies for `field_name`, or None if it supplies none."""
    spec = SPECS.get(field_name)
    if spec is None:
        return None
    return build_default(field_name=field_name, statute=STATUTE, spec=spec, raised_by=MODULE)
