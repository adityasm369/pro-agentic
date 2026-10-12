# Pro Agentic

A concept library for keeping up with AI, not a feed reader.

Concepts on the front page, each with an explainer grounded in the items that
mention it, and the field's movement visible as concepts appear and accelerate.
Ingestion is RSS, free and offline. The only model call is the explainer, on a
button, cached.

    python3 bin/ingest.py        # pull every enabled source
    ./start.sh                   # serve on :8777 behind the shared SSO
    python3 tests/run.py         # no network, no key required

See `specs/0001-concept-library.md` for why it is shaped this way.
