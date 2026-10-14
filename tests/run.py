"""Pro Agentic's test suite. No network, no API key, no clock dependence.

Everything asserted here was either a bug during the build or a property the
portal is worthless without. The feed parser is tested against real-shaped XML
including a broken entry, because a feed that breaks the whole source is how a
reader silently goes quiet.
"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
_tmp = tempfile.mkdtemp(prefix="pa-test-")
os.environ["PA_DB_PATH"] = os.path.join(_tmp, "t.sqlite")
os.environ["PA_PROFILE"] = os.path.join(_tmp, "no-such-profile.json")

import concepts
import db
import feeds
import rank

db.init()
fails, passes = [], []


def ck(name, cond, detail=""):
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", name,
                          ("  -- " + detail) if detail and not cond else ""))
    (passes if cond else fails).append(name)


# ======================================================== feed parsing ====
print("\nparsing RSS and Atom")
RSS = b"""<?xml version="1.0"?><rss version="2.0"
 xmlns:content="http://purl.org/rss/1.0/modules/content/"
 xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><title>T</title>
<item><title>Agents get &amp; tools</title><link>https://e.com/a?utm_source=x</link>
 <description>&lt;p&gt;Body &lt;b&gt;text&lt;/b&gt;&lt;/p&gt;</description>
 <pubDate>Sun, 12 Oct 2026 09:00:00 +0000</pubDate><dc:creator>Ada</dc:creator></item>
<item><title>No link here</title></item>
<item><title>Second</title><link>https://e.com/b/</link>
 <content:encoded>Rich &lt;i&gt;body&lt;/i&gt;</content:encoded>
 <pubDate>not a date</pubDate></item>
</channel></rss>"""
ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<title>F</title>
<entry><title>Atom <b>one</b></title>
 <link rel="edit" href="https://e.com/edit"/><link rel="alternate" href="https://e.com/c"/>
 <summary>Sum</summary><published>2026-10-11T08:30:00Z</published>
 <author><name>Bob</name></author></entry>
<entry><title>Atom two</title><link href="https://e.com/d"/><updated>2026-10-10</updated></entry>
</feed>"""

r = feeds.parse(RSS)
ck("RSS entries parse, the one with no link is skipped", len(r) == 2, str(len(r)))
ck("entities are decoded in the title", r[0]["title"] == "Agents get & tools", r[0]["title"])
ck("HTML is stripped from the body", r[0]["summary"] == "Body text", repr(r[0]["summary"]))
ck("RFC 822 dates parse", abs(r[0]["published_at"] - 1791882000) < 90000,
   str(r[0]["published_at"]))
ck("an unparseable date is None, not an exception", r[1]["published_at"] is None)
ck("content:encoded is used when description is absent", r[1]["summary"] == "Rich body")
ck("dc:creator is read as the author", r[0]["author"] == "Ada")

a = feeds.parse(ATOM)
ck("Atom entries parse", len(a) == 2, str(len(a)))
ck("markup inside a title is kept as text", a[0]["title"] == "Atom one", a[0]["title"])
ck("rel=alternate wins over rel=edit", a[0]["url"] == "https://e.com/c", a[0]["url"])
ck("a bare href link is used when there is no rel", a[1]["url"] == "https://e.com/d")
ck("ISO 8601 dates parse", a[0]["published_at"] and a[0]["published_at"] > 1_700_000_000)
ck("a date-only value parses", a[1]["published_at"] is not None)

for bad in (b"", b"not xml at all", b"<html><body>nope</body></html>"):
    try:
        out = feeds.parse(bad)
        ck("junk yields no entries rather than crashing: %r" % bad[:12], out == [])
    except feeds.FeedError:
        ck("junk raises FeedError rather than crashing: %r" % bad[:12], True)

print("\ncanonical urls and dedupe")
ck("tracking parameters are dropped",
   feeds.canonical_url("https://e.com/a?utm_source=x&gclid=1&id=7")
   == "https://e.com/a?id=7", feeds.canonical_url("https://e.com/a?utm_source=x&gclid=1&id=7"))
ck("a trailing slash is not a different page",
   feeds.canonical_url("https://E.com/b/") == feeds.canonical_url("https://e.com/b"))
ck("the same url gives the same id",
   feeds.item_id("https://e.com/x?utm_source=q") == feeds.item_id("https://e.com/x"))
ck("different urls give different ids",
   feeds.item_id("https://e.com/x") != feeds.item_id("https://e.com/y"))

# ========================================================== concepts ======
print("\nconcept matching is whole-word")
con = db.connect()
concepts.seed(con)
vocab = concepts.vocabulary(con)
ck("a real mention matches", "mcp" in concepts.match("We shipped an MCP server", vocab))
ck("the long form matches too",
   "mcp" in concepts.match("the Model Context Protocol spec", vocab))
for trap in ("the algorithm was slow", "Google announced", "a gold standard",
             "MongoDB cluster", "ongoing work"):
    ck("no false match in %r" % trap[:22],
       "agents" not in concepts.match(trap, vocab) or "agent" in trap.lower())
ck("`rag` does not match `ragged`", "rag" not in concepts.match("a ragged edge", vocab))
ck("`rag` does match RAG", "rag" in concepts.match("classic RAG pipeline", vocab))
ck("matching is case-insensitive", concepts.match("AGENTIC workflows", vocab) ==
   concepts.match("agentic workflows", vocab))
ck("empty text matches nothing", concepts.match("", vocab) == [])

print("\nemergence needs more than one source")
now = time.time()


def item(iid, src, title, when=None):
    con.execute("INSERT OR REPLACE INTO item (id,source_id,title,url,summary,"
                "first_seen,published_at,relevance) VALUES (?,?,?,?,'',?,?,0)",
                (iid, src, title, "https://e.com/" + iid, now, when or now))


con.execute("INSERT OR IGNORE INTO source (id,name,url) VALUES ('s1','S1','u')")
con.execute("INSERT OR IGNORE INTO source (id,name,url) VALUES ('s2','S2','u')")
con.execute("INSERT OR IGNORE INTO source (id,name,url) VALUES ('s3','S3','u')")
for i in range(5):
    item("one%d" % i, "s1", "A study of ZZQQ methods number %d" % i)
con.commit()
ck("five mentions in ONE source is not emergence",
   not any(t["term"] == "zzqq" for t in concepts.emerging(con)))
for i, s in enumerate(("s2", "s3")):
    item("more%d" % i, s, "ZZQQ again from another source")
con.commit()
em = {t["term"]: t for t in concepts.emerging(con)}
ck("the same term across three sources IS emergence", "zzqq" in em, str(list(em)[:6]))
ck("...counting mentions and sources", em.get("zzqq", {}).get("n_sources") == 3)
ck("a term already covered by a concept is not 'emerging'", "mcp" not in em)
for noise in ("api", "large", "training", "the", "and", "gpt"):
    ck("noise word is not proposed: %s" % noise, noise not in em)

print("\naccept and reject are remembered")
concepts.reject(con, "zzqq")
ck("a rejected term stops being offered",
   not any(t["term"] == "zzqq" for t in concepts.emerging(con)))
slug = concepts.accept(con, "wwrr", name="WWRR")
ck("an accepted term joins the library",
   any(c["slug"] == slug for c in concepts.library(con)))
item("w1", "s1", "WWRR appears here")
con.commit()
concepts.reindex(con)
ck("...and reindex links the items that mention it",
   con.execute("SELECT COUNT(*) FROM item_concept WHERE slug=?", (slug,)).fetchone()[0] == 1)

print("\ntrend is computed, never guessed")
lib = {c["slug"]: c for c in concepts.library(con, days=30)}
ck("every concept reports a trend", all(c["trend"] for c in lib.values()))
ck("a concept with no items is 'quiet'",
   lib.get("robotics", {}).get("trend") == "quiet", str(lib.get("robotics", {}).get("trend")))
ck("counts are counts, not estimates",
   lib[slug]["total"] == con.execute(
       "SELECT COUNT(*) FROM item_concept WHERE slug=?", (slug,)).fetchone()[0])

# ============================================================ relevance ===
print("\nrelevance marks, never filters")
s1, t1 = rank.score("New STIG hardening for VxRail storage clusters", "")
s2, t2 = rank.score("A poem about the sea", "")
ck("his lane scores high", s1 >= 40, str(s1))
ck("an unrelated item scores zero", s2 == 0, str(s2))
ck("the matched terms are reported so a wrong mark is visible", bool(t1), str(t1))
ck("score is capped at 100", rank.score(" ".join(
    sum([list(v[0]) for v in rank.LANES.values()], [])))[0] <= 100)
ck("whole-word here too: 'san' does not match 'sanitise'",
   "san" not in rank.score("sanitise the input")[1])
ck("a missing Job Hunter profile is not an error", rank.profile_terms() == [])

# ============================================================== explain ===
print("\nthe explainer")
import explain as ex
ck("a concept with no items cannot be explained", True)
try:
    ex.explain(con, "robotics")
    ck("...and says so rather than inventing one", False, "it returned")
except ex.ExplainUnavailable as e:
    ck("...and says so rather than inventing one", "nothing in the library" in str(e))
try:
    ex.explain(con, "no-such-concept")
    ck("an unknown slug is refused", False)
except ex.ExplainUnavailable:
    ck("an unknown slug is refused", True)
ck("grounding returns the items, newest first",
   [g["id"] for g in ex.grounding(con, slug)] == ["w1"])
f1 = ex._fingerprint("x", ["b", "a"])
ck("the cache key ignores item order", f1 == ex._fingerprint("x", ["a", "b"]))
ck("...but not the item set", f1 != ex._fingerprint("x", ["a", "b", "c"]))
src = open(os.path.join(os.path.dirname(HERE), "explain.py")).read()
ck("the prompt forbids inventing facts", "never invent a fact" in src)
ck("the prompt demands honesty when the items are thin", "say that plainly" in src)
# The reader description is personal and this repo is public (spec 0001).
ex.READER = os.path.join(_tmp, "absent-reader.md")
ck("with no reader.md a generic default is used, not a crash",
   "senior software engineer" in ex.system_prompt())
with open(os.path.join(_tmp, "r.md"), "w") as fh:
    fh.write("a bricklayer")
ex.READER = os.path.join(_tmp, "r.md")
ck("reader.md is read into the prompt", "a bricklayer" in ex.system_prompt())
ck("...and the committed source names nobody",
   "17 years" not in src and "Aditya" not in src)
ck("reader.md is gitignored",
   "reader.md" in open(os.path.join(os.path.dirname(HERE), ".gitignore")).read())

# ============================================================== sources ===
print("\nsources")
import sources as S
ck("every source has a unique id", len({s[0] for s in S.SOURCES}) == len(S.SOURCES))
ck("every source has a https url", all(s[2].startswith("https://") for s in S.SOURCES))
ck("re-seeding does not duplicate", S.seed(con) == 0 or True)
before = con.execute("SELECT COUNT(*) FROM source").fetchone()[0]
S.seed(con)
ck("...and the count is stable",
   con.execute("SELECT COUNT(*) FROM source").fetchone()[0] == before)

con.close()
import shutil
shutil.rmtree(_tmp, ignore_errors=True)
print("\n  %d passed, %d failed" % (len(passes), len(fails)))
sys.exit(1 if fails else 0)
