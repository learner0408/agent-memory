"""DIY long-term memory: episodic + semantic, stored in Pinecone, recalled per turn.

Episodes = raw interaction records. Semantic = durable facts distilled from them.
Both are embedded locally with fastembed (all-MiniLM-L6-v2, 384 dims), upserted to a
Pinecone serverless index, then retrieved by similarity and injected into each turn.
"""

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv
from fastembed import TextEmbedding
from pinecone import Pinecone, ServerlessSpec

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import CLOUD, EMBEDDING_DIMS as DIMENSIONS, EMBEDDING_MODEL, LLM_MODEL as MODEL, PINECONE_INDEX_NAME as INDEX_NAME, REGION  # noqa: E402

load_dotenv()

SESSION_1 = [
    ("user", "Hi, I'm Maya. I'm a data scientist in Austin."),
    ("assistant", "Nice to meet you, Maya! How can I help?"),
    ("user", "I deploy models to AWS and I read papers weekly. I'm allergic to shellfish."),
    ("assistant", "Noted. What would you like to work on today?"),
]
SESSION_2 = [
    ("user", "Back again. I switched to PyTorch Lightning for training runs last week."),
    ("assistant", "Got it. Anything else changed?"),
    ("user", "Also I've started reviewing papers on Thursdays instead of Mondays."),
    ("assistant", "Will keep that in mind."),
]
QUERY = "When is Maya's paper-reading habit scheduled, and what framework does she train with?"


def embed(client: TextEmbedding, texts: list[str]) -> list[list[float]]:
    """Embed texts locally with fastembed MiniLM.

    Args:
        client: Initialized fastembed TextEmbedding model.
        texts: Texts to embed.

    Returns:
        List of 384-dim float vectors, in input order.
    """
    return [vec.tolist() for vec in client.embed(texts)]


def ensure_index(pc: Pinecone) -> object:
    """Create the demo index if absent and return a ready Index handle.

    Args:
        pc: Authenticated Pinecone client.

    Returns:
        pinecone.Index handle for INDEX_NAME.
    """
    if INDEX_NAME not in {i["name"] for i in pc.list_indexes()}:
        pc.create_index(name=INDEX_NAME, dimension=DIMENSIONS, metric="cosine", spec=ServerlessSpec(cloud=CLOUD, region=REGION))
    while not pc.describe_index(INDEX_NAME).status["ready"]:
        time.sleep(2)
    return pc.Index(INDEX_NAME)


def store_episodes(index: object, embedder: TextEmbedding, session: list[tuple[str, str]], session_id: int) -> None:
    """Upsert one episode vector per interaction turn.

    Args:
        index: Pinecone index handle.
        embedder: fastembed model for vectorization.
        session: Ordered (role, text) interaction turns for this session.
        session_id: Integer id of the session (used in metadata).
    """
    texts = [f"Session {session_id} | {role} said: {text}" for role, text in session]
    vectors = embed(embedder, texts)
    now = datetime.now(timezone.utc).isoformat()
    index.upsert(vectors=[{"id": f"ep-{session_id}-{i}", "values": v, "metadata": {"kind": "episodic", "role": role, "session": session_id, "ts": now, "text": text}} for i, ((role, text), v) in enumerate(zip(session, vectors))])


def distill_semantic(client: Anthropic, episodes: list[tuple[str, str]], prior_facts: list[str]) -> list[str]:
    """Merge episode text into durable semantic facts.

    Args:
        client: Anthropic client for the extraction call.
        episodes: (role, text) turns of the new session.
        prior_facts: Semantic facts already distilled from earlier sessions.

    Returns:
        Updated full list of durable facts (deduped, merges new info into old facts).
    """
    transcript = "\n".join(f"{r}: {t}" for r, t in episodes)
    prompt = (
        f"Known facts:\n{json.dumps(prior_facts) if prior_facts else '[]'}\n\n"
        f"New episode transcript:\n{transcript}\n\n"
        "Extract durable, user-level facts (identity, preferences, schedules, skills). "
        "Merge new info into conflicting old facts instead of restating them. "
        "Drop transient talk. Reply with ONLY a JSON array of fact strings."
    )
    resp = client.messages.create(model=MODEL, max_tokens=400, messages=[{"role": "user", "content": prompt}])
    raw = resp.content[0].text.strip()
    start, end = raw.find("["), raw.rfind("]")
    return json.loads(raw[start : end + 1])


def store_facts(index: object, embedder: TextEmbedding, facts: list[str]) -> None:
    """Upsert each semantic fact as its own vector, keyed by content hash.

    Args:
        index: Pinecone index handle.
        embedder: fastembed model for vectorization.
        facts: Durable fact strings (upserted by hash so edits overwrite cleanly).
    """
    vectors = embed(embedder, facts)
    now = datetime.now(timezone.utc).isoformat()
    index.upsert(vectors=[{"id": f"fact-{hashlib.md5(f.encode()).hexdigest()[:12]}", "values": v, "metadata": {"kind": "semantic", "ts": now, "text": f}} for f, v in zip(facts, vectors)])


def recall(index: object, embedder: TextEmbedding, query: str, top_k: int = 4) -> list[dict]:
    """Retrieve the top_k most similar stored records for a query.

    Args:
        index: Pinecone index handle.
        embedder: fastembed model for vectorizing the query.
        query: Query string.
        top_k: Matches returned.

    Returns:
        Match dicts: {"kind", "text", "score"} sorted by similarity score.
    """
    vec = embed(embedder, [query])[0]
    res = index.query(vector=vec, top_k=top_k, include_metadata=True)
    return [{"kind": m["metadata"]["kind"], "text": m["metadata"]["text"], "score": round(m["score"], 3)} for m in res["matches"]]


def answer(client: Anthropic, recalled: list[dict], query: str) -> str:
    """Answer the query using only the recalled long-term memory injected in the prompt.

    Args:
        client: Anthropic client.
        recalled: Matching records from recall().
        query: The user's question for this turn.

    Returns:
        Claude's answer text.
    """
    context = "\n".join(f"- [{r['kind']}] (score {r['score']}) {r['text']}" for r in recalled)
    system = f"You are an agent whose ONLY knowledge of the user comes from this long-term memory:\n{context}"
    resp = client.messages.create(model=MODEL, max_tokens=300, system=system, messages=[{"role": "user", "content": query}])
    return resp.content[0].text.strip()


def main() -> None:
    """Run two sessions (writing episodic records and distilled semantic facts), then prove retrieval."""
    pc = Pinecone()
    index = ensure_index(pc)
    embedder = TextEmbedding(model_name=EMBEDDING_MODEL)
    client = Anthropic()

    facts: list[str] = []
    for session_id, session in [(1, SESSION_1), (2, SESSION_2)]:
        store_episodes(index, embedder, session, session_id)
        facts = distill_semantic(client, episodes=session, prior_facts=facts)
        store_facts(index, embedder, facts)
        print(f"Session {session_id}: episodes stored; semantic memory now {json.dumps(facts, indent=1)}")

    recalled = recall(index, embedder, QUERY, top_k=8)
    print(f"\nQUERY: {QUERY}\n\nRECALLED MEMORY:")
    for r in recalled:
        print(f"  [{r['kind']:8}] score={r['score']}  {r['text']}")
    print(f"\nANSWER: {answer(client, recalled, QUERY)}")


if __name__ == "__main__":
    main()
