"""
Science Newsroom — web.py  (Layout C: cards con imagen)
=========================================================
USO:
    pip install fastapi uvicorn aiofiles
    uvicorn web:app --reload --port 8000
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

DB_PATH    = Path(__file__).parent / "data.db"
IMAGES_DIR = Path(__file__).parent / "static" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

SITE_NAME = "CienciaHoy"
SITE_DESC = "Las últimas noticias científicas, cada día"

CAT_LABELS = {
    "cs.AI":             "Inteligencia Artificial",
    "cs.LG":             "Machine Learning",
    "physics.app-ph":    "Física Aplicada",
    "cond-mat.mtrl-sci": "Materiales",
    "eess.SY":           "Sistemas de Energía",
    "q-bio.NC":          "Neurociencia",
    "finance.markets":   "Mercados",
    "finance.crypto":    "Cripto",
    "sports.football":   "Fútbol",
    "sports.basketball": "Baloncesto",
}

app = FastAPI(title=SITE_NAME, version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

def get_db():
    if not DB_PATH.exists():
        raise HTTPException(status_code=503, detail="DB no encontrada.")
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def row_to_dict(row) -> dict:
    d = dict(row)
    if isinstance(d.get("tags"), str):
        try:    d["tags"] = json.loads(d["tags"])
        except: d["tags"] = []
    if d.get("published_at"):
        try:
            dt = datetime.fromisoformat(d["published_at"].replace("Z", "+00:00"))
            d["published_at_fmt"] = dt.strftime("%-d de %B, %Y")
        except:
            d["published_at_fmt"] = d["published_at"][:10]
    cat = d.get("category", "")
    d["category_label"] = CAT_LABELS.get(cat, cat.split(".")[-1] if "." in cat else cat)
    d["has_image"] = (IMAGES_DIR / f"{d['id']}.jpg").exists()
    return d

@app.get("/api/articles")
def list_articles(
    page:     int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=50),
    category: str = Query(None),
    tag:      str = Query(None),
):
    con    = get_db()
    offset = (page - 1) * per_page
    where  = ["a.status = 'published'"]
    params = []
    if category:
        where.append("a.category = ?"); params.append(category)
    if tag:
        where.append("a.tags LIKE ?"); params.append(f'%"{tag}"%')
    w     = " AND ".join(where)
    total = con.execute(f"SELECT COUNT(*) FROM articles a WHERE {w}", params).fetchone()[0]
    rows  = con.execute(
        f"SELECT a.*, p.arxiv_url, p.authors, p.score FROM articles a "
        f"LEFT JOIN papers p ON a.paper_id = p.id WHERE {w} ORDER BY a.published_at DESC LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()
    con.close()
    return {"total": total, "page": page, "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
            "articles": [row_to_dict(r) for r in rows]}

@app.get("/api/articles/{article_id}")
def get_article(article_id: str):
    con = get_db()
    row = con.execute(
        "SELECT a.*, p.arxiv_url, p.authors, p.score, p.abstract FROM articles a "
        "LEFT JOIN papers p ON a.paper_id = p.id WHERE a.id=? AND a.status='published'",
        (article_id,),
    ).fetchone()
    con.close()
    if not row: raise HTTPException(status_code=404, detail="No encontrado")
    return row_to_dict(row)

@app.get("/api/stats")
def get_stats():
    con = get_db()
    s   = {
        "total_articles": con.execute("SELECT COUNT(*) FROM articles WHERE status='published'").fetchone()[0],
        "total_papers":   con.execute("SELECT COUNT(*) FROM papers").fetchone()[0],
        "today_articles": con.execute("SELECT COUNT(*) FROM articles WHERE status='published' AND published_at >= date('now')").fetchone()[0],
        "categories":     [{"category": r[0], "count": r[1]} for r in con.execute(
            "SELECT category, COUNT(*) FROM articles WHERE status='published' GROUP BY category ORDER BY 2 DESC"
        ).fetchall()],
    }
    con.close()
    return s

@app.get("/api/categories")
def list_categories():
    con  = get_db()
    rows = con.execute("SELECT category, COUNT(*) as n FROM articles WHERE status='published' GROUP BY category ORDER BY n DESC").fetchall()
    con.close()
    return [{"category": r["category"], "count": r["n"], "label": CAT_LABELS.get(r["category"], r["category"])} for r in rows]

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=DM+Sans:wght@300;400;500&display=swap');
:root{--bg:#f5f4f0;--surface:#fff;--border:#e5e1d8;--text:#181714;--muted:#6b6760;--accent:#c04a1a;--radius:10px;--serif:'Playfair Display',Georgia,serif;--sans:'DM Sans',-apple-system,sans-serif;}
@media(prefers-color-scheme:dark){:root{--bg:#111009;--surface:#1a1916;--border:#2a2925;--text:#e8e4dc;--muted:#888580;--accent:#e8784a;}}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased;}
a{color:inherit;text-decoration:none;}
header{background:var(--surface);border-bottom:2px solid var(--text);position:sticky;top:0;z-index:100;}
.hinner{max-width:1200px;margin:0 auto;padding:0 1.5rem;display:flex;align-items:center;justify-content:space-between;height:56px;}
.logo{font-family:var(--serif);font-size:1.55rem;letter-spacing:-.02em;}
.logo em{color:var(--accent);font-style:normal;}
.hdate{font-size:.7rem;color:var(--muted);letter-spacing:.06em;text-transform:uppercase;}
.navbar{background:var(--surface);border-bottom:1px solid var(--border);overflow-x:auto;white-space:nowrap;}
.ninner{max-width:1200px;margin:0 auto;padding:0 1.5rem;display:flex;gap:0;}
.nbtn{font-size:.74rem;font-weight:500;letter-spacing:.04em;text-transform:uppercase;padding:9px 14px;border:none;background:none;color:var(--muted);cursor:pointer;border-bottom:2px solid transparent;transition:all .15s;flex-shrink:0;}
.nbtn:hover{color:var(--text);}
.nbtn.active{color:var(--accent);border-bottom-color:var(--accent);}
main{max-width:1200px;margin:0 auto;padding:2rem 1.5rem;}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:1.25rem;}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;cursor:pointer;transition:transform .18s,box-shadow .18s;display:flex;flex-direction:column;}
.card:hover{transform:translateY(-3px);box-shadow:0 8px 28px rgba(0,0,0,.09);}
.card-img{width:100%;aspect-ratio:16/9;background:var(--bg);overflow:hidden;position:relative;}
.card-img img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .3s;}
.card:hover .card-img img{transform:scale(1.04);}
.card-img-placeholder{width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:var(--border);font-size:2rem;color:var(--muted);}
.card-body{padding:1rem 1.1rem 1.1rem;flex:1;display:flex;flex-direction:column;}
.card-cat{font-size:.66rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-bottom:.35rem;}
.card-title{font-family:var(--serif);font-size:1rem;line-height:1.3;font-weight:700;margin-bottom:.45rem;flex:1;}
.card-summary{font-size:.8rem;color:var(--muted);line-height:1.5;margin-bottom:.65rem;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.card-meta{font-size:.68rem;color:var(--muted);display:flex;align-items:center;justify-content:space-between;}
.card-tags{display:flex;gap:.3rem;flex-wrap:wrap;}
.tag{font-size:.62rem;font-weight:600;letter-spacing:.05em;text-transform:uppercase;background:rgba(192,74,26,.08);color:var(--accent);border-radius:3px;padding:2px 6px;}
.empty{text-align:center;padding:4rem 1rem;color:var(--muted);}
.spinner{display:inline-block;width:26px;height:26px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .7s linear infinite;margin-bottom:1rem;}
@keyframes spin{to{transform:rotate(360deg);}}
.pagination{display:flex;justify-content:center;gap:.5rem;margin-top:2rem;flex-wrap:wrap;}
.pbtn{font-size:.78rem;padding:6px 14px;border-radius:6px;border:1px solid var(--border);background:var(--surface);color:var(--text);cursor:pointer;transition:all .15s;}
.pbtn:hover,.pbtn.active{background:var(--accent);border-color:var(--accent);color:#fff;}
"""

ARTICLE_CSS = CSS + """
.art-wrap{max-width:740px;margin:0 auto;padding:2rem 1.5rem 4rem;}
.back-btn{font-size:.75rem;color:var(--muted);display:inline-flex;align-items:center;gap:6px;margin-bottom:1.5rem;cursor:pointer;transition:color .15s;}
.back-btn:hover{color:var(--accent);}
.art-cat{font-size:.7rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-bottom:.6rem;}
.art-divider{width:44px;height:3px;background:var(--accent);margin:.6rem 0 1rem;}
.art-title{font-family:var(--serif);font-size:clamp(1.7rem,4vw,2.6rem);line-height:1.15;font-weight:700;letter-spacing:-.02em;margin-bottom:.9rem;}
.art-summary{font-size:1.05rem;color:var(--muted);border-left:3px solid var(--accent);padding-left:1rem;margin-bottom:1.25rem;font-style:italic;line-height:1.6;}
.art-meta{font-size:.73rem;color:var(--muted);display:flex;flex-wrap:wrap;gap:.7rem;align-items:center;padding:.9rem 0;border-top:1px solid var(--border);border-bottom:1px solid var(--border);margin-bottom:1.75rem;}
.art-score{font-weight:700;color:#059669;}
.art-img{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:8px;margin-bottom:1.75rem;display:block;}
.art-body{font-size:1rem;line-height:1.85;}
.art-body p{margin-bottom:1.2em;}
.art-source{margin-top:1.75rem;padding:.9rem 1.1rem;background:rgba(192,74,26,.06);border-radius:8px;font-size:.8rem;color:var(--muted);}
.art-source a{color:var(--accent);font-weight:600;}
.art-source a:hover{text-decoration:underline;}
.related{max-width:740px;margin:0 auto;padding:0 1.5rem 3rem;}
.rel-title{font-size:.7rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);border-bottom:1px solid var(--border);padding-bottom:.5rem;margin-bottom:1.1rem;}
.rel-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:1rem;}
.rel-card{cursor:pointer;transition:opacity .15s;}
.rel-card:hover{opacity:.7;}
.rel-cat{font-size:.65rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);margin-bottom:.2rem;}
.rel-title2{font-family:var(--serif);font-size:.9rem;font-weight:700;line-height:1.3;}
"""

INDEX_HTML = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{site_name}}</title>
<style>{CSS}</style>
</head>
<body>
<header><div class="hinner">
  <a class="logo" href="/"><em>Ciencia</em>Hoy</a>
  <span class="hdate" id="hdate"></span>
</div></header>
<div class="navbar"><div class="ninner" id="navbar">
  <button class="nbtn active" onclick="setCat(null,this)">Todo</button>
</div></div>
<main>
  <div class="grid" id="grid"></div>
  <div class="pagination" id="pagination"></div>
</main>
<script>
const API='';let page=1,cat=null;
const d=new Date();
document.getElementById('hdate').textContent=d.toLocaleDateString('es-ES',{{weekday:'long',year:'numeric',month:'long',day:'numeric'}});
async function loadCats(){{
  const cats=await fetch(API+'/api/categories').then(r=>r.json()).catch(()=>[]);
  const bar=document.getElementById('navbar');
  cats.forEach(c=>{{
    const b=document.createElement('button');
    b.className='nbtn';b.textContent=c.label+' ('+c.count+')';
    b.onclick=()=>setCat(c.category,b);bar.appendChild(b);
  }});
}}
function setCat(c,btn){{
  cat=c;page=1;
  document.querySelectorAll('.nbtn').forEach(b=>b.classList.remove('active'));
  if(btn)btn.classList.add('active');
  load();
}}
async function load(){{
  const g=document.getElementById('grid');
  g.innerHTML='<div class="empty"><div class="spinner"></div></div>';
  let url=API+'/api/articles?page='+page+'&per_page=12';
  if(cat)url+='&category='+encodeURIComponent(cat);
  try{{
    const data=await fetch(url).then(r=>r.json());
    if(!data.articles||!data.articles.length){{
      g.innerHTML='<div class="empty"><p>Sin noticias aún. Ejecuta el pipeline.</p></div>';return;
    }}
    g.innerHTML=data.articles.map(a=>card(a)).join('');
    pages(data.page,data.pages);
  }}catch(e){{g.innerHTML='<div class="empty"><p>Error: '+e.message+'</p></div>';}}
}}
function card(a){{
  const img=a.has_image
    ?'<img src="/static/images/'+esc(a.id)+'.jpg" alt="" loading="lazy">'
    :'<div class="card-img-placeholder">🔬</div>';
  const tags=(a.tags||[]).slice(0,2).map(t=>'<span class="tag">'+esc(t)+'</span>').join('');
  return`<div class="card" onclick="location='/article/'+esc('${{a.id}}')">
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
function pages(p,total){{
  const el=document.getElementById('pagination');
  if(total<=1){{el.innerHTML='';return;}}
  let h='';
  if(p>1)h+='<button class="pbtn" onclick="goPage('+(p-1)+')">← Anterior</button>';
  for(let i=Math.max(1,p-2);i<=Math.min(total,p+2);i++)
    h+='<button class="pbtn'+(i===p?' active':'')+'" onclick="goPage('+i+')">'+i+'</button>';
  if(p<total)h+='<button class="pbtn" onclick="goPage('+(p+1)+')">Siguiente →</button>';
  el.innerHTML=h;
}}
function goPage(p2){{page=p2;window.scrollTo({{top:0,behavior:'smooth'}});load();}}
function esc(s){{return s?String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'):''}}
loadCats();load();
</script>
</body></html>"""

ARTICLE_HTML = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{headline}} — {{site_name}}</title>
<style>{ARTICLE_CSS}</style>
</head>
<body>
<header><div class="hinner">
  <a class="logo" href="/"><em>Ciencia</em>Hoy</a>
  <span class="hdate" id="hdate"></span>
</div></header>
<div style="background:var(--surface);border-bottom:1px solid var(--border)">
  <div style="max-width:740px;margin:0 auto;padding:0 1.5rem;">
    <button class="nbtn active" onclick="history.back()">← Volver</button>
  </div>
</div>
<div class="art-wrap" id="art-wrap">
  <div class="empty"><div class="spinner"></div></div>
</div>
<div class="related" id="rel-wrap" style="display:none">
  <div class="rel-title">Más noticias</div>
  <div class="rel-grid" id="rel-grid"></div>
</div>
<script>
const AID='{{article_id}}';
const d=new Date();
document.getElementById('hdate').textContent=d.toLocaleDateString('es-ES',{{weekday:'long',year:'numeric',month:'long',day:'numeric'}});
function esc(s){{return s?String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'):''}}
function bodyHtml(t){{
  if(!t)return'';
  return t.split('\\n').map(p=>p.trim()).filter(p=>p).map(p=>'<p>'+esc(p)+'</p>').join('');
}}
async function loadArt(){{
  try{{
    const a=await fetch('/api/articles/'+AID).then(r=>r.json());
    document.title=esc(a.headline)+' — CienciaHoy';
    const score=a.score?(a.score*10).toFixed(1):null;
    const tags=(a.tags||[]).map(t=>'<span class="tag">'+esc(t)+'</span>').join(' ');
    let authors='';
    try{{authors=JSON.parse(a.authors||'[]').join(', ');}}catch(e){{}}
    const imgHtml=a.has_image
      ?'<img class="art-img" src="/static/images/'+AID+'.jpg" alt="">'
      :'';
    document.getElementById('art-wrap').innerHTML=`
      <div class="art-cat">${{esc(a.category_label||a.category||'')}}</div>
      <div class="art-divider"></div>
      <h1 class="art-title">${{esc(a.headline)}}</h1>
      <p class="art-summary">${{esc(a.summary)}}</p>
      <div class="art-meta">
        <span>${{a.published_at_fmt||''}}</span>
        ${{score?'<span class="art-score">Relevancia '+score+'/10</span>':''}}
        ${{tags}}
      </div>
      ${{imgHtml}}
      <div class="art-body">${{bodyHtml(a.body)}}</div>
      ${{a.arxiv_url?'<div class="art-source">Fuente: <a href="'+a.arxiv_url+'" target="_blank" rel="noopener">Ver paper original ↗</a>'+(authors?' · '+esc(authors):'')+'</div>':''}}
    `;
    loadRel(a.category);
  }}catch(e){{
    document.getElementById('art-wrap').innerHTML='<div class="empty"><p>Error cargando artículo. <a href="/" style="color:var(--accent)">← Portada</a></p></div>';
  }}
}}
async function loadRel(cat){{
  try{{
    const data=await fetch('/api/articles?per_page=4&category='+encodeURIComponent(cat)).then(r=>r.json());
    const others=(data.articles||[]).filter(a=>a.id!==AID).slice(0,3);
    if(!others.length)return;
    document.getElementById('rel-wrap').style.display='';
    document.getElementById('rel-grid').innerHTML=others.map(a=>`
      <div class="rel-card" onclick="location='/article/'+esc('${{a.id}}')">
        <div class="rel-cat">${{esc(a.category_label||'')}}</div>
        <div class="rel-title2">${{esc(a.headline)}}</div>
      </div>`).join('');
  }}catch(e){{}}
}}
loadArt();
</script>
</body></html>"""

@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX_HTML.format(site_name=SITE_NAME, site_desc=SITE_DESC)

@app.get("/article/{article_id}", response_class=HTMLResponse)
def article_page(article_id: str):
    con = get_db()
    row = con.execute("SELECT headline, summary FROM articles WHERE id=? AND status='published'", (article_id,)).fetchone()
    con.close()
    if not row: raise HTTPException(status_code=404, detail="No encontrado")
    return ARTICLE_HTML.format(
        site_name=SITE_NAME,
        article_id=article_id,
        headline=row["headline"].replace('"','&quot;'),
        summary=(row["summary"] or "").replace('"','&quot;'),
    )

@app.get("/health")
def health():
    return {"status": "ok", "db": DB_PATH.exists()}
