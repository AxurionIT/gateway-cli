# Changelog

## 1.2.0-beta.1 — Multi-Harness Support

- Added a configurable default harness and native provider configuration for OpenCode and Pi, plus isolated Claude Code launch and the existing Codex profile.
- Added model synchronization, harness discovery, integration installation/removal and local diagnostics. Provider updates preserve unrelated JSON settings, back up changes and refuse conflicting edits.
- Added child-process credential injection and tests using gateway fixtures. No inference is performed by setup, synchronization or diagnostics.
- OpenCode v2 provider loading and reasoning payloads were validated with a local simulated gateway; real router behavior remains unverified; Pi thinking is disabled pending mapping validation. Claude requires an Anthropic-compatible gateway and Claude model ID. See `docs/multi-harness.md` for limitations.

## 1.1.0

- Existing gateway CLI and independent Codex integration.
