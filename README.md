# Witching Hour

**What happened in the house at 3 AM?**

Witching Hour reads a home's night-time sensor logs. An open tabular foundation model (TabPFN) learns from the previous two weeks what every room should read at every moment of the night. When a room drifts outside that range, it becomes an event. Then an open-weight language model (Gemma 4, running locally through Ollama) tells you about the night twice:

- **The Medium** turns the events into a short Halloween ghost story.
- **The Skeptic** reads the same events and gives the boring explanation.

Neither narrator gets a free pass. Every sentence must cite an event, and every number in a sentence must match the cited event. Sentences that fail are dropped and the model gets one retry with feedback. The page shows how many sentences survived.

Built for the DEV Hacktoberfest Open-Source AI Challenge, Week 4: Ghost in the Machine.

**Built with PriorLabs-TabPFN.**

## Why local

Night-time sensor logs say when a family sleeps, when someone gets up, and when the house is empty. That data should not leave the house. Everything here runs on your own machine: TabPFN on CPU, Gemma through Ollama, the web app on localhost. No API keys, no account, no cost per question.

The public demo uses a public dataset (a real house in Belgium, published by its researchers under CC BY 4.0) and replays results computed by the same pipeline. It never runs a model on a visitor's question.

## How it works

```
sensor log (CSV) ──► for each night, each sensor:
                       TabPFN reads the last 14 days (in-context, no training loop)
                       and predicts quantiles for every 10 minute slot, 00:00 to 06:00
                   ──► surprise = distance from the expected median, in "sigmas" of the predicted band
                   ──► events = runs of slots beyond 4 sigma (or one slot beyond 6)
                   ──► Gemma: Medium story + Skeptic story, JSON with a citation per sentence
                   ──► validator: drop any sentence whose numbers are not in the cited events
```

- **Features** for each sensor: time of day, day of week, outdoor weather, and the same kind of sensor in the other rooms. Sensors in the same room are left out on purpose, so a shower (bathroom humidity and bathroom temperature rising together) shows up as two events instead of one explaining the other away.
- **Asymmetric band**: energy readings have a long upper tail and a floor at zero, so the upper and lower halves of the predicted band are scaled separately.
- **The agent** (`witching-hour ask`) is a small JSON tool-calling loop. Gemma can rank the nights, open one night's events, ask TabPFN what it expected at a given minute, and call a narrator. It never sees the raw log.
- **Planted ghosts benchmark** (`witching-hour evaluate`): smooth bumps of known size, time and length are added to real nights, then each model (TabPFN, LightGBM quantile regression, and a same-hour seasonal rule) is scored on how often it notices them at a 5% false alarm rate.

## Run it

You need Python 3.10+ and [Ollama](https://ollama.com).

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu   # CPU is enough
pip install -e ".[tabpfn]"
ollama pull gemma4:e4b

witching-hour fetch                       # the public UCI house, about 12 MB
witching-hour scan --limit 7              # scan a week of nights with TabPFN
witching-hour narrate --top 3             # Medium and Skeptic stories for the 3 strangest nights
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

## Commands

| Command | What it does |
|---|---|
| `fetch` | downloads the UCI dataset |
| `scan` | TabPFN scan per night (`--backend lightgbm` or `seasonal` for the baselines, `--shard i/n` for parallel jobs) |
| `index` | rebuilds `index.json` from the scanned nights |
| `narrate` | Medium and Skeptic stories with a local model (`--template` for a no-model fallback) |
| `ask` | the investigator agent |
| `evaluate` | planted ghosts benchmark |
| `serve` | the web app |

The full pipeline also runs in GitHub Actions (`.github/workflows/haunt.yml`): six parallel TabPFN shards, the benchmark, then Ollama with Gemma on the runner for the stories and the agent runs.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

The tests use a synthetic house and the seasonal baseline, so they run without TabPFN or Ollama.

## Credits

- [TabPFN](https://github.com/PriorLabs/TabPFN) by Prior Labs (Prior Labs License 1.1, see `NOTICE.md` and `licenses/`).
- [Gemma 4](https://huggingface.co/google/gemma-4-E4B-it) by Google (Apache 2.0), served by [Ollama](https://ollama.com).
- Data: [Appliances energy prediction](https://archive.ics.uci.edu/dataset/374/appliances+energy+prediction), Candanedo, Feldheim & Deramaix (2017), CC BY 4.0.

Code: MIT.
