"""Mem0: automated extraction-pipeline memory (Anthropic LLM + fastembed + Pinecone).

Every turn: mem0.search() before reasoning, mem0.add() after - the pipeline decides
ADD / UPDATE / DELETE / NOOP for each candidate fact, so contradictions overwrite.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from config import MEM0_CONFIG as CONFIG, MEM0_USER_ID as USER_ID  # noqa: E402
from mem0 import Memory  # noqa: E402


def show_add(result: dict) -> None:
    """Print the per-fact pipeline decisions from a mem0.add() call.

    Args:
        result: mem0.add() response dict (mem0 output, may be wrapped in {"results": [...]}).
    """
    events = result.get("results", result if isinstance(result, list) else result.get("events", []))
    for e in events:
        if isinstance(e, dict):
            print(f"    [{e.get('event', 'ADD').upper():6}] {(e.get('memory') or '')[:90]}")


def show_search(result: dict | list) -> None:
    """Print scored memory search results.

    Args:
        result: mem0.search() response, dict with "results", a bare list, or wrapped {"memories": [...]}.
    """
    scores = result.get("results", result.get("memories", [])) if isinstance(result, dict) else result
    for mem in scores:
        if isinstance(mem, dict):
            print(f"    score={round(mem.get('score') or 0, 3)}  {mem.get('memory', '')[:90]}")
        else:
            print(f"    {str(mem)[:90]}")


def main() -> None:
    """Run two sessions against Mem0 to show ADD for new facts and UPDATE on contradiction."""
    m = Memory.from_config(CONFIG)
    sessions = [
        "A couple of things about me - I'm Maya, I work as a data scientist, I'm vegetarian, "
        "and I do my machine-reading on Mondays.",
        "Heads up: I've started eating fish occasionally, and reading moved to Thursdays. "
        "I also picked up poker recently.",
    ]
    for i, text in enumerate(sessions, 1):
        print(f"\n=== SESSION {i} ===")
        print(f"USER : {text[:100]}...")

        print("SEARCH (before reasoning):")
        show_search(m.search(text, filters={"user_id": USER_ID}, limit=5))

        result = m.add([{"role": "user", "content": text}], user_id=USER_ID)
        print("PIPELINE DECISIONS (after turn):")
        show_add(result)

    print("\n=== FINAL MEMORY SEARCH: 'what does Maya eat' ===")
    show_search(m.search("what does Maya eat", filters={"user_id": USER_ID}, limit=5))
    all_memories = m.get_all(filters={"user_id": USER_ID})
    print("\n=== ALL STORED MEMORIES ===")
    records = all_memories.get("results", all_memories if isinstance(all_memories, list) else [])
    for mem in records:
        print(f"  {(mem if isinstance(mem, str) else mem.get('memory', ''))[:100]}")


if __name__ == "__main__":
    main()
