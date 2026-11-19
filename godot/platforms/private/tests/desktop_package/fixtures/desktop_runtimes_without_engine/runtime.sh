#!/usr/bin/env bash
set -euo pipefail
location="$(cd -- "$(dirname -- "$0")" && pwd)"
if [[ -f "$location/Game.pck" ]]; then
    cat "$location/Game.pck"
else
    cat "$location/../Resources/Game.pck"
fi
