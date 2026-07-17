# AgentTrust Session Report

**Generated:** 2026-07-17 18:57:52 UTC

## Executive Summary

| Metric | Value |
|--------|-------|
| Total governed runs | 2 |
| Allowed | 2 (100%) |
| Blocked | 0 (0%) |
| Escalated | 0 (0%) |
| Avg confidence | 93.0/100 |
| Avg latency | 30,210 ms |
| Total violations | 0 |
| Most common risk | LOW |

## Audit Log

| Timestamp | Decision | Confidence | Risk | Violations |
|-----------|----------|------------|------|------------|
| 2026-07-17 18:52:55 | ALLOW | 93 | LOW | — |
| 2026-07-17 18:55:50 | ALLOW | 93 | LOW | — |

## Governance Metrics

| Metric | Avg | Last | Count |
|--------|-----|------|-------|
| governance.input.confidence | 95.0 | 95.0 | 1 |
| governance.input.decision.allow | 1.0 | 1.0 | 1 |
| governance.input.decision.block | 0.0 | 0.0 | 1 |
| governance.input.decision.review | 0.0 | 0.0 | 1 |
| governance.input.policy_score | 100.0 | 100.0 | 1 |
| governance.input.risk | 0.0 | 0.0 | 1 |
| governance.input.violations | 0.0 | 0.0 | 1 |
| governance.output.confidence | 93.0 | 93.0 | 1 |
| governance.output.decision.allow | 1.0 | 1.0 | 1 |
| governance.output.decision.block | 0.0 | 0.0 | 1 |
| governance.output.decision.review | 0.0 | 0.0 | 1 |
| governance.output.policy_score | 100.0 | 100.0 | 1 |
| governance.output.risk | 0.0 | 0.0 | 1 |
| governance.output.violations | 0.0 | 0.0 | 1 |
| governance.overhead_ms | 0.0 | 0.0 | 1 |
| run.allowed | 1.0 | 1.0 | 1 |
| step.browser.ms | 2132.8 | 2012.1 | 2 |
| step.extraction.ms | 97.7 | 101.7 | 2 |
| step.planning.ms | 0.2 | 0.2 | 2 |
| step.reasoning.ms | 64553.4 | 67818.9 | 2 |

## Comparison Run

**Query:** What is a deep agent?

| | Without AgentTrust | With AgentTrust |
|--|--|--|
| Latency | 0 ms | 0 ms |
| Decision | — | ALLOW |
| Overhead | — | 0 ms |
