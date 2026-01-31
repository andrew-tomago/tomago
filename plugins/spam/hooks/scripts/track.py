#!/usr/bin/env python3
# created: 2026-01-31
# created_by:
#   agent: Claude Code 2.1.27
#   model: claude-opus-4-5-20251101
"""
Hook event capture for SPAM.
Receives hook JSON on stdin. Records matching activations to SQLite.
Always exits 0 — never blocks Claude.
"""
from __future__ import annotations
import json, sys, sqlite3, argparse
from pathlib import Path

DATA_DIR  = Path.home() / ".claude" / "spam"
CATALOG   = DATA_DIR / "catalog.json"
DB_PATH   = DATA_DIR / "activations.sqlite"

def load_catalog() -> dict:
    if not CATALOG.exists():
        return {"commands": []}
    return json.loads(CATALOG.read_text())

def detect(event: dict, catalog: dict) -> dict | None:
    tool_name  = event.get("tool_name", "")

    # Skill: exact match via Skill tool
    if tool_name == "Skill":
        name = event.get("tool_input", {}).get("skill", "")
        if name:
            return {"name": name, "type": "skill", "method": "tool_call"}

    # Command: user-typed, detected via prompt text
    if event.get("type") == "UserPromptSubmit" or "--event" in sys.argv and "UserPromptSubmit" in sys.argv:
        prompt = event.get("prompt", {})
        if isinstance(prompt, str):
            text = prompt
        else:
            text = prompt.get("text", "") if isinstance(prompt, dict) else ""
        for cmd in catalog.get("commands", []):
            if cmd.get("activation_pattern", "") and cmd["activation_pattern"] in text:
                return {"name": cmd["name"], "type": "command", "method": "prompt_match"}

    # Command: programmatic, detected via bash command string
    if tool_name == "Bash":
        cmd_str = event.get("tool_input", {}).get("command", "")
        for cmd in catalog.get("commands", []):
            script_path = cmd.get("script_path", "")
            if script_path and script_path in cmd_str:
                return {"name": cmd["name"], "type": "command", "method": "bash_match"}

    return None

def record(match: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=1.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 500")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activations (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            component_name    TEXT NOT NULL,
            component_type    TEXT NOT NULL
                              CHECK (component_type IN ('skill', 'command')),
            detection_method  TEXT NOT NULL
                              CHECK (detection_method IN ('tool_call', 'prompt_match', 'bash_match', 'transcript')),
            invoked_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_activations_time
            ON activations (invoked_at)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_activations_component
            ON activations (component_name, component_type)
    """)
    conn.execute("""
        INSERT INTO activations (component_name, component_type, detection_method)
        VALUES (?, ?, ?)
    """, [match["name"], match["type"], match["method"]])
    conn.commit()
    conn.close()

if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("--event", required=True)
        args = parser.parse_args()

        event = json.loads(sys.stdin.read())
        catalog = load_catalog()
        match = detect(event, catalog)
        if match:
            record(match)
    except Exception:
        pass  # Silent failure — never block Claude
    sys.exit(0)
