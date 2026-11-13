"""claude-vault command line interface."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from . import __version__
from .i18n import SUPPORTED, current, set_lang
from .prompt import PromptCancelled, PromptError, ask, gui_available
from .scrub import Scrubber, env_name
from .store import Vault, VaultError

PLACEHOLDER = re.compile(r"\$\{VAULT:([A-Za-z0-9_.\-]+)\}")


# --------------------------------------------------------------------------- util


def err(msg: str) -> None:
    print(f"vault: {msg}", file=sys.stderr)


def agent_context() -> str | None:
    """Return the name of the agent runtime we appear to be running inside."""
    if os.environ.get("VAULT_ALLOW_REVEAL") == "1":
        return None
    for env, label in (
        ("CLAUDECODE", "Claude Code"),
        ("CLAUDE_CODE_ENTRYPOINT", "Claude Code"),
        ("CURSOR_TRACE_ID", "Cursor"),
        ("AIDER_MODEL", "Aider"),
    ):
        if os.environ.get(env):
            return label
    return None


def open_vault(args) -> Vault:
    return Vault(
        home=Path(args.path).expanduser() if getattr(args, "path", None) else None,
        profile=getattr(args, "profile", None),
        backend=getattr(args, "backend", None),
    )


def parse_mapping(spec: str) -> tuple[str, str]:
    """``NAME`` or ``NAME:ENV_VAR`` or ``NAME=ENV_VAR``."""
    for sep in (":", "="):
        if sep in spec:
            name, var = spec.split(sep, 1)
            return name.strip(), var.strip()
    return spec.strip(), env_name(spec.strip())


# --------------------------------------------------------------------------- commands


def cmd_init(args) -> int:
    t = current()
    v = open_vault(args)
    v.save_config(backend=args.backend or v.backend, lang=args.lang)
    print(t("init.done", path=str(v.home), backend=v.backend))
    if v.backend == "file":
        print(t("init.file_backend"))
    return 0


def cmd_set(args) -> int:
    t = current()
    v = open_vault(args)
    if v.exists(args.name) and not (args.force or args.update):
        print(t("set.exists", name=args.name))
        return 0
    try:
        value, username = ask(
            args.name,
            want_username=args.with_username,
            note=args.note or "",
            from_stdin=args.stdin,
            force_tty=args.tty,
        )
    except PromptCancelled as exc:
        err(str(exc))
        return 130
    except PromptError as exc:
        err(str(exc))
        return 2
    v.set(args.name, value, kind=args.kind, note=args.note or "",
          username=username or (args.username or ""))
    del value
    print(t("set.saved", name=args.name, backend=v.backend))
    return 0


def cmd_need(args) -> int:
    """Ensure every named secret exists, prompting for the missing ones.

    This is the command an agent is meant to call. It prints names only.
    """
    t = current()
    v = open_vault(args)
    missing = [n for n in args.names if not v.exists(n)]
    if not missing:
        print(t("need.ok", names=", ".join(args.names)))
        return 0
    if args.check:
        print(t("need.missing", names=", ".join(missing)))
        return 1
    print(t("need.prompting", names=", ".join(missing)))
    for name in missing:
        try:
            value, username = ask(name, want_username=args.with_username,
                                  note=args.note or "", force_tty=args.tty)
        except PromptCancelled as exc:
            err(str(exc))
            return 130
        except PromptError as exc:
            err(str(exc))
            return 2
        v.set(name, value, kind=args.kind, note=args.note or "", username=username)
        del value
        print(t("set.saved", name=name, backend=v.backend))
    return 0


def cmd_list(args) -> int:
    t = current()
    v = open_vault(args)
    entries = v.list()
    if args.json:
        print(json.dumps([e.public() for e in entries], indent=2, ensure_ascii=False))
        return 0
    if not entries:
        print(t("list.empty", profile=v.profile))
        return 0
    width = max(len(e.name) for e in entries)
    print(t("list.header", profile=v.profile, count=len(entries), backend=v.backend))
    for e in entries:
        bits = [e.name.ljust(width), e.kind]
        if e.username:
            bits.append(f"({e.username})")
        if e.note:
            bits.append(f"- {e.note}")
        print("  " + "  ".join(bits))
    return 0


def cmd_has(args) -> int:
    v = open_vault(args)
    ok = v.exists(args.name)
    if not args.quiet:
        print("yes" if ok else "no")
    return 0 if ok else 1


def cmd_get(args) -> int:
    t = current()
    agent = agent_context()
    if agent and not args.reveal:
        err(t("get.blocked_agent", agent=agent))
        return 3
    if not args.reveal:
        err(t("get.needs_reveal"))
        return 3
    v = open_vault(args)
    try:
        sys.stdout.write(v.get(args.name) + ("" if args.no_newline else "\n"))
    except VaultError as exc:
        err(str(exc))
        return 1
    return 0


def cmd_rm(args) -> int:
    t = current()
    v = open_vault(args)
    if not v.exists(args.name):
        err(t("rm.missing", name=args.name))
        return 1
    v.delete(args.name)
    print(t("rm.done", name=args.name))
    return 0


def cmd_rename(args) -> int:
    t = current()
    v = open_vault(args)
    try:
        v.rename(args.old, args.new)
    except VaultError as exc:
        err(str(exc))
        return 1
    print(t("rename.done", old=args.old, new=args.new))
    return 0


def _collect(v: Vault, specs: list[str], use_all: bool) -> dict[str, tuple[str, str]]:
    """-> {secret_name: (env_var, value)}"""
    t = current()
    out: dict[str, tuple[str, str]] = {}
    if use_all:
        specs = [e.name for e in v.list()] + list(specs)
    for spec in specs:
        name, var = parse_mapping(spec)
        if not v.exists(name):
            raise VaultError(t("run.missing", name=name))
        out[name] = (var, v.get(name))
    return out


def cmd_run(args) -> int:
    t = current()
    if not args.command:
        err(t("run.no_command"))
        return 2
    v = open_vault(args)
    try:
        wanted = _collect(v, args.names, args.all)
    except VaultError as exc:
        err(str(exc))
        return 1

    env = os.environ.copy()
    for var, value in wanted.values():
        env[var] = value
    env["VAULT_INJECTED"] = ",".join(sorted(var for var, _ in wanted.values()))

    secrets = {name: value for name, (_, value) in wanted.items()}
    scrubber = Scrubber({} if args.no_scrub else secrets)

    cmd = list(args.command)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        err(t("run.no_command"))
        return 2
    if shutil.which(cmd[0]) is None and not Path(cmd[0]).exists():
        err(t("run.not_found", cmd=cmd[0]))
        return 127

    try:
        proc = subprocess.Popen(
            cmd, env=env,
            stdout=subprocess.PIPE if scrubber.active else None,
            stderr=subprocess.PIPE if scrubber.active else None,
        )
    except OSError as exc:
        err(f"{cmd[0]}: {exc}")
        return 126

    if not scrubber.active:
        return proc.wait()

    out_scrub, err_scrub = Scrubber(secrets), Scrubber(secrets)

    def pump(src, dst, filt: Scrubber) -> None:
        try:
            while True:
                chunk = src.read(4096)
                if not chunk:
                    break
                data = filt.feed(chunk)
                if data:
                    dst.write(data)
                    dst.flush()
            tail = filt.flush()
            if tail:
                dst.write(tail)
                dst.flush()
        except (BrokenPipeError, ValueError):
            pass

    threads = [
        threading.Thread(target=pump, args=(proc.stdout, sys.stdout.buffer, out_scrub),
                         daemon=True),
        threading.Thread(target=pump, args=(proc.stderr, sys.stderr.buffer, err_scrub),
                         daemon=True),
    ]
    for th in threads:
        th.start()
    code = proc.wait()
    for th in threads:
        th.join(timeout=5)
    return code


def cmd_env(args) -> int:
    t = current()
    v = open_vault(args)
    try:
        wanted = _collect(v, args.names, args.all)
    except VaultError as exc:
        err(str(exc))
        return 1

    lines = []
    for var, value in sorted(wanted.values()):
        if args.format == "export":
            lines.append(f"export {var}={_shell_quote(value)}")
        elif args.format == "powershell":
            lines.append(f"$env:{var} = '{value.replace(chr(39), chr(39) * 2)}'")
        else:
            lines.append(f"{var}={value}")
    body = "\n".join(lines) + "\n"

    if args.to:
        path = Path(args.to).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
        print(t("env.written", path=str(path), count=len(wanted)))
        _warn_gitignore(path)
        return 0

    if agent_context() and not args.unsafe_stdout:
        err(t("env.blocked_agent", agent=agent_context()))
        return 3
    if not args.unsafe_stdout:
        err(t("env.needs_flag"))
        return 3
    sys.stdout.write(body)
    return 0


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _warn_gitignore(path: Path) -> None:
    t = current()
    for parent in [path.parent, *path.parent.parents]:
        if (parent / ".git").exists():
            gi = parent / ".gitignore"
            text = gi.read_text(encoding="utf-8", errors="replace") if gi.exists() else ""
            rel = path.name
            if rel not in text:
                err(t("env.gitignore", name=rel, path=str(gi)))
            return


def cmd_template(args) -> int:
    """Render ${VAULT:NAME} placeholders in a file. Lets config files stay in git."""
    t = current()
    v = open_vault(args)
    src = Path(args.input).expanduser()
    if not src.exists():
        err(t("template.no_input", path=str(src)))
        return 1
    text = src.read_text(encoding="utf-8")
    names = sorted(set(PLACEHOLDER.findall(text)))
    if not names:
        err(t("template.no_placeholders", path=str(src)))
        return 1
    missing = [n for n in names if not v.exists(n)]
    if missing:
        err(t("run.missing", name=", ".join(missing)))
        return 1
    rendered = PLACEHOLDER.sub(lambda m: v.get(m.group(1)), text)
    dst = Path(args.output).expanduser()
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(rendered, encoding="utf-8")
    try:
        dst.chmod(0o600)
    except OSError:
        pass
    print(t("template.done", count=len(names), path=str(dst),
            names=", ".join(names)))
    _warn_gitignore(dst)
    return 0


def cmd_doctor(args) -> int:
    t = current()
    v = open_vault(args)
    rows: list[tuple[str, str]] = [
        ("version", __version__),
        ("python", sys.version.split()[0]),
        ("platform", sys.platform),
        ("vault path", str(v.home)),
        ("backend", v.backend),
        ("profile", v.profile),
        ("profiles", ", ".join(v.profiles())),
        ("secrets", str(len(v.list()))),
        ("language", current().lang),
        ("gui dialog", "available" if gui_available() else "unavailable (TTY fallback)"),
        ("tty", "yes" if sys.stdin.isatty() else "no"),
        ("agent detected", agent_context() or "no"),
    ]
    try:
        import keyring

        rows.append(("keyring backend", keyring.get_keyring().__class__.__name__))
    except Exception:
        rows.append(("keyring backend", "not installed"))

    width = max(len(k) for k, _ in rows)
    print(t("doctor.header"))
    for key, value in rows:
        print(f"  {key.ljust(width)}  {value}")

    problems = []
    if v.backend == "file" and not v.keyfile_path.exists() and v.list():
        problems.append(t("doctor.no_key"))
    if v.backend == "file" and sys.platform != "win32" and v.keyfile_path.exists():
        mode = oct(v.keyfile_path.stat().st_mode & 0o777)
        if mode != "0o600":
            problems.append(t("doctor.key_perms", mode=mode))
    hook = Path.home() / ".claude" / "hooks" / "vault_guard.py"
    if not hook.exists():
        problems.append(t("doctor.no_hook"))
    if problems:
        print()
        for p in problems:
            print("  ! " + p)
    else:
        print("\n  " + t("doctor.ok"))
    return 0


def cmd_install_claude(args) -> int:
    from .install import install

    return install(args)


def cmd_lang(args) -> int:
    t = current()
    if args.code:
        v = open_vault(args)
        v.save_config(lang=args.code)
        set_lang(args.code)
        print(current()("lang.set", code=args.code))
    else:
        print(t("lang.current", code=t.lang))
        print("  " + "  ".join(SUPPORTED))
    return 0


# --------------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="vault",
        description="Secrets for AI coding agents: the agent knows the name, "
                    "never the value.",
    )
    p.add_argument("--version", action="version", version=f"claude-vault {__version__}")
    p.add_argument("--path", help="vault directory (default: $VAULT_HOME)")
    p.add_argument("--profile", help="profile name (default: $VAULT_PROFILE or 'default')")
    p.add_argument("--backend", choices=("keyring", "file"), help="storage backend")
    p.add_argument("--lang", choices=SUPPORTED, help="interface language")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create the vault directory and config")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("set", help="store a secret via a dialog (value never printed)")
    s.add_argument("name")
    s.add_argument("--kind", default="secret",
                   choices=("secret", "password", "token", "apikey", "sshkey"))
    s.add_argument("--note", help="hint shown in the dialog and in 'vault list'")
    s.add_argument("--username", help="associated username, stored in the index")
    s.add_argument("--with-username", action="store_true",
                   help="also ask for a username in the dialog")
    s.add_argument("--stdin", action="store_true", help="read the value from stdin (CI)")
    s.add_argument("--tty", action="store_true", help="force the terminal prompt")
    s.add_argument("--force", action="store_true", help="overwrite without asking")
    s.add_argument("--update", action="store_true", help="alias for --force")
    s.set_defaults(func=cmd_set)

    s = sub.add_parser("need", help="ensure secrets exist, prompting for missing ones")
    s.add_argument("names", nargs="+")
    s.add_argument("--check", action="store_true", help="report only, never prompt")
    s.add_argument("--kind", default="secret")
    s.add_argument("--note")
    s.add_argument("--with-username", action="store_true")
    s.add_argument("--tty", action="store_true")
    s.set_defaults(func=cmd_need)

    s = sub.add_parser("list", help="list secret names (no values)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("has", help="exit 0 if a secret exists")
    s.add_argument("name")
    s.add_argument("-q", "--quiet", action="store_true")
    s.set_defaults(func=cmd_has)

    s = sub.add_parser("get", help="print a value (refused inside an agent)")
    s.add_argument("name")
    s.add_argument("--reveal", action="store_true", help="required acknowledgement")
    s.add_argument("-n", "--no-newline", action="store_true")
    s.set_defaults(func=cmd_get)

    s = sub.add_parser("rm", help="delete a secret")
    s.add_argument("name")
    s.set_defaults(func=cmd_rm)

    s = sub.add_parser("rename", help="rename a secret")
    s.add_argument("old")
    s.add_argument("new")
    s.set_defaults(func=cmd_rename)

    s = sub.add_parser("run", help="run a command with secrets as env vars, "
                                   "scrubbing its output")
    s.add_argument("names", nargs="*", metavar="NAME[:ENV_VAR]")
    s.add_argument("--all", action="store_true", help="inject every secret in the profile")
    s.add_argument("--no-scrub", action="store_true", help="disable output redaction")
    s.set_defaults(func=cmd_run, command=[])

    s = sub.add_parser("env", help="write secrets to a .env file (never to stdout)")
    s.add_argument("names", nargs="*", metavar="NAME[:ENV_VAR]")
    s.add_argument("--all", action="store_true")
    s.add_argument("--to", help="output file, e.g. .env.local")
    s.add_argument("--format", default="dotenv",
                   choices=("dotenv", "export", "powershell"))
    s.add_argument("--unsafe-stdout", action="store_true",
                   help="print to stdout anyway (refused inside an agent)")
    s.set_defaults(func=cmd_env)

    s = sub.add_parser("template",
                       help="render ${VAULT:NAME} placeholders into a real config file")
    s.add_argument("input")
    s.add_argument("output")
    s.set_defaults(func=cmd_template)

    s = sub.add_parser("doctor", help="diagnose the setup")
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("install-claude",
                       help="install the Claude Code skill, hook and permissions")
    s.add_argument("--scope", default="user", choices=("user", "project"))
    s.add_argument("--project", help="project directory for --scope project")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_install_claude)

    s = sub.add_parser("lang", help="show or set the interface language")
    s.add_argument("code", nargs="?", choices=SUPPORTED)
    s.set_defaults(func=cmd_lang)

    return p


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    # Split on the first bare "--" ourselves. argparse.REMAINDER interacts badly
    # with a preceding nargs="*", and "vault run A B -- cmd --flag" has to work.
    tail: list[str] = []
    if "--" in argv:
        idx = argv.index("--")
        argv, tail = argv[:idx], argv[idx + 1:]

    parser = build_parser()
    args = parser.parse_args(argv)
    if tail:
        if getattr(args, "cmd", None) != "run":
            err(f"unexpected arguments after '--': {' '.join(tail)}")
            return 2
        args.command = tail

    lang = args.lang
    if not lang:
        try:
            lang = Vault(home=Path(args.path).expanduser() if args.path else None
                         ).config().get("lang")
        except Exception:
            lang = None
    set_lang(lang)

    try:
        return int(args.func(args) or 0)
    except VaultError as exc:
        err(str(exc))
        return 1
    except KeyboardInterrupt:
        err(current()("error.cancelled"))
        return 130
    except BrokenPipeError:  # pragma: no cover
        return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
