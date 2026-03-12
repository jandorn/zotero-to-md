from __future__ import annotations

import re
from pathlib import Path

import fitz

_SHIFTED_ASCII_OFFSET = 29
_PROTECTED_ASCII_BASE = 0xE000
_TOKEN_PATTERN = re.compile(r"\S+")
_NUMERIC_TOKEN_PATTERN = re.compile(r"^[0-9][0-9.,;:()/%+\-–]*$")
_COMMON_REPAIRED_WORDS = {
    "a",
    "abstract",
    "an",
    "and",
    "are",
    "as",
    "at",
    "author",
    "be",
    "both",
    "but",
    "by",
    "can",
    "conference",
    "corresponding",
    "demand",
    "due",
    "email",
    "energy",
    "factory",
    "fax",
    "flexibility",
    "for",
    "from",
    "gas",
    "had",
    "has",
    "have",
    "he",
    "her",
    "his",
    "in",
    "integrate",
    "into",
    "is",
    "it",
    "its",
    "key",
    "keywords",
    "large",
    "life",
    "mail",
    "may",
    "more",
    "not",
    "of",
    "on",
    "or",
    "our",
    "planning",
    "production",
    "response",
    "simulation",
    "tel",
    "that",
    "the",
    "their",
    "therefore",
    "these",
    "this",
    "those",
    "to",
    "under",
    "use",
    "variable",
    "was",
    "were",
    "which",
    "who",
    "will",
    "with",
}


def extract_pdf_text(pdf_path: Path) -> str:
    with fitz.open(pdf_path) as document:
        pages = [page.get_text("text") for page in document]
    extracted = "\n\n".join(text.strip() for text in pages if text and text.strip()).strip()
    return _repair_shifted_pdf_text(extracted)


def _repair_shifted_pdf_text(text: str) -> str:
    protected = _protect_shifted_ascii_controls(text)
    repaired = _TOKEN_PATTERN.sub(lambda match: _repair_token(match.group(0)), protected)
    return _unprotect_shifted_ascii_controls(repaired)


def _protect_shifted_ascii_controls(text: str) -> str:
    protected: list[str] = []
    for char in text:
        codepoint = ord(char)
        if char in "\n\t":
            protected.append(char)
            continue
        if 0 <= codepoint < 32:
            repaired = codepoint + _SHIFTED_ASCII_OFFSET
            if 32 <= repaired <= 126:
                protected.append(chr(_PROTECTED_ASCII_BASE + repaired))
                continue
        protected.append(char)
    return "".join(protected)


def _unprotect_shifted_ascii_controls(text: str) -> str:
    restored: list[str] = []
    for char in text:
        codepoint = ord(char)
        if _PROTECTED_ASCII_BASE <= codepoint <= _PROTECTED_ASCII_BASE + 126:
            restored.append(chr(codepoint - _PROTECTED_ASCII_BASE))
        else:
            restored.append(char)
    return "".join(restored)


def _repair_token(token: str) -> str:
    plain_token = _unprotect_shifted_ascii_controls(token)
    if _NUMERIC_TOKEN_PATTERN.fullmatch(plain_token):
        return token

    repaired_segments: list[str] = []
    index = 0

    while index < len(token):
        if _is_suspicious_shifted_char(token[index]):
            end = index
            while end < len(token) and _is_suspicious_shifted_char(token[end]):
                end += 1
            repaired_segments.append(
                _repair_token_segment(
                    token[index:end],
                    prev_char=_unprotect_shifted_ascii_controls(token[index - 1]) if index > 0 else None,
                    next_char=_unprotect_shifted_ascii_controls(token[end]) if end < len(token) else None,
                )
            )
            index = end
            continue

        repaired_segments.append(token[index])
        index += 1

    return "".join(repaired_segments)


def _repair_token_segment(segment: str, *, prev_char: str | None, next_char: str | None) -> str:
    prefix, core, suffix = _trim_segment_edges(segment, prev_char=prev_char, next_char=next_char)
    contains_protected_ascii = any(
        _PROTECTED_ASCII_BASE <= ord(char) <= _PROTECTED_ASCII_BASE + 126 for char in core
    )
    if not core or (len(core) < 2 and not contains_protected_ascii):
        return segment

    repaired = _shift_ascii_segment(core)
    if _segment_score(repaired) >= _segment_score(core) + 6:
        return prefix + repaired + suffix
    return segment


def _trim_segment_edges(segment: str, *, prev_char: str | None, next_char: str | None) -> tuple[str, str, str]:
    prefix = ""
    suffix = ""
    core = segment

    if prev_char and prev_char.islower():
        while core and ord(core[0]) < _PROTECTED_ASCII_BASE and not core[0].isalnum():
            prefix += core[0]
            core = core[1:]

    if next_char and next_char.islower():
        while core and ord(core[-1]) < _PROTECTED_ASCII_BASE and not core[-1].isalnum():
            suffix = core[-1] + suffix
            core = core[:-1]

    return prefix, core, suffix


def _is_suspicious_shifted_char(char: str) -> bool:
    codepoint = ord(char)
    if _PROTECTED_ASCII_BASE <= codepoint <= _PROTECTED_ASCII_BASE + 126:
        return True
    return 32 <= codepoint <= 126 and not char.islower()


def _shift_ascii_segment(segment: str) -> str:
    repaired: list[str] = []
    for char in segment:
        codepoint = ord(char)
        if codepoint < 128:
            shifted = codepoint + _SHIFTED_ASCII_OFFSET
            repaired.append(chr(shifted) if shifted <= 126 else char)
        else:
            repaired.append(char)
    return "".join(repaired)


def _segment_score(segment: str) -> int:
    plain_segment = _unprotect_shifted_ascii_controls(segment)
    score = 0
    words = re.findall(r"[A-Za-z][A-Za-z'-]*|[0-9]+[A-Za-z]+", plain_segment)

    score += sum(char.islower() for char in plain_segment) * 3
    score += plain_segment.count(" ") * 2
    score += sum(char.isdigit() for char in plain_segment)
    score += sum(char in ".,;:!?()/%-+@" for char in plain_segment)

    if any(char in plain_segment for char in "`_^\\{}|"):
        score -= 10
    if any(ord(char) > 126 and not (0xFB00 <= ord(char) <= 0xFB06) for char in plain_segment):
        score -= 4

    for word in words:
        lowered = word.lower()
        if lowered in _COMMON_REPAIRED_WORDS:
            score += 8
        if word.islower() and len(word) >= 3:
            score += 4
        if word.istitle() and len(word) >= 3:
            score += 4
        if word.isupper() and len(word) <= 6:
            score += 2
        if word.isupper() and len(word) > 6:
            score -= len(word)

    return score
