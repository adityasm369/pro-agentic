"""How much does this item matter to HIM, specifically.

He asked for his profile to push storage, security-compliance and agentic work
up the list, with nothing hidden. So this returns a score and the terms that
earned it -- never a filter. The page shows everything; the marked ones sort
first, and the reason is visible so a wrong mark is obvious rather than
mysterious.

Terms come from his Job Hunter profile when it is readable, and fall back to a
static list when it is not, so this project does not break if that one moves.
Whole-word matching, same discipline as concepts.py.
"""
import json
import os
import re

JH_PROFILE = os.environ.get(
    "PA_PROFILE", "/data/projects/job-hunter/profile/profile.json")

# Weight by how much a hit actually tells us. "storage" in an AI feed is a
# strong signal about his lane; "security" is common enough to be weaker.
LANES = {
    "storage": (["storage", "nas", "san", "object storage", "block storage",
                 "replication", "disaster recovery", "vsan", "hci", "filesystem",
                 "file system", "s3", "data path"], 30),
    "compliance": (["stig", "disa", "compliance", "hardening", "cis benchmark",
                    "fedramp", "nist", "iso 27001", "audit", "zero trust",
                    "scap", "cve", "vulnerability"], 25),
    "agentic": (["agent", "agentic", "mcp", "tool use", "orchestration",
                 "multi-agent", "coding agent", "autonomous"], 20),
    "infra": (["kubernetes", "vmware", "vsphere", "hypervisor", "virtualisation",
               "virtualization", "cloud foundation", "on-premise", "on-prem",
               "datacenter", "data centre"], 15),
    "platform": (["python", "linux", "c++", "rest api", "middleware",
                  "distributed systems", "observability"], 10),
}
_CACHE = {}


def _pat(term):
    p = _CACHE.get(term)
    if p is None:
        p = _CACHE[term] = re.compile(
            r"(?<![a-z0-9])" + re.escape(term.lower()) + r"s?(?![a-z0-9])")
    return p


def profile_terms():
    """His own skills, if the Job Hunter profile is readable. Additive to the
    lanes above -- a skill he lists is evidence of interest even when it is not
    one of the five lanes."""
    try:
        with open(JH_PROFILE, encoding="utf-8") as fh:
            p = json.load(fh)
    except (OSError, ValueError):
        return []
    out = set()
    for s in (p.get("skills") or []):
        name = (s.get("name") if isinstance(s, dict) else s) or ""
        name = name.strip().lower()
        # Single short words make for noisy matches; multi-word skills are
        # specific enough to be worth it.
        if len(name) >= 5 and len(name.split()) <= 4:
            out.add(name)
    return sorted(out)[:150]


def score(title, summary="", extra_terms=None):
    """-> (0-100, [matched terms]). Never filters, only ranks."""
    text = ("%s %s" % (title or "", summary or "")).lower()
    if not text.strip():
        return 0, []
    total, hits = 0, []
    for lane, (terms, weight) in LANES.items():
        found = [t for t in terms if _pat(t).search(text)]
        if found:
            # One hit in a lane is the signal; five is the same signal louder.
            total += weight + min(len(found) - 1, 2) * 3
            hits.extend(found[:3])
    for t in (extra_terms or []):
        if _pat(t).search(text):
            total += 4
            hits.append(t)
    return min(100, total), sorted(set(hits))[:8]


def rescore(con, log=None):
    """Recompute every item's relevance. Needed after the lane list changes."""
    extra = profile_terms()
    n = 0
    for r in con.execute("SELECT id, title, summary FROM item"):
        s, terms = score(r["title"], r["summary"], extra)
        con.execute("UPDATE item SET relevance=?, rel_terms=? WHERE id=?",
                    (s, json.dumps(terms), r["id"]))
        n += 1
    con.commit()
    if log:
        log("rescored %d items" % n)
    return n
