#!/bin/sh
case "${3:-}" in
  */cache_mount) exit 0 ;;
  *) exit 1 ;;
esac
