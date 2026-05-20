"""
CienciaHoy — web.py
Lee desde articles.json (sin SQLite)
"""

import json
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

ARTICLES_PATH = Path(__file__).parent / "articles.json"
IMAGES_DIR    = Path(__file__).parent / "static" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

CAT_LABELS = {
    "cs.AI":             "Inteligencia Artificial",
    "cs.LG":             "Machine Learning",
    "physics.app-ph":    "Física Aplicada",
    "cond-mat.mtrl-sci": "Materiales",
    "eess.SY":           "Energía",
    "q-bio.NC":          "Neurociencia",
    "science.general":   "Ciencia",
    "science.life":      "Biología",
    "science.astronomy": "Astronomía",
}

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


def load_articles() -> list:
    if not ARTICLES_PATH.exists():
        return []
    try:
        return json.loads(ARTICLES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def enrich(a: dict) -> dict:
    d = dict(a)
    if isinstance(d.get("tags"), str):
        try:
            d["tags"] = json.loads(d["tags"])
        except Exception:
            d["tags"] = []
    if d.get("published_at"):
        try:
            dt = datetime.fromisoformat(d["published_at"].replace("Z", "+00:00"))
            meses = ["enero","febrero","marzo","abril","mayo","junio",
                     "julio","agosto","septiembre","octubre","noviembre","diciembre"]
            d["published_at_fmt"] = f"{dt.day} de {meses[dt.month-1]}, {dt.year}"
        except Exception:
            d["published_at_fmt"] = d["published_at"][:10]
    cat = d.get("category", "")
    d["category_label"] = CAT_LABELS.get(cat, cat.split(".")[-1] if "." in cat else cat)
    d["has_image"] = (IMAGES_DIR / f"{d['id']}.jpg").exists()
    return d


# ── API ───────────────────────────────────────────────────────────────────────

@app.get("/api/articles")
def list_articles(
    page:     int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=50),
    category: str = Query(None),
):
    all_articles = [enrich(a) for a in load_articles() if a.get("status") == "published"]
    if category:
        all_articles = [a for a in all_articles if a.get("category") == category]
    total  = len(all_articles)
    offset = (page - 1) * per_page
    page_articles = all_articles[offset:offset + per_page]
    return {
        "total":    total,
        "page":     page,
        "pages":    max(1, (total + per_page - 1) // per_page),
        "articles": page_articles,
    }


@app.get("/api/articles/{article_id}")
def get_article(article_id: str):
    all_articles = load_articles()
    for a in all_articles:
        if a.get("id") == article_id and a.get("status") == "published":
            return enrich(a)
    raise HTTPException(status_code=404, detail="No encontrado")


@app.get("/api/categories")
def list_categories():
    all_articles = [a for a in load_articles() if a.get("status") == "published"]
    counts: dict = {}
    for a in all_articles:
        cat = a.get("category", "")
        counts[cat] = counts.get(cat, 0) + 1
    return [
        {"category": cat, "count": n, "label": CAT_LABELS.get(cat, cat)}
        for cat, n in sorted(counts.items(), key=lambda x: -x[1])
    ]


@app.get("/health")
def health():
    return {"status": "ok", "articles_file": ARTICLES_PATH.exists(), "count": len(load_articles())}


@app.get("/debug")
def debug():
    import os
    base = Path(__file__).parent
    return {
        "cwd": str(base),
        "articles_path": str(ARTICLES_PATH),
        "articles_exists": ARTICLES_PATH.exists(),
        "files": os.listdir(base),
    }
    
# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=DM+Sans:wght@300;400;500;600&display=swap');
:root{
  --bg:#f5f4f0;--surface:#ffffff;--border:#e5e1d8;
  --text:#1a1816;--muted:#6b6760;--accent:#c04a1a;
  --radius:10px;
  --serif:'Playfair Display',Georgia,serif;
  --sans:'DM Sans',-apple-system,sans-serif;
}
@media(prefers-color-scheme:dark){
  :root{--bg:#0f0e0c;--surface:#1a1916;--border:#2a2925;--text:#e8e4dc;--muted:#88847f;--accent:#e8784a;}
}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased;}
a{color:inherit;text-decoration:none;}

header{background:var(--surface);border-bottom:2px solid var(--text);position:sticky;top:0;z-index:100;backdrop-filter:blur(8px);}
.hinner{max-width:1200px;margin:0 auto;padding:0 1.5rem;display:flex;align-items:center;justify-content:space-between;height:58px;}
.logo{font-family:var(--serif);font-size:1.6rem;font-weight:900;letter-spacing:-.02em;}
.logo em{color:var(--accent);font-style:normal;}
.hdate{font-size:.68rem;color:var(--muted);letter-spacing:.07em;text-transform:uppercase;}

.navbar{background:var(--surface);border-bottom:1px solid var(--border);overflow-x:auto;white-space:nowrap;-ms-overflow-style:none;scrollbar-width:none;}
.navbar::-webkit-scrollbar{display:none;}
.ninner{max-width:1200px;margin:0 auto;padding:0 1.5rem;display:flex;}
.nbtn{font-size:.72rem;font-weight:600;letter-spacing:.05em;text-transform:uppercase;padding:10px 16px;border:none;background:none;color:var(--muted);cursor:pointer;border-bottom:2px solid transparent;transition:all .15s;flex-shrink:0;font-family:var(--sans);}
.nbtn:hover{color:var(--text);}
.nbtn.active{color:var(--accent);border-bottom-color:var(--accent);}

main{max-width:1200px;margin:0 auto;padding:2.5rem 1.5rem;}

.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:1.5rem;}

.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;cursor:pointer;transition:transform .2s,box-shadow .2s;display:flex;flex-direction:column;}
.card:hover{transform:translateY(-4px);box-shadow:0 12px 36px rgba(0,0,0,.1);}

.card-img{width:100%;aspect-ratio:16/9;overflow:hidden;background:var(--border);}
.card-img img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .4s;}
.card:hover .card-img img{transform:scale(1.05);}
.card-placeholder{width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:2.5rem;}

.card-body{padding:1.1rem 1.2rem 1.2rem;flex:1;display:flex;flex-direction:column;gap:.4rem;}
.card-cat{font-size:.64rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);}
.card-title{font-family:var(--serif);font-size:1.05rem;line-height:1.28;font-weight:700;flex:1;}
.card-summary{font-size:.8rem;color:var(--muted);line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.card-meta{font-size:.68rem;color:var(--muted);display:flex;align-items:center;justify-content:space-between;margin-top:.3rem;}
.card-tags{display:flex;gap:.3rem;flex-wrap:wrap;}
.tag{font-size:.6rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;background:rgba(192,74,26,.1);color:var(--accent);border-radius:4px;padding:2px 7px;}

.empty{text-align:center;padding:5rem 1rem;color:var(--muted);}
.spinner{display:inline-block;width:28px;height:28px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .7s linear infinite;margin-bottom:1rem;}
@keyframes spin{to{transform:rotate(360deg);}}

.pagination{display:flex;justify-content:center;gap:.5rem;margin-top:2.5rem;flex-wrap:wrap;}
.pbtn{font-size:.78rem;padding:7px 16px;border-radius:6px;border:1px solid var(--border);background:var(--surface);color:var(--text);cursor:pointer;transition:all .15s;font-family:var(--sans);}
.pbtn:hover,.pbtn.active{background:var(--accent);border-color:var(--accent);color:#fff;}
"""

ART_CSS = CSS + """
.art-wrap{max-width:720px;margin:0 auto;padding:2.5rem 1.5rem 5rem;}
.back{font-size:.75rem;color:var(--muted);display:inline-flex;align-items:center;gap:6px;margin-bottom:2rem;cursor:pointer;transition:color .15s;background:none;border:none;font-family:var(--sans);}
.back:hover{color:var(--accent);}
.art-cat{font-size:.68rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-bottom:.5rem;}
.art-bar{width:40px;height:3px;background:var(--accent);margin:.5rem 0 1.2rem;}
.art-title{font-family:var(--serif);font-size:clamp(1.8rem,4vw,2.8rem);line-height:1.12;font-weight:900;letter-spacing:-.025em;margin-bottom:1rem;}
.art-summary{font-size:1.08rem;color:var(--muted);border-left:3px solid var(--accent);padding-left:1.1rem;margin-bottom:1.5rem;font-style:italic;line-height:1.65;}
.art-meta{font-size:.72rem;color:var(--muted);display:flex;flex-wrap:wrap;gap:.8rem;align-items:center;padding:1rem 0;border-top:1px solid var(--border);border-bottom:1px solid var(--border);margin-bottom:2rem;}
.art-score{font-weight:700;color:#059669;}
.art-img{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:10px;margin-bottom:2rem;display:block;}
.art-body{font-size:1.02rem;line-height:1.9;color:var(--text);}
.art-body p{margin-bottom:1.3em;}
.art-source{margin-top:2rem;padding:1rem 1.2rem;background:rgba(192,74,26,.06);border-radius:8px;font-size:.8rem;color:var(--muted);border-left:3px solid var(--accent);}
.art-source a{color:var(--accent);font-weight:600;}
.art-source a:hover{text-decoration:underline;}
.rel{max-width:720px;margin:0 auto;padding:0 1.5rem 4rem;}
.rel-head{font-size:.68rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);border-bottom:1px solid var(--border);padding-bottom:.6rem;margin-bottom:1.2rem;}
.rel-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:1rem;}
.rel-card{cursor:pointer;padding:.8rem;border:1px solid var(--border);border-radius:8px;transition:border-color .15s;}
.rel-card:hover{border-color:var(--accent);}
.rel-cat{font-size:.62rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);margin-bottom:.3rem;}
.rel-title{font-family:var(--serif);font-size:.92rem;font-weight:700;line-height:1.3;}
"""

# ── INDEX ─────────────────────────────────────────────────────────────────────

INDEX = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CienciaHoy — Noticias científicas</title>
<meta name="description" content="Las últimas noticias científicas cada día.">
<style>{CSS}</style>
</head>
<body>
<header>
  <div class="hinner">
    <a class="logo" href="/"><em>Ciencia</em>Hoy</a>
    <span class="hdate" id="hdate"></span>
  </div>
</header>
<nav class="navbar">
  <div class="ninner" id="navbar">
    <button class="nbtn active" onclick="setCat(null,this)">Todo</button>
  </div>
</nav>
<main>
  <div class="grid" id="grid"></div>
  <div class="pagination" id="pag"></div>
</main>
<script>
let page=1, cat=null;
const d=new Date();
const dias=['domingo','lunes','martes','miércoles','jueves','viernes','sábado'];
const meses=['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
document.getElementById('hdate').textContent=dias[d.getDay()]+', '+d.getDate()+' de '+meses[d.getMonth()]+' de '+d.getFullYear();

async function loadCats(){{
  const data=await fetch('/api/categories').then(r=>r.json()).catch(()=>[]);
  const bar=document.getElementById('navbar');
  data.forEach(c=>{{
    const b=document.createElement('button');
    b.className='nbtn';
    b.textContent=c.label+' ('+c.count+')';
    b.onclick=()=>setCat(c.category,b);
    bar.appendChild(b);
  }});
}}

function setCat(c,btn){{
  cat=c; page=1;
  document.querySelectorAll('.nbtn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  load();
}}

async function load(){{
  const g=document.getElementById('grid');
  g.innerHTML='<div class="empty"><div class="spinner"></div><p>Cargando...</p></div>';
  let url='/api/articles?page='+page+'&per_page=12';
  if(cat) url+='&category='+encodeURIComponent(cat);
  const data=await fetch(url).then(r=>r.json()).catch(()=>({{articles:[]}}));
  if(!data.articles||!data.articles.length){{
    g.innerHTML='<div class="empty"><p>Sin noticias aún.</p></div>';
    document.getElementById('pag').innerHTML='';
    return;
  }}
  g.innerHTML=data.articles.map(card).join('');
  renderPag(data.page,data.pages);
}}

function card(a){{
  const img=a.has_image
    ?`<img src="/static/images/${{esc(a.id)}}.jpg" alt="" loading="lazy">`
    :`<div class="card-placeholder">🔬</div>`;
  const tags=(a.tags||[]).slice(0,2).map(t=>`<span class="tag">${{esc(t)}}</span>`).join('');
  return`<div class="card" onclick="go('/article/${{esc(a.id)}}')">
    <div class="card-img">${{img}}</div>
    <div class="card-body">
      <div class="card-cat">${{esc(a.category_label||'')}}</div>
      <div class="card-title">${{esc(a.headline)}}</div>
      <div class="card-summary">${{esc(a.summary)}}</div>
      <div class="card-meta">
        <span>${{a.published_at_fmt||''}}</span>
        <div class="card-tags">${{tags}}</div>
      </div>
    </div>
  </div>`;
}}

function renderPag(p,total){{
  const el=document.getElementById('pag');
  if(total<=1){{el.innerHTML='';return;}}
  let h='';
  if(p>1) h+=`<button class="pbtn" onclick="goPage(${{p-1}})">← Anterior</button>`;
  for(let i=Math.max(1,p-2);i<=Math.min(total,p+2);i++)
    h+=`<button class="pbtn${{i===p?' active':''}}" onclick="goPage(${{i}})">${{i}}</button>`;
  if(p<total) h+=`<button class="pbtn" onclick="goPage(${{p+1}})">Siguiente →</button>`;
  el.innerHTML=h;
}}

function goPage(n){{page=n;window.scrollTo({{top:0,behavior:'smooth'}});load();}}
function go(url){{window.location.href=url;}}
function esc(s){{return s?String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'):''}}

loadCats();
load();
</script>
</body>
</html>"""

# ── ARTICLE ───────────────────────────────────────────────────────────────────

ARTICLE = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CienciaHoy</title>
<style>{ART_CSS}</style>
</head>
<body>
<header>
  <div class="hinner">
    <a class="logo" href="/"><em>Ciencia</em>Hoy</a>
    <span class="hdate" id="hdate"></span>
  </div>
</header>
<div style="background:var(--surface);border-bottom:1px solid var(--border);">
  <div style="max-width:720px;margin:0 auto;padding:0 1.5rem;">
    <button class="back" onclick="history.back()">← Volver</button>
  </div>
</div>
<div class="art-wrap" id="art"></div>
<div class="rel" id="rel" style="display:none">
  <div class="rel-head">Más noticias</div>
  <div class="rel-grid" id="rel-grid"></div>
</div>
<script>
const AID='{{article_id}}';
const d=new Date();
const dias=['domingo','lunes','martes','miércoles','jueves','viernes','sábado'];
const meses=['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
document.getElementById('hdate').textContent=dias[d.getDay()]+', '+d.getDate()+' de '+meses[d.getMonth()]+' de '+d.getFullYear();

function esc(s){{return s?String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'):''}}

function bodyHtml(t){{
  if(!t) return '';
  return t.split('\\n').map(p=>p.trim()).filter(Boolean).map(p=>`<p>${{esc(p)}}</p>`).join('');
}}

async function load(){{
  const a=await fetch('/api/articles/'+AID).then(r=>r.json()).catch(()=>null);
  if(!a){{
    document.getElementById('art').innerHTML='<div class="empty"><p>No encontrado. <a href="/" style="color:var(--accent)">← Portada</a></p></div>';
    return;
  }}
  document.title=esc(a.headline)+' — CienciaHoy';
  const score=a.score?((a.score)*10).toFixed(1):null;
  const tags=(a.tags||[]).map(t=>`<span class="tag">${{esc(t)}}</span>`).join(' ');
  let authors='';
  try{{authors=JSON.parse(a.authors||'[]').join(', ');}}catch(e){{}}
  const img=a.has_image?`<img class="art-img" src="/static/images/${{AID}}.jpg" alt="">`:'';

  document.getElementById('art').innerHTML=`
    <div class="art-cat">${{esc(a.category_label||a.category||'')}}</div>
    <div class="art-bar"></div>
    <h1 class="art-title">${{esc(a.headline)}}</h1>
    <p class="art-summary">${{esc(a.summary)}}</p>
    <div class="art-meta">
      <span>${{a.published_at_fmt||''}}</span>
      ${{score?`<span class="art-score">Relevancia ${{score}}/10</span>`:''}}
      ${{tags}}
    </div>
    ${{img}}
    <div class="art-body">${{bodyHtml(a.body)}}</div>
    ${{a.arxiv_url?`<div class="art-source">Fuente científica: <a href="${{a.arxiv_url}}" target="_blank" rel="noopener">Ver estudio original ↗</a>${{authors?' &middot; '+esc(authors):''}}</div>`:''}}
  `;

  loadRel(a.category);
}}

async function loadRel(cat){{
  const data=await fetch('/api/articles?per_page=4&category='+encodeURIComponent(cat)).then(r=>r.json()).catch(()=>null);
  if(!data) return;
  const others=(data.articles||[]).filter(a=>a.id!==AID).slice(0,3);
  if(!others.length) return;
  document.getElementById('rel').style.display='';
  document.getElementById('rel-grid').innerHTML=others.map(a=>`
    <div class="rel-card" onclick="window.location.href='/article/${{a.id}}'">
      <div class="rel-cat">${{esc(a.category_label||'')}}</div>
      <div class="rel-title">${{esc(a.headline)}}</div>
    </div>`).join('');
}}

load();
</script>
</body>
</html>"""

# ── ROUTES ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX

@app.get("/article/{article_id}", response_class=HTMLResponse)
def article_page(article_id: str):
    all_articles = load_articles()
    found = any(a.get("id") == article_id and a.get("status") == "published" for a in all_articles)
    if not found:
        raise HTTPException(status_code=404, detail="No encontrado")
    return ARTICLE.replace("{article_id}", article_id)