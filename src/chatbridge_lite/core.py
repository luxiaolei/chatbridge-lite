"""Core transport, safe persistence, and restart-tolerant callback decisions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import subprocess
from typing import Any


class LiteError(RuntimeError):
    pass


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_atom(value: str, name: str) -> str:
    if not value or len(value) > 512 or any(ord(ch) < 32 for ch in value):
        raise LiteError(f"{name} must be nonempty, <=512 chars and contain no control characters")
    return value


def validate_status(status: str) -> str:
    if status not in {"COMPLETE", "BLOCKED", "FAILED"}:
        raise LiteError("worker status must be COMPLETE, BLOCKED or FAILED")
    return status


def validate_mode(mode: str, controller: str | None = None) -> str:
    if mode not in {"chat", "codex"}:
        raise LiteError("mode must be chat or codex")
    if controller is not None:
        validate_atom(controller, "controller")
        if (mode == "codex") != controller.startswith("codex:"):
            raise LiteError("codex mode requires codex:<thread-id>; chat mode requires a Chat session ref")
    return mode


def worker_contract(message: str, *, mode: str, task: str, reason_to: str | None = None) -> str:
    """An explicit one-action callback instruction; don't double-submit queue result."""
    validate_mode(mode)
    validate_atom(task, "task")
    if mode == "codex":
        if not reason_to:
            raise LiteError("codex dispatch must include the exact private Reason recipient")
        reason_args(reason_to)
    args = ["cblite", "report", "--mode", mode, "--task", task,
            "--status", "COMPLETE", "--message", "<ACTUAL_RESULT_SUMMARY>"]
    if mode == "codex":
        args += ["--reason-to", reason_to]
    args += ["--execute"]
    command = " ".join(shlex.quote(item) for item in args)
    return (message.rstrip() + "\n\n[CHATBRIDGE_LITE_WORKER_CONTRACT_V1]\n"
            "After completing the authorized task, submit the durable result and, in codex mode, wake the original owner.\n"
            "Run the Lite REPORT action ONCE instead of separately running queue result; this action records the result first.\n"
            f"Use this command with your actual result summary and evidence: {command}\n"
            "Use --status BLOCKED and a precise blocker if the work cannot safely finish.\n"
            "Never claim COMPLETE without evidence, repeat an unknown send, or bypass current human approval.\n"
            "The original owning controller must verify and ACK before task/business completion.\n")


def build_dispatch(*, mode: str, controller: str, project: str, worker_session: str, task: str, message: str, request_id: str | None = None, bridge_bin: str = "chat-bridge") -> tuple[list[str], str]:
    validate_mode(mode, controller)
    for name, value in (("project", project), ("worker session", worker_session), ("task", task)):
        validate_atom(value, name)
    if not message.strip():
        raise LiteError("message is empty")
    request_id = request_id or ("lite-" + digest([mode, controller, project, worker_session, task, message])[:32])
    validate_atom(request_id, "request id")
    return ([bridge_bin, "queue", "submit", "--request-id", request_id, "--task", task, "--caller-ref", controller,
             "--project", project, "--session-ref", worker_session, "--message", message], request_id)


def build_report(*, task: str, status: str, summary: str, evidence: str = "", bridge_bin: str = "chat-bridge") -> list[str]:
    validate_atom(task, "task")
    validate_status(status)
    if not summary.strip():
        raise LiteError("summary is empty")
    args = [bridge_bin, "queue", "result", "--task", task, "--status", status, "--summary", summary]
    if evidence:
        validate_atom(evidence, "evidence URL")
        if not re.match(r"^https://[^\s]+$", evidence):
            raise LiteError("evidence URL must use https://")
        args += ["--github", evidence]
    return args


def callback_message(*, task: str, version: int, status: str, summary: str, blockers: str = "", evidence: str = "") -> str:
    validate_atom(task, "task")
    validate_status(status)
    if version < 1:
        raise LiteError("result version must be >=1")
    # A worker summary is untrusted free text. Escape line breaks so it cannot
    # forge other envelope fields or owner-ACK instructions.
    def single_line(value: str) -> str:
        return json.dumps(value.strip(), ensure_ascii=False)[1:-1]
    return ("CHATBRIDGE_LITE_CALLBACK_V1\n"
            f"task_id: {task}\nresult_version: {version}\nworker_status: {status}\n"
            f"summary: {single_line(summary)}\nblockers: {single_line(blockers or 'none reported')}\n"
            f"evidence: {single_line(evidence or 'none provided')}\n"
            "result_recorded_in: ChatBridge durable queue\n"
            "next_action: Check exact persisted task result and evidence, then issue owner ACK before continuing.\n"
            "notice_state: Delivery to Reason Network is NOT proof Codex processed this message.\n")


def reason_args(recipient: str, *, reason_bin: str = "reason-network") -> list[str]:
    validate_atom(recipient, "Reason Network recipient")
    if "/" not in recipient or recipient.startswith("/") or recipient.endswith("/"):
        raise LiteError("Reason Network recipient must be person/session")
    return [reason_bin, "send", recipient, "-"]


@dataclass
class ProcessReceipt:
    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def invoke(args: list[str], *, stdin: str | None = None, timeout: int = 120) -> ProcessReceipt:
    try:
        p = subprocess.run(args, input=stdin, text=True, capture_output=True, timeout=timeout, check=False)
        return ProcessReceipt(p.returncode, p.stdout, p.stderr, False)
    except subprocess.TimeoutExpired:
        return ProcessReceipt(None, timed_out=True)
    except OSError as ex:
        # Executable could not start: the operation is a proven PRE_SEND failure.
        return ProcessReceipt(127, stderr=str(ex))


def default_db() -> Path:
    return Path(os.environ.get("CBLITE_STATE_DB", "~/.local/state/chatbridge-lite/ledger.db")).expanduser()


class Ledger:
    """Local attempt guard; the authoritative worker result stays in ChatBridge."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else default_db()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            os.chmod(self.path.parent, 0o700)
        self.db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        if os.name != "nt":
            os.chmod(self.path, 0o600)
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.execute("CREATE TABLE IF NOT EXISTS attempts ("
                        "key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, phase TEXT NOT NULL, "
                        "operation_id TEXT, updated_at TEXT NOT NULL)")

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "Ledger":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _time() -> str:
        return datetime.now(timezone.utc).isoformat()

    def reserve(self, key: str, fingerprint: str) -> dict[str, str | None]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute("INSERT OR IGNORE INTO attempts(key,fingerprint,phase,operation_id,updated_at) VALUES(?,?,?,?,?)",
                            (key, fingerprint, "PREPARED", None, self._time()))
            row = self.db.execute("SELECT fingerprint,phase,operation_id FROM attempts WHERE key=?", (key,)).fetchone()
            if row[0] != fingerprint:
                raise LiteError(f"conflicting immutable intent for {key}")
            self.db.execute("COMMIT")
            return {"phase": row[1], "operation_id": row[2]}
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def transition(self, key: str, expected: str, phase: str, operation_id: str | None = None) -> bool:
        with self.db:
            r = self.db.execute("UPDATE attempts SET phase=?,operation_id=COALESCE(?,operation_id),updated_at=? "
                                "WHERE key=? AND phase=?", (phase, operation_id, self._time(), key, expected))
            return r.rowcount == 1

    def status(self, key: str) -> dict[str, str | None] | None:
        row = self.db.execute("SELECT fingerprint,phase,operation_id,updated_at FROM attempts WHERE key=?", (key,)).fetchone()
        return dict(zip(("fingerprint", "phase", "operation_id", "updated_at"), row)) if row else None


def read_operation_id(stdout: str) -> str | None:
    try:
        d = json.loads(stdout)
        if not isinstance(d, dict):
            return None
        for key in ("operationId", "operation_id", "id"):
            if isinstance(d.get(key), str):
                return d[key]
        if isinstance(d.get("operation"), dict) and isinstance(d["operation"].get("id"), str):
            return d["operation"]["id"]
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def monitor_decision(observation: dict[str, Any]) -> tuple[str, str]:
    """Fail closed: no Retry, no original-task replay, no acting on stale evidence."""
    task = observation.get("task", {})
    if not isinstance(task, dict):
        task = {}
    state = observation.get("sessionState") or observation.get("state") or observation.get("livenessState") or ""
    task_state = task.get("status") or observation.get("taskStatus") or observation.get("status") or ""
    if observation.get("observationFresh") is not True:
        return "OBSERVE_ONLY", "browser observation is missing or stale"
    if observation.get("userControlPaused") or observation.get("approvalPending") or observation.get("humanOwnsPage"):
        return "OBSERVE_ONLY", "human control or approval"
    if task_state in {"UNKNOWN", "DELIVERY_UNKNOWN", "WAITING_USER_APPROVAL", "WAITING_CAPACITY",
                      "RESULT_RECORDED", "COMPLETE", "FAILED", "BLOCKED", "CANCELLED", "AWAITING_DURABLE_UPDATE"} or observation.get("resultRecorded"):
        return "OBSERVE_ONLY", "uncertain, terminal, durable-result or approval state"
    if observation.get("deliveryUnknown") or observation.get("sendAttemptedUnknown"):
        return "OBSERVE_ONLY", "send/delivery not reconciled"
    if observation.get("projectControl") in {"PAUSED", "DRAINING"}:
        return "OBSERVE_ONLY", "project paused or draining"
    if state in {"RUNNING_ACTIVE", "RUNNING_QUIET", "SUSPECT_STALL", "GENERATING"}:
        return "OBSERVE_ONLY", "generation/quiet state not proof of failure"
    if state in {"ERROR_RECOVERABLE", "IDLE_INCOMPLETE"}:
        return "RECOVER_ELIGIBLE", "guarded same-task recovery only"
    return "OBSERVE_ONLY", "no characterized recovery evidence"
