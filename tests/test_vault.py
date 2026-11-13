import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from claude_vault.i18n import SUPPORTED, Translator  # noqa: E402
from claude_vault.scrub import Scrubber, env_name, scrub_text  # noqa: E402
from claude_vault.store import Vault, VaultError  # noqa: E402


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("VAULT_HOME", str(tmp_path / "vault"))
    monkeypatch.delenv("VAULT_PROFILE", raising=False)
    return Vault(home=tmp_path / "vault", backend="file")


# --------------------------------------------------------------------- store


def test_roundtrip(vault):
    vault.set("API_TOKEN", "sk-live-abc123", kind="token", note="staging")
    assert vault.exists("API_TOKEN")
    assert vault.get("API_TOKEN") == "sk-live-abc123"
    assert [e.name for e in vault.list()] == ["API_TOKEN"]
    assert vault.meta("API_TOKEN").note == "staging"


def test_index_never_contains_the_value(vault):
    vault.set("DB_PASSWORD", "hunter2-super-secret")
    raw = (vault.home / "index.json").read_text()
    assert "hunter2-super-secret" not in raw
    assert "DB_PASSWORD" in raw


def test_encrypted_blob_is_not_plaintext(vault):
    vault.set("DB_PASSWORD", "hunter2-super-secret")
    blob = (vault.home / "secrets.enc").read_bytes()
    assert b"hunter2-super-secret" not in blob
    assert b"DB_PASSWORD" not in blob


def test_profiles_are_isolated(tmp_path):
    a = Vault(home=tmp_path / "v", profile="prod", backend="file")
    b = Vault(home=tmp_path / "v", profile="dev", backend="file")
    a.set("DB_PASSWORD", "prod-value")
    b.set("DB_PASSWORD", "dev-value")
    assert a.get("DB_PASSWORD") == "prod-value"
    assert b.get("DB_PASSWORD") == "dev-value"
    assert sorted(Vault(home=tmp_path / "v", backend="file").profiles()) == ["dev", "prod"]


def test_delete_and_rename(vault):
    vault.set("OLD", "value-to-keep")
    vault.rename("OLD", "NEW")
    assert not vault.exists("OLD")
    assert vault.get("NEW") == "value-to-keep"
    vault.delete("NEW")
    assert not vault.exists("NEW")


def test_missing_secret_raises(vault):
    with pytest.raises(VaultError):
        vault.get("NOPE")


def test_invalid_name_rejected(vault):
    with pytest.raises(VaultError):
        vault.set("bad name", "x")


# --------------------------------------------------------------------- scrub


def test_scrub_plain_and_encoded():
    secrets = {"TOKEN": "s3cr3t-value-xyz"}
    assert "s3cr3t-value-xyz" not in scrub_text("key=s3cr3t-value-xyz", secrets)
    assert "REDACTED:TOKEN" in scrub_text("key=s3cr3t-value-xyz", secrets)
    # base64, as an SDK debug log would emit it
    import base64

    b64 = base64.b64encode(b"s3cr3t-value-xyz").decode()
    assert b64 not in scrub_text(f"Authorization: Basic {b64}", secrets)
    # json-escaped, as a structured log would emit it
    payload = json.dumps({"token": "s3cr3t-value-xyz"})
    assert "s3cr3t-value-xyz" not in scrub_text(payload, secrets)


def test_scrub_across_chunk_boundary():
    s = Scrubber({"T": "abcdefghij"})
    out = s.feed(b"prefix abcde") + s.feed(b"fghij suffix") + s.flush()
    assert b"abcdefghij" not in out
    assert b"REDACTED:T" in out


def test_scrub_short_values_are_not_redacted():
    # a 3-char secret would turn every log line into noise
    assert scrub_text("the cat sat", {"X": "cat"}) == "the cat sat"


def test_env_name():
    assert env_name("DB_PASSWORD") == "DB_PASSWORD"
    assert env_name("my-api.key") == "MY_API_KEY"
    assert env_name("1token") == "V_1TOKEN"


# --------------------------------------------------------------------- i18n


def test_all_locales_have_the_same_keys():
    base = set(json.loads(
        (Path(__file__).resolve().parents[1]
         / "src/claude_vault/locales/en.json").read_text(encoding="utf-8")
    ))
    for lang in SUPPORTED:
        path = (Path(__file__).resolve().parents[1]
                / f"src/claude_vault/locales/{lang}.json")
        keys = set(json.loads(path.read_text(encoding="utf-8")))
        assert keys == base, f"{lang}.json key mismatch: {base ^ keys}"


def test_translator_falls_back_to_english():
    t = Translator("fa")
    assert t("dialog.save") != "dialog.save"
    assert t("nonexistent.key") == "nonexistent.key"


def test_rtl_flag():
    assert Translator("fa").rtl and Translator("ar").rtl
    assert not Translator("en").rtl


# --------------------------------------------------------------------- cli


def _cli(args, env=None, **kw):
    full = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    full.update(env or {})
    return subprocess.run([sys.executable, "-m", "claude_vault", *args],
                          capture_output=True, text=True, env=full, **kw)


def test_cli_set_via_stdin_then_run(tmp_path):
    env = {"VAULT_HOME": str(tmp_path / "v"), "VAULT_BACKEND": "file",
           "VAULT_LANG": "en"}
    assert _cli(["set", "MY_TOKEN", "--stdin"], env,
                input="tok-abcdef-123456").returncode == 0

    listing = _cli(["list"], env)
    assert "MY_TOKEN" in listing.stdout
    assert "tok-abcdef-123456" not in listing.stdout

    run = _cli(["run", "MY_TOKEN", "--", sys.executable, "-c",
                "import os;print('leak:'+os.environ['MY_TOKEN'])"], env)
    assert run.returncode == 0
    assert "tok-abcdef-123456" not in run.stdout
    assert "REDACTED:MY_TOKEN" in run.stdout


def test_cli_get_is_refused_inside_an_agent(tmp_path):
    env = {"VAULT_HOME": str(tmp_path / "v"), "VAULT_BACKEND": "file",
           "VAULT_LANG": "en", "CLAUDECODE": "1"}
    _cli(["set", "T", "--stdin"], env, input="value-123456")
    out = _cli(["get", "T"], env)
    assert out.returncode == 3
    assert "value-123456" not in out.stdout


def test_cli_template_render(tmp_path):
    env = {"VAULT_HOME": str(tmp_path / "v"), "VAULT_BACKEND": "file",
           "VAULT_LANG": "en"}
    _cli(["set", "DB_PASSWORD", "--stdin"], env, input="p@ss-123456")
    src = tmp_path / "appsettings.template.json"
    src.write_text(json.dumps({"cs": "Server=db;Password=${VAULT:DB_PASSWORD}"}))
    dst = tmp_path / "appsettings.json"
    res = _cli(["template", str(src), str(dst)], env)
    assert res.returncode == 0
    assert "p@ss-123456" in dst.read_text()
    assert "p@ss-123456" not in res.stdout


def test_cli_need_check_reports_missing(tmp_path):
    env = {"VAULT_HOME": str(tmp_path / "v"), "VAULT_BACKEND": "file",
           "VAULT_LANG": "en"}
    res = _cli(["need", "ABSENT", "--check"], env)
    assert res.returncode == 1
    assert "ABSENT" in res.stdout


# --------------------------------------------------------------------- hook


def _hook(payload, env=None):
    hook = (Path(__file__).resolve().parents[1]
            / "src/claude_vault/hooks/vault_guard.py")
    full = {**os.environ}
    full.update(env or {})
    return subprocess.run([sys.executable, str(hook)], input=json.dumps(payload),
                          capture_output=True, text=True, env=full)


@pytest.mark.parametrize("command", [
    "vault get DB_PASSWORD",
    "vault --profile prod get API_KEY",
    "vault env API_KEY --unsafe-stdout",
    "vault run API_KEY --no-scrub -- curl https://x",
    "cat .env.local",
])
def test_hook_blocks_leaky_commands(command, tmp_path):
    res = _hook({"tool_name": "Bash", "tool_input": {"command": command}},
                {"VAULT_HOME": str(tmp_path)})
    assert res.returncode == 2, command
    assert "claude-vault" in res.stderr


@pytest.mark.parametrize("command", [
    "vault list",
    "vault need DB_PASSWORD",
    "vault run DB_PASSWORD -- psql -h localhost",
    "git status",
    "echo hello world",
])
def test_hook_allows_normal_commands(command, tmp_path):
    res = _hook({"tool_name": "Bash", "tool_input": {"command": command}},
                {"VAULT_HOME": str(tmp_path)})
    assert res.returncode == 0, command


def test_hook_blocks_reading_key_material(tmp_path):
    res = _hook({"tool_name": "Read",
                 "tool_input": {"file_path": str(tmp_path / "master.key")}},
                {"VAULT_HOME": str(tmp_path)})
    assert res.returncode == 2


def test_hook_blocks_echoing_an_injected_var(tmp_path):
    (tmp_path / "index.json").write_text(json.dumps(
        {"version": 1, "profiles": {"default": {"DB_PASSWORD": {"name": "DB_PASSWORD"}}}}
    ))
    res = _hook({"tool_name": "Bash", "tool_input": {"command": "echo $DB_PASSWORD"}},
                {"VAULT_HOME": str(tmp_path)})
    assert res.returncode == 2


def test_hook_allows_everything_on_malformed_input():
    hook = (Path(__file__).resolve().parents[1]
            / "src/claude_vault/hooks/vault_guard.py")
    res = subprocess.run([sys.executable, str(hook)], input="not json",
                         capture_output=True, text=True)
    assert res.returncode == 0
