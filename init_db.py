"""
CienciaHoy — init_db.py
Crea data.db con el esquema correcto y sin datos de ejemplo.
USO: python init_db.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data.db"

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS papers (
    id          TEXT PRIMARY KEY,
    title       TEXT,
    abstract    TEXT,
    authors     TEXT,
    category    TEXT,
    arxiv_url   TEXT,
    published   TEXT,
    source      TEXT DEFAULT 'arxiv',
    score       REAL DEFAULT 0,
    processed   INTEGER DEFAULT 0,
    fetched_at  TEXT
);

CREATE TABLE IF NOT EXISTS articles (
    id            TEXT PRIMARY KEY,
    paper_id      TEXT REFERENCES papers(id),
    headline      TEXT,
    summary       TEXT,
    body          TEXT,
    category      TEXT,
    tags          TEXT,
    image_prompt  TEXT,
    published_at  TEXT,
    status        TEXT DEFAULT 'draft'
);

CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at DESC);
"""

def init_db():
    print(f"Creando base de datos en: {DB_PATH}")
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    con.commit()
    con.close()
    print("✅ data.db creada y lista.")
    print("Siguiente paso: python pipeline.py")

if __name__ == "__main__":
    init_db()
