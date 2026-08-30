from __future__ import annotations

import re
from datetime import datetime
from difflib import SequenceMatcher
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


def match_name(card_name: str, spoken_name: str, threshold: float = 0.82) -> dict[str, bool | float]:
    card_tokens = sorted(set(normalize_name(card_name).split()))
    spoken_tokens = sorted(set(normalize_name(spoken_name).split()))
    if not card_tokens or not spoken_tokens:
        score = 0.0
    else:
        score = SequenceMatcher(None, " ".join(card_tokens), " ".join(spoken_tokens)).ratio()
    return {"match": score >= threshold, "score": round(score, 4)}


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
    if statuses.get("card_read") == "fail" or statuses.get("name_match") == "fail":
        return "fail"
    required = {"card_read", "hologram", "face_liveness", "name_match"}
    if required.issubset(statuses) and all(statuses[name] == "pass" for name in required):
        return "pass"
    return "needs_review"
