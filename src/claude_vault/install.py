"""Install the Claude Code integration: skill, guard hook, permission rules.

Settings are *merged*, never overwritten -- people have their own hooks.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from .i18n import current
from .store import vault_home

PKG = Path(__file__).parent

DENY_RULES = [
    "Bash(vault get:*)",
    "Bash(vault --* get:*)",
]

HOOK_MATCHER = "Bash|Read|Grep|Glob"


def _claude_dir(args) -> Path:
    if args.scope == "project":
        base = Path(args.project).expanduser() if args.project else Path.cwd()
        return base / ".claude"
    return Path.home() / ".claude"


def _merge_settings(path: Path, hook_cmd: str, force: bool) -> list[str]:
    changes: list[str] = []
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            backup = path.with_suffix(".json.bak")
            shutil.copy2(path, backup)
            changes.append(f"unparseable settings backed up to {backup}")
            data = {}
    if not isinstance(data, dict):
        data = {}

    perms = data.setdefault("permissions", {})
    deny = perms.setdefault("deny", [])
    if isinstance(deny, list):
        for rule in DENY_RULES:
            if rule not in deny:
                deny.append(rule)
                changes.append(f"deny rule: {rule}")

    hooks = data.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])
    if isinstance(pre, list):
        already = any(
            "vault_guard" in json.dumps(block) for block in pre if isinstance(block, dict)
        )
        if already and not force:
            changes.append("guard hook already registered")
        else:
            pre = [b for b in pre if "vault_guard" not in json.dumps(b)]
            pre.append({
                "matcher": HOOK_MATCHER,
                "hooks": [{"type": "command", "command": hook_cmd}],
            })
            hooks["PreToolUse"] = pre
            changes.append(f"PreToolUse hook on {HOOK_MATCHER}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return changes


def install(args) -> int:
    t = current()
    claude = _claude_dir(args)
    skill_dir = claude / "skills" / "vault"
    hook_dir = claude / "hooks"
    skill_dir.mkdir(parents=True, exist_ok=True)
    hook_dir.mkdir(parents=True, exist_ok=True)

    skill_src = PKG / "skill" / "SKILL.md"
    skill_dst = skill_dir / "SKILL.md"
    if skill_dst.exists() and not args.force:
        print("  = " + t("install.skill_exists", path=str(skill_dst)))
    else:
        shutil.copy2(skill_src, skill_dst)
        print("  + " + t("install.skill", path=str(skill_dst)))

    hook_dst = hook_dir / "vault_guard.py"
    shutil.copy2(PKG / "hooks" / "vault_guard.py", hook_dst)
    try:
        hook_dst.chmod(0o755)
    except OSError:
        pass
    print("  + " + t("install.hook", path=str(hook_dst)))

    python = Path(sys.executable).name or "python3"
    hook_cmd = f'{python} "{hook_dst}"'
    settings = claude / "settings.json"
    for change in _merge_settings(settings, hook_cmd, args.force):
        print("  + " + change)
    print("  + " + t("install.settings", path=str(settings)))

    print()
    print(t("install.done", vault=str(vault_home())))
    print(t("install.next"))
    return 0
