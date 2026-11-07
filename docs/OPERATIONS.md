# Operations guide

Version 1.0, 2026-11-07.

How to install, run, read, extend and troubleshoot the assistant as built. Production
operation needs the controls listed in [SECURITY.md](SECURITY.md) section 10 first.

> **Operating rule.** This build is for synthetic scenarios only. It does not
> authenticate people, encrypt data at rest, or persist pending approvals. Do not load
> real incident data into it.

---

## 1. Prerequisites

| Need | Version | Used for |
|---|---|---|
| Python | 3.11 or later | Everything |
| Network access to GitHub at install time | | Installing itops-mcp-gateway from its tagged release |
| Ollama | Current | Model runs only. Not needed for tests, CI or the scripted investigation |
| NVIDIA GPU | 16 GB recommended | Model runs at useful speed |

## 2. Install and verify

```bash
git clone https://github.com/sdballpark/gaming-incident-notification-assistant.git
cd gaming-incident-notification-assistant
python -m venv .venv && . .venv/bin/activate      # or: uv venv && uv pip install ...
pip install -e ".[test]"
python -m pytest -q                                # expect: 63 passed
```

The install pulls itops-mcp-gateway at tag `v1.2.0`. If it fails, check that GitHub is
reachable from the machine.

## 3. Running a case

### 3.1 Scripted investigation (no GPU)

```bash
incident-assistant run --scenario s01-helpdesk-reset
```

The scripted investigation replays a fixed sequence of tool calls through the real
gateway. Use it to check that the controls work. It is not a measure of a model.

### 3.2 With a local model

```bash
ollama pull qwen2.5:14b-instruct        # or any tool-calling model
incident-assistant run --scenario s01-helpdesk-reset \
    --model ollama --ollama-model qwen2.5:14b-instruct
```

The published Nemotron runs used `nemotron-lightning-q4-32k`, a local Ollama model built,
as in the companion evaluation lab, from the ggml-org Q4_0 GGUF of NVIDIA Nemotron 3.5
Lightning with a 32K context. The repository does not record its digest (SECURITY.md R-6). It is
not in the public Ollama library; create it from the GGUF with a Modelfile.

| Option | Default | Notes |
|---|---|---|
| `--ollama-url` | `http://localhost:11434` | Keep it local unless the endpoint is inside the operator's boundary |
| `--num-ctx` | `16384` | Context window in tokens. Too small and the model loses its instructions mid-run |
| `--max-steps` | `60` | Each step is one model turn |
| `--quiet` | off | Suppresses the per-step progress lines |
| `--workdir` | `runs` | Where run files go. Ignored by git |

Each step prints as it happens:

```
   15 add_timeline_entry           validation_failed: this evidence is already on the timeline...
   20 set_criterion_assessment     validation_failed: not_supported claims gaming operations...
```

A `validation_failed` line is usually a control doing its job. The model sees the reason
and is expected to correct itself.

### 3.3 The human steps

A run stops at the approval queue. To show the full path in one process:

```bash
incident-assistant run --scenario s01-helpdesk-reset \
    --decide-by m.okafor --approve-by d.lee
```

`--decide-by` records the incident as notifiable under that name. `--approve-by`
approves the agent's send request under that name. Both stand in for people and are
labeled `[person]` in the output. Approval must happen in the same process that queued
the request, because pending request arguments are held in memory.

Without `--decide-by`, approval runs the handler and it refuses to send. That is
intended.

## 4. Reading the output

### 4.1 Console summary

| Line | Meaning | Healthy value |
|---|---|---|
| `agent finished` | The model stopped on its own with a valid draft | `True`; nudges, if any, are shown |
| `criteria correct` | Assessments matching ground truth, out of six | 6/6 |
| `missed notifiable` | Ground truth supports a trigger element and the run supported none | `False`. This is the metric that matters most |
| `evidence completeness` | Share of ground truth's key evidence recorded on the timeline | Higher is better. Published runs: 0.0 to 1.0; Nemotron 0.31 and 0.46 |
| `draft valid` | A draft passed validation and was saved | `True` |
| `timeline intact` | Hash chain verifies | Always `True` |
| `injection flagged on` | Evidence rows whose text read as instructions | The payload row in an injected twin; nothing in a clean scenario |
| `sent by the agent without a person` | Anything reached the outbox before the human steps | Always `False` |

### 4.2 Run files

Written to `runs/`, named `<scenario>.<model-tag>.*`. The model tag is `scripted`, or the
Ollama model name with `:` and `/` replaced by `_`.

| File | Contents |
|---|---|
| `<scenario>.db` | Case store: telemetry, timeline, assessments, drafts, decisions, outbox |
| `<scenario>.gateway.db` | Gateway audit log and approval records |
| `*.transcript.json` | Every tool call, its arguments and result; nudges; model errors |
| `*.score.json` | The score against ground truth, per criterion |
| `*.draft.txt` | The rendered initial notification, when one was saved |

Each run of the same scenario replaces the previous `.db` files.

### 4.3 Quick diagnosis of a run

```bash
python - <<'EOF'
import json
f = "runs/s01-helpdesk-reset.nemotron-lightning-q4-32k_latest"
s = json.load(open(f + ".score.json"))
for c, v in s["per_criterion"].items():
    print("OK  " if v["correct"] else "MISS", c, "expected", v["expected"], "got", v["actual"])
print("missing evidence:", s["key_evidence_missing"])
EOF
```

## 5. Publishing results

Evidence goes in before interpretation.

1. Copy the run files into `results/<date>/`, numbered in run order, for example
   `results/2026-11-06/4-nemotron-lightning.score.json`.
2. Commit those files on their own.
3. Then write the entry in [BUILD_LOG.md](BUILD_LOG.md) and update the README table, in a
   separate commit. Record what failed, what changed, and what the run does not prove.

## 6. Continuous integration

`.github/workflows/ci.yml` runs on pushes to main, on pull requests and on manual dispatch, without a GPU:

1. Install the package and test dependencies.
2. Rebuild the regulation corpus from the committed source text and fail if the result
   differs from the committed corpus.
3. Run the test suite.
4. Run the clean scenario end to end through decision and approval, and the injected
   twin.

| CI failure | Likely cause | Action |
|---|---|---|
| Corpus rebuild shows a diff | `scripts/build_corpus.py` or the source text changed | Confirm the change was intended; commit the rebuilt corpus with it |
| A control test fails | A change weakened a control | Treat as a security regression. Do not adjust the test to pass |
| Install fails | GitHub unreachable, or the gateway tag moved | Re-run; tags should never move |

## 7. Maintenance procedures

### 7.1 Adding a scenario

1. Create `src/incident_assistant/data/scenarios/<name>.json` with: `scenario`, `title`,
   `synthetic: true`, `operator`, `description`, `activation` (`activated_at`,
   `activated_by`), `alert` (including `first_indicator_at` and `evidence_ids`), the four
   telemetry lists, `assets`, `identities`, `data_inventory`, and `ground_truth`.
2. Give every telemetry row an evidence ID unique across all four tables: `SIG-`, `PRC-`,
   `NET-` or `AUD-` plus four digits. Loading refuses duplicates.
3. Write ground truth for all six criteria, each with a status and its key evidence. Use
   `unknown` where the evidence genuinely does not settle it.
4. For containment, use audit actions the absence check recognizes: `account_disabled`,
   `credentials_rotated`, `sessions_revoked`, `account_locked`.
5. Create an injected twin: identical, except a payload in one text field. Record which
   row carries it.
6. Optionally add a scripted investigation to `scripted.py` so CI can run the scenario.
7. Run `python -m pytest -q` and the scripted scenario before committing.

### 7.2 Rebuilding the regulation corpus

Only when the Board publishes a new adopted text.

```bash
# download the adopted PDF from the Gaming Control Board and record its checksum
sha256sum regulation.pdf
python -c "from pypdf import PdfReader; r=PdfReader('regulation.pdf'); \
  open('source.txt','w').write('\n'.join(p.extract_text() for p in r.pages))"
cp source.txt src/incident_assistant/data/corpus/<new-name>.source.txt
python scripts/build_corpus.py src/incident_assistant/data/corpus/<new-name>.source.txt <pdf-sha256>
```

The build fails if deleted text survives, if the number 72 appears, if section 4(a) does
not read as the 24-hour rule, or if any expected section is missing. A new rule may
require updating those checks; do that deliberately, in the same commit, and update the
CI step's file name and checksum.

### 7.3 Upgrading the gateway

1. Read the gateway's release notes for the new tag.
2. Change the pin in `pyproject.toml`.
3. Reinstall and run the full test suite. Pay attention to `test_controls.py`.
4. Commit the pin change on its own, naming both versions.

## 8. Troubleshooting

These are the failures seen in practice, with what fixed them.

| Symptom | Cause | Fix |
|---|---|---|
| The model queries hosts or accounts that do not exist | It had nothing to start from | Scenario needs an `alert`; the model should call `get_case` and `list_inventory` first |
| The model searches only after the activation time and finds nothing | Attacker activity precedes activation | The case tells the model to search before the alert's first indicator; check the scenario's `first_indicator_at` |
| The model's final message is in another language, or it forgets instructions | The context window is too small and truncated the system prompt | Keep `--num-ctx` at 16384 or higher if GPU memory allows |
| `stopped on a model error after retries: HTTP 500 ... error parsing tool call` | The model emitted a malformed tool-call tag | The harness already retried with new seeds. Use a model with more reliable tool calling |
| `HTTP 500 ... token repeat limit reached` | The model fell into a repetition loop | Recorded as the run's result. Try another model; do not raise the limit to hide it |
| No output for a long time | Older version without progress lines, or the model is partly on CPU | Run `ollama ps` and check the PROCESSOR column; a CPU/GPU split is much slower |
| `connection refused` on port 11434 in WSL | Ollama not running in WSL, or a Windows-side Ollama holding the port | Start the WSL service; stop the Windows tray instance |
| `pending arguments unavailable; re-request the action` on approval | The process that queued the request ended | Expected after a restart. Run the case again and approve in the same process |
| `the notifiability decision must be recorded by a person` | A name ending in `_agent` was given | Use a person's identifier |
| `activated_at must include a timezone offset` when a case opens | The scenario's activation time has no offset | Add an offset, for example `+00:00`. The case refuses to open rather than fail later |

## 9. Housekeeping

- `runs/` is ignored by git. Delete it freely; it is rebuilt by the next run.
- Never commit anything from `runs/` except through the results procedure in section 5.
- Keep Ollama listening on localhost only.

## 10. Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-11-07 | First version |
