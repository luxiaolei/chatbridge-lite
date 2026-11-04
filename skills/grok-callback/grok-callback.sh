#!/usr/bin/env bash
# grok-callback.sh — notify a Grok Bot routine webhook that a ChatGPT Chat task
# delivered / is blocked / made progress. Secrets are read ONLY from
# ~/hz-secrets/grok-webhook.env (GROK_WEBHOOK_URL, GROK_WEBHOOK_KEY; mode 600)
# and are never printed. Never run this script with `bash -x`.
#
# Usage:
#   grok-callback.sh --repo OWNER/REPO --status 交付|阻塞|进度|测试 --note TEXT \
#       [--ref pr:123|issue:45|123 [--kind pr|issue]] [--link URL] [--dry-run]
#   (--ref / --link may be omitted; kind/number/link are then null in the JSON)
#
# Auth header: GROK_WEBHOOK_AUTH_HEADER from the secrets file (full line,
#   'Authorization: Bearer <key>') is used first; otherwise it falls back to
#   'Authorization: Bearer $GROK_WEBHOOK_KEY'.
# Env overrides (optional, non-secret):
#   GROK_WEBHOOK_ENV     path of the secrets file (default ~/hz-secrets/grok-webhook.env);
#                        must resolve (realpath) to a file inside ~/hz-secrets/, else the script exits.
#   GROK_WEBHOOK_HEADER  header name used only in the GROK_WEBHOOK_KEY fallback (default
#                        Authorization, value "Bearer <key>"; any other name gets the raw key).
#
# Exit: 0 on HTTP 2xx (or a successful --dry-run), 1 otherwise.
set -euo pipefail
set +x

HEADER_NAME="${GROK_WEBHOOK_HEADER:-Authorization}"

die() { echo "grok-callback: $*" >&2; exit 1; }

SECRETS_DIR="$HOME/hz-secrets"
ENV_FILE="$SECRETS_DIR/grok-webhook.env"
if [ -n "${GROK_WEBHOOK_ENV:-}" ]; then
  # Only allow overrides that resolve inside ~/hz-secrets/ (symlinks and ../ resolved).
  sec_real="$(realpath "$SECRETS_DIR" 2>/dev/null)" || die "cannot resolve $SECRETS_DIR"
  ov_dir="$(realpath "$(dirname "$GROK_WEBHOOK_ENV")" 2>/dev/null)" || die "GROK_WEBHOOK_ENV directory does not exist: $GROK_WEBHOOK_ENV"
  ov_real="$ov_dir/$(basename "$GROK_WEBHOOK_ENV")"
  [ -L "$ov_real" ] && { ov_real="$(realpath "$ov_real" 2>/dev/null)" || die "cannot resolve $GROK_WEBHOOK_ENV"; }
  case "$ov_real" in
    "$sec_real"/*) ENV_FILE="$ov_real" ;;
    *) die "GROK_WEBHOOK_ENV must point to a file inside $SECRETS_DIR/ (got $GROK_WEBHOOK_ENV)" ;;
  esac
fi

# need OPT VALUE...: fail clearly when an option is missing its value.
need() {
  if [ "$#" -lt 2 ] || [ -z "$2" ]; then die "option $1 requires a value"; fi
  case "$2" in --*) die "option $1 requires a value (got option $2)" ;; esac
}
usage() { sed -n '6,10p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 1; }

repo="" ref="" kind="" status="" link="" note="" dry=0
while [ $# -gt 0 ]; do
  case "$1" in
    --repo)   need "$@"; repo="$2"; shift 2 ;;
    --ref)    need "$@"; ref="$2"; shift 2 ;;
    --kind)   need "$@"; kind="$2"; shift 2 ;;
    --status) need "$@"; status="$2"; shift 2 ;;
    --link)   need "$@"; link="$2"; shift 2 ;;
    --note)   need "$@"; note="$2"; shift 2 ;;
    --dry-run) dry=1; shift ;;
    -h|--help) usage ;;
    *) die "unknown argument: $1" ;;
  esac
done

[ -n "$repo" ] && [ -n "$status" ] && [ -n "$note" ] || usage
number=""
if [ -n "$ref" ]; then
  case "$ref" in
    pr:*|issue:*) kind="${ref%%:*}"; number="${ref#*:}" ;;
    *) number="$ref" ;;
  esac
  [ -n "$kind" ] || die "--kind pr|issue is required when --ref is a bare number"
  case "$kind" in pr|issue) ;; *) die "kind must be pr or issue" ;; esac
  case "$number" in ''|*[!0-9]*) die "ref number must be an integer" ;; esac
fi
case "$status" in 交付|阻塞|进度|测试) ;; *) die "status must be 交付|阻塞|进度|测试" ;; esac
command -v jq >/dev/null || die "jq not found"
command -v curl >/dev/null || die "curl not found"

sent_at="$(TZ=Asia/Shanghai date '+%Y-%m-%dT%H:%M:%S+08:00')"
host="$(hostname -s 2>/dev/null || hostname)"
body="$(jq -n --arg repo "$repo" --arg kind "$kind" --arg number "$number" \
  --arg status "$status" --arg link "$link" --arg note "$note" \
  --arg sent_at "$sent_at" --arg host "$host" \
  'def nn: if . == "" then null else . end;
   {source:"chatgpt-chat", repo:$repo, kind:($kind|nn),
    number:(if $number == "" then null else ($number|tonumber) end), status:$status,
    link:($link|nn), note:$note, sent_at:$sent_at, host:$host}')"

check_env_file() {
  [ -f "$ENV_FILE" ] || die "secrets file missing: $ENV_FILE"
  # macOS/BSD first (stat -f %Lp), then GNU/Linux (stat -c %a); GNU `stat -f` means
  # "filesystem status" and may not fail, so only accept an octal answer.
  perm="$(stat -f '%Lp' "$ENV_FILE" 2>/dev/null || true)"
  case "$perm" in ''|*[!0-7]*) perm="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || true)" ;; esac
  case "$perm" in ''|*[!0-7]*) die "cannot read permissions of $ENV_FILE" ;; esac
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
  if [ -n "${GROK_WEBHOOK_AUTH_HEADER:-}" ]; then
    hl="$GROK_WEBHOOK_AUTH_HEADER"
  else
    [ -n "${GROK_WEBHOOK_KEY:-}" ] || { echo "nokey"; exit 0; }
    k="${GROK_WEBHOOK_KEY#Bearer }"           # tolerate a pasted full header value
    k="${k#Authorization: Bearer }"
    if [ "$HEADER_NAME" = "Authorization" ]; then hl="Authorization: Bearer $k"; else hl="$HEADER_NAME: $k"; fi
  fi
  case "$hl" in *:*) ;; *) echo "badheader"; exit 0 ;; esac
  case "$hl$GROK_WEBHOOK_URL" in *\"*|*\\*|*$'\n'*|*$'\r'*) echo "badchars"; exit 0 ;; esac
  # URL and header go via stdin config so they never appear in `ps`.
  printf 'url = "%s"\nheader = "%s"\n' "$GROK_WEBHOOK_URL" "$hl" |
    curl -sS -o /dev/null -w '%{http_code}' --max-time 20 -X POST \
      -H 'Content-Type: application/json' --data-binary @"$tmp" -K - 2>/dev/null || echo "000"
)"

case "$code" in
  nourl) die "GROK_WEBHOOK_URL not set in $ENV_FILE" ;;
  nokey) die "neither GROK_WEBHOOK_AUTH_HEADER nor GROK_WEBHOOK_KEY set in $ENV_FILE" ;;
  badheader) die "GROK_WEBHOOK_AUTH_HEADER must look like 'Name: value'" ;;
  badchars) die "URL/key contains unsupported characters (quote/backslash/newline)" ;;
esac
code="${code: -3}"
echo "HTTP $code"
case "$code" in
  2??) echo "ok: Grok webhook accepted ($status${kind:+ $kind#$number})"; exit 0 ;;
  # Observed meanings (未核实 / unverified): 401 = wrong or rotated key, 400 = routine paused.
  *)   echo "failed: webhook did not accept the callback"; exit 1 ;;
esac
