---
name: vault
description: Use when a task needs a password, API key, token, connection string, or any other credential - including when a command fails with 401/403, "authentication required", or "missing API key". Stores credentials outside the conversation and runs commands with them injected, so values never enter the transcript.
---

# vault - credentials without putting them in the conversation

Never ask the user to type a credential into the chat. Never read one from a
file. Never print one. Use the `vault` CLI: you work with **names**, the user
types **values** into a dialog you cannot see.

## The three commands you need

```bash
vault list                          # what credentials exist (names only)
vault need DB_PASSWORD API_TOKEN    # ensure they exist; opens a dialog for missing ones
vault run DB_PASSWORD -- psql ...   # run a command with $DB_PASSWORD set
```

`vault run` injects each secret as an environment variable and redacts the value
from the command's stdout/stderr on the way back to you. That redaction is why
you can safely run verbose commands.

## Workflow

1. **Check first.** `vault list` at the point you discover a credential is
   needed. If the name is there, go to step 3.
2. **Request it.** `vault need <NAME>` - this opens a dialog on the user's
   machine. Then tell them: *"I've opened a dialog for `<NAME>` - the value goes
   straight into your vault, I won't see it."* The command blocks until they
   finish, and exits non-zero if they cancel.
3. **Use it.** Wrap the real command:
   ```bash
   vault run GITHUB_TOKEN -- gh auth login --with-token
   vault run DB_PASSWORD -- dotnet ef database update
   vault run OPENAI_API_KEY ANTHROPIC_API_KEY -- python eval.py
   ```
4. **Remap when the variable name differs:**
   ```bash
   vault run DB_PASSWORD:ConnectionStrings__Default -- dotnet run
   ```

## Naming

Use the environment variable name the program already expects, uppercase with
underscores: `DATABASE_URL`, `STRIPE_SECRET_KEY`, `SMTP_PASSWORD`. If a secret
belongs to a specific host or account, say so in the name
(`PROD_DB_PASSWORD`, not `PASSWORD`) and add `--note` for context.

Add `--with-username` when the credential is a username/password pair.

## Config files

Do not write a secret into `appsettings.json`, `settings.py`, or any file that
could be committed. Commit a template with placeholders instead:

```jsonc
// appsettings.Development.template.json  (safe to commit)
{ "ConnectionStrings": { "Default": "Server=db;Password=${VAULT:PROD_DB_PASSWORD}" } }
```

```bash
vault template appsettings.Development.template.json appsettings.Development.json
```

The rendered file is written with 0600 permissions, and vault warns you if it
is not gitignored. When a tool can only read `.env`, use
`vault env NAME --to .env.local` - which writes the file but never prints it.

## Hard rules

- **Never** run `vault get`, `vault env --unsafe-stdout`, or `vault run --no-scrub`.
  A hook blocks these; attempting one wastes a turn.
- **Never** `cat`/`Read` a `.env` file, `master.key`, or `secrets.enc`.
- **Never** `echo $SECRET_NAME`, `printenv`, or dump the environment.
- **Never** ask for a credential in chat, even if the user offers. If the user
  pastes one anyway, say plainly that it is now in the transcript, suggest they
  rotate it, and store the replacement with `vault need`.
- For SSH, prefer a key plus `ssh-agent` over storing a password.

## When something is missing

`vault run` exits 1 and names the missing secret. Run `vault need <NAME>` and
retry. Do not guess a value, do not fall back to a placeholder, and do not
disable the check.

`vault doctor` reports the backend, vault path, language, and whether the guard
hook is installed - useful when a command behaves unexpectedly.

## Profiles

`--profile` (or `VAULT_PROFILE`) separates environments:

```bash
vault --profile prod run DB_PASSWORD -- ./migrate.sh
vault --profile staging list
```

When the user mentions an environment by name, use the matching profile rather
than prefixing every secret name.
