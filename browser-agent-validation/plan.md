# Browser Agent + AgentTrust Demo

## Technical Implementation Plan (Claude Code)

---

# 1. Project Overview

## Purpose

This project is **not** intended to build the most advanced Browser Agent.

Its purpose is to build a **technical demonstration** that explains how **AgentTrust** adds trust, governance, observability, and policy enforcement to an existing LangChain agent with **minimal code changes**.

The Browser Agent is simply the example application.

The real product being demonstrated is **AgentTrust**.

---

## Core Engineering Question

The demo should answer one question:

> **What changes when the exact same LangChain agent is executed with AgentTrust enabled?**

The Browser Agent should remain functionally identical.

The only difference between executions should be the addition of the AgentTrust middleware.

---

# 2. Original Browser Agent Use Case

The Browser Agent researches information from the web and produces a structured answer.

Example user request:

> **"Summarize the latest Model Context Protocol (MCP) updates."**

The Browser Agent should execute the following workflow.

```text
User Query
      │
      ▼
Understand Intent
      │
      ▼
Search the Web
      │
      ▼
Collect Top Results
      │
      ▼
Visit Web Pages
      │
      ▼
Extract Readable Content
      │
      ▼
Prepare Context
      │
      ▼
Reason using Ollama
      │
      ▼
Generate Structured Response
      │
      ▼
Return Result
```

The Browser Agent should focus **only** on solving the user's task.

It should **not** perform:

* policy validation
* trust evaluation
* confidence estimation
* risk scoring
* audit logging
* governance
* execution tracing

Those responsibilities belong entirely to AgentTrust.

---

# 3. AgentTrust Use Case

AgentTrust is **not another AI agent**.

It is a middleware layer that governs the execution of an AI agent.

It wraps around the Browser Agent without modifying its implementation.

Responsibilities include:

* Input Validation
* Prompt Injection Detection
* URL Validation
* Content Sanitization
* Schema Validation
* Citation Validation
* Confidence Estimation
* Risk Scoring
* Policy Enforcement
* Trust Decisions
* Audit Logging
* Metrics Collection
* Execution Tracing

Think of AgentTrust as the equivalent of middleware in a web framework.

Instead of generating answers, it determines whether those answers should be trusted.

---

# 4. Demo Objectives

The demo should execute the **same Browser Agent** in two modes.

## Mode A — Standard Browser Agent

```text
User
   │
   ▼
Browser Agent
   │
   ▼
Response
```

---

## Mode B — Browser Agent + AgentTrust

```text
User
   │
   ▼
Browser Agent
   │
   ▼
AgentTrust Middleware
   │
   ▼
Governed Response
```

The Browser Agent code should not change.

Only the middleware should be added.

---

# 5. Success Criteria

A successful demo should allow users to understand:

### Browser Agent

* How the agent plans work
* How tools are selected
* How search works
* How browser extraction works
* How Ollama generates responses

### AgentTrust

* Where governance is introduced
* Which policies are evaluated
* How confidence is calculated
* How risk is calculated
* How trust decisions are made
* How audit logs are generated
* How execution becomes observable

The comparison should focus on **execution**, not only the final response.

---

# 6. Technical Stack

## Runtime

* Python 3.11
* LangChain
* langchain-ollama
* Ollama
* Pydantic v2
* Typer
* Rich
* pytest

## Browser Tools

* DuckDuckGo Search
* Requests
* BeautifulSoup4
* Trafilatura

## AgentTrust

* AgentTrust SDK
* Local Policy Engine
* Local Audit Storage

---

## LLM Configuration

All reasoning must execute locally.

Do **not** use:

* OpenAI
* Anthropic
* Gemini
* Cloud-hosted models

Example:

```python
from langchain_ollama import ChatOllama

llm = ChatOllama(
    model="qwen3:8b",
    temperature=0
)
```

Recommended models

* qwen3:8b
* llama3.1:8b
* mistral

---

# 7. High-Level Architecture

```text
                    User
                      │
                      ▼
               Browser Agent
                      │
    ┌─────────────────────────────────┐
    │ Planning                        │
    │ Search                          │
    │ Browser                         │
    │ Content Extraction              │
    │ Ollama                          │
    │ Structured Response             │
    └─────────────────────────────────┘
                      │
                      ▼
            AgentTrust Middleware
                      │
    ┌─────────────────────────────────┐
    │ Input Validation                │
    │ Policy Engine                   │
    │ Confidence Engine               │
    │ Risk Engine                     │
    │ Decision Engine                 │
    │ Audit Logger                    │
    └─────────────────────────────────┘
                      │
                      ▼
               Final Response
```

---

# 8. Project Structure

```text
browser-agent-demo/

app/
browser_agent/
execution/
tools/
agenttrust/
models/
policies/
audit/
metrics/
comparison/
ui/
tests/
docs/

demo.py
README.md
CLAUDE.md
requirements.txt
```

---

# Phase 1 — Project Foundation

## Objective

Create a modular architecture that cleanly separates:

* Browser Agent
* Execution Engine
* AgentTrust
* UI
* Metrics
* Audit
* Comparison

## Tasks

Create interfaces for:

* SearchTool
* BrowserTool
* Extractor
* Summarizer
* ExecutionContext
* ExecutionTrace
* TrustMiddleware
* PolicyEngine
* AuditLogger

## Requirements

* Dependency Injection
* SOLID
* Strong Typing
* Pydantic Models

## Acceptance Criteria

* Project builds
* Imports resolve
* Empty interfaces exist

---

# Phase 2 — Browser Agent

## Objective

Build a production-quality Browser Agent.

Execution Flow

```text
Question
    ↓
Search
    ↓
Top URLs
    ↓
Browser
    ↓
Extract
    ↓
Prepare Context
    ↓
Ollama
    ↓
Summary
```

## Components

* Search Tool
* Browser Tool
* Content Extractor
* Ollama Summarizer

## Output Model

```python
BrowserResult

summary
sources
urls
latency
token_usage
```

## Acceptance Criteria

Running

```bash
python demo.py
```

returns:

* Summary
* Sources
* URLs
* Latency

---

# Phase 3 — Execution Engine

## Objective

Make every execution observable.

Instead of calling methods directly, execute every step through an execution engine.

```text
ExecutionEngine

↓

Planning

↓

Search

↓

Browser

↓

Extraction

↓

Reasoning

↓

Response
```

## Components

* ExecutionEngine
* ExecutionContext
* ExecutionEvent
* ExecutionNode
* ExecutionTrace

Each event records:

* Start Time
* End Time
* Duration
* Inputs
* Outputs
* Metadata
* Status

## Acceptance Criteria

Every execution generates:

```
trace.json
```

---

# Phase 4 — Trace Visualization

## Objective

Visualize execution.

Render timeline:

```text
Planning
✓ 120ms

Search
✓ 460ms

Browser
✓ 700ms

Extraction
✓ 410ms

Reasoning
✓ 1800ms

Response
✓ Done
```

Also save:

```
trace.json
```

Each trace node should contain:

* Step Name
* Duration
* Inputs
* Outputs
* Status
* Metadata

---

# Phase 5 — AgentTrust Middleware

## Objective

Integrate AgentTrust without modifying BrowserAgent.

Architecture

```text
BrowserAgent

↓

TrustMiddleware

↓

Response
```

Middleware should intercept:

* User Input
* Intermediate Results
* Final Response

BrowserAgent should never import AgentTrust.

---

# Phase 6 — Governance Engine

## Objective

Implement governance as independent services.

Components

* PolicyEngine
* ConfidenceEngine
* RiskEngine
* DecisionEngine

Execution Pipeline

```text
Response

↓

Schema Validation

↓

Citation Validation

↓

Confidence

↓

Risk

↓

Policy Evaluation

↓

Decision
```

Supported Decisions

* ALLOW
* BLOCK
* RETRY
* HUMAN_REVIEW

Acceptance Criteria

Each engine should be independently testable.

---

# Phase 7 — Audit System

## Objective

Persist every execution.

Generate:

```
audit.jsonl
```

Example

```json
{
  "execution_id": "",
  "timestamp": "",
  "decision": "ALLOW",
  "confidence": 92,
  "risk": "LOW",
  "latency": 2104,
  "violations": []
}
```

Components

* AuditLogger
* AuditEvent
* ExecutionMetadata

Audit log must be append-only.

---

# Phase 8 — Comparison Engine

## Objective

Execute the same workflow twice.

Flow

```text
Question

↓

Run Browser Agent

↓

Capture Trace

↓

Run Browser Agent + AgentTrust

↓

Capture Trace

↓

Compare
```

Output

```text
WITHOUT AGENTTRUST

Planning

Search

Browser

Reasoning

Response

────────────────────────

WITH AGENTTRUST

Planning

Input Validation

Search

Injection Detection

Browser

Confidence

Risk

Policies

Audit

Response
```

---

# Phase 9 — Metrics Engine

## Objective

Measure execution quality.

Track:

* Total Execution Time
* Planning Time
* Search Time
* Browser Time
* Extraction Time
* LLM Time
* Validation Time
* Confidence
* Risk
* Policy Violations
* Retry Count
* Human Review Count
* Blocked Count
* Allowed Count
* Average Latency

Generate:

```
metrics.json
```

---

# Phase 10 — Failure Scenarios

Create deterministic demonstrations.

## Scenario 1

Prompt Injection

## Scenario 2

Hallucinated Citation

## Scenario 3

Invalid URL

## Scenario 4

Low Confidence

## Scenario 5

Sensitive Data Leak

Each scenario executes twice.

```text
Without AgentTrust

↓

Failure

────────────────────

With AgentTrust

↓

Governed Decision
```

The goal is to clearly demonstrate the value of governance.

---

# Phase 11 — Interactive CLI

Use:

* Typer
* Rich

Main Menu

```text
Browser Agent Demo

1. Execute Browser Agent

2. Execute Browser Agent + AgentTrust

3. Compare Executions

4. View Execution Trace

5. View Audit Log

6. View Metrics Dashboard

7. Run Failure Scenarios

8. Exit
```

Each execution should display:

* Live progress
* Timeline
* Per-step latency
* Tool execution
* Trust decision
* Metrics
* Audit summary

---

# 9. Engineering Constraints

Claude Code should follow these architectural rules.

## Architecture

* BrowserAgent must never import AgentTrust.
* AgentTrust must wrap BrowserAgent using middleware.
* Components should remain loosely coupled.

## Design

* Use dependency injection.
* Use Protocol or ABC interfaces.
* Follow SOLID principles.
* Use Pydantic for all models.
* Strong typing throughout.

## Observability

Every execution step must emit structured events.

These events should power:

* Execution traces
* Metrics
* Audit logs
* Comparison engine

## Testing

Each phase must include:

* Unit Tests
* Integration Tests
* Sample Execution
* Documentation

## Documentation

For every completed phase generate:

* Architecture Diagram
* Mermaid Sequence Diagram
* Component Responsibilities
* Public APIs
* Extension Points

---

# 10. Final Deliverable

The completed project should provide:

* Browser Agent powered by Ollama
* Execution Engine
* Execution Timeline
* Execution Trace Viewer
* AgentTrust Middleware
* Policy Engine
* Confidence Engine
* Risk Engine
* Decision Engine
* Audit Logger
* Metrics Dashboard
* Comparison Engine
* Failure Scenario Demonstrations
* Interactive CLI
* Complete Documentation

The final result should resemble an **AI Observability & Governance Platform** rather than a simple browser agent. A user should be able to inspect every stage of execution, compare governed and ungoverned runs side by side, understand where AgentTrust integrates, and see measurable improvements in trust, visibility, and control—all while the underlying Browser Agent implementation remains unchanged.
