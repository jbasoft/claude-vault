#!/usr/bin/env python3
"""claude-vault PreToolUse guard for Claude Code.

A SKILL.md tells the model what to do. A hook makes it true. This script runs
before every Bash / Read / Grep / Glob tool call and blocks the handful of
commands that would move a secret *value* into the conversation:

  * ``vault get`` and ``vault env --unsafe-stdout``
  * reading the vault's key or encrypted blob
  * echo / printenv / env of a variable that holds an injected secret
  * reading a .env file that claude-vault wrote

Exit codes follow the Claude Code hook contract:
  0  allow
  2  block, and show stderr to the model so it can correct itself

Anything unexpected exits 0. A guard that breaks a workflow gets uninstalled,
and an uninstalled guard protects nothing.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ALLOW = 0
BLOCK = 2


# --------------------------------------------------------------------------- vault info


def vault_home() -> Path:
    env = os.environ.get("VAULT_HOME") or os.environ.get("CLAUDE_VAULT_HOME")
    if env:
        return Path(env).expanduser()
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "claude-vault"
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg) / "claude-vault") if xdg else (Path.home() / ".claude-vault")


def secret_env_names() -> set[str]:
    """Env var names derived from stored secret names. Names are not secret."""
    out: set[str] = set()
    try:
        data = json.loads((vault_home() / "index.json").read_text(encoding="utf-8"))
    except Exception:
        return out
    for names in (data.get("profiles") or {}).values():
        for name in names:
            cleaned = re.sub(r"[^A-Za-z0-9_]", "_", name).upper()
            if cleaned:
                out.add(cleaned)
            out.add(name)
    return out


PROTECTED_FILES = ("master.key", "secrets.enc")


# --------------------------------------------------------------------------- rules


REVEAL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\bvault\b[^|;&\n]*\bget\b", re.IGNORECASE),
        ("`vault get` prints a secret value into the transcript. Use "
         "`vault run <NAME> -- <your command>` instead, which injects it as an "
         "environment variable and scrubs it from the output."),
    ),
    (
        re.compile(r"\bvault\b[^|;&\n]*--unsafe-stdout", re.IGNORECASE),
        ("`vault env --unsafe-stdout` prints secret values. Write them to a file "
         "with `vault env <NAME> --to .env.local`, or avoid the file entirely "
         "with `vault run`."),
    ),
    (
        re.compile(r"\bvault\b[^|;&\n]*--no-scrub", re.IGNORECASE),
        ("`--no-scrub` lets the child process leak secrets into the transcript. "
         "Run it without that flag."),
    ),
]

READ_TOOLS = {"Read", "NotebookRead"}
SEARCH_TOOLS = {"Grep", "Glob"}

FILE_READERS = (
    r"cat|type|more|less|head|tail|strings|xxd|od|base64|nl|bat|Get-Content|gc|"
    r"Select-String|rg|grep|awk|sed|cp|copy|Copy-Item|scp|curl|iconv"
)


def check_bash(command: str) -> str | None:
    for pattern, message in REVEAL_PATTERNS:
        if pattern.search(command):
            return message

    home = str(vault_home())
    targets = "|".join(re.escape(x) for x in (*PROTECTED_FILES, home))
    if re.search(rf"({FILE_READERS})\b[^|;&\n]*({targets})", command, re.IGNORECASE):
        return (
            f"That would read the vault's own key material in {home}. The values "
            "there are deliberately out of reach. Use `vault list` to see the "
            "names, and `vault run` to use a secret."
        )

    names = secret_env_names()
    if names:
        alts = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
        # echo $SECRET / echo %SECRET% / Write-Host $env:SECRET
        if re.search(rf"\b(echo|print|printf|Write-Host|Write-Output)\b[^|;&\n]*"
                     rf"(\$\{{?(env:)?({alts}))", command, re.IGNORECASE):
            return ("That would print a secret value into the transcript. The value is "
                    "already in the environment of the process started by `vault run` "
                    "-- pass the variable to your program instead of echoing it.")
        if re.search(rf"%({alts})%", command):
            return ("That would print a secret value into the transcript. Pass the "
                    "variable to your program instead of echoing it.")

    if re.search(r"\b(printenv|env)\b\s*(\||$|;|&)", command) and os.environ.get(
        "VAULT_INJECTED"
    ):
        return ("Dumping the whole environment would include injected secrets. Name the "
                "specific variable your program needs instead.")

    if re.search(r"\b(cat|type|Get-Content|less|more|head|tail)\b[^|;&\n]*"
                 r"\.env(\.|\b)", command, re.IGNORECASE):
        return ("`.env` files written by claude-vault hold real secret values. Read the "
                "names with `vault list` and keep the values out of the conversation.")

    return None


def check_path(path: str) -> str | None:
    if not path:
        return None
    try:
        resolved = Path(path).expanduser()
    except Exception:
        return None
    text = str(resolved)
    home = str(vault_home())
    if any(text.endswith(f) for f in PROTECTED_FILES) or (
        text.startswith(home) and any(f in text for f in PROTECTED_FILES)
    ):
        return (f"{Path(path).name} is the vault's key material. Secret values are not "
                "readable by design -- use `vault list` for names and `vault run` to "
                "use a secret.")
    if re.search(r"(^|[/\\])\.env(\.[\w.-]+)?$", text):
        return ("`.env` files hold real secret values, which would land in the "
                "transcript. Use `vault list` for the names; the values stay out of "
                "the conversation.")
    return None


# --------------------------------------------------------------------------- main


def main() -> int:
    if os.environ.get("VAULT_GUARD_DISABLE") == "1":
        return ALLOW
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return ALLOW

    tool = payload.get("tool_name") or payload.get("tool") or ""
    data = payload.get("tool_input") or payload.get("input") or {}
    if not isinstance(data, dict):
        return ALLOW

    reason = None
    if tool == "Bash":
        reason = check_bash(str(data.get("command", "")))
    elif tool in READ_TOOLS:
        reason = check_path(str(data.get("file_path") or data.get("path") or ""))
    elif tool in SEARCH_TOOLS:
        reason = check_path(str(data.get("path") or ""))

    if reason:
        print(f"[claude-vault] Blocked.\n{reason}", file=sys.stderr)
        return BLOCK
    return ALLOW


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # never break the user's session
        sys.exit(ALLOW)
