"""
Science Newsroom — pipeline.py
==============================================
Fuentes: arXiv · Semantic Scholar · Europe PMC · CORE · NASA ADS
Todas gratuitas, sin API key obligatoria.

REQUISITOS:
    pip install requests schedule
    ollama pull mistral
"""

import json, time, sqlite3, hashlib, logging, requests, random
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────
# Para pruebas rápidas: PAPERS_PER_SOURCE=5, MAX_ARTICLES_PER_DAY=3
# Para producción:      PAPERS_PER_SOURCE=15, MAX_ARTICLES_PER_DAY=10

DB_PATH = Path(__file__).parent / "data.db"

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral"

PAPERS_PER_SOURCE    = 5    # papers a buscar por fuente/categoría
MIN_RELEVANCE_SCORE  = 0.65
MAX_ARTICLES_PER_DAY = 5    # techo de noticias diarias

ARXIV_CATEGORIES = [
    "cs.AI", "cs.LG", "physics.app-ph",
    "cond-mat.mtrl-sci", "eess.SY", "q-bio.NC",
]

SCIENCE_QUERIES = [
    "artificial intelligence machine learning",
    "materials science nanotechnology",
    "neuroscience brain",
    "quantum computing physics",
    "climate energy sustainability",
    "biotechnology medicine",
]

ARXIV_DELAY = 4   # segundos entre requests a arXiv (evita 429)

# ── LOGGING ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("newsroom")

# ── OLLAMA ────────────────────────────────────────────────────────────────────

def check_ollama() -> bool:
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        log.info("Ollama OK. Modelos: %s", models)
        match = any(OLLAMA_MODEL in m for m in models)
        if not match:
            log.warning("Modelo '%s' no encontrado. Ejecuta: ollama pull %s", OLLAMA_MODEL, OLLAMA_MODEL)
        return match
    except Exception as e:
        log.error("Ollama no responde: %s", e)
        return False

def ask_ollama(prompt: str, timeout: int = 300) -> str:
    for attempt in range(2):
        try:
            r = requests.post(
                OLLAMA_URL,
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                timeout=timeout,
            )
            resp = r.json().get("response", "").strip()
            if resp:
                return resp
        except requests.exceptions.Timeout:
            log.warning("Ollama timeout (intento %d/2)", attempt + 1)
        except Exception as e:
            log.warning("Ollama error (intento %d/2): %s", attempt + 1, e)
        time.sleep(4)
    return ""

def clean_json(text: str) -> str:
    text = text.strip()
    if "```" in text:
        p = text.split("```")[1].strip()
        text = p[4:].strip() if p.lower().startswith("json") else p
    s, e = text.find("{"), text.rfind("}")
    return text[s:e+1].strip() if s != -1 and e > s else text

# ── DB ────────────────────────────────────────────────────────────────────────

def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
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
            paper_id      TEXT,
            headline      TEXT,
            summary       TEXT,
            body          TEXT,
            category      TEXT,
            tags          TEXT,
            image_prompt  TEXT,
            published_at  TEXT,
            status        TEXT
        );
    """)
    # Migración: añadir columna source si no existe (para DBs antiguas)
    try:
        con.execute("ALTER TABLE papers ADD COLUMN source TEXT DEFAULT 'arxiv'")
        con.commit()
        log.info("Columna 'source' añadida a papers")
    except sqlite3.OperationalError:
        pass  # ya existe
    con.commit()
    con.close()
    log.info("DB lista")

def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def save_papers(papers: list, source: str = "arxiv") -> int:
    con = get_db()
    n = 0
    for p in papers:
        p.setdefault("source", source)
        try:
            cur = con.execute(
                "INSERT OR IGNORE INTO papers "
                "(id,title,abstract,authors,category,arxiv_url,published,source,fetched_at) "
                "VALUES (:id,:title,:abstract,:authors,:category,:arxiv_url,:published,:source,:fetched_at)",
                p,
            )
            n += cur.rowcount
        except Exception as e:
            log.warning("  save_papers error: %s", e)
    con.commit()
    con.close()
    log.info("  -> %d nuevos de %s", n, source)
    return n

# ── FUENTE 1: arXiv ──────────────────────────────────────────────────────────

def scout_arxiv(category: str) -> list:
    url = "https://export.arxiv.org/api/query"
    params = {
        "search_query": "cat:" + category,
        "sortBy":       "submittedDate",
        "sortOrder":    "descending",
        "max_results":  PAPERS_PER_SOURCE,
    }
    log.info("arXiv: %s", category)
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=60)
            r.raise_for_status()
            break
        except Exception as e:
            log.warning("  arXiv error (intento %d/3): %s", attempt + 1, e)
            if attempt == 2:
                log.error("  arXiv fallido para %s, saltando", category)
                return []
            time.sleep(10 * (attempt + 1))  # backoff generoso

    ns   = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(r.text)
    papers = []
    for entry in root.findall("atom:entry", ns):
        raw_id = entry.findtext("atom:id", "", ns)
        pid    = raw_id.split("/abs/")[-1].replace("/", "_")
        title  = entry.findtext("atom:title",   "", ns).strip()
        abstr  = entry.findtext("atom:summary", "", ns).strip()[:2000]
        if not title or not abstr:
            continue
        papers.append({
            "id":         "arxiv_" + pid,
            "title":      title,
            "abstract":   abstr,
            "authors":    json.dumps([]),
            "category":   category,
            "arxiv_url":  "https://arxiv.org/abs/" + pid.replace("_", "/"),
            "published":  entry.findtext("atom:published", "", ns),
            "source":     "arxiv",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    log.info("  -> %d papers", len(papers))
    return papers

# ── FUENTE 2: Semantic Scholar ────────────────────────────────────────────────

def scout_semantic_scholar(query: str) -> list:
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query":  query,
        "limit":  PAPERS_PER_SOURCE,
        "fields": "paperId,title,abstract,authors,year,externalIds,publicationDate",
        "sort":   "relevance",
    }
    log.info("Semantic Scholar: %s", query[:50])
    try:
        r = requests.get(url, params=params, timeout=30,
                         headers={"User-Agent": "ScienceNewsroom/1.0"})
        r.raise_for_status()
        data = r.json().get("data", [])
    except Exception as e:
        log.warning("  Semantic Scholar error: %s", e)
        return []

    papers = []
    for p in data:
        if not p.get("abstract"):
            continue
        pid      = "ss_" + p["paperId"]
        arxiv_id = (p.get("externalIds") or {}).get("ArXiv", "")
        url_p    = ("https://arxiv.org/abs/" + arxiv_id) if arxiv_id else \
                   ("https://www.semanticscholar.org/paper/" + p["paperId"])
        papers.append({
            "id":         pid,
            "title":      (p.get("title") or "").strip(),
            "abstract":   (p.get("abstract") or "").strip()[:2000],
            "authors":    json.dumps([a.get("name", "") for a in (p.get("authors") or [])[:5]]),
            "category":   "science.general",
            "arxiv_url":  url_p,
            "published":  p.get("publicationDate") or str(p.get("year", "")),
            "source":     "semantic_scholar",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    log.info("  -> %d papers", len(papers))
    time.sleep(2)
    return papers

# ── FUENTE 3: Europe PMC ─────────────────────────────────────────────────────

def scout_europe_pmc(query: str) -> list:
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query":      query + " OPEN_ACCESS:Y",
        "resultType": "core",
        "pageSize":   PAPERS_PER_SOURCE,
        "format":     "json",
        "sort":       "FIRST_PDATE desc",
    }
    log.info("Europe PMC: %s", query[:50])
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        results = r.json().get("resultList", {}).get("result", [])
    except Exception as e:
        log.warning("  Europe PMC error: %s", e)
        return []

    papers = []
    for p in results:
        abstract = p.get("abstractText", "") or p.get("abstract", "")
        if not abstract:
            continue
        pid   = "epmc_" + str(p.get("id", p.get("pmid", "")))
        doi   = p.get("doi", "")
        url_p = ("https://doi.org/" + doi) if doi else \
                ("https://europepmc.org/article/" + str(p.get("source","")) + "/" + str(p.get("id","")))
        papers.append({
            "id":         pid,
            "title":      (p.get("title") or "").strip().rstrip("."),
            "abstract":   abstract.strip()[:2000],
            "authors":    json.dumps([a.get("fullName","") for a in (p.get("authorList",{}).get("author") or [])[:5]]),
            "category":   "science.life",
            "arxiv_url":  url_p,
            "published":  p.get("firstPublicationDate", ""),
            "source":     "europe_pmc",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    log.info("  -> %d papers", len(papers))
    return papers

# ── FUENTE 4: CORE ───────────────────────────────────────────────────────────

def scout_core(query: str) -> list:
    url    = "https://api.core.ac.uk/v3/search/works"
    params = {"q": query, "limit": PAPERS_PER_SOURCE, "sort": "recency"}
    log.info("CORE: %s", query[:50])
    try:
        r = requests.get(url, params=params, timeout=30,
                         headers={"User-Agent": "ScienceNewsroom/1.0"})
        r.raise_for_status()
        results = r.json().get("results", [])
    except Exception as e:
        log.warning("  CORE error: %s", e)
        return []

    papers = []
    for p in results:
        abstract = p.get("abstract", "")
        if not abstract or len(abstract) < 80:
            continue
        pid    = "core_" + str(p.get("id", ""))
        urls   = p.get("sourceFulltextUrls") or []
        url_p  = p.get("downloadUrl") or (urls[0] if urls else "")
        papers.append({
            "id":         pid,
            "title":      (p.get("title") or "").strip(),
            "abstract":   abstract.strip()[:2000],
            "authors":    json.dumps([a.get("name","") for a in (p.get("authors") or [])[:5]]),
            "category":   "science.general",
            "arxiv_url":  url_p,
            "published":  str(p.get("publishedDate") or p.get("yearPublished",""))[:10],
            "source":     "core",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    log.info("  -> %d papers", len(papers))
    return papers

# ── FUENTE 5: NASA ADS ───────────────────────────────────────────────────────

def scout_nasa_ads(query: str = "exoplanets machine learning") -> list:
    url    = "https://api.adsabs.harvard.edu/v1/search/query"
    params = {
        "q":    query,
        "fl":   "bibcode,title,abstract,author,pubdate,identifier",
        "rows": PAPERS_PER_SOURCE,
        "sort": "date desc",
    }
    log.info("NASA ADS: %s", query[:50])
    try:
        r = requests.get(url, params=params, timeout=30,
                         headers={"Authorization": "Bearer anonymous"})
        if r.status_code == 401:
            log.info("  NASA ADS requiere token, saltando")
            return []
        r.raise_for_status()
        results = r.json().get("response", {}).get("docs", [])
    except Exception as e:
        log.warning("  NASA ADS error: %s", e)
        return []

    papers = []
    for p in results:
        abstract = p.get("abstract", "")
        if not abstract:
            continue
        bibcode  = p.get("bibcode", "")
        ids      = [x for x in (p.get("identifier") or []) if "arXiv" in str(x)]
        url_p    = ("https://arxiv.org/abs/" + ids[0].replace("arXiv:", "")) if ids else \
                   ("https://ui.adsabs.harvard.edu/abs/" + bibcode)
        title    = p.get("title", [""])[0] if isinstance(p.get("title"), list) else p.get("title", "")
        papers.append({
            "id":         "ads_" + bibcode.replace("/", "_"),
            "title":      title.strip(),
            "abstract":   abstract.strip()[:2000],
            "authors":    json.dumps((p.get("author") or [])[:5]),
            "category":   "science.astronomy",
            "arxiv_url":  url_p,
            "published":  (p.get("pubdate") or "")[:10],
            "source":     "nasa_ads",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    log.info("  -> %d papers", len(papers))
    return papers

# ── FILTER ────────────────────────────────────────────────────────────────────

FILTER_PROMPT = """\
Devuelve SOLO este JSON sin texto extra ni markdown.
"score" es UN NUMERO entre 0.0 y 1.0 (NO un objeto):

{
  "score": 0.75,
  "reason": "motivo breve",
  "tags": ["tag1", "tag2"]
}

Evalua relevancia cientifica e interes periodistico.

Titulo: TITULO_PAPER
Categoria: CATEGORIA_PAPER
Abstract: ABSTRACT_PAPER
"""

def filter_papers() -> list:
    con     = get_db()
    pending = [dict(r) for r in con.execute("SELECT * FROM papers WHERE processed=0").fetchall()]
    con.close()
    log.info("Filter: %d papers pendientes", len(pending))

    scored = []
    for p in pending:
        prompt = (FILTER_PROMPT
                  .replace("TITULO_PAPER",    p.get("title", ""))
                  .replace("CATEGORIA_PAPER", p.get("category", ""))
                  .replace("ABSTRACT_PAPER",  p.get("abstract", "")))

        raw = ask_ollama(prompt, timeout=300)

        if not raw:
            log.warning("  sin respuesta para: %s", p["title"][:60])
            con = get_db()
            con.execute("UPDATE papers SET score=0,processed=1 WHERE id=?", (p["id"],))
            con.commit(); con.close()
            continue

        log.info("  FILTER (%s): %s", p["id"][:18], raw[:80])

        try:
            result    = json.loads(clean_json(raw))
            raw_score = result.get("score", 0)
            if isinstance(raw_score, dict):
                vals  = [v for v in raw_score.values() if isinstance(v, (int, float))]
                score = float(sum(vals) / len(vals)) if vals else 0.0
            else:
                score = float(raw_score)
        except Exception:
            result = {}
            score  = 0.0

        con = get_db()
        con.execute("UPDATE papers SET score=?,processed=1 WHERE id=?", (score, p["id"]))
        con.commit(); con.close()

        if score >= MIN_RELEVANCE_SCORE:
            p["score"] = score
            p["tags"]  = result.get("tags", [])
            scored.append(p)
            log.info("  OK (%.2f): %s", score, p["title"][:60])
        else:
            log.info("  skip (%.2f): %s", score, p["title"][:60])

        time.sleep(1)

    log.info("Filter: %d relevantes", len(scored))
    return scored

# ── WRITER ────────────────────────────────────────────────────────────────────

WRITER_PROMPT = """\
Eres periodista cientifico. Convierte este paper en noticia en espanol.
Devuelve SOLO este JSON sin texto extra ni markdown:

{
  "headline": "Titular atractivo maximo 12 palabras",
  "summary": "Una frase resumen para portada",
  "body": "Noticia 120-160 palabras: que se descubrio, como, por que importa, limitaciones",
  "image_prompt": "English photorealistic image description max 10 words"
}

TITULO: TITULO_PAPER
ABSTRACT: ABSTRACT_PAPER
"""

def write_articles(papers: list) -> list:
    articles = []
    for p in papers:
        aid    = hashlib.sha1(p["id"].encode()).hexdigest()[:12]
        prompt = (WRITER_PROMPT
                  .replace("TITULO_PAPER",   p["title"])
                  .replace("ABSTRACT_PAPER", p["abstract"]))
        raw = ask_ollama(prompt, timeout=600)

        if not raw:
            log.warning("  Writer sin respuesta: %s", p["title"][:60])
            continue

        log.info("  WRITER (%s): %s", p["id"][:16], raw[:80])

        try:
            result = json.loads(clean_json(raw))
        except Exception as e:
            log.warning("  Writer JSON invalido: %s", e)
            continue

        if not result.get("headline") or not result.get("body"):
            log.warning("  Writer incompleto: %s", p["title"][:60])
            continue

        articles.append({
            "id":           aid,
            "paper_id":     p["id"],
            "headline":     result.get("headline", p["title"]),
            "summary":      result.get("summary", ""),
            "body":         result.get("body", ""),
            "category":     p["category"],
            "tags":         json.dumps(p.get("tags", [])),
            "image_prompt": result.get("image_prompt", ""),
            "published_at": datetime.now(timezone.utc).isoformat(),
            "status":       "published",
        })
        log.info("  articulo: %s", result.get("headline", "")[:60])
        time.sleep(1)

    log.info("Writer: %d articulos", len(articles))
    return articles

# ── VALIDATOR ─────────────────────────────────────────────────────────────────

VALIDATOR_PROMPT = """\
Revisa esta noticia y devuelve SOLO este JSON sin texto extra:

{
  "approved": true,
  "issues": []
}

Si el cuerpo contradice gravemente el abstract devuelve approved=false.

Abstract: ABSTRACT_PAPER
Titular: HEADLINE_PAPER
Cuerpo: BODY_PAPER
"""

def validate_articles(articles: list, papers_map: dict) -> list:
    validated = []
    for a in articles:
        paper  = papers_map.get(a["paper_id"], {})
        prompt = (VALIDATOR_PROMPT
                  .replace("ABSTRACT_PAPER", paper.get("abstract", ""))
                  .replace("HEADLINE_PAPER", a["headline"])
                  .replace("BODY_PAPER",     a["body"]))
        raw = ask_ollama(prompt, timeout=300)
        try:
            result = json.loads(clean_json(raw)) if raw else {"approved": True}
        except Exception:
            result = {"approved": True}

        if result.get("approved", True):
            validated.append(a)
        else:
            log.info("  Rechazado: %s", a["headline"][:60])

    log.info("Validator: %d/%d aprobados", len(validated), len(articles))
    return validated

# ── EDITOR ────────────────────────────────────────────────────────────────────

def editor_publish(articles: list):
    con = get_db()
    n   = 0
    for a in articles[:MAX_ARTICLES_PER_DAY]:
        con.execute(
            "INSERT OR REPLACE INTO articles "
            "(id,paper_id,headline,summary,body,category,tags,image_prompt,published_at,status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (a["id"], a["paper_id"], a["headline"], a["summary"],
             a["body"], a["category"], a["tags"],
             a["image_prompt"], a["published_at"], "published"),
        )
        n += 1
    con.commit(); con.close()
    log.info("Editor: %d articulos publicados", n)

# ── PIPELINE ──────────────────────────────────────────────────────────────────

def run_pipeline():
    log.info("PIPELINE START")

    if not check_ollama():
        log.error("Abortando: Ollama no disponible.")
        return

    init_db()  # también hace la migración de columna source automáticamente

    # ── Scout arXiv ──────────────────────────────────────────────────────────
    log.info("── Scout arXiv ──────────────────────")
    for cat in ARXIV_CATEGORIES:
        papers = scout_arxiv(cat)
        save_papers(papers, "arxiv")
        time.sleep(ARXIV_DELAY)  # respetar rate limit de arXiv

    # ── Scout Semantic Scholar ────────────────────────────────────────────────
    log.info("── Scout Semantic Scholar ───────────")
    for q in random.sample(SCIENCE_QUERIES, min(3, len(SCIENCE_QUERIES))):
        papers = scout_semantic_scholar(q)
        save_papers(papers, "semantic_scholar")
        time.sleep(2)

    # ── Scout Europe PMC ──────────────────────────────────────────────────────
    log.info("── Scout Europe PMC ─────────────────")
    for q in random.sample(SCIENCE_QUERIES, min(2, len(SCIENCE_QUERIES))):
        papers = scout_europe_pmc(q)
        save_papers(papers, "europe_pmc")

    # ── Scout CORE ───────────────────────────────────────────────────────────
    log.info("── Scout CORE ───────────────────────")
    for q in random.sample(SCIENCE_QUERIES, min(2, len(SCIENCE_QUERIES))):
        papers = scout_core(q)
        save_papers(papers, "core")

    # ── Scout NASA ADS ────────────────────────────────────────────────────────
    log.info("── Scout NASA ADS ───────────────────")
    papers = scout_nasa_ads("exoplanets machine learning recent")
    save_papers(papers, "nasa_ads")

    # ── Cuántos pendientes hay en total ──────────────────────────────────────
    con     = get_db()
    pending = con.execute("SELECT COUNT(*) FROM papers WHERE processed=0").fetchone()[0]
    con.close()
    log.info("Papers pendientes de evaluar: %d", pending)

    if pending == 0:
        log.info("Nada nuevo que procesar.")
        return

    # ── Filter ───────────────────────────────────────────────────────────────
    relevant = filter_papers()
    if not relevant:
        log.warning("Ningun paper supero el umbral %.2f.", MIN_RELEVANCE_SCORE)
        return

    relevant.sort(key=lambda x: x.get("score", 0), reverse=True)
    top = relevant[:MAX_ARTICLES_PER_DAY]
    log.info("Top %d papers para redactar", len(top))

    # ── Writer ───────────────────────────────────────────────────────────────
    articles = write_articles(top)
    if not articles:
        log.warning("El writer no genero articulos.")
        return

    # ── Validator ────────────────────────────────────────────────────────────
    con        = get_db()
    papers_map = {r["id"]: dict(r) for r in con.execute("SELECT * FROM papers").fetchall()}
    con.close()
    validated = validate_articles(articles, papers_map)
    if not validated:
        log.warning("El validador rechazo todos los articulos.")
        return

    # ── Editor ───────────────────────────────────────────────────────────────
    editor_publish(validated)
    log.info("DONE — %d articulos nuevos en http://localhost:8000", len(validated))

# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if "--scheduled" in sys.argv:
        import schedule
        log.info("Scheduler: pipeline diario a las 07:00")
        schedule.every().day.at("07:00").do(run_pipeline)
        run_pipeline()
        while True:
            schedule.run_pending()
            time.sleep(60)
    else:
        run_pipeline()
