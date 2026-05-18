"""
Science Newsroom — image_gen.py
================================
Genera imágenes para los artículos publicados que aún no tienen imagen.
Usa Pollinations.ai — gratuito, sin API key, sin instalación extra.

USO:
    python image_gen.py              # genera las que faltan
    python image_gen.py --all        # regenera todas

REQUISITOS:
    pip install requests
"""

import sqlite3
import requests
import time
import logging
import hashlib
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH    = Path(__file__).parent / "data.db"
IMAGES_DIR = Path(__file__).parent / "static" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Pollinations: genera imágenes realistas gratis
# Modelo: flux (el más realista disponible)
POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"
IMAGE_WIDTH  = 800
IMAGE_HEIGHT = 500

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("imggen")

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def build_prompt(image_prompt: str, category: str, headline: str) -> str:
    """
    Construye un prompt que produce imágenes fotorrealistas, no 'estilo IA'.
    Evita palabras que activan el estilo ilustración/digital-art.
    """
    base = image_prompt.strip() if image_prompt else ""

    # Si el prompt guardado es muy corto o vacío, construir uno desde el titular
    if len(base) < 15:
        # Fallback según categoría
        cat_fallbacks = {
            "cs.AI":             "scientists working with computer servers in a modern research lab",
            "cs.LG":             "researcher analyzing data visualizations on multiple screens",
            "physics.app-ph":    "physicist conducting experiment in laboratory with equipment",
            "cond-mat.mtrl-sci": "scientist examining material sample under microscope in lab",
            "eess.SY":           "engineer working on electrical systems and circuits",
            "q-bio.NC":          "neuroscientist studying brain scans in research facility",
        }
        base = cat_fallbacks.get(category, "scientist working in modern research laboratory")

    # Sufijos que fuerzan fotorrealismo y evitan estilo AI genérico
    realism_suffix = (
        "photorealistic, documentary photography style, "
        "natural lighting, shot on Canon EOS R5, 35mm lens, "
        "high resolution, no text, no watermark"
    )

    # Prefijo que bloquea estilos no deseados
    avoid = "no illustration, no cartoon, no digital art, no painting, no render"

    full_prompt = f"{base}, {realism_suffix}, {avoid}"
    return full_prompt


def generate_image(article_id: str, prompt: str) -> bool:
    """Descarga la imagen de Pollinations y la guarda en disco."""
    dest = IMAGES_DIR / f"{article_id}.jpg"

    if dest.exists():
        log.info("  ya existe: %s.jpg", article_id)
        return True

    import urllib.parse
    encoded = urllib.parse.quote(prompt, safe="")
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={IMAGE_WIDTH}&height={IMAGE_HEIGHT}&model=flux&nologo=true&enhance=true"
    )

    log.info("  generando imagen para %s…", article_id[:12])
    log.debug("  prompt: %s", prompt[:80])

    for attempt in range(3):
        try:
            r = requests.get(url, timeout=60, stream=True)
            r.raise_for_status()

            # Verificar que es una imagen real
            content_type = r.headers.get("content-type", "")
            if "image" not in content_type:
                log.warning("  respuesta no es imagen: %s", content_type)
                time.sleep(5)
                continue

            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

            size_kb = dest.stat().st_size // 1024
            log.info("  ✓ guardada %s.jpg (%d KB)", article_id[:12], size_kb)
            return True

        except requests.exceptions.Timeout:
            log.warning("  timeout (intento %d/3)", attempt + 1)
        except Exception as e:
            log.warning("  error (intento %d/3): %s", attempt + 1, e)

        time.sleep(5 * (attempt + 1))

    log.error("  ✗ fallido: %s", article_id[:12])
    return False


# ── Main ──────────────────────────────────────────────────────────────────────

def run(regenerate_all: bool = False):
    if not DB_PATH.exists():
        log.error("DB no encontrada: %s", DB_PATH)
        log.error("Ejecuta pipeline.py primero.")
        return

    con = get_db()
    articles = [dict(r) for r in con.execute(
        "SELECT id, headline, image_prompt, category FROM articles WHERE status='published'"
    ).fetchall()]
    con.close()

    log.info("%d artículos publicados", len(articles))

    pending = []
    for a in articles:
        img_path = IMAGES_DIR / f"{a['id']}.jpg"
        if regenerate_all or not img_path.exists():
            pending.append(a)

    log.info("%d imágenes a generar", len(pending))

    ok = 0
    fail = 0
    for a in pending:
        prompt = build_prompt(a.get("image_prompt", ""), a.get("category", ""), a.get("headline", ""))
        success = generate_image(a["id"], prompt)
        if success:
            ok += 1
        else:
            fail += 1
        # Pollinations pide ser amables con el rate limit
        time.sleep(2)

    log.info("DONE — %d OK, %d fallidas", ok, fail)
    log.info("Imágenes en: %s", IMAGES_DIR)


if __name__ == "__main__":
    import sys
    regenerate = "--all" in sys.argv
    run(regenerate_all=regenerate)
