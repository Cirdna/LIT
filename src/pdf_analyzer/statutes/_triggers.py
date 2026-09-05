"""Deterministic clause triggers for the Role B modules.

Pattern matching, not inference. A statutory warning has to be explainable to
the person receiving it ("your clause says 'excludes all implied warranties',
which is what s.6 is about"), and it has to fire the same way every time. An LLM
would give neither, so the triggers are regexes over the extracted text and the
matched phrase is reported back with the flag.

The cost of this choice is stated plainly: paraphrased or unusually drafted
exclusions will be missed. A missed trigger is a silent gap, which is why
`statutes.review_clause` records what it looked at.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Tuple


def phrase(*alternatives: str) -> re.Pattern:
    """Case-insensitive match on any of `alternatives`, whitespace-tolerant."""
    parts = [a.replace(" ", r"\s+") for a in alternatives]
    return re.compile(r"(?<!\w)(?:" + "|".join(parts) + r")(?!\w)", re.IGNORECASE)


# Language that gives away an attempt to cut off liability or a remedy. Kept in
# one place because every Role B statute needs the same notion.
EXCLUSION_VERBS = phrase(
    r"exclude[ds]?",
    r"excluding",
    r"exclusion",
    r"disclaim(?:s|ed|er)?",
    r"shall\s+not\s+be\s+liable",
    r"will\s+not\s+be\s+liable",
    r"no\s+liability",
    r"not\s+liable",
    r"accepts?\s+no\s+(?:liability|responsibility)",
    r"limit(?:s|ed|ation)?\s+(?:of\s+|its\s+)?liabilit\w*",
    r"limited\s+to",
    r"shall\s+not\s+exceed",
    r"waives?",
    r"waiver",
)


@dataclass(frozen=True)
class Trigger:
    """One provision's detection rule.

    `required` groups are ANDed: every group must match somewhere in the clause.
    Within a group the alternatives are ORed. That is enough to express "an
    exclusion AND a mention of personal injury" without a parser.
    """

    key: str
    citation: str
    required: Sequence[re.Pattern]
    trigger: str  # plain-language description of what was detected
    review_required: str  # what a human must now decide
    # None = not a reasonableness question; False = no reasonableness escape;
    # True = a statutory reasonableness test applies.
    reasonableness_test_applies: Optional[bool] = None
    factors: Tuple[str, ...] = ()
    # Set where the answer turns on whether the other side deals as a consumer.
    consumer_sensitive: bool = False


def matched_phrases(text: str, patterns: Iterable[re.Pattern]) -> Optional[list]:
    """The actual phrase each pattern matched, or None if any pattern misses."""
    hits = []
    for pattern in patterns:
        found = pattern.search(text)
        if found is None:
            return None
        hits.append(found.group(0).strip())
    return hits


def first_match(text: str, triggers: Sequence[Trigger]) -> Optional[Tuple[Trigger, list]]:
    """The most specific matching trigger.

    Triggers are declared most-specific-first, and only the first is returned:
    one clause yields at most one flag per statute, so a reader is not handed
    four overlapping warnings about the same sentence. The narrower provision is
    the more useful one to raise (s.2(1), which admits no reasonableness escape,
    rather than the general s.2(2)).
    """
    for trigger in triggers:
        hits = matched_phrases(text, trigger.required)
        if hits is not None:
            return trigger, hits
    return None


def flag_id(module: str, field_name: str, citation: str, text: str) -> str:
    """Stable across runs, so re-analysing a document does not duplicate flags."""
    digest = hashlib.sha1(text.strip().lower().encode("utf-8")).hexdigest()[:8]
    return f"{module}:{citation}:{field_name}:{digest}"
