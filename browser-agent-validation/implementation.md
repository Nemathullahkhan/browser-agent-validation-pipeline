# Browser Agent + AgentTrust Demo

# Step-by-Step Implementation Roadmap

---

# Project Philosophy

Do **not** build the entire project in one pass.

Instead, build the system incrementally.

Each phase should:

* Compile successfully
* Be independently testable
* Have unit tests
* Have documentation
* Be committed before starting the next phase

Each phase should produce a working demonstration.

---

# Milestone 1 — Project Bootstrap

## Goal

Create the project foundation.

### Tasks

* Create project structure
* Configure Python 3.11
* Configure virtual environment
* Install dependencies
* Configure Ruff
* Configure Black
* Configure pytest
* Configure logging
* Configure Rich
* Configure Typer
* Configure Pydantic

### Deliverables

```text
browser-agent-demo/

app/
browser_agent/
execution/
agenttrust/
metrics/
audit/
comparison/
ui/
tests/
docs/
```

### Exit Criteria

Running

```bash
python demo.py
```

prints

```
Browser Agent Demo Initialized
```

---

# Milestone 2 — Build Browser Agent

## Goal

Create a working Browser Agent without AgentTrust.

### Components

Search Tool

↓

Browser Tool

↓

HTML Extractor

↓

Ollama

↓

Structured Summary

### Tasks

Implement

* DuckDuckGo search
* Browser fetch
* HTML extraction
* Markdown conversion
* Ollama integration
* Summary generation

### Test

Ask

```
Summarize the latest MCP updates
```

Expected

* Search works
* Browser works
* Ollama responds
* Sources returned

### Exit Criteria

Working Browser Agent.

Nothing related to AgentTrust yet.

---

# Milestone 3 — Refactor into Execution Engine

Current

```
Search()

Browser()

Summarize()
```

New

```
Execution Engine

↓

Planning

↓

Search

↓

Browser

↓

Extract

↓

Reason

↓

Response
```

### Tasks

Create

* ExecutionEngine
* ExecutionStep
* ExecutionEvent
* ExecutionContext
* ExecutionTrace

Every execution step should emit events.

### Deliverables

```
trace.json
```

generated automatically.

---

# Milestone 4 — Build Execution Timeline

Goal

Visualize execution.

Current

```
Done.
```

New

```
Planning

120 ms

Search

430 ms

Browser

510 ms

Extraction

320 ms

Reasoning

1800 ms

Finished
```

### Tasks

Implement

* Timeline renderer
* Console renderer
* JSON trace exporter

### Exit Criteria

Every execution displays a timeline.

---

# Milestone 5 — Browser Agent Visualization

Goal

Visualize how Browser Agent works.

Render

```
User

↓

Planning

↓

Search

↓

Browser

↓

Extract

↓

LLM

↓

Summary
```

### Tasks

Create

* Node model
* Graph renderer
* Mermaid generator

### Exit Criteria

Automatically generate workflow diagrams.

---

# Milestone 6 — Introduce AgentTrust Middleware

This is the first governance milestone.

Current

```
BrowserAgent

↓

Response
```

New

```
BrowserAgent

↓

TrustMiddleware

↓

Response
```

### Tasks

Create

* TrustMiddleware
* ValidationContext
* TrustDecision

Browser Agent should remain untouched.

### Exit Criteria

Middleware wraps BrowserAgent successfully.

---

# Milestone 7 — Input Validation

Validate

* Empty prompts
* Prompt injection
* Oversized prompts
* Invalid inputs

Pipeline

```
User

↓

Input Validator

↓

Browser Agent
```

### Deliverables

Validation report.

---

# Milestone 8 — URL Governance

Validate

* URL format
* Allowed domains
* Dangerous URLs
* Redirect chains

Current

```
Search

↓

Browser
```

New

```
Search

↓

URL Validator

↓

Browser
```

---

# Milestone 9 — Content Governance

Current

```
Browser

↓

LLM
```

New

```
Browser

↓

Sanitizer

↓

Prompt Injection Detector

↓

Content Validator

↓

LLM
```

### Tasks

Implement

* HTML sanitization
* Injection detection
* Content filtering

---

# Milestone 10 — Response Governance

Current

```
LLM

↓

User
```

New

```
LLM

↓

Schema Validation

↓

Citation Validation

↓

Response Validator

↓

User
```

### Deliverables

Validation report.

---

# Milestone 11 — Confidence Engine

Goal

Estimate confidence.

Return

```
Confidence

92

High
```

### Metrics

* source count
* citation quality
* extraction quality
* reasoning completeness

---

# Milestone 12 — Risk Engine

Calculate

```
Low

Medium

High

Critical
```

Based on

* prompt risk
* source quality
* validation failures
* policy violations

---

# Milestone 13 — Policy Engine

Create policy system.

Example

```
Policy

Require Citation

Passed
```

Supported policies

* Required citations
* Minimum confidence
* Allowed domains
* Sensitive data
* Maximum risk

---

# Milestone 14 — Decision Engine

Combine

Confidence

*

Risk

*

Policies

↓

Decision

Supported

```
ALLOW

BLOCK

RETRY

HUMAN REVIEW
```

---

# Milestone 15 — Audit Logging

Generate

```
audit.jsonl
```

Every execution appends

```
Execution

↓

Decision

↓

Metrics

↓

Audit Event
```

---

# Milestone 16 — Metrics Engine

Collect

Execution metrics

Validation metrics

Policy metrics

Risk metrics

Confidence metrics

Store

```
metrics.json
```

---

# Milestone 17 — Comparison Runner

Run

Without AgentTrust

↓

Capture Trace

Run

With AgentTrust

↓

Capture Trace

↓

Diff

Output

```
WITHOUT

Planning

Search

Browser

Reason

Done

----------------

WITH

Planning

Validation

Search

Injection Scan

Browser

Confidence

Risk

Policies

Audit

Done
```

---

# Milestone 18 — Failure Scenarios

Create reproducible demos.

Scenario 1

Prompt Injection

Scenario 2

Hallucinated Citation

Scenario 3

Broken URL

Scenario 4

Missing Citation

Scenario 5

Sensitive Data

Each runs

Without AgentTrust

With AgentTrust

Compare outcomes.

---

# Milestone 19 — Interactive Dashboard

Build CLI dashboard.

Menu

```
1 Browser Agent

2 AgentTrust Execution

3 Compare

4 Timeline

5 Metrics

6 Audit

7 Policies

8 Failure Demos
```

Render using Rich.

---

# Milestone 20 — Polish

Improve

* Architecture diagrams
* Mermaid diagrams
* Logging
* Documentation
* Screenshots
* Demo GIFs
* Code comments
* README
* CLAUDE.md

---

# Final Deliverable

By the end of the project the demo should include:

✅ Browser Agent powered by Ollama

✅ Execution Engine

✅ Execution Timeline

✅ Execution Trace

✅ Workflow Visualization

✅ AgentTrust Middleware

✅ Input Validation

✅ URL Validation

✅ Content Validation

✅ Response Validation

✅ Confidence Engine

✅ Risk Engine

✅ Policy Engine

✅ Decision Engine

✅ Audit Logger

✅ Metrics Dashboard

✅ Side-by-Side Comparison

✅ Failure Scenario Demonstrations

✅ Interactive CLI

✅ Full Documentation

---

# Development Workflow

For **every milestone**, Claude Code should follow this process:

1. Analyze the requirements for the milestone.
2. Design the architecture before writing code.
3. Implement the feature with clear interfaces and dependency injection.
4. Add unit tests and integration tests.
5. Verify the feature manually using the CLI.
6. Update documentation (architecture notes, Mermaid diagrams, and API documentation).
7. Refactor if necessary before proceeding.
8. Commit the milestone before starting the next one.

No subsequent milestone should begin until the current milestone passes its tests and acceptance criteria.
