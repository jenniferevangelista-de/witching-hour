// One recorded hunt: three questions in the same memory thread, so the follow-ups
// only make sense if the agent remembers the night it found first.
import { writeFileSync } from "node:fs";
import { API, MODEL, mastra } from "./crew.js";

const QUESTIONS = [
  "Which night was the most haunted? Open its case file and tell me what Luna and Dr. Bigotes each said about it.",
  "And that same night, what did Xochi write to the family in the morning?",
  "Now look at tonight's forecast. Should the family worry about any room?",
];

function calls(res: any): { tool: string; args: unknown }[] {
  const raw: any[] = [...(res.toolCalls ?? []), ...((res.steps ?? []) as any[]).flatMap((s: any) => s.toolCalls ?? [])];
  const seen = new Set<string>();
  return raw.map((c) => ({
    id: c.payload?.toolCallId ?? c.toolCallId ?? JSON.stringify(c).slice(0, 60),
    tool: c.payload?.toolName ?? c.toolName ?? "unknown",
    args: c.payload?.args ?? c.args ?? c.input ?? {},
  })).filter((c) => (seen.has(c.id) ? false : (seen.add(c.id), true))).map(({ tool, args }) => ({ tool, args }));
}

const agent = mastra.getAgentById("ghost-hunter");
const memory = { resource: "witching-hour-demo", thread: `hunt-${Date.now()}` };
const runs = [];
for (const question of QUESTIONS) {
  const t0 = Date.now();
  const res: any = await agent.generate(question, { memory, maxSteps: 6 });
  const run = { question, answer: res.text, steps: calls(res).map((c) => ({ tool: c.tool, args: c.args })), model: `${MODEL} via Ollama (Mastra agent with memory)`, seconds: Math.round((Date.now() - t0) / 1000), usage: res.usage ?? null };
  console.log(`\nQ: ${question}\n${run.steps.map((s) => `  -> ${s.tool}(${JSON.stringify(s.args)})`).join("\n")}\nA: ${run.answer}`);
  runs.push(run);
}
writeFileSync(process.env.WH_OUT ?? "../demo_data/mastra_runs.json", JSON.stringify({ api: API, thread: memory.thread, runs }, null, 1));
