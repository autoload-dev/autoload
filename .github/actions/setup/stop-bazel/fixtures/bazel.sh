#!/bin/sh
# Logs each shutdown's workspace and output base; a successful one stops the fake server.
output_base=
nonblocking=false
while [ $# -gt 1 ]; do
    case "$1" in
        --output_base=*) output_base=${1#--output_base=} ;;
        --noblock_for_lock) nonblocking=true ;;
        *) exit 99 ;;
    esac
    shift
done
test "$1" = shutdown || exit 99
printf '%s %s\n' "$PWD" "$output_base" >>"$BAZEL_SHUTDOWN_LOG"
case "$PWD" in
    */failing) exit 23 ;;
    */locked) if "$nonblocking"; then exit 9; else sleep 60; fi ;;
    */hanging) exec "$NODE_BINARY" -e 'require("node:fs").writeFileSync(process.env.HANGING_PID, String(process.pid)); process.on("SIGTERM", () => {}); setInterval(() => {}, 1000)' ;;
esac
kill "$(cat "$output_base/server/server.pid.txt")"
