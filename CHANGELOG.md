# Changelog

## 1.2.0-beta.5 — Session approval controls

- Add an opt-in `--yolo` flag for session-scoped native approval bypass in supported harnesses, with warnings.
- Reject the flag for Pi, where an equivalent has not been verified.

## 1.2.0-beta.4 — Updates and OpenCode configuration

- Add release update checks, verified downloads, channel selection and rollback.
- Configure OpenCode model and reasoning effort through its process environment, and add the max effort option.

## 1.2.0-beta.3 — OpenCode launch fix

- Remove the unsupported `mini` subcommand when launching OpenCode.

## 1.2.0-beta.2 — OpenCode JSONC compatibility

- Support existing OpenCode JSONC configurations while preserving unrelated settings and comments.
- Protect against conflicting providers, invalid configurations and interrupted updates.
- Keep other harness integrations and session affinity experimental; see the compatibility matrix.

## 1.2.0-beta.1 — Multi-Harness Support

- Added a configurable default harness and native provider configuration for OpenCode and Pi, plus isolated Claude Code launch and the existing Codex profile.
- Added model synchronization, harness discovery, integration installation/removal and local diagnostics. Provider updates preserve unrelated JSON settings, back up changes and refuse conflicting edits.
- Added child-process credential injection and tests using gateway fixtures. No inference is performed by setup, synchronization or diagnostics.
- OpenCode v2 provider loading and reasoning payloads were validated with a local simulated gateway; real router behavior remains unverified; Pi thinking is disabled pending mapping validation. Claude requires an Anthropic-compatible gateway and Claude model ID. See `docs/multi-harness.md` for limitations.

## 1.1.0

- Existing gateway CLI and independent Codex integration.
