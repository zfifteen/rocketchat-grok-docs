# 06 — Network exposure (bind / 2FA / LAN)

**Impact:** High · **Phase:** D (polish) · **Status:** Done (2026-07-10)

**Nav:** [Index](../INDEX.md) · [Requirements](./requirements.md) · [Test plan](./test-plan.md) · [Project home](../../../README.md)

## Summary

RC is published on `0.0.0.0:3000` with 2FA disabled. Tighten bind address, document LAN vs ngrok, and harden principal account auth.

## Implementation notes (2026-07-10)

ports 127.0.0.1:3000; RC_PORT_BIND override; 2FA remains off with loopback+ngrok compensating control
