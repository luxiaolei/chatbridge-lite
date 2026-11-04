#!/usr/bin/env bash
# grok-callback.sh — notify a Grok Bot routine webhook that a ChatGPT Chat task
# delivered / is blocked / made progress. Secrets are read ONLY from
# ~/hz-secrets/grok-webhook.env (GROK_WEBHOOK_URL, GROK_WEBHOOK_KEY; mode 600)
# and are never printed. Never run this script with `bash -x`.
#
# Usage:
#   grok-callback.sh --repo OWNER/REPO --ref pr:123|issue:45|123 [--kind pr|issue] \
#       --status 交付|阻塞|进度|测试 --link URL --note TEXT [--dry-run]
#
# Env overrides (optional, non-secret):
#   GROK_WEBHOOK_ENV     path of the secrets file (default ~/hz-secrets/grok-webhook.env)
#   GROK_WEBHOOK_HEADER  header name for the key (default Authorization, sent as "Bearer <key>")
#                        if set to anything else, the raw key is sent as that header's value.
#
# Exit: 0 on HTTP 2xx (or a successful --dry-run), 1 otherwise.
set -euo pipefail
set +x

ENV_FILE="${GROK_WEBHOOK_ENV:-$HOME/hz-secrets/grok-webhook.env}"
HEADER_NAME="${GROK_WEBHOOK_HEADER:-Authorization}"

die() { echo "grok-callback: $*" >&2; exit 1; }
usage() { sed -n '6,9p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 1; }

repo="" ref="" kind="" status="" link="" note="" dry=0
while [ $# -gt 0 ]; do
  case "$1" in
    --repo)   repo="${2-}"; shift 2 ;;
    --ref)    ref="${2-}"; shift 2 ;;
    --kind)   kind="${2-}"; shift 2 ;;
    --status) status="${2-}"; shift 2 ;;
    --link)   link="${2-}"; shift 2 ;;
    --note)   note="${2-}"; shift 2 ;;
    --dry-run) dry=1; shift ;;
    -h|--help) usage ;;
    *) die "unknown argument: $1" ;;
  esac
done

[ -n "$repo" ] && [ -n "$ref" ] && [ -n "$status" ] && [ -n "$link" ] && [ -n "$note" ] || usage
case "$ref" in
  pr:*|issue:*) kind="${ref%%:*}"; number="${ref#*:}" ;;
  *) number="$ref" ;;
esac
[ -n "$kind" ] || die "--kind pr|issue is required when --ref is a bare number"
case "$kind" in pr|issue) ;; *) die "kind must be pr or issue" ;; esac
case "$number" in ''|*[!0-9]*) die "ref number must be an integer" ;; esac
case "$status" in 交付|阻塞|进度|测试) ;; *) die "status must be 交付|阻塞|进度|测试" ;; esac
command -v jq >/dev/null || die "jq not found"
command -v curl >/dev/null || die "curl not found"

sent_at="$(TZ=Asia/Shanghai date '+%Y-%m-%dT%H:%M:%S+08:00')"
host="$(hostname -s 2>/dev/null || hostname)"
body="$(jq -n --arg repo "$repo" --arg kind "$kind" --argjson number "$number" \
  --arg status "$status" --arg link "$link" --arg note "$note" \
  --arg sent_at "$sent_at" --arg host "$host" \
  '{source:"chatgpt-chat", repo:$repo, kind:$kind, number:$number, status:$status,
    link:$link, note:$note, sent_at:$sent_at, host:$host}')"

check_env_file() {
  [ -f "$ENV_FILE" ] || die "secrets file missing: $ENV_FILE"
  perm="$(stat -f '%Lp' "$ENV_FILE" 2>/dev/null || stat -c '%a' "$ENV_FILE")"
  [ "$perm" = "600" ] || die "secrets file must be mode 600 (is $perm): $ENV_FILE"
}

if [ "$dry" = 1 ]; then
  echo "$body"
  if [ -f "$ENV_FILE" ]; then
    check_env_file
    target="$( set +x; set -a; . "$ENV_FILE" >/dev/null 2>&1; set +a
      u="${GROK_WEBHOOK_URL:-}"; [ -n "$u" ] || { echo "(GROK_WEBHOOK_URL not set)"; exit 0; }
      h="${u#*://}"; h="${h%%/*}"; echo "${u%%://*}://$h/***" )"
    echo "target: $target"
  else
    echo "target: (secrets file not present yet: $ENV_FILE)"
  fi
  echo "dry-run: no request sent"
  exit 0
fi

check_env_file
tmp="$(mktemp -t grokcb.XXXXXX)"; trap 'rm -f "$tmp"' EXIT
printf '%s' "$body" > "$tmp"

code="$(
  set +x
  set -a; . "$ENV_FILE" >/dev/null 2>&1; set +a
  [ -n "${GROK_WEBHOOK_URL:-}" ] || { echo "nourl"; exit 0; }
  [ -n "${GROK_WEBHOOK_KEY:-}" ] || { echo "nokey"; exit 0; }
  k="${GROK_WEBHOOK_KEY#Bearer }"           # tolerate a pasted full header value
  k="${k#Authorization: Bearer }"
  case "$k$GROK_WEBHOOK_URL" in *\"*|*\\*|*$'\n'*) echo "badchars"; exit 0 ;; esac
  if [ "$HEADER_NAME" = "Authorization" ]; then hv="Bearer $k"; else hv="$k"; fi
  # URL and header go via stdin config so they never appear in `ps`.
  printf 'url = "%s"\nheader = "%s: %s"\n' "$GROK_WEBHOOK_URL" "$HEADER_NAME" "$hv" |
    curl -sS -o /dev/null -w '%{http_code}' --max-time 20 -X POST \
      -H 'Content-Type: application/json' --data-binary @"$tmp" -K - 2>/dev/null || echo "000"
)"

case "$code" in
  nourl) die "GROK_WEBHOOK_URL not set in $ENV_FILE" ;;
  nokey) die "GROK_WEBHOOK_KEY not set in $ENV_FILE" ;;
  badchars) die "URL/key contains unsupported characters (quote/backslash/newline)" ;;
esac
code="${code: -3}"
echo "HTTP $code"
case "$code" in
  2??) echo "ok: Grok webhook accepted ($status $kind#$number)"; exit 0 ;;
  *)   echo "failed: webhook did not accept the callback"; exit 1 ;;
esac
