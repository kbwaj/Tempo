#!/bin/sh
set -eu
cd "$(dirname "$0")"
exec python3 tempo_prototype/tempo_demo.py
