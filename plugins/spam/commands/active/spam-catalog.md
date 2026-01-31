---
name: spam-catalog
description: List all installed Claude Code skills and commands across plugins with their source and metadata
version: 0.1.0
model: claude-sonnet-4-20250514
---

# SPAM Catalog

Show the complete catalog of all installed Claude Code skills and commands, grouped by source (plugins, user-scoped, project-scoped) with descriptions and paths.

## Workflow

Run the following steps in order:

1. Rebuild the catalog of installed skills and commands:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/spam-stats/scripts/catalog-builder.py"
   ```

2. Read and format the catalog output:
   ```bash
   python3 -c "
import json
from pathlib import Path

catalog_path = Path.home() / '.claude' / 'spam' / 'catalog.json'
if catalog_path.exists():
    catalog = json.loads(catalog_path.read_text())

    # Group by source
    by_source = {}
    for skill in catalog.get('skills', []):
        src = skill['source']
        if src not in by_source:
            by_source[src] = {'skills': [], 'commands': []}
        by_source[src]['skills'].append(skill)

    for cmd in catalog.get('commands', []):
        src = cmd['source']
        if src not in by_source:
            by_source[src] = {'skills': [], 'commands': []}
        by_source[src]['commands'].append(cmd)

    # Render
    print('SPAM — Installed Skills & Commands Catalog')
    print('=' * 50)
    print()

    for source in sorted(by_source.keys()):
        data = by_source[source]
        print(f'[{source}]')
        print()

        if data['skills']:
            print('  Skills:')
            for skill in data['skills']:
                desc = skill.get('description', '(no description)')
                print(f'    • {skill[\"name\"]:30} {desc}')
            print()

        if data['commands']:
            print('  Commands:')
            for cmd in data['commands']:
                print(f'    • {cmd[\"activation_pattern\"]:30}')
            print()
else:
    print('Catalog not found — run catalog-builder.py first')
"
   ```

3. Present the formatted listing to the user.

## Prerequisites

- Python 3.7+
- Catalog already built via `/spam-stats` or direct `catalog-builder.py` invocation

## Data Location

- **Catalog:** `~/.claude/spam/catalog.json`

## Notes

- The catalog is a snapshot of installed components at query time; it updates whenever `/spam-stats` or `/spam-catalog` runs
- Components are indexed by `(name, source)` composite key — duplicates across sources are kept separate
- Script paths for commands are discovered via symlink resolution; commands without discoverable scripts show empty `script_path`

See `/docs/architecture.md` for technical details.
