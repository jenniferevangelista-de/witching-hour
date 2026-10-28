# Witching Hour

**What if someone tried to warn you, and you never heard them?**

Witching Hour is a paranormal activity detector built for Halloween and Día de los Muertos. A crew of three tiny ghost hunters carries an open-source kit, and their terminal, **PARANORMAL.exe**, opens three kinds of cases:

| Case | What you bring | What the kit measures |
|---|---|---|
| 🏚️ **The House** | a house's sensor log (the demo uses a real house in Belgium, four months, every 10 minutes) | **TabPFN**, the spirit meter, learns what every room should feel like at every minute of the night and flags the readings that break the pattern |
| 🎞️ **The Unheard** | a recording of the night you almost went out and something made you stay | light, motion and sound, frame by frame, **inside the browser** (OpenCV does the same in Python); the moments that stand out become numbered evidence |
| 📹 **The Room** | your camera and microphone, live | the same measurements in real time, while you ask the board questions |

In every case the crew reads the evidence, and Luna can open a **Ouija board** for whatever the evidence cannot explain. Here is the rule that holds the whole thing together: **the evidence is real, the spirits are fiction.** A spirit may say anything spooky it wants, but every message other than YES, NO or GOODBYE must point at a real, measured moment. The crew is held even tighter: every sentence they write must cite a piece of evidence, and every number in it must match what it cites. Sentences that fail are dropped before anyone reads them. We call it **cite or vanish**.

| | Character | Job | Voice |
|---|---|---|---|
| <img src="witching_hour/static/characters/luna.svg" width="90" alt="Luna"> | **Luna, the Medium.** A tiny sugar-skull ghost with a marigold crown and a crystal ball. Whispery, dramatic, loves suspense. *"Shhh... the house is breathing."* | Turns the evidence into a first-person ghost story, and opens the board | ElevenLabs "Jessica" |
| <img src="witching_hour/static/characters/bigotes.svg" width="90" alt="Dr. Bigotes"> | **Dr. Bigotes, the Skeptic.** A black cat scientist with round glasses, a lab coat and a flashlight. Grumpy, kind underneath, never believes without data. *"Hmph. Probably the kettle."* | Explains what most likely happened, writes a note under every piece of evidence, and checks the official warnings in a real browser | ElevenLabs "George" |
| <img src="witching_hour/static/characters/xochi.svg" width="90" alt="Xochi"> | **Xochi, the Night Watch.** A xoloitzcuintli, the dog that guides souls on Día de los Muertos, with a lantern and a marigold collar. *"I kept watch. Here is what I saw."* | Carries messages to the living: a calm morning note for the family (with the WHO 18 °C check for cold rooms) and the case dossier | ElevenLabs "Matilda" |

**Live demo:** https://witching-hour.onrender.com

Built for the DEV Hacktoberfest Open-Source AI Challenge, Week 4: Ghost in the Machine.

**Built with PriorLabs-TabPFN.**

## The demo case: The Warning

`demo/make_warning.py` renders a short staged clip, made for this project and clearly labeled as staged: a woman takes her coat and walks to the door at 21:43. The hallway light flickers, a whisper, three knocks, and a shadow taller than her passes behind her. She stops, comes back, and hangs the coat up. The kit finds the flicker, the whisper, the knocks and the shadow as separate pieces of evidence with timestamps; Dr. Bigotes offers ordinary explanations for each; Luna asks for a Guardian, tells it what the woman remembers, and the board spells what it had been trying to say. The spirit is invented. The flicker at 7.0 s and the knocks at 9.0 s are not.

## Spirits

`witching_hour/spirits.py` turns a case's evidence into a fictional spirit and a séance:

- **Six archetypes**: Guardian, Lost One, Trickster, Watcher, Hostile Presence, Silent One. The model picks the one the evidence suggests and gives the spirit a name, a backstory and a goal, or the visitor can choose.
- **Answer contract**: every turn returns `response.message` (what the glass spells: A to Z, 0 to 9, at most three words), `response.spoken`, `response.animation_sequence` (the board positions the glass visits, computed in code, not by the model), `response.fictional: true` and `grounding.related_evidence_ids`. An answer that breaks a rule (no evidence cited, evidence that does not exist, more than three words) is sent back once with the reason, and then replaced by a plain template answer.
- **No harm**: words about hurting yourself or others are refused before they reach the board.
- **Your words**: in The Unheard you can tell Luna what happened that night ("I was about to go out, and something made me stay"). The spirit hears it as a memory, never as evidence, and can never cite it.
- **Memory**: the spirit remembers the last eight turns of the session. Sessions live in memory or, with `MONGODB_URI`, in MongoDB Atlas.
- **Who answers**: Gemma 4 E4B through Ollama when it is running. On the public demo, Gemma 3 27B through Backboard when a key is set, and scripted template answers otherwise. The page always says which one answered.
- **The Room**: when real motion is measured within a few seconds after the glass stops, the page goes dark and says *"That wasn't part of the game."* It is a narrative effect triggered by a real measurement, and the page says so.

## Why local

Night-time sensor logs say when someone goes to bed, when they get up, how long the bathroom light stays on, and when the house is empty. A recording of your hallway says even more. For someone who lives alone, that is the most private data they have. Everything here can run on a small machine at home: TabPFN on CPU, Gemma through Ollama, the web app on localhost. Recordings and the live camera are analyzed in the browser and never uploaded; only the list of measured moments goes to the board.

The public demo uses a public research dataset (a real house in Belgium, published under CC BY 4.0) and a staged clip, and replays results computed by the same pipeline.

## How it works

```
sensor log (CSV) ──► for each night, each sensor:
                       TabPFN reads the last 14 days (in-context, no training loop)
                       and predicts quantiles for every 10 minute slot, 00:00 to 06:00
                   ──► surprise = distance from the expected median, in "sigmas" of the predicted band
                   ──► events = runs of slots beyond 4 sigma (or one slot beyond 6)
                   ──► cold-room checks = living spaces below 18 °C for an hour or more (WHO)
                   ──► Gemma: Medium, Skeptic and Morning note, JSON with a citation per sentence
                   ──► validator: drop any sentence whose numbers are not in what it cites
```

- **Features** for each sensor: time of day, day of week, outdoor weather, and the same kind of sensor in the other rooms. Sensors in the same room are left out on purpose, so a shower (bathroom humidity and bathroom temperature rising together) shows up as two events instead of one explaining the other away.
- **Asymmetric band**: energy readings have a long upper tail and a floor at zero, so the upper and lower halves of the predicted band are scaled separately.
- **Tonight**: live hourly weather for the house's town (Google results through SerpApi) goes into a second TabPFN model trained on the house's past nights, which forecasts each room for tonight and the chance it drops below 18 °C.
- **The agent** (`witching-hour ask`) is a small JSON tool-calling loop. Gemma can rank the nights, open one night, ask TabPFN what it expected at a given minute, read tonight's forecast, and call a narrator. It never sees the raw log.
- **Planted ghosts benchmark** (`witching-hour evaluate`): smooth bumps of known size, time and length are added to real nights, then TabPFN, LightGBM quantile regression and a same-hour seasonal rule are scored on how often they notice them at a 5% false alarm rate, with paired bootstrap intervals.

## Run it

You need Python 3.10+ and [Ollama](https://ollama.com).

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu   # CPU is enough
pip install -e ".[tabpfn]"
ollama pull gemma4:e4b

witching-hour fetch                       # the public UCI house, about 12 MB
witching-hour scan --limit 7              # scan a week of nights with TabPFN
witching-hour narrate --top 3             # Medium, Skeptic and Morning note for the 3 strangest nights
witching-hour ask "Which night was the most haunted, and what probably happened?"
witching-hour serve                       # http://127.0.0.1:8000
```

TabPFN v2 weights download from Hugging Face on first use, no account needed. To use a newer TabPFN version, accept its license at [priorlabs.ai](https://priorlabs.ai) and set `WH_TABPFN_VERSION` (for example `v3.5`).

### Your own house (Home Assistant)

Export history from Home Assistant as CSV (columns `entity_id,state,last_changed`), then:

```bash
witching-hour scan --source ha --path history.csv --tz Europe/Brussels --out my_house
witching-hour narrate --data my_house --top 3
witching-hour serve --data my_house
```

Temperatures, humidity, power and lights (`on`/`off` becomes 1/0) are recognized from the entity names.

## Optional pieces

All of these are off unless you ask for them. Keys live in a local `.env` (never committed) or in CI secrets.

| Piece | Command | What it adds |
|---|---|---|
| Durable night watch (Temporal) | `pip install -e ".[durable]"`, `witching-hour worker`, `witching-hour watch --nights ...` | one workflow per night; a crashed worker or a stopped Ollama is retried, finished work is reused |
| Agent tracing (Sentry) | `pip install -e ".[tracing]"`, set `SENTRY_DSN` | gen_ai spans for the agent, each chat and each tool call, with tokens and latency; no prompts or readings are sent |
| Voice (ElevenLabs) | `witching-hour voice --top 8`, set `ELEVENLABS_API_KEY` | the Morning note and the Medium read aloud, verified sentences only |
| Tonight (SerpApi) | `witching-hour tonight --place "Your town"`, set `SERPAPI_KEY` | live hourly forecast plus a TabPFN forecast per room |
| Model bake-off (Backboard) | `witching-hour bakeoff --top 6`, set `BACKBOARD_API_KEY` | open-weight models compared on how many of their sentences pass the validator; also the public demo's spirit voice |
| Field trip (Browserbase) | `witching-hour fieldwork`, set `BROWSERBASE_API_KEY` | Dr. Bigotes opens the official weather warnings page in a real cloud browser (Playwright over CDP) and reads it |
| Mastra agent | `cd mastra && npm install && npm run hunt` | the same hunt as a TypeScript Mastra agent with memory, calling the demo API as tools |
| Fine-tuned apprentice (Tinker) | `python train/make_sft.py`, `python train/tinker_sft.py` | a LoRA on Qwen3-8B trained on verified stories, scored on later nights with the same validator |
| Family room (Auth0) | set `AUTH0_*` and `FAMILY_EMAILS` | on a home install, only signed-in family members may ask the agent or read the live notes |
| Memory (MongoDB Atlas) | `witching-hour atlas`, set `MONGODB_URI` | case files with open embeddings and Atlas Vector Search ("has this ghost visited before?"), plus spirit sessions |
| Archive (Tiger Data) | `witching-hour tiger`, set `TIGER_DATABASE_URL` | readings as a TimescaleDB hypertable and stories with pgvector, hybrid search with reciprocal rank fusion |
| Season report (Ultramarine) | `witching-hour season`, set `PAPERINSTRUMENTS_API_KEY` | reads every case file and reports patterns across the season, each finding citing its nights |

The durable run in `.github/workflows/durable.yml` kills the worker in the middle of a TabPFN scan and stops Ollama while the stories are being written. Every night still finished; the retries are in `docs/durable/temporal_summary.json`.

## Commands

| Command | What it does |
|---|---|
| `fetch` | downloads the UCI dataset |
| `scan` | TabPFN scan per night (`--backend lightgbm` or `seasonal` for the baselines, `--shard i/n` for parallel jobs) |
| `index` | rebuilds `index.json` from the scanned nights |
| `narrate` | Medium, Skeptic and Morning note with a local model (`--template` for a no-model fallback) |
| `ask` | the investigator agent |
| `tonight` | live forecast and TabPFN room forecast |
| `evaluate` | planted ghosts benchmark |
| `ouija` | Luna's board message for each of the most haunted nights of the house |
| `footage` | The Unheard in Python: evidence from a recording with OpenCV and ffmpeg |
| `seance` | summons a spirit from a case's evidence and records a séance |
| `voice`, `bakeoff`, `fieldwork`, `season`, `atlas`, `tiger`, `worker`, `watch` | the optional pieces above |
| `serve` | the web app |

The full pipeline runs in GitHub Actions: `haunt.yml` (twelve parallel TabPFN shards), `narrate.yml` (Gemma on eight runners), `benchmark.yml`, `durable.yml`, `tonight.yml`, `ask.yml`, `mastra.yml`, `tinker.yml`, `vault.yml`, `warning.yml` (renders The Warning, investigates it and records the séance), `ouija.yml`, `screens.yml`, and `tests.yml` on every push.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

The tests use a synthetic house, the seasonal baseline and scripted models, so they run without TabPFN, Ollama or any key.

## Credits

- [TabPFN](https://github.com/PriorLabs/TabPFN) by Prior Labs (Prior Labs License 1.1, see `NOTICE.md` and `licenses/`).
- [Gemma 4](https://huggingface.co/google/gemma-4-E4B-it) by Google (Apache 2.0), served by [Ollama](https://ollama.com).
- The Warning is a staged clip rendered by `demo/make_warning.py` for this project. No real person or event.
- Data: [Appliances energy prediction](https://archive.ics.uci.edu/dataset/374/appliances+energy+prediction), Candanedo, Feldheim & Deramaix (2017), CC BY 4.0.
- WHO Housing and Health Guidelines (2018): https://www.who.int/publications/i/item/9789241550376

Code: MIT.
