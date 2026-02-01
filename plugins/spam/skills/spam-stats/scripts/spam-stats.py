#!/usr/bin/env python3
# created: 2026-01-31
# updated: 2026-01-31
# created_by:
#   agent: Claude Code 2.1.27
#   model: claude-opus-4-5-20251101
# /// script
# requires-python = ">=3.9"
# dependencies = ["duckdb>=1.0"]
# ///
"""
Stats engine for SPAM.
Queries activation data via DuckDB's SQLite scanner.
Renders temporal analytics (daily, weekly, monthly, yearly, all-time).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path.home() / ".claude" / "spam"
DB_PATH = DATA_DIR / "activations.sqlite"
CATALOG_PATH = DATA_DIR / "catalog.json"


def load_catalog() -> dict:
    """Load catalog.json; return empty if missing."""
    if not CATALOG_PATH.exists():
        return {"skills": [], "commands": []}
    try:
        return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"skills": [], "commands": []}


def get_db_stats() -> dict | None:
    """Query activation database for metadata and counts."""
    if not DB_PATH.exists():
        return None
    try:
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute(
            """
            SELECT
                COUNT(*) as total_events,
                MIN(invoked_at) as earliest,
                MAX(invoked_at) as latest
            FROM activations
            """
        ).fetchone()
        conn.close()
        if row:
            return {
                "total_events": row[0],
                "earliest": row[1],
                "latest": row[2],
            }
    except Exception:
        pass
    return None


def format_stats_table(data: list[dict]) -> str:
    """Format activation stats into an aligned ASCII table."""
    if not data:
        return "(no data)"

    # Column definitions
    cols = [
        ("Component", "name", 25),
        ("Type", "type", 10),
        ("Today", "today", 8),
        ("Weekly", "weekly", 8),
        ("Monthly", "monthly", 9),
        ("Yearly", "yearly", 8),
        ("All-Time", "all_time", 10),
    ]

    # Header
    lines = []
    header = " │ ".join(f"{col[0]:^{col[2]}}" for col in cols)
    sep = "─" * (len(header) + 6)
    lines.append("┌" + sep + "┐")
    lines.append("│ " + header + " │")
    lines.append("├" + sep + "┤")

    # Rows
    for row in data:
        cells = []
        for col_name, key, width in cols:
            val = row.get(key, "")
            if isinstance(val, int):
                cells.append(f"{val:>{width}}")
            else:
                cells.append(f"{str(val):<{width}}")
        lines.append("│ " + " │ ".join(cells) + " │")

    # Footer
    lines.append("└" + sep + "┘")
    return "\n".join(lines)


def run_stats_query(db_path: str, catalog: dict) -> list[dict]:
    """
    Execute DuckDB query against SQLite database.
    Returns list of dicts with activation counts per time horizon.
    """
    try:
        import duckdb
    except ImportError:
        print(
            "Error: duckdb not installed.\n"
            "Run with: uv run --script <this-script>\n"
            "Or install manually: pip install duckdb\n"
        )
        sys.exit(1)

    conn = duckdb.connect()
    conn.execute("INSTALL sqlite; LOAD sqlite;")
    conn.execute(f"ATTACH '{db_path}' AS spam (TYPE sqlite, READ_ONLY)")

    # Build catalog CTE values dynamically
    catalog_items = []
    for skill in catalog.get("skills", []):
        catalog_items.append((skill["name"], "skill"))
    for cmd in catalog.get("commands", []):
        catalog_items.append((cmd["name"], "command"))

    # Deduplicate and sort
    catalog_items = sorted(set(catalog_items))

    if not catalog_items:
        return []

    # Build VALUES clause
    values_list = ", ".join(
        f"('{name}', '{ctype}')" for name, ctype in catalog_items
    )

    query = f"""
    WITH catalog AS (
        VALUES {values_list}
        AS t(component_name, component_type)
    )
    SELECT
        c.component_name AS name,
        c.component_type AS type,
        COUNT(i.id) FILTER (WHERE DATE(i.invoked_at) = CURRENT_DATE)
            AS today,
        COUNT(i.id) FILTER (WHERE i.invoked_at >= CURRENT_DATE - INTERVAL '7 days')
            AS weekly,
        COUNT(i.id) FILTER (WHERE i.invoked_at >= CURRENT_DATE - INTERVAL '30 days')
            AS monthly,
        COUNT(i.id) FILTER (WHERE i.invoked_at >= CURRENT_DATE - INTERVAL '365 days')
            AS yearly,
        COUNT(i.id) AS all_time
    FROM catalog c
    LEFT JOIN spam.activations i
        ON c.component_name = i.component_name
        AND c.component_type = i.component_type
    GROUP BY c.component_name, c.component_type
    ORDER BY all_time DESC, name ASC
    """

    result = conn.execute(query).fetchall()
    conn.close()

    # Convert to list of dicts
    return [
        {
            "name": row[0],
            "type": row[1],
            "today": row[2],
            "weekly": row[3],
            "monthly": row[4],
            "yearly": row[5],
            "all_time": row[6],
        }
        for row in result
    ]


def get_detection_method_counts() -> dict:
    """Count activations by detection method."""
    if not DB_PATH.exists():
        return {}
    try:
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute(
            """
            SELECT detection_method, COUNT(*) as count
            FROM activations
            GROUP BY detection_method
            ORDER BY count DESC
            """
        ).fetchall()
        conn.close()
        return {method: count for method, count in rows}
    except Exception:
        return {}


def main():
    catalog = load_catalog()
    db_stats = get_db_stats()

    if db_stats is None:
        print("SPAM — Skill & Plugin Activations Monitor")
        print("=" * 40)
        print()
        print("No activation data collected yet.")
        print()
        print("To start tracking:")
        print("1. Install the spam plugin")
        print("2. Use any skill or command")
        print("3. Run /spam-stats again")
        print()
        return

    # Query stats
    stats = run_stats_query(str(DB_PATH), catalog)
    detection_counts = get_detection_method_counts()

    # Render report
    print("SPAM — Skill & Plugin Activations Monitor")
    print("=" * 40)
    print()

    skill_count = len(catalog.get("skills", []))
    cmd_count = len(catalog.get("commands", []))
    print(f"Catalog: {skill_count} skills, {cmd_count} commands")
    print(f"Database: {DB_PATH} ({db_stats['total_events']} events)")
    if db_stats.get("latest"):
        print(f"Latest activation: {db_stats['latest']}")
    print()

    # Stats table
    print(format_stats_table(stats))
    print()

    # Detection method summary
    if detection_counts:
        methods = ", ".join(
            f"{count} {method}" for method, count in sorted(
                detection_counts.items(),
                key=lambda x: -x[1],
            )
        )
        print(f"Detection methods: {methods}")
    print()


if __name__ == "__main__":
    main()
