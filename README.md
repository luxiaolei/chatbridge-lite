# ChatBridge Lite

**Make ChatGPT Web chats your task workers, with a Codex App or ChatGPT chat as the controller.**

> **Early alpha / adapter preview, not a production-ready unattended service.** This repository intentionally keeps the first iteration small: it wraps an existing, separately installed ChatBridge queue, uses Reason Network for Codex wake-up notifications, and applies conservative recovery gates. It is not an OpenAI API, is not affiliated with OpenAI, and does not bypass ChatGPT or Codex rate limits.

## The two modes

```text
Mode A — Chat controller

ChatGPT controller
      │  durable dispatch
      ▼
ChatBridge queue → ChatGPT Web worker
      ▲                      │
      └── durable result ←───┘
      │
      └── callback to original Chat controller → review + ACK → next task

Mode B — Codex controller

Codex App controller
      │  durable dispatch
      ▼
ChatBridge queue → ChatGPT Web worker
                       │
                       ├─ record result → ChatBridge SQLite
                       └─ Reason Network send → exact Codex App thread (wake)
                                                   │
                                                   ▼
                                      read durable result → review + ACK
```

The **Reason Network push is a wake-up message, not an acceptance or exactly-once proof**. If the Codex thread is absent/unavailable, the original result stays in ChatBridge for later reconciliation. Lite never replays a potentially delivered notification automatically.

## Why this is smaller than ChatBridge

- One CLI, three core paths: `dispatch`, `report`, and `monitor`.
- Two controller modes share the same durable queue and worker result protocol.
- No second browser engine, account pool, daemon, or task database of authority.
- A tiny local SQLite **attempt ledger** blocks ambiguous duplicate sends. ChatBridge remains authoritative for task/result/owner ACK.
- Recovery is gated and defaults to **observe only**, not blind Retry/Resend.
- Initial setup is a guided check, not a hidden browser or plugin installation.

This **alpha still requires an installed compatible ChatBridge** for task queue and ChatGPT Web routing. Extracting its minimal reliable delivery core into Lite is a later milestone, not something this alpha pretends to have finished.

## Requirements

- Python 3.10+ on the host running this CLI.
- Installed and configured `chat-bridge` CLI (same host) and a verified ChatGPT Project/worker session.
- **Current browser dispatcher:** Ego Lite with the supported `ego-browser` runtime and an already signed-in ChatGPT account. Remote Desktop Commander provides local-computer tools but does **not** replace `ego-browser` in this alpha.
- For the **Codex controller**: configured [Reason Network](https://reasonmachines.com/) on the host and a *known exact* `person/session` recipient that owns the job.
- **Recommended local-computer connection for the worker Chat:** [Remote Desktop Commander](https://github.com/desktop-commander/remote-desktop-commander) — simpler hosted remote-MCP onboarding for filesystem/terminal access; see [setup guide](docs/REMOTE-SETUP.md). Verify the exact device and permissions in ChatGPT before running commands.
- **Advanced alternative:** [chatgpt-open-remote-mcp](https://github.com/luxiaolei/chatgpt-open-remote-mcp) is a separate Linux-focused MCP server with explicit grants and OpenAI Secure MCP Tunnel setup; it is more involved and is not a drop-in replacement for Ego Lite.
- Browser Use / Chrome automation is an optional future adapter. Its presence does not make it a drop-in equivalent of Ego Lite's verified runtime.

Do not enter login passwords, browser cookies, API tokens or private message addresses in a public repository, screenshot, GitHub Issue or example file.

## Connect ChatGPT to your computer (recommended first)

Start with [Remote Desktop Commander](docs/REMOTE-SETUP.md). It pairs a small local agent with a hosted remote MCP connection and is usually less setup than maintaining a custom computer-control MCP server. Usage limits and paid tiers may apply; verify the current plan/limits in the [dashboard](https://mcp.desktopcommander.app/) before relying on frequent or unattended calls. Do not assume a free quota or price from this repository.

Keep the layers distinct: Remote Desktop Commander gives the worker Chat access to the authorized machine; **this alpha still uses Ego Lite / `ego-browser` for its existing ChatGPT Web dispatch runtime**. The custom [chatgpt-open-remote-mcp](https://github.com/luxiaolei/chatgpt-open-remote-mcp) path is a more advanced, Linux-focused option.

## Install and discover

```bash
python3 -m pip install --user -e .
cblite doctor
```

The doctor reports local executable availability and guided plugin steps. It **cannot** prove a remote plugin is actually connected to a particular ChatGPT session.

All potentially mutating commands are **preview-only by default**. Add `--execute` deliberately.

## Codex controller example (replace placeholders)

```bash
cblite dispatch \
  --mode codex \
  --controller 'codex:<ACTUAL_THREAD_ID>' \
  --project '<EXACT_CHATGPT_PROJECT>' \
  --worker-session '<VERIFIED_WORKER_SESSION_REF>' \
  --task DEMO-001 \
  --reason-to '<YOUR_PERSON/YOUR_CODEX_THREAD_SESSION>' \
  --message 'Research three options and give sources, blockers and a recommendation.'
```

The preview prints an intent fingerprint, not the full prompt. Once the binding and owner are confirmed, add `--execute`. The original thread identity is never inferred from a guessed username or default account.

The worker should return a durable result and then notify the original Codex thread:

```bash
cblite report --mode codex --task DEMO-001 --status COMPLETE \
  --message 'Three options evaluated, sources attached.' \
  --evidence 'https://github.com/OWNER/REPO/issues/1' \
  --reason-to '<YOUR_PERSON/YOUR_CODEX_THREAD_SESSION>'
```

Add `--execute` only when authorized. The report command first calls the installed Bridge's `queue result`; **only after a successful result receipt** does it invoke `reason-network send <person/session> -` with the callback body over standard input. If the result receipt is unknown, no push is sent. If the Reason send response is unknown, it is **never auto-sent again**.

On receiving the push, the *original Codex controller* must validate the stored result with `queue receive`, review evidence, and only then `queue ack`. Reason Network's successful command exit is **not** the Codex ACK.

## Chat controller example

```bash
cblite dispatch \
  --mode chat \
  --controller '<REGISTERED_CHAT_CONTROLLER_SESSION_REF>' \
  --project '<EXACT_CHATGPT_PROJECT>' \
  --worker-session '<VERIFIED_WORKER_SESSION_REF>' \
  --task DEMO-002 --message 'Produce a short report with sources.'
```

After executing the dispatch, a Chat worker can call:

```bash
cblite report --mode chat --task DEMO-002 --status COMPLETE \
  --message 'Completed with durable evidence.' --execute
```

ChatBridge owns the durable callback route to the original Chat controller. The controller still needs to review and ACK the result.

## 30-minute watchdog / Luna Max

If you already run a half-hour Luna Max monitoring task, **reuse it** rather than creating a second scheduler. It may query the exact worker task and invoke `cblite monitor` using a fresh observation. Example of preview-only monitoring:

```bash
cblite monitor --project '<PROJECT>' --worker-session '<SESSION>' --task DEMO-001
```

Only fresh, bound `ERROR_RECOVERABLE` or `IDLE_INCOMPLETE` evidence is eligible for the installed Bridge's guarded same-task `recover` (when `--execute` is used). A quiet or apparently stuck Chat is **not**, by itself, permission for Retry, Resend, Stop or task replay. Details: [Monitoring policy](docs/monitor.md).

## Checks

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The tests use mocks and synthetic task IDs. **No real ChatGPT send, Reason message or watchdog recovery is performed by the tests.** See [architecture](docs/architecture.md) and [release gates](docs/release-gates.md) before attempting a live demo.

## Marketing claim boundary

Appropriate: **“Delegate suitable work from Codex to ChatGPT Web workers, and bring durable results back to your controller.”**

Not substantiated: “unlimited usage,” “zero cost,” “always-on 24/7 under every account,” “zero Codex tokens,” or “guaranteed reliable automatic retries.” These are subject to the account plan, model quota, UI/tool runtime, approval flow and platform terms.

MIT License. Brand names are used only to identify independent integrations.
