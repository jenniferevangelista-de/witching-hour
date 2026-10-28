"""Tiger Data (Postgres + TimescaleDB + pgvector): the house's readings and the crew's stories.

- readings: every 10 minute reading as a hypertable, so nightly summaries are a
  time_bucket query (the coldest hour of every room, every night).
- stories: every verified story with a full-text index and an embedding from an
  open model, so the agent can run hybrid search (keywords + meaning, fused with
  reciprocal rank fusion): "the night the bathroom fogged up".

Needs TIGER_DATABASE_URL (a Tiger Cloud service; the free tier is enough).
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS readings (time timestamptz NOT NULL, sensor text NOT NULL, value double precision);
SELECT create_hypertable('readings', 'time', if_not_exists => TRUE);
CREATE TABLE IF NOT EXISTS stories (
  id text PRIMARY KEY, night date, mode text, title text, body text,
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(body, ''))) STORED,
  embedding vector({dim}));
CREATE INDEX IF NOT EXISTS stories_tsv ON stories USING gin (tsv);
"""

COLDEST_SQL = """
SELECT time_bucket('1 day', time)::date AS night, sensor, min(value) AS coldest
FROM readings WHERE sensor = %s AND extract(hour from time) < 6
GROUP BY 1, 2 ORDER BY coldest ASC LIMIT %s
"""

HYBRID_SQL = """
WITH kw AS (
  SELECT id, row_number() OVER (ORDER BY ts_rank(tsv, plainto_tsquery('english', %(q)s)) DESC) AS r
  FROM stories WHERE tsv @@ plainto_tsquery('english', %(q)s) LIMIT 20),
vec AS (
  SELECT id, row_number() OVER (ORDER BY embedding <=> %(v)s::vector) AS r FROM stories ORDER BY embedding <=> %(v)s::vector LIMIT 20)
SELECT s.id, s.night, s.mode, s.title, left(s.body, 220) AS excerpt,
       coalesce(1.0 / (60 + kw.r), 0) + coalesce(1.0 / (60 + vec.r), 0) AS score
FROM stories s LEFT JOIN kw ON kw.id = s.id LEFT JOIN vec ON vec.id = s.id
WHERE kw.id IS NOT NULL OR vec.id IS NOT NULL ORDER BY score DESC LIMIT %(k)s
"""


def rrf(rank_lists: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal rank fusion, the same formula as HYBRID_SQL (kept in Python for tests)."""
    scores: dict[str, float] = {}
    for ranks in rank_lists:
        for i, item in enumerate(ranks, 1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + i)
    return sorted(scores.items(), key=lambda kv: -kv[1])


def connect(url: str | None = None):
    import psycopg

    return psycopg.connect(url or os.environ["TIGER_DATABASE_URL"], autocommit=True)


def load(house, data_dir: str | Path, url: str | None = None) -> dict:
    """Readings into the hypertable (COPY), verified stories with embeddings into `stories`."""
    from .atlas_memory import embed

    data_dir = Path(data_dir)
    stories = []
    for p in sorted((data_dir / "stories").glob("*.json")):
        st = json.loads(p.read_text(encoding="utf-8"))
        if st["sentences"] and any(s["cites"] for s in st["sentences"]):
            stories.append((f"{st['night']}.{st['mode']}", st["night"], st["mode"], st["title"],
                            " ".join(s["text"] for s in st["sentences"])))
    vectors = embed([f"{s[3]}. {s[4]}" for s in stories])
    with connect(url) as conn, conn.cursor() as cur:
        cur.execute(SCHEMA.format(dim=len(vectors[0])))
        cur.execute("TRUNCATE readings")
        long = house.df[house.sensor_ids].stack().reset_index()
        buf = io.StringIO()
        long.to_csv(buf, header=False, index=False)
        buf.seek(0)
        with cur.copy("COPY readings (time, sensor, value) FROM STDIN WITH (FORMAT csv)") as cp:
            cp.write(buf.read())
        for s, v in zip(stories, vectors):
            cur.execute("INSERT INTO stories (id, night, mode, title, body, embedding) VALUES (%s,%s,%s,%s,%s,%s::vector) "
                        "ON CONFLICT (id) DO UPDATE SET title = excluded.title, body = excluded.body, embedding = excluded.embedding",
                        (*s, str(v)))
        cur.execute("SELECT count(*) FROM readings")
        n = cur.fetchone()[0]
    return {"readings": n, "stories": len(stories)}


def coldest_nights(sensor: str, limit: int = 5, url: str | None = None) -> list[dict]:
    with connect(url) as conn, conn.cursor() as cur:
        cur.execute(COLDEST_SQL, (sensor, limit))
        return [{"night": str(r[0]), "sensor": r[1], "coldest": round(r[2], 2)} for r in cur.fetchall()]


def search_stories(query: str, k: int = 5, url: str | None = None) -> list[dict]:
    from .atlas_memory import embed

    v = embed([query])[0]
    with connect(url) as conn, conn.cursor() as cur:
        cur.execute(HYBRID_SQL, {"q": query, "v": str(v), "k": k})
        cols = [c.name for c in cur.description]
        return [{**dict(zip(cols, r)), "night": str(r[1]), "score": round(float(r[5]), 4)} for r in cur.fetchall()]
