"""
CienciaHoy — pipeline.py
1 articulo, imagen hardcodeada por categoria, sin humanos posibles.
"""

import json, time, sqlite3, hashlib, logging, requests, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

DB_PATH      = Path(__file__).parent / "data.db"
OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral"

PAPERS_PER_SOURCE    = 5
MIN_RELEVANCE_SCORE  = 0.55
MAX_ARTICLES_PER_DAY = 1

ARXIV_CATEGORIES = ["cs.AI"]

IMAGES_DIR   = Path(__file__).parent / "static" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_WIDTH  = 800
IMAGE_HEIGHT = 500

# ── PROMPTS DE IMAGEN 100% HARDCODEADOS — NUNCA HUMANOS ──────────────────────
# Rotamos entre varios para variedad. Todos son objetos/naturaleza/macro.

IMAGE_PROMPTS = {
    "cs.AI": [
        "glowing fiber optic cables macro close-up blue light",
        "computer circuit board macro green traces copper",
        "server rack data center blinking LED lights",
        "abstract binary data stream floating blue dark background",
        "microchip processor macro photography extreme detail",
    ],
    "cs.LG": [
        "colorful neural network diagram glowing nodes dark background",
        "computer monitor showing colorful graphs and code no people",
        "data visualization abstract colorful chart macro",
        "electronic circuit board close-up macro photography",
        "glowing computer chip semiconductor wafer macro",
    ],
    "physics.app-ph": [
        "laboratory glass beakers chemical liquids colorful macro",
        "laser beam splitting prism physics experiment",
        "oscilloscope screen showing wave patterns close-up",
        "magnetic field iron filings pattern macro photography",
        "optical fiber light transmission macro close-up",
    ],
    "cond-mat.mtrl-sci": [
        "crystal structure mineral macro photography colorful",
        "metal surface electron microscope texture detail",
        "graphene nanotube structure visualization macro",
        "polymer material surface macro photography",
        "alloy metal cross section microscope detail",
    ],
    "eess.SY": [
        "solar panel array desert landscape golden hour",
        "wind turbines field sunset dramatic sky",
        "power grid electrical transformer station",
        "lithium battery cells close-up macro photography",
        "smart meter electrical equipment close-up",
    ],
    "q-bio.NC": [
        "neuron synapse fluorescence microscopy colorful",
        "brain tissue slice stained microscopy purple blue",
        "DNA double helix macro visualization colorful",
        "cell division mitosis fluorescence microscopy",
        "MRI brain scan cross section colorful",
    ],
    "science.general": [
        "laboratory glassware flask beakers colorful liquids",
        "periodic table elements close-up macro",
        "microscope lens close-up laboratory equipment",
        "test tubes colorful chemicals laboratory",
        "scientific instrument dial gauge close-up macro",
    ],
    "science.life": [
        "plant cell chloroplast fluorescence microscopy green",
        "bacteria culture petri dish laboratory macro",
        "DNA gel electrophoresis bands laboratory",
        "enzyme protein structure colorful visualization",
        "cell membrane lipid bilayer macro visualization",
    ],
    "science.astronomy": [
        "telescope mirror reflective surface close-up macro",
        "star field deep space nebula colorful astronomy",
        "galaxy spiral arms long exposure photography",
        "radio telescope dish array landscape",
        "planetary surface texture macro geology",
    ],
}

DEFAULT_PROMPTS = [
    "laboratory glassware colorful chemicals macro close-up",
    "scientific equipment metal instruments close-up",
    "crystal mineral macro photography colorful detail",
    "fiber optic cables light macro close-up blue",
    "circuit board electronic components macro photography",
]

import random

def get_image_prompt(category: str) -> str:
    prompts = IMAGE_PROMPTS.get(category, DEFAULT_PROMPTS)
    base    = random.choice(prompts)
    suffix  = (
        ", photorealistic, documentary photography, natural lighting, "
        "Canon EOS R5, 100mm macro lens, high resolution, sharp focus, "
        "no text, no watermark, no humans, no people, no hands, no faces, "
        "no bodies, no illustration, no cartoon, no digital art, no painting"
    )
    return base + suffix

# ── LOGGING ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("cienciahoy")

# ── OLLAMA ────────────────────────────────────────────────────────────────────

def check_ollama() -> bool:
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        match  = any(OLLAMA_MODEL in m for m in models)
        log.info("Ollama OK" if match else "Modelo no encontrado")
        return match
    except Exception as e:
        log.error("Ollama no responde: %s", e)
        return False

def ask_ollama(prompt: str, timeout: int = 120) -> str:
    for attempt in range(2):
        try:
            r    = requests.post(
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
            log.warning("Ollama error: %s", e)
        time.sleep(3)
    return ""

def clean_json(text: str) -> str:
    text = text.strip()
    if "```" in text:
        p    = text.split("```")[1].strip()
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
    try:
        con.execute("ALTER TABLE papers ADD COLUMN source TEXT DEFAULT 'arxiv'")
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
    log.info("  -> %d nuevos", n)
    return n

# ── SCOUT ─────────────────────────────────────────────────────────────────────

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
        r = requests.get(url, params=params, timeout=30)
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
    pending = [dict(r) for r in con.execute("SELECT * FROM papers WHERE processed=0").fetchall()]
    con.close()
    log.info("Filter: %d papers pendientes", len(pending))

    scored = []
    for p in pending:
        prompt = (FILTER_PROMPT
                  .replace("TITULO_PAPER",   p.get("title", ""))
                  .replace("ABSTRACT_PAPER", p.get("abstract", "")))
        raw    = ask_ollama(prompt, timeout=120)

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
        con.execute("UPDATE papers SET score=?,processed=1 WHERE id=?", (score, p["id"]))
        con.commit()
        con.close()

        if score >= MIN_RELEVANCE_SCORE:
            p["score"] = score
            p["tags"]  = result.get("tags", [])
            scored.append(p)
            log.info("OK (%.2f): %s", score, p["title"][:60])
        else:
            log.info("skip (%.2f): %s", score, p["title"][:60])

    log.info("Filter: %d relevantes", len(scored))
    return scored

# ── WRITER ────────────────────────────────────────────────────────────────────

WRITER_PROMPT = """\
Eres periodista cientifico. Convierte este paper en noticia en espanol para publico general.
Devuelve SOLO este JSON sin texto extra ni markdown:
{
  "headline": "Titular atractivo maximo 12 palabras",
  "summary": "Una frase resumen para portada maxim 20 palabras",
  "body": "Noticia de 150 palabras: que se descubrio, como, por que importa, limitaciones. Sin jeroglifos ni caracteres raros."
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
        raw = ask_ollama(prompt, timeout=180)

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

        # Imagen 100% hardcodeada — Ollama no toca esto
        image_prompt = get_image_prompt(p["category"])

        articles.append({
            "id":           aid,
            "paper_id":     p["id"],
            "headline":     result.get("headline", p["title"]),
            "summary":      result.get("summary", ""),
            "body":         result.get("body", ""),
            "category":     p["category"],
            "tags":         json.dumps(p.get("tags", [])),
            "image_prompt": image_prompt,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "status":       "published",
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
            "(id,paper_id,headline,summary,body,category,tags,image_prompt,published_at,status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (a["id"], a["paper_id"], a["headline"], a["summary"],
             a["body"], a["category"], a["tags"],
             a["image_prompt"], a["published_at"], "published"),
        )
        n += 1
    con.commit()
    con.close()
    log.info("Editor: %d articulos publicados", n)

# ── IMAGE GEN ─────────────────────────────────────────────────────────────────

def generate_images(articles: list):
    log.info("── Generando imagenes ───────────────")
    for a in articles:
        dest = IMAGES_DIR / f"{a['id']}.jpg"
        if dest.exists():
            log.info("imagen ya existe: %s", a["id"])
            continue

        prompt  = a["image_prompt"]
        encoded = urllib.parse.quote(prompt, safe="")
        url     = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={IMAGE_WIDTH}&height={IMAGE_HEIGHT}&model=flux&nologo=true&enhance=true&seed={random.randint(1,9999)}"
        )
        log.info("generando imagen para: %s", a["headline"][:50])

        ok = False
        for attempt in range(3):
            try:
                r = requests.get(url, timeout=90, stream=True)
                r.raise_for_status()
                if "image" not in r.headers.get("content-type", ""):
                    time.sleep(5)
                    continue
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                size_kb = dest.stat().st_size // 1024
                log.info("✓ imagen guardada (%d KB)", size_kb)
                ok = True
                break
            except Exception as e:
                log.warning("imagen error (intento %d/3): %s", attempt + 1, e)
                time.sleep(5 * (attempt + 1))

        if not ok:
            log.warning("✗ imagen fallida para %s", a["id"])

        time.sleep(3)

# ── PIPELINE ──────────────────────────────────────────────────────────────────

def run_pipeline():
    log.info("═══ PIPELINE START ═══════════════════")

    if not check_ollama():
        log.error("Abortando: Ollama no disponible.")
        return

    init_db()

    log.info("── Scout ────────────────────────────")
    for cat in ARXIV_CATEGORIES:
        papers = scout_arxiv(cat)
        save_papers(papers, "arxiv")
        time.sleep(2)

    con     = get_db()
    pending = con.execute("SELECT COUNT(*) FROM papers WHERE processed=0").fetchone()[0]
    con.close()
    log.info("Papers pendientes: %d", pending)

    if pending == 0:
        log.info("Nada nuevo que procesar.")
        return

    log.info("── Filter ───────────────────────────")
    relevant = filter_papers()
    if not relevant:
        log.warning("Ningun paper supero el umbral.")
        return

    relevant.sort(key=lambda x: x.get("score", 0), reverse=True)
    top = relevant[:MAX_ARTICLES_PER_DAY]
    log.info("Mejor paper: %s", top[0]["title"][:60])

    log.info("── Writer ───────────────────────────")
    articles = write_articles(top)
    if not articles:
        log.warning("El writer no genero articulos.")
        return

    log.info("── Editor ───────────────────────────")
    editor_publish(articles)

    log.info("── Imagenes ─────────────────────────")
    generate_images(articles)

    log.info("═══ DONE — 1 articulo listo ══════════")

if __name__ == "__main__":
    run_pipeline()
