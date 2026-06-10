"""Tests for sensitive personal data detection."""

from app.services.pii_filter import PII_WARNING, detect_sensitive_data


def test_detects_passport_number() -> None:
    result = detect_sensitive_data("Мой паспорт 4510 123456")

    assert result.contains_pii is True
    assert "passport" in result.categories


def test_detects_snils() -> None:
    result = detect_sensitive_data("СНИЛС 123-456-789 01")

    assert result.contains_pii is True
    assert "snils" in result.categories


def test_allows_symptoms_without_pii() -> None:
    result = detect_sensitive_data("Болит голова уже три дня")

    assert result.contains_pii is False


def test_warning_message_is_russian() -> None:
    assert "Пожалуйста, не вводите" in PII_WARNING
