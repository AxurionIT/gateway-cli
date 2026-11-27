# Multi-harness integration: current compatibility

This document describes the development state, not a claim of verified end-to-end compatibility. Setup and sync query `/models`; they do not run inference. No live inference was performed in development.

| Harness | Configuration / protocol | Model discovery | Reasoning | Session affinity |
| --- | --- | --- | --- | --- |
| OpenCode v2 | Native Axurion provider, OpenAI-compatible | `/models` on sync | Real OpenCode v2.3.2 sent medium/high/xhigh to a simulated gateway; router interpretation unverified | Native session headers observed; resume and gateway recognition unverified |
| Codex | Independent Axurion profile, Responses | Gateway; profile uses selected model | `model_reasoning_effort`; router interpretation unverified | Native behavior unverified |
| Pi | Native `models.json`, Responses | All entries; Pi defaults apply when limits are missing | Thinking disabled; explicit effort rejected until mapping verified | Native behavior unverified |
| Claude Code | Isolated process environment, Anthropic Messages required | Explicit Claude model ID; gateway compatibility not established | CLI `--effort`; availability and gateway mapping depend on model | Native behavior unverified |

Neither model limits nor multimodal capabilities are inferred. `/models` may not contain enough metadata for Pi: omitted limits are supplied by Pi defaults (currently 128000 context and 16384 output), not verified gateway capabilities. Check limits before use. Provider configuration does not establish that streaming, tool use, token counting, thinking or fallback works through a particular server. Claude Code is not advertised as officially supporting non-Claude models. Claude launch requires the gateway to implement Anthropic's Messages protocol; compatibility is not detected automatically. The CLI does not circumvent managed policies or alter personal credentials.

OpenCode's provider references `AXURION_API_KEY` rather than saving a key in its configuration. `axurion` injects it only in the child environment; when starting OpenCode directly, supply that variable using your own secure environment mechanism. Existing `opencode.jsonc` is edited in place while preserving unrelated content. If both global files exist, OpenCode loads JSONC after JSON; an Axurion provider in the lower-priority JSON file must be resolved manually to avoid shadowing. Remove conflicting unmanaged `axurion` entries manually only after reviewing them; the CLI refuses to overwrite them. Backups are adjacent to modified configuration files. Files changed by the user after installation are not removed automatically.

## External verification still required

OpenCode v2.3.2 provider loading, launch and model/effort payloads were exercised against a local simulated gateway. Verify preservation of existing settings and authentication in real installations, session resume and actual router behavior. Verify Pi and Claude launch against their documented protocols and all supported operating systems. Test effort routing, streaming, tools, session affinity and failover only with explicit authorization for inference. Mock tests establish request construction and local state management, not server behavior.

## Adding an adapter

Implement an `Adapter` in `gateway_cli/harnesses/adapters.py` and register it in `gateway_cli/harnesses/__init__.py`. Detection must not run shell commands. Synchronization must use only documented native config and verified catalogue metadata, avoid persisting secrets, preserve unrelated settings, and refuse unmanaged conflicts. Use `update_provider` for managed JSON providers, and implement safe removal and process-scoped credentials. Add fixture tests for idempotence, conflict handling, interrupted writes, launch and removal. If a protocol capability cannot be verified, do not advertise it; document its limitation. The current CLI still contains harness-specific launch/Codex handling; the adapter contract is not yet fully decoupled.

OpenCode also sends a separate low-effort request to generate a conversation title. If the gateway lacks a Low chain this auxiliary request may fail; its behavior depends on the router. The selected effort on the main request is not changed.

In one simulated no-Low-chain test, a 400 response to the title request did not prevent the main High response from completing. This does not establish behavior for every gateway or failure mode.
