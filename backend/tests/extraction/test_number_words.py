"""Amounts written in words count as evidence when they say the same number (D-063)."""
from decimal import Decimal

import pytest

from app.services.extraction.extractor import _number_matches, _word_numbers


@pytest.mark.parametrize(
    ("words", "number"),
    [
        ("forty-nine thousand five hundred rupees", 49_500),
        ("one hundred and twenty thousand", 120_000),
        ("two lakh fifty thousand", 250_000),
        ("fifty thousand", 50_000),
        ("twelve", 12),
        ("three crore", 30_000_000),
    ],
)
def test_word_numbers(words: str, number: int) -> None:
    assert Decimal(number) in _word_numbers(words)


def test_words_and_digits_together() -> None:
    assert _number_matches(Decimal(49_000), "49 thousand rupees", required=True)
    assert _number_matches(Decimal(120_000), "Rs 1.2 lakh", required=True)


def test_words_that_say_another_number_do_not_match() -> None:
    assert not _number_matches(Decimal(45_900), "forty-nine thousand five hundred rupees", required=True)


def test_ordinary_words_are_not_numbers() -> None:
    assert _word_numbers("for the new finance cabin") == []
    assert not _number_matches(Decimal(5000), "a few thousand rupees", required=True)
