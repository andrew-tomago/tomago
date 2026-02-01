---
name: spam-catalog
description: "[Skill] [Sonnet] List installed skills and commands with source metadata"
model: claude-sonnet-4-5
disable-model-invocation: true
user-invocable: true
version: 0.1.0
---

# SPAM Catalog

Show the complete catalog of all installed Claude Code skills and commands, grouped by source (plugins, user-scoped, project-scoped) as a scannable markdown table.

## Output Columns

| Column | Description |
|--------|-------------|
| Name | Skill or command name |
| Scope | Installation scope (user, project, or both) |
| Lifecycle | Stage: active, passive, or dev |
| Model | Model specified in frontmatter (if any) |

## Workflow

Run these steps in order:

1. Rebuild the catalog:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/spam-stats/scripts/catalog-builder.py"
   ```

2. Render the markdown table:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/spam-catalog/scripts/format-catalog.py"
   ```

3. Present the rendered table to the user.

## Data Location

- **Catalog:** `~/.claude/spam/catalog.json`

## Notes

- The catalog is a snapshot at query time; it rebuilds on each invocation
- Components indexed by `(name, source)` composite key — duplicates across sources kept separate
- Symlink alias pairs (kebab-case / underscore) are deduplicated automatically
