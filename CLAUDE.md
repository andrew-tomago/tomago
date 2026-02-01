# CLAUDE.md

Guidance for working with code and plugins in this marketplace repository.

## Overview

**tomago** is a public Claude Code plugin marketplace containing the **spam** plugin — a skill and plugin activations monitor that tracks usage analytics across sessions.

## Architecture
```
tomago/
├── .claude-plugin/marketplace.json   # Marketplace registry
└── plugins/spam/
    ├── .claude-plugin/plugin.json    # Plugin metadata
    ├── skills/                       # Source of truth (2 skills)
    │   ├── spam-catalog/
    │   └── spam-stats/
    ├── commands/                     # Symlink projection layer
    ├── hooks/                        # Event capture (track.py)
    │   ├── hooks.json
    │   └── scripts/
    └── docs/                         # Reference documentation
```

**Core invariant:** `commands/` contains only symlinks to `skills/<name>/SKILL.md`. No original logic ever lives in `commands/`.

### Skill Lifecycle (symlink promotion)

| Stage | Location | Model | User |
|-------|----------|:-----:|:----:|
| Development | `commands/_dev/<name>.md` | no | yes |
| Production Active | `commands/act/<domain>/<name>.md` | no | yes |
| Production Passive | *(symlink removed)* | yes | no |

Promotion = move symlink. Autonomy = remove symlink + flip frontmatter flags.

## Conventions

See [claude-skills-build-tool spec](https://github.com/andrew-tomago/claude-skills-build-tool/blob/main/README.md) for frontmatter spec, naming, symlinks, and invocation rules.

**Model selection:**
- Default: `claude-sonnet-4-5`
- Use `claude-opus-4-5` for multi-file refactors, API design, or complex logic

## Workflow Rules

### When Committing: Version Bump Logic (`plugin.json`)

Pre-1.0: MAJOR stays `0`. Version tracks the **catalog surface**—what users can invoke and discover.

**MINOR** (`0.x.0`) — skill surface changes:
- New skill added to `skills/` with a command symlink in `commands/`
- Skill output/behavior fundamentally changes (different format, different workflow)
- Skill removed or renamed
- `plugin.json` schema change

**PATCH** (`0.x.y`) — internals only:
- Routine changes to existing skills (prompt refined, new phases, tool allowances, or expanded scope)
- Docs, metadata, or template/example updates
- General fixes: correcting bugs, formatting, or broken symlinks
- Frontmatter alignment/refactoring across skills

**No bump:** `_dev/`-only additions, dev tooling shuffles, CLAUDE.md edits

Post-1.0: TODO(4) establish rules for MAJOR version changes for breaking changes.

## Key Reference Files

| File | Purpose |
|------|---------|
| `plugins/spam/docs/architecture.md` | System design, detection strategies, data flow |
| `plugins/spam/README.md` | Install instructions, dependencies, verify setup |
| `plugins/spam/hooks/hooks.json` | Hook configuration (PostToolUse, UserPromptSubmit) |
| `.claude-plugin/marketplace.json` | Marketplace registry metadata |
