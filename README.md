# Agent Memory Examples

Four runnable examples of the dominant agent-memory implementation patterns, all using **Anthropic Claude** as the LLM (via the shared `config.py` -> `LLM_MODEL`). Each script is standalone: `uv run examples/<file>.py`.

All shared configuration (model, index names, dims, cloud/region, Mem0 config) lives in **`config.py`** at the project root, imported by every example.

| # | Script | Pattern | Long-term memory store |
|---|--------|---------|------------------------|
| 01 | `01_short_term_memory.py` | Short-term / working memory: sliding window + LLM summarization of evicted turns | — (context window only) |
| 02 | `02_diy_episodic_semantic.py` | DIY long-term memory: episodic records + semantic facts distilled by Claude | Pinecone (serverless, 384-dim, local fastembed embeddings) |
| 03 | `03_letta_self_managed.py` | Letta (MemGPT): the agent edits its own memory via tool calls | Letta server's Postgres (in-container), Docker |
| 04 | `04_mem0_extraction.py` | Mem0: automated extraction pipeline (ADD/UPDATE/DELETE/NOOP per fact) | Pinecone (`agent-memory-mem0`, namespace `mem0`) |

## Prerequisites

1. **Python deps** (managed by uv, per [AGENTS.md](AGENTS.md)):
   ```bash
   uv sync
   ```
2. **Keys** — copy `.env.example` to `.env` and fill in:
   - `ANTHROPIC_API_KEY` — used by all four examples (also passed into the Letta container).
   - `PINECONE_API_KEY` — used by examples 02 and 04 (free serverless tier is sufficient).
   - `MEM0_TELEMETRY=False` — required (already in `.env.example`): Mem0's telemetry otherwise tries to create its own `mem0migrations`/index on your vector DB, which trips Pinecone's free-tier 5-index cap.
   - Env must be loaded **before** `import mem0` (see imports order in example 04) — the telemetry flag is read at import time.

## Example 03: Letta server (Docker Desktop)

Start the server with your Anthropic key passed through:

```bash
docker run --name letta -p 8283:8283 \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  ghcr.io/letta-ai/letta:latest
```

- First run pulls the image (~2 GB). The dashboard is at http://localhost:8283.
- Stop later with `docker stop letta && docker rm letta` — ask before restarting in-session per AGENTS.md.
- The example script waits for server health, picks the first Anthropic model the server has registered, and expects no other env config.

## Running

```bash
uv run examples/01_short_term_memory.py        # needs ANTHROPIC_API_KEY
uv run examples/02_diy_episodic_semantic.py    # needs ANTHROPIC + PINECONE
uv run examples/03_letta_self_managed.py       # needs Docker+key; runs server-side LLM calls
uv run examples/04_mem0_extraction.py          # needs ANTHROPIC + PINECONE
```

## Notes

- **Centralized config**: `config.py` holds `LLM_MODEL`, `EMBEDDING_MODEL`/`EMBEDDING_DIMS`, `PINECONE_INDEX_NAME`, `MEM0_INDEX_NAME`/`MEM0_NAMESPACE`, `LETTA_URL`, and `MEM0_CONFIG`. Scripts import from it after a small `sys.path` bootstrap (they live in `examples/`).
- **Model**: `claude-sonnet-4-6` — `claude-sonnet-4-5` hits end-of-life Nov 30, 2026. Note the Anthropic SDK rejects a `temperature` kwarg for 4.6 models, which is why Mem0's config sets `enable_sampling_parameters: False`.
- **Embeddings**: `sentence-transformers/all-MiniLM-L6-v2` (384 dims) via `fastembed` (ONNX, runs in-process, no extra API key). Chosen because Anthropic has no embedding API and `torch`/`onnxruntime` latest have no wheels for Intel macOS — `fastembed 0.7.x` + pinned `onnxruntime 1.20.1` do (`pyproject.toml` pins this).
- **Pinecone indexes**: `agent-memory-demo-384` (ex 02) and `agent-memory-mem0` (ex 04) are auto-created in `aws/us-east-1` if missing. Delete them from the console to reset memory.
- **Ex 02 fact ids** are content-hash based, so semantic facts **overwrite** rather than duplicate across runs; episode ids are per-session.
- **Ex 04** re-runs accumulate into the same user memory (`maya-demo`) — that's the demonstration (contradictions get UPDATEd, not appended). To reset, clear the namespace in console or change `USER_ID`.
- Mem0's extraction pipeline makes one extra LLM call per `add()`; expect slight latency.
