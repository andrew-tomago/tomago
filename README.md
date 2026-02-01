# tomago

Public marketplace for [andrew-tomago](https://github.com/andrew-tomago) Claude Code plugins.

## Installation

```bash
claude plugin marketplace add ~/andrew-tomago/public/tomago
```

## Plugins

| Plugin | Version | Description |
|--------|---------|-------------|
| [spam](./plugins/spam/) | 0.1.0 | Skill & plugin activations monitor — usage analytics across sessions |

## Usage

```bash
# List available plugins
claude plugin marketplace list

# Install a plugin
claude plugin install spam@tomago

# Validate marketplace structure
claude plugin validate ~/andrew-tomago/public/tomago/
```

## Structure

```
tomago/
├── .claude-plugin/
│   └── marketplace.json
├── .gitignore
├── README.md
└── plugins/
    └── spam/
        ├── .claude-plugin/plugin.json
        ├── LICENSE
        ├── README.md
        ├── hooks/           (event capture)
        ├── skills/          (2 skills)
        └── docs/            (1 reference doc)
```
