"""The one model call: explain a concept, grounded in what is being said now.

This is the only part of Pro Agentic that costs money, and it runs on a button.
Everything else -- ingestion, matching, trends -- is arithmetic over stored
rows and works with no key at all.

Why it is worth a call rather than a link to someone's blog post: the model is
given the ACTUAL ITEMS from his feeds that mention the concept, and asked to
explain it as those items discuss it. That makes the answer current and
specific to the corpus he is reading, which is the one thing a general chatbot
answer cannot be. It also means the explanation can be checked against the
items listed beneath it.

Cached by (concept, prompt version, the set of items used), so pressing it
twice costs nothing and a stale explainer is detectable rather than silent.
"""
import hashlib
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
PROMPT_VERSION = 2
TIER = "sonnet"
MAX_ITEMS = 18

sys.path.insert(0, "/data/projects/job-hunter")   # anthropic_api lives there


class ExplainUnavailable(Exception):
    pass


def _client():
    try:
        import anthropic_api as claude
    except ImportError as exc:
        raise ExplainUnavailable(
            "the Anthropic client is not reachable: %s" % exc) from exc
    if not claude.available():
        raise ExplainUnavailable("no Anthropic key configured")
    return claude


# Who the explanation is pitched at. Kept in a file rather than hardcoded here:
# this repository is public, and an explainer tuned to one person's CV is both a
# privacy question and worse software -- anyone cloning it would get answers
# written for somebody else. Edit reader.md (gitignored) to make it yours.
READER = os.path.join(BASE, "reader.md")
DEFAULT_READER = """a senior software engineer with a decade of backend and
infrastructure experience and some applied AI. Assume distributed systems, APIs,
security and operations are second nature."""


def reader():
    try:
        with open(READER, encoding="utf-8") as fh:
            t = fh.read().strip()
            if t:
                return t
    except OSError:
        pass
    return DEFAULT_READER


SYSTEM_TEMPLATE = """You explain one concept in AI to %s

Do NOT explain what an LLM is. Do explain what is genuinely new or specific
about this concept.

You are given recent items from his feeds that mention it. Explain the concept
AS THOSE ITEMS DISCUSS IT -- what people are actually doing with it right now,
not a textbook definition. If the items disagree, say so. If the items are thin
or off-topic, say that plainly rather than padding from memory; a short honest
answer is worth more than a confident vague one.

Structure, in markdown, no preamble:

**What it is** - two or three sentences.
**Why it exists** - the problem it solves, and what people did before.
**Where it stands now** - what these items show is happening, with dates where
the items give them. Name sources.
**Worth your time?** - a direct verdict for this reader specifically.
"Not yet, because..." is a fine answer.
**To try it** - one concrete first step, or say there is nothing to try yet.

Rules: never invent a fact, a date, a version or a benchmark that is not in the
items. Do not use the words "delve", "landscape", "revolutionise" or "unlock"."""


def system_prompt():
    return SYSTEM_TEMPLATE % reader()


def _fingerprint(slug, item_ids):
    return hashlib.sha256(
        json.dumps([PROMPT_VERSION, slug, sorted(item_ids)]).encode()).hexdigest()[:16]


def grounding(con, slug, limit=MAX_ITEMS):
    """The items the explanation must be built from: most recent first, because
    a concept's current meaning is carried by its current coverage."""
    rows = con.execute(
        "SELECT i.id, i.title, i.summary, i.url, s.name AS source, "
        "       COALESCE(i.published_at, i.first_seen) AS t "
        "FROM item_concept ic JOIN item i ON i.id = ic.item_id "
        "JOIN source s ON s.id = i.source_id "
        "WHERE ic.slug = ? ORDER BY t DESC LIMIT ?", (slug, limit)).fetchall()
    return [dict(r) for r in rows]


def explain(con, slug, tier=None, force=False):
    """-> {explainer, model, cached, n_items, cost_usd}."""
    c = con.execute("SELECT * FROM concept WHERE slug=?", (slug,)).fetchone()
    if not c:
        raise ExplainUnavailable("no such concept: %s" % slug)
    items = grounding(con, slug)
    if not items:
        raise ExplainUnavailable(
            "nothing in the library mentions this yet, so there is nothing to "
            "ground an explanation in. Run an ingest first.")
    fp = _fingerprint(slug, [i["id"] for i in items])
    if not force and c["explainer"] and (c["explain_items"] or "") == fp:
        return {"explainer": c["explainer"], "model": c["explain_model"],
                "cached": True, "n_items": len(items), "cost_usd": 0.0,
                "explained_at": c["explained_at"]}

    claude = _client()
    import datetime
    lines = []
    for i in items:
        when = (datetime.date.fromtimestamp(i["t"]).isoformat() if i["t"] else "undated")
        lines.append("- [%s] %s — %s\n  %s" % (
            when, i["source"], i["title"], (i["summary"] or "")[:320]))
    user = ("CONCEPT: %s\n\nRECENT ITEMS FROM HIS FEEDS (%d):\n%s"
            % (c["name"], len(items), "\n".join(lines)))
    try:
        # 8000, not 2000: the model reasons before it writes and that counts
        # against the cap. 2000 was hit on the first real run, with a ~600
        # token explainer as the actual output.
        text, meta = claude.call(tier or TIER, system_prompt(), user, max_tokens=8000)
    except Exception as exc:
        raise ExplainUnavailable(str(exc)[:240]) from exc

    con.execute("UPDATE concept SET explainer=?, explained_at=?, explain_model=?, "
                "explain_items=? WHERE slug=?",
                (text.strip(), time.time(), meta.get("model"), fp, slug))
    con.commit()
    return {"explainer": text.strip(), "model": meta.get("model"), "cached": False,
            "n_items": len(items), "cost_usd": meta.get("cost_usd") or 0.0,
            "explained_at": time.time()}
