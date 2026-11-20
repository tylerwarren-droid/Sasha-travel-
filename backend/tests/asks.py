"""Sasha 393 · a term ask is "<what it's about>: <the question>?" (voice.term_ask) — q() is the question, as the tests named it before."""


def q(ask: str) -> str:
    s = str(ask or "").split(": ", 1)[-1]
    return s[:1].upper() + s[1:]
