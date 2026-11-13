---
name: Scrubber missed a leak
about: A secret value appeared in output that vault run should have redacted
title: "scrubber: "
labels: ["leak-pattern"]
---

**Do not paste the real secret.** Use a fake value that reproduces the shape.

### The command

```bash
vault run FAKE_TOKEN -- <the command that leaked>
```

### What appeared in the output

The encoding the value was in (raw / URL-encoded / base64 / JSON-escaped /
something else), and the surrounding line with the value replaced by `XXXX`.

### Expected

`***REDACTED:FAKE_TOKEN***`

### Environment

Output of `vault doctor` (it contains no secret values).

### A failing test, if you can

The most useful thing you can send is a case added to
`test_scrub_plain_and_encoded` in `tests/test_vault.py` that fails on `main`.
