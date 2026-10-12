# 0001 — A concept library, not a feed reader

- **Status:** accepted
- **Date:** 2026-10-12
- **Area:** everything (v1)

## Evidence

His words: *"a portal for learning all the latest live updates on AI, the
concepts, and how the AI world is evolving, as of this month and today ... so
that I can keep myself updated with the latest happenings and use the latest
tools."*

Asked what it should lead with, he chose **concept library first**: concepts on
the front page, each with an explainer, and the news items that reference it
hanging off it.

That choice is the whole design. A feed reader loses to the firehose — AI
produces more headlines per day than anyone reads, and a list sorted by time
rewards whoever posted last. A concept is the unit that actually persists: MCP
matters for a year, the forty posts about MCP do not. And a concept **appearing
for the first time** is the clearest available signal of the field moving,
which is the "how the AI world is evolving" part he asked for and the part a
chronological list cannot show.

## Required behaviour

1. **Ingest is free and offline.** RSS/Atom from a curated source list on a
   cron, with conditional GET. No model is involved in ingestion, so the
   portal keeps working, and costing nothing, if the Anthropic key is absent.
2. **Concepts are extracted mechanically**, whole-word against a seeded
   vocabulary with aliases (MCP = Model Context Protocol). Matching must not
   repeat the Job Hunter substring bug: `go` must not match `algorithm`.
3. **Emerging concepts are detected, not just known ones.** A capitalised or
   technical term that recurs across **more than one source** inside a short
   window is a candidate, surfaced for him to accept or reject. A term seen in
   one source once is noise; the same term in three sources in a week is the
   field moving.
4. **Each concept has an explainer written on demand and cached** — grounded in
   the items that actually mention it, so it explains the concept *as it is
   being discussed now* rather than from the model's training data. That
   grounding is the only reason this beats asking a chatbot.
5. **Nothing is hidden.** Items relevant to his profile (storage, security
   compliance, agentic) are marked and sort higher; everything else is still
   there.
6. **Every number on the page is real.** An item count is a count of stored
   items. A trend is computed from timestamps. Nothing is estimated and
   presented as measured.

## Out of scope for v1

Full-text search, embeddings, recommendations, comments, a public view, email
digests, and any write-back to his other projects.

## Shape

```
feeds.py     fetch + parse RSS/Atom           stdlib only
concepts.py  vocabulary, extraction, emergence
rank.py      profile relevance marker
explain.py   the one model call, cached
db.py        SQLite
app.py       ThreadingHTTPServer + shared SSO
bin/ingest.py  cron entry
```

## Verification

A test suite that runs with no network and no key: parsing of real RSS and
Atom fixtures including a malformed one; whole-word concept matching with the
`go`/`algorithm` case asserted; emergence requiring more than one source;
dedupe by URL across refetches; relevance marking; and the explainer cached,
grounded, and degrading to a clear message when no key is configured.

## Risks

A curated source list is an editorial choice and will skew what he sees; the
sources are therefore listed in one file he can edit, and the page names the
source of every item. Concept extraction by keyword will miss things a human
would catch — hence requirement 3, which is the escape hatch.
