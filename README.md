CienciaHoy — AI Science Newsroom

Medio de prensa científico 100% automatizado con IA.
Convierte papers de arXiv en noticias legibles cada día.

Archivos
science-newsroom/
├── pipeline.py   ← todos los agentes (scout → filter → writer → validator → editor)
├── web.py        ← servidor web + frontend completo
├── init_db.py    ← crea la DB con ejemplos para ver la web ya
└── data.db       ← se crea automáticamente
Arrancar en 5 pasos

.\env\Scripts\Activate.ps1


1. Instalar dependencias
pip install httpx schedule fastapi uvicorn requests
2. Instalar Ollama
ollama run llama3

ollama run mistral
3. Inicializar la base de datos (con ejemplos)
python init_db.py

Esto crea data.db con 3 noticias de ejemplo para que veas la web funcionando antes de correr el pipeline completo.

4. Ver la web
uvicorn web:app --reload --port 8000

Abre http://localhost:8000

5. Correr el pipeline (genera noticias reales)
# Una sola vez
python pipeline.py

# Con scheduler automático (corre diariamente a las 7am)
python pipeline.py --scheduled

El pipeline tarda ~10-20 minutos la primera vez dependiendo de cuántos papers encuentre.

Configuración

Edita las variables al inicio de pipeline.py:

PAPERS_PER_CATEGORY = 30      # papers por categoría a buscar
MIN_RELEVANCE_SCORE = 0.65    # umbral mínimo para escribir la noticia
MAX_ARTICLES_PER_DAY = 20     # techo de publicaciones diarias

ARXIV_CATEGORIES = [
    "cs.AI",              # Inteligencia artificial
    "cs.LG",              # Machine learning
    "physics.app-ph",     # Física aplicada
    "cond-mat.mtrl-sci",  # Ciencia de materiales
    "eess.SY",            # Sistemas de energía
    "q-bio.NC",           # Neurociencia computacional
]

Lista completa de categorías arXiv:
https://arxiv.org/category_taxonomy

API REST

La web expone endpoints que puedes usar desde cualquier frontend:

Endpoint	Descripción
GET /api/articles	Lista paginada de artículos
GET /api/articles/{id}	Artículo completo
GET /api/stats	Estadísticas generales
GET /api/categories	Categorías con conteo
GET /health	Health check

Parámetros de /api/articles:

page (default: 1)
per_page (default: 12, max: 50)
category (ej: cs.AI)
tag (ej: energía)
Deploy en producción (Ollama)
Opción 1: servidor local o VPS con Ollama instalado
Instalar Ollama en la máquina
Descargar modelo (llama3 o mistral)
Ejecutar pipeline como servicio
Opción 2: híbrido
Pipeline con Ollama en máquina local
Web en servidor externo (Render / similar)
Base de datos compartida
Costo estimado
Antes (API en la nube)
~0.75 USD/día (~20–25 USD/mes)
Ahora (Ollama local)
0 USD en APIs
Solo coste de hardware eléctrico
Próximos pasos (v2)
 Ad Agent: sistema de anuncios automático
 Newsletter: envío diario automático
 SEO: sitemap.xml + meta tags dinámicos
 PubMed: segunda fuente científica de papers
 RSS feed: /feed.xml para agregadores
 Dashboard de admin: moderación de artículos