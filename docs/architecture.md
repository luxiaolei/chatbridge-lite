# Architecture and responsibility boundaries

## Runtime components

1. **Controller**: either one registered ChatGPT Project chat or the original, active/resumable Codex App thread.
2. **Existing ChatBridge**: queue, durable result, exact owner, result version, controller acceptance, ChatGPT Web target, error/recovery policy.
3. **Worker Chat**: performs bounded work using its actual connected permissions.
4. **Reason Network**: optional active notification into a named *Codex* session, using stdin body and normal `send` (not `--fyi`).
5. **ChatBridge Lite**: presentation/admission adapter + private attempt ledger; it is not a second authoritative control plane.
6. **Luna Max or another independently scheduled monitor**: checks age/progress every configured interval and may request guarded same-task recovery. It does not claim a successful result from UI appearance alone.

## Wire contracts

`dispatch` → `chat-bridge queue submit` → saved operation. `queue submit` means queued, **not** delivered and not accepted.

`report` → `chat-bridge queue result` → durable worker result. For Codex mode *after that step succeeds*, `reason-network send <person/session> -` receives this envelope over stdin:

```text
CHATBRIDGE_LITE_CALLBACK_V1
task_id: TASK_ID
result_version: 1
worker_status: COMPLETE | BLOCKED | FAILED
summary: ...
blockers: ...
evidence: https://...
result_recorded_in: ChatBridge durable queue
next_action: Check exact persisted task result and evidence, then issue owner ACK before continuing.
notice_state: Delivery to Reason Network is NOT proof Codex processed this message.
```

A Reason Network process exit 0 is named `REASON_SUBMITTED`, not delivered/consumed/ACK. A lost response becomes `REASON_UNKNOWN`; Lite does **not** auto-repeat it.

`queue receive` and `queue ack` execute under the **original registered Codex owner/host/thread**, not an arbitrary terminal user. If the App is closed or a thread is archived and cannot be resumed, Lite preserves the result and surfaces a follow-up; it does not impersonate an old thread.

## Attempt journal

SQLite under the local user's private state path records only fingerprint, attempt stage, operation ID and timestamps. It does **not** store message bodies or Reason Network credentials. Phases are monotonic and one distinct task+version can be tried only once without explicit out-of-band reconciliation.

Important unknown states:

- `DISPATCH_UNKNOWN`: ChatBridge command returned no conclusive pre/post-send evidence; no automatic second submit.
- `RESULT_UNKNOWN`: worker result command ambiguous; no Reason push until durable result is independently proven.
- `REASON_UNKNOWN`: durable result exists but push response ambiguous; no second Reason send.
- `REASON_SUBMITTED`: notification command returned success; owner acceptance remains outstanding.
- `CHAT_CALLBACK_QUEUED`: Bridge owns the callback; controller still must ACK.

## Threat and human-control boundaries

- No remote shell execution from untrusted callback text.
- Never run `Reason Network --from` with guessed identity; destination is a per-user local config, not global repo data.
- Never infer a Codex thread from filesystem names or a random session; require exact current owner.
- No credential export, login bypass, browser CAPTCHA circumvention or quota farming.
- No Retry/Stop/Continue if human approval, protected draft, uncertain send, stale observation or user ownership is active.
- No integration is guaranteed by the mere presence of an installed plugin. Establish a real, authorized host connection.
- Existing ChatBridge pause/drain/UNKNOWN and user-control gates remain authoritative and must be enforced in the underlying Bridge.

## Current alpha scope

Available: local previews, durable attempt anti-replay guard, adapter commands, Reason Network callback formatting and safe monitor policy with synthetic tests.

Not yet proven for public release: setup on a clean new user's machine, Chrome/Browser Use compatibility, full 24/7 continued task loops, delivery/ACK under failures, restart across machines, private plugin permission setup, automated dependency installation, and failover against all front-end changes.

A private real-message canary with explicit permission is required before marking the user-facing demo ready.
