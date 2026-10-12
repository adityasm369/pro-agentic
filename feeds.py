"""Fetch and parse RSS and Atom. Standard library only.

No feedparser, for the same reason the rest of this estate avoids
dependencies: the formats are twenty years old and barely move, and the parts
that actually break -- a feed that lies about its encoding, a date in a format
nobody standardised, a <content:encoded> full of HTML -- are not handled for
you by a library either.

Conditional GET is used throughout. A feed that has not changed costs one 304,
which is what makes a frequent cron polite rather than abusive.
"""
import email.utils
import gzip
import hashlib
import html
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = ("Mozilla/5.0 (compatible; ProAgentic/1.0; +personal learning portal; "
      "one request per source per run)")
TIMEOUT = 25
MAX_BYTES = 8 * 1024 * 1024
SUMMARY_CHARS = 700

NS = {"atom": "http://www.w3.org/2005/Atom",
      "content": "http://purl.org/rss/1.0/modules/content/",
      "dc": "http://purl.org/dc/elements/1.1/"}


class FeedError(Exception):
    pass


# --------------------------------------------------------------- fetching ---
def fetch(url, etag=None, modified=None):
    """-> (body_bytes, etag, modified) or (None, etag, modified) on 304."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/atom+xml, application/rss+xml, "
        "application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
        "Accept-Encoding": "gzip"})
    if etag:
        req.add_header("If-None-Match", etag)
    if modified:
        req.add_header("If-Modified-Since", modified)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise FeedError("feed larger than %d bytes" % MAX_BYTES)
            if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            return raw, r.headers.get("ETag"), r.headers.get("Last-Modified")
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return None, etag, modified
        raise FeedError("HTTP %s" % e.code) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise FeedError("%s: %s" % (type(e).__name__, e)) from e


# ---------------------------------------------------------------- parsing ---
def _text(el):
    if el is None:
        return ""
    # itertext(), not .text: a <title> containing markup has its words in the
    # children, and .text alone returns the empty string before the first tag.
    return html.unescape(" ".join(el.itertext())).strip()


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def strip_html(s):
    return _WS.sub(" ", html.unescape(_TAG.sub(" ", s or ""))).strip()


def parse_date(s):
    """-> epoch seconds, or None. Feeds use RFC 822, ISO 8601, and neither."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        return email.utils.parsedate_to_datetime(s).timestamp()
    except (TypeError, ValueError, OverflowError):
        pass
    t = s.replace("Z", "+00:00")
    for cand in (t, t[:19], t[:10]):
        try:
            import datetime
            d = datetime.datetime.fromisoformat(cand)
            if d.tzinfo is None:
                d = d.replace(tzinfo=datetime.timezone.utc)
            return d.timestamp()
        except ValueError:
            continue
    return None


def canonical_url(url):
    """Drop the tracking noise so the same post fetched twice is one item."""
    try:
        u = urllib.parse.urlsplit((url or "").strip())
    except ValueError:
        return (url or "").strip()
    if not u.scheme:
        return (url or "").strip()
    keep = [(k, v) for k, v in urllib.parse.parse_qsl(u.query)
            if not k.lower().startswith(("utm_", "mc_"))
            and k.lower() not in ("gclid", "fbclid", "ref", "source", "gbraid",
                                  "gad_source", "gad_campaignid")]
    path = u.path.rstrip("/") or "/"
    return urllib.parse.urlunsplit(
        (u.scheme.lower(), u.netloc.lower(), path,
         urllib.parse.urlencode(keep), ""))


def item_id(url):
    return hashlib.sha256(canonical_url(url).encode("utf-8")).hexdigest()[:24]


def parse(body):
    """-> list of {title, url, summary, author, published_at}.

    Handles RSS 2.0 and Atom. A feed that will not parse at all raises; a
    single malformed entry inside a good feed is skipped, because losing one
    post is better than losing the source.
    """
    if not body:
        return []
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        raise FeedError("not XML: %s" % e) from e

    out = []
    nodes = root.findall(".//item") or root.findall(".//atom:entry", NS)
    for n in nodes:
        try:
            title = _text(n.find("title")) or _text(n.find("atom:title", NS))
            link = ""
            le = n.find("link")
            if le is not None:
                link = (le.text or "").strip()
            if not link:
                for a in n.findall("atom:link", NS):
                    rel = a.get("rel") or "alternate"
                    if rel == "alternate" and a.get("href"):
                        link = a.get("href").strip()
                        break
                else:
                    a = n.find("atom:link", NS)
                    link = (a.get("href").strip() if a is not None and a.get("href") else "")
            if not link:
                link = _text(n.find("guid"))
            if not link or not title:
                continue
            body_txt = (_text(n.find("content:encoded", NS))
                        or _text(n.find("atom:content", NS))
                        or _text(n.find("description"))
                        or _text(n.find("atom:summary", NS)))
            when = (_text(n.find("pubDate")) or _text(n.find("atom:published", NS))
                    or _text(n.find("atom:updated", NS)) or _text(n.find("dc:date", NS)))
            author = (_text(n.find("atom:author/atom:name", NS))
                      or _text(n.find("dc:creator", NS)) or _text(n.find("author")))
            out.append({"title": strip_html(title)[:400],
                        "url": link,
                        "summary": strip_html(body_txt)[:SUMMARY_CHARS],
                        "author": author[:120] or None,
                        "published_at": parse_date(when)})
        except Exception:
            continue          # one bad entry must not cost the whole feed
    return out


# ------------------------------------------------------------- ingestion ----
def ingest_source(con, row, now=None):
    """Fetch one source and store what is new. -> (added, status)."""
    import concepts
    import rank
    now = now or time.time()
    try:
        body, etag, modified = fetch(row["url"], row["etag"], row["modified"])
    except FeedError as e:
        con.execute("UPDATE source SET last_error=? WHERE id=?", (str(e)[:200], row["id"]))
        con.commit()
        return 0, "error: %s" % e
    if body is None:
        con.execute("UPDATE source SET last_ok=?, last_error=NULL WHERE id=?", (now, row["id"]))
        con.commit()
        return 0, "unchanged"
    try:
        entries = parse(body)
    except FeedError as e:
        con.execute("UPDATE source SET last_error=? WHERE id=?", (str(e)[:200], row["id"]))
        con.commit()
        return 0, "error: %s" % e

    vocab = concepts.vocabulary(con)
    added = 0
    for e in entries:
        iid = item_id(e["url"])
        if con.execute("SELECT 1 FROM item WHERE id=?", (iid,)).fetchone():
            continue
        score, terms = rank.score(e["title"], e["summary"])
        con.execute(
            "INSERT INTO item (id,source_id,title,url,summary,author,published_at,"
            "first_seen,relevance,rel_terms) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (iid, row["id"], e["title"], canonical_url(e["url"]), e["summary"],
             e["author"], e["published_at"], now, score, json.dumps(terms)))
        for slug in concepts.match(e["title"] + " " + (e["summary"] or ""), vocab):
            con.execute("INSERT OR IGNORE INTO item_concept (item_id,slug) VALUES (?,?)",
                        (iid, slug))
        added += 1
    con.execute("UPDATE source SET etag=?, modified=?, last_ok=?, last_error=NULL, "
                "n_items=(SELECT COUNT(*) FROM item WHERE source_id=?) WHERE id=?",
                (etag, modified, now, row["id"], row["id"]))
    con.commit()
    return added, "ok"


def ingest_all(con, only=None, log=print):
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM source WHERE enabled=1 ORDER BY id")]
    if only:
        rows = [r for r in rows if r["id"] in set(only)]
    total, errs = 0, 0
    for r in rows:
        added, status = ingest_source(con, r)
        total += added
        if status.startswith("error"):
            errs += 1
        log("  %-16s %-10s %s" % (r["id"], "+%d" % added if added else "-", status))
    return total, errs
