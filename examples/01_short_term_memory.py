"""Short-term (working) memory: sliding window + LLM summarization of older turns."""

import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import KEEP_LAST, LLM_MODEL as MODEL  # noqa: E402

load_dotenv()

SCRIPTED_CONVERSATION = [
    "Hi! I'm planning a 5-day trip to Japan in March with my spouse.",
    "Our budget is around 2500 USD for the two of us, excluding flights.",
    "We love food, temples, and cherry blossoms. We are vegetarians.",
    "We'll be flying in and out of Tokyo.",
    "Should we rent a car or use trains?",
    "Great, thanks! One more thing - do we need to buy a rail pass in advance?",
]


def summarize(client: Anthropic, old_turns: list[dict], prior_summary: str) -> str:
    """Compress older conversation turns into a running summary.

    Args:
        client: Anthropic client used for the summarization call.
        old_turns: Oldest turns being evicted from the window, as {"role", "content"} dicts.
        prior_summary: Existing rolling summary to merge into.

    Returns:
        Updated summary text covering prior_summary plus new old_turns.
    """
    transcript = "\n".join(f"{t['role']}: {t['content']}" for t in old_turns)
    prompt = (
        f"Existing summary:\n{prior_summary or '(none)'}\n\n"
        f"New turns to fold in:\n{transcript}\n\n"
        "Merge the new turns into the summary. Keep every fact (names, numbers, "
        "preferences, decisions). Reply with only the updated summary."
    )
    resp = client.messages.create(model=MODEL, max_tokens=500, messages=[{"role": "user", "content": prompt}])
    return resp.content[0].text.strip()


def window_management(client: Anthropic, history: list[dict], summary: str) -> tuple[str, str, bool]:
    """Decide what stays in the context window: evict old turns, summarize them.

    Args:
        client: Anthropic client for the summarization call.
        history: Current dialogue, as {"role", "content"} dicts.
        summary: Current rolling summary of evicted turns.

    Returns:
        Tuple of (new summary, full dialogue kept by caller, evicted flag).
    """
    overflow = len(history) - KEEP_LAST
    if overflow >= 2:
        summary = summarize(client, history[:overflow], summary)
        history = history[overflow:]
        history.insert(0, {"role": "user", "content": f"[Summary of earlier conversation]\n{summary}"})
        return summary, history, True
    return summary, history, False


def reply(client: Anthropic, history: list[dict]) -> tuple[str, int]:
    """Send the current window to Claude and return its answer.

    Args:
        client: Anthropic client.
        history: The in-window dialogue including summary header if present.

    Returns:
        Tuple of (assistant response text, input_tokens billed for this turn).
    """
    resp = client.messages.create(model=MODEL, max_tokens=600, messages=history)
    return resp.content[0].text, resp.usage.input_tokens


def main() -> None:
    """Simulate a 6-turn conversation, showing what survives in the working-memory window."""
    client = Anthropic()
    history: list[dict] = []
    summary = ""
    for user_msg in SCRIPTED_CONVERSATION:
        history.append({"role": "user", "content": user_msg})
        summary, history, evicted = window_management(client, history, summary)
        if evicted:
            print(f"\n[EVICTED + SUMMARIZED] window now holds {len(history) - 1} raw turns + 1 summary block")
        answer, input_tokens = reply(client, history)
        print(f"\nUser   : {user_msg}")
        print(f"Claude : {answer[:220]}{'...' if len(answer) > 220 else ''}")
        print(f"[input_tokens={input_tokens}]")
        history.append({"role": "assistant", "content": answer})
    print("\n--- FINAL WORKING MEMORY (what a resumed session would see) ---")
    for m in history:
        print(f"{m['role'].upper():>10}: {m['content'][:120]}")


if __name__ == "__main__":
    main()
