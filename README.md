# tomago

Private marketplace for [andrew-tomago](https://github.com/andrew-tomago) Claude Code plugins.

## Installation

```bash
claude plugin marketplace add ~/andrew-tomago/private/tomago
```

## Plugins

| Plugin | Version | Description |
|--------|---------|-------------|
| [unique](./plugins/unique/) | 0.1.0 | Skills-first toolkit: project scaffolding, GitHub workflows, file ops, and dotfiles management |

## Usage

```bash
# List available plugins
claude plugin marketplace list

# Install a plugin
claude plugin install unique@tomago

# Validate marketplace structure
claude plugin validate ~/andrew-tomago/private/tomago/
```

## Structure

```
tomago/
├── .claude-plugin/
│   └── marketplace.json
├── .gitignore
├── README.md
└── plugins/
    └── unique/
        ├── .claude-plugin/plugin.json
        ├── LICENSE
        ├── README.md
        ├── commands/_dev/.gitkeep
        ├── skills/          (11 skills)
        └── docs/            (5 reference docs)
```
