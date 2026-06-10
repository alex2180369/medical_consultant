"""Detection of sensitive personal data in user messages."""

from __future__ import annotations

import re
from dataclasses import dataclass

PII_WARNING = (
    "Пожалуйста, не вводите ваши полные паспортные данные или точный адрес "
    "в чат с ИИ в целях вашей же безопасности."
)

PASSPORT_PATTERN = re.compile(
    r"\b\d{2}\s?\d{2}\s?\d{6}\b|\b\d{4}\s?\d{6}\b",
    re.IGNORECASE,
)
SNILS_PATTERN = re.compile(r"\b\d{3}-\d{3}-\d{3}\s?\d{2}\b|\b\d{11}\b")
INN_PATTERN = re.compile(r"\b\d{10}\b|\b\d{12}\b")
PHONE_PATTERN = re.compile(
    r"(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}\b"
)
EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    re.IGNORECASE,
)
FULL_NAME_PATTERN = re.compile(
    r"\b[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){2,}\b"
)
ADDRESS_PATTERN = re.compile(
    r"\b(?:ул\.?|улица|пр\.?|проспект|пер\.?|переулок|д\.?|дом|кв\.?|квартира|"
    r"г\.?|город|обл\.?|область|район|микрорайон|пос\.?|посёлок)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class PiiCheckResult:
    """Result of a personal-data scan."""

    contains_pii: bool
    categories: tuple[str, ...]


def detect_sensitive_data(text: str) -> PiiCheckResult:
    """Return whether the text likely contains sensitive personal data."""
    categories: list[str] = []

    if PASSPORT_PATTERN.search(text):
        categories.append("passport")
    if SNILS_PATTERN.search(text):
        categories.append("snils")
    if INN_PATTERN.search(text):
        categories.append("inn")
    if PHONE_PATTERN.search(text):
        categories.append("phone")
    if EMAIL_PATTERN.search(text):
        categories.append("email")
    if FULL_NAME_PATTERN.search(text):
        categories.append("full_name")
    if ADDRESS_PATTERN.search(text):
        categories.append("address")

    return PiiCheckResult(
        contains_pii=bool(categories),
        categories=tuple(categories),
    )
