#!/usr/bin/env sh
# Usage: ./jhb.sh <command> ...   (or: python -m jhb <command>)
cd "$(dirname "$0")" && exec python3 -m jhb "$@"
