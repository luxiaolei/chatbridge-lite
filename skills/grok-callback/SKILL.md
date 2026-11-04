---
name: grok-callback
description: When a ChatGPT Chat worker finishes a task, gets blocked, or reaches a milestone, notify the Grok Bot controller — primarily through its routine webhook from xlmini, with a GitHub Draft PR as the fallback wake-up.
---

# Grok callback (ChatGPT Chat → Grok Bot)

Use this in a ChatGPT Chat worker that is connected to the user's Mac mini
(xlmini) through Remote Desktop Commander. There are two channels: a webhook
(primary, fast) and a GitHub PR listener (fallback, always on).

**任务状态以 PR/Issue 为准。** The webhook is only a notification; it does not
record or change task state.

## Which one to use

| Situation | Do |
| --- | --- |
| Normal delivery (交付) or blocked (阻塞) | **Both**: open the Draft PR first, then run the script. |
| Remote desktop unavailable, or the script still fails after one retry | **PR fallback only**, and state 「回调失败 HTTP <code>」 in the PR body or a PR comment. |
| Progress report only, no PR needed | **Script only**, with `--status 进度`. |

## 1. Primary: routine webhook

ChatGPT runs `~/agent-tools/grok-callback.sh` on xlmini (via Remote Desktop
Commander); the script POSTs JSON to the Grok routine's webhook.

### Secrets

- Read **only** from `~/hz-secrets/grok-webhook.env` on xlmini (mode 600; the script refuses any other mode). `GROK_WEBHOOK_ENV` may override the path, but only to a file that resolves inside `~/hz-secrets/`. The user copies the values from the routine panel.
- Variables (names only — never write the values anywhere):
  - `GROK_WEBHOOK_URL` — the routine's "POST to" URL.
  - `GROK_WEBHOOK_AUTH_HEADER` — the full header line, format `Authorization: Bearer <key>`. Used first.
  - `GROK_WEBHOOK_KEY` — the bare key; fallback, sent as `Authorization: Bearer <key>` when `GROK_WEBHOOK_AUTH_HEADER` is absent.
- Never `cat`/`echo`/`grep` the values, never run the script with `bash -x`, and never paste them into the chat, a PR, an Issue, a commit or a log. The script passes the URL and header to curl over stdin (not visible in `ps`) and only prints the HTTP code.

### Command

```bash
# delivered / blocked: point at the Draft PR
~/agent-tools/grok-callback.sh --repo luxiaolei/huazhuo-runtime --ref pr:123 \
  --status 交付 --link https://github.com/luxiaolei/huazhuo-runtime/pull/123 \
  --note "#45 完成，等待验收"

# progress only (no PR)
~/agent-tools/grok-callback.sh --repo luxiaolei/huazhuo-runtime --ref issue:45 \
  --status 进度 --note "调研完成一半，明早交付"

# preview: prints the JSON body and the target host with the path masked; sends nothing
~/agent-tools/grok-callback.sh ... --dry-run
```

| Arg | Meaning |
| --- | --- |
| `--repo` | required; `owner/name` |
| `--status` | required; `交付` / `阻塞` / `进度` / `测试` |
| `--note` | required; one sentence: what was delivered, or what is blocking |
| `--ref` | optional; `pr:<n>` or `issue:<n>`; a bare `<n>` needs `--kind pr\|issue` |
| `--link` | optional; PR (or Issue) URL — always give it for 交付/阻塞 |
| `--dry-run` | print body + masked target, do not send |

### JSON body

```json
{
  "source": "chatgpt-chat",
  "repo": "luxiaolei/huazhuo-runtime",
  "kind": "pr",
  "number": 123,
  "status": "交付",
  "link": "https://github.com/luxiaolei/huazhuo-runtime/pull/123",
  "note": "one sentence",
  "sent_at": "2026-11-04T22:30:00+08:00",
  "host": "xlmini"
}
```

| Field | Meaning |
| --- | --- |
| `source` | always `chatgpt-chat` |
| `repo` | from `--repo` |
| `kind` / `number` | from `--ref`; `null` when omitted |
| `status` | from `--status` |
| `link` | from `--link`; `null` when omitted |
| `note` | from `--note` |
| `sent_at` | send time, ISO 8601, `+08:00` |
| `host` | short hostname of the sender |

### Result

The script prints `HTTP <code>` and one line; exit 0 on 2xx, 1 otherwise.
**HTTP 200 only means Grok accepted the call and started a run** — not that it
finished or agreed. Typical failures (**未核实** — observed by third parties,
not confirmed in official docs): 401 = key rotated/wrong, 400 = routine paused;
both need the user, not more retries. `HTTP 000` = network error.

## 2. Fallback: GitHub PR listener

The fallback covers **only these two repositories** — a PR opened anywhere else
does not wake Grok. Grok listens (GitHub account `luxiaolei`) on:

- `luxiaolei/huazhuo-runtime`
- `luxiaolei/huazhuo-blueprint`

for the events **`pr-opened`** and **`issue-assigned`**.

On delivery, open a Draft PR:

- Title starts with the Issue number: `#123 <short summary>`.
- When blocked, add 「阻塞」: `#123 阻塞 <short summary>`, and write in the body exactly what is blocking, what you tried, and what decision you need.
- `gh pr create --draft --title "#123 …" --body "…"`

Limits of this channel:

- The routine does **not** receive repo-wide issue comments: commenting on an Issue alone will **not** wake Grok.
- Pushing new commits to an existing PR does **not** trigger it either. Only **opening a new PR** or **assigning an Issue** wakes Grok.

## Failure handling

1. Non-2xx from the script: wait a few seconds and retry **once**.
2. Still failing: rely on the PR fallback — the Draft PR must exist — and add `回调失败 HTTP <code>，依赖 GitHub 兜底通知` to the PR body or a PR comment. Do not loop.

## Don'ts

- No force push, no rebase of pushed history, no merge.
- No secrets anywhere outside `~/hz-secrets/grok-webhook.env`.

`grok-callback.sh` in this folder is a copy of `~/agent-tools/grok-callback.sh` (no secrets inside). Install: `install -m 700 skills/grok-callback/grok-callback.sh ~/agent-tools/`.
