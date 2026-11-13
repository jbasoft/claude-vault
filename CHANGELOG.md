# Changelog

## 0.3.0 — first public release

- `vault run` — inject secrets as environment variables into a child process and
  scrub the value out of its stdout and stderr, covering raw, URL-encoded,
  base64 and JSON-escaped forms, including matches split across read buffers.
- `vault need` — the command an agent calls to make a credential exist: prints
  names, opens a native dialog for whatever is missing, blocks until answered.
- `vault template` — render `${VAULT:NAME}` placeholders into a real config
  file, so the template stays in git and the rendered file does not.
- `vault install-claude` — installs the skill, the `PreToolUse` guard hook and
  deny rules, merging into an existing `settings.json` without disturbing it.
- Storage: OS credential store when available, otherwise an AES-256-GCM file
  with the data key wrapped by DPAPI, the keyring, or a `0600` key file.
- Profiles, `vault doctor`, configurable `VAULT_HOME`.
- Six interface languages (en, fa, ar, fr, tr, es) with RTL dialog layout.
