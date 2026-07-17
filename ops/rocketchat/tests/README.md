# Rocket.Chat ↔ Grok integration tests

```bash
python3 ~/.grok/agency/ops/rocketchat/tests/test_rc_integration.py
```

Covers: env load, seed-without-wake, principal-only filtering, lock single-flight,
wake argv safety (no `--disallowed-tools Agent`), missing secrets, unreachable RC,
optional live smoke (login + post + presence).

Shared production logic: `../wake/wake_lib.py`.
