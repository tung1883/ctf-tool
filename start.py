#!/usr/bin/env python3
"""CTF page editor & server — python start.py → http://localhost:8081/edit"""

import contextlib
import io
import json
import mimetypes
import re
import socket
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE          = Path(__file__).parent
CONFIGS_PATH  = HERE / "configs.json"
PORT          = 8081
PROXY_LOG_DIR = HERE / "proxy-logs"

_proxy_procs: dict = {}

# ---------------------------------------------------------------------------
# SVG icon library
# ---------------------------------------------------------------------------
_SVG_PATHS = {
    "flag":       '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/>',
    "globe":      '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
    "lock":       '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "microscope": '<path d="M6 18h8"/><path d="M3 22h18"/><path d="M14 22a7 7 0 1 0 0-14h-1"/><path d="M9 14h2"/><path d="M9 12a2 2 0 0 1-2-2V6h6v4a2 2 0 0 1-2 2Z"/><path d="M12 6V3a1 1 0 0 0-1-1H9a1 1 0 0 0-1 1v3"/>',
    "terminal":   '<polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>',
    "eye":        '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
    "puzzle":     '<path d="M20.5 11H19V7c0-1.1-.9-2-2-2h-4V3.5A2.5 2.5 0 0 0 10.5 1A2.5 2.5 0 0 0 8 3.5V5H4c-1.1 0-2 .9-2 2v3.8h1.5c1.5 0 2.7 1.2 2.7 2.7S5 16.2 3.5 16.2H2V20c0 1.1.9 2 2 2h3.8v-1.5c0-1.5 1.2-2.7 2.7-2.7S13.2 19 13.2 20.5V22H17c1.1 0 2-.9 2-2v-4h1.5c1.4 0 2.5-1.1 2.5-2.5S21.9 11 20.5 11z"/>',
    "layers":     '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
    "users":      '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "award":      '<circle cx="12" cy="8" r="6"/><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/>',
    "clock":      '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "check":      '<polyline points="20 6 9 17 4 12"/>',
    "x-mark":     '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    "book":       '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
    "lightbulb":  '<line x1="9" y1="18" x2="15" y2="18"/><line x1="10" y1="22" x2="14" y2="22"/><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14"/>',
    "arrow-left": '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>',
    "shield":     '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "heart":      '<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>',
    "feather":    '<path d="M20.24 12.24a6 6 0 0 0-8.49-8.49L5 10.5V19h8.5z"/><line x1="16" y1="8" x2="2" y2="22"/><line x1="17.5" y1="15" x2="9" y2="15"/>',
}

def icon(name: str, size: int = 24, cls: str = "") -> str:
    paths = _SVG_PATHS.get(name, _SVG_PATHS["flag"])
    cls_attr = f' class="{cls}"' if cls else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}"'
        f' viewBox="0 0 24 24" fill="none" stroke="currentColor"'
        f' stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"{cls_attr}>'
        f'{paths}</svg>'
    )

# ---------------------------------------------------------------------------
# HTML generation helpers
# ---------------------------------------------------------------------------
def esc(text: str) -> str:
    return str(text).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

_BASE_CSS = """
  :root {{
    --accent: {accent};
    --bg: #0d1117; --bg2: #161b22; --bg3: #21262d;
    --text: #e6edf3; --muted: #8b949e; --border: #30363d;
    --radius: 8px; --green: #2ea043; --red: #f85149;
  }}
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  svg.icon {{ vertical-align: middle; flex-shrink: 0; }}

  nav {{ position: sticky; top: 0; z-index: 100; background: rgba(13,17,23,.92); backdrop-filter: blur(8px); border-bottom: 1px solid var(--border); padding: .75rem 2rem; display: flex; justify-content: space-between; align-items: center; gap: 1rem; }}
  .nav-brand {{ font-weight: 700; font-size: 1.1rem; color: var(--accent); display: flex; align-items: center; gap: .5rem; white-space: nowrap; }}
  .nav-links {{ display: flex; align-items: center; flex-wrap: wrap; gap: .25rem; }}
  .nav-links a {{ padding: .3rem .75rem; color: var(--muted); font-size: .875rem; border-radius: 6px; transition: color .15s, background .15s; }}
  .nav-links a:hover {{ color: var(--text); background: var(--bg3); text-decoration: none; }}
  .nav-links .btn-nav {{ background: var(--accent); color: #000 !important; font-weight: 600; }}
  .nav-links .btn-nav:hover {{ opacity: .85; background: var(--accent); }}

  section {{ padding: 4rem 2rem; max-width: 1100px; margin: 0 auto; }}
  section h2 {{ font-size: 1.75rem; font-weight: 700; margin-bottom: 2rem; display: flex; align-items: center; gap: .6rem; }}
  section h2::before {{ content: ''; display: inline-block; width: 4px; height: 1.5rem; background: var(--accent); border-radius: 2px; flex-shrink: 0; }}

  .btn {{ display: inline-flex; align-items: center; gap: .5rem; margin-top: 1.5rem; padding: .75rem 1.75rem; background: var(--accent); color: #000; font-weight: 700; border-radius: 6px; transition: opacity .2s; }}
  .btn:hover {{ opacity: .85; text-decoration: none; }}
  .btn-outline {{ background: transparent; border: 1.5px solid var(--accent); color: var(--accent); }}
  .btn-outline:hover {{ background: var(--accent); color: #000; }}

  footer {{ text-align: center; padding: 2rem; border-top: 1px solid var(--border); color: var(--muted); font-size: .85rem; }}
  .footer-links {{ margin-bottom: .75rem; display: flex; justify-content: center; gap: 1.5rem; }}
"""

def _base_head(title: str, accent: str, extra_css: str = "") -> str:
    return f"""<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<style>
{_BASE_CSS.format(accent=esc(accent))}
{extra_css}
</style>
</head>"""

def _nav(cfg: dict, current: str = "main") -> str:
    ev = cfg["event"]
    h  = cfg["hero"]
    logo_svg = icon(cfg["site"].get("logo_icon", "flag"), 20, "icon")
    lab_link = ""
    if h.get("show_lab_link"):
        active = ' style="color:var(--accent)"' if current == "lab" else ""
        lab_link = f'<a href="/lab-question/"{active}>{icon("book",16,"icon")} Lab</a>'
    main_active = ' style="color:var(--text)"' if current == "main" else ""
    return f"""<nav>
  <span class="nav-brand">{logo_svg} {esc(ev["name"])}</span>
  <div class="nav-links">
    <a href="/{'"' if current != "main" else '#"'}{main_active}>Home</a>
    <a href="{'/' if current != 'main' else ''}#categories">Categories</a>
    <a href="{'/' if current != 'main' else ''}#schedule">Schedule</a>
    <a href="{'/' if current != 'main' else ''}#faq">FAQ</a>
    {lab_link}
    <a href="{esc(h['cta_url'])}" class="btn-nav">{esc(h["cta_text"])}</a>
  </div>
</nav>"""

def _footer(cfg: dict) -> str:
    ft = cfg["footer"]
    ev = cfg["event"]
    links = "".join(
        f'<a href="{esc(s["url"])}">{esc(s["label"])}</a>'
        for s in ft.get("socials", [])
    )
    if ft.get("email"):
        links += f'<a href="mailto:{esc(ft["email"])}">{esc(ft["email"])}</a>'
    return f"""<footer>
  <div class="footer-links">{links}</div>
  <div>&copy; {esc(ft['copyright'])} · Organized by {esc(ev['organizer'])}</div>
</footer>"""

def _build_stats(stats: list) -> str:
    items = []
    for s in stats:
        ic = icon(s.get("icon","layers"), 28, "icon") if s.get("icon") else ""
        items.append(
            f'<div class="stat">{ic}'
            f'<span class="stat-value">{esc(s["value"])}</span>'
            f'<span class="stat-label">{esc(s["label"])}</span></div>'
        )
    return '<div class="stats-grid">' + "\n".join(items) + '</div>'

def _build_categories(cats: list) -> str:
    cards = []
    for c in cats:
        ic = icon(c.get("icon","flag"), 32, "icon")
        cards.append(
            f'<div class="card">'
            f'<div class="card-icon">{ic}</div>'
            f'<h3>{esc(c["name"])}</h3>'
            f'<p>{esc(c["description"])}</p>'
            f'</div>'
        )
    return '<div class="cards-grid">' + "\n".join(cards) + '</div>'

def _build_partners(partners: list) -> str:
    if not partners:
        return ""
    tier_order = ["gold", "silver", "bronze"]
    tier_labels = {"gold": "Gold", "silver": "Silver", "bronze": "Bronze"}
    grouped: dict = {}
    for p in partners:
        grouped.setdefault(p.get("tier","bronze"), []).append(p)
    html = []
    for tier in tier_order:
        if tier not in grouped:
            continue
        logo_items = []
        for p in grouped[tier]:
            inner = (f'<img src="{esc(p["logo_url"])}" alt="{esc(p["name"])}" class="partner-img">'
                     if p.get("logo_url") else f'<span class="partner-text">{esc(p["name"])}</span>')
            logo_items.append(
                f'<a href="{esc(p.get("website","#"))}" class="partner-logo partner-{tier}" '
                f'title="{esc(p["name"])}" target="_blank" rel="noopener">{inner}</a>'
            )
        html.append(
            f'<div class="partner-tier">'
            f'<span class="tier-badge tier-{tier}">{tier_labels[tier]}</span>'
            f'<div class="partner-row">{"".join(logo_items)}</div>'
            f'</div>'
        )
    return "\n".join(html)

def _build_schedule(schedule: list) -> str:
    rows = "".join(
        f'<div class="sched-row">'
        f'<span class="sched-time">{esc(s["time"])}</span>'
        f'<span class="sched-event">{esc(s["event"])}</span>'
        f'</div>'
        for s in schedule
    )
    return f'<div class="schedule">{rows}</div>'

def _build_faq(faq: list) -> str:
    items = "".join(
        f'<details class="faq-item">'
        f'<summary>{esc(item["q"])}</summary>'
        f'<p>{esc(item["a"])}</p>'
        f'</details>'
        for item in faq
    )
    return f'<div class="faq-list">{items}</div>'

_INDEX_CSS = """
  .hero { text-align: center; padding: 6rem 2rem 4rem; background: radial-gradient(ellipse at top, #0d2a1f 0%, var(--bg) 70%); }
  .hero-logo { margin-bottom: .75rem; color: var(--accent); }
  .hero h1 { font-size: clamp(2rem,5vw,3.5rem); font-weight: 800; margin: .25rem 0; }
  .hero p { max-width: 600px; margin: 1rem auto; color: var(--muted); font-size: 1.05rem; }
  .hero-meta { margin-top: 1rem; color: var(--muted); font-size: .9rem; display: flex; justify-content: center; align-items: center; gap: 1.25rem; flex-wrap: wrap; }
  .hero-meta span { display: flex; align-items: center; gap: .35rem; }
  .flag-badge { display: inline-block; background: var(--bg3); border: 1px solid var(--accent); border-radius: 4px; padding: .2rem .6rem; font-family: monospace; color: var(--accent); font-size: .9rem; }
  .hero-actions { display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap; }
  .hero-disclaimer { max-width: 680px; margin: 1.25rem auto 0; background: rgba(248,81,73,.08); border: 1px solid rgba(248,81,73,.4); border-radius: var(--radius); padding: .75rem 1.1rem; font-size: .85rem; color: #f98989; line-height: 1.55; }
  .stats-grid { display: flex; flex-wrap: wrap; gap: 1rem; justify-content: center; }
  .stat { background: var(--bg2); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.5rem 2.25rem; text-align: center; display: flex; flex-direction: column; align-items: center; gap: .4rem; min-width: 130px; color: var(--muted); }
  .stat-value { font-size: 2rem; font-weight: 800; color: var(--accent); line-height: 1; }
  .stat-label { font-size: .8rem; text-transform: uppercase; letter-spacing: .06em; }
  .cards-grid { display: grid; grid-template-columns: repeat(auto-fill,minmax(220px,1fr)); gap: 1rem; }
  .card { background: var(--bg2); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.5rem; transition: border-color .2s, transform .2s; }
  .card:hover { border-color: var(--accent); transform: translateY(-2px); }
  .card-icon { color: var(--accent); margin-bottom: .75rem; }
  .card h3 { margin-bottom: .4rem; }
  .card p { color: var(--muted); font-size: .9rem; }
  .partner-tier { margin-bottom: 2rem; }
  .tier-badge { display: inline-block; font-size: .7rem; font-weight: 700; text-transform: uppercase; letter-spacing: .1em; padding: .2rem .6rem; border-radius: 20px; margin-bottom: .75rem; }
  .tier-gold   { background: rgba(212,175,55,.15); color: #d4af37; border: 1px solid #d4af37; }
  .tier-silver { background: rgba(192,192,192,.15); color: #c0c0c0; border: 1px solid #c0c0c0; }
  .tier-bronze { background: rgba(205,127,50,.15);  color: #cd7f32; border: 1px solid #cd7f32; }
  .partner-row { display: flex; flex-wrap: wrap; gap: .75rem; align-items: center; }
  .partner-logo { display: flex; align-items: center; justify-content: center; background: var(--bg2); border: 1px solid var(--border); border-radius: var(--radius); padding: .75rem 1.5rem; min-width: 140px; height: 60px; transition: border-color .2s; }
  .partner-logo:hover { border-color: var(--accent); text-decoration: none; }
  .partner-gold   { border-color: rgba(212,175,55,.4); }
  .partner-silver { border-color: rgba(192,192,192,.3); }
  .partner-img { max-height: 36px; max-width: 120px; object-fit: contain; filter: grayscale(1) brightness(1.4); transition: filter .2s; }
  .partner-logo:hover .partner-img { filter: none; }
  .partner-text { font-weight: 600; color: var(--muted); font-size: .9rem; white-space: nowrap; }
  .partner-logo:hover .partner-text { color: var(--text); }
  .schedule { display: flex; flex-direction: column; gap: .75rem; }
  .sched-row { display: flex; gap: 1.5rem; align-items: baseline; padding: 1rem 1.25rem; background: var(--bg2); border: 1px solid var(--border); border-radius: var(--radius); flex-wrap: wrap; }
  .sched-time { color: var(--accent); font-family: monospace; font-size: .875rem; white-space: nowrap; }
  .faq-list { display: flex; flex-direction: column; gap: .5rem; }
  .faq-item { background: var(--bg2); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
  .faq-item summary { padding: 1rem 1.25rem; cursor: pointer; font-weight: 600; list-style: none; display: flex; justify-content: space-between; align-items: center; }
  .faq-item summary::after { content: '+'; color: var(--accent); font-size: 1.25rem; }
  .faq-item[open] summary::after { content: '\\2212'; }
  .faq-item p { padding: 0 1.25rem 1rem; color: var(--muted); }
"""

_LAB_CSS = """
  .lab-hero { padding: 4rem 2rem 3rem; background: radial-gradient(ellipse at top, #0d1f2a 0%, var(--bg) 70%); text-align: center; border-bottom: 1px solid var(--border); }
  .lab-hero h1 { font-size: clamp(1.75rem,4vw,2.75rem); font-weight: 800; margin-bottom: .5rem; }
  .lab-hero p { max-width: 640px; margin: 0 auto; color: var(--muted); font-size: 1rem; }
  .back-link { display: inline-flex; align-items: center; gap: .4rem; font-size: .875rem; color: var(--muted); margin: 1.5rem 2rem .5rem; }
  .back-link:hover { color: var(--text); text-decoration: none; }
  .lab-disclaimer { background: rgba(248,81,73,.07); border: 1px solid rgba(248,81,73,.4); border-left: 4px solid #f85149; border-radius: var(--radius); padding: 1rem 1.25rem; margin: 0 2rem 0; font-size: .875rem; color: #f98989; line-height: 1.6; max-width: 1100px; }
  .rules-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; }
  @media (max-width: 600px) { .rules-grid { grid-template-columns: 1fr; } }
  .rules-col { background: var(--bg2); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.5rem; }
  .rules-col.allowed   { border-top: 3px solid var(--green); }
  .rules-col.forbidden { border-top: 3px solid var(--red); }
  .rules-col h3 { display: flex; align-items: center; gap: .5rem; font-size: 1rem; margin-bottom: 1rem; }
  .allowed   h3 { color: var(--green); }
  .forbidden h3 { color: var(--red);   }
  .rules-list { list-style: none; display: flex; flex-direction: column; gap: .6rem; }
  .rules-list li { display: flex; align-items: flex-start; gap: .6rem; font-size: .9rem; color: var(--muted); line-height: 1.5; }
  .rules-list li svg { flex-shrink: 0; margin-top: 2px; }
  .allowed   .rules-list li svg { color: var(--green); }
  .forbidden .rules-list li svg { color: var(--red);   }
  .questions-list { display: flex; flex-direction: column; gap: 1rem; }
  .q-card { background: var(--bg2); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.5rem; display: flex; gap: 1.25rem; transition: border-color .2s; }
  .q-card:hover { border-color: var(--accent); }
  .q-num { font-size: 2.5rem; font-weight: 900; color: var(--border); line-height: 1; min-width: 3rem; text-align: center; padding-top: .1rem; font-variant-numeric: tabular-nums; }
  .q-body { flex: 1; }
  .q-body h3 { font-size: 1.1rem; margin-bottom: .4rem; }
  .q-body p  { color: var(--muted); font-size: .9rem; margin-bottom: .75rem; }
  .q-meta { display: flex; align-items: center; gap: .75rem; flex-wrap: wrap; }
  .q-points { background: var(--bg3); border: 1px solid var(--border); border-radius: 4px; padding: .15rem .6rem; font-size: .8rem; font-weight: 600; color: var(--accent); font-family: monospace; }
  .q-hint { margin-top: .75rem; }
  .q-hint summary { display: flex; align-items: center; gap: .4rem; cursor: pointer; font-size: .85rem; color: var(--muted); list-style: none; }
  .q-hint summary:hover { color: var(--accent); }
  .q-hint p { margin-top: .5rem; padding: .75rem 1rem; background: var(--bg3); border-radius: 6px; font-size: .875rem; color: var(--muted); border-left: 3px solid var(--accent); }
"""

def render_index(cfg: dict) -> str:
    s  = cfg["site"]
    ev = cfg["event"]
    h  = cfg["hero"]
    accent = s.get("accent_color", "#00ff88")
    partners_html = _build_partners(cfg.get("partners", []))
    partners_section = (
        f'<section id="partners"><h2>Partners &amp; Sponsors</h2>{partners_html}</section>'
        if partners_html else ""
    )
    lab_btn = (
        f'<a href="/lab-question/" class="btn btn-outline">{icon("book",18,"icon")} {esc(h.get("lab_cta_text","View Lab"))}</a>'
        if h.get("show_lab_link") else ""
    )
    disclaimer_html = (
        f'<div class="hero-disclaimer">⚠ {esc(h["disclaimer"])}</div>'
        if h.get("disclaimer") else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
{_base_head(s["title"], accent, _INDEX_CSS)}
<body>
{_nav(cfg, "main")}
<div class="hero">
  <div class="hero-logo">{icon(s.get("logo_icon","flag"), 56, "icon")}</div>
  <h1>{esc(h["headline"])}</h1>
  <p>{esc(h["description"])}</p>
  <div class="hero-meta">
    <span>{icon("clock",15,"icon")} {esc(ev["date"])}</span>
    <span>{icon("clock",15,"icon")} {esc(ev["duration"])}</span>
    <span>{icon("globe",15,"icon")} {esc(ev["location"])}</span>
  </div>
  <div style="margin-top:.9rem">Flag format: <span class="flag-badge">{esc(ev["flag_format"])}</span></div>
  {disclaimer_html}
  <div class="hero-actions">
    <a href="{esc(h['cta_url'])}" class="btn">{icon("flag",18,"icon")} {esc(h["cta_text"])}</a>
    {lab_btn}
  </div>
</div>
<section id="stats"><h2>By the Numbers</h2>{_build_stats(cfg["stats"])}</section>
<section id="categories"><h2>Challenge Categories</h2>{_build_categories(cfg["categories"])}</section>
{partners_section}
<section id="schedule"><h2>Schedule</h2>{_build_schedule(cfg["schedule"])}</section>
<section id="faq"><h2>FAQ</h2>{_build_faq(cfg["faq"])}</section>
{_footer(cfg)}
</body>
</html>"""

def render_lab(cfg: dict) -> str:
    s      = cfg["site"]
    lab    = cfg.get("lab", {})
    accent = s.get("accent_color", "#00ff88")
    title  = lab.get("title", "Lab Challenges")
    sub    = lab.get("subtitle", "")
    desc   = lab.get("description", "")
    rules  = lab.get("rules", {})

    allowed_items = "".join(
        f'<li>{icon("check",16,"icon")} <span>{esc(r)}</span></li>'
        for r in rules.get("allowed", [])
    )
    forbidden_items = "".join(
        f'<li>{icon("x-mark",16,"icon")} <span>{esc(r)}</span></li>'
        for r in rules.get("not_allowed", [])
    )

    q_cards = []
    for q in lab.get("questions", []):
        hint_html = (
            f'<details class="q-hint">'
            f'<summary>{icon("lightbulb",14,"icon")} Show hint</summary>'
            f'<p>{esc(q["hint"])}</p>'
            f'</details>'
            if q.get("hint") else ""
        )
        num_str = str(q.get("number","?")).zfill(2)
        q_cards.append(
            f'<div class="q-card">'
            f'<div class="q-num">{num_str}</div>'
            f'<div class="q-body">'
            f'<h3>{esc(q.get("title","Challenge"))}</h3>'
            f'<p>{esc(q.get("description",""))}</p>'
            f'<div class="q-meta"><span class="q-points">{esc(str(q.get("points","")))} pts</span></div>'
            f'{hint_html}'
            f'</div></div>'
        )

    disclaimer_block = (
        f'<div class="lab-disclaimer">⚠ {esc(lab["disclaimer"])}</div>'
        if lab.get("disclaimer") else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
{_base_head(f'{esc(title)} — {esc(s["title"])}', accent, _LAB_CSS)}
<body>
{_nav(cfg, "lab")}
<div class="lab-hero">
  <h1>{esc(title)}</h1>
  {'<p style="color:var(--accent);font-size:.9rem;margin-bottom:.5rem">'+esc(sub)+'</p>' if sub else ''}
  <p>{esc(desc)}</p>
</div>
<a href="/" class="back-link">{icon("arrow-left",16,"icon")} Back to main page</a>
{disclaimer_block}
<section id="rules">
  <h2>Rules</h2>
  <div class="rules-grid">
    <div class="rules-col allowed">
      <h3>{icon("check",18,"icon")} Allowed</h3>
      <ul class="rules-list">{allowed_items}</ul>
    </div>
    <div class="rules-col forbidden">
      <h3>{icon("x-mark",18,"icon")} Not Allowed</h3>
      <ul class="rules-list">{forbidden_items}</ul>
    </div>
  </div>
</section>
<section id="questions">
  <h2>Challenges ({len(lab.get("questions",[]))} total)</h2>
  <div class="questions-list">{"".join(q_cards)}</div>
</section>
{_footer(cfg)}
</body>
</html>"""

def generate_pages(config_source) -> str:
    if isinstance(config_source, dict):
        cfg = config_source
    else:
        with open(config_source, encoding="utf-8") as f:
            cfg = json.load(f)
    out = HERE / "index.html"
    out.write_text(render_index(cfg), encoding="utf-8")
    print(f"  [gen] {out.relative_to(HERE)}")
    lab_dir = HERE / "lab-question"
    lab_dir.mkdir(exist_ok=True)
    lab_out = lab_dir / "index.html"
    lab_out.write_text(render_lab(cfg), encoding="utf-8")
    print(f"  [gen] {lab_out.relative_to(HERE)}")

# ---------------------------------------------------------------------------
# Proxy helpers
# ---------------------------------------------------------------------------
def _is_port_listening(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.05)
        return s.connect_ex(("127.0.0.1", port)) == 0

def _proxy_target_from_log(port: int) -> str:
    log = PROXY_LOG_DIR / f"proxy-{port}.log"
    if not log.exists():
        return "?"
    pat = re.compile(r"\[proxy\] listening on :\d+ -> (\S+)", re.IGNORECASE)
    try:
        for line in log.read_text(errors="replace").splitlines():
            m = pat.search(line)
            if m:
                return m.group(1)
    except Exception:
        pass
    return "?"

def _list_proxy_forwardings() -> list:
    rows = []
    seen: set = set()
    for port, proc in list(_proxy_procs.items()):
        active = proc.poll() is None and _is_port_listening(port)
        rows.append({"port": port, "target": _proxy_target_from_log(port), "active": active, "tracked": True})
        seen.add(port)
    if PROXY_LOG_DIR.exists():
        for f in sorted(PROXY_LOG_DIR.glob("proxy-*.log")):
            m = re.match(r"^proxy-(\d+)\.log$", f.name)
            if not m:
                continue
            port = int(m.group(1))
            if port in seen:
                continue
            if _is_port_listening(port):
                rows.append({"port": port, "target": _proxy_target_from_log(port), "active": True, "tracked": False})
            else:
                # stale log — clean up so it doesn't slow future polls
                try:
                    f.unlink(missing_ok=True)
                    (PROXY_LOG_DIR / f"proxy-{port}.log.err").unlink(missing_ok=True)
                except Exception:
                    pass
    return sorted(rows, key=lambda r: r["port"])

# ---------------------------------------------------------------------------
# Editor UI
# ---------------------------------------------------------------------------
EDITOR_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Config Editor</title>
<style>
:root{
  --accent:#00ff88;--bg:#0d1117;--bg2:#161b22;--bg3:#21262d;
  --text:#e6edf3;--muted:#8b949e;--border:#30363d;--r:6px;
  --sbw:172px;--tbh:50px;--green:#2ea043;--red:#f85149;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;overflow:hidden}
#tb{position:fixed;top:0;left:0;right:0;height:var(--tbh);display:flex;align-items:center;
  justify-content:space-between;padding:0 1rem;background:var(--bg2);
  border-bottom:1px solid var(--border);z-index:100;gap:.5rem}
.brand{font-weight:700;color:var(--accent);white-space:nowrap;font-size:.95rem}
#tb-right{display:flex;align-items:center;gap:.4rem;flex-wrap:wrap}
#st{font-size:.75rem;padding:.2rem .6rem;border-radius:20px;white-space:nowrap}
.st-ok{background:rgba(46,160,67,.15);color:var(--green);border:1px solid rgba(46,160,67,.35)}
.st-dirty{background:rgba(210,153,34,.15);color:#d2991a;border:1px solid rgba(210,153,34,.35)}
.st-busy{background:rgba(0,255,136,.1);color:var(--accent);border:1px solid rgba(0,255,136,.25)}
#lay{position:fixed;top:var(--tbh);left:0;right:0;bottom:0;display:flex}
#sb{width:var(--sbw);flex-shrink:0;overflow-y:auto;border-right:1px solid var(--border);
    background:var(--bg);padding:.5rem 0}
#ct{flex:1;overflow-y:auto;padding:1.5rem 1.75rem}
.nb{display:block;width:100%;padding:.55rem 1rem;text-align:left;background:none;border:none;
    cursor:pointer;color:var(--muted);font-size:.85rem;transition:color .15s,background .15s;
    border-left:3px solid transparent}
.nb:hover{color:var(--text);background:var(--bg3)}
.nb.on{color:var(--accent);background:rgba(0,255,136,.07);border-left-color:var(--accent)}
.nb.hl{font-weight:600}
.sb-sep{margin:.4rem .6rem;border:none;border-top:1px solid var(--border)}
.btn{display:inline-flex;align-items:center;gap:.3rem;padding:.38rem .85rem;
     border-radius:var(--r);border:none;cursor:pointer;font-size:.82rem;font-weight:500;
     transition:opacity .15s,background .15s;text-decoration:none;color:inherit}
.btn-pri{background:var(--accent);color:#000}
.btn-pri:hover{opacity:.85}
.btn-ghost{background:transparent;border:1px solid var(--border);color:var(--muted)}
.btn-ghost:hover{color:var(--text);border-color:var(--muted)}
.btn-add{background:rgba(0,255,136,.08);color:var(--accent);border:1px dashed rgba(0,255,136,.35);
         width:100%;justify-content:center;padding:.55rem;margin-top:.25rem}
.btn-add:hover{background:rgba(0,255,136,.16)}
.btn-rm{background:rgba(248,81,73,.12);color:var(--red);border:1px solid rgba(248,81,73,.3);
        padding:.2rem .5rem;font-size:.78rem}
.btn-rm:hover{background:rgba(248,81,73,.22)}
.btn-xs{background:var(--bg3);border:1px solid var(--border);color:var(--muted);
        padding:.18rem .45rem;font-size:.75rem}
.btn-xs:hover{color:var(--text)}
.btn-xs:disabled{opacity:.3;cursor:default}
.f{margin-bottom:.9rem}
.f label{display:block;font-size:.72rem;color:var(--muted);margin-bottom:.28rem;
          text-transform:uppercase;letter-spacing:.05em}
.f input[type=text],.f input[type=number],.f input[type=url],.f input[type=email],
.f textarea,.f select{
  width:100%;padding:.45rem .7rem;background:var(--bg3);border:1px solid var(--border);
  border-radius:var(--r);color:var(--text);font-size:.875rem;font-family:inherit;
  transition:border-color .15s}
.f input:focus,.f textarea:focus,.f select:focus{outline:none;border-color:var(--accent)}
.f textarea{resize:vertical;min-height:72px}
.f select{cursor:pointer;-webkit-appearance:none}
.f-row{display:grid;grid-template-columns:1fr 1fr;gap:.75rem}
.f-color-wrap{display:flex;align-items:center;gap:.6rem}
.f input[type=color]{width:44px;height:34px;padding:2px;cursor:pointer;border-radius:var(--r)}
.color-hex{font-family:monospace;font-size:.82rem;color:var(--muted)}
.f-check{display:flex;align-items:center;gap:.5rem;cursor:pointer;padding-top:.4rem}
.f-check input{cursor:pointer;accent-color:var(--accent);width:15px;height:15px}
.card{background:var(--bg2);border:1px solid var(--border);border-radius:var(--r);
      margin-bottom:.7rem;overflow:hidden}
.card-h{display:flex;align-items:center;justify-content:space-between;padding:.65rem 1rem;
        background:var(--bg3);border-bottom:1px solid var(--border);gap:.5rem}
.card-h strong{font-size:.875rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card-acts{display:flex;gap:.35rem;flex-shrink:0}
.card-b{padding:1rem}
.sl{display:flex;flex-direction:column;gap:.35rem;margin-bottom:.4rem}
.sl-row{display:flex;align-items:center;gap:.4rem}
.sl-row input{flex:1;padding:.45rem .7rem;background:var(--bg3);border:1px solid var(--border);border-radius:var(--r);color:var(--text);font-size:.875rem;font-family:inherit;transition:border-color .15s}
.sl-row input:focus{outline:none;border-color:var(--accent)}
.sl-row button{flex-shrink:0}
.sh{font-size:1.2rem;font-weight:700;margin-bottom:1.25rem;padding-bottom:.6rem;
    border-bottom:1px solid var(--border)}
.ssh{font-size:.72rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);
     margin:1.5rem 0 .75rem}
#log{display:none;position:fixed;bottom:0;left:var(--sbw);right:0;max-height:130px;
     background:#080d11;border-top:1px solid var(--border);z-index:80}
#log-h{display:flex;justify-content:space-between;align-items:center;
       padding:.3rem .9rem;border-bottom:1px solid var(--border)}
#log-h span{font-size:.72rem;color:var(--muted)}
#log-b{padding:.5rem .9rem;font-family:monospace;font-size:.75rem;color:#7ee787;
       overflow-y:auto;max-height:95px;white-space:pre-wrap}
</style>
</head>
<body>

<header id="tb">
  <span class="brand">Config Editor</span>
  <div id="tb-right">
    <label style="display:flex;align-items:center;gap:.4rem;font-size:.78rem;color:var(--muted)">
      Config:
      <select id="cfg-sel" onchange="switchCfg(this.value)" style="background:var(--bg3);border:1px solid var(--border);color:var(--text);border-radius:var(--r);padding:.3rem .6rem;font-size:.8rem;cursor:pointer;min-width:110px"></select>
    </label>
    <span id="st" class="st-ok">Loaded</span>
    <button onclick="saveCfg()" class="btn btn-ghost">Save</button>
    <button onclick="regen()" class="btn btn-pri">Save &amp; Regenerate</button>
    <a href="/" target="_blank" class="btn btn-ghost">Preview ↗</a>
    <a href="/lab-question/" target="_blank" class="btn btn-ghost">Preview Lab ↗</a>
  </div>
</header>

<div id="lay">
  <nav id="sb">
    <button class="nb on" data-t="event"    onclick="tab('event')">Site &amp; Event</button>
    <button class="nb"    data-t="hero"     onclick="tab('hero')">Hero</button>
    <hr class="sb-sep">
    <button class="nb hl" data-t="lab"      onclick="tab('lab')">★ Lab</button>
    <hr class="sb-sep">
    <button class="nb"    data-t="partners" onclick="tab('partners')">Partners</button>
    <button class="nb"    data-t="schedule" onclick="tab('schedule')">Schedule</button>
    <button class="nb"    data-t="faq"      onclick="tab('faq')">FAQ</button>
    <button class="nb"    data-t="footer"   onclick="tab('footer')">Footer</button>
    <hr class="sb-sep">
    <button class="nb"    data-t="adv"      onclick="tab('adv')">Advanced</button>
    <hr class="sb-sep">
    <button class="nb"    data-t="proxy"    onclick="tab('proxy')">⇄ Proxy</button>
  </nav>
  <main id="ct"><p style="color:var(--muted);padding:1rem">Loading…</p></main>
</div>

<div id="log">
  <div id="log-h">
    <span>Generator output</span>
    <button class="btn-xs" onclick="document.getElementById('log').style.display='none'">✕ close</button>
  </div>
  <div id="log-b"></div>
</div>

<script>
let cfg = {}, cur = 'event', cfgName = 'default';

const H = s => String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const A = s => String(s??'').replace(/"/g,'&quot;').replace(/'/g,'&#39;');

function sp(path, val) {
  const keys = path.split('.');
  let o = cfg;
  for (let i = 0; i < keys.length-1; i++) {
    const k = /^\d+$/.test(keys[i]) ? +keys[i] : keys[i];
    o = o[k];
  }
  const last = /^\d+$/.test(keys[keys.length-1]) ? +keys[keys.length-1] : keys[keys.length-1];
  o[last] = val;
  dirty();
}

function dirty(){ st('Unsaved changes','dirty') }
function st(msg,type){ const e=document.getElementById('st'); e.textContent=msg; e.className='st-'+type }

async function loadConfigs(){
  const r = await fetch('/api/configs');
  const names = await r.json();
  const sel = document.getElementById('cfg-sel');
  sel.innerHTML = names.map(n=>`<option value="${n}"${n===cfgName?' selected':''}>${n}</option>`).join('');
}

async function switchCfg(name){
  const sel = document.getElementById('cfg-sel');
  if(document.getElementById('st').className==='st-dirty'){
    if(!confirm('You have unsaved changes. Switch config anyway?')){ sel.value=cfgName; return; }
  }
  cfgName = name;
  await loadCfg();
}

async function loadCfg(){
  const r = await fetch('/api/config?name='+encodeURIComponent(cfgName));
  cfg = await r.json();
  tab(cur);
  st('Loaded','ok');
}

async function saveCfg(){
  st('Saving…','busy');
  try{
    await fetch('/api/config?name='+encodeURIComponent(cfgName),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)});
    st('Saved','ok');
  }catch(e){ st('Save failed!','dirty') }
}

async function regen(){
  st('Regenerating…','busy');
  const log = document.getElementById('log');
  const logb = document.getElementById('log-b');
  log.style.display='none';
  try{
    const r = await fetch('/api/regenerate?name='+encodeURIComponent(cfgName),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)});
    const d = await r.json();
    st(d.ok ? 'Regenerated' : 'Regen failed!', d.ok ? 'ok' : 'dirty');
    if(d.output){ logb.textContent=d.output; log.style.display='block'; }
  }catch(e){ st('Failed!','dirty') }
}

function f(label, path, val, type='text'){
  const v = A(String(val??''));
  if(type==='textarea')
    return `<div class="f"><label>${label}</label><textarea oninput="sp('${path}',this.value)">${H(String(val??''))}</textarea></div>`;
  if(type==='color')
    return `<div class="f"><label>${label}</label><div class="f-color-wrap"><input type="color" value="${v}" oninput="sp('${path}',this.value);this.nextElementSibling.textContent=this.value"><span class="color-hex">${v}</span></div></div>`;
  const cb = type==='number' ? `sp('${path}',+this.value)` : `sp('${path}',this.value)`;
  return `<div class="f"><label>${label}</label><input type="${type}" value="${v}" oninput="${cb}"></div>`;
}
function fChk(label, path, val){
  return `<div class="f"><label class="f-check"><input type="checkbox" ${val?'checked':''} onchange="sp('${path}',this.checked)"> ${label}</label></div>`;
}
function fSel(label, path, val, opts){
  const os = opts.map(o=>`<option value="${A(o)}" ${val===o?'selected':''}>${H(o)}</option>`).join('');
  return `<div class="f"><label>${label}</label><select onchange="sp('${path}',this.value)">${os}</select></div>`;
}

const TABS = {event:tEvent,hero:tHero,lab:tLab,partners:tPartners,schedule:tSchedule,faq:tFaq,footer:tFooter,adv:tAdv,proxy:tProxy};
let _proxyTimer = null;
function tab(name){
  cur=name;
  if(_proxyTimer){ clearInterval(_proxyTimer); _proxyTimer=null; }
  document.querySelectorAll('.nb').forEach(b=>b.classList.toggle('on',b.dataset.t===name));
  document.getElementById('ct').innerHTML = TABS[name] ? TABS[name]() : '';
  if(name==='proxy'){ pollProxy(); _proxyTimer=setInterval(pollProxy,2000); }
}

function tEvent(){
  const s=cfg.site||{}, ev=cfg.event||{};
  return `<div class="sh">Site &amp; Event</div>
    <div class="f-row">${f('Site title','site.title',s.title)}${f('Accent color','site.accent_color',s.accent_color,'color')}</div>
    <div class="f-row">${f('Logo icon key','site.logo_icon',s.logo_icon)}${f('Flag format','event.flag_format',ev.flag_format)}</div>
    <div class="ssh">Event</div>
    <div class="f-row">${f('Event name','event.name',ev.name)}${f('Organizer','event.organizer',ev.organizer)}</div>
    <div class="f-row">${f('Date','event.date',ev.date)}${f('Duration','event.duration',ev.duration)}</div>
    ${f('Location','event.location',ev.location)}`;
}

function tHero(){
  const h=cfg.hero||{};
  return `<div class="sh">Hero Section</div>
    ${f('Headline','hero.headline',h.headline)}
    ${f('Description','hero.description',h.description,'textarea')}
    <div class="f-row">${f('Button text','hero.cta_text',h.cta_text)}${f('Button URL','hero.cta_url',h.cta_url)}</div>
    <div class="f-row">${f('Lab button text','hero.lab_cta_text',h.lab_cta_text)}${fChk('Show lab link in nav &amp; hero','hero.show_lab_link',h.show_lab_link)}</div>
    ${f('Disclaimer (shows red warning box — leave blank to hide)','hero.disclaimer',h.disclaimer||'','textarea')}`;
}

function tLab(){
  const lab=cfg.lab||{}, r=lab.rules||{};
  return `<div class="sh">Lab</div>
    ${f('Title','lab.title',lab.title)}
    ${f('Subtitle','lab.subtitle',lab.subtitle)}
    ${f('Description','lab.description',lab.description,'textarea')}
    ${f('Disclaimer (shows red warning box — leave blank to hide)','lab.disclaimer',lab.disclaimer||'','textarea')}
    <div class="ssh">Questions</div>
    <div id="ql">${rQL()}</div>
    <button onclick="addQ()" class="btn btn-add">+ Add Question</button>
    <div class="ssh">Rules — Allowed</div>
    <div id="al">${rSL('lab.rules.allowed',r.allowed||[])}</div>
    <button onclick="addR('allowed')" class="btn btn-add">+ Add Rule</button>
    <div class="ssh">Rules — Not Allowed</div>
    <div id="nl">${rSL('lab.rules.not_allowed',r.not_allowed||[])}</div>
    <button onclick="addR('not_allowed')" class="btn btn-add">+ Add Rule</button>`;
}

function rQL(){
  const qs=cfg.lab?.questions||[];
  if(!qs.length) return '<p style="color:var(--muted);font-size:.85rem;margin-bottom:.5rem">No questions yet.</p>';
  return qs.map((q,i)=>`
    <div class="card">
      <div class="card-h">
        <strong>${String(q.number||i+1).padStart(2,'0')}. ${H(q.title||'Untitled')}</strong>
        <div class="card-acts">
          <button class="btn-xs" onclick="mvQ(${i},-1)" ${i===0?'disabled':''}>↑</button>
          <button class="btn-xs" onclick="mvQ(${i},1)"  ${i===qs.length-1?'disabled':''}>↓</button>
          <button class="btn-rm" onclick="rmQ(${i})">Remove</button>
        </div>
      </div>
      <div class="card-b">
        <div class="f-row">${f('Number','lab.questions.'+i+'.number',q.number,'number')}${f('Points','lab.questions.'+i+'.points',q.points,'number')}</div>
        ${f('Title','lab.questions.'+i+'.title',q.title)}
        ${f('Description','lab.questions.'+i+'.description',q.description,'textarea')}
        ${f('Hint (leave blank to hide)','lab.questions.'+i+'.hint',q.hint||'')}
      </div>
    </div>`).join('');
}

function rSL(base, items){
  if(!items.length) return '<p style="color:var(--muted);font-size:.82rem;margin-bottom:.35rem">No items yet.</p>';
  return `<div class="sl">`+items.map((v,i)=>
    `<div class="sl-row"><input type="text" value="${A(v)}" oninput="sp('${base}.${i}',this.value)"><button class="btn-rm" onclick="rmR('${base}',${i})">×</button></div>`
  ).join('')+`</div>`;
}

function addQ(){ if(!cfg.lab) cfg.lab={}; if(!cfg.lab.questions) cfg.lab.questions=[]; cfg.lab.questions.push({number:cfg.lab.questions.length+1,title:'',description:'',points:100,hint:''}); dirty(); document.getElementById('ql').innerHTML=rQL(); }
function rmQ(i){ cfg.lab.questions.splice(i,1); dirty(); document.getElementById('ql').innerHTML=rQL(); }
function mvQ(i,d){ const a=cfg.lab.questions, j=i+d; if(j<0||j>=a.length) return; [a[i],a[j]]=[a[j],a[i]]; dirty(); document.getElementById('ql').innerHTML=rQL(); }

function addR(which){ if(!cfg.lab) cfg.lab={}; if(!cfg.lab.rules) cfg.lab.rules={allowed:[],not_allowed:[]}; cfg.lab.rules[which].push(''); dirty(); const id=which==='allowed'?'al':'nl'; document.getElementById(id).innerHTML=rSL('lab.rules.'+which,cfg.lab.rules[which]); }
function rmR(base,i){ const keys=base.split('.'); let arr=cfg; for(const k of keys) arr=arr[/^\d+$/.test(k)?+k:k]; arr.splice(i,1); dirty(); document.getElementById(base.includes('not_allowed')?'nl':'al').innerHTML=rSL(base,arr); }

function tPartners(){
  return `<div class="sh">Partners &amp; Sponsors</div>
    <div id="pl">${rPL()}</div>
    <button onclick="addP()" class="btn btn-add">+ Add Partner</button>`;
}
function rPL(){
  const ps=cfg.partners||[];
  if(!ps.length) return '<p style="color:var(--muted);font-size:.85rem;margin-bottom:.5rem">No partners yet.</p>';
  return ps.map((p,i)=>`
    <div class="card">
      <div class="card-h">
        <strong>${H(p.name||'Unnamed')}</strong>
        <div class="card-acts">
          <span style="font-size:.75rem;color:var(--muted);margin-right:.25rem">${p.tier||''}</span>
          <button class="btn-xs" onclick="mvP(${i},-1)" ${i===0?'disabled':''}>↑</button>
          <button class="btn-xs" onclick="mvP(${i},1)"  ${i===ps.length-1?'disabled':''}>↓</button>
          <button class="btn-rm" onclick="rmP(${i})">Remove</button>
        </div>
      </div>
      <div class="card-b">
        <div class="f-row">${f('Name','partners.'+i+'.name',p.name)}${fSel('Tier','partners.'+i+'.tier',p.tier,['gold','silver','bronze'])}</div>
        <div class="f-row">${f('Logo URL (blank = text badge)','partners.'+i+'.logo_url',p.logo_url)}${f('Website','partners.'+i+'.website',p.website)}</div>
      </div>
    </div>`).join('');
}
function addP(){ if(!cfg.partners) cfg.partners=[]; cfg.partners.push({name:'',logo_url:'',website:'#',tier:'silver'}); dirty(); document.getElementById('pl').innerHTML=rPL(); }
function rmP(i){ cfg.partners.splice(i,1); dirty(); document.getElementById('pl').innerHTML=rPL(); }
function mvP(i,d){ const a=cfg.partners,j=i+d; if(j<0||j>=a.length)return; [a[i],a[j]]=[a[j],a[i]]; dirty(); document.getElementById('pl').innerHTML=rPL(); }

function tSchedule(){
  return `<div class="sh">Schedule</div>
    <div id="scl">${rSCL()}</div>
    <button onclick="addSC()" class="btn btn-add">+ Add Item</button>`;
}
function rSCL(){
  const sc=cfg.schedule||[];
  if(!sc.length) return '<p style="color:var(--muted);font-size:.85rem;margin-bottom:.5rem">No items.</p>';
  return sc.map((s,i)=>`
    <div class="card">
      <div class="card-h">
        <strong style="font-family:monospace;font-size:.8rem">${H(s.time||'')}</strong>
        <div class="card-acts">
          <button class="btn-xs" onclick="mvSC(${i},-1)" ${i===0?'disabled':''}>↑</button>
          <button class="btn-xs" onclick="mvSC(${i},1)"  ${i===sc.length-1?'disabled':''}>↓</button>
          <button class="btn-rm" onclick="rmSC(${i})">Remove</button>
        </div>
      </div>
      <div class="card-b">
        <div class="f-row">${f('Time','schedule.'+i+'.time',s.time)}${f('Event','schedule.'+i+'.event',s.event)}</div>
      </div>
    </div>`).join('');
}
function addSC(){ if(!cfg.schedule) cfg.schedule=[]; cfg.schedule.push({time:'',event:''}); dirty(); document.getElementById('scl').innerHTML=rSCL(); }
function rmSC(i){ cfg.schedule.splice(i,1); dirty(); document.getElementById('scl').innerHTML=rSCL(); }
function mvSC(i,d){ const a=cfg.schedule,j=i+d; if(j<0||j>=a.length)return; [a[i],a[j]]=[a[j],a[i]]; dirty(); document.getElementById('scl').innerHTML=rSCL(); }

function tFaq(){
  return `<div class="sh">FAQ</div>
    <div id="fql">${rFQL()}</div>
    <button onclick="addFQ()" class="btn btn-add">+ Add Q&amp;A</button>`;
}
function rFQL(){
  const fq=cfg.faq||[];
  if(!fq.length) return '<p style="color:var(--muted);font-size:.85rem;margin-bottom:.5rem">No items.</p>';
  return fq.map((item,i)=>`
    <div class="card">
      <div class="card-h">
        <strong style="font-size:.82rem">${H(item.q||'Untitled')}</strong>
        <div class="card-acts">
          <button class="btn-xs" onclick="mvFQ(${i},-1)" ${i===0?'disabled':''}>↑</button>
          <button class="btn-xs" onclick="mvFQ(${i},1)"  ${i===fq.length-1?'disabled':''}>↓</button>
          <button class="btn-rm" onclick="rmFQ(${i})">Remove</button>
        </div>
      </div>
      <div class="card-b">
        ${f('Question','faq.'+i+'.q',item.q)}
        ${f('Answer','faq.'+i+'.a',item.a,'textarea')}
      </div>
    </div>`).join('');
}
function addFQ(){ if(!cfg.faq) cfg.faq=[]; cfg.faq.push({q:'',a:''}); dirty(); document.getElementById('fql').innerHTML=rFQL(); }
function rmFQ(i){ cfg.faq.splice(i,1); dirty(); document.getElementById('fql').innerHTML=rFQL(); }
function mvFQ(i,d){ const a=cfg.faq,j=i+d; if(j<0||j>=a.length)return; [a[i],a[j]]=[a[j],a[i]]; dirty(); document.getElementById('fql').innerHTML=rFQL(); }

function tFooter(){
  const ft=cfg.footer||{};
  return `<div class="sh">Footer</div>
    <div class="f-row">${f('Email','footer.email',ft.email,'email')}${f('Copyright text','footer.copyright',ft.copyright)}</div>
    <div class="ssh">Social Media Links</div>
    <div id="sol">${rSOL()}</div>
    <button onclick="addSO()" class="btn btn-add">+ Add Social Link</button>`;
}
function rSOL(){
  const ss=cfg.footer?.socials||[];
  if(!ss.length) return '<p style="color:var(--muted);font-size:.85rem;margin-bottom:.5rem">No socials yet.</p>';
  return ss.map((s,i)=>`
    <div class="card">
      <div class="card-h">
        <strong>${H(s.label||'Unnamed')}</strong>
        <div class="card-acts">
          <button class="btn-xs" onclick="mvSO(${i},-1)" ${i===0?'disabled':''}>↑</button>
          <button class="btn-xs" onclick="mvSO(${i},1)"  ${i===ss.length-1?'disabled':''}>↓</button>
          <button class="btn-rm" onclick="rmSO(${i})">Remove</button>
        </div>
      </div>
      <div class="card-b">
        <div class="f-row">${f('Label','footer.socials.'+i+'.label',s.label)}${f('URL','footer.socials.'+i+'.url',s.url)}</div>
      </div>
    </div>`).join('');
}
function addSO(){ if(!cfg.footer) cfg.footer={}; if(!cfg.footer.socials) cfg.footer.socials=[]; cfg.footer.socials.push({label:'',url:''}); dirty(); document.getElementById('sol').innerHTML=rSOL(); }
function rmSO(i){ cfg.footer.socials.splice(i,1); dirty(); document.getElementById('sol').innerHTML=rSOL(); }
function mvSO(i,d){ const a=cfg.footer.socials,j=i+d; if(j<0||j>=a.length)return; [a[i],a[j]]=[a[j],a[i]]; dirty(); document.getElementById('sol').innerHTML=rSOL(); }

function tAdv(){
  const st=cfg.stats||[], cats=cfg.categories||[];
  const statsH=st.map((s,i)=>`
    <div class="card">
      <div class="card-h"><strong>${H(s.label||'Stat '+i)}</strong></div>
      <div class="card-b">
        <div class="f-row">${f('Value','stats.'+i+'.value',s.value)}${f('Label','stats.'+i+'.label',s.label)}</div>
        ${f('Icon key (e.g. clock, users, award)','stats.'+i+'.icon',s.icon||'')}
      </div>
    </div>`).join('');
  const catsH=cats.map((c,i)=>`
    <div class="card">
      <div class="card-h">
        <strong>${H(c.name||'Category')}</strong>
        <div class="card-acts">
          <button class="btn-xs" onclick="mvC(${i},-1)" ${i===0?'disabled':''}>↑</button>
          <button class="btn-xs" onclick="mvC(${i},1)"  ${i===cats.length-1?'disabled':''}>↓</button>
          <button class="btn-rm" onclick="rmC(${i})">Remove</button>
        </div>
      </div>
      <div class="card-b">
        <div class="f-row">${f('Name','categories.'+i+'.name',c.name)}${f('Icon key (e.g. globe, lock)','categories.'+i+'.icon',c.icon)}</div>
        ${f('Description','categories.'+i+'.description',c.description)}
      </div>
    </div>`).join('');
  return `<div class="sh">Advanced</div>
    <div class="ssh">Stats Tiles</div>${statsH}
    <div class="ssh">Challenge Categories</div>
    <div id="cl">${catsH}</div>
    <button onclick="addC()" class="btn btn-add">+ Add Category</button>`;
}
function addC(){ if(!cfg.categories) cfg.categories=[]; cfg.categories.push({name:'',icon:'flag',description:''}); dirty(); tab('adv'); }
function rmC(i){ cfg.categories.splice(i,1); dirty(); tab('adv'); }
function mvC(i,d){ const a=cfg.categories,j=i+d; if(j<0||j>=a.length)return; [a[i],a[j]]=[a[j],a[i]]; dirty(); tab('adv'); }

let _proxies = [];

async function pollProxy(){
  try{
    const r = await fetch('/api/proxy');
    _proxies = await r.json();
    if(cur==='proxy'){
      const el = document.getElementById('proxy-list');
      if(el) el.innerHTML = rProxyList();
    }
  }catch(e){}
}

function tProxy(){
  return `<div class="sh">Proxy Forwardings</div>
    <div id="proxy-list">${rProxyList()}</div>
    <div class="ssh">Start New Forwarding</div>
    <div class="card">
      <div class="card-b">
        <div style="display:grid;grid-template-columns:120px 90px 1fr;gap:.75rem">
          <div class="f"><label>Local Port</label><input type="number" id="px-port" placeholder="8012" min="1024" max="65535" style="width:100%"></div>
          <div class="f"><label>Scheme</label><select id="px-scheme" style="width:100%;background:var(--bg3);border:1px solid var(--border);color:var(--text);border-radius:var(--r);padding:.45rem .7rem;font-size:.875rem"><option value="https">https</option><option value="http">http</option></select></div>
          <div class="f"><label>Target Host</label><input type="text" id="px-host" placeholder="test-example.dev" style="width:100%"></div>
        </div>
        <button onclick="startProxy()" class="btn btn-pri" style="width:100%;margin-top:.4rem">▶ Start Forwarding</button>
      </div>
    </div>`;
}

function rProxyList(){
  if(!_proxies.length) return '<p style="color:var(--muted);font-size:.85rem;margin-bottom:.75rem">(no active forwardings)</p>';
  return _proxies.map(p=>`
    <div class="card" style="margin-bottom:.5rem">
      <div class="card-h">
        <strong style="font-family:monospace">:${p.port} → ${H(p.target)}</strong>
        <div class="card-acts">
          <span style="font-size:.7rem;padding:.15rem .45rem;border-radius:10px;${p.active?'background:rgba(46,160,67,.2);color:#2ea043':'background:rgba(248,81,73,.15);color:#f85149'}">${p.active?'live':'dead'}</span>
          <button class="btn-rm" onclick="stopProxy(${p.port})">Stop</button>
        </div>
      </div>
    </div>`).join('');
}

async function startProxy(){
  const port   = +document.getElementById('px-port').value;
  const scheme = document.getElementById('px-scheme').value;
  const host   = document.getElementById('px-host').value.trim();
  if(!port||!host){ alert('Enter a port and host.'); return; }
  if(port<1024||port>65535){ alert('Port must be 1024–65535.'); return; }
  try{
    const r = await fetch('/api/proxy/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({port,scheme,host})});
    const d = await r.json();
    if(!d.ok){
      const msg = d.error ? 'Proxy failed to start:\\n\\n'+d.error : 'Proxy did not bind the port. Check the log for details.';
      alert(msg);
    } else{ document.getElementById('px-port').value=''; document.getElementById('px-host').value=''; pollProxy(); }
  }catch(e){ alert('Error: '+e.message); }
}

async function stopProxy(port){
  try{
    await fetch('/api/proxy/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({port})});
    pollProxy();
  }catch(e){}
}

loadConfigs().then(() => loadCfg());
</script>
</body>
</html>'''

# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"  {fmt % args}")

    def handle_error(self, request, client_address):
        pass  # suppress client-disconnect noise (WinError 10053, BrokenPipe, etc.)

    def handle(self):
        try:
            super().handle()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def _send(self, code, ctype, body):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, data):
        self._send(code, "application/json", json.dumps(data, ensure_ascii=False))

    def _cfg_name(self) -> str:
        params = parse_qs(urlparse(self.path).query)
        name = params.get("name", ["default"])[0]
        return re.sub(r'[^a-z0-9\-]', '', name.lower()) or "default"

    def _load_configs(self) -> dict:
        if CONFIGS_PATH.exists():
            with open(CONFIGS_PATH, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_configs(self, data: dict):
        with open(CONFIGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/edit":
            self._send(200, "text/html; charset=utf-8", EDITOR_HTML)
            return

        if path == "/api/configs":
            self._json(200, sorted(self._load_configs().keys()))
            return

        if path == "/api/config":
            name = self._cfg_name()
            cfgs = self._load_configs()
            if name not in cfgs:
                self._json(404, {"error": "config not found"}); return
            self._json(200, cfgs[name])
            return

        if path == "/api/proxy":
            self._json(200, _list_proxy_forwardings())
            return

        # static files
        file_path = HERE / path.lstrip("/")
        if file_path.is_dir():
            file_path = file_path / "index.html"
        if file_path.is_file():
            ctype, _ = mimetypes.guess_type(str(file_path))
            self._send(200, ctype or "application/octet-stream", file_path.read_bytes())
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        path   = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)

        if path == "/api/config":
            try:
                name = self._cfg_name()
                cfg  = json.loads(body)
                cfgs = self._load_configs()
                cfgs[name] = cfg
                self._save_configs(cfgs)
                self._json(200, {"ok": True})
            except Exception as e:
                self._json(400, {"error": str(e)})

        elif path == "/api/regenerate":
            try:
                name = self._cfg_name()
                cfg  = json.loads(body) if body.strip() else None
                if cfg:
                    cfgs = self._load_configs()
                    cfgs[name] = cfg
                    self._save_configs(cfgs)
                else:
                    cfg = self._load_configs().get(name, {})
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    generate_pages(cfg)
                self._json(200, {"ok": True, "output": buf.getvalue().strip()})
            except Exception as e:
                self._json(200, {"ok": False, "output": str(e)})

        elif path == "/api/proxy/start":
            import time as _time
            try:
                data   = json.loads(body)
                port   = int(data["port"])
                scheme = data.get("scheme", "https")
                if scheme not in ("http", "https"):
                    scheme = "https"
                host = re.sub(r'^https?://', '', data["host"].strip())
                host = re.sub(r'/.*$', '', host)
                if not host or not (1024 <= port <= 65535):
                    self._json(400, {"error": "invalid port or host"}); return
                PROXY_LOG_DIR.mkdir(parents=True, exist_ok=True)
                err_path = PROXY_LOG_DIR / f"proxy-{port}.log.err"
                log_out = open(PROXY_LOG_DIR / f"proxy-{port}.log", "w")
                log_err = open(err_path, "w")
                target = f"{scheme}://{host}"
                args = [sys.executable, str(HERE / "start.py"), "--proxy-worker", str(port), target]
                proc = subprocess.Popen(args, stdout=log_out, stderr=log_err)
                _proxy_procs[port] = proc
                _time.sleep(1.0)
                alive = proc.poll() is None
                listening = _is_port_listening(port)
                err_text = ""
                if not alive or not listening:
                    log_out.flush(); log_err.flush()
                    try:
                        err_text = err_path.read_text(errors="replace").strip()[-600:]
                    except Exception:
                        pass
                self._json(200, {
                    "ok":        alive and listening,
                    "pid":       proc.pid,
                    "listening": listening,
                    "error":     err_text,
                })
            except Exception as e:
                self._json(500, {"error": str(e)})

        elif path == "/api/proxy/stop":
            try:
                port = int(json.loads(body)["port"])
                if port in _proxy_procs:
                    try:
                        _proxy_procs[port].terminate()
                        _proxy_procs[port].wait(timeout=3)
                    except Exception:
                        try: _proxy_procs[port].kill()
                        except Exception: pass
                    del _proxy_procs[port]
                if _is_port_listening(port):
                    subprocess.run(
                        ["powershell", "-NoProfile", "-Command",
                         f"Stop-Process -Id (Get-NetTCPConnection -LocalPort {port} -State Listen).OwningProcess -Force"],
                        capture_output=True,
                    )
                self._json(200, {"ok": True})
            except Exception as e:
                self._json(500, {"error": str(e)})

        else:
            self._json(404, {"error": "not found"})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def _free_port(port: int):
    """Kill all processes listening on port using netstat (no elevation needed)."""
    import time
    try:
        r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=5)
        pids = set()
        for line in r.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if parts and parts[-1].isdigit():
                    pids.add(parts[-1])
        if not pids:
            return
        for pid in pids:
            result = subprocess.run(
                ["taskkill", "/F", "/PID", pid],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                print(f"  Killed pid {pid} on :{port}")
            else:
                print(f"  Could not kill pid {pid}: {result.stderr.strip()}")
        time.sleep(0.8)
    except Exception as e:
        print(f"  Warning: _free_port failed: {e}")

def _run_proxy_worker(port: int, target: str):
    """Pure-Python reverse proxy. Spawned as a subprocess via --proxy-worker."""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from urllib.request import urlopen, Request
    import ssl

    target = target.rstrip('/')
    _skip_req  = {'host','connection','keep-alive','proxy-authenticate',
                  'proxy-authorization','te','trailers','transfer-encoding','upgrade'}
    _skip_resp = {'transfer-encoding','connection','keep-alive'}
    ctx = ssl.create_default_context() if target.startswith('https') else None

    class _Handler(BaseHTTPRequestHandler):
        def do_request(self):
            url  = target + self.path
            hdrs = {k: v for k, v in self.headers.items() if k.lower() not in _skip_req}
            hdrs['Host'] = target.split('://', 1)[-1]
            length = int(self.headers.get('Content-Length', 0) or 0)
            body = self.rfile.read(length) if length else None
            try:
                req  = Request(url, data=body, headers=hdrs, method=self.command)
                resp = urlopen(req, context=ctx, timeout=30)
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in _skip_resp:
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp.read())
            except Exception as exc:
                try:
                    self.send_response(502)
                    self.send_header('Content-Type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(f'Proxy error: {exc}'.encode())
                except Exception:
                    pass

        do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = do_request

        def log_message(self, fmt, *args):
            print(f'[proxy:{port}] ' + fmt % args, flush=True)

    print(f'[proxy] listening on :{port} -> {target}', flush=True)
    HTTPServer(('', port), _Handler).serve_forever()


def main():
    import time
    _free_port(PORT)
    url = f"http://localhost:{PORT}"
    print(f"\n  Config Editor  →  {url}/edit")
    print(f"  Page preview   →  {url}/")
    print(f"  Lab preview    →  {url}/lab-question/")
    print(f"  Ctrl+C to stop\n")
    # retry binding a few times in case OS hasn't released the port yet
    server = None
    for attempt in range(6):
        try:
            server = HTTPServer(("", PORT), Handler)
            break
        except OSError as e:
            if attempt < 5:
                print(f"  Port {PORT} busy, retrying ({attempt+1}/5)…")
                time.sleep(0.5)
            else:
                print(f"  Could not bind to port {PORT}: {e}")
                sys.exit(1)
    threading.Timer(0.8, lambda: webbrowser.open(f"{url}/edit")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--proxy-worker":
        _run_proxy_worker(int(sys.argv[2]), sys.argv[3])
    else:
        main()
