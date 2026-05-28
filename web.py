"""
CienciaHoy — web.py
Layout estilo portal MSN · header original · footer crema
Colores: fondo #f5f4f0, acento #c04a1a, tipografia Playfair + DM Sans
"""

import json
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

ARTICLES_PATH = Path(__file__).parent / "articles.json"
IMAGES_DIR    = Path(__file__).parent / "static" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

try:
    from newsletter import add_subscriber, remove_subscriber
    NEWSLETTER_OK = True
except ImportError:
    NEWSLETTER_OK = False

CAT_LABELS = {
    "cs.AI":             "Tecnología",
    "cs.LG":             "Tecnología",
    "cs.RO":             "Tecnología",
    "eess.SY":           "Tecnología",
    "physics.app-ph":    "Ciencia",
    "cond-mat.mtrl-sci": "Ciencia",
    "q-bio.NC":          "Salud",
    "science.general":   "Ciencia",
    "science.life":      "Salud",
    "science.astronomy": "Ciencia",
    "health":            "Salud",
    "technology":        "Tecnología",
}

CAT_COLORS = {
    "Tecnología": "#1a6bcc",
    "Ciencia":    "#c04a1a",
    "Salud":      "#7b2d8b",
}

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET","POST"], allow_headers=["*"])
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
    cat   = d.get("category", "")
    label = CAT_LABELS.get(cat, cat.split(".")[-1] if "." in cat else cat)
    d["category_label"] = label
    d["category_color"]  = CAT_COLORS.get(label, "#c04a1a")
    d["has_image"] = (IMAGES_DIR / f"{d['id']}.jpg").exists()
    # fuente: preferir source_url, caer en arxiv_url
    d["source_url"] = d.get("source_url") or d.get("arxiv_url") or ""
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
        all_articles = [a for a in all_articles if a.get("category_label") == category]
    total  = len(all_articles)
    offset = (page - 1) * per_page
    return {
        "total":    total,
        "page":     page,
        "pages":    max(1, (total + per_page - 1) // per_page),
        "articles": all_articles[offset:offset + per_page],
    }


@app.get("/api/articles/{article_id}")
def get_article(article_id: str):
    for a in load_articles():
        if a.get("id") == article_id and a.get("status") == "published":
            return enrich(a)
    raise HTTPException(status_code=404, detail="No encontrado")


@app.get("/api/categories")
def list_categories():
    all_articles = [enrich(a) for a in load_articles() if a.get("status") == "published"]
    counts: dict = {}
    for a in all_articles:
        lbl = a.get("category_label", "")
        counts[lbl] = counts.get(lbl, 0) + 1
    return [
        {"category": lbl, "count": n, "label": lbl, "color": CAT_COLORS.get(lbl, "#c04a1a")}
        for lbl, n in sorted(counts.items(), key=lambda x: -x[1])
    ]


@app.post("/subscribe")
async def subscribe(request: Request):
    if not NEWSLETTER_OK:
        return JSONResponse({"ok": False, "reason": "newsletter_no_disponible"}, status_code=503)
    try:
        body  = await request.json()
        email = body.get("email", "")
    except Exception:
        return JSONResponse({"ok": False, "reason": "json_invalido"}, status_code=400)
    result = add_subscriber(email)
    return JSONResponse(result, status_code=200 if result["ok"] else 400)


@app.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe_page(email: str = Query("")):
    if email and NEWSLETTER_OK:
        remove_subscriber(email)
        msg = f"El email <strong>{email}</strong> ha sido dado de baja correctamente."
    else:
        msg = "No se pudo procesar la baja en este momento."
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<title>Baja newsletter · CienciaHoy</title>
<style>body{{font-family:sans-serif;background:#f5f4f0;display:flex;align-items:center;
justify-content:center;min-height:100vh;margin:0;}}
.box{{background:#fff;border-radius:8px;padding:2.5rem 3rem;max-width:480px;
border:1px solid #e5e1d8;text-align:center;}}
.logo{{font-family:Georgia,serif;font-size:1.6rem;font-weight:700;color:#1a1816;margin-bottom:1rem;}}
.logo em{{color:#c04a1a;font-style:normal;}}
p{{color:#6b6760;line-height:1.6;}} a{{color:#c04a1a;font-weight:600;}}
</style></head><body><div class="box">
<div class="logo"><em>Ciencia</em>Hoy</div>
<p>{msg}</p>
<p style="margin-top:1.2rem;"><a href="/">Volver a la portada</a></p>
</div></body></html>"""


@app.get("/health")
def health():
    return {"status": "ok", "articles_file": ARTICLES_PATH.exists(), "count": len(load_articles())}


@app.get("/debug")
def debug():
    import os
    base = Path(__file__).parent
    return {"cwd": str(base), "articles_exists": ARTICLES_PATH.exists(), "files": os.listdir(base)}


# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=DM+Sans:wght@300;400;500;600&display=swap');
:root{
  --bg:#f5f4f0;
  --surface:#ffffff;
  --border:#e5e1d8;
  --border-light:#ede9e0;
  --text:#1a1816;
  --muted:#6b6760;
  --light-muted:#9c9890;
  --accent:#c04a1a;
  --accent-hover:#a03a12;
  --cat-sci:#c04a1a;
  --cat-tec:#1a6bcc;
  --cat-sal:#7b2d8b;
  --radius:8px;
  --serif:'Playfair Display',Georgia,serif;
  --sans:'DM Sans',-apple-system,sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased;}
a{color:inherit;text-decoration:none;}
img{display:block;width:100%;height:100%;object-fit:cover;}

/* ── HEADER — original, no tocar ── */
header{background:var(--surface);border-bottom:2px solid var(--text);position:sticky;top:0;z-index:100;}
.hinner{max-width:1280px;margin:0 auto;padding:0 1.5rem;display:flex;align-items:center;justify-content:space-between;height:58px;}
.logo{font-family:var(--serif);font-size:1.6rem;font-weight:900;letter-spacing:-.02em;}
.logo em{color:var(--accent);font-style:normal;}
.hdate{font-size:.68rem;color:var(--muted);letter-spacing:.07em;text-transform:uppercase;}

/* ── NAVBAR ── */
.navbar{background:var(--surface);border-bottom:1px solid var(--border);overflow-x:auto;white-space:nowrap;scrollbar-width:none;}
.navbar::-webkit-scrollbar{display:none;}
.ninner{max-width:1280px;margin:0 auto;padding:0 1.5rem;display:flex;}
.nbtn{font-size:.7rem;font-weight:600;letter-spacing:.05em;text-transform:uppercase;padding:10px 16px;border:none;background:none;color:var(--muted);cursor:pointer;border-bottom:2px solid transparent;transition:all .15s;flex-shrink:0;font-family:var(--sans);}
.nbtn:hover{color:var(--text);}
.nbtn.active{color:var(--accent);border-bottom-color:var(--accent);}
.nbtn-dot{display:inline-block;width:5px;height:5px;border-radius:50%;margin-right:6px;vertical-align:middle;}

/* ── MAIN ── */
main{max-width:1280px;margin:0 auto;padding:1.8rem 1.5rem 3rem;}

/* ── SECTION HEAD ── */
.sec-head{display:flex;align-items:center;gap:.8rem;margin-bottom:.8rem;}
.sec-title{font-size:.68rem;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);white-space:nowrap;}
.sec-line{flex:1;height:1px;background:var(--border);}

/* ── HERO BLOCK ── */
.hero-block{display:grid;grid-template-columns:1.85fr 1fr;gap:1rem;margin-bottom:1.8rem;}
@media(max-width:768px){.hero-block{grid-template-columns:1fr;}}

.hero-main{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;cursor:pointer;transition:box-shadow .2s;}
.hero-main:hover{box-shadow:0 8px 28px rgba(0,0,0,.09);}
.hero-main-img{aspect-ratio:16/8;overflow:hidden;background:var(--border);}
.hero-main-img img{transition:transform .5s;}
.hero-main:hover .hero-main-img img{transform:scale(1.04);}
.hero-main-body{padding:1rem 1.2rem 1.2rem;}
.hero-cat{font-size:.65rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;margin-bottom:.5rem;}
.hero-title{font-family:var(--serif);font-size:1.55rem;line-height:1.18;font-weight:700;margin-bottom:.6rem;color:var(--text);}
.hero-sum{font-size:.88rem;color:var(--muted);line-height:1.6;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;}
.hero-meta{font-size:.68rem;color:var(--light-muted);margin-top:.6rem;}

/* ── SIDE STACK ── */
.hero-side{display:flex;flex-direction:column;gap:.75rem;}

.side-card{display:flex;gap:.75rem;cursor:pointer;padding:.75rem;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);transition:border-color .2s,box-shadow .2s;}
.side-card:hover{border-color:var(--accent);box-shadow:0 4px 14px rgba(0,0,0,.07);}
.side-card-img{width:76px;height:62px;flex-shrink:0;overflow:hidden;border-radius:5px;background:var(--border);}
.side-card-body{flex:1;display:flex;flex-direction:column;gap:.2rem;}
.side-card-cat{font-size:.6rem;font-weight:700;letter-spacing:.09em;text-transform:uppercase;}
.side-card-title{font-family:var(--serif);font-size:.88rem;line-height:1.25;font-weight:700;color:var(--text);}
.side-card-meta{font-size:.63rem;color:var(--light-muted);margin-top:auto;}

/* ad mini en side */
.ad-mini{border:1px dashed var(--border);border-radius:var(--radius);flex:1;min-height:62px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;background:#faf9f6;padding:.8rem;text-align:center;cursor:pointer;transition:border-color .15s;}
.ad-mini:hover{border-color:var(--accent);}
.ad-mini-icon{font-size:1.2rem;}
.ad-mini-text{font-size:.65rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--light-muted);}
.ad-mini-sub{font-size:.6rem;color:var(--border);margin-top:1px;}

/* ── THREE COLUMNS ── */
.three-col{display:grid;grid-template-columns:repeat(3,1fr);gap:.9rem;margin-bottom:1.5rem;}
@media(max-width:860px){.three-col{grid-template-columns:repeat(2,1fr);}}
@media(max-width:540px){.three-col{grid-template-columns:1fr;}}

/* ── STANDARD CARD ── */
.card{cursor:pointer;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;display:flex;flex-direction:column;transition:transform .2s,box-shadow .2s,border-color .2s;}
.card:hover{transform:translateY(-3px);box-shadow:0 8px 24px rgba(0,0,0,.09);border-color:#d4cfc6;}
.card-img{aspect-ratio:16/9;overflow:hidden;background:var(--border);flex-shrink:0;}
.card-img img{transition:transform .4s;}
.card:hover .card-img img{transform:scale(1.05);}
.card-ph{width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:2rem;background:var(--bg);}
.card-body{padding:.85rem 1rem 1rem;flex:1;display:flex;flex-direction:column;gap:.28rem;}
.card-cat{font-size:.62rem;font-weight:700;letter-spacing:.09em;text-transform:uppercase;}
.card-title{font-family:var(--serif);font-size:.96rem;line-height:1.25;font-weight:700;flex:1;color:var(--text);}
.card-summary{font-size:.76rem;color:var(--muted);line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.card-meta{font-size:.63rem;color:var(--light-muted);margin-top:.3rem;}

/* ── BANNER NEWSLETTER ── */
.banner-nl{background:var(--accent);border-radius:var(--radius);padding:.9rem 1.3rem;display:flex;align-items:center;justify-content:space-between;gap:1rem;margin-bottom:1.5rem;}
@media(max-width:600px){.banner-nl{flex-direction:column;text-align:center;}}
.bn-label{font-size:.62rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:rgba(255,255,255,.55);margin-bottom:.2rem;}
.bn-title{font-size:.98rem;font-weight:700;color:#fff;line-height:1.25;}
.bn-sub{font-size:.75rem;color:rgba(255,255,255,.55);margin-top:.15rem;}
.bn-form{display:flex;gap:.4rem;flex-shrink:0;}
@media(max-width:600px){.bn-form{width:100%;}}
.bn-input{background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.3);border-radius:5px;padding:7px 12px;font-size:.78rem;color:#fff;font-family:var(--sans);outline:none;width:180px;}
.bn-input::placeholder{color:rgba(255,255,255,.5);}
.bn-input:focus{border-color:rgba(255,255,255,.7);}
.bn-btn{background:#fff;border:none;border-radius:5px;padding:7px 14px;font-size:.72rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--accent);cursor:pointer;white-space:nowrap;font-family:var(--sans);transition:opacity .15s;}
.bn-btn:hover{opacity:.88;}

/* ── TWO COL + SIDEBAR ── */
.two-col-layout{display:grid;grid-template-columns:1fr 280px;gap:1rem;margin-bottom:1.5rem;}
@media(max-width:860px){.two-col-layout{grid-template-columns:1fr;}}
.two-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:.9rem;}
@media(max-width:540px){.two-grid{grid-template-columns:1fr;}}

/* ── SIDEBAR ── */
.sidebar{}
.sidebox{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:.9rem 1rem;margin-bottom:.75rem;}
.side-box-title{font-size:.68rem;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--text);border-bottom:2px solid var(--text);padding-bottom:.4rem;margin-bottom:.75rem;}
.list-item{display:flex;gap:.5rem;padding:.45rem 0;border-bottom:1px solid var(--border-light);align-items:flex-start;}
.list-item:last-child{border-bottom:none;}
.list-num{font-family:var(--serif);font-size:1.25rem;font-weight:700;color:var(--border);line-height:1;width:22px;flex-shrink:0;}
.list-cat{font-size:.58rem;font-weight:700;letter-spacing:.09em;text-transform:uppercase;margin-bottom:.15rem;}
.list-title{font-family:var(--serif);font-size:.82rem;font-weight:700;line-height:1.28;color:var(--text);}
.list-card{cursor:pointer;transition:opacity .15s;}
.list-card:hover{opacity:.7;}

.ad-sq{border:1px dashed var(--border);border-radius:var(--radius);min-height:200px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:.3rem;background:#faf9f6;padding:1rem;text-align:center;cursor:pointer;transition:border-color .15s;}
.ad-sq:hover{border-color:var(--accent);}
.ad-sq-icon{font-size:1.5rem;margin-bottom:.2rem;}
.ad-sq-title{font-size:.72rem;font-weight:700;color:var(--text);}
.ad-sq-sub{font-size:.65rem;color:var(--light-muted);line-height:1.5;}
.ad-sq-cta{margin-top:.5rem;font-size:.65rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--accent);}

/* ── BANNER AD ── */
.banner-ad{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:.9rem 1.3rem;display:flex;align-items:center;justify-content:space-between;gap:1rem;margin-bottom:.5rem;}
@media(max-width:600px){.banner-ad{flex-direction:column;}}
.ba-label{font-size:.6rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--light-muted);margin-bottom:.2rem;}
.ba-title{font-size:.95rem;font-weight:700;color:var(--text);}
.ba-sub{font-size:.75rem;color:var(--muted);margin-top:.1rem;}
.ba-btn{background:var(--text);border:none;border-radius:5px;padding:7px 16px;font-size:.72rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--surface);cursor:pointer;white-space:nowrap;font-family:var(--sans);transition:opacity .15s;flex-shrink:0;}
.ba-btn:hover{opacity:.8;}

/* ── SPINNER / EMPTY ── */
.empty{text-align:center;padding:4rem 1rem;color:var(--muted);display:flex;flex-direction:column;align-items:center;gap:.8rem;}
.spinner{width:26px;height:26px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .7s linear infinite;}
@keyframes spin{to{transform:rotate(360deg);}}

/* ── PAGINATION ── */
.pagination{display:flex;justify-content:center;gap:.4rem;margin-top:2rem;flex-wrap:wrap;}
.pbtn{font-size:.75rem;padding:6px 14px;border-radius:5px;border:1px solid var(--border);background:var(--surface);color:var(--text);cursor:pointer;transition:all .15s;font-family:var(--sans);}
.pbtn:hover,.pbtn.active{background:var(--accent);border-color:var(--accent);color:#fff;}

/* ── FOOTER CREMA ── */
footer{background:#eee9e0;border-top:2px solid var(--text);margin-top:2rem;}
.footer-inner{max-width:1280px;margin:0 auto;padding:2.2rem 1.5rem 0;}
.footer-grid{display:grid;grid-template-columns:1.8fr 1fr 1fr 1.4fr;gap:2rem;padding-bottom:2rem;border-bottom:1px solid #d8d3c8;}
@media(max-width:860px){.footer-grid{grid-template-columns:1fr 1fr;}}
@media(max-width:520px){.footer-grid{grid-template-columns:1fr;}}
.footer-brand .logo{font-size:1.5rem;}
.footer-brand p{font-size:.8rem;color:var(--muted);line-height:1.7;margin-top:.7rem;max-width:220px;}
.footer-col h4{font-size:.64rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--light-muted);margin-bottom:.9rem;}
.footer-col ul{list-style:none;display:flex;flex-direction:column;gap:.5rem;}
.footer-col ul li a,.footer-col ul li span{font-size:.82rem;color:var(--muted);cursor:pointer;transition:color .15s;}
.footer-col ul li a:hover,.footer-col ul li span:hover{color:var(--accent);}
.footer-nl{background:var(--surface);border:1px solid #d8d3c8;border-radius:var(--radius);padding:1.1rem;}
.footer-nl h4{font-size:.64rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);margin-bottom:.5rem;}
.footer-nl p{font-size:.78rem;color:var(--muted);line-height:1.6;margin-bottom:.8rem;}
.footer-nl-form{display:flex;flex-direction:column;gap:.4rem;}
.footer-nl-input{background:var(--bg);border:1px solid #d8d3c8;border-radius:4px;padding:7px 10px;font-size:.8rem;color:var(--text);font-family:var(--sans);outline:none;transition:border-color .15s;}
.footer-nl-input:focus{border-color:var(--accent);}
.footer-nl-btn{background:var(--accent);border:none;border-radius:4px;padding:7px 10px;font-size:.72rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:#fff;cursor:pointer;font-family:var(--sans);transition:background .15s;}
.footer-nl-btn:hover{background:var(--accent-hover);}
.footer-bottom{padding:1rem 0;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.5rem;}
.footer-legal{display:flex;gap:1.2rem;flex-wrap:wrap;}
.footer-legal a{font-size:.68rem;color:var(--light-muted);transition:color .15s;}
.footer-legal a:hover{color:var(--accent);}
.footer-copy{font-size:.68rem;color:#b0aba2;}
"""

ART_EXTRA = """
.art-wrap{max-width:760px;margin:0 auto;padding:2rem 1.5rem 4rem;}
.back-bar{background:var(--surface);border-bottom:1px solid var(--border);}
.back-bar-inner{max-width:760px;margin:0 auto;padding:.5rem 1.5rem;}
.back{font-size:.72rem;color:var(--muted);display:inline-flex;align-items:center;gap:5px;cursor:pointer;transition:color .15s;background:none;border:none;font-family:var(--sans);}
.back:hover{color:var(--text);}
.art-breadcrumb{font-size:.68rem;color:var(--muted);margin-bottom:1.4rem;display:flex;align-items:center;gap:.4rem;}
.art-breadcrumb a{color:var(--muted);transition:color .15s;}
.art-breadcrumb a:hover{color:var(--accent);}
.art-cat{font-size:.65rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;margin-bottom:.5rem;}
.art-bar{width:36px;height:3px;background:var(--accent);margin:.5rem 0 1.1rem;}
.art-title{font-family:var(--serif);font-size:clamp(1.7rem,4vw,2.5rem);line-height:1.12;font-weight:900;letter-spacing:-.02em;margin-bottom:.9rem;}
.art-summary{font-size:1.05rem;color:var(--muted);border-left:3px solid var(--accent);padding-left:1rem;margin-bottom:1.4rem;font-style:italic;line-height:1.7;}
.art-meta{font-size:.7rem;color:var(--muted);display:flex;flex-wrap:wrap;gap:.8rem;align-items:center;padding:.9rem 0;border-top:1px solid var(--border);border-bottom:1px solid var(--border);margin-bottom:1.8rem;}
.art-score{font-weight:700;color:#059669;}
.art-img{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:var(--radius);margin-bottom:1.8rem;display:block;}
.art-body{font-size:1rem;line-height:1.9;color:var(--text);}
.art-body p{margin-bottom:1.3em;}
.tag{font-size:.6rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;background:rgba(192,74,26,.1);color:var(--accent);border-radius:4px;padding:2px 7px;}

/* fuente al pie del articulo */
.art-source{margin-top:2.5rem;padding:1rem 1.2rem;background:rgba(192,74,26,.05);border-radius:var(--radius);border-left:3px solid var(--accent);}
.art-source-label{font-size:.6rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-bottom:.35rem;}
.art-source a{font-size:.88rem;color:var(--text);font-weight:600;word-break:break-all;text-decoration:underline;text-decoration-color:rgba(192,74,26,.3);}
.art-source a:hover{color:var(--accent);}
.art-source-authors{font-size:.75rem;color:var(--muted);margin-top:.3rem;}

.rel-section{max-width:760px;margin:0 auto;padding:0 1.5rem 4rem;}
.rel-head{font-size:.68rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);border-bottom:1px solid var(--border);padding-bottom:.5rem;margin-bottom:1rem;}
.rel-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:.9rem;}
.rel-card{cursor:pointer;padding:.8rem;border:1px solid var(--border);border-radius:var(--radius);transition:border-color .15s,transform .15s;background:var(--surface);}
.rel-card:hover{border-color:var(--accent);transform:translateY(-2px);}
.rel-cat{font-size:.6rem;font-weight:700;letter-spacing:.09em;text-transform:uppercase;margin-bottom:.25rem;}
.rel-title{font-family:var(--serif);font-size:.9rem;font-weight:700;line-height:1.28;color:var(--text);}
"""

JS_COMMON = """
function esc(s){return s?String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'):''}
function go(url){window.location.href=url;}
function setDate(id){
  const d=new Date();
  const dias=['domingo','lunes','martes','mi\\u00e9rcoles','jueves','viernes','s\\u00e1bado'];
  const meses=['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
  const el=document.getElementById(id);
  if(el) el.textContent=dias[d.getDay()]+', '+d.getDate()+' de '+meses[d.getMonth()]+' de '+d.getFullYear();
}
async function nlSubscribe(inputId, btnId){
  const inp=document.getElementById(inputId), btn=document.getElementById(btnId);
  if(!inp||!btn) return;
  const email=inp.value.trim();
  if(!email){inp.focus();return;}
  btn.disabled=true; btn.textContent='Enviando...';
  try{
    const r=await fetch('/subscribe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})});
    const d=await r.json();
    if(d.ok){inp.value='';btn.textContent='\\u2713 Suscrito';btn.style.background='#059669';}
    else{btn.textContent='Email no v\\u00e1lido';setTimeout(()=>{btn.disabled=false;btn.textContent='Suscribirme \\u2192';btn.style.background='';},2500);}
  }catch(e){btn.textContent='Error';setTimeout(()=>{btn.disabled=false;btn.textContent='Suscribirme \\u2192';},2500);}
}
"""

FOOTER_HTML = """
<footer>
  <div class="footer-inner">
    <div class="footer-grid">
      <div class="footer-brand">
        <a class="logo" href="/"><em>Ciencia</em>Hoy</a>
        <p>Periodismo cient&iacute;fico independiente. Traducimos la investigaci&oacute;n acad&eacute;mica m&aacute;s relevante al lenguaje de todos los d&iacute;as.</p>
      </div>
      <div class="footer-col">
        <h4>El medio</h4>
        <ul>
          <li><span>Qui&eacute;nes somos</span></li>
          <li><span>Metodolog&iacute;a</span></li>
          <li><span>Fuentes</span></li>
          <li><span>Colabora</span></li>
        </ul>
      </div>
      <div class="footer-col">
        <h4>Contacto</h4>
        <ul>
          <li><a href="mailto:hola@cienciahoy.es">hola@cienciahoy.es</a></li>
          <li><a href="mailto:publicidad@cienciahoy.es">publicidad@cienciahoy.es</a></li>
          <li><span>Twitter / X</span></li>
          <li><span>LinkedIn</span></li>
        </ul>
      </div>
      <div class="footer-col">
        <div class="footer-nl">
          <h4>Newsletter semanal</h4>
          <p>Los descubrimientos de la semana, cada lunes en tu bandeja.</p>
          <div class="footer-nl-form">
            <input class="footer-nl-input" id="footer-nl-inp" type="email" placeholder="tu@email.com">
            <button class="footer-nl-btn" id="footer-nl-btn"
              onclick="nlSubscribe('footer-nl-inp','footer-nl-btn')">Suscribirme &rarr;</button>
          </div>
        </div>
      </div>
    </div>
    <div class="footer-bottom">
      <div class="footer-legal">
        <a href="#">Aviso legal</a>
        <a href="#">Privacidad</a>
        <a href="#">Cookies</a>
        <a href="#">Publicidad</a>
      </div>
      <div class="footer-copy">&copy; 2025 CienciaHoy &middot; Todos los derechos reservados</div>
    </div>
  </div>
</footer>
"""

HEADER_HTML = """
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
"""

# ── INDEX PAGE ────────────────────────────────────────────────────────────────

INDEX = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CienciaHoy &mdash; Periodismo cient&iacute;fico</title>
<meta name="description" content="Las &uacute;ltimas noticias de ciencia, tecnolog&iacute;a y salud explicadas con claridad.">
<style>{CSS}</style>
</head>
<body>
{HEADER_HTML}
<main id="main">
  <div id="content-area"><div class="empty"><div class="spinner"></div></div></div>
  <div class="pagination" id="pag"></div>
</main>
{FOOTER_HTML}
<script>
{JS_COMMON}
setDate('hdate');
let page=1, currentCat=null;

async function loadCats(){{
  const data=await fetch('/api/categories').then(r=>r.json()).catch(()=>[]);
  const bar=document.getElementById('navbar');
  data.forEach(c=>{{
    const b=document.createElement('button');
    b.className='nbtn';
    b.innerHTML=`<span class="nbtn-dot" style="background:${{esc(c.color)}}"></span>${{esc(c.label)}}`;
    b.onclick=()=>setCat(c.category,b);
    bar.appendChild(b);
  }});
}}

function setCat(c,btn){{
  currentCat=c; page=1;
  document.querySelectorAll('.nbtn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  load();
}}

async function load(){{
  const area=document.getElementById('content-area');
  area.innerHTML='<div class="empty"><div class="spinner"></div></div>';
  let url='/api/articles?page='+page+'&per_page=12';
  if(currentCat) url+='&category='+encodeURIComponent(currentCat);
  const data=await fetch(url).then(r=>r.json()).catch(()=>({{articles:[]}}));
  const arts=data.articles||[];
  if(!arts.length){{area.innerHTML='<div class="empty"><p>Sin noticias a&uacute;n.</p></div>';document.getElementById('pag').innerHTML='';return;}}
  area.innerHTML=renderLayout(arts);
  renderPag(data.page,data.pages||1);
}}

function catColor(a){{return esc(a.category_color||'#c04a1a');}}

function heroCard(a){{
  const img=a.has_image?`<img src="/static/images/${{esc(a.id)}}.jpg" alt="" loading="lazy">`:`<div class="card-ph">&#x1F52C;</div>`;
  return`<div class="hero-main" onclick="go('/article/${{esc(a.id)}}')">
    <div class="hero-main-img">${{img}}</div>
    <div class="hero-main-body">
      <div class="hero-cat" style="color:${{catColor(a)}}">${{esc(a.category_label||'')}}</div>
      <div class="hero-title">${{esc(a.headline)}}</div>
      <div class="hero-sum">${{esc(a.summary)}}</div>
      <div class="hero-meta">${{esc(a.published_at_fmt||'')}}</div>
    </div>
  </div>`;
}}

function sideCard(a){{
  const img=a.has_image?`<img src="/static/images/${{esc(a.id)}}.jpg" alt="" loading="lazy">`:`<div class="card-ph" style="font-size:1rem">&#x1F52C;</div>`;
  return`<div class="side-card" onclick="go('/article/${{esc(a.id)}}')">
    <div class="side-card-img">${{img}}</div>
    <div class="side-card-body">
      <div class="side-card-cat" style="color:${{catColor(a)}}">${{esc(a.category_label||'')}}</div>
      <div class="side-card-title">${{esc(a.headline)}}</div>
      <div class="side-card-meta">${{esc(a.published_at_fmt||'')}}</div>
    </div>
  </div>`;
}}

function stdCard(a){{
  const img=a.has_image?`<img src="/static/images/${{esc(a.id)}}.jpg" alt="" loading="lazy">`:`<div class="card-ph">&#x1F52C;</div>`;
  return`<div class="card" onclick="go('/article/${{esc(a.id)}}')">
    <div class="card-img">${{img}}</div>
    <div class="card-body">
      <div class="card-cat" style="color:${{catColor(a)}}">${{esc(a.category_label||'')}}</div>
      <div class="card-title">${{esc(a.headline)}}</div>
      <div class="card-summary">${{esc(a.summary)}}</div>
      <div class="card-meta">${{esc(a.published_at_fmt||'')}}</div>
    </div>
  </div>`;
}}

function listCard(a,n){{
  return`<div class="list-card list-item" onclick="go('/article/${{esc(a.id)}}')">
    <div class="list-num">${{n}}</div>
    <div>
      <div class="list-cat" style="color:${{catColor(a)}}">${{esc(a.category_label||'')}}</div>
      <div class="list-title">${{esc(a.headline)}}</div>
    </div>
  </div>`;
}}

function renderLayout(arts){{
  let h='';

  // ── HERO (art 0 + sides 1-2) ──
  if(arts.length>0){{
    h+=`<div class="sec-head"><span class="sec-title">Destacado</span><span class="sec-line"></span></div>`;
    h+=`<div class="hero-block">`;
    h+=heroCard(arts[0]);
    h+=`<div class="hero-side">`;
    if(arts[1]) h+=sideCard(arts[1]);
    if(arts[2]) h+=sideCard(arts[2]);
    h+=`<div class="ad-mini">
      <div class="ad-mini-icon">&#x1F4E2;</div>
      <div class="ad-mini-text">Anunc&iacute;ate en CienciaHoy</div>
      <div class="ad-mini-sub">publicidad@cienciahoy.es</div>
    </div>`;
    h+=`</div></div>`;
  }}

  // ── TRES CARDS (arts 3-5) ──
  const three=arts.slice(3,6);
  if(three.length){{
    h+=`<div class="sec-head" style="margin-top:1.4rem"><span class="sec-title">&Uacute;ltimas noticias</span><span class="sec-line"></span></div>`;
    h+=`<div class="three-col">`+three.map(stdCard).join('')+`</div>`;
  }}

  // ── BANNER NEWSLETTER ──
  h+=`<div class="banner-nl">
    <div>
      <div class="bn-label">Newsletter gratuito</div>
      <div class="bn-title">Ciencia de la semana, cada lunes en tu correo</div>
      <div class="bn-sub">Un&eacute;te a los lectores de CienciaHoy</div>
    </div>
    <div class="bn-form">
      <input class="bn-input" id="bnl-inp" type="email" placeholder="tu@email.com">
      <button class="bn-btn" id="bnl-btn" onclick="nlSubscribe('bnl-inp','bnl-btn')">Suscribirme &rarr;</button>
    </div>
  </div>`;

  // ── DOS COL + SIDEBAR (arts 6-9 + 10-11 en sidebar) ──
  const colArts=arts.slice(6,10);
  const sideArts=arts.slice(10,13);
  if(colArts.length){{
    h+=`<div class="sec-head"><span class="sec-title">M&aacute;s ciencia</span><span class="sec-line"></span></div>`;
    h+=`<div class="two-col-layout">`;
    h+=`<div class="two-grid">`+colArts.map(stdCard).join('')+`</div>`;
    h+=`<div class="sidebar">`;
    if(sideArts.length){{
      h+=`<div class="sidebox"><div class="side-box-title">Lo m&aacute;s le&iacute;do</div>`;
      sideArts.forEach((a,i)=>{{h+=listCard(a,String(i+1).padStart(2,'0'));}});
      h+=`</div>`;
    }}
    h+=`<div class="ad-sq">
      <div class="ad-sq-icon">&#x1F4CA;</div>
      <div class="ad-sq-title">Espacio publicitario</div>
      <div class="ad-sq-sub">Llega a lectores<br>apasionados por la ciencia</div>
      <div class="ad-sq-cta">Contactar &rarr;</div>
    </div>`;
    h+=`</div></div>`;
  }}

  // ── BANNER AD ──
  h+=`<div class="banner-ad">
    <div>
      <div class="ba-label">Publicidad &middot; Banner disponible</div>
      <div class="ba-title">&iquest;Tu marca frente a lectores apasionados por la ciencia?</div>
      <div class="ba-sub">Audiencia cualificada &middot; publicidad@cienciahoy.es</div>
    </div>
    <button class="ba-btn">An&uacute;nciate &rarr;</button>
  </div>`;

  return h;
}}

function renderPag(p,total){{
  const el=document.getElementById('pag');
  if(total<=1){{el.innerHTML='';return;}}
  let h='';
  if(p>1) h+=`<button class="pbtn" onclick="goPage(${{p-1}})">&larr; Anterior</button>`;
  for(let i=Math.max(1,p-2);i<=Math.min(total,p+2);i++)
    h+=`<button class="pbtn${{i===p?' active':''}}" onclick="goPage(${{i}})">${{i}}</button>`;
  if(p<total) h+=`<button class="pbtn" onclick="goPage(${{p+1}})">Siguiente &rarr;</button>`;
  el.innerHTML=h;
}}

function goPage(n){{page=n;window.scrollTo({{top:0,behavior:'smooth'}});load();}}

loadCats();
load();
</script>
</body>
</html>"""

# ── ARTICLE PAGE ──────────────────────────────────────────────────────────────

ARTICLE = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CienciaHoy</title>
<style>{CSS}{ART_EXTRA}</style>
</head>
<body>
{HEADER_HTML}
<div class="back-bar">
  <div class="back-bar-inner">
    <button class="back" onclick="history.back()">&larr; Volver a portada</button>
  </div>
</div>
<div class="art-wrap" id="art">
  <div class="empty"><div class="spinner"></div></div>
</div>
<div class="rel-section" id="rel" style="display:none">
  <div class="rel-head">M&aacute;s noticias</div>
  <div class="rel-grid" id="rel-grid"></div>
</div>
{FOOTER_HTML}
<script>
{JS_COMMON}
setDate('hdate');
const AID='{{article_id}}';

// navbar en articulo: solo portada
(function(){{
  const bar=document.getElementById('navbar');
  const b=document.createElement('a');
  b.href='/';b.className='nbtn active';b.textContent='Portada';
  bar.appendChild(b);
}})();

function bodyHtml(t){{
  if(!t) return '';
  return t.split('\\n').map(p=>p.trim()).filter(Boolean).map(p=>`<p>${{esc(p)}}</p>`).join('');
}}

async function load(){{
  const wrap=document.getElementById('art');
  const a=await fetch('/api/articles/'+AID).then(r=>r.json()).catch(()=>null);
  if(!a){{
    wrap.innerHTML='<div class="empty"><p>No encontrado. <a href="/" style="color:var(--accent)">&larr; Portada</a></p></div>';
    return;
  }}
  document.title=a.headline+' \u2014 CienciaHoy';
  const score=a.score?(a.score*10).toFixed(1):null;
  const tags=(a.tags||[]).map(t=>`<span class="tag">${{esc(t)}}</span>`).join(' ');
  let authors='';
  try{{authors=JSON.parse(a.authors||'[]').join(', ');}}catch(e){{}}
  const img=a.has_image?`<img class="art-img" src="/static/images/${{AID}}.jpg" alt="">`:'';
  const color=esc(a.category_color||'#c04a1a');

  // fuente: source_url tiene prioridad sobre arxiv_url
  const srcUrl=a.source_url||a.arxiv_url||'';

  wrap.innerHTML=`
    <div class="art-breadcrumb">
      <a href="/">Portada</a>
      <span style="color:var(--border)">&rsaquo;</span>
      <span style="color:${{color}}">${{esc(a.category_label||a.category||'')}}</span>
    </div>
    <div class="art-cat" style="color:${{color}}">${{esc(a.category_label||a.category||'')}}</div>
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
    ${{srcUrl?`
    <div class="art-source">
      <div class="art-source-label">Referencia:</div>
      <a href="${{esc(srcUrl)}}" target="_blank" rel="noopener">
        Consulta el paper completo &nearr;
      </a>
      ${{authors?`<div class="art-source-authors">${{esc(authors)}}</div>`:''}}
    </div>`:''}}`
  ;
  loadRel(a.category_label||a.category);
}}

async function loadRel(cat){{
  const data=await fetch('/api/articles?per_page=6&category='+encodeURIComponent(cat)).then(r=>r.json()).catch(()=>null);
  if(!data) return;
  const others=(data.articles||[]).filter(a=>a.id!==AID).slice(0,3);
  if(!others.length) return;
  document.getElementById('rel').style.display='';
  document.getElementById('rel-grid').innerHTML=others.map(a=>`
    <div class="rel-card" onclick="go('/article/${{a.id}}')">
      <div class="rel-cat" style="color:${{esc(a.category_color||'#c04a1a')}}">${{esc(a.category_label||'')}}</div>
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
    found = any(
        a.get("id") == article_id and a.get("status") == "published"
        for a in load_articles()
    )
    if not found:
        raise HTTPException(status_code=404, detail="No encontrado")
    return ARTICLE.replace("{article_id}", article_id)
