"""Registered harness adapters."""
from .adapters import OpenCode, Codex, Pi, Claude
HARNESSES = {x.name: x for x in (
    OpenCode('opencode', 'OpenCode', 'opencode'),
    Codex('codex', 'Codex CLI', 'codex'),
    Pi('pi', 'Pi Coding Agent', 'pi'),
    Claude('claude', 'Claude Code', 'claude'),
)}
