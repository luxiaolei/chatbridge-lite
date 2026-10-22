"""Conservative CLI for thin Web↔Chat / Codex↔Chat agent orchestration."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

from .core import (
    Ledger, LiteError, build_dispatch, build_report, callback_message, digest, invoke,
    monitor_decision, read_operation_id, reason_args, validate_mode, worker_contract
)


def emit(**values: object) -> None:
    print(json.dumps(values, ensure_ascii=False, sort_keys=True))


def read_message(args: argparse.Namespace) -> str:
    if args.message_file:
        return Path(args.message_file).read_text(encoding="utf-8")
    if args.message is not None:
        return args.message
    raise LiteError("provide --message or --message-file")


def doctor(args: argparse.Namespace) -> int:
    checks = {x: bool(shutil.which(name)) for x, name in (("bridge", args.bridge_bin), ("reason_network", args.reason_bin), ("ego_browser", args.ego_bin))}
    emit(ok=checks["bridge"] and checks["ego_browser"], dependencies=checks,
         guidance=["Recommended local-computer connector: Remote Desktop Commander. Pair the device and connect the ChatGPT app; see https://github.com/desktop-commander/remote-desktop-commander and docs/REMOTE-SETUP.md.",
                   "This alpha still requires Ego Lite / ego-browser for ChatGPT Web dispatch; Remote Desktop Commander does not replace that runtime.",
                   "Advanced Linux-focused alternative: https://github.com/luxiaolei/chatgpt-open-remote-mcp (Secure MCP Tunnel and explicit grants require extra setup).",
                   "Browser Use can be evaluated separately, but is not a validated drop-in replacement.",
                   "For Codex-controller mode also install and configure Reason Network on the receiving machine.",
                   "Verify the exact paired host and plugin permissions in ChatGPT; a local executable check cannot prove remote connectivity. Check current Remote Desktop Commander usage limits/pricing in its dashboard."])
    return 0 if checks["bridge"] and checks["ego_browser"] else 2


def dispatch(args: argparse.Namespace) -> int:
    msg = read_message(args)
    envelope = worker_contract(msg, mode=args.mode, task=args.task, reason_to=args.reason_to)
    cmd, request_id = build_dispatch(mode=args.mode, controller=args.controller, project=args.project,
                                      worker_session=args.worker_session, task=args.task, message=envelope,
                                      request_id=args.request_id, bridge_bin=args.bridge_bin)
    if not args.execute:
        emit(ok=True, preview=True, mode=args.mode, task=args.task, request_id=request_id, to=args.worker_session,
             message_sha256=digest(envelope), action="Bridge queue submit; no send performed")
        return 0
    key = "dispatch:" + args.task
    fp = digest([args.mode, args.controller, args.project, args.worker_session, envelope, request_id, args.reason_to or ""])
    with Ledger(args.state_db) as ledger:
        saved = ledger.reserve(key, fp)
        if saved["phase"] != "PREPARED":
            emit(ok=False, task=args.task, state=saved["phase"], warning="Previous attempt exists. Not replayed.")
            return 3
        if not ledger.transition(key, "PREPARED", "DISPATCH_IN_FLIGHT"):
            raise LiteError("concurrent dispatch; not repeated")
        receipt = invoke(cmd, timeout=args.timeout)
        if receipt.ok:
            op = read_operation_id(receipt.stdout)
            ledger.transition(key, "DISPATCH_IN_FLIGHT", "QUEUED_IN_BRIDGE", op)
            emit(ok=True, task=args.task, request_id=request_id, bridge_submitted=True,
                 operation_id=op, note="Queued is not proven Web delivery; check Bridge operation status.")
            return 0
        # A timeout/unknown process response can follow Send; fail closed.
        phase = "DISPATCH_UNKNOWN" if receipt.timed_out or receipt.returncode != 127 else "DISPATCH_PRE_SEND_FAILED"
        ledger.transition(key, "DISPATCH_IN_FLIGHT", phase)
        emit(ok=False, task=args.task, state=phase, warning="Do not blindly re-submit; reconcile the original Bridge operation.")
        return 4


def report(args: argparse.Namespace) -> int:
    mode = validate_mode(args.mode)
    summary = read_message(args)
    command = build_report(task=args.task, status=args.status, summary=summary, evidence=args.evidence or "",
                           bridge_bin=args.bridge_bin)
    if mode == "codex" and not args.reason_to:
        raise LiteError("--reason-to is required for codex callback")
    body = callback_message(task=args.task, version=args.result_version, status=args.status, summary=summary,
                            blockers=args.blockers or "", evidence=args.evidence or "")
    if not args.execute:
        emit(ok=True, preview=True, mode=mode, task=args.task, status=args.status, summary_sha256=digest(summary),
             reason_target=args.reason_to if mode == "codex" else None,
             action="Durable Bridge result then Reason Network wake-up only for Codex")
        return 0
    key = f"result:{args.task}:{args.result_version}"
    fp = digest([mode, args.task, args.result_version, args.status, summary, args.blockers or "",
                 args.evidence or "", args.reason_to or ""])
    with Ledger(args.state_db) as ledger:
        saved = ledger.reserve(key, fp)
        if saved["phase"] == "PREPARED":
            if not ledger.transition(key, "PREPARED", "RESULT_IN_FLIGHT"):
                raise LiteError("concurrent result; not replayed")
            result = invoke(command, timeout=args.timeout)
            if result.ok:
                ledger.transition(key, "RESULT_IN_FLIGHT", "RESULT_RECORDED")
                saved["phase"] = "RESULT_RECORDED"
            else:
                phase = "RESULT_UNKNOWN" if result.timed_out or result.returncode != 127 else "RESULT_PRE_SEND_FAILED"
                ledger.transition(key, "RESULT_IN_FLIGHT", phase)
                emit(ok=False, task=args.task, state=phase,
                     warning="No Reason notification sent; verify durable result before any retry.")
                return 4
        if saved["phase"] != "RESULT_RECORDED":
            emit(ok=False, task=args.task, state=saved["phase"],
                 warning="Existing attempt not replayed. Only a confirmed RESULT_RECORDED may proceed to notification.")
            return 3
        if mode == "chat":
            ledger.transition(key, "RESULT_RECORDED", "CHAT_CALLBACK_QUEUED")
            emit(ok=True, task=args.task, state="CHAT_CALLBACK_QUEUED",
                 note="Bridge owns the Chat callback; controller acceptance/ACK is separate.")
            return 0
        if not ledger.transition(key, "RESULT_RECORDED", "REASON_IN_FLIGHT"):
            raise LiteError("concurrent Reason notification; not repeated")
        send = invoke(reason_args(args.reason_to, reason_bin=args.reason_bin), stdin=body, timeout=args.timeout)
        if send.ok:
            ledger.transition(key, "REASON_IN_FLIGHT", "REASON_SUBMITTED")
            emit(ok=True, task=args.task, state="REASON_SUBMITTED",
                 note="Message submitted; only the original Codex owner can prove processing/ACK.")
            return 0
        state = "REASON_UNKNOWN" if send.timed_out or send.returncode != 127 else "REASON_PRE_SEND_FAILED"
        ledger.transition(key, "REASON_IN_FLIGHT", state)
        emit(ok=False, task=args.task, state=state,
             warning="Result is already durable. Do not repeat Reason send without independent reconciliation.")
        return 4


def monitor(args: argparse.Namespace) -> int:
    if args.snapshot_file and args.execute:
        raise LiteError("Cannot execute recovery from a file snapshot; require fresh live observation")
    if args.snapshot_file:
        raw = Path(args.snapshot_file).read_text(encoding="utf-8")
        observation = json.loads(raw)
    else:
        if not (args.project and args.worker_session and args.task):
            raise LiteError("monitor requires --snapshot-file or project, worker-session and task")
        receipt = invoke([args.bridge_bin, "status", args.worker_session, "--project", args.project, "--task", args.task],
                         timeout=args.timeout)
        if not receipt.ok:
            emit(ok=False, action="OBSERVE_ONLY", reason="Bridge status unavailable; no recovery sent")
            return 4
        try:
            observation = json.loads(receipt.stdout)
        except json.JSONDecodeError:
            emit(ok=False, action="OBSERVE_ONLY", reason="Bridge status not JSON; no recovery sent")
            return 4
    if not isinstance(observation, dict):
        raise LiteError("monitor snapshot must be JSON object")
    action, reason = monitor_decision(observation)
    if action != "RECOVER_ELIGIBLE" or not args.execute:
        emit(ok=True, action=action, reason=reason, executed=False)
        return 0
    if not (args.project and args.worker_session and args.task):
        emit(ok=False, action="OBSERVE_ONLY", reason="exact task route required before recovery")
        return 4
    receipt = invoke([args.bridge_bin, "recover", args.worker_session, "--project", args.project, "--task", args.task],
                     timeout=args.timeout)
    emit(ok=receipt.ok, action="GUARDED_RECOVER_CALLED" if receipt.ok else "RECOVERY_UNCERTAIN",
         reason="Bridge performs its own fresh UI/owner/delivery checks; no Retry or Resend issued by Lite",
         executed=True)
    return 0 if receipt.ok else 4


def status(args: argparse.Namespace) -> int:
    with Ledger(args.state_db) as ledger:
        found = ledger.status(args.key)
    emit(ok=found is not None, key=args.key, record=found)
    return 0 if found else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cblite", description="Small, opt-in bridge over verified ChatGPT sessions")
    parser.add_argument("--state-db", type=Path, help="Local private ledger location (default ~/.local/state/chatbridge-lite)")
    parser.add_argument("--bridge-bin", default=os.environ.get("CBLITE_BRIDGE_BIN", "chat-bridge"))
    parser.add_argument("--reason-bin", default=os.environ.get("CBLITE_REASON_BIN", "reason-network"))
    parser.add_argument("--timeout", type=int, default=120)
    subs = parser.add_subparsers(dest="command", required=True)
    d = subs.add_parser("doctor", help="Local dependencies and guided setup; no browser operation")
    d.add_argument("--ego-bin", default=os.environ.get("CBLITE_EGO_BIN", "ego-browser"))
    d.set_defaults(fn=doctor)
    p = subs.add_parser("dispatch", help="Durable task dispatch, preview by default")
    p.add_argument("--mode", choices=["chat", "codex"], required=True)
    p.add_argument("--project", required=True)
    p.add_argument("--controller", required=True)
    p.add_argument("--worker-session", required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--request-id")
    p.add_argument("--reason-to", help="Private Codex callback destination; never embed in public config")
    mg = p.add_mutually_exclusive_group(required=True)
    mg.add_argument("--message")
    mg.add_argument("--message-file")
    p.add_argument("--execute", action="store_true")
    p.set_defaults(fn=dispatch)
    r = subs.add_parser("report", help="Worker durable result; Codex wake via Reason Network")
    r.add_argument("--mode", choices=["chat", "codex"], required=True)
    r.add_argument("--task", required=True)
    r.add_argument("--result-version", type=int, default=1)
    r.add_argument("--status", choices=["COMPLETE", "BLOCKED", "FAILED"], required=True)
    r.add_argument("--blockers")
    r.add_argument("--evidence")
    r.add_argument("--reason-to")
    mg = r.add_mutually_exclusive_group(required=True)
    mg.add_argument("--message", help="Result summary")
    mg.add_argument("--message-file")
    r.add_argument("--execute", action="store_true")
    r.set_defaults(fn=report)
    w = subs.add_parser("monitor", help="Read current evidence and suggest guarded same-task recovery")
    w.add_argument("--snapshot-file")
    w.add_argument("--project")
    w.add_argument("--worker-session")
    w.add_argument("--task")
    w.add_argument("--execute", action="store_true")
    w.set_defaults(fn=monitor)
    s = subs.add_parser("status", help="Read private Lite attempt ledger, not ChatGPT live state")
    s.add_argument("key", help="dispatch:TASK_ID or result:TASK_ID:VERSION")
    s.set_defaults(fn=status)
    args = parser.parse_args(argv)
    if args.timeout < 1 or args.timeout > 600:
        parser.error("--timeout must be 1..600 seconds")
    try:
        return args.fn(args)
    except (LiteError, OSError, ValueError, json.JSONDecodeError) as exc:
        emit(ok=False, error=type(exc).__name__, message=str(exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
