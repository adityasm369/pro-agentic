#!/bin/sh
# Pull every source. Conditional GET means an unchanged feed costs one 304, so
# this is cheap enough to run often and costs nothing at all -- no model is
# involved in ingestion.
docker exec -u node openclaw-87fc-openclaw-1 sh -c \
  'cd /data/projects/pro-agentic && python3 bin/ingest.py --quiet' \
  >> /var/log/proagentic-ingest.log 2>&1
