# SPAM — Skill & Plugin Activations Monitor

Tracks skill and command activations across Claude Code sessions via hooks,
reconciles from session transcripts, and surfaces analytics through DuckDB.

## Skills

| Skill | Purpose |
|-------|---------|
| `spam-stats` | Activation analytics — counts, trends across temporal horizons |
| `spam-catalog` | Lists installed skills, commands, hooks across all plugins |

## Install

```bash
claude plugin install spam@tomago
```

## Dependencies

| Dependency | Required By | Install |
|------------|-------------|---------|
| Python 3.9+ | All scripts | Ships with macOS; or `uv python install 3.12` |
| [`uv`](https://github.com/astral-sh/uv) | `spam-stats` | `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `duckdb` (Python) | `spam-stats` | **Automatic** — resolved by `uv run` via PEP 723 inline metadata |
| `sqlite3` (Python) | `track.py`, hooks | Ships with Python stdlib |

**Hot-path hooks** (`track.py`) use only Python stdlib — no external deps, no `uv` overhead.

**Analytics queries** (`spam-stats.py`) use DuckDB, managed automatically via
[PEP 723](https://peps.python.org/pep-0723/) inline script metadata +
`uv run --script`. First invocation caches the duckdb wheel; subsequent runs
resolve in ~350ms.

### Verify Setup

```bash
# Confirm uv is available
uv --version

# Pre-warm duckdb cache (optional — happens automatically on first /spam-stats)
uv run --script ~/.claude/plugins/cache/tomago/spam/*/skills/spam-stats/scripts/spam-stats.py
```

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for system design and data flow.

## License

[MIT](LICENSE)
