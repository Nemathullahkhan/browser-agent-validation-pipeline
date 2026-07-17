# CLAUDE.md — Browser Agent + AgentTrust Demo

## Project Purpose

This is a **technical demonstration** showing how AgentTrust adds governance, observability, and policy enforcement to a LangChain Browser Agent with minimal code changes.

The Browser Agent is the example application. The real product being demonstrated is **AgentTrust**.

---

## Core Demo Question

> What changes when the exact same LangChain agent is executed with AgentTrust enabled?

The Browser Agent implementation must remain identical. Only AgentTrust middleware is added.

---

## Architecture Rule (Critical)

**BrowserAgent must never import AgentTrust.**

AgentTrust wraps the Browser Agent as middleware. The agent itself does no governance, validation, or logging — those are AgentTrust's sole responsibilities.

```
User → Browser Agent → AgentTrust Middleware → Governed Response
```

---

## Tech Stack

- **Python 3.11**, Pydantic v2, LangChain, langchain-ollama
- **LLM**: Local Ollama only (`qwen3:8b`, `llama3.1:8b`, or `mistral`) — no cloud LLMs
- **Browser tools**: DuckDuckGo Search, Requests, BeautifulSoup4, Trafilatura
- **AgentTrust SDK**: `agentrust-sdk[embedded,retry]`
- **CLI**: Typer + Rich
- **Testing**: pytest

---

## Project Structure

```
app/
  browser_agent/      # Search, browser, extraction, Ollama summarizer
  execution/          # ExecutionEngine, ExecutionContext, ExecutionTrace
  agenttrust/         # Middleware wrapping BrowserAgent
  models/             # Pydantic models
  policies/           # AgentTrust policy YAML files
  audit/              # AuditLogger, AuditEvent
  metrics/            # MetricsEngine
  comparison/         # Side-by-side comparison engine
  ui/                 # Rich/Typer CLI

tests/
demo.py
requirements.txt
```

---

## AgentTrust SDK — Critical Usage Rules

### embed_gateway() must be called BEFORE @harness

`@harness` captures `base_url` at decoration time. Call `embed_gateway()` first or every governance call will fail.

```python
# CORRECT
from agentrust_sdk import embed_gateway, harness
embed_gateway()                        # FIRST — starts gateway
@harness(agent_id="browser-agent")     # SECOND — captures correct URL
def run_agent(user: str, input: str) -> dict: ...

# WRONG — @harness locks in wrong URL
@harness(agent_id="browser-agent")
def run_agent(...): ...
embed_gateway()   # too late
```

### Three Integration Patterns

| Pattern | When to Use |
|---------|-------------|
| `@harness` decorator | Production — wraps the function that calls the chain |
| `auto_instrument()` | Zero code changes — patches `Runnable.invoke()` globally |
| `client.validate()` | Per-tool governance, dashboards, raw score access |

### ValidateResponse Key Fields

```python
r.approved                      # bool
r.blocked                       # bool
r.needs_review                  # bool
r.decision.outcome              # "approve" | "block" | "escalate"
r.decision.reason               # plain-English explanation
r.validation.final_confidence   # float 0–100
r.validation.policy_score       # float 0–100
r.risk.tier                     # "low" | "medium" | "high" | "critical"
r.validation.failures           # list[str] — violated rules
r.envelope_id                   # unique audit ID
```

### Policy Scoring

```
Start = 100 points
CRITICAL violation → score = 0 instantly (always blocks)
HIGH     violation → -25 points
MEDIUM   violation → -10 points
LOW      violation → -5  points

policy_score < 60 → BLOCK
confidence  < 50  → BLOCK
```

### Decision Thresholds

```
confidence >= 90                           → approve
policy_score >= 60 AND confidence >= 70    → approve
confidence < 50                            → block
policy_score < 60                          → block
risk == critical                           → escalate
```

---

## Engineering Constraints

### Architecture
- BrowserAgent must never import AgentTrust
- AgentTrust wraps BrowserAgent via middleware — not internal modification
- Components remain loosely coupled

### Design
- Dependency injection throughout
- Protocol or ABC interfaces
- SOLID principles
- Pydantic models for all data structures
- Strong typing throughout

### Observability
- Every execution step emits structured events
- Events power: execution traces, metrics, audit logs, comparison engine
- Every execution generates `trace.json`

### AgentTrust Middleware Intercepts
- User input
- Intermediate results (per-tool)
- Final response

### Audit
- Append-only `audit.jsonl`
- Local storage at `~/.agentrust/audit.jsonl`

---

## Demo Modes

**Mode A — Standard Browser Agent**: No governance, raw output

**Mode B — Browser Agent + AgentTrust**: Same agent + middleware = governed output

**Mode C — Comparison**: Run both, show side-by-side execution timelines

---

## BrowserResult Output Model

```python
class BrowserResult:
    summary: str
    sources: list[str]
    urls: list[str]
    latency: float
    token_usage: dict
```

---

## Failure Scenarios (Phase 10)

Each scenario runs twice (without / with AgentTrust):

1. Prompt Injection
2. Hallucinated Citation
3. Invalid URL
4. Low Confidence
5. Sensitive Data Leak

---

## AgentTrust Decisions

- `ALLOW` — output returned normally
- `BLOCK` — `BlockedError` raised
- `RETRY` — exponential backoff triggered
- `HUMAN_REVIEW` — escalated to review queue

---

## Environment Variables

```bash
AGENTRUST_ENABLED=true
AGENTRUST_GATEWAY_URL=http://localhost:8765   # set automatically by embed_gateway()
AGENTRUST_FAILURE_MODE=open                  # open | closed | queue
```

---

## Installation

```bash
pip install "agentrust-sdk[embedded,retry]"
pip install langchain langchain-core langchain-ollama
pip install duckduckgo-search requests beautifulsoup4 trafilatura
pip install typer rich pytest pydantic
```
