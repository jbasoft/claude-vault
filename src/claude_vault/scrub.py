"""Streaming output redaction.

``vault run`` injects secrets into a child process, so the child can leak them
back: ``curl -v`` echoes headers, a stack trace prints a connection string, a
verbose SDK logs its own API key. Everything the child writes is therefore
filtered on the way out.

Encoded forms are covered too, because leaks are rarely literal:
raw, URL-encoded, base64, JSON-escaped, and base64 of ``user:password``.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.parse

MIN_LEN = 4  # never redact something so short it would match everything
MASK = b"***REDACTED:%s***"


def _variants(value: str) -> list[bytes]:
    out: set[bytes] = set()

    def add(s: str | bytes) -> None:
        b = s.encode("utf-8", "surrogateescape") if isinstance(s, str) else s
        if len(b) >= MIN_LEN:
            out.add(b)

    add(value)
    add(value.strip())
    add(urllib.parse.quote(value, safe=""))
    add(urllib.parse.quote_plus(value))
    add(json.dumps(value)[1:-1])  # JSON string body, backslash-escaped
    try:
        add(base64.b64encode(value.encode("utf-8")))
        add(base64.b64encode(value.encode("utf-8")).rstrip(b"="))
    except Exception:
        pass
    return sorted(out, key=len, reverse=True)


class Scrubber:
    """Byte-stream filter. Feed chunks, get redacted chunks."""

    def __init__(self, secrets: dict[str, str]) -> None:
        self._patterns: list[tuple[bytes, bytes]] = []
        for name, value in secrets.items():
            if not value:
                continue
            mask = MASK % name.encode("ascii", "replace")
            for variant in _variants(value):
                self._patterns.append((variant, mask))
        self._patterns.sort(key=lambda p: len(p[0]), reverse=True)
        self._max = max((len(p[0]) for p in self._patterns), default=1)
        self._carry = b""

    @property
    def active(self) -> bool:
        return bool(self._patterns)

    def _apply(self, data: bytes) -> bytes:
        for needle, mask in self._patterns:
            if needle in data:
                data = data.replace(needle, mask)
        return data

    def feed(self, chunk: bytes) -> bytes:
        if not self._patterns:
            return chunk
        # Redact the whole buffer first: a match that straddles the cut point
        # must be caught before anything is released.
        buf = self._apply(self._carry + chunk)
        # Then hold back a tail, so a secret split across two chunks is still
        # caught on the next feed. Release through the last newline so that
        # output stays live rather than lagging a block behind.
        keep = self._max - 1
        cut = len(buf) - keep
        nl = buf.rfind(b"\n")
        if nl + 1 > cut:
            cut = nl + 1
        if cut <= 0:
            self._carry = buf
            return b""
        self._carry = buf[cut:]
        return buf[:cut]

    def flush(self) -> bytes:
        out = self._apply(self._carry)
        self._carry = b""
        return out


def scrub_text(text: str, secrets: dict[str, str]) -> str:
    s = Scrubber(secrets)
    return (s.feed(text.encode("utf-8", "surrogateescape")) + s.flush()).decode(
        "utf-8", "replace"
    )


_ENVLIKE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def env_name(secret_name: str) -> str:
    """NAME -> NAME, my-api.key -> MY_API_KEY."""
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", secret_name).upper()
    if not cleaned or cleaned[0].isdigit():
        cleaned = "V_" + cleaned
    return cleaned
