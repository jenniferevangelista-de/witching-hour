"""Long-term memory in MongoDB Atlas: has this ghost visited before?

Every case file becomes a document with an embedding from an open embedding
model (nomic-embed-text through Ollama). Atlas Vector Search then answers the
question a ghost hunter always asks: which other nights looked like this one?
Every hunt the agent runs is stored too, so it can recall what it concluded.

Needs MONGODB_URI (an Atlas cluster; the free M0 tier is enough).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

DB = "witching_hour"
EMBED_MODEL = os.environ.get("WH_EMBED_MODEL", "nomic-embed-text")
INDEX = "case_vectors"


def embed(texts: list[str], host: str | None = None) -> list[list[float]]:
    import requests

    host = (host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
    r = requests.post(f"{host}/api/embed", json={"model": EMBED_MODEL, "input": texts}, timeout=300)
    r.raise_for_status()
    return r.json()["embeddings"]


def case_text(doc: dict) -> str:
    parts = [f"{doc['weekday']} {doc['night']}"] + doc.get("apparitions", []) + doc.get("cold_rooms", [])
    parts += [doc.get(k, "") for k in ("medium", "skeptic", "family")]
    return " | ".join(p for p in parts if p)


def client(uri: str | None = None):
    from pymongo import MongoClient

    return MongoClient(uri or os.environ["MONGODB_URI"], appname="witching-hour", serverSelectionTimeoutMS=20000)


def sync(data_dir: str | Path, uri: str | None = None) -> dict:
    """Upsert every case file with its embedding and make sure the vector index exists."""
    from pymongo import ReplaceOne
    from pymongo.operations import SearchIndexModel

    from .season import case_files

    docs = case_files(data_dir)
    vectors = embed([case_text(d) for d in docs])
    coll = client(uri)[DB]["case_files"]
    coll.bulk_write([ReplaceOne({"_id": d["night"]}, {**d, "_id": d["night"], "text": case_text(d), "embedding": v},
                                upsert=True) for d, v in zip(docs, vectors)])
    if INDEX not in [i["name"] for i in coll.list_search_indexes()]:
        coll.create_search_index(SearchIndexModel(name=INDEX, type="vectorSearch", definition={
            "fields": [{"type": "vector", "path": "embedding", "numDimensions": len(vectors[0]), "similarity": "cosine"}]}))
    return {"case_files": len(docs), "dimensions": len(vectors[0]), "index": INDEX}


def seen_before(night: str, k: int = 3, uri: str | None = None) -> list[dict]:
    """Nights whose case files are closest to this one (Atlas Vector Search)."""
    coll = client(uri)[DB]["case_files"]
    me = coll.find_one({"_id": night}, {"embedding": 1})
    if not me:
        return []
    pipeline = [
        {"$vectorSearch": {"index": INDEX, "path": "embedding", "queryVector": me["embedding"], "numCandidates": 100, "limit": k + 1}},
        {"$match": {"_id": {"$ne": night}}},
        {"$project": {"_id": 0, "night": 1, "weekday": 1, "apparitions": 1, "cold_rooms": 1, "score": {"$meta": "vectorSearchScore"}}},
    ]
    return list(coll.aggregate(pipeline))[:k]


def remember_hunt(run: dict, uri: str | None = None) -> None:
    client(uri)[DB]["hunts"].insert_one({**run, "at": datetime.now(timezone.utc)})


def past_hunts(limit: int = 5, uri: str | None = None) -> list[dict]:
    cur = client(uri)[DB]["hunts"].find({}, {"_id": 0, "question": 1, "answer": 1, "at": 1}).sort("at", -1).limit(limit)
    return [{**h, "at": h["at"].isoformat()} for h in cur]
