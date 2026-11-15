import { config } from "dotenv";
import path from "node:path";

config({ path: path.resolve(import.meta.dirname, "../../.env") });

import { LettaAgentClient } from "@letta-ai/letta-agent-sdk";

const SCENARIO_1 =
  "A few things about me for later: I'm Sam, I live in Rotterdam, I'm vegan, " +
  "and I'm training for a half marathon in June. Remember whatever is worth remembering.";
const SCENARIO_2 =
  "Update: as of this month I've switched to a ketogenic diet. " +
  "Also, the half marathon got moved to July.";
const SCENARIO_3 =
  "Using everything you know about me: what should I eat the night before a long training run, and why?";

function resolveToken(): string {
  const token = process.env.LETTA_APP_SERVER_TOKEN;
  if (!token) {
    throw new Error("LETTA_APP_SERVER_TOKEN is not set - put it in the project .env");
  }
  return token;
}

async function streamEvents(messages) {
  for await (const m of messages) {
    const evt = m as Record<string, any>;
    if (evt.type === "assistant") {
      process.stdout.write(evt.content || "");
    } else if (evt.type === "tool_call") {
      const label = String(evt.toolName ?? "");
      const inputStr = JSON.stringify(evt.toolInput ?? "").toLowerCase();
      if (/memory|memfs/i.test(label + inputStr)) {
        const input = evt.toolInput ?? {};
        const detail = input.description || input.file_path || input.command || "";
        console.log(`\n  [MEMORY TOOL] ${label}: ${String(detail).slice(0, 90)}`);
      }
    }
  }
  process.stdout.write("\n---\n");
}

async function main() {
  const client = new LettaAgentClient({
    backend: "remote",
    url: process.env.LETTA_APP_SERVER_URL ?? "http://127.0.0.1:4500",
    authToken: resolveToken(),
  });

  const agentId = await client.createAgent({
    persona: "You are a friendly assistant with persistent, self-managed memory stored in your own memory repository.",
    human: "Facts about the user Sam will be recorded here as Sam shares them.",
  });
  console.log("Agent ID:", agentId);

  await using session1 = client.createSession(agentId, { cwd: "/workspace" });
  console.log("\nSESSION 1 - tell the agent facts; watch it file them in its memory repo");
  await streamEvents(session1.stream(await session1.send(SCENARIO_1)));

  await using session2 = client.createSession(agentId, { cwd: "/workspace" });
  console.log("\nSESSION 2 - new session, same agent: corrections must land in the same memory");
  await streamEvents(session2.stream(await session2.send(SCENARIO_2)));

  await using session3 = client.createSession(agentId, { cwd: "/workspace" });
  console.log("\nSESSION 3 - quiz cross-session memory");
  await streamEvents(session3.stream(await session3.send(SCENARIO_3)));

  console.log("\n--- YOUR AGENT'S MEMORY LIVES HERE (host-visible bind mount) ---");
  console.log(`cd ${process.cwd()}/../../.letta-state/lc-local-backend/memfs/${agentId}/memory`);
  console.log("git log --oneline");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
