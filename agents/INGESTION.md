# Silicon Mind — Agent Internal-Brain Ingestion

gr0b's session-log hooks only capture what an agent *writes out*. Each agent
also keeps an **internal brain** locked in its own config dirs — Claude Code's
`~/.claude/projects/*.jsonl`, Cowork's local session transcripts, Gemini's
`~/.gemini`, Codex's `~/.codex`. Silicon Mind ingests those into the shared
brain — **decisions and lessons only, never raw transcripts**, junk-filtered at
the gate, **opt-in per agent**.

## Consent is the whole design

These stores are private. Nothing is read unless you explicitly opt in. In
`gr0b.config.yaml`:

```yaml
ingest:
  queue: "~/.gr0b/ingest-queue"
  sources:
    claude_code_jsonl: true          # ~/.claude/projects/*.jsonl
    claude_cowork_transcripts: true  # Cowork sessions via session_info MCP
    claude_memories: false
    gemini_internal: false
    codex_internal: false
```

`gr0b_ingest.py` **refuses to run** for any source not set to `true`. A missing
flag is treated as `false`. This is the line that makes the project safe to open
source: a fork's brain stays empty until its owner flips a flag for a store they
own.

## Three filters at the gate

Nothing reaches the shared brain without passing all three:

1. **Junk filter** — boilerplate/spam sessions (the ~60 "Analyze this codebase
   for security vulnerabilities" template runs, warmups, bare "test"/"hi") are
   dropped whole, before any line is read.
2. **Privacy filter** — sessions whose framing signals personal / wellbeing /
   therapeutic content (`psychology`, `therapy`, `vulnerable`, `my mental…`,
   personal journals/protocols) are a **hard skip**, same tier as junk, *even
   when the agent source is opted in*. Technical decisions are fair game; a
   person's inner life is not.
3. **Line filter** — within a surviving session, only lines that carry a
   decision, root cause, or lesson are kept (`decided`, `root cause`, `the bug
   was`, `never/always`, `instead of`, `switched to`, …), and assistant sign-off
   theater ("standing ready", "mission accomplished") is stripped. Capped at 12
   lines/session, deduped.

## Architecture: extract → queue → commit

Extraction and memory-writing are **decoupled** on purpose.

```
  internal store ──extract──▶ ~/.gr0b/ingest-queue/*.md ──commit──▶ agentmemory
   (host files)   gr0b_ingest.py   (inspectable cards)    MCP / daily task   (+ done/)
```

- **EXTRACT** (`gr0b_ingest.py`, runs on the host where the files live): reads
  the store, applies the three filters, writes **one markdown card per session**
  to `ingest-queue/`. Each card has YAML front-matter (source, session_id,
  project, timestamps) and a `## Decisions & lessons` bullet list.
- **COMMIT** (any MCP client, or the daily Cowork task): drains the queue into
  agentmemory via `memory_save`, then archives cards to `ingest-queue/done/`.

Why a queue instead of writing memory directly? It is **inspectable** (you can
read exactly what will enter the brain before it does — consent + audit), it
**survives agentmemory downtime**, and extraction can run anywhere the files are
readable even if the memory daemon is elsewhere.

State (which sessions are already processed) lives in `~/.gr0b/.ingest_state.json`
so re-runs are idempotent — only new sessions produce new cards.

## Per-agent adapters

| Source | Adapter | How it reads |
|---|---|---|
| `claude_code_jsonl` | `gr0b_ingest.py --agent claude-code` | parses `~/.claude/projects/**/*.jsonl`, one session per file |
| `claude_cowork_transcripts` | daily Cowork task (MCP) | `session_info.list_sessions` + `read_transcript`, distilled via `memory_save` |
| `claude_memories` | *(not built — flag off)* | — |
| `gemini_internal` | *(not built — flag off)* | — |
| `codex_internal` | *(not built — flag off)* | — |

Cowork transcripts are not host files — they come through the `session_info`
MCP — so that adapter lives in the daily scheduled task rather than this script.
The same three filters apply (the script's `JUNK_PROMPT_RE` / `PRIVATE_PROMPT_RE`
are the shared reference implementation).

## Usage

```bash
# Extract Claude Code jsonl → queue
python3 ~/.gr0b/scripts/gr0b_ingest.py --agent claude-code

# Purge the legacy spam sessions from a previous unfiltered import
python3 ~/.gr0b/scripts/gr0b_ingest.py --purge-spam          # dry run
python3 ~/.gr0b/scripts/gr0b_ingest.py --purge-spam --apply  # delete

# Inspect state and the pending queue
python3 ~/.gr0b/scripts/gr0b_ingest.py --status
```

## Inherited follow-ups

- `gr0b_doctor.py` should learn to detect a re-polluted memory store (spam
  signature) the way it now detects the three diseases fixed on 2026-06-12.
- Gemini / Codex adapters remain unbuilt by design — wire them only when their
  owner opts in and their store format is mapped.
