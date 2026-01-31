# CLAUDE.md

Guidance for working with code and plugins in this marketplace repository.

## Overview

**tomago** is a Claude Code plugin marketplace containing Andrew's public plugins.

## Architecture
```
tomago/
├── .claude-plugin/marketplace.json   # Marketplace registry
└── plugins/spam/
    ├── .claude-plugin/plugin.json    # Plugin metadata
    ├── skills/                       # Source of truth
    ├── commands/                     # Symlink projection layer
    └── docs/                         # Reference documentation
```

**Core invariant:** `commands/` contains only symlinks to `skills/<name>/SKILL.md`. No original logic ever lives in `commands/`.

### Skill Lifecycle (symlink promotion)

| Stage | Location | Model | User |
|-------|----------|:-----:|:----:|
| Development | `commands/<name>.md` | no | yes |
| Production Active | `commands/active/<name>.md` | no | yes |
| Production Passive | `commands/passive/<name>.md`| yes | no |

Promotion = move symlink. Autonomy = remove symlink + flip frontmatter flags.

### Domain Directories in `act/`
TODO: complete this when done

## Conventions
TODO: link to another doc

**Model selection:**
- Default: `claude-sonnet-4-5`
- Use `claude-opus-4-5` for multi-file refactors, API design, or complex logic

## Workflow Rules

### When Committing: Version Bump Logic (`plugin.json`)

Pre-1.0: MAJOR stays `0`. Version tracks the **catalog surface**—what users can invoke and discover.

**MINOR** (`0.x.0`) — skill surface changes:
- New skill added to `skills/` with a command symlink in `command/` or `commands/act/`
- Skill output/behavior fundamentally changes (different format, different workflow)
- Skill removed or renamed
- `plugin.json` schema change

**PATCH** (`0.x.y`) — internals only:
- Routine changes to existing skills (prompt refined, new phases, tool allowances, or expanded scope)
- Docs, metadata, or template/example updates
- General fixes: correcting bugs, formatting, or broken symlinks
- Frontmatter alignment/refactoring across skills

**No bump:** `_dev/`-only additions, dev tooling shuffles, CLAUDE.md edits

Post-1.0: TODO establish rules for MAJOR version changes for breaking changes.

## Commands

See `Makefile` (or `docs/reference/commands.md`) for marketplace ops, skill dev, and validation commands.

## Key Reference Files
TODO
