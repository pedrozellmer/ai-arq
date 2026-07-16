# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
"""
Gera index.html do blog + posts individuais a partir de posts.json.
Cada post fica em /blog/posts/{slug}.html, otimizado pra SEO.
"""
import json
import os
from datetime import datetime, date

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_URL = "https://ai.arq.br"

with open(os.path.join(THIS_DIR, "posts.json"), "r", encoding="utf-8") as f:
    DATA = json.load(f)

POSTS = DATA["posts"]


# ─── Common HTML head/footer ─────────────────────────────────────────────
COMMON_STYLES = '''
<style>
  body { font-family: 'Inter', sans-serif; }
  .gradient-main { background: linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%); }
  .gradient-text { background: linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
  .prose-aiarq h2 { font-size: 1.75rem; font-weight: 700; color: #0f172a; margin-top: 2.5rem; margin-bottom: 1rem; line-height: 1.3; }
  .prose-aiarq h3 { font-size: 1.25rem; font-weight: 600; color: #1e293b; margin-top: 2rem; margin-bottom: .75rem; }
  .prose-aiarq p { font-size: 1.0625rem; line-height: 1.75; color: #334155; margin-bottom: 1.25rem; }
  .prose-aiarq ul, .prose-aiarq ol { margin-bottom: 1.5rem; padding-left: 1.75rem; }
  .prose-aiarq ul li { font-size: 1.0625rem; line-height: 1.75; color: #334155; margin-bottom: .5rem; list-style: disc; }
  .prose-aiarq ol li { font-size: 1.0625rem; line-height: 1.75; color: #334155; margin-bottom: .5rem; list-style: decimal; }
  .prose-aiarq strong { color: #0f172a; font-weight: 600; }
  .prose-aiarq a { color: #4f46e5; text-decoration: underline; }
  .prose-aiarq a:hover { color: #4338ca; }
  /* Cards de download: tira sublinhado e força cor do gray-900 */
  .prose-aiarq .aiarq-dl-btn { text-decoration: none !important; color: #111827 !important; }
  .prose-aiarq .aiarq-dl-btn:hover { text-decoration: none !important; }
  /* Bloco de fontes: lista mais densa, sem disc */
  .aiarq-sources ul li { list-style: none; line-height: 1.5; padding: 0; margin: 0; }
  .aiarq-sources ul { margin: 0; padding: 0; }
  html { scroll-behavior: smooth; }
</style>
'''

NAV = '''
<nav class="sticky top-0 z-50 border-b bg-white/90 backdrop-blur-md">
  <div class="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
    <a href="/" class="flex items-center gap-2 no-underline">
      <div class="flex h-9 w-9 items-center justify-center rounded-lg gradient-main text-white font-bold text-sm">AI</div>
      <span class="text-xl font-bold text-gray-900">AI<span class="gradient-text">.arq</span></span>
    </a>
    <div class="hidden md:flex items-center gap-8 text-sm text-gray-600">
      <a href="/#como-funciona" class="hover:text-indigo-600 transition">Como Funciona</a>
      <a href="/precos.html" class="hover:text-indigo-600 transition">Planos</a>
      <a href="/blog/" class="text-indigo-600 font-medium transition">Blog</a>
      <a href="/faq.html" class="hover:text-indigo-600 transition">FAQ</a>
    </div>
    <div class="flex items-center gap-3">
      <a href="/login.html" class="text-sm text-gray-600 hover:text-gray-900 px-3 py-2 rounded-lg hover:bg-gray-100 transition">Entrar</a>
      <a href="/login.html?novo=1" class="text-sm gradient-main text-white px-4 py-2 rounded-lg font-medium transition shadow-sm">Comece Grátis</a>
    </div>
  </div>
</nav>
'''

FOOTER = '''
<footer class="border-t bg-gray-50 mt-20">
  <div class="mx-auto max-w-6xl px-4 py-12 grid gap-8 md:grid-cols-4">
    <div>
      <div class="flex items-center gap-2 mb-3">
        <div class="flex h-8 w-8 items-center justify-center rounded-lg gradient-main text-white font-bold text-xs">AI</div>
        <span class="text-lg font-bold text-gray-900">AI<span class="gradient-text">.arq</span></span>
      </div>
      <p class="text-sm text-gray-500">Quantitativo de obra com IA, em 5 minutos.</p>
    </div>
    <div>
      <h4 class="text-sm font-semibold text-gray-900 mb-3">Produto</h4>
      <ul class="space-y-2 text-sm text-gray-600">
        <li><a href="/" class="hover:text-indigo-600">Início</a></li>
        <li><a href="/#como-funciona" class="hover:text-indigo-600">Como funciona</a></li>
        <li><a href="/precos.html" class="hover:text-indigo-600">Preços</a></li>
        <li><a href="/login.html" class="hover:text-indigo-600">Entrar</a></li>
      </ul>
    </div>
    <div>
      <h4 class="text-sm font-semibold text-gray-900 mb-3">Conteúdo</h4>
      <ul class="space-y-2 text-sm text-gray-600">
        <li><a href="/blog/" class="hover:text-indigo-600">Blog</a></li>
        <li><a href="/faq.html" class="hover:text-indigo-600">FAQ</a></li>
        <li><a href="javascript:void(0)" onclick="aiArqContactOpen()" class="hover:text-indigo-600">Contato</a></li>
      </ul>
    </div>
    <div>
      <h4 class="text-sm font-semibold text-gray-900 mb-3">Legal</h4>
      <ul class="space-y-2 text-sm text-gray-600">
        <li><a href="/termos.html" class="hover:text-indigo-600">Termos</a></li>
        <li><a href="/privacidade.html" class="hover:text-indigo-600">Privacidade</a></li>
      </ul>
    </div>
  </div>
  <div class="border-t bg-gray-100">
    <div class="mx-auto max-w-6xl px-4 py-4 text-center text-xs text-gray-500">
      &copy; 2026 AI.arq · Quantitativo com IA pra arquitetos brasileiros
      <span class="ml-2 text-gray-400">· v0.5.0 Beta</span>
    </div>
  </div>
</footer>
'''


import re
NUMBERED_RE = re.compile(r'^\d+[\.\)]\s+(.+)$')
BULLET_RE   = re.compile(r'^[\-\u2022]\s+(.+)$')


def _classify_line(line):
    """Retorna ('numbered'|'bullet'|'text', texto_limpo)."""
    s = line.strip()
    m = NUMBERED_RE.match(s)
    if m:
        return ('numbered', m.group(1))
    m = BULLET_RE.match(s)
    if m:
        return ('bullet', m.group(1))
    return ('text', s)


DOWNLOAD_BUTTONS_HTML = '''
<div class="aiarq-downloads my-8 p-6 rounded-2xl border border-gray-200 bg-gray-50">
  <div class="grid gap-3 sm:grid-cols-2">
    <a href="/blog/downloads/memorial-descritivo-obra-modelo.pdf" download
       class="aiarq-dl-btn flex items-center gap-4 p-4 rounded-xl bg-white border border-gray-200 hover:border-indigo-400 hover:shadow-md transition no-underline">
      <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-red-50 text-red-600 font-bold text-xs">PDF</div>
      <div class="flex-1 min-w-0">
        <div class="font-semibold text-gray-900 leading-tight">Modelo em PDF</div>
        <div class="text-xs text-gray-500 mt-0.5">Pra ler e imprimir · 328 KB</div>
      </div>
      <svg class="w-5 h-5 text-gray-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
    </a>
    <a href="/blog/downloads/memorial-descritivo-obra-modelo.docx" download
       class="aiarq-dl-btn flex items-center gap-4 p-4 rounded-xl bg-white border border-gray-200 hover:border-indigo-400 hover:shadow-md transition no-underline">
      <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 font-bold text-xs">DOCX</div>
      <div class="flex-1 min-w-0">
        <div class="font-semibold text-gray-900 leading-tight">Modelo editável (Word)</div>
        <div class="text-xs text-gray-500 mt-0.5">Pra editar no Word/Docs · 40 KB</div>
      </div>
      <svg class="w-5 h-5 text-gray-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
    </a>
  </div>
</div>
'''


def _flush_buffer(buf, kind, body_html):
    """Empurra o buffer atual como p/ul/ol e zera."""
    if not buf:
        return body_html
    if kind == 'numbered':
        body_html += "<ol>" + "".join(f"<li>{t}</li>" for t in buf) + "</ol>"
    elif kind == 'bullet':
        body_html += "<ul>" + "".join(f"<li>{t}</li>" for t in buf) + "</ul>"
    else:
        # Junta as linhas de texto num parágrafo só
        body_html += "<p>" + " ".join(buf) + "</p>"
    return body_html


def render_section(s):
    """Renderiza uma seção (h2 + body).

    Parser:
    1. Split por \\n\\n (parágrafos visuais)
    2. Classifica cada parágrafo: text / numbered / bullet / download
    3. Renderiza, MESCLANDO parágrafos consecutivos do mesmo tipo de lista.
    4. Texto continua como parágrafos separados (visual normal).
    """
    body_html = ""
    paragraphs = s["body"].split("\n\n")

    # 1ª passada: classifica cada parágrafo + extrai linhas
    blocks = []  # lista de tuplas (kind, list_de_textos)
    for p in paragraphs:
        if p.strip() == "<DOWNLOAD_BUTTONS>":
            blocks.append(("download", []))
            continue
        lines = [l for l in p.strip().split("\n") if l.strip()]
        if not lines:
            continue

        # Classifica cada linha do parágrafo
        classified = [_classify_line(l) for l in lines]
        kinds = {k for k, _ in classified}

        if kinds == {'numbered'}:
            blocks.append(("numbered", [t for _, t in classified]))
        elif kinds == {'bullet'}:
            blocks.append(("bullet", [t for _, t in classified]))
        else:
            # Misto ou só texto: subdivide em sub-blocos
            buf = []
            cur_kind = None
            for kind, txt in classified:
                if cur_kind is None:
                    cur_kind = kind
                    buf = [txt]
                elif kind == cur_kind:
                    buf.append(txt)
                else:
                    blocks.append((cur_kind, buf))
                    cur_kind = kind
                    buf = [txt]
            if buf:
                blocks.append((cur_kind, buf))

    # 2ª passada: mescla blocos consecutivos de lista da mesma natureza
    merged = []
    for kind, items in blocks:
        if merged and merged[-1][0] == kind and kind in ('numbered', 'bullet'):
            merged[-1] = (kind, merged[-1][1] + items)
        else:
            merged.append((kind, items))

    # 3ª passada: renderiza
    for kind, items in merged:
        if kind == "download":
            body_html += DOWNLOAD_BUTTONS_HTML
        elif kind == "numbered":
            body_html += "<ol>" + "".join(f"<li>{t}</li>" for t in items) + "</ol>"
        elif kind == "bullet":
            body_html += "<ul>" + "".join(f"<li>{t}</li>" for t in items) + "</ul>"
        else:
            # Cada bloco de texto vira um <p> próprio
            body_html += "<p>" + " ".join(items) + "</p>"

    return f"<h2>{s['h2']}</h2>{body_html}"


def calc_read_time(post):
    """Calcula tempo de leitura real baseado em 220 palavras/min."""
    text = post.get("intro", "") + " "
    for s in post.get("sections", []):
        text += s.get("body", "") + " "
    text += post.get("cta", "")
    # remove placeholder
    text = text.replace("<DOWNLOAD_BUTTONS>", "")
    words = len(text.split())
    minutes = max(1, round(words / 220))
    return minutes


def render_sources(sources):
    """Renderiza bloco de fontes no rodapé do post."""
    if not sources:
        return ""

    # Agrupa por tipo pra mostrar em seções. "norm" cobre tanto NBR ABNT quanto
    # leis/acórdãos/resoluções — separados em dois blocos pra não rotular tudo
    # como "Normas ABNT" (que estaria errado pra uma Lei ou Acórdão).
    norms = [s for s in sources if s.get("type") == "norm"]
    abnt = [s for s in norms if "NBR" in (s.get("title", "") or "").upper()]
    legal = [s for s in norms if s not in abnt]
    books = [s for s in sources if s.get("type") == "book"]
    links = [s for s in sources if s.get("type", "link") in ("link", "official")]

    items_html = ""

    def _render_norm_group(group, header):
        out = f'<div class="mb-4"><div class="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">{header}</div><ul class="space-y-1.5 text-sm text-gray-700">'
        for src in group:
            cite = f'<strong>{src["title"]}</strong>'
            if src.get("description"):
                cite += f' &mdash; <span class="text-gray-600">{src["description"]}</span>'
            out += f'<li>{cite}</li>'
        out += '</ul></div>'
        return out

    if abnt:
        items_html += _render_norm_group(abnt, "Normas ABNT")
    if legal:
        items_html += _render_norm_group(legal, "Leis e Atos Normativos")

    if books:
        items_html += '<div class="mb-4"><div class="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Livros e Manuais</div><ul class="space-y-1.5 text-sm text-gray-700">'
        for src in books:
            cite = f'<strong>{src["title"]}</strong>'
            if src.get("author"):
                cite += f' &mdash; {src["author"]}'
            meta_parts = []
            if src.get("publisher"):
                meta_parts.append(src["publisher"])
            if src.get("year"):
                meta_parts.append(str(src["year"]))
            if meta_parts:
                cite += f' <span class="text-gray-500">({", ".join(meta_parts)})</span>'
            items_html += f'<li>{cite}</li>'
        items_html += '</ul></div>'

    if links:
        items_html += '<div><div class="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">Web</div><ul class="space-y-1.5 text-sm text-gray-700">'
        for src in links:
            link = f'<a href="{src["url"]}" target="_blank" rel="noopener nofollow" class="text-indigo-600 hover:text-indigo-800">{src["title"]}</a>'
            if src.get("publisher"):
                link += f' <span class="text-gray-500">&middot; {src["publisher"]}</span>'
            items_html += f'<li>{link}</li>'
        items_html += '</ul></div>'

    return f'''
    <aside class="aiarq-sources mt-12 p-6 rounded-2xl bg-gray-50 border border-gray-200">
      <h3 class="flex items-center gap-2 text-sm font-bold text-gray-900 uppercase tracking-wide mb-5">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"/></svg>
        Fontes &amp; Referências
      </h3>
      {items_html}
      <p class="mt-4 text-xs text-gray-400 italic">
        Última atualização: {datetime.now().strftime('%d/%m/%Y')}. Normas ABNT podem ter sido revisadas após esta data — sempre consulte a versão vigente.
      </p>
    </aside>
    '''


def pick_related_posts(post, n=3):
    """Escolhe até n posts relacionados pra linkar no fim de um post.

    Regra:
    1. Só posts JÁ publicados (publish_date <= hoje) — links pra posts futuros
       seriam redirecionados pelo guard JS, viram link morto pro SEO.
    2. Nunca o próprio post.
    3. Prioriza a MESMA categoria, do mais recente pro mais antigo.
    4. Se a categoria não tem n posts, completa com os mais recentes de
       qualquer categoria.
    """
    today = date.today().isoformat()
    candidates = [
        p for p in POSTS
        if p["slug"] != post["slug"] and p["publish_date"] <= today
    ]
    # Mais recente primeiro
    candidates.sort(key=lambda p: p["publish_date"], reverse=True)

    same_cat = [p for p in candidates if p["category"] == post["category"]]
    others = [p for p in candidates if p["category"] != post["category"]]

    ordered = same_cat + others
    return ordered[:n]


def render_related_posts(post):
    """Renderiza o bloco 'Leia também' com links reais pra posts irmãos."""
    related = pick_related_posts(post, 3)
    if not related:
        return ""

    cards = ""
    for rp in related:
        rp_url = f"/blog/posts/{rp['slug']}.html"
        cards += f'''
        <a href="{rp_url}" class="aiarq-related-card block p-5 rounded-xl bg-white border border-gray-200 hover:border-indigo-400 hover:shadow-md transition no-underline">
          <span class="inline-block bg-indigo-100 text-indigo-700 text-xs font-semibold uppercase tracking-wide px-2.5 py-1 rounded-full mb-3">{rp["category"]}</span>
          <div class="font-semibold text-gray-900 leading-snug">{rp["title"]}</div>
        </a>'''

    return f'''
    <section class="aiarq-related mt-16 pt-8 border-t border-gray-200">
      <h2 class="flex items-center gap-2 text-lg font-bold text-gray-900 mb-5">
        <svg class="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/></svg>
        Leia também
      </h2>
      <div class="grid gap-4 sm:grid-cols-3">
        {cards}
      </div>
    </section>
    '''


def render_post_html(post):
    """Gera HTML completo de um post."""
    sections_html = "".join(render_section(s) for s in post["sections"])

    # Adiciona bloco de fontes no fim, se houver
    sources_html = render_sources(post.get("sources", []))

    # Bloco "Leia também" — internal linking entre posts irmãos (SEO)
    related_html = render_related_posts(post)

    # Recalcula tempo de leitura baseado nas palavras reais
    post["estimated_read_min"] = calc_read_time(post)

    publish_date_iso = f'{post["publish_date"]}T10:00:00-03:00'
    publish_date_br = datetime.fromisoformat(post["publish_date"]).strftime("%d/%m/%Y")

    canonical_url = f"{SITE_URL}/blog/posts/{post['slug']}.html"

    # Schema.org Article (JSON-LD) — boost SEO
    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": post["title"],
        "description": post["description"],
        "datePublished": publish_date_iso,
        "dateModified": publish_date_iso,
        "author": {"@type": "Organization", "name": "AI.arq"},
        "publisher": {
            "@type": "Organization",
            "name": "AI.arq",
            "logo": {"@type": "ImageObject", "url": f"{SITE_URL}/favicon.png"}
        },
        "image": f"{SITE_URL}/og-image.png",
        "url": canonical_url,
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical_url},
        "keywords": post["keywords"],
        "articleSection": post["category"],
    }

    return f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preconnect" href="https://cdn.tailwindcss.com">

<title>{post["title"]} | AI.arq</title>
<meta name="description" content="{post["description"]}">
<meta name="keywords" content="{post["keywords"]}">
<meta name="author" content="AI.arq">

<link rel="canonical" href="{canonical_url}">
<link rel="icon" type="image/x-icon" href="/favicon.ico">

<!-- Open Graph -->
<meta property="og:type" content="article">
<meta property="og:url" content="{canonical_url}">
<meta property="og:title" content="{post["title"]}">
<meta property="og:description" content="{post["description"]}">
<meta property="og:image" content="{SITE_URL}/og-image.png">
<meta property="og:locale" content="pt_BR">
<meta property="og:site_name" content="AI.arq">
<meta property="article:published_time" content="{publish_date_iso}">
<meta property="article:author" content="AI.arq">
<meta property="article:section" content="{post["category"]}">

<!-- Twitter -->
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{post["title"]}">
<meta name="twitter:description" content="{post["description"]}">
<meta name="twitter:image" content="{SITE_URL}/og-image.png">

<!-- Data agendada (lida por JS pra esconder antes da hora) -->
<meta name="publish-date" content="{post["publish_date"]}">

<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" rel="stylesheet">
{COMMON_STYLES}

<script type="application/ld+json">
{json.dumps(schema, ensure_ascii=False, indent=2)}
</script>
</head>
<body class="bg-white text-gray-900 antialiased">

{NAV}

<!-- Guard JS: se publish_date > hoje, redireciona pra /blog -->
<script>
(function () {{
  const meta = document.querySelector('meta[name="publish-date"]');
  if (!meta) return;
  const pubDate = new Date(meta.content + 'T10:00:00-03:00');
  if (pubDate > new Date()) {{
    document.documentElement.style.display = 'none';
    window.location.replace('/blog/');
  }}
}})();
</script>

<article class="mx-auto max-w-3xl px-4 py-12">
  <!-- Breadcrumb -->
  <nav class="text-sm text-gray-500 mb-6">
    <a href="/" class="hover:text-indigo-600">Início</a>
    <span class="mx-2">›</span>
    <a href="/blog/" class="hover:text-indigo-600">Blog</a>
    <span class="mx-2">›</span>
    <span class="text-gray-700">{post["category"]}</span>
  </nav>

  <!-- Categoria -->
  <span class="inline-block bg-indigo-100 text-indigo-700 text-xs font-semibold uppercase tracking-wide px-3 py-1 rounded-full mb-4">{post["category"]}</span>

  <!-- Título -->
  <h1 class="text-3xl md:text-4xl font-bold text-gray-900 leading-tight mb-4">{post["title"]}</h1>

  <!-- Meta -->
  <div class="flex items-center gap-4 text-sm text-gray-500 mb-10 pb-6 border-b">
    <span>📅 {publish_date_br}</span>
    <span>·</span>
    <span>⏱️ {post["estimated_read_min"]} min de leitura</span>
  </div>

  <!-- Intro destacada -->
  <p class="text-xl text-gray-700 leading-relaxed mb-8 italic">{post["intro"]}</p>

  <!-- Corpo -->
  <div class="prose-aiarq">
    {sections_html}
  </div>

  <!-- CTA -->
  <div class="mt-12 p-8 rounded-2xl bg-gradient-to-br from-indigo-50 to-cyan-50 border-2 border-indigo-100">
    <h3 class="text-xl font-bold text-gray-900 mb-3">⚡ Pronto pra acelerar seu trabalho?</h3>
    <p class="text-gray-700 mb-5">{post["cta"]}</p>
    <a href="/login.html?novo=1" class="inline-flex items-center gap-2 gradient-main text-white font-semibold px-6 py-3 rounded-xl no-underline shadow-btn">
      Começar grátis
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 8l4 4m0 0l-4 4m4-4H3"/></svg>
    </a>
    <p class="mt-3 text-xs text-gray-500">Primeiro projeto grátis. Sem cartão.</p>
  </div>

  {sources_html}

  <!-- Leia também (posts relacionados) -->
  {related_html}

  <!-- Voltar ao blog -->
  <div class="mt-12 text-center">
    <a href="/blog/" class="text-indigo-600 hover:text-indigo-800 font-medium no-underline">← Ver mais artigos</a>
  </div>
</article>

{FOOTER}

<!-- Chat widget + Modal de contato (compartilhados com o resto do site) -->
<script src="/chat-widget.js"></script>
<script src="/contact-modal.js"></script>
<script src="/cookie-consent.js" defer></script>
</body>
</html>'''


def render_index_html():
    """Gera o index.html do blog que lista todos os posts visíveis."""
    today = date.today().isoformat()

    # Recalcula tempo de leitura de todos
    for post in POSTS:
        post["estimated_read_min"] = calc_read_time(post)

    # Constrói cards (server-side filtrado por data ainda — JS adiciona filtro extra)
    cards_html = ""
    for post in sorted(POSTS, key=lambda p: p["publish_date"], reverse=True):
        publish_date_br = datetime.fromisoformat(post["publish_date"]).strftime("%d/%m/%Y")
        is_future = post["publish_date"] > today
        future_class = ' data-future="true" style="display:none"' if is_future else ''

        cards_html += f'''
        <article{future_class} class="post-card group rounded-2xl border bg-white p-6 shadow-sm hover:shadow-lg transition cursor-pointer" data-publish-date="{post["publish_date"]}" onclick="window.location='/blog/posts/{post["slug"]}.html'">
          <span class="inline-block bg-indigo-100 text-indigo-700 text-xs font-semibold uppercase tracking-wide px-2.5 py-1 rounded-full mb-3">{post["category"]}</span>
          <h2 class="text-xl font-bold text-gray-900 mb-2 group-hover:text-indigo-600 transition leading-tight">{post["title"]}</h2>
          <p class="text-sm text-gray-600 leading-relaxed mb-4">{post["description"]}</p>
          <div class="flex items-center justify-between text-xs text-gray-500">
            <span>📅 {publish_date_br}</span>
            <span>⏱️ {post["estimated_read_min"]} min</span>
          </div>
        </article>
        '''

    return f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="preconnect" href="https://cdn.tailwindcss.com">

<title>Blog AI.arq — Quantitativos, SINAPI e BDI pra arquitetos</title>
<meta name="description" content="Artigos práticos sobre planilha de quantitativos, SINAPI, TCPO, BDI e memorial descritivo. Conteúdo gratuito pra arquitetos e engenheiros brasileiros.">
<meta name="keywords" content="blog arquitetura, planilha quantitativos, sinapi, tcpo, bdi, memorial descritivo, ia arquitetura">

<link rel="canonical" href="{SITE_URL}/blog/">
<link rel="icon" type="image/x-icon" href="/favicon.ico">

<meta property="og:type" content="website">
<meta property="og:url" content="{SITE_URL}/blog/">
<meta property="og:title" content="Blog AI.arq — Quantitativos, SINAPI, IA na arquitetura">
<meta property="og:description" content="Conteúdo prático sobre quantitativos de obra, SINAPI, TCPO, BDI e IA aplicada à arquitetura.">
<meta property="og:image" content="{SITE_URL}/og-image.png">

<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" rel="stylesheet">
{COMMON_STYLES}
</head>
<body class="bg-gray-50 text-gray-900 antialiased">

{NAV}

<!-- Hero do blog -->
<header class="bg-white border-b">
  <div class="mx-auto max-w-6xl px-4 py-16 text-center">
    <span class="inline-block mb-4 bg-indigo-100 text-indigo-700 text-sm font-medium px-4 py-1.5 rounded-full">Blog AI.arq</span>
    <h1 class="text-4xl md:text-5xl font-bold text-gray-900 mb-4">Conteúdo prático pra arquitetos brasileiros</h1>
    <p class="text-lg text-gray-600 max-w-2xl mx-auto">Quantitativos, SINAPI, TCPO, BDI, memorial descritivo, IA aplicada à arquitetura. Tudo gratuito, escrito direto ao ponto.</p>
  </div>
</header>

<!-- Listagem -->
<main class="mx-auto max-w-6xl px-4 py-12">
  <div id="post-grid" class="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
    {cards_html}
  </div>

  <!-- Aviso quando não há posts (raro) -->
  <div id="no-posts" class="hidden text-center py-20 text-gray-500">
    <p>Em breve teremos novos artigos. Volta aqui em alguns dias!</p>
  </div>
</main>

{FOOTER}

<!-- JS: filtra posts cuja data > hoje (sincroniza com client time se houver desvio) -->
<script>
(function () {{
  const today = new Date();
  const cards = document.querySelectorAll('.post-card');
  let visible = 0;
  cards.forEach(c => {{
    const pubDate = new Date(c.dataset.publishDate + 'T10:00:00-03:00');
    if (pubDate > today) {{
      c.style.display = 'none';
    }} else {{
      c.style.display = '';
      visible++;
    }}
  }});
  if (visible === 0) {{
    document.getElementById('no-posts').classList.remove('hidden');
    document.getElementById('post-grid').classList.add('hidden');
  }}
}})();
</script>

<!-- Chat widget + Modal de contato -->
<script src="/chat-widget.js"></script>
<script src="/contact-modal.js"></script>
<script src="/cookie-consent.js" defer></script>
</body>
</html>'''


def render_sitemap():
    """Gera sitemap.xml com URLs do site, incluindo só posts já publicados."""
    today = date.today().isoformat()
    urls = [
        (f"{SITE_URL}/", "1.0", "weekly"),
        (f"{SITE_URL}/precos.html", "0.9", "weekly"),
        (f"{SITE_URL}/exemplo.html", "0.8", "monthly"),
        (f"{SITE_URL}/blog/", "0.9", "weekly"),
        (f"{SITE_URL}/faq.html", "0.7", "monthly"),
        (f"{SITE_URL}/termos.html", "0.3", "yearly"),
        (f"{SITE_URL}/privacidade.html", "0.3", "yearly"),
    ]
    for post in POSTS:
        if post["publish_date"] <= today:
            urls.append((
                f"{SITE_URL}/blog/posts/{post['slug']}.html",
                "0.8",
                "monthly",
            ))

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for url, priority, freq in urls:
        xml += f'  <url>\n'
        xml += f'    <loc>{url}</loc>\n'
        xml += f'    <changefreq>{freq}</changefreq>\n'
        xml += f'    <priority>{priority}</priority>\n'
        xml += f'  </url>\n'
    xml += '</urlset>\n'
    return xml


def render_robots():
    # Auditoria SEO 2026-05-23: páginas auth não devem indexar (canibalizam
    # home com thin content). Páginas pós-login expostas no robots não
    # acrescentam nada porque exigem JWT.
    return f'''User-agent: *
Allow: /

# Páginas pós-login: não indexar (thin content, exigem auth)
Disallow: /admin.html
Disallow: /admin/
Disallow: /dashboard.html
Disallow: /projeto.html
Disallow: /revisao.html
Disallow: /cronograma.html
Disallow: /meus-projetos.html
Disallow: /visualizar-prancha.html

# Páginas de autenticação: não indexar (canibalizam home)
Disallow: /login.html
Disallow: /cadastro.html

# Diretórios técnicos
Disallow: /_*
Disallow: /backend/

Sitemap: {SITE_URL}/sitemap.xml
'''


def main():
    posts_dir = os.path.join(THIS_DIR, "posts")
    os.makedirs(posts_dir, exist_ok=True)

    # Gera HTML de cada post
    for post in POSTS:
        html = render_post_html(post)
        path = os.path.join(posts_dir, f"{post['slug']}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"✓ posts/{post['slug']}.html")

    # Gera index.html do blog
    with open(os.path.join(THIS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_index_html())
    print("✓ blog/index.html")

    # Gera sitemap.xml na raiz do site
    sitemap_path = os.path.join(THIS_DIR, "..", "sitemap.xml")
    with open(sitemap_path, "w", encoding="utf-8") as f:
        f.write(render_sitemap())
    print("✓ sitemap.xml")

    # Gera robots.txt na raiz
    robots_path = os.path.join(THIS_DIR, "..", "robots.txt")
    with open(robots_path, "w", encoding="utf-8") as f:
        f.write(render_robots())
    print("✓ robots.txt")

    print(f"\n✅ Total: {len(POSTS)} posts gerados")


if __name__ == "__main__":
    main()
