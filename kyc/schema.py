from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .verify import decide


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CheckResult(StrictModel):
    status: Literal["pass", "fail", "unclear"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str]


class KYCChecks(StrictModel):
    card_read: CheckResult
    hologram: CheckResult
    face_liveness: CheckResult
    name_match: CheckResult


class ExtractedIdentity(StrictModel):
    name: str = ""
    pan: str = ""
    dob: str = ""


class KYCResult(StrictModel):
    decision: Literal["pass", "fail", "needs_review"]
    checks: KYCChecks
    extracted: ExtractedIdentity
    session_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: str = ""

    @model_validator(mode="after")
    def decision_matches_checks(self) -> "KYCResult":
        expected = decide(self.checks.model_dump())
        if self.decision != expected:
            raise ValueError(
                f"decision {self.decision!r} does not match checks; expected {expected!r}"
            )
        return self
