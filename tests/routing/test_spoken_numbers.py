"""Spoken-number normalisation: STT says words, headers carry digits."""

from app.router.matcher import normalize_spoken_numbers


def test_informal_address_style():
    assert normalize_spoken_numbers("one twenty three main street") == "123 main street"


def test_digit_by_digit():
    assert normalize_spoken_numbers("one two three main street") == "123 main street"


def test_tens_and_ones():
    assert normalize_spoken_numbers("twenty three main street") == "23 main street"


def test_hundreds_with_and():
    assert normalize_spoken_numbers("two hundred and twelve king street") == "212 king street"


def test_hundred_with_informal_tail():
    assert normalize_spoken_numbers("twenty one hundred king street") == "2100 king street"


def test_teens():
    assert normalize_spoken_numbers("seventeen oak avenue") == "17 oak avenue"


def test_standalone_count():
    assert normalize_spoken_numbers("does it have four bedrooms") == "does it have 4 bedrooms"


def test_plain_text_unchanged():
    assert normalize_spoken_numbers("is the property still available") == "is the property still available"


def test_digits_already_present_unchanged():
    assert normalize_spoken_numbers("123 main street") == "123 main street"


def test_mixed_sentence():
    assert normalize_spoken_numbers("hi i'm calling about the house on one twenty three main street") == \
        "hi i'm calling about the house on 123 main street"


def test_empty():
    assert normalize_spoken_numbers("") == ""
