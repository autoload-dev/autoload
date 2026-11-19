#!/bin/sh
nonblocking=false
if [ "$1" = --noblock_for_lock ]; then nonblocking=true; shift; fi
test "$1" = shutdown || exit 99
printf '%s\n' "$PWD" >> "$BAZEL_SHUTDOWN_LOG"
case "$PWD" in
  */failing) exit 23 ;;
  */locked) if "$nonblocking"; then exit 9; else sleep 60; fi ;;
  */hanging) exec "$NODE_BINARY" -e 'require("node:fs").writeFileSync(process.env.HANGING_PID, String(process.pid)); process.on("SIGTERM", () => {}); setInterval(() => {}, 1000)' ;;
esac
