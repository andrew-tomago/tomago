# SPAM — Skill & Plugin Activations Monitor
## POC Architecture

> Scope: Internal architecture for the tracking and reporting system. Plugin packaging and distribution are out of scope for this document.

---

## Purpose

SPAM tracks activations of Claude Code skills and commands across all installed plugins. It persists activation events to a local SQLite database (stdlib — zero dependencies on the hot path) and surfaces temporal analytics via `/spam-stats` using DuckDB's SQLite scanner for query ergonomics: component-level counts across daily, weekly, monthly, yearly, and all-time horizons.

---

## The Detection Problem

Skills and commands are *semantic* events — Claude deciding to activate a capability. Hooks are *mechanical* — they intercept tool executions at defined lifecycle points. The core architectural challenge: reliably mapping mechanical signals to semantic events.

### The Skill Tool Signal

Skills are not activated by Claude reading SKILL.md files from disk. Claude Code exposes a dedicated `Skill` tool:

```
Skill
  Input: { skill: string, args?: string }   // e.g. "pdf", "xlsx", "spam-catalog"
```

Both model-invoked and user-invoked (`/skill-name`) activations flow through this tool. The call produces a `PostToolUse` event with `tool_name: "Skill"` and `tool_input.skill` set to the skill name. Detection is exact — no path matching or catalog cross-reference required.

### Command Signals

Commands have no equivalent dedicated tool. They activate in two ways:

**User-typed:** `/command-name` appears in the raw prompt. Captured by `UserPromptSubmit`.

**Programmatic / subagent:** A bash command invokes the underlying command script. Captured by `PostToolUse` on `Bash`, matched against known script paths from the catalog.

---

## Approach Comparison

Five detection strategies were evaluated. Each is assessed on coverage across four activation vectors, runtime characteristics, and implementation complexity.

### 1. Hooks (`PostToolUse` + `UserPromptSubmit`)

| Signal | On-demand skills | User commands | Programmatic commands | Preloaded subagent skills |
|---|---|---|---|---|
| Coverage | ✅ | ✅ | ✅ | ❌ |

Hooks are the only mechanism that fires deterministically on every relevant tool execution without requiring Claude to cooperate. The `Skill` matcher on `PostToolUse` provides exact skill detection. `UserPromptSubmit` provides exact command detection for user-typed activations. `Bash` matching on `PostToolUse` closes the programmatic gap for commands whose script paths are known in the catalog.

Runtime cost is ~2ms per event (Python startup + single-row SQLite INSERT). Well within the 30s default hook timeout. The script always exits 0 — tracking failures are silent and never block Claude.

The single blind spot is preloaded subagent skills. This is a structural limitation of the hook system, not a configuration issue. See dedicated section below.

### 2. Filesystem Watchers (FSEvents / inotify)

| Signal | On-demand skills | User commands | Programmatic commands | Preloaded subagent skills |
|---|---|---|---|---|
| Coverage | ⚠️ | ❌ | ❌ | ⚠️ |

A persistent background daemon watching skill directories for file reads. Theoretically catches any SKILL.md access regardless of activation mechanism.

Rejected on three grounds. It requires a persistent daemon — operational overhead that hooks avoid entirely. It provides zero coverage for commands, which have no filesystem signature at activation time. Preloaded subagent skills may be cached in memory after initial session load, meaning the daemon wouldn't see repeated accesses within a session.

### 3. Transcript Parsing (Batch)

| Signal | On-demand skills | User commands | Programmatic commands | Preloaded subagent skills |
|---|---|---|---|---|
| Coverage | ✅ | ✅ | ✅ | ✅ |

Claude Code persists session transcripts as JSONL. These contain the full tool call history — Skill tool calls, UserPromptSubmit payloads, Bash commands, and injected skill content for preloaded subagents. Parsing transcripts after the fact provides complete, ground-truth event data.

The limitation is timing: this is a batch process, not real-time. It cannot power live counters or mid-session queries. Its value is as a reconciliation layer that runs at `/spam-stats` time, filling gaps left by hooks. It is the only approach with complete coverage including preloaded subagent skills.

### 4. MCP Tracking Server

| Signal | On-demand skills | User commands | Programmatic commands | Preloaded subagent skills |
|---|---|---|---|---|
| Coverage | ⚠️ | ⚠️ | ⚠️ | ❌ |

An MCP server exposing a `track_activation()` tool that Claude calls after using a skill or command. Detection depends entirely on Claude deciding to call the tracking tool. Even with explicit instruction in every skill and command definition, activation is non-deterministic.

Rejected. Analytics infrastructure must not depend on LLM cooperation.

### 5. Embedded Tracking in SKILL.md

| Signal | On-demand skills | User commands | Programmatic commands | Preloaded subagent skills |
|---|---|---|---|---|
| Coverage | ⚠️ | N/A | N/A | ❌ |

Each SKILL.md includes an instruction to run a tracking script before proceeding. Tracking becomes a side effect of skill execution rather than an independent observation layer.

Rejected for the same non-determinism as MCP. It also pollutes every skill with infrastructure concerns and provides zero coverage for commands or preloaded skills.

### Summary

| Approach | Full Coverage | Real-Time | Requires Daemon | Depends on LLM | Complexity |
|---|---|---|---|---|---|
| Hooks | No (misses preloaded) | Yes | No | No | Low |
| Filesystem watchers | No | Yes | **Yes** | No | High |
| Transcript parsing | **Yes** | No | No | No | Medium |
| MCP server | No | Yes | No | **Yes** | Low |
| Embedded in SKILL.md | No | Yes | No | **Yes** | Invasive |

No single approach achieves full coverage at low complexity. The recommended architecture combines the two complementary approaches: hooks for real-time capture, transcript parsing for reconciliation.

---

## The Preloaded Subagent Skills Gap

When a subagent is spawned with preloaded skills, the full skill content is injected into the subagent's context at startup — bypassing the `Skill` tool entirely. No `PostToolUse` event fires. No hook runs. The skill is active and executing but invisible to any real-time detection mechanism.

This is expected behavior for subagent initialization, not an edge case or bug. It is a structural property of how preloaded subagents work: context injection at startup is faster and more reliable than requiring each subagent to invoke skills individually.

**Impact for SPAM:** Preloaded activations are a subset of total activations. For personal usage analytics, undercounting this subset is acceptable — the data is recoverable retroactively via transcript parsing, and the undercounting is bounded (only affects subagent-spawned skills, not interactive sessions). For billing or access-control use cases, this gap would be disqualifying. SPAM is analytics, not accounting.

**Mitigation path:** Transcript reconciliation. The JSONL transcripts record what actually happened in each session, including content injections for preloaded skills. The reconciler runs at `/spam-stats` time, scans recent transcripts for skill activations with no corresponding row in the `activations` table, and backfills them with `detection_method = 'transcript'`.

**Open item:** The exact JSONL structure for preloaded skill injection requires verification against real session data. On-demand Skill tool calls appear as standard `tool_use` blocks — confirmed. Preloaded injection may use a different event structure that needs to be identified empirically.

---

## Recommended Architecture

SQLite for writes, DuckDB for reads. Hooks write to SQLite via the stdlib `sqlite3` module — zero pip dependencies on the hot path. At `/spam-stats` time, DuckDB attaches the SQLite file read-only via its SQLite scanner and runs the analytical query with full DuckDB SQL ergonomics (`FILTER`, `INTERVAL`, `VALUES` CTEs).

```
┌──────────────────────────────────────────────────────────┐
│  Claude Code Session                                     │
│                                                          │
│  User types /command      ──► UserPromptSubmit hook       │
│  Claude invokes skill     ──► PostToolUse / Skill hook    │
│  Subagent runs bash       ──► PostToolUse / Bash hook     │
│  Subagent preloads skill  ──► (no hook — gap)            │
│                                                          │
│  Hooks ──► track.py ──► SQLite INSERT (stdlib)           │
│  Session ──► transcript JSONL persisted to disk           │
└──────────────────────────────────────────────────────────┘

  /spam-stats invoked
      │
      ├── catalog-builder.py    → filesystem scan → catalog.json
      ├── reconcile.py          → transcript parse → backfill gaps (sqlite3)
      └── spam-stats.py         → DuckDB ← SQLite scanner → render report
```

**Why split engines?** SQLite handles concurrent OLTP writes from multiple sessions natively — WAL mode, busy timeouts, auto-increment all work out of the box via the stdlib. DuckDB's strengths (columnar analytics, `FILTER` clauses, `INTERVAL` arithmetic) shine at query time but its single-writer model makes it unsuitable for concurrent hook writes from parallel Claude sessions. The SQLite scanner bridges both: writes stay fast and contention-safe; reads get DuckDB's query expressiveness.

---

## Component Specifications

### Data Layout

State lives outside the skill directory in a user-scoped location. This keeps data persistent across project switches and reinstalls.

```
~/.claude/spam/
├── activations.sqlite  # SQLite — the event store (written by hooks + reconciler)
└── catalog.json        # Rebuilt fresh on each /spam-stats activation
```

### Hook Configuration

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [{
          "type": "command",
          "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/track.py --event UserPromptSubmit",
          "timeout": 5
        }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Skill",
        "hooks": [{
          "type": "command",
          "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/track.py --event PostToolUse",
          "timeout": 5
        }]
      },
      {
        "matcher": "Bash",
        "hooks": [{
          "type": "command",
          "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/track.py --event PostToolUse",
          "timeout": 5
        }]
      }
    ]
  }
}
```

Three matchers total. `Skill` is the primary signal for skills — exact match, no false positives. `UserPromptSubmit` is the primary signal for user-typed commands. `Bash` is the secondary signal for programmatic command activation — it records a hit only if the bash command string contains a known command script path from the catalog. This prevents the `Bash` matcher from generating noise on every shell command Claude runs.

### track.py

The event capture script. Receives hook JSON on stdin. Extracts skill name directly from `tool_input.skill` for Skill events. Matches against catalog for command detection. Inserts into SQLite on match. Always exits 0.

Uses only stdlib modules (`json`, `sys`, `sqlite3`, `pathlib`) — no pip dependencies. This is critical: the hook fires on every matched tool call across every session. A missing pip dependency would silently break all tracking.

```python
#!/usr/bin/env python3
"""
Hook event capture for SPAM.
Receives hook JSON on stdin. Records matching activations to SQLite.
Always exits 0 — never blocks Claude.
"""
import json, sys, sqlite3
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
    event_type = event.get("type", "")

    # Skill: exact match via Skill tool
    if tool_name == "Skill":
        name = event.get("tool_input", {}).get("skill", "")
        if name:
            return {"name": name, "type": "skill", "method": "tool_call"}

    # Command: user-typed, detected via prompt text
    if event_type == "UserPromptSubmit":
        prompt = event.get("prompt", {}).get("text", "")
        for cmd in catalog.get("commands", []):
            if cmd["activation_pattern"] in prompt:
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
        INSERT INTO activations (component_name, component_type, detection_method)
        VALUES (?, ?, ?)
    """, [match["name"], match["type"], match["method"]])
    conn.commit()
    conn.close()

if __name__ == "__main__":
    try:
        event   = json.loads(sys.stdin.read())
        catalog = load_catalog()
        match   = detect(event, catalog)
        if match:
            record(match)
    except Exception:
        pass  # Silent failure — never block Claude
    sys.exit(0)
```

The `CREATE TABLE IF NOT EXISTS` in `record()` serves as the bootstrap mechanism. No separate initialization script needed — the table and data directory self-create on first activation.

### SQLite Schema (Event Store)

```sql
CREATE TABLE IF NOT EXISTS activations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    component_name    TEXT NOT NULL,
    component_type    TEXT NOT NULL
                      CHECK (component_type IN ('skill', 'command')),
    detection_method  TEXT NOT NULL
                      CHECK (detection_method IN ('tool_call', 'prompt_match', 'bash_match', 'transcript')),
    invoked_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_activations_time
    ON activations (invoked_at);

CREATE INDEX IF NOT EXISTS idx_activations_component
    ON activations (component_name, component_type);
```

`invoked_at` stores ISO 8601 timestamps as TEXT — SQLite's recommended approach for datetime. DuckDB's SQLite scanner auto-casts these to `TIMESTAMP` at read time, so the analytical queries use native temporal arithmetic.

`detection_method` is the key data quality column. It lets `/spam-stats` distinguish between high-confidence signals (`tool_call` — exact, zero false positives) and lower-confidence ones (`prompt_match` — substring-based, possible false positives). Reconciled entries from transcripts are tagged `transcript`.

### catalog-builder.py

Scans known skill and command locations to produce `catalog.json`. This is the reference list that `track.py` uses for command matching, and that `/spam-stats` uses to display zero-activation components.

**Scan targets:**

```
~/.claude/skills/                           # user-scoped skills
~/.claude/commands/                         # user-scoped commands
$CLAUDE_PROJECT_DIR/.claude/skills/         # project skills
$CLAUDE_PROJECT_DIR/.claude/commands/       # project commands
~/.claude/plugins/*/skills/                 # plugin skills
~/.claude/plugins/*/commands/               # plugin commands
```

**Output structure:**

```json
{
  "generated_at": "2026-01-31T12:00:00",
  "skills": [
    {
      "name": "spam-catalog",
      "source": "plugin:spam",
      "skill_md_path": "/Users/andrew/.claude/plugins/spam/skills/spam-catalog/SKILL.md"
    }
  ],
  "commands": [
    {
      "name": "spam-stats",
      "source": "plugin:spam",
      "activation_pattern": "/spam-stats",
      "script_path": "/Users/andrew/.claude/plugins/spam/scripts/spam-stats.py"
    }
  ]
}
```

`source` tracks which plugin (or user/project scope) each component came from. This enables per-plugin aggregation in the stats output.

### reconcile.py

Runs at `/spam-stats` time, **before** the stats query. Parses recent session transcripts for skill activations — particularly preloaded subagent skills — that have no corresponding row in `activations`. Backfills missing entries with `detection_method = 'transcript'`.

Uses `sqlite3` (stdlib) for both the dedup check and backfill writes. This keeps the reconciler on the same engine as `track.py` and avoids DuckDB write contention.

```python
#!/usr/bin/env python3
"""
Transcript reconciliation for SPAM.
Finds skill activations in session transcripts not captured by hooks.
Backfills into activations with detection_method = 'transcript'.
"""
import json, sqlite3
from pathlib import Path
from datetime import datetime

DATA_DIR       = Path.home() / ".claude" / "spam"
DB_PATH        = DATA_DIR / "activations.sqlite"
TRANSCRIPT_DIR = Path.home() / ".claude" / "logs"  # verify path

def extract_skill_events(transcript_dir: Path) -> list[dict]:
    """Pull Skill tool_use events from JSONL transcripts."""
    events = []
    for f in sorted(transcript_dir.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            try:
                row = json.loads(line)
                if row.get("type") == "tool_use" and row.get("name") == "Skill":
                    events.append({
                        "name":      row["input"].get("skill", ""),
                        "timestamp": row.get("timestamp", datetime.now().isoformat())
                    })
                # TODO: add detection pattern for preloaded skill injection
                # once transcript format is verified empirically
            except json.JSONDecodeError:
                continue
    return events

def backfill(events: list[dict]):
    """Insert events that lack a matching row in activations."""
    conn = sqlite3.connect(str(DB_PATH), timeout=1.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 500")
    for ev in events:
        # Deduplicate: check for existing record within a 1-second window
        row = conn.execute("""
            SELECT COUNT(*) FROM activations
            WHERE component_name = ?
              AND component_type = 'skill'
              AND invoked_at BETWEEN datetime(?, '-1 second')
                                 AND datetime(?, '+1 second')
        """, [ev["name"], ev["timestamp"], ev["timestamp"]]).fetchone()

        if row[0] == 0:
            conn.execute("""
                INSERT INTO activations
                    (component_name, component_type, detection_method, invoked_at)
                VALUES (?, 'skill', 'transcript', ?)
            """, [ev["name"], ev["timestamp"]])
    conn.commit()
    conn.close()

if __name__ == "__main__":
    if TRANSCRIPT_DIR.exists() and DB_PATH.exists():
        events = extract_skill_events(TRANSCRIPT_DIR)
        if events:
            backfill(events)
```

The 1-second deduplication window prevents double-counting events that were already captured by hooks. It's intentionally tight — hook-captured events have sub-second timestamp precision, so a 1-second window is sufficient to match without risk of collapsing genuinely separate activations.

### Stats Query

At `/spam-stats` time, `spam-stats.py` uses DuckDB to attach the SQLite file read-only and run the analytical query. DuckDB's SQLite scanner handles type coercion (TEXT timestamps → TIMESTAMP) automatically.

```python
# spam-stats.py setup (illustrative)
import duckdb

conn = duckdb.connect()  # in-memory — no DuckDB file on disk
conn.execute("INSTALL sqlite; LOAD sqlite;")
conn.execute(f"ATTACH '{db_path}' AS spam (TYPE sqlite, READ_ONLY)")
```

```sql
WITH catalog AS (
    -- Generated programmatically from catalog.json.
    -- The VALUES clause below is illustrative; spam-stats.py builds this dynamically.
    VALUES
        ('spam-catalog', 'skill'),
        ('spam-stats',   'command')
    AS t(component_name, component_type)
)
SELECT
    c.component_name,
    c.component_type,
    COUNT(i.id) FILTER (WHERE i.invoked_at >= CURRENT_DATE)                        AS today,
    COUNT(i.id) FILTER (WHERE i.invoked_at >= CURRENT_DATE - INTERVAL '7 days')    AS weekly,
    COUNT(i.id) FILTER (WHERE i.invoked_at >= CURRENT_DATE - INTERVAL '30 days')   AS monthly,
    COUNT(i.id) FILTER (WHERE i.invoked_at >= CURRENT_DATE - INTERVAL '365 days')  AS yearly,
    COUNT(i.id)                                                                     AS all_time
FROM catalog c
LEFT JOIN spam.activations i
    ON  c.component_name = i.component_name
    AND c.component_type = i.component_type
GROUP BY c.component_name, c.component_type
ORDER BY all_time DESC;
```

The LEFT JOIN ensures zero-activation components appear in the output. The `catalog` CTE is generated at query time from `catalog.json` — not hardcoded. This means newly installed skills and commands appear in the next stats run even if they have no activation history yet.

Note the `spam.activations` qualified table name — the SQLite database is attached under the `spam` schema, keeping it separate from DuckDB's in-memory default schema.

---

## Concurrency

Multiple Claude Code sessions may run simultaneously, each firing hooks that write to the same SQLite file. Three mitigations handle this without application-level retry logic:

**WAL mode.** Readers don't block writers. Enabled via `PRAGMA journal_mode=WAL` on every connection open. Once set, WAL mode persists across connections — the PRAGMA is idempotent.

**Busy timeout.** `PRAGMA busy_timeout = 500` tells SQLite to wait up to 500ms for a write lock before returning `SQLITE_BUSY`. Concurrent INSERTs from parallel sessions queue briefly rather than failing immediately.

**Single-row INSERTs.** No transaction batching. Each hook activation writes exactly one row and commits. Lock hold time is sub-millisecond per write — contention window is minimal.

SQLite's concurrency model is well-matched to this workload: many short writes from independent processes, infrequent reads at stats-query time. DuckDB only touches the file read-only at `/spam-stats` time, after the reconciler has finished writing — no cross-engine write contention.

---

## Dependencies

| Component | Engine | Install Required |
|-----------|--------|-----------------|
| track.py (hot path) | sqlite3 | No — Python stdlib |
| reconcile.py | sqlite3 | No — Python stdlib |
| spam-stats.py (query time) | duckdb | No — managed by `uv run` via PEP 723 |
| catalog-builder.py | N/A (filesystem only) | No |

The `duckdb` pip dependency is isolated to the `/spam-stats` read path. If DuckDB is unavailable, a fallback pure-SQLite stats query is feasible (replace `FILTER` with `SUM(CASE WHEN ...)` and `INTERVAL` with `date()`/`julianday()` arithmetic). Not implemented unless needed.

---

## Open Items

**Transcript format verification.** The exact JSONL structure for preloaded subagent skill injection needs confirmation against real session data. On-demand Skill tool calls appear as standard `tool_use` blocks — confirmed. The preloaded injection pattern is the open item that determines whether `reconcile.py` can fully close the preloaded subagent gap.

**Transcript location.** `~/.claude/logs/` is assumed. The actual path should be discovered programmatically — it may vary by installation or configuration.

**`$CLAUDE_PLUGIN_ROOT` environment variable.** The hook configuration references this variable for script paths. Verify it is set by Claude Code at hook execution time. If not, an alternative path resolution strategy is needed (absolute paths, or a relative path from a known anchor).

**Command detection precision.** `prompt_match` uses substring matching against activation patterns. A user typing `/spam-stats is great` triggers detection even without invoking the command. For personal analytics this is acceptable noise. Tighten to word-boundary or end-of-token matching if false positives become meaningful.

**Catalog staleness.** `catalog.json` is rebuilt at `/spam-stats` time. Components installed between two stats runs have no tracking data for that interval. Expected behavior — the catalog is a snapshot, not a live index.
