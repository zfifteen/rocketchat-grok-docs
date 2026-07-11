# 04 — Fix Docker healthcheck

**Impact:** High · **Phase:** B (ops truth) · **Status:** Done (2026-07-10)

**Nav:** [Index](../INDEX.md) · [Requirements](./requirements.md) · [Test plan](./test-plan.md) · [Project home](../../../README.md)

## Summary

Rocket.Chat container healthcheck calls `curl`, which is missing in the image, so Compose reports **unhealthy** forever while the service actually works. Replace with a real probe.

## Implementation notes (2026-07-10)

node http healthcheck; compose recreated; container healthy
