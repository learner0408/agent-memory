"""Letta (MemGPT): agent self-managed memory via Docker server.

The agent itself owns memory: always-resident core memory blocks it edits with tool
calls, plus archival memory it pages in/out via search. Run the server first (see README).
"""

import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from letta_client import Letta
from letta_client.types import CreateBlockParam, MessageCreateParam

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import LETTA_URL  # noqa: E402

load_dotenv()

SCENARIO_1 = (
    "A few things about me for later: I'm Sam, I live in Rotterdam, I'm vegan, "
    "and I'm training for a half marathon in June. Save anything worth remembering."
)
SCENARIO_2 = (
    "Update: I've switched to a ketogenic diet as of this month. "
    "Also, the half marathon got moved to July."
)
SCENARIO_3 = "Given everything you know about me, what should I eat the night before a long training run, and what should I train in?"


def pick_anthropic_model(client: Letta) -> str:
    """Pick the first Anthropic model handle registered on the server.

    Args:
        client: Connected Letta client.

    Returns:
        Model handle string (e.g. "anthropic/claude-sonnet-4-5").
    """
    for m in client.models.list():
        if m.handle.startswith("anthropic/"):
            return m.handle
    raise RuntimeError("No Anthropic model available on the Letta server - check ANTHROPIC_API_KEY in the container env.")


def create_agent(client: Letta, model: str) -> object:
    """Create a Letta agent with editable core memory blocks.

    Args:
        client: Connected Letta client.
        model: Anthropic model handle to register as the agent's LLM.

    Returns:
        Created AgentState object.
    """
    return client.agents.create(
        name="memory-demo",
        model=model,
        memory_blocks=[
            CreateBlockParam(label="persona", value="Friendly assistant with persistent, self-managed memory.", limit=2000),
            CreateBlockParam(label="human", value="Facts about the user Sam will go here as Sam shares them.", limit=2000),
        ],
    )


def say(agent_id: str, client: Letta, text: str) -> None:
    """Send a user turn and print the agent's visible response plus any memory tool activity.

    Args:
        agent_id: Id of the created demo agent.
        client: Connected Letta client.
        text: User message body.
    """
    resp = client.agents.messages.create(agent_id=agent_id, messages=[MessageCreateParam(role="user", content=text)])
    print(f"\nUSER     : {text[:90]}...")
    for m in resp.messages:
        kind = getattr(m, "message_type", type(m).__name__)
        if kind in ("assistant_message", "reasoning_message"):
            text = getattr(m, "text", None)
            if not text:
                content = getattr(m, "content", [])
                text = " ".join(c.get("text", c if isinstance(c, str) else "") for c in content) if isinstance(content, list) else str(content)
            print(f"{kind.upper():>17}: {text[:160]}")
        elif kind == "tool_return_message":
            for tr in getattr(m, "tool_return", []) or []:
                if "memory" in ((tr.name if hasattr(tr, "name") else "") or "").lower():
                    print(f"    [MEMORY TOOL] {tr.name}: {(tr.tool_return or '')[:110]}")


def show_core_memory(client: Letta, agent_id: str) -> None:
    """Print the current content of every core memory block of the agent.

    Args:
        client: Connected Letta client.
        agent_id: Id of the demo agent.
    """
    state = client.agents.retrieve(agent_id=agent_id)
    memory = getattr(state, "memory", None)
    block = None
    if memory is not None:
        get_block = getattr(memory, "get_block", None)
        if get_block:
            try:
                block = get_block("human").value
            except Exception:
                block = None
        if block is None:
            for b in getattr(memory, "blocks", []):
                if getattr(b, "label", "") == "human":
                    block = getattr(b, "value", None)
    if block is None:
        for b in client.agents.blocks.list(agent_id=agent_id):
            if getattr(b, "label", "") == "human":
                block = getattr(b, "value", None)
    print("\n--- CORE MEMORY [human] (edited by the agent itself) ---")
    print(block)


def archival(client: Letta, agent_id: str, query: str) -> None:
    """Search the agent's archival (long-term, out-of-window) memory and print hits.

    Args:
        client: Connected Letta client.
        agent_id: Id of the demo agent.
        query: Search query.
    """
    hits = client.agents.passages.search(agent_id=agent_id, query=query)
    print(f"\n--- ARCHIVAL MEMORY SEARCH: '{query}' ---")
    for p in (getattr(hits, "passages", None) or hits if isinstance(hits, (list, tuple)) else []):
        print(f"  score={round(p.score or 0, 3)}  {p.text[:120]}")


def main() -> None:
    """Wait for the server, run the 3-scenario conversation, and print the self-maintained memory."""
    client = Letta(base_url=LETTA_URL)
    for attempt in range(15):
        try:
            client.health()
            break
        except Exception:
            if attempt == 14:
                raise SystemExit("Letta server not reachable - run the Docker command from README first.")
            time.sleep(2)
    agent = create_agent(client, pick_anthropic_model(client))
    print(f"Agent created: {agent.id} (model: {getattr(agent, 'model', 'server default')})")

    say(agent.id, client, SCENARIO_1)
    say(agent.id, client, SCENARIO_2)
    show_core_memory(client, agent.id)
    say(agent.id, client, SCENARIO_3)
    show_core_memory(client, agent.id)
    archival(client, agent.id, "diet marathon training")


if __name__ == "__main__":
    main()
