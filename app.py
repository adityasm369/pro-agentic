"""Pro Agentic — HTTP surface. Standard library, shared SSO, port 8777.

Read paths are cheap: every number on a page is a COUNT over stored rows.
The only endpoint that spends money is /api/explain, and it is a POST.
"""
import json
import os
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(BASE, "ui")
sys.path.insert(0, BASE)
sys.path.insert(0, "/data/projects/_shared")

import concepts
import db
import explain as explain_mod
import rank
import sources as sources_mod

PORT = int(os.environ.get("PA_PORT", "8777"))
BIND = os.environ.get("PA_BIND", "127.0.0.1")
PORTAL = os.environ.get("PA_PORTAL", "https://me.aditya-sriram-mattaparthi.online")

try:
    import sso
except ImportError:
    sso = None


def _authed(headers):
    # No sso module (a bare checkout) means no gate: the app is still usable
    # locally. On the VPS the module is always there.
    return True if sso is None else bool(sso.authed(headers))


class H(BaseHTTPRequestHandler):
    server_version = "ProAgentic"

    def log_message(self, fmt, *a):
        pass

    # ------------------------------------------------------------ helpers --
    def _send(self, code, payload, ctype="application/json", cache="no-store"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _file(self, path, ctype):
        try:
            with open(path, "rb") as fh:
                return self._send(200, fh.read(), ctype, cache="no-cache")
        except OSError:
            return self._send(404, {"error": "not found"})

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}") if n else {}
        except (ValueError, TypeError):
            return {}

    def _gate(self, path):
        if _authed(self.headers):
            return False
        if path.startswith("/api/"):
            self._send(401, {"error": "sign in at the portal"})
        else:
            nxt = urllib.parse.quote("https://%s%s" % (self.headers.get("Host") or "", path))
            self.send_response(302)
            self.send_header("Location", "%s/login?next=%s" % (PORTAL, nxt))
            self.end_headers()
        return True

    # ---------------------------------------------------------------- GET --
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        p, q = u.path, urllib.parse.parse_qs(u.query)
        if p == "/healthz":
            return self._send(200, {"ok": True})
        if p == "/favicon.svg":
            return self._file(os.path.join("/data/projects/_shared/icons", "proagentic.svg"),
                              "image/svg+xml")
        if self._gate(p):
            return
        if p in ("/", "/index.html"):
            return self._file(os.path.join(UI, "index.html"), "text/html; charset=utf-8")

        con = db.connect()
        try:
            if p == "/api/library":
                days = int((q.get("days", ["30"])[0]) or 30)
                return self._send(200, {
                    "ok": True,
                    "concepts": concepts.library(con, days=days),
                    "days": days,
                    "stats": self._stats(con)})

            if p == "/api/emerging":
                return self._send(200, {"ok": True, "terms": concepts.emerging(con)})

            if p == "/api/concept":
                slug = q.get("slug", [""])[0]
                c = con.execute("SELECT * FROM concept WHERE slug=?", (slug,)).fetchone()
                if not c:
                    return self._send(404, {"error": "no such concept"})
                items = [dict(r) for r in con.execute(
                    "SELECT i.*, s.name AS source FROM item_concept ic "
                    "JOIN item i ON i.id = ic.item_id JOIN source s ON s.id = i.source_id "
                    "WHERE ic.slug=? ORDER BY COALESCE(i.published_at, i.first_seen) DESC "
                    "LIMIT 120", (slug,))]
                for it in items:
                    it["rel_terms"] = json.loads(it.get("rel_terms") or "[]")
                return self._send(200, {"ok": True, "concept": dict(c), "items": items})

            if p == "/api/items":
                days = int((q.get("days", ["7"])[0]) or 7)
                order = "i.relevance DESC, t DESC" if q.get("sort", [""])[0] == "relevance" \
                    else "t DESC"
                rows = con.execute(
                    "SELECT i.*, s.name AS source, "
                    "COALESCE(i.published_at, i.first_seen) AS t "
                    "FROM item i JOIN source s ON s.id = i.source_id "
                    "WHERE COALESCE(i.published_at, i.first_seen) >= ? "
                    "ORDER BY " + order + " LIMIT 200",
                    (time.time() - days * 86400,)).fetchall()
                items = []
                for r in rows:
                    d = dict(r)
                    d["rel_terms"] = json.loads(d.get("rel_terms") or "[]")
                    d["concepts"] = [x[0] for x in con.execute(
                        "SELECT slug FROM item_concept WHERE item_id=?", (d["id"],))]
                    items.append(d)
                return self._send(200, {"ok": True, "items": items, "days": days})

            if p == "/api/sources":
                return self._send(200, {"ok": True, "sources": [
                    dict(r) for r in con.execute("SELECT * FROM source ORDER BY kind, name")]})
            return self._send(404, {"error": "not found"})
        finally:
            con.close()

    def _stats(self, con):
        now = time.time()
        g = lambda sql, *a: con.execute(sql, a).fetchone()[0]
        return {
            "items": g("SELECT COUNT(*) FROM item"),
            "today": g("SELECT COUNT(*) FROM item WHERE COALESCE(published_at,first_seen)>=?",
                       now - 86400),
            "week": g("SELECT COUNT(*) FROM item WHERE COALESCE(published_at,first_seen)>=?",
                      now - 7 * 86400),
            "month": g("SELECT COUNT(*) FROM item WHERE COALESCE(published_at,first_seen)>=?",
                       now - 30 * 86400),
            "concepts": g("SELECT COUNT(*) FROM concept WHERE status='accepted'"),
            "sources_ok": g("SELECT COUNT(*) FROM source WHERE enabled=1 AND last_error IS NULL"),
            "sources_bad": g("SELECT COUNT(*) FROM source WHERE enabled=1 AND last_error IS NOT NULL"),
            "last_ingest": g("SELECT MAX(last_ok) FROM source") or 0,
        }

    # --------------------------------------------------------------- POST --
    def do_POST(self):
        u = urllib.parse.urlsplit(self.path)
        p = u.path
        if self._gate(p):
            return
        b = self._body()
        con = db.connect()
        try:
            if p == "/api/explain":
                # The only paid call in the app.
                try:
                    r = explain_mod.explain(con, b.get("slug") or "",
                                            tier=b.get("tier"), force=bool(b.get("force")))
                except explain_mod.ExplainUnavailable as exc:
                    return self._send(200, {"ok": False, "error": str(exc)[:300]})
                return self._send(200, {"ok": True, **r})

            if p == "/api/concept/accept":
                slug = concepts.accept(con, b.get("term") or "", name=b.get("name"),
                                       kind=b.get("kind") or "idea")
                concepts.reindex(con)
                return self._send(200, {"ok": True, "slug": slug})

            if p == "/api/concept/reject":
                return self._send(200, {"ok": True,
                                        "slug": concepts.reject(con, b.get("term") or "")})

            if p == "/api/item/mark":
                col = "read_at" if b.get("what") == "read" else "saved_at"
                val = None if b.get("off") else time.time()
                con.execute("UPDATE item SET %s=? WHERE id=?" % col, (val, b.get("id")))
                n = con.total_changes
                con.commit()
                return self._send(200 if n else 404, {"ok": bool(n)})

            if p == "/api/ingest":
                import feeds
                sources_mod.seed(con)
                concepts.seed(con)
                added, errs = feeds.ingest_all(con, log=lambda *x: None)
                return self._send(200, {"ok": True, "added": added, "errors": errs,
                                        "stats": self._stats(con)})
            return self._send(404, {"error": "not found"})
        finally:
            con.close()


def main():
    db.init()
    con = db.connect()
    sources_mod.seed(con)
    concepts.seed(con)
    con.close()
    srv = ThreadingHTTPServer((BIND, PORT), H)
    srv.daemon_threads = True
    print("Pro Agentic on http://%s:%d" % (BIND, PORT), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
