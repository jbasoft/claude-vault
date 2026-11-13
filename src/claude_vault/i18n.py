"""Tiny locale loader. No third-party deps, no gettext compilation step."""

from __future__ import annotations

import json
import locale
import os
from pathlib import Path

LOCALE_DIR = Path(__file__).parent / "locales"
SUPPORTED = ("en", "fa", "ar", "fr", "tr", "es")
RTL = ("fa", "ar")
FALLBACK = "en"

_cache: dict[str, dict[str, str]] = {}


def detect_lang() -> str:
    """VAULT_LANG wins, then CLAUDE_VAULT_LANG, then the OS locale, then English."""
    for env in ("VAULT_LANG", "CLAUDE_VAULT_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        raw = os.environ.get(env)
        if raw:
            code = raw.split(".")[0].split("_")[0].lower()
            if code in SUPPORTED:
                return code
    try:
        sysloc = locale.getlocale()[0] or ""
    except (ValueError, TypeError):  # pragma: no cover - platform dependent
        sysloc = ""
    code = sysloc.split("_")[0].lower()
    return code if code in SUPPORTED else FALLBACK


def _load(lang: str) -> dict[str, str]:
    if lang not in _cache:
        path = LOCALE_DIR / f"{lang}.json"
        try:
            _cache[lang] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _cache[lang] = {}
    return _cache[lang]


class Translator:
    def __init__(self, lang: str | None = None) -> None:
        self.lang = lang if lang in SUPPORTED else detect_lang()
        self.rtl = self.lang in RTL

    def __call__(self, key: str, **kwargs: object) -> str:
        text = _load(self.lang).get(key) or _load(FALLBACK).get(key) or key
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError):
                return text
        return text


_default: Translator | None = None


def t(key: str, **kwargs: object) -> str:
    global _default
    if _default is None:
        _default = Translator()
    return _default(key, **kwargs)


def set_lang(lang: str | None) -> Translator:
    global _default
    _default = Translator(lang)
    return _default


def current() -> Translator:
    global _default
    if _default is None:
        _default = Translator()
    return _default
