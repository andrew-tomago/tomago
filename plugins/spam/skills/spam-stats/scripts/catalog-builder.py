#!/usr/bin/env python3
# created: 2026-01-31
# created_by:
#   agent: Claude Code 2.1.29
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

LIFECYCLE_DIRS = {
    "active": "active",
    "act": "active",
    "_dev": "dev",
    "passive": "passive",
}


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


def _infer_lifecycle(md_path: Path, commands_base: Path) -> str:
    """Infer lifecycle stage from a command's position in the directory tree."""
    try:
        rel = md_path.relative_to(commands_base)
    except ValueError:
        return "active"
    if len(rel.parts) <= 1:
        return "active"
    return LIFECYCLE_DIRS.get(rel.parts[0], "active")


def scan_skills(base: Path, source: str, scope: str = "") -> list:
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
            "scope": scope,
            "lifecycle": "active",
            "model": fm.get("model", ""),
            "description": fm.get("description", ""),
            "skill_md_path": str(skill_md.resolve()),
        })

    return entries


def scan_commands(base: Path, source: str, scope: str = "") -> list:
    """Find ``.md`` command files recursively, deduplicating symlink aliases.

    Uses ``rglob`` to handle arbitrary subdirectory nesting (``act/``,
    ``active/``, ``passive/``, ``_dev/``, domain dirs like ``act/dotfiles/``).
    Symlink alias pairs (kebab vs underscore) are collapsed — the resolved
    path is used as dedup key so only one entry per real file appears.
    """
    entries: list = []
    if not base.is_dir():
        return entries

    seen_resolved: set = set()

    try:
        md_files = sorted(base.rglob("*.md"))
    except OSError:
        return md_files

    for child in md_files:
        if not child.is_file():
            continue

        # Deduplicate symlink alias pairs by resolved path
        try:
            resolved = child.resolve(strict=True)
        except (OSError, ValueError):
            resolved = child
        if resolved in seen_resolved:
            continue
        seen_resolved.add(resolved)

        cmd_name = child.stem
        lifecycle = _infer_lifecycle(child, base)
        script_path = ""
        model = ""
        description = ""

        # Extract frontmatter from the resolved target
        fm = extract_frontmatter(resolved)
        model = fm.get("model", "")
        description = fm.get("description", "")

        # If the .md is a symlink, try to discover a companion script
        if child.is_symlink():
            try:
                scripts_dir = resolved.parent / "scripts"
                if scripts_dir.is_dir():
                    for s in sorted(scripts_dir.iterdir()):
                        if s.is_file():
                            script_path = str(s.resolve())
                            break
            except (OSError, ValueError):
                pass

        entries.append({
            "name": cmd_name,
            "source": source,
            "scope": scope,
            "lifecycle": lifecycle,
            "model": model,
            "description": description,
            "activation_pattern": f"/{cmd_name}",
            "script_path": script_path,
        })

    return entries


def discover_plugins() -> list:
    """Return list of ``(plugin_root, plugin_name, scopes)`` tuples.

    Reads ``~/.claude/plugins/installed_plugins.json`` (v1 or v2),
    otherwise falls back to globbing the plugin cache directory.
    """
    plugins_dir = Path.home() / ".claude" / "plugins"
    manifest = plugins_dir / "installed_plugins.json"
    results: list = []

    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))

            version = data.get("version", 1) if isinstance(data, dict) else 1

            if version >= 2 and isinstance(data, dict):
                # v2: {"version": 2, "plugins": {"name@org": [{"scope":..., "installPath":...}]}}
                seen_paths: dict = {}  # installPath -> (name, scopes)
                for key, scope_entries in data.get("plugins", {}).items():
                    plugin_name = key.split("@")[0]
                    if not isinstance(scope_entries, list):
                        continue
                    for entry in scope_entries:
                        if not isinstance(entry, dict):
                            continue
                        install_path = entry.get("installPath", "")
                        entry_scope = entry.get("scope", "")
                        if not install_path:
                            continue
                        p = Path(install_path).expanduser()
                        key_path = str(p)
                        if key_path in seen_paths:
                            seen_paths[key_path][1].add(entry_scope)
                        else:
                            seen_paths[key_path] = (plugin_name, {entry_scope})
                for path_str, (name, scopes) in seen_paths.items():
                    p = Path(path_str)
                    if p.is_dir():
                        results.append((p, name, scopes))

            elif isinstance(data, list):
                # v1 list format
                for entry in data:
                    if isinstance(entry, dict):
                        p = Path(entry.get("path", "")).expanduser()
                        name = entry.get("name", p.name)
                        if p.is_dir():
                            results.append((p, name, set()))

            elif isinstance(data, dict) and version < 2:
                # v1 dict format
                for name, entry in data.items():
                    if isinstance(entry, dict):
                        p = Path(entry.get("path", "")).expanduser()
                        if p.is_dir():
                            results.append((p, name, set()))
                    elif isinstance(entry, str):
                        p = Path(entry).expanduser()
                        if p.is_dir():
                            results.append((p, name, set()))

        except (OSError, json.JSONDecodeError, TypeError):
            pass

    # Fallback: glob the cache directory
    if not results:
        cache_dir = plugins_dir / "cache"
        if cache_dir.is_dir():
            # Pattern: cache/<org>/<plugin>/<version>/
            try:
                for candidate in sorted(cache_dir.glob("*/*/*")):
                    if candidate.is_dir():
                        plugin_name = candidate.parent.name
                        pjson = candidate / "plugin.json"
                        if pjson.is_file():
                            try:
                                pdata = json.loads(
                                    pjson.read_text(encoding="utf-8")
                                )
                                plugin_name = pdata.get("name", plugin_name)
                            except (OSError, json.JSONDecodeError):
                                pass
                        results.append((candidate, plugin_name, set()))
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
    skills.extend(scan_skills(home / ".claude" / "skills", "user", scope="user"))
    commands.extend(scan_commands(home / ".claude" / "commands", "user", scope="user"))

    # 2. Project-scoped
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        p = Path(project_dir)
        skills.extend(scan_skills(p / ".claude" / "skills", "project", scope="project"))
        commands.extend(scan_commands(p / ".claude" / "commands", "project", scope="project"))

    # 3. Plugins
    for plugin_root, plugin_name, scopes in discover_plugins():
        source = f"plugin:{plugin_name}"
        scope_str = ", ".join(sorted(scopes)) if scopes else ""
        skills.extend(scan_skills(plugin_root / "skills", source, scope=scope_str))
        commands.extend(scan_commands(plugin_root / "commands", source, scope=scope_str))

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
