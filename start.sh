#!/bin/sh
# Serve Pro Agentic. --expose binds 0.0.0.0 so the Traefik sidecar can reach it;
# without it the app answers only on loopback and the public host 502s while
# looking healthy from inside the container.
cd "$(dirname "$0")"
[ "$1" = "--expose" ] && export PA_BIND=0.0.0.0
[ -f data/pid ] && kill "$(cat data/pid)" 2>/dev/null
sleep 0.3
mkdir -p data
nohup python3 app.py > data/server.log 2>&1 &
echo $! > data/pid
sleep 1
printf 'pro-agentic pid %s on %s:%s\n' "$(cat data/pid)" "${PA_BIND:-127.0.0.1}" "${PA_PORT:-8777}"
tail -2 data/server.log
