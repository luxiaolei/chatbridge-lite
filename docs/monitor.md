# Luna Max / 30-minute monitoring policy

The purpose of a watchdog is **safe diagnosis and evidence-based recovery**, not repeatedly telling a slow model to Retry.

## Recommended scheduled check

1. On the independently scheduled tick (e.g. each 30 minutes), read a fresh exact-task status from the authoritative Bridge/ChatGPT session.
2. Validate actual Project/account/worker conversation, task ID, owner, control epoch, current assistant/user message and observation timestamp.
3. If the task is actively generating, quiet, awaiting a user approval, user-owned, paused, result-recorded or delivery-unknown: observe only and report the reason.
4. Only a fresh `ERROR_RECOVERABLE` or `IDLE_INCOMPLETE` state without contrary evidence is eligible for guarded **same-task** `chat-bridge recover`.
5. Never emit a second original task Send, Resend or Retry merely because 30 minutes elapsed; do not close running Tabs in anticipation of server-side continuation.
6. If recovery cannot be proved, keep task `BLOCKED/UNKNOWN` with the original operation and notify the owner once.

## CLI examples

```bash
# Read live evidence (preview-only)
cblite monitor --project PROJECT --worker-session SESSION_REF --task TASK_ID

# Replay synthetic status evidence from a saved fixture (preview-only)
cblite monitor --snapshot-file tests/fixtures/recoverable.json

# Explicit operator-approved guarded recovery; old Bridge revalidates its own gates
cblite monitor --project PROJECT --worker-session SESSION_REF --task TASK_ID --execute
```

Do not run an unattended scheduler until the underlying status shape, feedback loop, idempotence and owner-side ACK have been tested against the **installed** code. Luna Max is an execution choice; this repository neither creates a schedule nor assumes the model has unrestricted tool permissions.
