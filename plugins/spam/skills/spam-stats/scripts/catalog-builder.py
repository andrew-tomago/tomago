#!/usr/bin/env python3
# created: 2026-01-31
# created_by:
#   agent: Claude Code 2.1.27
#   model: claude-opus-4-5-20251101
"""
Catalog builder for SPAM.
Scans filesystem for installed Claude Code skills and commands.
Outputs catalog.json for use by track.py and spam-stats.py.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path.home() / ".claude" / "spam"
CATALOG_PATH = DATA_DIR / "catalog.json"


def extract_frontmatter(path: Path) -> dict:
    """Parse YAML frontmatter from a markdown file.

    Looks for a ``---`` delimited block at the start of the file and
    extracts simple ``key: value`` pairs.  Returns a dict with at least
    a ``description`` key (empty string if not found).
    """
    result: dict = {"description": ""}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return result

    # Frontmatter must start at the very beginning of the file
    if not text.startswith("---"):
        return result

    end = text.find("---", 3)
    if end == -1:
        return result

    block = text[3:end].strip()
    for line in block.splitlines():
        match = re.match(r"^(\w[\w\-]*)\s*:\s*(.+)$", line)
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip().strip("\"'")
            result[key] = value

    return result


def scan_skills(base: Path, source: str) -> list:
    """Find ``SKILL.md`` files under ``base/*/SKILL.md``."""
    entries: list = []
    if not base.is_dir():
        return entries

    try:
        candidates = sorted(base.iterdir())
    except OSError:
        return entries

    for child in candidates:
        if not child.is_dir():
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.is_file():
            continue

        fm = extract_frontmatter(skill_md)
        entries.append({
            "name": child.name,
            "source": source,
            "description": fm.get("description", ""),
            "skill_md_path": str(skill_md.resolve()),
        })

    return entries


def scan_commands(base: Path, source: str) -> list:
    """Find ``.md`` command files, resolve symlinks for script paths.

    Searches the base directory plus known subdirectories
    (``active/``, ``passive/``, ``_dev/``).
    """
    entries: list = []
    if not base.is_dir():
        return entries

    search_dirs = [base]
    for subdir_name in ("active", "passive", "_dev"):
        sub = base / subdir_name
        if sub.is_dir():
            search_dirs.append(sub)

    for search_dir in search_dirs:
        try:
            children = sorted(search_dir.iterdir())
        except OSError:
            continue

        for child in children:
            if not child.is_file() or child.suffix != ".md":
                continue

            cmd_name = child.stem
            script_path = ""

            # If the .md is a symlink, try to discover a companion script
            if child.is_symlink():
                try:
                    resolved = child.resolve(strict=True)
                    scripts_dir = resolved.parent / "scripts"
                    if scripts_dir.is_dir():
                        # Pick the first script file found
                        for s in sorted(scripts_dir.iterdir()):
                            if s.is_file():
                                script_path = str(s.resolve())
                                break
                except (OSError, ValueError):
                    # Broken symlink — skip script discovery, still record command
                    pass

            entries.append({
                "name": cmd_name,
                "source": source,
                "activation_pattern": f"/{cmd_name}",
                "script_path": script_path,
            })

    return entries


def discover_plugins() -> list:
    """Return list of ``(plugin_root, plugin_name)`` tuples.

    Reads ``~/.claude/plugins/installed_plugins.json`` when available,
    otherwise falls back to globbing the plugin cache directory.
    """
    plugins_dir = Path.home() / ".claude" / "plugins"
    manifest = plugins_dir / "installed_plugins.json"
    results: list = []

    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            # Expect a list of objects with at least a "path" or "name" key,
            # or a dict keyed by plugin name.
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict):
                        p = Path(entry.get("path", "")).expanduser()
                        name = entry.get("name", p.name)
                        if p.is_dir():
                            results.append((p, name))
            elif isinstance(data, dict):
                for name, entry in data.items():
                    if isinstance(entry, dict):
                        p = Path(entry.get("path", "")).expanduser()
                        if p.is_dir():
                            results.append((p, name))
                    elif isinstance(entry, str):
                        p = Path(entry).expanduser()
                        if p.is_dir():
                            results.append((p, name))
        except (OSError, json.JSONDecodeError, TypeError):
            pass

    # Fallback: glob the cache directory
    if not results:
        cache_dir = plugins_dir / "cache"
        if cache_dir.is_dir():
            # Pattern: cache/<org>/<repo>/<ref>/<plugin>/
            try:
                for candidate in sorted(cache_dir.glob("*/*/*/*")):
                    if candidate.is_dir():
                        plugin_name = candidate.name
                        # Check for plugin.json to get a better name
                        pjson = candidate / "plugin.json"
                        if pjson.is_file():
                            try:
                                pdata = json.loads(
                                    pjson.read_text(encoding="utf-8")
                                )
                                plugin_name = pdata.get("name", plugin_name)
                            except (OSError, json.JSONDecodeError):
                                pass
                        results.append((candidate, plugin_name))
            except OSError:
                pass

    return results


def _dedup(items: list, key_fields: tuple) -> list:
    """Remove duplicates by composite key, keeping first occurrence."""
    seen: set = set()
    out: list = []
    for item in items:
        key = tuple(item.get(f, "") for f in key_fields)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def build_catalog() -> dict:
    """Assemble full catalog from all scan targets."""
    skills: list = []
    commands: list = []

    home = Path.home()

    # 1. User-scoped
    skills.extend(scan_skills(home / ".claude" / "skills", "user"))
    commands.extend(scan_commands(home / ".claude" / "commands", "user"))

    # 2. Project-scoped
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        p = Path(project_dir)
        skills.extend(scan_skills(p / ".claude" / "skills", "project"))
        commands.extend(scan_commands(p / ".claude" / "commands", "project"))

    # 3. Plugins
    for plugin_root, plugin_name in discover_plugins():
        source = f"plugin:{plugin_name}"
        skills.extend(scan_skills(plugin_root / "skills", source))
        commands.extend(scan_commands(plugin_root / "commands", source))

    # De-duplicate
    skills = _dedup(skills, ("name", "source"))
    commands = _dedup(commands, ("name", "source"))

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "skills": skills,
        "commands": commands,
    }


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    catalog = build_catalog()
    CATALOG_PATH.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    print(f"Catalog: {len(catalog['skills'])} skills, {len(catalog['commands'])} commands")
    print(f"Written to {CATALOG_PATH}")


if __name__ == "__main__":
    main()
