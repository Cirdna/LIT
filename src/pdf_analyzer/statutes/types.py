"""Inputs the statute modules read.

Deliberately small and free of pipeline imports: a statute module must be
testable with a string and a dataclass, so that its legal content can be
reviewed by someone who does not want to read the extraction pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from ..schema import Location, Source


class CounterpartyStatus(str, Enum):
    """Whether the other side deals as a consumer.

    This changes the answer under UCTA (ss.6(2) vs 6(3)) and it is NOT something
    the extraction pipeline currently determines. UNKNOWN is therefore the
    honest default, and modules must widen their review question rather than
    assume business-to-business.
    """

    CONSUMER = "consumer"
    BUSINESS = "business"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ContractContext:
    """What is known about the contract as a whole.

    Every field defaults to "not known". The real pipeline does not classify
    contract type or counterparty status (see WIRING_STATUS.md), so a statute
    module must behave correctly when told nothing.
    """

    counterparty_status: CounterpartyStatus = CounterpartyStatus.UNKNOWN
    # True where the terms are the supplier's own written standard terms, which
    # is what brings UCTA s.3 into play at all.
    on_written_standard_terms: Optional[bool] = None
    # Free-form hint ("sale of goods", "hire", "services"). None = unclassified.
    contract_type_hint: Optional[str] = None


@dataclass(frozen=True)
class ClauseField:
    """One already-extracted field, as Role B sees it.

    `text` is the clause exactly as extracted. Nothing in this package rewrites
    it — a flag is an annotation, never an edit.
    """

    field_name: str  # the extracted category key, e.g. "cap_on_liability"
    text: str
    source: Optional[Source] = None
    location: Optional[Location] = None
    # Whether Stage 3 located this text on the cited page. A statutory warning
    # about a sentence that may not be in the document is worse than no warning,
    # so callers should pass grounded clauses only and modules record the fact.
    is_grounded: bool = True
    context: ContractContext = field(default_factory=ContractContext)
