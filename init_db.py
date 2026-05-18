"""
Science Newsroom — init_db.py
==============================
Crea data.db con el esquema correcto + 3 artículos de ejemplo
para que puedas ver la web funcionando antes de correr el pipeline.

USO:
    python init_db.py
"""

import json
import sqlite3
from datetime import datetime, timezone, timedelta
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

CREATE INDEX IF NOT EXISTS idx_articles_status
    ON articles(status);

CREATE INDEX IF NOT EXISTS idx_articles_published
    ON articles(published_at DESC);
"""

# ─── Datos de ejemplo ─────────────────────────────────────────────────────────

EXAMPLE_PAPERS = [
    {
        "id": "2401_00001",
        "title": "Efficient Thermal Energy Storage Using Novel Phase-Change Materials with Enhanced Conductivity",
        "abstract": "We present a new class of phase-change materials (PCMs) incorporating graphene nanoplatelets that achieve 18% improvement in thermal conductivity compared to conventional paraffin-based systems. Experimental validation across 500 charge-discharge cycles demonstrates stable performance with less than 2% degradation. Applications include industrial waste heat recovery and residential heating systems.",
        "authors": json.dumps(["García, M.", "Chen, L.", "Müller, H."]),
        "category": "eess.SY",
        "arxiv_url": "https://arxiv.org/abs/2401.00001",
        "published": (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat(),
        "score": 0.87,
        "processed": 1,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    },
    {
        "id": "2401_00002",
        "title": "A Sparse Mixture-of-Experts Architecture for Large Language Models with Reduced Inference Cost",
        "abstract": "This work introduces SparseMax, a mixture-of-experts transformer variant that activates only 12% of parameters per token during inference while maintaining 97% of the performance of dense baselines on standard benchmarks. Evaluated on 8 natural language understanding tasks, SparseMax reduces GPU memory requirements by 4x with only 1.8% accuracy drop.",
        "authors": json.dumps(["Park, J.", "Williams, S.", "Patel, A.", "Rossi, F."]),
        "category": "cs.AI",
        "arxiv_url": "https://arxiv.org/abs/2401.00002",
        "published": (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat(),
        "score": 0.91,
        "processed": 1,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    },
    {
        "id": "2401_00003",
        "title": "Cortical Plasticity Mechanisms in Adult Zebrafish Following Optic Nerve Regeneration",
        "abstract": "Unlike mammals, zebrafish can regenerate optic nerve fibers within weeks of injury. Using calcium imaging and single-cell RNA sequencing, we identified a population of Müller glia cells that dedifferentiate and act as neural progenitors, re-establishing functional visual circuits in 94% of injured animals within 21 days. The transcription factor Ascl1a was found critical for this process.",
        "authors": json.dumps(["Okafor, N.", "Tanaka, Y.", "Brito, C."]),
        "category": "q-bio.NC",
        "arxiv_url": "https://arxiv.org/abs/2401.00003",
        "published": (datetime.now(timezone.utc) - timedelta(hours=18)).isoformat(),
        "score": 0.83,
        "processed": 1,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    },
]

EXAMPLE_ARTICLES = [
    {
        "id": "art000001",
        "paper_id": "2401_00001",
        "headline": "Nuevo material mejora almacenamiento térmico un 18% con grafeno",
        "summary": "Investigadores desarrollaron materiales de cambio de fase con nanoplaquetas de grafeno que superan en eficiencia a los sistemas de parafina convencionales, abriendo la puerta a recuperación industrial de calor residual.",
        "body": """Un equipo internacional de investigadores ha presentado una nueva clase de materiales de cambio de fase (PCM, por sus siglas en inglés) que incorporan nanoplaquetas de grafeno para mejorar de forma significativa la eficiencia del almacenamiento de energía térmica.

El estudio, publicado en la plataforma de preprints arXiv, demuestra que estos materiales alcanzan una mejora del 18% en conductividad térmica en comparación con los sistemas de parafina convencionales, ampliamente utilizados en la industria.

Los investigadores validaron el rendimiento del material durante 500 ciclos de carga y descarga, observando una degradación inferior al 2%, lo que sugiere una vida útil prolongada y un comportamiento estable en condiciones reales de operación.

Entre las aplicaciones más prometedoras identificadas por el equipo figuran la recuperación de calor residual en entornos industriales y los sistemas de calefacción residencial, dos sectores donde la eficiencia energética tiene un impacto directo en las emisiones de carbono.

El uso de grafeno como aditivo conductor no es nuevo en la literatura científica, pero la formulación específica presentada en este trabajo —que combina tamaño de partícula, concentración y método de dispersión— representa un enfoque novedoso que los autores describen como escalable industrialmente.

Limitaciones del estudio: Los experimentos se realizaron en condiciones de laboratorio controladas. Los autores señalan que son necesarias pruebas en prototipos a escala real antes de evaluar la viabilidad comercial del material.""",
        "category": "eess.SY",
        "tags": json.dumps(["energía", "materiales", "grafeno", "térmica"]),
        "image_prompt": "graphene nanoplatelet thermal energy storage material laboratory research scientific",
        "published_at": (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat(),
        "status": "published",
    },
    {
        "id": "art000002",
        "paper_id": "2401_00002",
        "headline": "Nueva arquitectura de IA recorta memoria GPU a la cuarta parte sin perder precisión",
        "summary": "SparseMax activa solo el 12% de sus parámetros por token durante la inferencia, reduciendo el consumo de memoria cuatro veces con apenas un 1.8% de pérdida de rendimiento en tareas de lenguaje natural.",
        "body": """Un equipo de investigadores en aprendizaje automático ha presentado SparseMax, una variante de la arquitectura transformer que promete hacer los modelos de lenguaje grandes más accesibles y eficientes en recursos computacionales.

La innovación central de SparseMax consiste en una estrategia de activación selectiva: durante la inferencia, el modelo activa únicamente el 12% de sus parámetros por cada token procesado, en lugar de involucrar toda la red como ocurre en los transformers densos tradicionales.

Esta técnica, enmarcada en la familia de los modelos "mezcla de expertos" (Mixture of Experts, MoE), permite reducir los requisitos de memoria GPU en un factor de cuatro. En términos prácticos, esto podría democratizar el uso de modelos de gran escala en entornos con hardware más limitado.

La pérdida de rendimiento asociada es de apenas un 1.8% en ocho tareas estándar de comprensión del lenguaje natural, y el modelo retiene el 97% del rendimiento de sus equivalentes densos, según los experimentos reportados por los autores.

El trabajo se suma a una línea de investigación activa que busca equilibrar capacidad y eficiencia en modelos de IA, un problema relevante tanto por razones económicas como medioambientales dado el alto costo energético del entrenamiento e inferencia a gran escala.

Limitaciones del estudio: Los resultados se obtuvieron en benchmarks establecidos y podría no reflejar el comportamiento en tareas específicas o distribuciones de datos fuera de distribución. El código fuente no ha sido publicado aún.""",
        "category": "cs.AI",
        "tags": json.dumps(["IA", "LLM", "eficiencia", "transformers"]),
        "image_prompt": "sparse neural network architecture diagram artificial intelligence machine learning efficiency",
        "published_at": (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat(),
        "status": "published",
    },
    {
        "id": "art000003",
        "paper_id": "2401_00003",
        "headline": "El pez cebra regenera sus nervios ópticos: una clave para tratar la ceguera",
        "summary": "Científicos identificaron las células gliales responsables de la regeneración óptica en peces cebra, un proceso que restaura la visión en el 94% de los casos en solo tres semanas. El hallazgo abre nuevas vías para terapias en humanos.",
        "body": """A diferencia de los mamíferos, el pez cebra posee una notable capacidad: puede regenerar las fibras del nervio óptico en cuestión de semanas tras sufrir una lesión. Un nuevo estudio explora los mecanismos celulares y moleculares que hacen posible esta hazaña biológica.

Mediante imágenes de calcio y secuenciación de ARN monocelular —técnicas que permiten monitorizar la actividad celular y el perfil genético de células individuales—, el equipo identificó una población específica de células gliales de Müller que juegan un papel central en el proceso.

Estas células son capaces de desdiferenciarse, es decir, de revertir a un estado más primitivo que les permite actuar como progenitores neurales. A partir de ahí, establecen nuevos circuitos visuales funcionales en el 94% de los animales con lesión óptica, en un plazo de solo 21 días.

El factor de transcripción Ascl1a resultó ser crítico para desencadenar este proceso regenerativo. Cuando los investigadores inhibieron su expresión, la regeneración se vio severamente comprometida, lo que convierte a esta molécula en un candidato prometedor para intervenciones terapéuticas.

El hallazgo tiene implicaciones directas para la investigación sobre enfermedades degenerativas de la retina y del nervio óptico en humanos, como el glaucoma o la neuropatía óptica isquémica, condiciones para las que actualmente no existen tratamientos regenerativos.

Limitaciones del estudio: Los resultados se obtuvieron en un modelo animal (Danio rerio) y la extrapolación a mamíferos requiere investigación adicional. La activación de Ascl1a en células humanas podría tener efectos no deseados que deberán evaluarse.""",
        "category": "q-bio.NC",
        "tags": json.dumps(["neurociencia", "regeneración", "visión", "zebrafish"]),
        "image_prompt": "zebrafish optic nerve regeneration neuroscience laboratory scientific research glial cells",
        "published_at": (datetime.now(timezone.utc) - timedelta(hours=16)).isoformat(),
        "status": "published",
    },
]

# ─── Main ─────────────────────────────────────────────────────────────────────

def init_db():
    print(f"Creando base de datos en: {DB_PATH}")
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)

    print("Insertando papers de ejemplo…")
    for p in EXAMPLE_PAPERS:
        con.execute("""
            INSERT OR IGNORE INTO papers
                (id, title, abstract, authors, category, arxiv_url,
                 published, score, processed, fetched_at)
            VALUES
                (:id, :title, :abstract, :authors, :category, :arxiv_url,
                 :published, :score, :processed, :fetched_at)
        """, p)

    print("Insertando artículos de ejemplo…")
    for a in EXAMPLE_ARTICLES:
        con.execute("""
            INSERT OR IGNORE INTO articles
                (id, paper_id, headline, summary, body, category,
                 tags, image_prompt, published_at, status)
            VALUES
                (:id, :paper_id, :headline, :summary, :body, :category,
                 :tags, :image_prompt, :published_at, :status)
        """, a)

    con.commit()
    con.close()

    print()
    print("✅ data.db creada con:")
    print(f"   - {len(EXAMPLE_PAPERS)} papers de ejemplo")
    print(f"   - {len(EXAMPLE_ARTICLES)} artículos publicados")
    print()
    print("Siguiente paso: uvicorn web:app --reload")


if __name__ == "__main__":
    init_db()
