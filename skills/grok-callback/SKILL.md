---
name: grok-callback
description: When a ChatGPT Chat worker finishes a task, gets blocked, or reaches a milestone, open a Draft PR and wake the Grok Bot controller through its routine webhook from xlmini.
---

# Grok callback (ChatGPT Chat → Grok Bot)

Use this in a ChatGPT Chat worker that is connected to the user's Mac mini
(xlmini) through Remote Desktop Commander.

## When to use

- **交付 (delivered):** the task is done and the result is in a PR.
- **阻塞 (blocked):** you cannot continue without a decision, an access grant or a fix outside your reach.
- **进度 (progress):** a meaningful stage is finished and the controller should know before the end.
- **测试 (test):** only for wiring tests.

## Steps

1. **Open a Draft PR first. Always.**
   - Title starts with the Issue number: `#123 <short summary>`.
   - When blocked, add 「阻塞」: `#123 阻塞 <short summary>`, and write in the body exactly what is blocking, what you tried, and what decision you need.
   - `gh pr create --draft --title "#123 …" --body "…"`. Never force push; never merge.
2. **Then wake Grok** by running on xlmini (via Remote Desktop Commander):

   ```bash
   ~/agent-tools/grok-callback.sh --repo OWNER/REPO --ref pr:<PR number> \
     --status 交付|阻塞|进度 --link <PR URL> --note "<one sentence>"
   ```

   Optionally preview first with `--dry-run` (prints the JSON body and the target host with the path masked; sends nothing).
3. Report the script's output (`HTTP <code>` + one line) in the chat. Nothing else from the environment.

## Message format

Arguments:

| Arg | Meaning |
| --- | --- |
| `--repo` | `owner/name` of the repository |
| `--ref` | `pr:<n>` or `issue:<n>`; a bare `<n>` needs `--kind pr\|issue` |
| `--status` | `交付` / `阻塞` / `进度` / `测试` |
| `--link` | URL of the PR (or Issue) |
| `--note` | one sentence: what was delivered, or what is blocking |
| `--dry-run` | print body + masked target, do not send |

JSON body POSTed to the webhook:

```json
{
  "source": "chatgpt-chat",
  "repo": "owner/name",
  "kind": "pr",
  "number": 123,
  "status": "交付",
  "link": "https://github.com/owner/name/pull/123",
  "note": "one sentence",
  "sent_at": "2026-11-04T22:30:00+08:00",
  "host": "xlmini"
}
```

The key is sent as `Authorization: Bearer <key>` (Grok Bot routine webhook format). `GROK_WEBHOOK_HEADER` can override the header name if that ever changes. Exit code 0 means HTTP 2xx: Grok accepted the call and started a run, not that it finished.

## Secrets

- URL and key live only in `~/hz-secrets/grok-webhook.env` on xlmini (`GROK_WEBHOOK_URL=…`, `GROK_WEBHOOK_KEY=…`, mode 600). The user copies them from the routine panel.
- Never `cat`, `echo`, `grep` the values, run the script with `bash -x`, or paste them into the chat, a PR, an Issue, a commit or a log. The script refuses to run if the file is not mode 600, passes the URL and header to curl over stdin (not visible in `ps`), and only prints the HTTP code.

## GitHub fallback

Grok also listens for `pr-opened` and `issue-assigned` on the watched repositories. Even if the callback never goes out, opening the Draft PR wakes Grok — this is why step 1 is mandatory. The callback is only a faster, richer notification.

## Failure handling

- Non-2xx (or `HTTP 000` = network error): wait a few seconds and retry **once**.
- Still failing: add a PR comment such as `回调失败 HTTP <code>，依赖 GitHub 兜底通知`, and stop. Do not loop. 401 usually means the key was rotated; 400 means the routine is paused — both need the user, not retries.

## Don'ts

- No force push, no merge, no rewriting pushed history.
- No secrets anywhere outside the secrets file.

`grok-callback.sh` in this folder is a copy of `~/agent-tools/grok-callback.sh` (no secrets inside). Install: `install -m 700 skills/grok-callback/grok-callback.sh ~/agent-tools/`.
