"""Sasha 212 · WHAT THE AVATAR SAYS IS NOT WHAT THE CHAT SHOWS. "€4,213.47" was slurred aloud: the spoken version has no raw
figures — money rounded and in words ("about four thousand two hundred euros"), dates and times written out ("Saturday the
twenty-first of November", "eight thirty in the morning"), every other number in words, a code's digits one by one. The
chat keeps the digits (the display text is never changed here)."""
from __future__ import annotations

import re

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
         "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_ORD = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth", "twelve": "twelfth"}
MONTHS = ("January|February|March|April|May|June|July|August|September|October|November|December|"
          "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec")
_FULL = {m[:3].lower(): m for m in "January February March April May June July August September October November December".split()}
_CUR = {"€": "euros", "£": "pounds", "$": "dollars", "EUR": "euros", "GBP": "pounds", "USD": "dollars"}


def words(n: int) -> str:
    if n < 0:
        return "minus " + words(-n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("" if n % 10 == 0 else "-" + _ONES[n % 10])
    if n < 1000:
        return _ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " and " + words(n % 100))
    for size, name in ((10 ** 9, "billion"), (10 ** 6, "million"), (1000, "thousand")):
        if n >= size:
            rest = n % size
            return words(n // size) + f" {name}" + ("" if rest == 0 else (" and " if rest < 100 else " ") + words(rest))
    return str(n)


def ordinal(n: int) -> str:
    w = words(n)
    head, _, last = w.rpartition("-") if "-" in w else w.rpartition(" ")
    sep = "-" if "-" in w else " "
    if last in _ORD:
        last = _ORD[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last += "th"
    return (head + sep if head else "") + last


def money(amount: float) -> int:
    """Rounded the way a person says it: under 100 to the nearest 5, under 1,000 to the nearest 10, else the nearest 100."""
    step = 5 if amount < 100 else 10 if amount < 1000 else 100
    return int(round(amount / step) * step)


def clock(h: int, m: int) -> str:
    if (h, m) == (12, 0):
        return "midday"
    if (h, m) == (0, 0):
        return "midnight"
    part = "in the morning" if h < 12 else "in the afternoon" if h < 18 else "in the evening"
    mins = "" if m == 0 else (" oh " + _ONES[m] if m < 10 else " " + words(m))
    return f"{words(h % 12 or 12)}{mins} {part}"


def _say_money(num: str, cur: str, before: str) -> str:
    amt = float(num.replace(",", ""))
    about = "" if re.search(r"(about|around|roughly|nearly|almost|just under|just over)\s*$", before.lower()) else "about "
    n = money(amt)
    word = _CUR.get(cur.strip().upper(), _CUR.get(cur.strip(), cur.strip().lower() if cur.strip().isalpha() else "euros"))
    word = {"euro": "euros"}.get(word, word)
    return f"{about}{words(n)} {word}" if n != 1 else f"{about}one {word.rstrip('s')}"


def speakable(text: str) -> str:
    t = text or ""
    # money: €4,213.47 · £ 4,200 · EUR 120 · 2,770.81 euros
    t = re.sub(r"(?P<cur>[€£$]|\b(?:EUR|GBP|USD)\s)\s?(?P<num>\d[\d,]*(?:\.\d+)?)(?:\s?euros?\b)?",
               lambda m: _say_money(m.group("num"), m.group("cur"), m.string[max(0, m.start() - 12):m.start()]), t)
    t = re.sub(r"(?P<num>\d[\d,]*(?:\.\d+)?)\s?(?P<cur>euros?|pounds|dollars)\b",
               lambda m: _say_money(m.group("num"), m.group("cur"), m.string[max(0, m.start() - 12):m.start()]), t)
    # times: 08:30 · 21:00 · 9pm · 9:30 a.m.
    t = re.sub(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\s?(am|pm|a\.m\.|p\.m\.)?(?=\W|$)",
               lambda m: clock((int(m.group(1)) % 12) + (12 if (m.group(3) or "").startswith("p") else 0) if m.group(3) else int(m.group(1)),
                               int(m.group(2))), t)
    t = re.sub(r"\b(1[0-2]|0?[1-9])\s?(am|pm|a\.m\.|p\.m\.)(?=\W|$)",
               lambda m: clock(int(m.group(1)) % 12 + (12 if m.group(2).startswith("p") else 0), 0), t, flags=re.I)
    # dates: 21 November · November 21 · the 21st · 2026-11-21
    t = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", lambda m: f"the {ordinal(int(m.group(3)))} of "
               f"{list(_FULL.values())[int(m.group(2)) - 1]}", t)
    t = re.sub(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({MONTHS})\b",
               lambda m: f"the {ordinal(int(m.group(1)))} of {_FULL.get(m.group(2)[:3].lower(), m.group(2))}", t)
    t = re.sub(rf"\b({MONTHS})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b",
               lambda m: f"{_FULL.get(m.group(1)[:3].lower(), m.group(1))} the {ordinal(int(m.group(2)))}", t)
    t = re.sub(r"\bthe (\d{1,2})(?:st|nd|rd|th)\b", lambda m: f"the {ordinal(int(m.group(1)))}", t)
    t = re.sub(r"\b(\d{1,2})(?:st|nd|rd|th)\b", lambda m: ordinal(int(m.group(1))), t)
    t = re.sub(r"\b(19|20)(\d{2})\b", lambda m: f"{words(int(m.group(1)))} {words(int(m.group(2))) if int(m.group(2)) >= 10 else 'oh ' + words(int(m.group(2)))}", t)
    # a number that is part of a NAME ("222 Tattoo", "Hotel 1898") is read digit by digit, as people say a name
    t = re.sub(r"\b(\d{1,4})(?=\s+(?!(?:Days?|Nights?|People|Persons?|Hotels?|Stays?|Flights?|Euros?|Pounds?|Dollars?)\b)[A-Z][a-z])",
               lambda m: " ".join(_ONES[int(d)] for d in m.group(1)), t)
    t = re.sub(r"\b((?!(?:For|About|Around|Under|Over|Only|Just)\b)[A-Z][a-z]+) (\d{3,4})\b(?!\s*(?:euros?|pounds|dollars|people|nights?|days?))",
               lambda m: m.group(1) + " " + " ".join(_ONES[int(d)] for d in m.group(2)), t)
    # a code's digits one by one: IB 6453 · IB6453 · AA123
    t = re.sub(r"\b([A-Z]{2,3})\s?(\d{2,5})\b", lambda m: m.group(1) + " " + " ".join(_ONES[int(d)] for d in m.group(2)), t)
    # everything else: in words
    t = re.sub(r"\d[\d,]*(?:\.\d+)?", lambda m: words(int(float(m.group(0).replace(",", "")))) if "." not in m.group(0)
               else words(int(round(float(m.group(0).replace(",", ""))))), t)
    t = re.sub(r"\s*/\s*(night|person|day|week)\b", r" a \1", t)
    t = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), t)   # a sentence that now starts with a word
    return re.sub(r"\s{2,}", " ", t).strip()


__all__ = ["speakable", "words", "ordinal", "money", "clock"]
