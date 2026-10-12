#!/usr/bin/env python3
"""Pull every enabled source. Free, offline, no model involved.

  python3 bin/ingest.py              all enabled sources
  python3 bin/ingest.py --only anthropic-news simonw
  python3 bin/ingest.py --reindex    rebuild concept links after an alias edit
  python3 bin/ingest.py --rescore    recompute relevance after a lane edit

Safe to cron. Conditional GET means an unchanged feed costs one 304.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import concepts
import db
import feeds
import rank
import sources


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--reindex", action="store_true")
    ap.add_argument("--rescore", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    log = (lambda *x: None) if a.quiet else print

    db.init()
    con = db.connect()
    added_src = sources.seed(con)
    added_con = concepts.seed(con)
    if added_src or added_con:
        log("seeded %d source(s), %d concept(s)" % (added_src, added_con))

    if a.reindex:
        concepts.reindex(con, log=log)
    if a.rescore:
        rank.rescore(con, log=log)
    if a.reindex or a.rescore:
        con.close()
        return

    t0 = time.time()
    total, errs = feeds.ingest_all(con, only=a.only, log=log)
    n = con.execute("SELECT COUNT(*) FROM item").fetchone()[0]
    links = con.execute("SELECT COUNT(*) FROM item_concept").fetchone()[0]
    log("\n+%d new, %d items total, %d concept links, %d source error(s), %.0fs"
        % (total, n, links, errs, time.time() - t0))
    con.close()


if __name__ == "__main__":
    main()
