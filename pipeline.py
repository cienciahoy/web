"""
CienciaHoy — pipeline.py
Fuentes: arXiv + Semantic Scholar + Europe PMC + CORE + PubMed
Escritura via Groq API (Llama 3.3 70B)
Imagenes via Unsplash API (query contextual generada por IA)
Categorias: Ciencia, Salud, Tecnologia
"""

import json, time, sqlite3, hashlib, logging, requests, urllib.parse, random
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

DB_PATH      = Path(__file__).parent / "data.db"

# ── KEYS ──────────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
import os
load_dotenv()

GROQ_API_KEY     = os.getenv("GROQ_API_KEY", "")
UNSPLASH_API_KEY = os.getenv("UNSPLASH_API_KEY", "")

GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.3-70b-versatile"
UNSPLASH_URL = "https://api.unsplash.com/photos/random"

PAPERS_PER_SOURCE    = 5
MIN_RELEVANCE_SCORE  = 0.55
MAX_ARTICLES_PER_DAY = 12
FILTER_LIMIT         = 30

# ── BALANCE DE CATEGORIAS ─────────────────────────────────────────────────────
# Cuantos articulos maximos por grupo de categoria en la seleccion final
QUOTA_PER_GROUP = {
    "science":    4,   # cs.AI, cs.LG, cs.RO, physics.app-ph, eess.SY, science.*
    "health":     4,   # health, q-bio.NC, pubmed, europe_pmc
    "technology": 4,   # cs.AI, cs.RO, eess.SY tambien aplican; se diferencia por fuente
}

# Categorias que se cuentan como "technology" (tienen solapamiento con science)
TECH_CATEGORIES = {"cs.AI", "cs.LG", "cs.RO", "eess.SY", "technology"}
HEALTH_CATEGORIES = {"health", "q-bio.NC"}

def classify_group(category: str) -> str:
    if category in HEALTH_CATEGORIES:
        return "health"
    if category in TECH_CATEGORIES:
        return "technology"
    return "science"

ARXIV_CATEGORIES = ["cs.AI", "cs.LG", "cs.RO", "q-bio.NC", "physics.app-ph", "eess.SY"]

SCIENCE_QUERIES = [
    "artificial intelligence machine learning",
    "neuroscience brain",
    "materials science nanotechnology",
    "climate energy sustainability",
    "robotics autonomous systems",
    "quantum computing semiconductor",
]

HEALTH_QUERIES = [
    "cancer treatment therapy",
    "drug discovery medicine",
    "infectious disease vaccine",
    "mental health depression anxiety",
    "genetics genomics disease",
]

IMAGES_DIR   = Path(__file__).parent / "static" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_WIDTH  = 800
IMAGE_HEIGHT = 500

# ── LOGGING ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("cienciahoy")

# ── GROQ ──────────────────────────────────────────────────────────────────────

GROQ_HEADERS = {
    "Authorization": f"Bearer {GROQ_API_KEY}",
    "Content-Type":  "application/json",
}

def check_groq() -> bool:
    for attempt in range(3):
        try:
            r = requests.post(
                GROQ_URL,
                headers=GROQ_HEADERS,
                json={
                    "model": GROQ_MODEL,
                    "messages": [{"role": "user", "content": "di ok"}],
                    "max_tokens": 10,
                },
                timeout=15,
            )
            r.raise_for_status()
            log.info("Groq OK")
            return True
        except Exception as e:
            log.warning("Groq check intento %d/3: %s", attempt + 1, e)
            time.sleep(10)
    log.error("Groq no disponible tras 3 intentos")
    return False


def ask_groq(prompt: str, timeout: int = 30) -> str | None:
    wait_times = [15, 30, 60]
    for attempt in range(3):
        try:
            r = requests.post(
                GROQ_URL,
                headers=GROQ_HEADERS,
                json={
                    "model": GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1500,
                    "temperature": 0.7,
                },
                timeout=timeout,
            )
            if r.status_code == 429:
                wait = wait_times[attempt]
                log.warning("ask_groq 429 — esperando %ds (intento %d/3)", wait, attempt + 1)
                time.sleep(wait)
                continue
            r.raise_for_status()
            data = r.json()
            time.sleep(2)
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            log.warning("ask_groq intento %d/3: %s", attempt + 1, e)
            time.sleep(wait_times[attempt])
    log.error("ask_groq fallo tras 3 intentos")
    return None


def clean_json(text: str) -> str:
    import re
    text = text.strip()
    if "```" in text:
        p    = text.split("```")[1].strip()
        text = p[4:].strip() if p.lower().startswith("json") else p
    s, e = text.find("{"), text.rfind("}")
    if s != -1 and e > s:
        text = text[s:e+1].strip()
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    return text

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
            source_url    TEXT,
            image_query   TEXT,
            published_at  TEXT,
            status        TEXT
        );
    """)
    # Migraciones seguras para columnas nuevas
    for col, definition in [
        ("source",      "TEXT DEFAULT 'arxiv'"),
        ("source_url",  "TEXT DEFAULT ''"),
        ("image_query", "TEXT DEFAULT ''"),
    ]:
        try:
            con.execute(f"ALTER TABLE papers ADD COLUMN {col} {definition}")
            con.commit()
        except sqlite3.OperationalError:
            pass
    for col, definition in [
        ("source_url",  "TEXT DEFAULT ''"),
        ("image_query", "TEXT DEFAULT ''"),
    ]:
        try:
            con.execute(f"ALTER TABLE articles ADD COLUMN {col} {definition}")
            con.commit()
        except sqlite3.OperationalError:
            pass
    con.commit()
    con.close()
    log.info("DB lista")

def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def save_papers(papers: list, source: str = "arxiv") -> int:
    con = get_db()
    n   = 0
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
            log.warning("save_papers error: %s", e)
    con.commit()
    con.close()
    log.info("  -> %d nuevos de %s", n, source)
    return n

# ── FUENTE 1: arXiv ──────────────────────────────────────────────────────────

def scout_arxiv(category: str) -> list:
    url    = "https://export.arxiv.org/api/query"
    params = {
        "search_query": "cat:" + category,
        "sortBy":       "submittedDate",
        "sortOrder":    "descending",
        "max_results":  PAPERS_PER_SOURCE,
    }
    log.info("Scout arXiv: %s", category)
    try:
        r = requests.get(url, params=params, timeout=40)
        r.raise_for_status()
    except Exception as e:
        log.warning("arXiv error: %s", e)
        return []

    ns     = {"atom": "http://www.w3.org/2005/Atom"}
    root   = ET.fromstring(r.text)
    papers = []
    for entry in root.findall("atom:entry", ns):
        raw_id = entry.findtext("atom:id", "", ns)
        pid    = raw_id.split("/abs/")[-1].replace("/", "_")
        title  = entry.findtext("atom:title",   "", ns).strip()
        abstr  = entry.findtext("atom:summary", "", ns).strip()[:2000]
        if not title or not abstr:
            continue

        # Extraer DOI del link si existe
        doi_url = ""
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("title") == "doi":
                doi_url = link.attrib.get("href", "")
                break
        if not doi_url:
            doi_url = "https://arxiv.org/abs/" + pid.replace("_", "/")

        papers.append({
            "id":         "arxiv_" + pid,
            "title":      title,
            "abstract":   abstr,
            "authors":    json.dumps([]),
            "category":   category,
            "arxiv_url":  doi_url,
            "published":  entry.findtext("atom:published", "", ns),
            "source":     "arxiv",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    log.info("  -> %d papers", len(papers))
    return papers

# ── FUENTE 2: Semantic Scholar ────────────────────────────────────────────────

def scout_semantic_scholar(query: str, category: str = "science.general") -> list:
    url    = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query":  query,
        "limit":  PAPERS_PER_SOURCE,
        "fields": "paperId,title,abstract,authors,year,externalIds,publicationDate",
        "sort":   "relevance",
    }
    log.info("Scout Semantic Scholar: %s", query[:50])
    try:
        r = requests.get(url, params=params, timeout=30,
                         headers={"User-Agent": "CienciaHoy/1.0"})
        r.raise_for_status()
        data = r.json().get("data", [])
    except Exception as e:
        log.warning("Semantic Scholar error: %s", e)
        return []

    papers = []
    for p in data:
        if not p.get("abstract"):
            continue
        pid      = "ss_" + p["paperId"]
        ext_ids  = p.get("externalIds") or {}
        arxiv_id = ext_ids.get("ArXiv", "")
        doi      = ext_ids.get("DOI", "")
        if doi:
            url_p = "https://doi.org/" + doi
        elif arxiv_id:
            url_p = "https://arxiv.org/abs/" + arxiv_id
        else:
            url_p = "https://www.semanticscholar.org/paper/" + p["paperId"]
        papers.append({
            "id":         pid,
            "title":      (p.get("title") or "").strip(),
            "abstract":   (p.get("abstract") or "").strip()[:2000],
            "authors":    json.dumps([a.get("name", "") for a in (p.get("authors") or [])[:5]]),
            "category":   category,
            "arxiv_url":  url_p,
            "published":  p.get("publicationDate") or str(p.get("year", "")),
            "source":     "semantic_scholar",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    log.info("  -> %d papers", len(papers))
    time.sleep(2)
    return papers

# ── FUENTE 3: Europe PMC ─────────────────────────────────────────────────────

def scout_europe_pmc(query: str, category: str = "health") -> list:
    url    = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query":      query + " OPEN_ACCESS:Y",
        "resultType": "core",
        "pageSize":   PAPERS_PER_SOURCE,
        "format":     "json",
        "sort":       "FIRST_PDATE desc",
    }
    log.info("Scout Europe PMC: %s", query[:50])
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        results = r.json().get("resultList", {}).get("result", [])
    except Exception as e:
        log.warning("Europe PMC error: %s", e)
        return []

    papers = []
    for p in results:
        abstract = p.get("abstractText", "") or p.get("abstract", "")
        if not abstract:
            continue
        pid   = "epmc_" + str(p.get("id", p.get("pmid", "")))
        doi   = p.get("doi", "")
        url_p = ("https://doi.org/" + doi) if doi else \
                ("https://europepmc.org/article/" + str(p.get("source", "")) + "/" + str(p.get("id", "")))
        papers.append({
            "id":         pid,
            "title":      (p.get("title") or "").strip().rstrip("."),
            "abstract":   abstract.strip()[:2000],
            "authors":    json.dumps([a.get("fullName", "") for a in (p.get("authorList", {}).get("author") or [])[:5]]),
            "category":   category,
            "arxiv_url":  url_p,
            "published":  p.get("firstPublicationDate", ""),
            "source":     "europe_pmc",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    log.info("  -> %d papers", len(papers))
    return papers

# ── FUENTE 4: CORE ───────────────────────────────────────────────────────────

def scout_core(query: str, category: str = "science.general") -> list:
    url    = "https://api.core.ac.uk/v3/search/works"
    params = {"q": query, "limit": PAPERS_PER_SOURCE, "sort": "recency"}
    log.info("Scout CORE: %s", query[:50])
    try:
        r = requests.get(url, params=params, timeout=30,
                         headers={"User-Agent": "CienciaHoy/1.0"})
        r.raise_for_status()
        results = r.json().get("results", [])
    except Exception as e:
        log.warning("CORE error: %s", e)
        return []

    papers = []
    for p in results:
        abstract = p.get("abstract", "")
        if not abstract or len(abstract) < 80:
            continue
        pid   = "core_" + str(p.get("id", ""))
        doi   = p.get("doi", "")
        urls  = p.get("sourceFulltextUrls") or []
        if doi:
            url_p = "https://doi.org/" + doi
        elif p.get("downloadUrl"):
            url_p = p["downloadUrl"]
        elif urls:
            url_p = urls[0]
        else:
            url_p = ""
        papers.append({
            "id":         pid,
            "title":      (p.get("title") or "").strip(),
            "abstract":   abstract.strip()[:2000],
            "authors":    json.dumps([a.get("name", "") for a in (p.get("authors") or [])[:5]]),
            "category":   category,
            "arxiv_url":  url_p,
            "published":  str(p.get("publishedDate") or p.get("yearPublished", ""))[:10],
            "source":     "core",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    log.info("  -> %d papers", len(papers))
    return papers

# ── FUENTE 5: PubMed ─────────────────────────────────────────────────────────

def scout_pubmed(query: str) -> list:
    log.info("Scout PubMed: %s", query[:50])
    try:
        search = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={
                "db":      "pubmed",
                "term":    query,
                "retmax":  PAPERS_PER_SOURCE,
                "sort":    "date",
                "retmode": "json",
            },
            timeout=30,
        )
        search.raise_for_status()
        ids = search.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            log.info("  -> 0 papers")
            return []

        fetch = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            params={
                "db":      "pubmed",
                "id":      ",".join(ids),
                "retmode": "xml",
            },
            timeout=30,
        )
        fetch.raise_for_status()
        root = ET.fromstring(fetch.text)

    except Exception as e:
        log.warning("PubMed error: %s", e)
        return []

    papers = []
    for article in root.findall(".//PubmedArticle"):
        try:
            pmid    = article.findtext(".//PMID", "")
            title   = article.findtext(".//ArticleTitle", "").strip()
            abstr   = " ".join(t.text or "" for t in article.findall(".//AbstractText")).strip()[:2000]
            if not title or not abstr:
                continue
            authors = []
            for a in article.findall(".//Author")[:5]:
                ln = a.findtext("LastName", "")
                fn = a.findtext("ForeName", "")
                if ln:
                    authors.append(f"{ln} {fn}".strip())

            # Intentar obtener DOI del articulo
            doi = ""
            for aid in article.findall(".//ArticleId"):
                if aid.attrib.get("IdType") == "doi":
                    doi = aid.text or ""
                    break
            url_p = ("https://doi.org/" + doi) if doi else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

            pub_date = article.findtext(".//PubDate/Year", "") or article.findtext(".//PubDate/MedlineDate", "")[:4]
            papers.append({
                "id":         "pubmed_" + pmid,
                "title":      title,
                "abstract":   abstr,
                "authors":    json.dumps(authors),
                "category":   "health",
                "arxiv_url":  url_p,
                "published":  pub_date,
                "source":     "pubmed",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            continue

    log.info("  -> %d papers", len(papers))
    time.sleep(1)
    return papers

# ── FILTER ────────────────────────────────────────────────────────────────────

FILTER_PROMPT = """\
Devuelve SOLO este JSON, sin texto extra ni markdown:
{
  "score": 0.75,
  "reason": "motivo breve",
  "tags": ["tag1", "tag2"]
}
score es un numero entre 0.0 y 1.0.
Evalua relevancia cientifica e interes periodistico para publico general.
Titulo: TITULO_PAPER
Abstract: ABSTRACT_PAPER
"""

def filter_papers() -> list:
    con     = get_db()
    pending = [dict(r) for r in con.execute(
        "SELECT * FROM papers WHERE processed=0 ORDER BY fetched_at DESC LIMIT ?",
        (FILTER_LIMIT,)
    ).fetchall()]
    con.close()
    log.info("Filter: %d papers a procesar (limite=%d)", len(pending), FILTER_LIMIT)

    scored = []
    for p in pending:
        prompt = (FILTER_PROMPT
                  .replace("TITULO_PAPER",   p.get("title", ""))
                  .replace("ABSTRACT_PAPER", p.get("abstract", "")))
        raw    = ask_groq(prompt)

        score  = 0.0
        result = {}
        if raw:
            try:
                result    = json.loads(clean_json(raw))
                raw_score = result.get("score", 0)
                score     = float(raw_score) if not isinstance(raw_score, dict) else 0.0
            except Exception:
                pass

        con = get_db()
        procesado = 1 if raw is not None else 0
        con.execute("UPDATE papers SET score=?,processed=? WHERE id=?", (score, procesado, p["id"]))
        con.commit()
        con.close()

        if raw is None:
            log.warning("Groq no respondio, paper queda pendiente: %s", p["title"][:60])
            continue

        if score >= MIN_RELEVANCE_SCORE:
            p["score"] = score
            p["tags"]  = result.get("tags", [])
            scored.append(p)
            log.info("OK (%.2f): %s", score, p["title"][:60])
        else:
            log.info("skip (%.2f): %s", score, p["title"][:60])

    log.info("Filter: %d relevantes", len(scored))
    return scored


def select_balanced(papers: list, max_total: int = MAX_ARTICLES_PER_DAY) -> list:
    """
    Selecciona papers manteniendo cuotas por grupo (science / health / technology).
    Dentro de cada grupo ordena por score descendente.
    """
    groups: dict[str, list] = {"science": [], "health": [], "technology": []}
    for p in papers:
        g = classify_group(p.get("category", ""))
        groups[g].append(p)

    for g in groups:
        groups[g].sort(key=lambda x: x.get("score", 0), reverse=True)

    selected = []
    # Rellenar hasta cuota de cada grupo
    for g, quota in QUOTA_PER_GROUP.items():
        selected.extend(groups[g][:quota])

    # Si sobran slots (algún grupo tenia menos papers que su cuota), rellenar con el resto
    used_ids = {p["id"] for p in selected}
    remaining = [p for p in papers if p["id"] not in used_ids]
    remaining.sort(key=lambda x: x.get("score", 0), reverse=True)
    slots = max_total - len(selected)
    if slots > 0:
        selected.extend(remaining[:slots])

    selected.sort(key=lambda x: x.get("score", 0), reverse=True)
    log.info(
        "Seleccion equilibrada: %d science | %d health | %d technology | total %d",
        sum(1 for p in selected if classify_group(p["category"]) == "science"),
        sum(1 for p in selected if classify_group(p["category"]) == "health"),
        sum(1 for p in selected if classify_group(p["category"]) == "technology"),
        len(selected),
    )
    return selected[:max_total]

# ── IMAGE QUERY GENERATOR ─────────────────────────────────────────────────────

IMAGE_QUERY_PROMPT = """\
Dado el siguiente titular y resumen de una noticia cientifica, genera una consulta de busqueda
en ingles para encontrar una fotografia relevante en Unsplash. La imagen debe representar
visualmente el TEMA CONCRETO de la noticia, no a cientificos genericos en laboratorio.

Ejemplos:
- Noticia sobre genoma humano -> "DNA double helix molecular structure"
- Noticia sobre cancer de pulmon -> "lung anatomy medical illustration"
- Noticia sobre inteligencia artificial -> "neural network abstract visualization"
- Noticia sobre energia solar -> "solar panel array sunlight"
- Noticia sobre cerebro y memoria -> "human brain neuron microscopy"
- Noticia sobre vacunas ARNm -> "molecular syringe medicine laboratory"
- Noticia sobre cambio climatico artico -> "arctic ice melting polar"

Devuelve SOLO la consulta en ingles, entre 3 y 6 palabras, sin comillas ni explicacion.

Titular: HEADLINE
Resumen: SUMMARY
"""

def generate_image_query(headline: str, summary: str) -> str:
    prompt = (IMAGE_QUERY_PROMPT
              .replace("HEADLINE", headline)
              .replace("SUMMARY", summary[:200]))
    result = ask_groq(prompt, timeout=20)
    if result:
        # Limpiar la respuesta: quitar comillas, saltos de linea, etc.
        query = result.strip().strip('"').strip("'").split("\n")[0].strip()
        if 2 <= len(query.split()) <= 8:
            log.info("  image query: '%s'", query)
            return query
    return "science research laboratory"

# ── WRITER ────────────────────────────────────────────────────────────────────

WRITER_PROMPT = """\
Eres periodista cientifico experto. Convierte este paper en noticia en espanol para publico general.
Usa palabras reales del diccionario. Nunca inventes palabras.

Devuelve SOLO este JSON sin texto extra ni markdown:

{
  "headline": "Titular atractivo maximo 12 palabras",
  "summary": "Bajada de la noticia: entre 60 y 70 palabras en espanol. Presenta el descubrimiento con suficiente contexto para que el lector entienda de que trata la noticia sin necesidad de leer el cuerpo. Explica brevemente que se encontro, quien lo hizo o donde, y por que es relevante. Escrita en estilo periodistico claro, directo y atractivo.",
  "body": "Articulo periodistico de 400 a 500 palabras en espanol. Explica claramente que se descubrio, como se hizo el descubrimiento, por que importa, cuales son las limitaciones y que podria ocurrir en el futuro. Usa estructura de articulo real con: contexto inicial, descripcion del descubrimiento, explicacion de como funciona o como se logro, impacto cientifico o tecnologico, limitaciones actuales y perspectivas futuras. Mantener tono profesional, claro y natural, como una noticia de ciencia o tecnologia publicada en un medio reconocido. Sin jeroglifos, simbolos raros ni caracteres extranos. Solo palabras reales en espanol.",
  "image_query": "Consulta en ingles de 3 a 6 palabras para buscar en Unsplash una imagen que represente visualmente el tema concreto de esta noticia. NO usar 'scientist laboratory' ni 'researcher'. Usar conceptos visuales especificos del tema: moleculas, organos, tecnologia, fenomenos naturales, etc."
}

TITULO: TITULO_PAPER

ABSTRACT: ABSTRACT_PAPER

URL_FUENTE: URL_PAPER
"""

def write_articles(papers: list) -> list:
    articles = []
    for p in papers:
        aid       = hashlib.sha1(p["id"].encode()).hexdigest()[:12]
        source_url = p.get("arxiv_url", "")
        prompt = (WRITER_PROMPT
                  .replace("TITULO_PAPER",   p["title"])
                  .replace("ABSTRACT_PAPER", p["abstract"][:800])
                  .replace("URL_PAPER",      source_url))
        raw = ask_groq(prompt, timeout=60)

        if not raw:
            log.warning("Writer sin respuesta: %s", p["title"][:60])
            continue

        try:
            result = json.loads(clean_json(raw))
        except Exception as e:
            log.warning("Writer JSON invalido: %s", e)
            continue

        if not result.get("headline") or not result.get("body"):
            log.warning("Writer incompleto")
            continue

        # Obtener image_query del JSON del writer; si no viene, generarla aparte
        image_query = result.get("image_query", "").strip()
        if not image_query or len(image_query.split()) < 2:
            image_query = generate_image_query(
                result.get("headline", p["title"]),
                result.get("summary", ""),
            )

        articles.append({
            "id":          aid,
            "paper_id":    p["id"],
            "headline":    result.get("headline", p["title"]),
            "summary":     result.get("summary", ""),
            "body":        result.get("body", ""),
            "category":    p["category"],
            "tags":        json.dumps(p.get("tags", [])),
            "source_url":  source_url,
            "image_query": image_query,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "status":      "published",
        })
        log.info("Articulo: %s", result.get("headline", "")[:60])

    log.info("Writer: %d articulos", len(articles))
    return articles

# ── EDITOR ────────────────────────────────────────────────────────────────────

def editor_publish(articles: list):
    con = get_db()
    n   = 0
    for a in articles[:MAX_ARTICLES_PER_DAY]:
        con.execute(
            "INSERT OR REPLACE INTO articles "
            "(id,paper_id,headline,summary,body,category,tags,source_url,image_query,published_at,status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (a["id"], a["paper_id"], a["headline"], a["summary"],
             a["body"], a["category"], a["tags"],
             a.get("source_url", ""), a.get("image_query", ""),
             a["published_at"], "published"),
        )
        n += 1
    con.commit()
    con.close()
    log.info("Editor: %d articulos publicados", n)

# ── IMAGE GEN via UNSPLASH ────────────────────────────────────────────────────

def generate_images(articles: list):
    log.info("── Descargando imagenes Unsplash ────")
    for a in articles:
        dest = IMAGES_DIR / f"{a['id']}.jpg"
        if dest.exists():
            log.info("imagen ya existe: %s", a["id"])
            continue

        # Usar la query contextual generada por IA
        query = a.get("image_query") or "science research"
        log.info("buscando imagen: '%s' para: %s", query, a["headline"][:40])

        ok = False
        for attempt in range(3):
            try:
                r = requests.get(
                    UNSPLASH_URL,
                    params={
                        "query":       query,
                        "orientation": "landscape",
                        "w":           IMAGE_WIDTH,
                        "h":           IMAGE_HEIGHT,
                    },
                    headers={"Authorization": f"Client-ID {UNSPLASH_API_KEY}"},
                    timeout=30,
                )
                r.raise_for_status()
                data    = r.json()
                img_url = data["urls"]["regular"]
                img     = requests.get(img_url, timeout=60, stream=True)
                img.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in img.iter_content(chunk_size=8192):
                        f.write(chunk)
                size_kb = dest.stat().st_size // 1024
                log.info("imagen guardada (%d KB) — foto de %s", size_kb, data.get("user", {}).get("name", "?"))
                ok = True
                break
            except Exception as e:
                log.warning("imagen error (intento %d/3): %s", attempt + 1, e)
                time.sleep(5 * (attempt + 1))

        if not ok:
            log.warning("imagen fallida para %s", a["id"])

        time.sleep(1)

# ── EXPORT ────────────────────────────────────────────────────────────────────

def export_json():
    con  = get_db()
    rows = con.execute("SELECT * FROM articles WHERE status='published' ORDER BY published_at DESC").fetchall()
    con.close()
    articles = []
    for r in rows:
        d = dict(r)
        try:
            d["tags"] = json.loads(d.get("tags", "[]"))
        except Exception:
            d["tags"] = []
        articles.append(d)
    out = Path(__file__).parent / "articles.json"
    out.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Exportado articles.json — %d articulos", len(articles))

# ── PIPELINE ──────────────────────────────────────────────────────────────────

def run_pipeline():
    log.info("═══ PIPELINE START ═══════════════════")

    if not check_groq():
        log.error("Abortando: Groq no disponible.")
        return

    init_db()

    # ── arXiv: Ciencia y Tecnologia ──────────────────────────────────────────
    log.info("── Scout arXiv ──────────────────────")
    for cat in ARXIV_CATEGORIES:
        papers = scout_arxiv(cat)
        save_papers(papers, "arxiv")
        time.sleep(4)

    # ── Semantic Scholar: Ciencia y Tecnologia ────────────────────────────────
    log.info("── Scout Semantic Scholar ───────────")
    for q in random.sample(SCIENCE_QUERIES, min(2, len(SCIENCE_QUERIES))):
        papers = scout_semantic_scholar(q, category="science.general")
        save_papers(papers, "semantic_scholar")
        time.sleep(2)

    # ── PubMed: Salud ─────────────────────────────────────────────────────────
    log.info("── Scout PubMed ─────────────────────")
    for q in random.sample(HEALTH_QUERIES, min(2, len(HEALTH_QUERIES))):
        papers = scout_pubmed(q)
        save_papers(papers, "pubmed")
        time.sleep(2)

    # ── Europe PMC: Salud ─────────────────────────────────────────────────────
    log.info("── Scout Europe PMC ─────────────────")
    for q in random.sample(HEALTH_QUERIES, min(1, len(HEALTH_QUERIES))):
        papers = scout_europe_pmc(q, category="health")
        save_papers(papers, "europe_pmc")
        time.sleep(2)

    # ── CORE: Ciencia general ─────────────────────────────────────────────────
    log.info("── Scout CORE ───────────────────────")
    for q in random.sample(SCIENCE_QUERIES, min(1, len(SCIENCE_QUERIES))):
        papers = scout_core(q, category="science.general")
        save_papers(papers, "core")
        time.sleep(2)

    con     = get_db()
    pending = con.execute("SELECT COUNT(*) FROM papers WHERE processed=0").fetchone()[0]
    con.close()
    log.info("Papers pendientes: %d", pending)

    if pending == 0:
        log.info("Nada nuevo que procesar.")
        export_json()
        return

    log.info("── Filter ───────────────────────────")
    relevant = filter_papers()
    if not relevant:
        log.warning("Ningun paper supero el umbral.")
        export_json()
        return

    # Seleccion equilibrada por categoria
    log.info("── Seleccion equilibrada ────────────")
    top = select_balanced(relevant, MAX_ARTICLES_PER_DAY)
    log.info("Top %d papers seleccionados", len(top))

    log.info("── Writer ───────────────────────────")
    articles = write_articles(top)
    if not articles:
        log.warning("El writer no genero articulos.")
        export_json()
        return

    log.info("── Editor ───────────────────────────")
    editor_publish(articles)

    log.info("── Imagenes ─────────────────────────")
    generate_images(articles)

    export_json()

    log.info("═══ DONE — %d articulos nuevos listos ═══", len(articles))


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
