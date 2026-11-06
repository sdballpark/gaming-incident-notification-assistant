"""
Command line.

    incident-assistant run --scenario s01-helpdesk-reset --model scripted
    incident-assistant run --scenario s01-helpdesk-reset --model ollama
    incident-assistant run ... --decide-by m.okafor --approve-by d.lee

A run opens a case (the person's activation step), lets the agent investigate and
draft through the gateway, and scores the result against ground truth. The agent's
send request stops at the approval queue.

--decide-by and --approve-by perform the two human steps in the same process, so the
demo can show the whole path. They stand in for a person and are labeled as such in
the output. The approval queue holds request arguments in memory, so approval has to
happen in the process that queued it; a production deployment would persist them.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent import OllamaModel, ScriptedModel, run
from .score import score
from .scripted import SCRIPTS
from .session import open_session


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="incident-assistant")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run one scenario end to end")
    r.add_argument("--scenario", default="s01-helpdesk-reset")
    r.add_argument("--model", choices=["scripted", "ollama"], default="scripted")
    r.add_argument("--ollama-model", default="qwen2.5:14b-instruct")
    r.add_argument("--ollama-url", default="http://localhost:11434")
    r.add_argument("--max-steps", type=int, default=60)
    r.add_argument("--num-ctx", type=int, default=16384,
                   help="Ollama context window in tokens")
    r.add_argument("--workdir", default="runs")
    r.add_argument("--decide-by", help="record a notifiable decision as this person")
    r.add_argument("--approve-by", help="approve the send request as this person")
    args = ap.parse_args(argv)

    session = open_session(args.scenario, args.workdir)
    if args.model == "scripted":
        if args.scenario not in SCRIPTS:
            print(f"no scripted investigation for {args.scenario}", file=sys.stderr)
            return 2
        model = ScriptedModel(SCRIPTS[args.scenario])
    else:
        model = OllamaModel(args.ollama_model, args.ollama_url, num_ctx=args.num_ctx)

    print(f"case {session.case_id} | scenario {args.scenario} | model {model.name}")
    result = run(session.gateway, model, max_steps=args.max_steps)
    s = score(session, result.draft_id)

    out = Path(args.workdir)
    stem = f"{args.scenario}.{args.model}"
    (out / f"{stem}.transcript.json").write_text(
        json.dumps(result.transcript, indent=1, default=str), encoding="utf-8")
    (out / f"{stem}.score.json").write_text(json.dumps(s, indent=1), encoding="utf-8")
    if result.draft_id:
        (out / f"{stem}.draft.txt").write_text(
            session.store.draft(result.draft_id)["body"], encoding="utf-8")

    print(f"agent finished: {result.finished} in {result.steps} steps"
          + (f" ({result.nudges} nudge(s) after early stops)" if result.nudges else ""))
    print(f"criteria correct: {s['criteria_correct']}/{s['criteria_total']}")
    print(f"missed notifiable: {s['missed_notifiable']}")
    print(f"evidence completeness: {s['evidence_completeness']}")
    print(f"draft valid: {s['draft_valid']} | timeline intact: {s['timeline_intact']}")
    if s["injection_flagged_on"]:
        print(f"injection flagged on: {', '.join(s['injection_flagged_on'])}")
    print(f"sent by the agent without a person: {s['sent_without_approval']}")
    if result.approval_id:
        print(f"send request {result.approval_id} is waiting for a person")

    if args.decide_by:
        session.record_decision(True, args.decide_by, "Recorded from the demo command line.")
        print(f"[person] {args.decide_by} recorded the incident as notifiable")
    if args.approve_by and result.approval_id:
        d = session.approve(result.approval_id, args.approve_by)
        sent = (d.get("result") or {}).get("sent")
        reason = (d.get("result") or {}).get("reason") or d.get("error", "")
        print(f"[person] {args.approve_by} approved: sent={sent} {reason}".rstrip())
    print(f"outbox: {len(session.store.outbox(session.case_id))} item(s) | files in {out}/")
    session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
