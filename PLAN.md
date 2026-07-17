# LangChain Price-Comparison Agent — Technical Build Plan

This is the step-by-step build plan for the validation test agent, structured so you can build and validate it incrementally — plain agent first, AgentTrust-wrapped second.

---

## Project Structure

```
examples/langchain_price_agent/
├── .env                        # AgentTrust config (no OpenAI key needed)
├── agent/
│   ├── tools.py                # fetch_html, extract_price, compare_prices
│   ├── claude_code_llm.py      # Claude CLI LLM wrapper (replaces langchain-openai)
│   ├── build_agent.py          # LangChain agent construction
│   └── callback_handler.py     # Custom execution-trace logger
├── runs/
│   ├── run_a_unmonitored.py    # Baseline run — no governance
│   └── run_b_agenttrust.py     # AgentTrust-wrapped run
├── analysis/
│   └── compare_runs.py         # Join traces on correlation_id, produce report
├── policy/
│   └── price_agent.yaml        # Custom AgentTrust policy for this agent
└── logs/                       # Auto-created at runtime
    ├── execution_trace.jsonl   # Tool timings, inputs, reasoning
    └── governance_trace.jsonl  # AgentTrust ValidateResponse per step
```

---

## Step 0: Environment Setup

```bash
python -m venv venv
source venv/bin/activate   # or venv\Scripts\activate on Windows

# LangChain stack — no langchain-openai needed; LLM backbone is the local `claude` CLI
pip install langchain langchain-community
pip install requests beautifulsoup4
pip install python-dotenv pandas matplotlib

# AgentTrust SDK — install from the local package
pip install -e /path/to/agent-trust-sdk/agentrust_sdk
# or if the embedded extras are needed:
pip install -e "/path/to/agent-trust-sdk/agentrust_sdk[embedded,retry]"
```

**`.env`**

```dotenv
# LLM backbone: uses your local `claude` CLI OAuth session — no API key required.
# Run `claude auth status` before Step 5; it must show loggedIn: true.

# AgentTrust
AGENTRUST_KEY=at_...                         # JWT or opaque key from `agentrust init --local`
AGENTRUST_GATEWAY_URL=http://localhost:8765  # Embedded gateway (set by embed_gateway())
AGENTRUST_FAILURE_MODE=open                  # open | closed | queue
AGENTRUST_ENABLED=true                       # Master kill-switch; set false to disable governance
```

---

## Step 1: Define the Tools

Build each tool as a standalone testable function before wiring into LangChain.

**`agent/tools.py`**

```python
import re
import time
import requests
from bs4 import BeautifulSoup

APPROVED_DOMAINS = ["site-a.example.com", "site-b.example.com"]  # replace with real domains


def fetch_html(url: str) -> dict:
    """Fetch raw HTML for an approved domain. Returns status, size, timing, html."""
    domain = url.split("/")[2]
    if domain not in APPROVED_DOMAINS:
        raise ValueError(f"Domain not approved: {domain}")

    start = time.time()
    resp = requests.get(url, timeout=10)
    elapsed = time.time() - start

    return {
        "url": url,
        "status": resp.status_code,
        "html": resp.text,
        "size": len(resp.text),
        "elapsed_sec": round(elapsed, 3),
    }


def extract_price(html: str) -> dict:
    """Parse a price out of HTML. Returns value + match count for validation."""
    soup = BeautifulSoup(html, "html.parser")
    # Replace with the real site's price element selector
    matches = re.findall(r"\$\s?(\d+\.\d{2})", soup.get_text())
    return {
        "matches_found": len(matches),
        "price": float(matches[0]) if len(matches) == 1 else None,
        "raw_matches": matches,
    }


def compare_prices(price_a: float, price_b: float) -> dict:
    if price_a is None or price_b is None:
        return {"error": "Missing price — cannot compare"}
    cheaper = "A" if price_a < price_b else "B"
    return {
        "cheaper_site": cheaper,
        "price_a": price_a,
        "price_b": price_b,
        "difference": round(abs(price_a - price_b), 2),
    }
```

**Test standalone before touching LangChain.** Run against two real or mock URLs, confirm you get sane output. Don't debug tool logic and agent logic at the same time.

---

## Step 2: Wrap as LangChain Tools

```python
from langchain.tools import StructuredTool
from pydantic import BaseModel
from agent.tools import fetch_html, extract_price, compare_prices


class FetchInput(BaseModel):
    url: str


class ExtractInput(BaseModel):
    html: str


class CompareInput(BaseModel):
    price_a: float
    price_b: float


fetch_tool = StructuredTool.from_function(
    func=fetch_html,
    name="fetch_html",
    description="Fetch HTML from an approved product page URL.",
    args_schema=FetchInput,
)

extract_tool = StructuredTool.from_function(
    func=extract_price,
    name="extract_price",
    description="Extract a numeric price from fetched HTML.",
    args_schema=ExtractInput,
)

compare_tool = StructuredTool.from_function(
    func=compare_prices,
    name="compare_prices",
    description="Compare two prices and return the cheaper option.",
    args_schema=CompareInput,
)
```

---

## Step 3: Build the Custom Execution-Trace Callback Handler

This captures URL, status, timing, tool reasoning, and a `correlation_id` that links each tool-call row to the AgentTrust governance row written in Step 6.

**`agent/callback_handler.py`**

```python
import json
import time
import uuid
from collections import defaultdict
from langchain.callbacks.base import BaseCallbackHandler


class ExecutionTraceHandler(BaseCallbackHandler):
    """Writes a JSONL execution trace.  Every tool-start/end pair shares a
    correlation_id so the governance trace can be joined on that key."""

    def __init__(self, run_id: str, log_path: str = "logs/execution_trace.jsonl"):
        self.run_id = run_id
        self.log_path = log_path
        # maps tool-call serial → correlation_id so start and end share it
        self._pending: dict[int, str] = {}
        self._call_counter = defaultdict(int)

    # expose so run_b can pull the current correlation_id for a given tool
    def correlation_id_for(self, tool_name: str) -> str:
        key = self._call_counter[tool_name] - 1
        return self._pending.get(key, str(uuid.uuid4()))

    def _write(self, record: dict):
        record["run_id"] = self.run_id
        record["timestamp"] = time.time()
        with open(self.log_path, "a") as f:
            f.write(json.dumps(record) + "\n")

    def on_tool_start(self, serialized, input_str, **kwargs):
        cid = str(uuid.uuid4())
        serial = self._call_counter[serialized.get("name", "")]
        self._call_counter[serialized.get("name", "")] += 1
        self._pending[serial] = cid
        self._write({
            "event": "tool_start",
            "tool": serialized.get("name"),
            "input": input_str,
            "correlation_id": cid,
        })

    def on_tool_end(self, output, **kwargs):
        # kwargs may contain tool name via run_manager; fall back to last seen
        tool_name = kwargs.get("name", list(self._call_counter.keys())[-1] if self._call_counter else "unknown")
        serial = self._call_counter[tool_name] - 1
        cid = self._pending.get(serial, str(uuid.uuid4()))
        self._write({
            "event": "tool_end",
            "tool": tool_name,
            "output": str(output),
            "correlation_id": cid,
        })

    def on_agent_action(self, action, **kwargs):
        self._write({
            "event": "agent_action",
            "tool": action.tool,
            "tool_input": action.tool_input,
            "log": action.log,     # captures the agent's reasoning text
            "correlation_id": str(uuid.uuid4()),
        })
```

**The `correlation_id` is the join key** between the execution trace and the governance trace. Generate it at `tool_start`, carry it through `tool_end`, and write it into every `ValidateResponse` you log in Step 6.

---

## Step 4: Build the Agent

### 4a — Implement the Claude CLI LLM wrapper

**`agent/claude_code_llm.py`**

```python
import subprocess
from langchain_core.language_models.llms import LLM


class ClaudeCodeLLM(LLM):
    """LangChain LLM that shells out to the local `claude` CLI.
    Requires `claude auth status` to show loggedIn: true — no API key needed."""

    model: str = "sonnet"

    @property
    def _llm_type(self) -> str:
        return "claude-code-cli"

    def _call(self, prompt: str, stop=None, **kwargs) -> str:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", self.model,
             "--output-format", "text", "--no-caching"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"claude CLI error: {result.stderr}")
        return result.stdout.strip()
```

Smoke-test before building the agent:

```python
from agent.claude_code_llm import ClaudeCodeLLM
llm = ClaudeCodeLLM(model="sonnet")
print(llm.invoke("Reply with the single word: ok"))  # expect: ok
```

### 4b — Build the agent

**`agent/build_agent.py`**

```python
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from agent.tools_wrapped import fetch_tool, extract_tool, compare_tool
from agent.claude_code_llm import ClaudeCodeLLM

# Reuses your existing `claude auth` session — no API key needed.
# Pass model="opus" for the larger model.
llm = ClaudeCodeLLM(model="sonnet")

REACT_PROMPT = PromptTemplate.from_template(
    "You compare prices for a product across two approved sites. "
    "Fetch each site, extract the price, then compare. "
    "Only use the two approved domains you are given.\n\n"
    "You have access to the following tools:\n\n"
    "{tools}\n\n"
    "Use the following format:\n\n"
    "Question: the input question you must answer\n"
    "Thought: you should always think about what to do\n"
    "Action: the action to take, should be one of [{tool_names}]\n"
    "Action Input: the input to the action\n"
    "Observation: the result of the action\n"
    "... (this Thought/Action/Action Input/Observation can repeat N times)\n"
    "Thought: I now know the final answer\n"
    "Final Answer: the final answer as raw JSON with keys "
    "cheaper_site, price_a, price_b, difference (no markdown fences, no prose)\n\n"
    "Begin!\n\n"
    "Question: {input}\n"
    "Thought:{agent_scratchpad}"
)

tools = [fetch_tool, extract_tool, compare_tool]
agent = create_react_agent(llm, tools, REACT_PROMPT)
agent_executor = AgentExecutor(
    agent=agent, tools=tools, verbose=True, handle_parsing_errors=True
)
```

---

## Step 5: Run A — Unmonitored Baseline

**`runs/run_a_unmonitored.py`**

```python
import uuid
import os
from dotenv import load_dotenv

load_dotenv()
os.makedirs("logs", exist_ok=True)

from agent.build_agent import agent_executor
from agent.callback_handler import ExecutionTraceHandler

run_id = str(uuid.uuid4())
handler = ExecutionTraceHandler(run_id=run_id)

result = agent_executor.invoke(
    {"input": "Compare the price of [product] on site-a.example.com and site-b.example.com"},
    config={"callbacks": [handler]},
)
print(result)
print(f"\nRun ID: {run_id}")
print("Execution trace → logs/execution_trace.jsonl")
```

Run this first. Confirm the JSONL has sensible entries and all three tools appear before adding AgentTrust — you want a clean baseline to diff against.

---

## Step 6: Configure AgentTrust Policy

Before Run B, tell AgentTrust what a valid price-comparison output looks like and which domains are approved.

**`policy/price_agent.yaml`**

```yaml
meta:
  id: price-agent
  version: "1.0"
  description: "Rules for the LangChain price-comparison agent"
  patterns:
    - "price-comparison-agent"

rules:
  - id: output_cheaper_site_present
    description: "Output must include a cheaper_site field"
    severity: high
    target: output.cheaper_site
    op: exists
    effect: deny

  - id: output_price_a_present
    description: "Output must include price_a"
    severity: high
    target: output.price_a
    op: exists
    effect: deny

  - id: output_price_b_present
    description: "Output must include price_b"
    severity: high
    target: output.price_b
    op: exists
    effect: deny

  - id: approved_domains_only
    description: "Only approved domains may be fetched"
    severity: critical
    target: output.domains_used
    op: not_in_list
    value: ["evil.com", "shadow-site.net"]
    effect: deny

  - id: large_price_difference_review
    description: "Differences above $50 are escalated for human review"
    severity: medium
    target: output.difference
    op: lte
    value: 50.0
    effect: review
```

Drop this file in your `policy/` directory. The embedded gateway picks up YAML policy files in its working directory automatically (or load via the PolicyEngine API).

---

## Step 7: Run B — AgentTrust-Wrapped

AgentTrust offers three integration patterns. Use **Pattern C** (direct `client.validate()`) here because it gives you per-step governance with full access to the `ValidateResponse` for logging and correlation.

**`runs/run_b_agenttrust.py`**

```python
import uuid
import json
import time
import os
from dotenv import load_dotenv

load_dotenv()
os.makedirs("logs", exist_ok=True)

# --- AgentTrust setup ---
from agentrust_sdk import embed_gateway, AgentTrustClient, BlockedError

# Start the in-process SQLite gateway BEFORE any validate() calls
gw = embed_gateway()          # binds on http://127.0.0.1:8765 by default
client = AgentTrustClient()   # reads AGENTRUST_KEY + AGENTRUST_GATEWAY_URL from env

from agent.build_agent import agent_executor
from agent.callback_handler import ExecutionTraceHandler

AGENT_ID = "price-comparison-agent"
USER     = "qa-runner"

run_id = str(uuid.uuid4())
handler = ExecutionTraceHandler(run_id=run_id)

# Monkey-patch tool execution to call client.validate() after each tool finishes
# so we get per-tool governance, not just final-output governance.

_orig_on_tool_end = handler.on_tool_end

def _governed_on_tool_end(output, **kwargs):
    tool_name = kwargs.get("name", "unknown")
    serial = handler._call_counter.get(tool_name, 1) - 1
    cid = handler._pending.get(serial, str(uuid.uuid4()))

    # Parse the tool output (it's a stringified dict)
    try:
        tool_output = json.loads(output) if isinstance(output, str) else output
    except Exception:
        tool_output = {"raw": str(output)}

    # Govern this individual tool output
    r = client.validate(
        agent_id=AGENT_ID,
        user=USER,
        input=f"tool_call:{tool_name}",
        output=tool_output,
        framework="LangChain",
        metadata={"correlation_id": cid, "run_id": run_id},
    )

    # Write governance trace — tagged with the same correlation_id
    with open("logs/governance_trace.jsonl", "a") as f:
        f.write(json.dumps({
            "event": "tool_governance",
            "tool": tool_name,
            "correlation_id": cid,
            "run_id": run_id,
            "timestamp": time.time(),
            "envelope_id": r.envelope_id,
            # Decision
            "outcome": r.decision.outcome,           # "approve" | "block" | "escalate"
            "decision_reason": r.decision.reason,
            "policy_version": r.decision.policy_version,
            # Risk
            "risk_tier": r.risk.tier,                # "low" | "medium" | "high" | "critical"
            "risk_score": r.risk.score,
            "risk_reason": r.risk.reason,
            # Validation scores
            "policy_score": r.validation.policy_score,
            "final_confidence": r.validation.final_confidence,
            "failures": r.validation.failures,
        }) + "\n")

    if r.blocked:
        raise BlockedError(
            reason=r.decision.reason,
            envelope_id=r.envelope_id,
        )

    _orig_on_tool_end(output, **kwargs)


handler.on_tool_end = _governed_on_tool_end

# --- Final-output governance (Pattern C) ---
try:
    result = agent_executor.invoke(
        {"input": "Compare the price of [product] on site-a.example.com and site-b.example.com"},
        config={"callbacks": [handler]},
    )
except BlockedError as e:
    print(f"BLOCKED mid-execution: {e.reason} (envelope_id={e.envelope_id})")
    result = None

if result:
    # Validate the final composed output too
    final_output = result.get("output", result)
    if isinstance(final_output, str):
        # Try to extract structured dict the agent produced
        try:
            final_output = json.loads(final_output)
        except Exception:
            final_output = {"answer": final_output}

    r_final = client.validate(
        agent_id=AGENT_ID,
        user=USER,
        input="Compare the price of [product] on site-a.example.com and site-b.example.com",
        output=final_output,
        framework="LangChain",
        metadata={"step": "final_output", "run_id": run_id},
    )

    with open("logs/governance_trace.jsonl", "a") as f:
        f.write(json.dumps({
            "event": "final_governance",
            "correlation_id": "final",
            "run_id": run_id,
            "timestamp": time.time(),
            "envelope_id": r_final.envelope_id,
            "outcome": r_final.decision.outcome,
            "decision_reason": r_final.decision.reason,
            "risk_tier": r_final.risk.tier,
            "policy_score": r_final.validation.policy_score,
            "final_confidence": r_final.validation.final_confidence,
            "failures": r_final.validation.failures,
        }) + "\n")

    if r_final.blocked:
        print(f"BLOCKED at final output: {r_final.decision.reason}")
    elif r_final.needs_review:
        print(f"ESCALATED for human review: {r_final.decision.reason}")
    else:
        print(f"APPROVED — confidence {r_final.validation.final_confidence:.1f}%")
        print(result)

gw.stop()
print(f"\nRun ID: {run_id}")
print("Governance trace → logs/governance_trace.jsonl")
```

**Alternative — @harness on the whole agent call (Pattern A)**

If per-tool governance is not required, the decorator pattern is simpler:

```python
from agentrust_sdk import harness, embed_gateway, BlockedError

embed_gateway()  # MUST run before @harness is applied

@harness(
    agent_id="price-comparison-agent",
    block_on_block=True,
    block_on_review=False,
)
def run_price_agent(user: str, input: str) -> dict:
    result = agent_executor.invoke({"input": input})
    # Return the structured dict that AgentTrust will evaluate against policy
    return result.get("output", {"raw": str(result)})

try:
    output = run_price_agent(user="qa-runner", input="Compare prices on both sites")
except BlockedError as e:
    print(f"BLOCKED: {e.reason} (envelope_id={e.envelope_id})")
```

The `@harness` decorator automatically calls `client.validate()` on the returned dict and raises `BlockedError` if the outcome is `block`.

**Alternative — auto_instrument (Pattern B, zero code changes)**

```python
from agentrust_sdk import embed_gateway, auto_instrument

embed_gateway()
auto_instrument(agent_id="price-comparison-agent", langchain=True)

# All subsequent chain.invoke() / executor.invoke() calls are governed
# automatically. Fire-and-forget — never blocks, never raises.
result = agent_executor.invoke({"input": "Compare prices on both sites"})
```

---

## Step 8: Join and Compare

**`analysis/compare_runs.py`**

```python
import json
import pandas as pd

def load_jsonl(path: str) -> pd.DataFrame:
    with open(path) as f:
        return pd.DataFrame([json.loads(line) for line in f if line.strip()])

exec_trace = load_jsonl("logs/execution_trace.jsonl")
gov_trace  = load_jsonl("logs/governance_trace.jsonl")

# Join on correlation_id — each tool-end row pairs with one governance row
merged = exec_trace.merge(gov_trace, on="correlation_id", how="left", suffixes=("_exec", "_gov"))
merged.to_csv("analysis/merged_trace.csv", index=False)

# Summary stats
print("\n=== Governance Summary ===")
print(merged.groupby("outcome")["correlation_id"].count().rename("calls"))

print("\n=== Blocked or Escalated Steps ===")
flagged = merged[merged["outcome"].isin(["block", "escalate"])]
print(flagged[["tool_exec", "outcome", "decision_reason", "risk_tier", "policy_score", "failures"]])

print("\n=== Risk Tier Distribution ===")
print(merged.groupby("risk_tier")["policy_score"].agg(["count", "mean"]))

print("\n=== Policy Score Stats ===")
print(merged["policy_score"].describe())
```

**What the merged frame tells you:**

| Column             | What it shows                                                    |
| ------------------ | ---------------------------------------------------------------- |
| `tool`             | Which LangChain tool triggered this governance call              |
| `outcome`          | `approve` / `block` / `escalate` per tool call                   |
| `risk_tier`        | `low` / `medium` / `high` / `critical`                           |
| `policy_score`     | 0–100, how well the tool output matched policy rules             |
| `final_confidence` | 0–100 composite (Developer tier+)                                |
| `failures`         | List of specific policy rule violations                          |
| `decision_reason`  | Plain-English explanation of the decision                        |
| `envelope_id`      | Unique audit ID — traceable in the embedded gateway's SQLite log |

**Diff Run A vs Run B:** Run A has no governance rows; Run B has one governance row per tool call plus a `final_governance` row. The violations column in Run B is what governance caught that the unmonitored run didn't flag.

---

## AgentTrust SDK Reference (Quick Sheet)

### Installation

```bash
pip install "agentrust-sdk"              # Core only
pip install "agentrust-sdk[embedded]"    # + in-process SQLite gateway
pip install "agentrust-sdk[retry]"       # + tenacity retry / backoff
pip install "agentrust-sdk[full]"        # Everything
```

### Key Imports

```python
from agentrust_sdk import (
    harness,                 # @harness decorator
    embed_gateway,           # EmbeddedGateway,  # In-process SQLite gateway
    AgentTrustClient,        # Sync client
    AsyncAgentTrustClient,   # Async client
    BlockedError,            # Raised when outcome == "block" and block_on_block=True
    TierGateError,           # Raised when capability exceeds your tier
    auto_instrument,         # auto_wrap,  # Zero-code monkey-patching
    Tier, Capability,        # Tier/capability enums
)
```

### `client.validate()` Signature

```python
r = client.validate(
    agent_id="price-comparison-agent",   # required
    user="alice",                         # required
    input="...",                          # required
    output={"cheaper_site": "A", ...},   # optional (final output dict)
    framework="LangChain",               # label shown in audit logs
    model="gpt-4o",                      # LLM model name
    tools_called=[...],                  # list of ToolCall dicts
    latency_ms=1234.0,
    tokens=512,
    session_id="session-xyz",
    metadata={"correlation_id": cid},
)
```

### `ValidateResponse` Fields

```python
r.envelope_id                    # str  — unique audit ID
r.approved                       # bool — outcome == "approve"
r.blocked                        # bool — outcome == "block"
r.needs_review                   # bool — outcome in ("escalate", "request_evidence")

r.decision.outcome               # "approve" | "block" | "escalate" | "request_evidence"
r.decision.reason                # str — plain-English explanation
r.decision.policy_version        # str — version of applied policy

r.risk.tier                      # "low" | "medium" | "high" | "critical"
r.risk.score                     # float 0–100
r.risk.reason                    # str

r.validation.policy_score        # float 0–100 — policy rule compliance
r.validation.final_confidence    # float 0–100 — composite (Developer tier+)
r.validation.schema_score        # float 0–100 — output structure validity
r.validation.evidence_score      # float 0–100 — evidence completeness
r.validation.tool_trust_score    # float 0–100 — tool invocation integrity
r.validation.consistency_score   # float 0–100 — internal consistency
r.validation.failures            # list[str] — rule violation descriptions
```

### Environment Variables

```bash
AGENTRUST_KEY=at_...                        # API key (JWT or opaque)
AGENTRUST_GATEWAY_URL=http://localhost:8765  # Gateway URL
AGENTRUST_ENABLED=true                       # Kill-switch
AGENTRUST_FAILURE_MODE=open                  # open | closed | queue
AGENTRUST_TIMEOUT_SEC=10
AGENTRUST_RETRY_ATTEMPTS=3
```

### Tier Capabilities

| Tier       | Key Capabilities                                                          |
| ---------- | ------------------------------------------------------------------------- |
| OSS        | Schema validation only                                                    |
| Free       | Auto-decision, local audit, base policy                                   |
| Developer  | Confidence engine, risk scoring, built-in policy packs, MCP adapter       |
| Team       | Custom policies, webhooks, review queue, LangGraph adapter, central audit |
| Enterprise | Trust chain, LLM judge, multi-agent governance                            |

---

## Build Order Summary

1. **Tools standalone** — test `fetch_html`, `extract_price`, `compare_prices` outside LangChain
2. **Wrap as `StructuredTool`s** — confirm tool schemas serialize correctly
3. **Callback handler** — verify `correlation_id` appears in pairs in the JSONL
4. **Agent assembly** — `AgentExecutor` with `verbose=True`, confirm reasoning appears
5. **Run A** — unmonitored baseline; confirm clean execution trace log
6. **Policy YAML** — define approved-domain rules and output schema rules for `price-comparison-agent`
7. **Run B** — AgentTrust-wrapped; confirm governance trace rows appear with matching `correlation_id`s
8. **Join & compare** — `compare_runs.py`; report what governance caught that Run A missed

Each step is independently testable. Don't move to the next until the current one produces output you trust.
