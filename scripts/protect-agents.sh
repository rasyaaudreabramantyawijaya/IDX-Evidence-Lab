#!/bin/sh
set -eu

# Local guard for AGENTS.md. This is intentionally supplemental: a user with
# administrator/filesystem access can always bypass local file permissions.

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TARGET="$ROOT_DIR/AGENTS.md"
CONFIG="$ROOT_DIR/.agents-protection.env"

fail() { printf 'protect-agents: %s\n' "$*" >&2; exit 1; }

[ -f "$TARGET" ] || fail "missing $TARGET"
[ -f "$CONFIG" ] || fail "create $CONFIG from .agents-protection.env.example first"

# shellcheck disable=SC1090
. "$CONFIG"
: "${AUTHORIZED_PUBLIC_IP:?AUTHORIZED_PUBLIC_IP is required in $CONFIG}"
: "${AUTHORIZED_UID:?AUTHORIZED_UID is required in $CONFIG}"

current_uid=$(id -u)
[ "$current_uid" = "$AUTHORIZED_UID" ] || fail "current UID $current_uid is not the authorized owner UID"

current_ip=$(curl -4fsS --max-time 5 https://api.ipify.org 2>/dev/null || true)
[ -n "$current_ip" ] || fail "could not determine public IPv4; refusing to change AGENTS.md"
[ "$current_ip" = "$AUTHORIZED_PUBLIC_IP" ] || fail "public IP $current_ip is not authorized"

owner_uid=$(stat -f '%u' "$TARGET" 2>/dev/null || stat -c '%u' "$TARGET")
[ "$owner_uid" = "$AUTHORIZED_UID" ] || fail "AGENTS.md owner UID $owner_uid is unexpected"

lock() {
  chmod 0444 "$TARGET"
  printf 'AGENTS.md locked read-only (0444).\n'
}

verify() {
  mode=$(stat -f '%Lp' "$TARGET" 2>/dev/null || stat -c '%a' "$TARGET")
  [ "$mode" = "444" ] || fail "AGENTS.md is not locked; mode is $mode"
  printf 'AGENTS.md verified: owner UID %s, mode %s.\n' "$owner_uid" "$mode"
}

case "${1:-}" in
  lock)
    lock
    ;;
  unlock)
    chmod 0644 "$TARGET"
    printf 'AGENTS.md temporarily unlocked for the authorized owner. Run lock when finished.\n'
    ;;
  edit)
    chmod 0644 "$TARGET"
    trap 'chmod 0444 "$TARGET"' EXIT HUP INT TERM
    "${EDITOR:-vi}" "$TARGET"
    ;;
  verify)
    verify
    ;;
  *)
    printf 'Usage: %s {lock|unlock|edit|verify}\n' "$0" >&2
    exit 2
    ;;
esac
