"""Turn a requester's deadline phrase ("by Friday", "within two weeks") into a date.

Pure code with no clock: the caller passes the day the request was sent, in the organization's
local time. Only clear, common phrases are understood. Anything else returns None, and the
priority step then ignores the deadline instead of guessing (never invent values).
"""
import calendar
import re
from datetime import date, timedelta

_WEEKDAYS = {name.lower(): index for index, name in enumerate(calendar.day_name)}
_WEEKDAYS.update({name.lower(): index for index, name in enumerate(calendar.day_abbr)})
_MONTHS = {name.lower(): index for index, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.lower(): index for index, name in enumerate(calendar.month_abbr) if name})
_MONTHS["sept"] = 9
_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
# Words for "as soon as possible": the deadline is the day the request was sent.
_NOW_WORDS = re.compile(r"\b(asap|immediately|right now|now|today|tonight)\b")
_LEADING = re.compile(r"^(?:needed |required |due )?(?:by|before|on|until|latest by|no later than)\s+")

_WEEKDAY = "|".join(sorted(_WEEKDAYS, key=len, reverse=True))
_MONTH = "|".join(sorted(_MONTHS, key=len, reverse=True))
_COUNT = r"(\d+|" + "|".join(_NUMBER_WORDS) + r")"
_WITHIN = re.compile(rf"\b(?:within|in)\s+(?:the next\s+)?{_COUNT}\s+(hour|day|week)s?\b")
_NEXT_WEEKDAY = re.compile(rf"\bnext\s+({_WEEKDAY})\b")
_WEEKDAY_ONLY = re.compile(rf"\b({_WEEKDAY})\b")
_DAY_MONTH = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH})\b")
_MONTH_DAY = re.compile(rf"\b({_MONTH})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b")
_DAY_OF_MONTH = re.compile(r"\bthe\s+(\d{1,2})(?:st|nd|rd|th)\b")


def _count(word: str) -> int:
    return int(word) if word.isdigit() else _NUMBER_WORDS[word]


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def resolve_deadline(phrase: str | None, sent_on: date) -> date | None:
    """The date a deadline phrase points to, or None when it is not clear.

    A weekday means the nearest such day on or after sent_on ("next Monday": strictly after).
    A date that has already passed this year stays in the past, so the request shows as
    overdue rather than silently moving to next year.
    """
    if not phrase or not phrase.strip():
        return None
    text = " ".join(phrase.lower().replace(",", " ").split())
    text = _LEADING.sub("", text)

    if "tomorrow" in text:
        return sent_on + timedelta(days=1)
    if _NOW_WORDS.search(text) or re.search(r"\bin an? hour\b", text):
        return sent_on
    if match := _WITHIN.search(text):
        amount, unit = _count(match.group(1)), match.group(2)
        if unit == "hour":
            return sent_on + timedelta(days=amount // 24)  # whole days only
        return sent_on + timedelta(days=amount * (7 if unit == "week" else 1))
    if re.search(r"\bend of (?:the )?week\b", text):
        return sent_on + timedelta(days=(4 - sent_on.weekday()) % 7)  # Friday
    if re.search(r"\bend of (?:the )?month\b", text):
        last_day = calendar.monthrange(sent_on.year, sent_on.month)[1]
        return sent_on.replace(day=last_day)
    if match := _NEXT_WEEKDAY.search(text):
        ahead = (_WEEKDAYS[match.group(1)] - sent_on.weekday()) % 7 or 7
        return sent_on + timedelta(days=ahead)
    if match := _DAY_MONTH.search(text):
        return _safe_date(sent_on.year, _MONTHS[match.group(2)], int(match.group(1)))
    if match := _MONTH_DAY.search(text):
        return _safe_date(sent_on.year, _MONTHS[match.group(1)], int(match.group(2)))
    if match := _DAY_OF_MONTH.search(text):
        day = int(match.group(1))
        this_month = _safe_date(sent_on.year, sent_on.month, day)
        if this_month is None:
            return None  # "the 31st" in a 30-day month: unclear, do not guess
        if this_month >= sent_on:
            return this_month
        year, month = (sent_on.year + 1, 1) if sent_on.month == 12 else (sent_on.year, sent_on.month + 1)
        return _safe_date(year, month, day)
    if match := _WEEKDAY_ONLY.search(text):
        return sent_on + timedelta(days=(_WEEKDAYS[match.group(1)] - sent_on.weekday()) % 7)
    return None
