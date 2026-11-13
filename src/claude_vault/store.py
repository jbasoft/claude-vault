"""Secret storage.

Two backends, selected automatically:

``keyring``  values live in the OS credential store (Windows Credential
             Manager / macOS Keychain / Secret Service). Nothing secret ever
             touches the vault directory.
``file``     values live in an AES-256-GCM encrypted blob inside the vault
             directory. The data key is wrapped with DPAPI on Windows, or kept
             in the OS keyring, or (last resort, with a warning) in a 0600 key
             file.

Either way the *index* -- names, timestamps, notes -- is plain JSON, because
names are not secret and Claude is allowed to read them.
"""

from __future__ import annotations

import base64
import json
import os
import platform
import secrets
import stat
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

SERVICE = "claude-vault"
MASTER_KEY_ENTRY = "__master_key__"
INDEX_VERSION = 1


class VaultError(RuntimeError):
    pass


# --------------------------------------------------------------------------- paths


def vault_home() -> Path:
    """Vault directory. Override with VAULT_HOME (the configurable path)."""
    env = os.environ.get("VAULT_HOME") or os.environ.get("CLAUDE_VAULT_HOME")
    if env:
        return Path(env).expanduser().resolve()
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base).joinpath("claude-vault").resolve()
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg).joinpath("claude-vault").resolve()
    return Path.home().joinpath(".claude-vault").resolve()


def current_profile() -> str:
    return os.environ.get("VAULT_PROFILE") or "default"


def _harden(path: Path) -> None:
    """Best-effort 0600 / 0700."""
    try:
        if path.is_dir():
            path.chmod(stat.S_IRWXU)
        else:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


# --------------------------------------------------------------------------- keyring


def _keyring():
    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring

        if isinstance(keyring.get_keyring(), FailKeyring):
            return None
        return keyring
    except Exception:
        return None


# --------------------------------------------------------------------------- crypto


def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        return AESGCM
    except Exception as exc:  # pragma: no cover
        raise VaultError(
            "The file backend needs the 'cryptography' package: pip install cryptography"
        ) from exc


def _dpapi_protect(data: bytes) -> bytes:  # pragma: no cover - Windows only
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    src = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)
    ):
        raise VaultError("CryptProtectData failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:  # pragma: no cover - Windows only
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    src = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)
    ):
        raise VaultError("CryptUnprotectData failed (vault was created by another user?)")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


# --------------------------------------------------------------------------- model


@dataclass
class Entry:
    name: str
    kind: str = "secret"  # secret | token | password | apikey
    note: str = ""
    username: str = ""
    created: float = 0.0
    updated: float = 0.0

    def public(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- vault


class Vault:
    def __init__(self, home: Path | None = None, profile: str | None = None,
                 backend: str | None = None) -> None:
        self.home = home or vault_home()
        self.profile = profile or current_profile()
        self.home.mkdir(parents=True, exist_ok=True)
        _harden(self.home)
        self.index_path = self.home / "index.json"
        self.blob_path = self.home / "secrets.enc"
        self.keyfile_path = self.home / "master.key"
        self.config_path = self.home / "config.json"
        self.backend = backend or self._resolve_backend()

    # -- config / backend ---------------------------------------------------

    def _read_json(self, path: Path, default):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default

    def _resolve_backend(self) -> str:
        explicit = os.environ.get("VAULT_BACKEND")
        if explicit in ("keyring", "file"):
            return explicit
        cfg = self._read_json(self.config_path, {})
        if cfg.get("backend") in ("keyring", "file"):
            return cfg["backend"]
        return "keyring" if _keyring() else "file"

    def save_config(self, **kwargs) -> None:
        cfg = self._read_json(self.config_path, {})
        cfg.update({k: v for k, v in kwargs.items() if v is not None})
        self.config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        _harden(self.config_path)

    def config(self) -> dict:
        return self._read_json(self.config_path, {})

    # -- index --------------------------------------------------------------

    def _index(self) -> dict:
        data = self._read_json(self.index_path, {})
        if not isinstance(data, dict) or "profiles" not in data:
            data = {"version": INDEX_VERSION, "profiles": {}}
        return data

    def _write_index(self, data: dict) -> None:
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.index_path)
        _harden(self.index_path)

    def profiles(self) -> list[str]:
        return sorted(self._index()["profiles"].keys()) or ["default"]

    def list(self) -> list[Entry]:
        raw = self._index()["profiles"].get(self.profile, {})
        return [Entry(**v) for _, v in sorted(raw.items())]

    def exists(self, name: str) -> bool:
        return name in self._index()["profiles"].get(self.profile, {})

    def meta(self, name: str) -> Entry | None:
        raw = self._index()["profiles"].get(self.profile, {}).get(name)
        return Entry(**raw) if raw else None

    # -- key material -------------------------------------------------------

    def _master_key(self, create: bool = False) -> bytes:
        kr = _keyring()
        if kr is not None:
            try:
                stored = kr.get_password(SERVICE, MASTER_KEY_ENTRY)
            except Exception:
                stored = None
            if stored:
                return base64.b64decode(stored)
            if create:
                key = secrets.token_bytes(32)
                try:
                    kr.set_password(SERVICE, MASTER_KEY_ENTRY,
                                    base64.b64encode(key).decode())
                    return key
                except Exception:
                    pass  # fall through to file

        if self.keyfile_path.exists():
            blob = self.keyfile_path.read_bytes()
            if blob.startswith(b"DPAPI1"):
                return _dpapi_unprotect(blob[6:])
            return base64.b64decode(blob)

        if not create:
            raise VaultError("Vault is not initialised yet; store a secret first.")

        key = secrets.token_bytes(32)
        if platform.system() == "Windows":
            self.keyfile_path.write_bytes(b"DPAPI1" + _dpapi_protect(key))
        else:
            self.keyfile_path.write_bytes(base64.b64encode(key))
            print(
                "claude-vault: no OS keyring available; the data key is stored in "
                f"{self.keyfile_path} with 0600 permissions.",
                file=sys.stderr,
            )
        _harden(self.keyfile_path)
        return key

    # -- blob ---------------------------------------------------------------

    def _read_blob(self) -> dict:
        if not self.blob_path.exists():
            return {}
        raw = self.blob_path.read_bytes()
        if len(raw) < 13 or raw[:1] != b"\x01":
            raise VaultError("Encrypted vault file is corrupt or unreadable.")
        nonce, ct = raw[1:13], raw[13:]
        AESGCM = _aesgcm()
        try:
            plain = AESGCM(self._master_key()).decrypt(nonce, ct, b"claude-vault")
        except Exception as exc:
            raise VaultError("Could not decrypt the vault (wrong key or tampered file).") from exc
        return json.loads(plain.decode("utf-8"))

    def _write_blob(self, data: dict) -> None:
        AESGCM = _aesgcm()
        nonce = secrets.token_bytes(12)
        ct = AESGCM(self._master_key(create=True)).encrypt(
            nonce, json.dumps(data).encode("utf-8"), b"claude-vault"
        )
        tmp = self.blob_path.with_suffix(".tmp")
        tmp.write_bytes(b"\x01" + nonce + ct)
        _harden(tmp)
        tmp.replace(self.blob_path)
        _harden(self.blob_path)

    # -- public API ---------------------------------------------------------

    def _slot(self, name: str) -> str:
        return f"{self.profile}/{name}"

    def set(self, name: str, value: str, *, kind: str = "secret",
            note: str = "", username: str = "") -> None:
        if not name or any(c in name for c in " \t\n/\\"):
            raise VaultError(f"Invalid secret name: {name!r}")
        if self.backend == "keyring":
            kr = _keyring()
            if kr is None:
                raise VaultError("keyring backend requested but unavailable.")
            kr.set_password(SERVICE, self._slot(name), value)
        else:
            blob = self._read_blob() if self.blob_path.exists() else {}
            blob[self._slot(name)] = value
            self._write_blob(blob)

        idx = self._index()
        prof = idx["profiles"].setdefault(self.profile, {})
        now = time.time()
        existing = prof.get(name, {})
        prof[name] = Entry(
            name=name,
            kind=kind or existing.get("kind", "secret"),
            note=note or existing.get("note", ""),
            username=username or existing.get("username", ""),
            created=existing.get("created") or now,
            updated=now,
        ).public()
        idx["backend"] = self.backend
        self._write_index(idx)

    def get(self, name: str) -> str:
        if not self.exists(name):
            raise VaultError(f"No secret named {name!r} in profile {self.profile!r}.")
        if self.backend == "keyring":
            kr = _keyring()
            if kr is None:
                raise VaultError("keyring backend requested but unavailable.")
            value = kr.get_password(SERVICE, self._slot(name))
        else:
            value = self._read_blob().get(self._slot(name))
        if value is None:
            raise VaultError(
                f"{name!r} is in the index but its value is missing from the {self.backend} "
                "backend. Re-run 'vault set' for it."
            )
        return value

    def delete(self, name: str) -> None:
        if self.backend == "keyring":
            kr = _keyring()
            if kr is not None:
                try:
                    kr.delete_password(SERVICE, self._slot(name))
                except Exception:
                    pass
        elif self.blob_path.exists():
            blob = self._read_blob()
            blob.pop(self._slot(name), None)
            self._write_blob(blob)
        idx = self._index()
        idx["profiles"].get(self.profile, {}).pop(name, None)
        self._write_index(idx)

    def rename(self, old: str, new: str) -> None:
        value = self.get(old)
        m = self.meta(old)
        self.set(new, value, kind=m.kind if m else "secret",
                 note=m.note if m else "", username=m.username if m else "")
        self.delete(old)
