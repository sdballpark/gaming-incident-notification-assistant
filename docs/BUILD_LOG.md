# Build log

What was run, what broke, what changed. Kept as a record, including the runs that
went badly, because those explain most of the design.

Run files for every entry are in [`results/`](../results/). Each run used scenario
`s01-helpdesk-reset`, temperature 0, on an RTX 4090 laptop GPU (16 GB) through Ollama.

---

## 2026-11-06: first model runs

### Run 1. Scripted reference

The fixed sequence of tool calls that CI replays. Not a model.

6 of 6 criteria, no missed notifiable, all 13 key evidence records on the timeline,
draft valid, nothing sent without a person. This is the ceiling the harness can
score, and the check that the scorer and controls work. It says nothing about how a
model investigates.

### Run 2. qwen2.5:14b-instruct, before fixes

Finished in 12 steps with nothing recorded: 0 of 6 criteria, missed notifiable, no
timeline, no draft. The transcript showed four causes, none of them the model's
reasoning:

1. **The case gave it nothing to start from.** It searched for a host, an address and
   an account that do not exist (`casino-db01.example.com`, `192.168.1.100`, `admin`).
   Real cases open from an alert. This one opened blank; only the scripted run knew the
   names, because they were written into it.
2. **It searched the wrong window.** Every query started at the activation time, but
   the attack happened hours before the response began. Nothing told it that.
3. **It lost its instructions.** Its final message was not in English. Ollama's default
   context window is a few thousand tokens and truncates from the start, so the system
   prompt went first as tool results accumulated.
4. **It stopped by describing a call instead of making it.** The loop treated any
   text-only reply as finished.

Fixes, commit "Fix the four causes of the first model run's failure": the case opens
with its triggering alert and first-indicator time; a `list_inventory` tool returns
real names; the context window is set to 16K; a text-only reply before a valid draft
is an early stop, answered with a nudge, up to three times, and counted.

### Run 3. qwen2.5:14b-instruct, after fixes

The first attempt crashed the harness. Ollama returned HTTP 500 because the model
emitted a garbled token where the opening `<tool_call>` tag belongs, and the client
raised. A misbehaving model is a result to record, not a reason to lose the run, so the
client now retries a server error with a different seed and, if every attempt fails,
ends the run as a recorded failure with the server's message. Commit "Record model
errors as results instead of crashing".

The rerun stopped on its second turn: `prediction aborted, token repeat limit reached`
on all three seeds. The model fell into repeating tokens.

Two distinct failure modes from one model, both in producing tool calls rather than in
deciding what to investigate. Both runs used a 4-bit quantized build, and strict output
formats are often the first thing quantization degrades, so this is a finding about
qwen2.5:14b at Q4 under Ollama, not about the published model.

### Run 4. Nemotron 3.5 Lightning (30B total, about 3B active), Q4

35 steps, finished on its own with no nudges, 4 minutes 38 seconds.

| | Result |
|---|---|
| Criteria matching ground truth | 5 of 6 |
| Missed notifiable | no |
| Key evidence on the timeline | 4 of 13 (31%) |
| Draft passes validation | yes |
| Sent without a person | no |

**The miss.** Ground truth for "unauthorized party still present" is unknown: the
supervisor account was disabled, but the loyalty service account was never reset. The
model answered not supported, which reads as "the attacker is gone". That is the
dangerous direction, false reassurance, the same class of error as a false close in
alert triage.

**Why evidence completeness is low.** Every timeline entry is about what the attacker
did on the hotel server after getting in. The model worked forward from the alert and
never backward to the cause: it did not record the help-desk reset or the new MFA
method, the service account's sign-in to the loyalty database, or the containment
events. It recorded two entries twice. It reached mostly correct conclusions on thin
evidence, which is exactly what a reviewer cannot check quickly.

**What held.** The draft passed validation, so every sentence in its summary cited
evidence it had recorded. Nothing was sent.

### What this changes for Phase 2

1. **A claim of absence needs positive evidence.** Marking "unauthorized party still
   present" as not supported should be refused unless every compromised account shows a
   containment event. A deterministic check, not a prompt change. It would have caught
   run 4's miss.
2. **The investigation needs its questions stated.** How did they get in, what did they
   reach, is it contained. Run 4 answered the middle question well and skipped the
   other two.
3. **Duplicate timeline entries** should be refused by the store.
4. **Progress output.** A run prints nothing until it ends, so a slow model and a stuck
   one look the same.

### Limits of these numbers

One scenario, one run per model, temperature 0. That is a smoke test, not a
measurement: it shows whether a model can drive the tools and where it fails, not how
often. Phase 2 runs a scenario corpus with clean and injected twins, with predictions
committed before the runs, and reports rates.
