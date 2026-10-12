"""Concepts: the unit this portal is organised around.

A headline is perishable and a concept is not. Forty posts about MCP are forty
posts; MCP is one thing worth understanding, and it stays worth understanding
next month. So the library is concepts, and items hang off them.

Two ways a concept gets here:

  seeded      a starting vocabulary, with aliases, so day one is not empty.
  emerging    a term that recurs ACROSS SOURCES in a short window. One source
              saying a word twice is that author's habit; three sources saying
              it in a week is the field moving, which is the thing he asked to
              be able to see. Emerging terms are proposed, never auto-added:
              the library is his, and a wrong concept is worse than a missing
              one because it pollutes every count that follows.

Matching is WHOLE-WORD. The Job Hunter build spent a day on a bug where the
term `go` matched "algorithm", "Google" and "gold"; the same mistake here
would attach half the corpus to the wrong concept.
"""
import json
import re
import time

# slug, display name, kind, aliases
SEED = [
    ("mcp", "Model Context Protocol (MCP)", "protocol",
     ["mcp", "model context protocol"]),
    ("agents", "Agents", "idea",
     ["agent", "agentic", "agentic ai", "multi-agent", "agent harness"]),
    ("tool-use", "Tool use / function calling", "technique",
     ["tool use", "tool calling", "function calling", "tool runner"]),
    ("rag", "Retrieval-augmented generation", "technique",
     ["rag", "retrieval augmented generation", "agentic rag", "retrieval-augmented"]),
    ("evals", "Evals", "technique",
     ["eval", "evals", "benchmark", "leaderboard", "llm-as-a-judge", "llm as a judge"]),
    ("fine-tuning", "Fine-tuning", "technique",
     ["fine-tuning", "fine tuning", "finetuning", "lora", "qlora", "peft", "rlhf", "dpo"]),
    ("reasoning", "Reasoning and test-time compute", "technique",
     ["chain of thought", "chain-of-thought", "test-time compute", "test time compute",
      "extended thinking", "reasoning model", "inference-time"]),
    ("context", "Context engineering", "technique",
     ["context window", "long context", "context engineering", "prompt caching",
      "context compaction"]),
    ("prompting", "Prompting", "technique",
     ["prompt engineering", "system prompt", "few-shot", "zero-shot", "meta-prompt"]),
    ("safety", "Safety and alignment", "idea",
     ["alignment", "ai safety", "red team", "red-teaming", "jailbreak",
      "constitutional ai", "interpretability"]),
    ("ai-security", "AI security", "idea",
     ["prompt injection", "model poisoning", "data exfiltration", "owasp llm",
      "ai security", "supply chain attack", "guardrail", "guardrails"]),
    ("governance", "Governance and compliance", "idea",
     ["ai act", "eu ai act", "nist ai rmf", "iso 42001", "model card",
      "ai governance", "compliance", "stig", "soc 2"]),
    ("multimodal", "Multimodal", "technique",
     ["multimodal", "vision model", "vision-language", "text-to-image",
      "text to video", "speech-to-text"]),
    ("local-models", "Open-weight and local models", "idea",
     ["open-weight", "open weights", "open source model", "llama", "mistral",
      "qwen", "gemma", "deepseek", "ollama", "gguf", "quantization", "quantisation"]),
    ("infra", "Serving and infrastructure", "idea",
     ["inference", "vllm", "kv cache", "gpu", "tpu", "serving", "throughput",
      "latency", "batching", "distillation"]),
    ("coding-agents", "Coding agents", "tool",
     ["coding agent", "code agent", "swe-bench", "claude code", "copilot",
      "cursor", "devin", "codex"]),
    ("memory", "Agent memory", "technique",
     ["agent memory", "long-term memory", "memory tool", "scratchpad",
      "episodic memory"]),
    ("orchestration", "Orchestration frameworks", "tool",
     ["langchain", "langgraph", "llamaindex", "crewai", "autogen", "dspy",
      "pydantic ai", "workflow engine"]),
    ("robotics", "Embodied AI and robotics", "idea",
     ["robotics", "embodied", "world model", "vla model"]),
    ("economics", "Cost and economics", "idea",
     ["token cost", "price per token", "cost per task", "inference cost",
      "capex", "compute spend"]),
]

# Words that look like terms and carry nothing. Without this the emerging-term
# detector proposes "The Model" and "New AI" every single week.
STOP = set("""the a an and or of to in for with on at by from as is are was were be
been being this that these those it its his her their our your my we i you they
them he she across over under into than then so such which who whom whose what
when where why how not no nor but if while during after before above below up
down out off again further once all any both each few more most other some only
own same too very can will just should now also via per within without upon among
between through about against new news today week month year first last next best
large small long short high low fast slow full real deep multi single cross self
and or but not with without via using used use make made get got see seen show shown
why how use using used make makes made get gets got one two three ai llm llms model
models data open source free paper papers blog post posts update updates release
releases version versions here there what's whats introducing announcing""".split())

MIN_SOURCES = 2        # a term in one source is that author's habit
MIN_MENTIONS = 3
WINDOW_DAYS = 21


def _pattern(alias):
    # Whole-word, and the alias may contain spaces, dots or hyphens.
    return re.compile(r"(?<![a-z0-9])" + re.escape(alias.lower()) + r"(?![a-z0-9])")


_CACHE = {}


def _compiled(alias):
    p = _CACHE.get(alias)
    if p is None:
        p = _CACHE[alias] = _pattern(alias)
    return p


def seed(con):
    """Insert the starting vocabulary. Never overwrites an existing row: his
    edits to a name, the aliases or the status outrank the seed list."""
    n = 0
    for slug, name, kind, aliases in SEED:
        cur = con.execute(
            "INSERT OR IGNORE INTO concept (slug,name,aliases,kind,status,seeded) "
            "VALUES (?,?,?,?,'accepted',1)",
            (slug, name, json.dumps(aliases), kind))
        n += cur.rowcount
    con.commit()
    return n


def vocabulary(con, status="accepted"):
    """-> [(slug, [compiled alias patterns])] for matching."""
    rows = con.execute("SELECT slug, name, aliases FROM concept WHERE status=?",
                       (status,)).fetchall()
    out = []
    for r in rows:
        try:
            aliases = json.loads(r["aliases"] or "[]")
        except ValueError:
            aliases = []
        terms = {a.lower().strip() for a in (aliases or []) if a and a.strip()}
        terms.add(r["slug"].replace("-", " "))
        out.append((r["slug"], [_compiled(t) for t in sorted(terms)]))
    return out


def match(text, vocab):
    """-> sorted list of slugs whose vocabulary appears in `text`."""
    low = (text or "").lower()
    if not low:
        return []
    return sorted({slug for slug, pats in vocab if any(p.search(low) for p in pats)})


def reindex(con, log=None):
    """Rebuild item_concept from scratch. Needed after he edits a concept's
    aliases, because the links were computed at ingest time."""
    vocab = vocabulary(con)
    con.execute("DELETE FROM item_concept")
    n = 0
    for r in con.execute("SELECT id, title, summary FROM item"):
        for slug in match((r["title"] or "") + " " + (r["summary"] or ""), vocab):
            con.execute("INSERT OR IGNORE INTO item_concept (item_id,slug) VALUES (?,?)",
                        (r["id"], slug))
            n += 1
    con.commit()
    if log:
        log("reindexed: %d links" % n)
    return n


# ------------------------------------------------------------- emergence ---
# Acronyms and names that are technical but carry no concept. Without these the
# detector proposes API, GPU and LLM every week, which is true and useless.
TECH_STOP = set("""api apis gpu gpus cpu tpu llm llms ai ml nlp sdk cli url http https
json yaml xml html css pdf csv sql rest grpc ssh tls ssl cpu ram ssd hdd os io ux ui
id ids faq ceo cto phd usa uk eu us ieee acm arxiv github gitlab aws gcp azure ibm
pr prs ci cd qa rfc iso nist mit bsd gpl apache python java rust golang js ts npm pip
docker k8s vm vms sdk app apps web api2 v1 v2 v3 v4 v5 2024 2025 2026 2027
new now top best next big one two three first last paper code data model models
openai google meta microsoft nvidia amazon apple deepmind anthropic mistral
gpt chatgpt bert gan cnn rnn lstm mlp relu sota eval evals benchmark""".split())

MIN_SOURCES = 3        # one source is an author's habit, two is a coincidence
MIN_MENTIONS = 4
WINDOW_DAYS = 21

_ACRONYM = re.compile(r"\b([A-Z]{3,8})\b")
_CAMEL = re.compile(r"\b([A-Za-z]+[a-z][A-Z][A-Za-z]*)\b")
_VERSIONED = re.compile(r"\b([A-Za-z][A-Za-z.+#-]{1,18}[-\s]?\d+(?:\.\d+)?)\b")


def _candidate_terms(title, summary):
    """Terms that could be a NEW concept, as opposed to a common word.

    Only three shapes qualify, and the restriction is the whole point. An
    earlier version also accepted any capitalised word mid-sentence, which
    produced 532 candidates led by "api", "large" and "training" -- because
    arXiv and most blogs write titles in Title Case, so every word looks like
    a proper noun. Precision matters more than recall here: ten real
    candidates he reads beat five hundred he ignores.

      ACRONYM    MCP, GRPO, DPO, RLHF      3-8 capitals
      CamelCase  LangGraph, vLLM, LlamaIndex
      versioned  GPT-5, Qwen3, Llama 4      a name carrying a number

    A multi-word phrase like "Mixture of Experts" is deliberately NOT detected;
    it cannot be told apart from a Title Case fragment without a language model,
    and guessing produces exactly the noise this replaced.
    """
    text = "%s. %s" % (title or "", summary or "")
    out = set()
    for m in _ACRONYM.findall(text):
        if m.lower() not in TECH_STOP and m.lower() not in STOP:
            out.add(m.lower())
    for m in _CAMEL.findall(text):
        if m.lower() not in TECH_STOP and m.lower() not in STOP and len(m) >= 4:
            out.add(m.lower())
    for m in _VERSIONED.findall(text):
        t = " ".join(m.split()).lower()
        head = re.split(r"[-\s]?\d", t)[0].strip("-. ")
        # Only grammar words are rejected here, NOT TECH_STOP: a version number
        # is what makes a common family name newsworthy. Bare "GPT" is noise and
        # is stopped above; "GPT-6" is a release and must survive.
        if head and head not in STOP and len(head) >= 2 and not t[0].isdigit():
            out.add(t)
    return {t for t in out if 2 < len(t) <= 30 and t not in STOP}


def emerging(con, days=WINDOW_DAYS, min_sources=MIN_SOURCES, min_mentions=MIN_MENTIONS):
    """Terms recurring across sources that no accepted concept covers.

    Returns [{term, mentions, sources, first_seen, examples}], busiest first.
    Proposals only -- nothing is added to the library here.
    """
    since = time.time() - days * 86400
    known = vocabulary(con)
    rejected = {r[0] for r in con.execute(
        "SELECT LOWER(name) FROM concept WHERE status='rejected'")}
    seen = {}
    for r in con.execute(
            "SELECT id, source_id, title, summary, COALESCE(published_at, first_seen) AS t "
            "FROM item WHERE COALESCE(published_at, first_seen) >= ?", (since,)):
        text = (r["title"] or "") + " " + (r["summary"] or "")
        covered = set()
        for slug, pats in known:
            if any(p.search(text.lower()) for p in pats):
                covered.add(slug)
        for term in _candidate_terms(r["title"], r["summary"]):
            if term in rejected:
                continue
            # Covered by a concept already in the library? Then it is not new.
            if any(p.search(term) for _, pats in known for p in pats):
                continue
            d = seen.setdefault(term, {"term": term, "mentions": 0, "sources": set(),
                                       "first_seen": r["t"], "examples": []})
            d["mentions"] += 1
            d["sources"].add(r["source_id"])
            d["first_seen"] = min(d["first_seen"], r["t"] or d["first_seen"])
            if len(d["examples"]) < 3:
                d["examples"].append({"id": r["id"], "title": r["title"]})
    out = [{**d, "sources": sorted(d["sources"]), "n_sources": len(d["sources"])}
           for d in seen.values()
           if len(d["sources"]) >= min_sources and d["mentions"] >= min_mentions]
    out.sort(key=lambda d: (-d["n_sources"], -d["mentions"], d["term"]))
    return out


def accept(con, term, name=None, kind="idea", aliases=None):
    slug = re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")[:40]
    con.execute("INSERT OR REPLACE INTO concept (slug,name,aliases,kind,status,"
                "seeded,first_seen) VALUES (?,?,?,?,'accepted',0,?)",
                (slug, name or term, json.dumps(sorted({term.lower()} | set(aliases or []))),
                 kind, time.time()))
    con.commit()
    return slug


def reject(con, term):
    slug = re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")[:40]
    con.execute("INSERT OR REPLACE INTO concept (slug,name,aliases,kind,status,seeded) "
                "VALUES (?,?,?,?,'rejected',0)",
                (slug, term, json.dumps([term.lower()]), "idea"))
    con.commit()
    return slug


# ----------------------------------------------------------------- trend ---
def library(con, days=30):
    """Every accepted concept with its real activity. Counts are counts."""
    since = time.time() - days * 86400
    prev = since - days * 86400
    out = []
    for c in con.execute("SELECT * FROM concept WHERE status='accepted' ORDER BY name"):
        row = con.execute(
            "SELECT COUNT(*) n, "
            "  SUM(CASE WHEN COALESCE(i.published_at,i.first_seen) >= ? THEN 1 ELSE 0 END) recent, "
            "  SUM(CASE WHEN COALESCE(i.published_at,i.first_seen) >= ? "
            "           AND COALESCE(i.published_at,i.first_seen) < ? THEN 1 ELSE 0 END) before, "
            "  MAX(COALESCE(i.published_at,i.first_seen)) last, "
            "  COUNT(DISTINCT i.source_id) srcs "
            "FROM item_concept ic JOIN item i ON i.id = ic.item_id WHERE ic.slug=?",
            (since, prev, since, c["slug"])).fetchone()
        n, recent, before = row["n"] or 0, row["recent"] or 0, row["before"] or 0
        out.append({
            "slug": c["slug"], "name": c["name"], "kind": c["kind"],
            "total": n, "recent": recent, "before": before,
            "sources": row["srcs"] or 0, "last": row["last"],
            # Direction only, and only when there is something to compare to.
            # A percentage off two items would be arithmetic theatre.
            "trend": ("new" if before == 0 and recent > 0 else
                      "up" if recent > before else
                      "down" if recent < before else "level") if n else "quiet",
            "explained": bool(c["explainer"]),
        })
    out.sort(key=lambda d: (-d["recent"], -d["total"], d["name"]))
    return out
