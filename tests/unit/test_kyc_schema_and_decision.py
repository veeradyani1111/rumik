from itertools import product

import pytest
from pydantic import ValidationError

from kyc.schema import CheckResult, ExtractedIdentity, KYCChecks, KYCResult
from kyc.verify import decide


def _check(status: str) -> dict[str, object]:
    return {"status": status, "confidence": 0.9, "reasons": [f"observed {status}"]}


def test_kyc_result_serializes_the_structured_contract() -> None:
    result = KYCResult(
        decision="pass",
        checks=KYCChecks(
            card_read=CheckResult(**_check("pass")),
            hologram=CheckResult(**_check("pass")),
            face_liveness=CheckResult(**_check("pass")),
            name_match=CheckResult(**_check("pass")),
            face_match=CheckResult(**_check("pass")),
        ),
        extracted=ExtractedIdentity(name="Veer Adyani", pan="ABCDE1234F", dob="2000-08-30"),
        session_id="sess_123",
        notes="Heuristic liveness only.",
    )

    payload = result.model_dump(mode="json")
    assert payload["decision"] == "pass"
    assert payload["checks"]["hologram"]["confidence"] == 0.9
    assert payload["timestamp"].endswith("Z")


def test_check_confidence_must_be_between_zero_and_one() -> None:
    with pytest.raises(ValidationError):
        CheckResult(status="pass", confidence=1.1, reasons=[])


def test_kyc_result_rejects_decision_that_contradicts_checks() -> None:
    passing = CheckResult(**_check("pass"))

    with pytest.raises(ValidationError, match="does not match checks"):
        KYCResult(
            decision="fail",
            checks=KYCChecks(
                card_read=passing,
                hologram=passing,
                face_liveness=passing,
                name_match=passing,
                face_match=passing,
            ),
            extracted=ExtractedIdentity(),
            session_id="sess_123",
        )


@pytest.mark.parametrize("statuses", list(product(("pass", "fail", "unclear"), repeat=5)))
def test_decision_truth_table_for_every_check_combination(statuses: tuple[str, ...]) -> None:
    names = ("card_read", "hologram", "face_liveness", "name_match", "face_match")
    checks = {name: _check(status) for name, status in zip(names, statuses, strict=True)}

    hard_fail = ("card_read", "name_match", "face_match")
    if any(checks[name]["status"] == "fail" for name in hard_fail):
        expected = "fail"
    elif all(check["status"] == "pass" for check in checks.values()):
        expected = "pass"
    else:
        expected = "needs_review"

    assert decide(checks) == expected
