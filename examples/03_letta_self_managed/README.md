# Example 03: Letta (self-managed memory) — via Letta App Server

Demonstrates Letta's model: **the agent owns its memory** — it files facts into a per-agent git-backed repository (MemFS) using its own tools, across sessions.

- Requires the **Letta App Server running locally** in Docker (`--backend local`), an **Anthropic key**, and **Node.js 22.19+**.
- The Python-side examples live elsewhere; TypeScript is used here because the official Agent SDK (`@letta-ai/letta-agent-sdk`) is TypeScript-only.

## 1. One-time setup (token lives in the root `.env`)

```bash
# from the project root
openssl rand -hex 32          # copy the output
# add to .env: LETTA_APP_SERVER_TOKEN=<the hex value>
```

Before each `docker run`, regenerate the token file the container mounts — **from `.env`, which stays the single source of truth**:

```bash
grep '^LETTA_APP_SERVER_TOKEN=' .env | cut -d= -f2- > app-server-token
```

## 2. Start the App Server (Docker, from the project root)

```bash
set -a; source .env; set +a     # brings in ANTHROPIC_API_KEY
docker run --rm --name letta-app-server -p 4500:4500 \
  -v "$(pwd)/.letta-state:/root/.letta" \
  -v letta-expr-workspace:/workspace \
  -v "$PWD/app-server-token:/run/secrets/app-server-token:ro" \
  -e ANTHROPIC_API_KEY \
  letta/letta:latest \
  letta server --backend local --listen ws://0.0.0.0:4500 \
  --ws-auth capability-token --ws-token-file /run/secrets/app-server-token
```

- `--backend local` keeps state on the (mounted) local disk: everything under `.letta-state/` on the host.
- First run pulls the image (~323 MB).

## 3. Run the script

```bash
npm install
npx tsx quickstart.ts
```

The script self-loads the root `.env` (dotenv), so no env vars need exporting. Three sessions run against the same agent: facts → corrections (diet/marathon updates) → a quiz answered purely from memory.

## 4. See the memory (the git repo)

The agent stores memory as files under:

```
.letta-state/lc-local-backend/memfs/<agent-id>/memory
```

Inspect it from the host:

```bash
cd .letta-state/lc-local-backend/memfs/<agent-id>/memory
git log --oneline        # each memory edit is a commit
git status --short       # live (uncommitted) edits the agent made most recently
git show                 # latest change
```

## Notes

- State is **not** backed up automatically — the `.letta-state/` directory is the backup target.
- `app-server-token` and `.letta-state/` are gitignored; `LETTA_APP_SERVER_TOKEN` in `.env` is the durable copy.
