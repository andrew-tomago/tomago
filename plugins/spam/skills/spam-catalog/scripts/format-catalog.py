#!/usr/bin/env python3
# created: 2026-01-31
# created_by:
#   agent: Claude Code 2.1.29
#   model: claude-opus-4-5-20251101
"""
Markdown table renderer for the SPAM catalog.
Reads catalog.json and outputs a grouped, scannable table per source.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

CATALOG_PATH = Path.home() / ".claude" / "spam" / "catalog.json"


def load_catalog() -> dict:
    if not CATALOG_PATH.is_file():
        print("Catalog not found — run catalog-builder.py first", file=sys.stderr)
        sys.exit(1)
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def merge_entries(catalog: dict) -> list[dict]:
    """Merge skills and commands into a unified list, dedup by (name, source)."""
    seen: set = set()
    merged: list = []
    for item in catalog.get("skills", []) + catalog.get("commands", []):
        key = (item["name"], item["source"])
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def render(catalog: dict) -> str:
    entries = merge_entries(catalog)
    by_source: dict[str, list[dict]] = {}
    for e in entries:
        by_source.setdefault(e["source"], []).append(e)

    lines: list[str] = []
    generated = catalog.get("generated_at", "unknown")
    lines.append("# SPAM — Installed Skills & Commands")
    lines.append("")
    lines.append(f"_Generated: {generated}_")

    total = 0
    for source in sorted(by_source):
        items = sorted(by_source[source], key=lambda x: x["name"])
        total += len(items)
        lines.append("")
        lines.append(f"## {source}")
        lines.append("")
        lines.append("| Name | Scope | Lifecycle | Model |")
        lines.append("|------|-------|-----------|-------|")
        for item in items:
            name = item.get("name", "")
            scope = item.get("scope", "")
            lifecycle = item.get("lifecycle", "")
            model = item.get("model", "")
            lines.append(f"| {name} | {scope} | {lifecycle} | {model} |")

    lines.append("")
    lines.append(f"**Total:** {total} entries across {len(by_source)} sources")
    return "\n".join(lines)


def main():
    catalog = load_catalog()
    print(render(catalog))


if __name__ == "__main__":
    main()
