# Contributing

Thanks for looking. Small, focused pull requests are the easiest to merge.

```bash
git clone https://github.com/jbasoft/claude-vault && cd claude-vault
pip install -e ".[dev]"
pytest -q
ruff check src tests
```

## Especially wanted

1. **Leak patterns the scrubber misses.** If a tool emits a secret in an encoding
   `scrub.py` does not cover, a failing test in `tests/test_vault.py` is the most
   valuable thing you can send — the fix usually follows in a few lines.
2. **Guard rules for other agents.** `hooks/vault_guard.py` is Claude Code's hook
   contract. Cursor, Aider, Windsurf and Codex each have their own; a sibling
   script plus an `install-*` command would make the project useful to far more
   people.
3. **Locales.** Copy `src/claude_vault/locales/en.json`, translate the values,
   keep the keys. `test_all_locales_have_the_same_keys` enforces the rest. Add
   the code to `SUPPORTED` in `i18n.py`, and to `RTL` if the script is
   right-to-left.
4. **Platform reports.** The file backend's key wrapping differs per OS. Running
   `vault doctor` on a platform the CI matrix misses, and opening an issue with
   the output, genuinely helps.

## Ground rules

- **No new runtime dependencies** without a strong reason. The whole thing should
  stay installable with `pipx install claude-vault` on a locked-down machine.
- **Never widen what the agent can read.** A feature that makes a value easier to
  print is the one feature this project exists to refuse. If you need an escape
  hatch, it goes behind an explicit human-only flag, like `vault get --reveal`.
- **The guard fails open.** Do not make a rule that errors out on unexpected
  input; return "allow" and move on.
- **Tests for behaviour, not implementation.** The important assertions are
  "the value is not in this string" and "this command was blocked".
- Keep the README honest. If a change narrows what the tool protects against, the
  security section changes in the same PR.

## Commit messages

Plain imperative subject lines (`add base64 variant to scrubber`). No strict
convention is enforced.
