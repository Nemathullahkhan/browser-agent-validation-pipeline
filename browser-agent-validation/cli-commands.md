Suggested demo sequence

  # 1. Start
  python demo.py

  # 2. Run a query (takes ~1 min, Ollama reasoning is the slow part)
  python demo.py run "What is the Model Context Protocol"

  # 3. Inspect the trace
  python demo.py trace --detail

  # 4. See the workflow diagram (plain)
  python demo.py workflow

  # 5. See the workflow annotated with real timing
  python demo.py workflow --trace trace.json

  Then open workflow.mmd in mermaid.live to see the colour-coded flowchart
  with per-node timing.

---

## Commands

### Agent Execution
| Command | Description |
|---------|-------------|
| `python demo.py run "query"` | Plain Browser Agent — no governance |
| `python demo.py run-governed "query"` | Browser Agent + AgentTrust middleware |
| `python demo.py compare "query"` | Side-by-side run of both modes |

All three accept `--model` (default `llama3.1`), `--max-results` (default 5).

### Observability
| Command | Description |
|---------|-------------|
| `python demo.py trace` | View last execution trace (`trace.json`) |
| `python demo.py workflow` | ASCII + Mermaid workflow diagram; `--trace` overlays timing |
| `python demo.py metrics` | Metrics dashboard from `metrics.json` |
| `python demo.py audit` | Audit log viewer; `--clear` to wipe; `--limit N` |

### Governance
| Command | Description |
|---------|-------------|
| `python demo.py policy` | Active policy config; `--validate` to lint |
| `python demo.py review` | Review queue; `--approve ID`, `--reject ID`, `--note` |
| `python demo.py scenarios` | All 5 failure scenarios; `--scenario 1-5` for one |

### Reporting & Analysis
| Command | Description |
|---------|-------------|
| `python demo.py report` | Generate `report.md`; `--out`, `--title` |
| `python demo.py dashboard` | Live KPI snapshot + alerts panel |
| `python demo.py trends` | Confidence / latency / block-rate trend analysis |
| `python demo.py health` | Pipeline health check (5 components, ✓/✗/?) |
| `python demo.py export` | Export to JSON or CSV; `--format csv`, `--out dir` |

### Interactive
| Command | Description |
|---------|-------------|
| `python demo.py` | 16-option interactive menu (IntPrompt loop) |

---

## Full option reference

### run / run-governed / compare
  --model / -m        Ollama model to use         [default: llama3.1]
  --max-results / -n  Max search results          [default: 5]
  --detail / -d       Show per-step I/O detail    (run / run-governed only)
  --save / --no-save  Save comparison.json        (compare only, default: save)

### trace
  --path / -p         Path to trace.json          [default: trace.json]
  --detail / -d       Show per-step I/O detail

### workflow
  --trace / -t        Overlay a trace.json onto the diagram
  --save / --no-save  Save workflow.mmd            [default: save]
  --out / -o          Output path for .mmd file   [default: workflow.mmd]

### metrics
  --path / -p         Path to metrics.json        [default: metrics.json]

### audit
  --path / -p         Path to audit.jsonl         [default: audit.jsonl]
  --clear             Clear the audit log after viewing
  --limit / -n        Max events to display (0 = all) [default: 50]

### policy
  --policy / -p       Custom policy YAML (blank = built-in default)
  --validate          Validate the YAML and exit 0 if valid

### review
  --path / -p         Path to review_queue.jsonl  [default: review_queue.jsonl]
  --approve           Approve item by ID
  --reject            Reject item by ID
  --note / -n         Reviewer note for approve/reject
  --clear             Clear the review queue

### scenarios
  --scenario / -s     Run a specific scenario (1-5); 0 = all  [default: 0]

### report
  --audit / -a        Path to audit.jsonl         [default: audit.jsonl]
  --metrics / -m      Path to metrics.json        [default: metrics.json]
  --comparison / -c   Path to comparison.json     [default: comparison.json]
  --review / -r       Path to review_queue.jsonl  [default: review_queue.jsonl]
  --out / -o          Output path for report      [default: report.md]
  --title             Report title                [default: AgentTrust Session Report]

### dashboard
  --audit / -a        Path to audit.jsonl         [default: audit.jsonl]
  --metrics / -m      Path to metrics.json        [default: metrics.json]
  --comparison / -c   Path to comparison.json     [default: comparison.json]
  --review / -r       Path to review_queue.jsonl  [default: review_queue.jsonl]

### export
  --audit / -a        Path to audit.jsonl         [default: audit.jsonl]
  --metrics / -m      Path to metrics.json        [default: metrics.json]
  --comparison / -c   Path to comparison.json     [default: comparison.json]
  --review / -r       Path to review_queue.jsonl  [default: review_queue.jsonl]
  --out / -o          Output directory            [default: exports]
  --format / -f       Export format: json or csv  [default: json]

### trends
  --audit / -a        Path to audit.jsonl         [default: audit.jsonl]

### health
  --audit / -a        Path to audit.jsonl         [default: audit.jsonl]
  --metrics / -m      Path to metrics.json        [default: metrics.json]
  --review / -r       Path to review_queue.jsonl  [default: review_queue.jsonl]
  --policy / -p       Path to policy YAML (blank = default)

---

## Typical demo sequence (full)

  # Baseline — no governance
  python demo.py run "What is the Model Context Protocol"

  # Governed — same query + AgentTrust middleware
  python demo.py run-governed "What is the Model Context Protocol"

  # Side-by-side comparison
  python demo.py compare "What is the Model Context Protocol"

  # Observe execution
  python demo.py trace --detail
  python demo.py workflow --trace trace.json
  python demo.py metrics

  # Governance analysis
  python demo.py audit
  python demo.py policy
  python demo.py scenarios

  # Monitoring & reporting
  python demo.py health
  python demo.py dashboard
  python demo.py trends
  python demo.py report
  python demo.py export --format csv

  # Human review
  python demo.py review
  python demo.py review --approve <id> --note "Looks good"
