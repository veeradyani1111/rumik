import pytest

from kyc.verify import match_name, normalize_dob, normalize_name, pan_holder_type, validate_pan


@pytest.mark.parametrize("pan", ["ABCDE1234F", " abcde1234f "])
def test_validate_pan_accepts_and_normalizes_valid_shape(pan: str) -> None:
    assert validate_pan(pan) is True


@pytest.mark.parametrize("pan", ["ABCD1234F", "ABCDE12345", "ABCDE-1234-F", ""])
def test_validate_pan_rejects_invalid_shape(pan: str) -> None:
    assert validate_pan(pan) is False


def test_pan_holder_type_reads_fourth_character() -> None:
    assert pan_holder_type("ABCPD1234E") == "individual"
    assert pan_holder_type("ABCCD1234E") == "company"
    assert pan_holder_type("bad") is None


def test_name_matching_ignores_honorifics_punctuation_order_and_case() -> None:
    result = match_name("Mr. Veer Adyani", "ADYANI, VEER")

    assert normalize_name("Mr. Veer Adyani") == "VEER ADYANI"
    assert result["match"] is True
    assert result["score"] == pytest.approx(1.0)


def test_name_matching_reports_a_clear_mismatch() -> None:
    result = match_name("Veer Adyani", "Asha Sharma")

    assert result["match"] is False
    assert result["score"] < 0.82


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("30/08/2000", "2000-08-30"), ("2000-08-30", "2000-08-30"), ("30-08-00", "2000-08-30")],
)
def test_normalize_dob_returns_iso_date(raw: str, expected: str) -> None:
    assert normalize_dob(raw) == expected


def test_normalize_dob_returns_none_for_impossible_date() -> None:
    assert normalize_dob("31/02/2000") is None
