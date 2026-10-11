"""Shared annotation definitions and metadata; runtime checking lives in validation."""
import re
from datetime import timedelta
from typing import Annotated


class UnsetType:
    """Marks an omitted partial-update field."""


UNSET = UnsetType()
editable = object()  # Marks fields included in INSERT/UPDATE statements.


# Metadata predicates return whether an already type-checked value is valid.
def positive(value):
    return value > 0


def nonnegative(value):
    return value >= 0


def nonblank(value):
    return bool(value.strip())


def fits_bigint(value):
    return value <= 9223372036854775807


def positive_duration(value):
    return value > timedelta(0)


def email_address(value):
    # Application contact syntax, not deliverability or full RFC mailbox validation.
    return len(value) <= 256 and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value) is not None


def phone_number(value):
    # Keep phone numbers as text: leading zeroes and international prefixes matter.
    return (len(value) <= 16 and re.fullmatch(r'\+?[0-9 ()-]+', value) is not None
            and any('0' <= char <= '9' for char in value))


def name_length(value):
    return len(value) <= 256


Email = Annotated[str, email_address]
PhoneNumber = Annotated[str, phone_number]
PositiveInt = Annotated[int, positive]
NonNegativeInt = Annotated[int, nonnegative]
PositiveBigInt = Annotated[int, positive, fits_bigint]
NonBlankText = Annotated[str, nonblank]
Name = Annotated[NonBlankText, name_length]
PositiveDuration = Annotated[timedelta, positive_duration]
VALIDATION_RULES = {
    email_address: "must be an email address of at most 256 characters",
    phone_number: "must contain a digit and at most 16 characters: digits, spaces, +, ( ), or -",
    name_length: "must be at most 256 characters",
    positive: "must be positive", nonnegative: "must be non-negative",
    nonblank: "must not be blank", fits_bigint: "exceeds the BIGINT range",
    positive_duration: "must be a positive duration",
}


