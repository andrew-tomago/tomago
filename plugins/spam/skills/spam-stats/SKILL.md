---
name: spam-stats
description: "[Skill] [Sonnet] Display activation analytics across temporal horizons"
model: claude-sonnet-4-5
disable-model-invocation: true
user-invocable: true
version: 0.1.0
---

# SPAM Stats

Show activation metrics for all installed Claude Code skills and commands across daily, weekly, monthly, yearly, and all-time horizons.

## Workflow

Run the following steps in order:

1. Rebuild the catalog of installed skills and commands:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/spam-stats/scripts/catalog-builder.py"
   ```

2. Reconcile missed activations from session transcripts (backfill preloaded subagent skills):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/spam-stats/scripts/reconcile.py"
   ```

3. Query and render the activation analytics report:
   ```bash
   uv run --script "${CLAUDE_PLUGIN_ROOT}/skills/spam-stats/scripts/spam-stats.py"
   ```

The report displays component-level activation counts in a formatted table, grouped by component type (skill/command) and sorted by all-time usage. Detection methods are summarized at the bottom (tool_call, prompt_match, bash_match, transcript).

## Prerequisites

- Python 3.9+
- `uv` (astral-sh/uv) — manages duckdb dependency via PEP 723 inline metadata
- Claude Code hooks configured (installed via `claude plugin install`)

## Data Location

- **Event store:** `~/.claude/spam/activations.sqlite` (SQLite, written by hooks)
- **Catalog:** `~/.claude/spam/catalog.json` (rebuilt on each run)

## Notes

- Hook-based tracking is real-time; preloaded subagent skill activations are reconciled retroactively from transcripts
- Component zero-activation entries appear in the output (showing full coverage)
- Detection method distribution helps identify gaps in hook coverage

See `/docs/architecture.md` for technical details.
