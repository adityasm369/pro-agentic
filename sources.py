"""The source list. Editorial, and therefore in one file he can edit.

A curated list decides what he sees, so it is kept visible rather than buried
in a database migration. Every item on the page names its source for the same
reason. `kind` is used only to group the source page.
"""
SOURCES = [
    # Every URL here was probed and returned XML. A guessed feed URL 404s
    # silently into the error column and the source simply never appears, so
    # the list is verified rather than plausible. Anthropic publishes no RSS
    # for its news or engineering blog as of Oct 2026 -- both 404 -- so they
    # are absent rather than listed broken.

    # --- the labs: primary announcements, no intermediary -------------------
    ("openai-news",     "OpenAI",                "https://openai.com/news/rss.xml",                  "lab"),
    ("deepmind",        "Google DeepMind",       "https://deepmind.google/blog/rss.xml",             "lab"),
    ("googleai",        "Google Research",       "https://research.google/blog/rss/",                "lab"),
    ("google-ai-blog",  "Google · The Keyword",  "https://blog.google/technology/ai/rss/",           "lab"),
    ("mistral",         "Mistral AI",            "https://mistral.ai/rss.xml",                       "lab"),
    ("msr",             "Microsoft Research",    "https://www.microsoft.com/en-us/research/feed/",   "lab"),
    ("meta-eng",        "Meta Engineering",      "https://engineering.fb.com/feed/",                 "lab"),

    # --- research: where a technique appears before it has a name -----------
    ("arxiv-ai",        "arXiv cs.AI",           "https://rss.arxiv.org/rss/cs.AI",                  "research"),
    ("arxiv-cl",        "arXiv cs.CL",           "https://rss.arxiv.org/rss/cs.CL",                  "research"),
    ("arxiv-lg",        "arXiv cs.LG",           "https://rss.arxiv.org/rss/cs.LG",                  "research"),
    ("arxiv-cr",        "arXiv cs.CR (security)","https://rss.arxiv.org/rss/cs.CR",                  "research"),
    ("bair",            "Berkeley BAIR",         "https://bair.berkeley.edu/blog/feed.xml",          "research"),

    # --- tooling: the part he asked for, "use the latest tools" -------------
    ("hf-blog",         "Hugging Face",          "https://huggingface.co/blog/feed.xml",             "tooling"),
    ("github-ai",       "GitHub Blog · AI",      "https://github.blog/ai-and-ml/feed/",              "tooling"),
    ("modal",           "Modal",                 "https://modal.com/blog/atom.xml",                  "tooling"),
    ("llamaindex",      "LlamaIndex",            "https://medium.com/feed/@llama_index",             "tooling"),
    ("nvidia-dev",      "NVIDIA Developer",      "https://developer.nvidia.com/blog/feed",           "tooling"),
    ("aws-ml",          "AWS Machine Learning",  "https://aws.amazon.com/blogs/machine-learning/feed/", "tooling"),
    ("azure",           "Microsoft Azure",       "https://azure.microsoft.com/en-us/blog/feed/",     "tooling"),

    # --- the people who read everything so he does not have to --------------
    ("simonw",          "Simon Willison",        "https://simonwillison.net/atom/everything/",       "newsletter"),
    ("latent-space",    "Latent Space",          "https://www.latent.space/feed",                    "newsletter"),
    ("import-ai",       "Import AI",             "https://importai.substack.com/feed",               "newsletter"),
    ("sebastian",       "Sebastian Raschka",     "https://magazine.sebastianraschka.com/feed",       "newsletter"),
    ("interconnects",   "Interconnects",         "https://www.interconnects.ai/feed",                "newsletter"),

    # --- security + AI: his lane -------------------------------------------
    ("owasp-genai",     "OWASP GenAI",           "https://genai.owasp.org/feed/",                    "security"),
    ("nist-cyber",      "NIST Cybersecurity",    "https://www.nist.gov/blogs/cybersecurity-insights/rss.xml", "security"),
]


def seed(con):
    """Insert any source not already present. Never overwrites `enabled`,
    `etag` or the error state -- re-seeding must not silently re-enable a feed
    he turned off, nor discard a conditional-GET token."""
    n = 0
    for sid, name, url, kind in SOURCES:
        cur = con.execute(
            "INSERT OR IGNORE INTO source (id,name,url,kind,enabled) VALUES (?,?,?,?,1)",
            (sid, name, url, kind))
        n += cur.rowcount
        # Name and URL are editorial and may be corrected here; the rest is state.
        con.execute("UPDATE source SET name=?, url=?, kind=? WHERE id=?",
                    (name, url, kind, sid))
    con.commit()
    return n
