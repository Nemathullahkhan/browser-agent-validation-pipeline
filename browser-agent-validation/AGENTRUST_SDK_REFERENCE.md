# AgentTrust SDK — Complete Reference

## What It Is

AgentTrust is a runtime governance platform for AI agents. It sits between your agent's LLM output and any real-world action, answers "Is this safe to act on?", and enforces a policy decision before the caller gets the result.

Every validation produces one of four outcomes:

| Outcome  | Effect                                    |
|----------|-------------------------------------------|
| approve  | Result returned to caller normally        |
| block    | BlockedError raised (if block_on_block=True) |
| escalate | Routes to human review queue              |
| retry    | Exponential backoff triggered             |

---

## Installation

```bash
pip install "agentrust-sdk"                    # Core only (schema validation, OSS mode)
pip install "agentrust-sdk[embedded,retry]"    # + in-process SQLite gateway + retry backoff
pip install "agentrust-sdk[langchain]"         # + LangChain adapter
pip install "agentrust-sdk[langgraph]"         # + LangGraph node adapter
pip install "agentrust-sdk[crewai]"            # + CrewAI callback adapter
pip install "agentrust-sdk[full]"              # Everything
```

---

## Three Deployment Modes

| Mode             | What Runs                                      | When to Use                    |
|------------------|------------------------------------------------|--------------------------------|
| OSS (no API key) | In-process schema validation only              | Dev / open-source / unit tests |
| Embedded Gateway | FastAPI + SQLite in a background thread        | Single-machine apps, demos, CI |
| Full Gateway     | Docker / Helm with Postgres + Redis + LLM judge | Production                    |

---

## Key Imports

```python
from agentrust_sdk import (
    harness,               # @harness decorator — primary integration method
    validate,              # alias for harness
    embed_gateway,         # starts in-process SQLite gateway
    EmbeddedGateway,
    AgentTrustClient,      # sync HTTP client
    AsyncAgentTrustClient, # async HTTP client
    BlockedError,          # raised on block (has .reason, .envelope_id, .outcome)
    TierGateError,         # raised on capability above your tier
    GatewayUnavailableError,
    auto_instrument,       # zero-code framework patching
    auto_wrap,             # wraps a single compiled LangGraph instance
    Tier, Capability,      # enums for tier/capability checks
    is_allowed,
    SDK_CONFIG,            # env-var config singleton
    WebhookDispatcher,     # webhook notifications (Team tier+)
    drain_queue,           # replay buffered requests (queue mode)
)
```

---

## CRITICAL ORDERING RULE

`embed_gateway()` must be called **before** any `@harness` decorator is evaluated.

`@harness` captures `base_url` at decoration time. If `embed_gateway()` runs after, `@harness` silently locks in `http://localhost:8000` (the default) and every governance call fails with Connection refused.

```python
# CORRECT
from agentrust_sdk import embed_gateway, harness

embed_gateway()   # ← FIRST: starts gateway, sets AGENTRUST_GATEWAY_URL env var

@harness(agent_id="my-agent")    # ← SECOND: captures the now-correct URL
def my_agent(user: str, input: str) -> dict:
    ...

# WRONG
@harness(agent_id="my-agent")   # captures http://localhost:8000 — wrong
def my_agent(...): ...

embed_gateway()                  # too late
```

---

## LangChain Integration — Three Patterns

### Pattern A — `@harness` Decorator (Recommended for Production)

`@harness` wraps the function that calls your chain, not the chain itself. The chain runs unchanged; `@harness` intercepts the dict returned by your wrapper and validates it against policy before passing it back to the caller.

```python
import os
os.environ["AGENTRUST_GATEWAY_URL"] = "http://localhost:8765"  # or use embed_gateway()

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from agentrust_sdk import embed_gateway, harness, BlockedError

embed_gateway()   # MUST come before @harness

llm    = ChatOpenAI(model="gpt-4o-mini", temperature=0)
prompt = ChatPromptTemplate.from_template("Answer the question: {topic}")
chain  = prompt | llm | StrOutputParser()

# Pattern A: wrap the chain-calling function
@harness(
    agent_id="research-agent",   # drives which policy YAML activates
    block_on_block=True,         # raise BlockedError if outcome == "block"
    block_on_review=False,       # don't raise on escalate (default)
)
def run_research_chain(user: str, input: str) -> dict:
    result = chain.invoke({"topic": input})   # chain runs here — unchanged
    return {                                   # THIS dict is what gets validated
        "answer":  result,
        "sources": ["nist.gov/ai-rmf"],
        "model":   "gpt-4o-mini",
        "status":  "success",
    }

try:
    result = run_research_chain(user="alice", input="What is AI safety?")
    print(result["answer"])
except BlockedError as e:
    print(f"Blocked: {e.reason}")
    print(f"Audit ID: {e.envelope_id}")
```

#### How `@harness` execution flows

```
run_research_chain(user="alice", input="...")
  │
  ├── 1. Function body runs → chain.invoke() executes
  ├── 2. Function returns {"answer": "...", "status": "success", ...}
  ├── 3. @harness intercepts the return dict
  ├── 4. client.validate(agent_id="research-agent", output={...})
  │       → ValidationEngine: schema, tool-trust, policy, consistency, grounding
  │       → ConfidenceEngine: weighted 0–100%
  │       → RiskEngine: action × impact × gap × sensitivity
  │       → DecisionEngine: approve / block / escalate
  ├── 5a. outcome="approve" → dict returned to caller normally
  └── 5b. outcome="block"   → BlockedError raised, dict suppressed
```

`@harness` validates the dict you **RETURN**, not the raw LLM string. This means you can add required business fields (`amount`, `currency`, `transaction_id`) inside your wrapper before validation evaluates them.

---

### Domain policy activation via `agent_id`

| agent_id pattern          | Policies applied                      |
|---------------------------|---------------------------------------|
| payment-*, billing-*, invoice-* | base.yaml + financial.yaml (PCI-DSS) |
| patient-*, medical-*, ehr-*     | base.yaml + medical.yaml (HIPAA)     |
| price-comparison-agent          | base.yaml + your price_agent.yaml    |
| Anything else                   | base.yaml only                       |

---

### Pattern B — `auto_instrument()` (Zero Code Changes)

Patches LangChain's `Runnable.invoke()` globally. Every subsequent `chain.invoke()` call is governed automatically — no decorator or wrapper needed.

```python
from agentrust_sdk import embed_gateway, auto_instrument

embed_gateway()

patched = auto_instrument(
    agent_id="langchain-auto",
    langchain=True,
    openai=False,    # don't patch OpenAI SDK
    langgraph=False, # don't patch LangGraph
)
print(f"Patched: {patched}")  # ['langchain_core.runnables.base.Runnable.invoke']

# All chain.invoke() calls from here forward are automatically governed
result = chain.invoke({"topic": "EU AI Act risk classification"})
```

#### What `auto_instrument()` actually patches

| Framework          | What Gets Patched                                           |
|--------------------|-------------------------------------------------------------|
| LangChain (LCEL)   | `langchain_core.runnables.base.Runnable.invoke()`           |
| LangChain (Legacy) | `langchain.llms.base.BaseLLM.predict()` + `Chain.__call__()` |
| OpenAI SDK         | `openai.chat.completions.create()` (sync + async)           |
| LangGraph          | `CompiledStateGraph.invoke()` / `ainvoke()`                 |

**When to use Pattern B:**

- Wrapping an existing LangChain app with zero code changes
- Monitoring/advisory mode during initial rollout
- Prototyping before adding explicit `@harness` in production

**Caveat:** Global patching can have side effects in complex apps with many chains. `@harness` is clearer and more auditable in production.

---

### Pattern C — `client.validate()` (Full Control)

You call `chain.invoke()` yourself and pass the output to `client.validate()`. Returns the full `ValidateResponse` object with every score and failure detail.

```python
from agentrust_sdk import embed_gateway, AgentTrustClient

embed_gateway()
client = AgentTrustClient()  # auto-resolves tier from AGENTRUST_KEY

chain_output = chain.invoke({"topic": "Transfer $500"})

r = client.validate(
    agent_id  = "payment-processor",
    user      = "alice",
    input     = "Transfer $500 to account XYZ",
    output    = {
        "chain_output": chain_output,
        "status": "ok",
        "account": "4929-XXXX",
        # missing: amount, currency — financial.yaml will catch this
    },
    framework = "LangChain",
    model     = "gpt-4o-mini",
    latency_ms = 1240.0,
    tokens    = 512,
    metadata  = {"correlation_id": "cid-abc-123"},  # for trace correlation
)

# Inspect every score
print(f"Outcome:     {r.decision.outcome}")          # "approve" | "block" | "escalate"
print(f"Reason:      {r.decision.reason}")
print(f"Confidence:  {r.validation.final_confidence:.1f}%")
print(f"Policy:      {r.validation.policy_score:.0f}/100")
print(f"Risk tier:   {r.risk.tier}")                 # "low" | "medium" | "high" | "critical"
print(f"Failures:    {r.validation.failures}")        # list of violated rules
print(f"Envelope ID: {r.envelope_id}")               # unique audit ID

if r.blocked:
    raise ValueError(f"Governance blocked: {r.decision.reason}")
elif r.needs_review:
    send_to_human_review_queue(r)
else:
    execute_action(chain_output)
```

**Use Pattern C when:**

- Building dashboards or monitoring tools (need raw scores)
- Writing governance unit tests for chain outputs
- Doing per-tool governance inside an AgentExecutor (see LangChain Price Agent below)
- Handling block and escalate differently in your business logic

---

### Pattern A — Advisory Mode (Observe Before Enforcing)

During initial rollout, set `block_on_block=False` to log violations without raising:

```python
@harness(agent_id="payment-processor", block_on_block=False)
def run_payment_advisory(user: str, input: str) -> dict:
    result = chain.invoke({"topic": input})
    return {"status": "ok", "invoice": "INV-001", "note": result}

# Violations are logged to audit trail but result is still returned — no exception raised
result = run_payment_advisory(user="alice", input="Process payment")
# Switch to block_on_block=True in production
```

---

## LangChain Price Agent — Real-World Integration

This is the full pattern for per-tool governance inside a LangChain AgentExecutor using Pattern C with `correlation_id` for trace correlation.

### Project Structure

```
examples/langchain_price_agent/
├── agent/
│   ├── tools.py                # fetch_html, extract_price, compare_prices
│   ├── build_agent.py          # AgentExecutor + LangChain tools
│   └── callback_handler.py     # ExecutionTraceHandler with correlation_id logging
├── runs/
│   ├── run_a_unmonitored.py    # Baseline — no governance
│   └── run_b_agenttrust.py     # AgentTrust per-tool + final-output governance
├── policy/
│   └── price_agent.yaml        # Custom policy rules for this agent
├── analysis/
│   └── compare_runs.py         # Join traces on correlation_id, produce report
└── logs/
    ├── execution_trace.jsonl   # Tool timings + reasoning (from callback handler)
    └── governance_trace.jsonl  # ValidateResponse per tool call
```

### Step 1 — Custom Policy YAML

Create `policy/price_agent.yaml`. The `patterns` field determines which `agent_id` values activate these rules:

```yaml
meta:
  id: price-agent
  version: "1.0"
  description: "Rules for the LangChain price-comparison agent"
  patterns:
    - "price-comparison-agent"   # activates for agent_id="price-comparison-agent"

rules:
  - id: output_cheaper_site_present
    severity: high
    target: output.cheaper_site
    op: exists
    effect: deny

  - id: output_price_a_present
    severity: high
    target: output.price_a
    op: exists
    effect: deny

  - id: approved_domains_only
    severity: critical
    target: output.domains_used
    op: not_in_list
    value: ["evil.com", "shadow-site.net"]
    effect: deny

  - id: large_price_difference_review
    severity: medium
    target: output.difference
    op: lte
    value: 50.0
    effect: review                # escalate (not block) when difference > $50
```

### Step 2 — Callback Handler with `correlation_id`

```python
# agent/callback_handler.py
import json, time, uuid
from collections import defaultdict
from langchain.callbacks.base import BaseCallbackHandler

class ExecutionTraceHandler(BaseCallbackHandler):
    def __init__(self, run_id: str, log_path: str = "logs/execution_trace.jsonl"):
        self.run_id = run_id
        self.log_path = log_path
        self._pending: dict[int, str] = {}
        self._call_counter = defaultdict(int)

    def correlation_id_for(self, tool_name: str) -> str:
        key = self._call_counter[tool_name] - 1
        return self._pending.get(key, str(uuid.uuid4()))

    def _write(self, record: dict):
        record.update({"run_id": self.run_id, "timestamp": time.time()})
        with open(self.log_path, "a") as f:
            f.write(json.dumps(record) + "\n")

    def on_tool_start(self, serialized, input_str, **kwargs):
        cid = str(uuid.uuid4())
        name = serialized.get("name", "")
        serial = self._call_counter[name]
        self._call_counter[name] += 1
        self._pending[serial] = cid
        self._write({"event": "tool_start", "tool": name, "input": input_str,
                     "correlation_id": cid})

    def on_tool_end(self, output, **kwargs):
        tool_name = kwargs.get("name", list(self._call_counter.keys())[-1])
        serial = self._call_counter[tool_name] - 1
        cid = self._pending.get(serial, str(uuid.uuid4()))
        self._write({"event": "tool_end", "tool": tool_name, "output": str(output),
                     "correlation_id": cid})
```

`correlation_id` is the join key — generated at `tool_start`, carried through `tool_end`, and written into every `ValidateResponse` in the governance trace so the two logs can be joined.

### Step 3 — Run B: Per-Tool Governance (Pattern C)

```python
# runs/run_b_agenttrust.py
import uuid, json, time, os
from agentrust_sdk import embed_gateway, AgentTrustClient, BlockedError

gw     = embed_gateway()      # MUST be first
client = AgentTrustClient()

from agent.build_agent import agent_executor
from agent.callback_handler import ExecutionTraceHandler

AGENT_ID = "price-comparison-agent"
run_id   = str(uuid.uuid4())
handler  = ExecutionTraceHandler(run_id=run_id)

# Monkey-patch on_tool_end to intercept each tool output and call client.validate()
_orig_on_tool_end = handler.on_tool_end

def _governed_on_tool_end(output, **kwargs):
    tool_name = kwargs.get("name", "unknown")
    serial    = handler._call_counter.get(tool_name, 1) - 1
    cid       = handler._pending.get(serial, str(uuid.uuid4()))

    try:
        tool_output = json.loads(output) if isinstance(output, str) else output
    except Exception:
        tool_output = {"raw": str(output)}

    r = client.validate(
        agent_id  = AGENT_ID,
        user      = "qa-runner",
        input     = f"tool_call:{tool_name}",
        output    = tool_output,
        framework = "LangChain",
        metadata  = {"correlation_id": cid, "run_id": run_id},
    )

    # Write governance trace for later join analysis
    with open("logs/governance_trace.jsonl", "a") as f:
        f.write(json.dumps({
            "event":            "tool_governance",
            "tool":             tool_name,
            "correlation_id":   cid,
            "run_id":           run_id,
            "timestamp":        time.time(),
            "envelope_id":      r.envelope_id,
            "outcome":          r.decision.outcome,
            "decision_reason":  r.decision.reason,
            "risk_tier":        r.risk.tier,
            "policy_score":     r.validation.policy_score,
            "final_confidence": r.validation.final_confidence,
            "failures":         r.validation.failures,
        }) + "\n")

    if r.blocked:
        raise BlockedError(reason=r.decision.reason, envelope_id=r.envelope_id)

    _orig_on_tool_end(output, **kwargs)

handler.on_tool_end = _governed_on_tool_end

# Run the agent — governed per tool call
try:
    result = agent_executor.invoke(
        {"input": "Compare prices on site-a.example.com vs site-b.example.com"},
        config={"callbacks": [handler]},
    )
except BlockedError as e:
    print(f"BLOCKED mid-execution: {e.reason}  audit={e.envelope_id}")
    result = None

# Validate the final composed output too
if result:
    final_output = result.get("output", result)
    r_final = client.validate(
        agent_id = AGENT_ID,
        user     = "qa-runner",
        input    = "Compare prices on both sites",
        output   = final_output if isinstance(final_output, dict) else {"answer": str(final_output)},
        metadata = {"step": "final_output", "run_id": run_id},
    )

    if r_final.blocked:
        print(f"BLOCKED at final output: {r_final.decision.reason}")
    elif r_final.needs_review:
        print(f"ESCALATED: {r_final.decision.reason}")
    else:
        print(f"APPROVED — confidence {r_final.validation.final_confidence:.1f}%")

gw.stop()
```

### Step 4 — Join Traces for Analysis

```python
# analysis/compare_runs.py
import json, pandas as pd

def load_jsonl(path):
    with open(path) as f:
        return pd.DataFrame([json.loads(l) for l in f if l.strip()])

exec_trace = load_jsonl("logs/execution_trace.jsonl")
gov_trace  = load_jsonl("logs/governance_trace.jsonl")

# Join on correlation_id — one governance row per tool-end row
merged = exec_trace.merge(gov_trace, on="correlation_id", how="left", suffixes=("_exec", "_gov"))

print(merged.groupby("outcome")["correlation_id"].count())      # approve / block / escalate counts
print(merged[merged["outcome"].isin(["block","escalate"])])     # flagged steps
print(merged.groupby("risk_tier")["policy_score"].describe())   # risk distribution
```

---

## `client.validate()` Full Signature

```python
r = client.validate(
    agent_id          = "my-agent",           # required — drives policy selection
    user              = "alice",              # required — audit identity
    input             = "user's query...",   # required — the prompt/instruction
    output            = {"key": "value"},    # the dict to validate against policy
    framework         = "LangChain",         # label in audit logs
    model             = "gpt-4o-mini",       # LLM model name
    tools_called      = [                    # optional tool call records
        {"name": "fetch_html", "arguments": {...}, "result": {...}, "latency_ms": 340.0}
    ],
    latency_ms        = 1234.0,
    tokens            = 512,
    parent_envelope_id = None,               # for multi-agent trust chain
    session_id        = "session-xyz",
    metadata          = {"correlation_id": "abc-123"},
)
```

### ValidateResponse Fields

```python
r.envelope_id                     # str  — unique audit ID, traceable in SQLite log
r.approved                        # bool — outcome == "approve"
r.blocked                         # bool — outcome == "block"
r.needs_review                    # bool — outcome in ("escalate", "request_evidence")
r.schema_valid                    # bool — schema_score >= 80 and no failures

r.decision.outcome                # "approve" | "block" | "escalate" | "request_evidence"
r.decision.reason                 # plain-English explanation
r.decision.policy_version         # policy version that was applied

r.validation.policy_score         # float 0–100  — YAML rule compliance
r.validation.final_confidence     # float 0–100  — composite weighted score (Developer+)
r.validation.schema_score         # float 0–100  — output structure validity
r.validation.evidence_score       # float 0–100  — evidence completeness
r.validation.tool_trust_score     # float 0–100  — tool invocation integrity
r.validation.consistency_score    # float 0–100  — internal consistency (model, latency)
r.validation.failures             # list[str]    — human-readable rule violation descriptions

r.risk.tier                       # "low" | "medium" | "high" | "critical"
r.risk.score                      # float 0–100
r.risk.reason                     # str

r.latency_ms                      # float — gateway validation round-trip time
r.tier_info                       # str — "oss" | "free" | "developer" | "team" | "enterprise"
```

---

## `@harness` Full Signature

```python
@harness(
    agent_id         = "payment-agent",   # str — drives policy selection
    user_kwarg       = "user",            # which kwarg to extract as the user field
    input_kwarg      = "input",           # which kwarg to extract as the input field
    base_url         = None,              # override AGENTRUST_GATEWAY_URL
    api_key          = None,              # override AGENTRUST_KEY
    block_on_block   = True,             # raise BlockedError when outcome=="block"
    block_on_review  = False,            # raise BlockedError when outcome=="escalate"
    raise_on_tier_gate = False,          # raise TierGateError when above your tier
    framework        = None,             # label for audit logs (auto-detected if None)
    raise_on_error   = False,            # raise if gateway itself errors
)
```

---

## Exceptions

```python
class BlockedError(RuntimeError):
    outcome: str       # "block" | "escalate" | "request_evidence"
    reason: str        # plain-English explanation from DecisionEngine
    envelope_id: str   # audit ID — look it up in ~/.agentrust/audit.jsonl

class TierGateError(RuntimeError):
    # raised when raise_on_tier_gate=True and your tier can't use that capability

class GatewayUnavailableError(RuntimeError):
    # raised when AGENTRUST_FAILURE_MODE=closed and gateway is unreachable
```

---

## 4-Engine Validation Pipeline

Every call runs through four sequential engines:

```
Stage 1 — ValidationEngine
  ├── Schema check       → output is a dict, not empty
  ├── Tool-trust check   → tool calls have non-null results
  ├── Policy check       → YAML rule evaluation (base + domain packs)
  ├── Consistency check  → model/latency/output populated
  ├── Grounding check    → numbers backed by tool results
  └── Adversarial check  → scans input for injection patterns:
        "ignore previous instructions", "jailbreak", "DAN",
        "pretend you are", "exfiltrate", "leak + bypass data"

Stage 2 — ConfidenceEngine
  → Weighted average of 6 signals → 0–100%

Stage 3 — RiskEngine
  → action_severity × business_impact × confidence_gap × policy_sensitivity
  → low / medium / high / critical

Stage 4 — DecisionEngine  (thresholds)
  confidence >= 90             → approve
  policy_score >= 60
    AND confidence >= 70       → approve
  confidence < 50              → block
  policy_score < 60            → block
  risk == critical             → escalate
  otherwise                    → escalate / retry
```

---

## Policy Scoring

```
Start = 100 points
CRITICAL violation → score = 0 instantly (blocks regardless of confidence)
HIGH     violation → -25 points each
MEDIUM   violation → -10 points each
LOW      violation → -5  points each
Clamped to [0, 100]

policy_score < 60 → BLOCK
```

---

## Environment Variables

```bash
# Gateway
AGENTRUST_ENABLED=true                      # kill-switch — false disables entire SDK instantly
AGENTRUST_GATEWAY_URL=http://localhost:8765  # remote or embedded gateway URL
AGENTRUST_KEY=at_...                         # API key (JWT or opaque)

# Resilience
AGENTRUST_FAILURE_MODE=open    # open=log&continue | closed=raise | queue=buffer to SQLite
AGENTRUST_TIMEOUT_SEC=10
AGENTRUST_RETRY_ATTEMPTS=3
AGENTRUST_RETRY_BACKOFF=0.5

# Embedded gateway
AGENTRUST_EMBED_PORT=8765
AGENTRUST_EMBED_DB=~/.agentrust/embedded.db  # :memory: for ephemeral

# Webhooks (Team tier+)
AGENTRUST_WEBHOOK_URL=https://discord.com/api/webhooks/...
AGENTRUST_WEBHOOK_EVENTS=block,escalate    # or "all"
```

---

## Tier System

| Tier       | Price   | Unlocks                                                                 |
|------------|---------|-------------------------------------------------------------------------|
| OSS        | Free    | Schema validation only                                                  |
| Free       | Free    | Auto-decision engine, local audit trail, base policy pack               |
| Developer  | $49/mo  | Confidence engine, risk scoring, domain policy packs (financial/medical), MCP adapter |
| Team       | $149/mo | Custom policy YAML, webhooks, human-review queue, LangGraph/CrewAI/AutoGen adapters, central audit |
| Enterprise | Custom  | LLM judge (Claude), trust chain provenance, multi-agent governance, SSO, SOC2 export |

---

## Pattern Comparison

|                    | `@harness`              | `auto_instrument()`     | `client.validate()`              |
|--------------------|-------------------------|-------------------------|----------------------------------|
| Code change required | Wrap one function     | None                    | Manual flow                      |
| Control over validated fields | Full         | Limited                 | Full                             |
| Access to raw scores | No (use BlockedError) | No                      | Yes                              |
| Best for           | Production agents       | Retrofitting existing apps | Dashboards, testing, per-tool governance |
| Async support      | Yes                     | Yes                     | Yes (AsyncAgentTrustClient)      |

---

## Audit Trail

Every validation appends to `~/.agentrust/audit.jsonl`:

```json
{
  "timestamp": "2026-07-16T10:30:00Z",
  "agent_id": "payment-processor",
  "envelope_id": "env_abc123",
  "decision": "block",
  "mad_code": "M4.a",
  "policy_score": 0.0,
  "confidence": 70.6,
  "risk_tier": "critical",
  "violations": ["critical[payment_amount_present]"]
}
```

---

## Prerequisites: AgentTrust SDK + LangChain

### 1. Python Version

**Python >= 3.10**

The SDK uses modern type hint syntax that won't work on 3.9 or below. Recommended: Python 3.11.

Check yours:

```bash
python3 --version
```

---

### 2. Install the Packages

Minimum for LangChain integration:

```bash
pip install "agentrust-sdk[embedded,retry]"
pip install langchain langchain-core
```

If using OpenAI as your LLM:

```bash
pip install langchain-openai
```

If using Anthropic / AWS / other providers:

```bash
pip install langchain-anthropic    # for Claude
pip install langchain-aws          # for Bedrock
pip install langchain-ollama       # for local Ollama models
```

Full install (everything at once):

```bash
pip install "agentrust-sdk[embedded,retry]" langchain langchain-core langchain-openai
```

---

### 3. What Each Package Does

| Package              | Purpose                                              | Required?                |
|----------------------|------------------------------------------------------|--------------------------|
| agentrust-sdk        | Core SDK — `@harness`, `client.validate()`, `BlockedError` | Yes                 |
| [embedded] extra     | Enables `embed_gateway()` — runs FastAPI + SQLite in-process | Yes (for embedded mode) |
| [retry] extra        | Exponential backoff when gateway is temporarily unreachable | Recommended         |
| langchain            | AgentExecutor, tools, chains                         | Yes                      |
| langchain-core       | LCEL (prompt \| llm \| parser), Runnable, BaseChatModel | Yes                   |
| langchain-openai     | ChatOpenAI — only if you use OpenAI models           | Only if using OpenAI     |

---

### 4. LLM Provider API Key

AgentTrust itself doesn't need an LLM API key. But your LangChain agent does to call the actual model:

```bash
# For OpenAI (GPT-4, GPT-4o, etc.)
export OPENAI_API_KEY=sk-...

# For Anthropic (Claude)
export ANTHROPIC_API_KEY=sk-ant-...

# For AWS Bedrock — configure AWS credentials normally
```

Note: The example in this repo (`langchain_agent.py`) uses a `_MockLLM` that needs no API key — useful for testing governance logic without LLM costs.

---

### 5. AgentTrust API Key

| Use Case                           | Key Needed?              |
|------------------------------------|--------------------------|
| OSS / local dev / testing          | No                       |
| Free tier (auto-decision, audit)   | Yes — run `agentrust init` |
| Developer / Team / Enterprise      | Yes — paid plan          |

```bash
# Get a free key (writes to ~/.agentrust/config.yaml)
agentrust init

# Or set manually
export AGENTRUST_KEY=at_...
```

---

### 6. Gateway — Pick One

**Option A: Embedded (Recommended for Development)**

No extra setup. Just call `embed_gateway()` in your code:

```python
from agentrust_sdk import embed_gateway
embed_gateway()   # starts FastAPI + SQLite on http://127.0.0.1:8765
```

Requires `[embedded]` extra. Writes to `~/.agentrust/embedded.db`.

**Option B: Docker (Staging)**

```bash
# Requires Docker + Docker Compose
cd agentrust-edge/
docker compose up gateway -d
export AGENTRUST_GATEWAY_URL=http://localhost:8000
```

**Option C: Remote / SaaS**

```bash
export AGENTRUST_GATEWAY_URL=https://your-gateway-url
export AGENTRUST_KEY=at_...
```

---

### 7. Environment Variables to Set

```bash
# Required — set by embed_gateway() automatically, or set manually
export AGENTRUST_GATEWAY_URL=http://localhost:8765

# Optional but recommended
export AGENTRUST_KEY=at_...              # your API key
export AGENTRUST_FAILURE_MODE=open       # open | closed | queue
export AGENTRUST_ENABLED=true            # kill-switch

# Your LLM provider
export OPENAI_API_KEY=sk-...
```

---

### 8. Minimal Working Setup (Copy-Paste)

```bash
# 1. Create a virtual environment
python3.11 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 2. Install everything needed
pip install "agentrust-sdk[embedded,retry]" langchain langchain-core langchain-openai

# 3. Set your keys
export OPENAI_API_KEY=sk-...      # skip if using mock LLM
export AGENTRUST_ENABLED=true

# 4. Run
python your_langchain_agent.py
```

Verify the install works:

```python
from agentrust_sdk import embed_gateway, harness, BlockedError
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

print("All imports OK — ready to use AgentTrust with LangChain")
```

---

### 9. Summary

| Prerequisite                      | Required        | Notes                                  |
|-----------------------------------|-----------------|----------------------------------------|
| Python 3.10+                      | Yes             | 3.11 recommended                       |
| agentrust-sdk[embedded,retry]     | Yes             | Core SDK + gateway + retry             |
| langchain + langchain-core        | Yes             | LangChain runtime                      |
| langchain-openai (or other)       | Only with real LLM | Skip if using mock LLM for testing  |
| LLM API key (OPENAI_API_KEY etc.) | Only with real LLM | Not needed for mock/testing         |
| AgentTrust API key                | Only for paid tiers | OSS/local dev works without it     |
| Docker                            | No              | Only needed for staging/production gateway |
| Write access to ~/.agentrust/     | Yes             | SQLite + audit log storage             |
