from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, Mapping


PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
HONORIFICS = {"MR", "MRS", "MS", "MISS", "DR", "SHRI", "SMT"}
HOLDER_TYPES = {
    "P": "individual",
    "C": "company",
    "H": "hindu_undivided_family",
    "F": "firm",
    "A": "association_of_persons",
    "T": "trust",
    "B": "body_of_individuals",
    "L": "local_authority",
    "J": "artificial_juridical_person",
    "G": "government",
}


def _normalize_pan(pan: str) -> str:
    return pan.strip().upper()


def validate_pan(pan: str) -> bool:
    return PAN_PATTERN.fullmatch(_normalize_pan(pan)) is not None


def pan_holder_type(pan: str) -> str | None:
    normalized = _normalize_pan(pan)
    if not validate_pan(normalized):
        return None
    return HOLDER_TYPES.get(normalized[3])


def normalize_name(name: str) -> str:
    tokens = re.sub(r"[^A-Z0-9\s]", " ", name.upper()).split()
    return " ".join(token for token in tokens if token not in HONORIFICS)


def match_card_name(card_name: str, registered_name: str) -> dict[str, bool | float]:
    """Compare card-read and entered names; the live browser flow uses JS helpers."""
    card_tokens = sorted(set(normalize_name(card_name).split()))
    registered_tokens = sorted(set(normalize_name(registered_name).split()))
    matched = bool(card_tokens) and card_tokens == registered_tokens
    return {"match": matched, "score": 1.0 if matched else 0.0}


def normalize_dob(value: str) -> str | None:
    for date_format in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(value.strip(), date_format).date().isoformat()
        except ValueError:
            continue
    return None


CheckStatus = Literal["pass", "fail", "unclear"]


def decide(checks: Mapping[str, Mapping[str, object]]) -> Literal["pass", "fail", "needs_review"]:
    statuses = {name: check.get("status") for name, check in checks.items()}
    # A confident failure on identity, the claim match, or the face-on-card match
    # is a hard reject. Heuristic checks stay "unclear" when not confident, which
    # routes to human review rather than a wrongful rejection.
    hard_fail = ("card_read", "name_match", "face_match")
    if any(statuses.get(name) == "fail" for name in hard_fail):
        return "fail"
    required = {"card_read", "hologram", "face_liveness", "name_match", "face_match"}
    if required.issubset(statuses) and all(statuses[name] == "pass" for name in required):
        return "pass"
    return "needs_review"
