# SPAM — Skill & Plugin Activations Monitor

Tracks skill and command activations across Claude Code sessions via hooks, reconciles from session transcripts, and surfaces analytics through DuckDB. Designed as a plugin for the `tomago` CLI framework.

## Skills

| Skill | Purpose |
|-------|---------|
| `spam-stats` | Activation analytics — counts, trends, per-session breakdowns |
| `spam-catalog` | Lists installed skills, commands, hooks across all plugins |

## Install

```bash
claude plugin install spam@tomago
```

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for system design and data flow.

## License

[MIT](LICENSE)
