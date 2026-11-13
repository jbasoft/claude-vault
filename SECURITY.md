# Security policy

## Reporting a vulnerability

Please use GitHub's **private vulnerability reporting** (Security → Report a
vulnerability) rather than a public issue. If that is unavailable, open an issue
titled "security contact request" with no details and a maintainer will follow up.

Please include: the version, the platform, the backend (`vault doctor` output is
ideal — it contains no secret values), and a minimal reproduction.

## Scope

In scope, and treated as a real vulnerability:

- A secret value reaching stdout, stderr, or a log through any command the guard
  hook permits.
- A leak pattern the scrubber misses — a real encoding a tool actually emits.
- Reading a stored value without the user's OS credentials or key file.
- A guard-hook bypass: a shell construction that reveals a value and that the
  hook allows (quoting tricks, `$(…)`, variable indirection, `eval`, and so on).
- Weak file permissions, predictable nonces, key reuse, or any crypto misuse.
- A secret written anywhere unencrypted that is not the file the user asked for.

Out of scope, and documented in the README rather than fixed:

- Malware or another process running under the same user account.
- A program the user deliberately runs that exfiltrates its own environment.
- Secrets the model saw before claude-vault was installed. Rotate them.
- An agent with unrestricted shell access defeating the hook in a way that
  requires the user to approve an obviously destructive command.
- Physical access, or an attacker who already has the user's login password.

## Design notes for reviewers

- The index (`index.json`) is plaintext on purpose: it holds names, kinds, notes
  and timestamps, never values. The agent is expected to read it.
- The file backend uses AES-256-GCM with a random 96-bit nonce per write and the
  associated data `claude-vault`. The data key is 256 bits from
  `secrets.token_bytes`.
- Key wrapping, in order of preference: OS keyring → DPAPI (`CryptProtectData`,
  current-user scope) on Windows → a `0600` key file, which warns on stderr.
- `vault get` and `vault env --unsafe-stdout` exist for humans and refuse to run
  when an agent runtime is detected. They are not a bypass; they are the
  deliberate, logged, human-only exit.
- The guard hook fails **open** by design. A guard that breaks workflows gets
  uninstalled, and the threat model is accidental disclosure, not a hostile
  agent. Treat the hook as defence in depth, not as a sandbox boundary.

## Supported versions

The latest released minor version receives fixes. This is a young project; pin a
version if you need stability.
