// The Witching Hour ghost hunter, Mastra edition.
// An agent with memory and three tools over the Witching Hour API (the public demo by default),
// running an open-weight model through Ollama's OpenAI-compatible endpoint.
import { Mastra } from "@mastra/core";
import { Agent } from "@mastra/core/agent";
import { createTool } from "@mastra/core/tools";
import { LibSQLStore } from "@mastra/libsql";
import { Memory } from "@mastra/memory";
import { z } from "zod";

export const API = process.env.WH_API ?? "https://witching-hour.onrender.com";
export const MODEL = process.env.WH_MODEL ?? "gemma4:e4b";
const OLLAMA = process.env.OLLAMA_URL ?? "http://127.0.0.1:11434/v1";

async function get(path: string): Promise<any> {
  const r = await fetch(API + path, { signal: AbortSignal.timeout(90_000) });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

const PHENOMENA: Record<string, string> = {
  "temperature|below": "a cold spot", "temperature|above": "a warmth with no source",
  "humidity|above": "breath on the glass", "humidity|below": "the air drying out",
  "energy|above": "the machines waking up", "energy|below": "the house going too quiet",
  "light|above": "lights coming on", "light|below": "lights going out",
};

export const hauntedNights = createTool({
  id: "haunted-nights",
  description: "Nights of the house ranked by their strongest apparition (how far a reading strayed from what the TabPFN spirit meter expected).",
  inputSchema: z.object({
    month: z.string().optional().describe("optional month filter, YYYY-MM"),
    topK: z.number().int().min(1).max(10).default(3),
  }),
  execute: async ({ month, topK }) => {
    const idx = await get("/api/nights");
    const rows = (idx.nights as any[]).filter((n) => !month || n.night.startsWith(month))
      .sort((a, b) => b.score - a.score).slice(0, topK ?? 3);
    return rows.map((n) => ({ night: n.night, weekday: n.weekday, sigma: n.score, apparitions: n.n_events, coldRooms: n.n_cold, headline: n.headline }));
  },
});

export const caseFile = createTool({
  id: "case-file",
  description: "Open one night's case file: its apparitions, cold-room checks, and what Luna (the Medium), Dr. Bigotes (the Skeptic) and Xochi (the Night Watch) wrote.",
  inputSchema: z.object({ date: z.string().describe("YYYY-MM-DD") }),
  execute: async ({ date }) => {
    const n = await get(`/api/nights/${date}`);
    const crew: Record<string, string> = { medium: "Luna", skeptic: "Dr. Bigotes", family: "Xochi" };
    return {
      night: n.night, weekday: n.weekday, sigma: n.score,
      apparitions: (n.events as any[]).map((e) => ({ id: e.id, room: e.room, what: PHENOMENA[`${e.kind}|${e.direction}`] ?? "a strange reading", from: e.start, to: e.end, observed: `${e.observed} ${e.unit}`, expected: `${e.expected} ${e.unit}`, sigma: e.sigma })),
      coldRooms: (n.checks ?? []).map((c: any) => ({ id: c.id, room: c.room, from: c.start, to: c.end, minutes: c.minutes, coldest: `${c.coldest} °C` })),
      stories: Object.fromEntries(Object.entries(n.stories ?? {}).map(([k, s]: [string, any]) => [crew[k] ?? k, { title: s.title, text: (s.sentences as any[]).map((x) => x.text).join(" ") }])),
    };
  },
});

export const tonight = createTool({
  id: "tonight",
  description: "Tonight's live weather for the house's town and TabPFN's forecast for each room, with the chance of dropping below 18 °C.",
  inputSchema: z.object({}),
  execute: async () => {
    const t = await get("/api/tonight");
    if (!t.rooms) return { error: "no forecast yet" };
    return { place: t.place, fetchedAt: t.fetched_at, rooms: (t.rooms as any[]).map((r) => ({ room: r.room, coldestExpected: `${r.expected} °C at ${r.coldest_time}`, chanceBelow18: r.p_below_18 })) };
  },
});

export const hunter = new Agent({
  id: "ghost-hunter",
  name: "Witching Hour ghost hunter",
  instructions: `You lead the Witching Hour ghost-hunting crew for one real house (sensor logs, midnight to 6 AM).
Use the tools for every fact. Never invent nights, rooms, times or numbers; copy them exactly from tool results.
When you quote Luna, Dr. Bigotes or Xochi, quote what the case file says they wrote.
Answer in 2 to 5 sentences, a little spooky in tone, always grounded.`,
  model: { id: `ollama/${MODEL}`, url: OLLAMA },
  tools: { hauntedNights, caseFile, tonight },
  memory: new Memory({ options: { lastMessages: 20 } }),
});

export const mastra = new Mastra({
  agents: { hunter },
  storage: new LibSQLStore({ id: "witching-hour-memory", url: "file:./mastra.db" }),
});
