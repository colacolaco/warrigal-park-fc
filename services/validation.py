"""Validation helpers shared by the service layer."""

from __future__ import annotations

import re
from datetime import date, datetime

AGE_OF_MAJORITY = 18

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


class ValidationError(ValueError):
    """Raised when user-supplied data fails a field-level rule."""


class BusinessRuleError(ValueError):
    """Raised when a request violates a club business rule."""


def parse_date(value: object, field: str = "date") -> date:
    """Accept an ISO date, a :class:`date`, or one of the common AU formats."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        raise ValidationError(f"{field} is required")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValidationError(
        f"{field} must be a date such as 2014-03-08 (got {text!r})"
    )


def require_text(value: object, field: str, max_length: int = 80) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValidationError(f"{field} is required")
    if len(text) > max_length:
        raise ValidationError(f"{field} must be at most {max_length} characters")
    return text


def optional_email(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if not _EMAIL_RE.match(text):
        raise ValidationError(f"email address {text!r} is not valid")
    return text


def optional_phone(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    if len(digits) < 8:
        raise ValidationError("phone number must contain at least 8 digits")
    return text


def parse_gender(value: object) -> str:
    text = str(value or "U").strip().upper()[:1] or "U"
    if text not in {"F", "M", "U"}:
        raise ValidationError("gender must be F, M or U")
    return text


def calculate_age(date_of_birth: date, on: date | None = None) -> int:
    """Completed years of age on a given date."""
    on = on or date.today()
    return (
        on.year
        - date_of_birth.year
        - ((on.month, on.day) < (date_of_birth.month, date_of_birth.day))
    )


def is_minor(date_of_birth: date, on: date | None = None) -> bool:
    """The single definition of 'under 18' used by the whole application.

    The club decided (Confluence decision record D-004) that a registration is
    judged by the player's age *on the day the registration is completed*, so
    this function is always called with the completion date rather than
    ``date.today()`` when a registration is being finalised.
    """
    return calculate_age(date_of_birth, on) < AGE_OF_MAJORITY


def age_group_for(date_of_birth: date, on: date | None = None) -> str:
    """Suggest a junior age group from the player's age.

    Under 6 to Under 18, then ``Seniors``.  This is only a suggestion used to
    pre-fill the registration form; the registrar can override it.
    """
    age = calculate_age(date_of_birth, on)
    if age >= AGE_OF_MAJORITY:
        return "Seniors"
    return f"U{max(age, 6)}"
