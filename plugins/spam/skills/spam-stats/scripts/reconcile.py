#!/usr/bin/env python3
# created: 2026-01-31
# created_by:
#   agent: Claude Code 2.1.27
#   model: claude-opus-4-5-20251101
"""
Transcript reconciliation for SPAM.
Finds skill activations in session transcripts not captured by hooks.
Backfills into activations with detection_method = 'transcript'.

Stdlib only — no pip dependencies.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path.home() / ".claude" / "spam"
DB_PATH = DATA_DIR / "activations.sqlite"
TRANSCRIPT_DIR = Path(
    os.environ.get("SPAM_TRANSCRIPT_DIR", str(Path.home() / ".claude" / "projects"))
)

# TODO: Verify transcript directory path empirically. The actual location may
# differ from ~/.claude/projects/ — check ~/.claude/logs/ as an alternative.


def extract_skill_events(transcript_dir: Path) -> list[dict]:
    """Pull Skill tool_use events from JSONL transcripts."""
    events: list[dict] = []
    if not transcript_dir.is_dir():
        return events

    for f in sorted(transcript_dir.rglob("*.jsonl")):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Standard Skill tool_use events
            if row.get("type") == "tool_use" and row.get("name") == "Skill":
                skill_name = row.get("input", {}).get("skill", "")
                if skill_name:
                    events.append({
                        "name": skill_name,
                        "timestamp": row.get(
                            "timestamp",
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    })

            # TODO: Add detection pattern for preloaded skill injection
            # once transcript format is verified empirically.

    return events


def backfill(events: list[dict]) -> int:
    """Insert events that lack a matching row in activations.

    Returns count of backfilled rows.
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=1.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 500")

    inserted = 0
    for ev in events:
        # Deduplicate: check for existing record within a 1-second window
        count = conn.execute(
            """
            SELECT COUNT(*) FROM activations
            WHERE component_name = ?
              AND component_type = 'skill'
              AND invoked_at BETWEEN datetime(?, '-1 second')
                                 AND datetime(?, '+1 second')
            """,
            [ev["name"], ev["timestamp"], ev["timestamp"]],
        ).fetchone()[0]

        if count == 0:
            conn.execute(
                """
                INSERT INTO activations
                    (component_name, component_type, detection_method, invoked_at)
                VALUES (?, 'skill', 'transcript', ?)
                """,
                [ev["name"], ev["timestamp"]],
            )
            inserted += 1

    conn.commit()
    conn.close()
    return inserted


def main():
    if not DB_PATH.exists():
        print("No activation database — nothing to reconcile.")
        return
    if not TRANSCRIPT_DIR.exists():
        print(f"Transcript dir not found: {TRANSCRIPT_DIR}")
        return

    events = extract_skill_events(TRANSCRIPT_DIR)
    if not events:
        print("No transcript events found.")
        return

    inserted = backfill(events)
    print(f"Reconciled: {len(events)} transcript events, {inserted} backfilled.")


if __name__ == "__main__":
    main()
