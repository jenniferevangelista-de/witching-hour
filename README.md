# Witching Hour

**A paranormal activity detector for real houses, built for Halloween and Día de los Muertos.**

Witching Hour is a ghost-hunting kit. Its **spirit meter** is TabPFN, an open tabular foundation model: it reads a house's own previous two weeks of sensor logs and learns what every room should feel like at every moment of the night. When a reading breaks that pattern between midnight and 6 AM, the needle jumps and the crew takes the case. The crew are three little characters played by Gemma 4, an open-weight model running locally through Ollama:

| | Character | Job | Voice |
|---|---|---|---|
| <img src="witching_hour/static/characters/luna.svg" width="90" alt="Luna"> | **Luna, the Medium.** A tiny sugar-skull ghost with a marigold crown and a crystal ball. Whispery, dramatic, loves suspense. *"Shhh... the house is breathing."* | Turns the apparitions into a spooky first-person ghost story | ElevenLabs "Jessica" |
| <img src="witching_hour/static/characters/bigotes.svg" width="90" alt="Dr. Bigotes"> | **Dr. Bigotes, the Skeptic.** A black cat scientist with round glasses, a lab coat and a flashlight. Grumpy, kind underneath, never believes without data. *"Hmph. Probably the kettle."* | Explains what most likely happened, and checks the official warnings in a real browser | ElevenLabs "George" |
| <img src="witching_hour/static/characters/xochi.svg" width="90" alt="Xochi"> | **Xochi, the Night Watch.** A xoloitzcuintli, the dog that guides souls on Día de los Muertos, with a lantern and a marigold collar. *"I kept watch. Here is what I saw."* | Writes a calm morning note for the family of someone who lives in the house alone, with the WHO 18 °C check for cold rooms | ElevenLabs "Matilda" |

None of them gets a free pass: **cite or vanish**. Every sentence must cite an apparition (or a cold-room check), and every number in it must match what it cites. Sentences that fail are dropped before anyone reads them.

**Live demo:** https://witching-hour.onrender.com

Built for the DEV Hacktoberfest Open-Source AI Challenge, Week 4: Ghost in the Machine.

**Built with PriorLabs-TabPFN.**

## Why local

Night-time sensor logs say when someone goes to bed, when they get up, how long the bathroom light stays on, and when the house is empty. For someone who lives alone, that is the most private data they have. Everything here can run on a small machine at home: TabPFN on CPU, Gemma through Ollama, the web app on localhost. No API keys, no account, no cost per question.

The public demo uses a public research dataset (a real house in Belgium, published under CC BY 4.0) and replays results computed by the same pipeline. It never runs a model on a visitor's question.

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
| Model bake-off (Backboard) | `witching-hour bakeoff --top 6`, set `BACKBOARD_API_KEY` | open-weight models compared on how many of their sentences pass the validator |

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
| `voice`, `bakeoff`, `worker`, `watch` | the optional pieces above |
| `serve` | the web app |

The full pipeline runs in GitHub Actions: `haunt.yml` (twelve parallel TabPFN shards), `narrate.yml` (Gemma on four runners, then the agent), `benchmark.yml`, `durable.yml`, `screens.yml`, and `tests.yml` on every push.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

The tests use a synthetic house, the seasonal baseline and scripted models, so they run without TabPFN, Ollama or any key.

## Credits

- [TabPFN](https://github.com/PriorLabs/TabPFN) by Prior Labs (Prior Labs License 1.1, see `NOTICE.md` and `licenses/`).
- [Gemma 4](https://huggingface.co/google/gemma-4-E4B-it) by Google (Apache 2.0), served by [Ollama](https://ollama.com).
- Data: [Appliances energy prediction](https://archive.ics.uci.edu/dataset/374/appliances+energy+prediction), Candanedo, Feldheim & Deramaix (2017), CC BY 4.0.
- WHO Housing and Health Guidelines (2018): https://www.who.int/publications/i/item/9789241550376

Code: MIT.
