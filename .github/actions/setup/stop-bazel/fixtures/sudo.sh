#!/bin/sh
test "$1" = -n || exit 99
shift
exec "$@"
