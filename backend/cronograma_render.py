# -*- coding: utf-8 -*-
"""NÚCLEO do novo export de cronograma (AI.arq) — HTML → PDF/PNG.

Pipeline:
  build_context(cronograma, branding, template)  → dict de contexto (contrato fixo)
  montar_html(...)                               → Jinja2 renderiza documento.html.j2,
                                                   depois resolver_color_mix() troca
                                                   os color-mix()/var(--accent) por cores
                                                   concretas (WeasyPrint NÃO suporta color-mix)
  render_pdf_bytes(...)                           → WeasyPrint HTML→PDF (5 páginas A4 paisagem)
  render_png_paginas(pdf_bytes)                   → pypdfium2 rasteriza cada página → PNG (pro PPTX)

Arquitetura-chave: os templates das páginas mantêm o CSS das referências
PRATICAMENTE VERBATIM (inclusive var(--accent), var(--p-*) e color-mix(...)).
Este módulo injeta :root{--accent:<hex>} e o pacote --p-* da direção no wrapper,
e faz um passe pós-Jinja que resolve todo color-mix() e var(--accent) solto.

Tudo defensivo: qualquer falha degrada com segurança, nunca derruba o processo.
"""
from __future__ import annotations

import os
import io
import re
import base64
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────
#  Constantes de geometria (sistema de coordenadas das referências)
# ─────────────────────────────────────────────────────────────────────
_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "cronograma_templates")

# Curva S — viewBox '0 0 1000 400'; plot x 70..970, y 20 (=100%) .. 360 (=0%)
_CURVA_X0, _CURVA_X1 = 70.0, 970.0
_CURVA_Y_BASE = 360.0            # y de 0%
_CURVA_Y_TOP = 20.0              # y de 100%
_CURVA_H = _CURVA_Y_BASE - _CURVA_Y_TOP   # 340

_ACCENT_DEFAULT = "#4F46E5"

_MESES_PT = ["jan", "fev", "mar", "abr", "mai", "jun",
             "jul", "ago", "set", "out", "nov", "dez"]

# Direções válidas
TEMPLATES_VALIDOS = ("escuro", "blueprint", "claro", "editorial", "bold")

# ─────────────────────────────────────────────────────────────────────
#  Cores das fases no Gantt (18/07): as barras usam a COR REAL de cada
#  fase (paleta "materiais de obra" do cronograma.py) — mesma da tela.
#  Tudo pré-calculado AQUI em hex/rgba concretos: o resolvedor pós-Jinja
#  só entende color-mix com var(--accent), então não criamos mixes novos.
# ─────────────────────────────────────────────────────────────────────
try:
    from cronograma import CATEGORIA_COR, CATEGORIA_LABEL
except Exception:                      # import defensivo (testes isolados)
    CATEGORIA_COR, CATEGORIA_LABEL = {}, {}

_COR_FALLBACK = "#8E8CA8"

def _hex_rgb(h: str) -> Tuple[int, int, int]:
    h = (h or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:
        return 142, 140, 168          # _COR_FALLBACK

def _mix_hex(cor: str, base: str, peso_cor: float) -> str:
    """Mistura `cor` sobre `base` (ex.: 0.15 = 15% da cor). Devolve hex."""
    r1, g1, b1 = _hex_rgb(cor)
    r2, g2, b2 = _hex_rgb(base)
    m = lambda a, b: max(0, min(255, round(a * peso_cor + b * (1 - peso_cor))))
    return f"#{m(r1, r2):02X}{m(g1, g2):02X}{m(b1, b2):02X}"

def _fase_visual(f: Dict, cat: str) -> Dict:
    """cor / texto / tons derivados da fase, prontos pro template."""
    cor = (f.get("cor") or "").strip()
    if not re.match(r"^#[0-9a-fA-F]{6}$", cor):
        cor = CATEGORIA_COR.get(cat, _COR_FALLBACK)
    r, g, b = _hex_rgb(cor)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return {
        "cor": cor,
        "txt": "#1D1B16" if lum > 165 else "#FFFFFF",   # areia/lilás → texto escuro
        "cor_soft": _mix_hex(cor, "#FFFFFF", 0.16),       # fundo suave (blueprint)
        "cor_glow": f"rgba({r},{g},{b},.45)",             # brilho (escuro)
    }


# ─────────────────────────────────────────────────────────────────────
#  PALETAS — pacote --p-* por direção (valores do mestre Cronograma.dc.html)
#  Chaves SEM o prefixo '--' (o documento.html.j2 imprime '--{{k}}:{{v}}').
# ─────────────────────────────────────────────────────────────────────
PALETAS: Dict[str, Dict[str, str]] = {
    "escuro": {
        "p-bg": "#0f1115",
        "p-grid": "none",
        "p-title": "#f5f6f8",
        "p-body": "#c3cad6",
        "p-muted": "#5b6472",
        "p-border": "#23283a",
        "p-card": "rgba(255,255,255,.05)",
        "p-eyebrow": "color-mix(in srgb, var(--accent) 55%, #ffffff)",
        "p-ft": "'Space Grotesk'",
        "p-fb": "'Space Grotesk'",
        "p-fl": "'Space Grotesk'",
        "p-radius": "12px",
        "p-title-weight": "600",
    },
    "blueprint": {
        "p-bg": "#f3f1ea",
        "p-grid": ("linear-gradient(rgba(60,55,44,.06) 1px,transparent 1px),"
                   "linear-gradient(90deg,rgba(60,55,44,.06) 1px,transparent 1px)"),
        "p-title": "#26231c",
        "p-body": "#3a3730",
        "p-muted": "#8a8472",
        "p-border": "#26231c",
        "p-card": "#f7f5ef",
        "p-eyebrow": "var(--accent)",
        "p-ft": "'IBM Plex Sans'",
        "p-fb": "'IBM Plex Sans'",
        "p-fl": "'IBM Plex Mono'",
        "p-radius": "2px",
        "p-title-weight": "600",
    },
    "claro": {
        "p-bg": "#f8f7f4",
        "p-grid": "none",
        "p-title": "#1a1712",
        "p-body": "#44403c",
        "p-muted": "#a8a29a",
        "p-border": "#e7e5df",
        "p-card": "#ffffff",
        "p-eyebrow": "var(--accent)",
        "p-ft": "'Space Grotesk'",
        "p-fb": "'Inter'",
        "p-fl": "'Inter'",
        "p-radius": "16px",
        "p-title-weight": "600",
    },
    "editorial": {
        "p-bg": "#f6f2e9",
        "p-grid": "none",
        "p-title": "#2b2519",
        "p-body": "#6f6857",
        "p-muted": "#a89f8c",
        "p-border": "#d8cfbd",
        "p-card": "#efe9dc",
        "p-eyebrow": "var(--accent)",
        "p-ft": "'Instrument Serif'",
        "p-fb": "'Inter'",
        "p-fl": "'Inter'",
        "p-radius": "6px",
        "p-title-weight": "400",
    },
    "bold": {
        "p-bg": "#fdfcfa",
        "p-grid": "none",
        "p-title": "#141414",
        "p-body": "#5a5a5a",
        "p-muted": "#adadad",
        "p-border": "#ececec",
        "p-card": "#f5f4f2",
        "p-eyebrow": "var(--accent)",
        "p-ft": "'Space Grotesk'",
        "p-fb": "'Space Grotesk'",
        "p-fl": "'Space Grotesk'",
        "p-radius": "16px",
        "p-title-weight": "700",
    },
}

# Cores nomeadas que aparecem nas referências
_NAMED_COLORS = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "transparent": None,  # tratado à parte
}


# ─────────────────────────────────────────────────────────────────────
#  Cor: normalização + mistura sRGB
# ─────────────────────────────────────────────────────────────────────
def _norm_hex(h: Optional[str]) -> str:
    """Normaliza um hex: '#RGB'→'#RRGGBB', valida, minúsculo.
    Retorna _ACCENT_DEFAULT se inválido/vazio."""
    if not h or not isinstance(h, str):
        return _ACCENT_DEFAULT
    h = h.strip().lower()
    if not h.startswith("#"):
        return _ACCENT_DEFAULT
    body = h[1:]
    hexset = set("0123456789abcdef")
    if len(body) == 3 and all(c in hexset for c in body):
        body = "".join(c * 2 for c in body)
    if len(body) == 6 and all(c in hexset for c in body):
        return "#" + body
    return _ACCENT_DEFAULT


def _hex_to_rgb(h: str) -> Tuple[int, int, int]:
    h = _norm_hex(h)[1:]
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _plain_rgb(token: str, accent_hex: str) -> Optional[Tuple[int, int, int]]:
    """Resolve um token de cor 'opaca' pra (r,g,b). None se transparent."""
    t = (token or "").strip().lower()
    if t == "transparent":
        return None
    if t.startswith("var(--accent"):
        return _hex_to_rgb(accent_hex)
    if t.startswith("#"):
        return _hex_to_rgb(t)
    if t in _NAMED_COLORS:
        return _NAMED_COLORS[t]
    # fallback conservador: usa o accent
    return _hex_to_rgb(accent_hex)


def _mix(accent_hex: str, other: str, pct: float) -> str:
    """Mistura linear sRGB por canal: base*pct% + other*(100-pct)%.

    `accent_hex` é a cor base (nome herdado do contrato; funciona com qualquer hex).
    `other` pode ser '#hex', '#fff', 'white'/'black', ou 'transparent'
    (→ rgba(base, pct/100)). Retorna 'rrggbb' hex ou 'rgba(...)'.
    """
    ar, ag, ab = _hex_to_rgb(accent_hex)
    p = max(0.0, min(1.0, pct / 100.0))
    o = (other or "").strip().lower()
    if o == "transparent":
        a = round(p, 4)
        return f"rgba({ar}, {ag}, {ab}, {a})"
    orgb = _plain_rgb(other, accent_hex)
    if orgb is None:  # defensivo
        return f"rgba({ar}, {ag}, {ab}, {round(p,4)})"
    orr, ogg, obb = orgb
    r = round(ar * p + orr * (1 - p))
    g = round(ag * p + ogg * (1 - p))
    b = round(ab * p + obb * (1 - p))
    return f"#{r:02x}{g:02x}{b:02x}"


def _split_top_level(s: str, sep: str = ",") -> List[str]:
    """Divide `s` por `sep` respeitando parênteses aninhados."""
    out, buf, depth = [], [], 0
    for ch in s:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == sep and depth == 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return out


_VAR_ACCENT_RE = re.compile(r"var\(\s*--accent\s*(?:,[^)]*)?\)")


def _resolve_mix_expr(inner: str, accent_hex: str) -> str:
    """Resolve o CONTEÚDO de um color-mix(...) (sem os parênteses externos).
    Espera 'in srgb, <colorA> N%, <colorB>'."""
    try:
        # Neutraliza var(--accent[,...]) dentro (em A e/ou B) pro accent concreto.
        inner = _VAR_ACCENT_RE.sub(accent_hex, inner)
        parts = _split_top_level(inner, ",")
        if len(parts) < 3:
            return accent_hex  # forma inesperada — degrade seguro
        a_with_pct = parts[1].strip()
        b_token = parts[2].strip()
        m = re.match(r"^(.*?)\s+([\d.]+)\s*%$", a_with_pct)
        if not m:
            # às vezes o percentual está no segundo termo — degrade
            return accent_hex
        color_a = m.group(1).strip()
        pct = float(m.group(2))
        if color_a == "transparent":
            rgb = _plain_rgb(b_token, accent_hex)
            if rgb is None:
                return "transparent"
            r, g, b = rgb
            return f"rgba({r}, {g}, {b}, {round((100 - pct) / 100.0, 4)})"
        base_hex = color_a if color_a.startswith("#") else accent_hex
        return _mix(base_hex, b_token, pct)
    except Exception:
        return accent_hex


def resolver_color_mix(html: str, accent_hex: str) -> str:
    """Passe pós-Jinja: troca TODAS as ocorrências de color-mix(...) pela cor
    concreta calculada a partir do accent, e var(--accent[,...]) solto pelo hex.

    Faz varredura com balanceamento de parênteses (color-mix contém var(...)
    aninhado), então funciona inclusive dentro de linear-gradient/radial-gradient.
    """
    accent_hex = _norm_hex(accent_hex)
    if not html:
        return html
    try:
        out: List[str] = []
        i = 0
        needle = "color-mix("
        while True:
            j = html.find(needle, i)
            if j == -1:
                out.append(html[i:])
                break
            out.append(html[i:j])
            # varre parênteses balanceados a partir do '(' de color-mix
            k = j + len("color-mix")  # aponta pro '('
            depth = 0
            start_inner = k + 1
            while k < len(html):
                ch = html[k]
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            if k >= len(html):  # sem fechamento — aborta troca
                out.append(html[j:])
                break
            inner = html[start_inner:k]
            out.append(_resolve_mix_expr(inner, accent_hex))
            i = k + 1
        result = "".join(out)
    except Exception:
        result = html
    # var(--accent) / var(--accent,#...) solto → hex
    try:
        result = _VAR_ACCENT_RE.sub(accent_hex, result)
    except Exception:
        pass
    return result


# ─────────────────────────────────────────────────────────────────────
#  Datas
# ─────────────────────────────────────────────────────────────────────
def _parse_iso(s: Optional[str]) -> Optional[date]:
    if not s or not isinstance(s, str):
        return None
    try:
        return date.fromisoformat(s[:10])
    except Exception:
        return None


def _iso_to_br(s: Optional[str]) -> str:
    d = _parse_iso(s)
    if not d:
        return ""
    return d.strftime("%d/%m/%Y")


def _mes_label(d: date) -> str:
    """jan/26, ago/26, jan/27 — abreviação PT-BR + ano 2 dígitos."""
    return f"{_MESES_PT[d.month - 1]}/{d.year % 100:02d}"


def _mes_label_from_iso(s: Optional[str]) -> str:
    d = _parse_iso(s)
    return _mes_label(d) if d else ""


def _first_of_month(d: date) -> date:
    return date(d.year, d.month, 1)


def _next_month(d: date) -> date:
    y, m = d.year, d.month + 1
    if m > 12:
        y += 1
        m = 1
    return date(y, m, 1)


def _last_day_of_month(d: date) -> date:
    nxt = _next_month(_first_of_month(d))
    return date.fromordinal(nxt.toordinal() - 1)


# ─────────────────────────────────────────────────────────────────────
#  Categorias → 3 baldes de cor do Gantt (estrutura|instalacoes|acabamentos)
# ─────────────────────────────────────────────────────────────────────
def _cat_from_label(label: str) -> str:
    l = (label or "").lower()
    if any(k in l for k in ("elétric", "eletric", "hidrául", "hidraul", "hidr",
                            "incêndio", "incendio", "condicionado", "climat",
                            "gás", " gas", "instalaç", "instalac", "spda",
                            "lógic", "logic", "cabeamento", "dados", "ar-cond")):
        return "instalacoes"
    if any(k in l for k in ("revestimento", "piso", "forro", "pintura",
                            "marcenaria", "mobili", "louç", "louc", "lou ",
                            "metais", "acabamento", "esquadria")):
        return "acabamentos"
    return "estrutura"


def _norm_cat(categoria: Optional[str], label: str) -> str:
    """Normaliza a categoria da engine (7 valores) pros 3 baldes do Gantt.
    Prefere o campo real; cai pro label se ausente."""
    c = (categoria or "").strip().lower()
    if not c:
        return _cat_from_label(label)
    if "instala" in c:
        return "instalacoes"
    if "acabamento" in c:
        return "acabamentos"
    if c in ("estrutura", "preliminares", "vedacoes", "vedações",
             "entrega", "complementares"):
        return "estrutura"
    # valor desconhecido — deriva do label
    return _cat_from_label(label)


def _real_cat(categoria: Optional[str], label: str) -> str:
    """Categoria REAL (1 dos 7 slugs da paleta materiais), pra legenda/cor.
    Diferente de _norm_cat, que colapsa em 3 baldes só pro layout antigo."""
    c = (categoria or "").strip().lower()
    c = c.replace("ç", "c").replace("õ", "o").replace("ã", "a").replace("é", "e")
    if c in CATEGORIA_COR:
        return c
    return _norm_cat(categoria, label)   # fallback: slug válido (tem cor+label)


# ─────────────────────────────────────────────────────────────────────
#  Geometria — Gantt (barras + eixo)
# ─────────────────────────────────────────────────────────────────────
def build_gantt(fases: List[Dict]) -> Tuple[List[Dict], List[Dict], Optional[float], List[Dict]]:
    """Retorna (fases_ctx, axis_ctx).

    t0 = min(inicio); mes_fim = mês de max(fim); tN = último dia de mes_fim;
    total = (tN - t0).days.
    Por fase: left_pct, width_pct(>=0.6), label_pct, dur_dias, label, cat.
    axis: 1º dia de cada mês m com t0 < m <= 1º dia de mes_fim.
    """
    fases = fases or []
    parsed = []
    for f in fases:
        ini = _parse_iso(f.get("inicio"))
        fim = _parse_iso(f.get("fim"))
        if not ini or not fim:
            continue
        parsed.append((f, ini, fim))
    if not parsed:
        return [], [], None, []

    t0 = min(p[1] for p in parsed)
    fim_max = max(p[2] for p in parsed)
    tN = _last_day_of_month(fim_max)
    total = (tN - t0).days
    if total <= 0:
        total = 1

    fases_ctx: List[Dict] = []
    for f, ini, fim in parsed:
        left = (ini - t0).days / total * 100.0
        width = (fim - ini).days / total * 100.0
        width = max(0.6, width)
        left = max(0.0, min(100.0, left))
        dur = f.get("dur_dias")
        if dur is None:
            dur = (fim - ini).days
        cat = _norm_cat(f.get("categoria"), f.get("label", ""))
        cat_real = _real_cat(f.get("categoria"), f.get("label", ""))
        try:
            pct_exec = int(max(0, min(100, float(f.get("pct_executado") or 0))))
        except Exception:
            pct_exec = 0
        fases_ctx.append({
            "label": f.get("label", ""),
            "dur_dias": int(dur),
            "left_pct": round(left, 2),
            "width_pct": round(width, 2),
            "label_pct": round(left + width, 2),
            "cat": cat,
            "cat_real": cat_real,
            "pct_exec": pct_exec,
            **_fase_visual(f, cat_real),
        })

    # Eixo de meses
    axis: List[Dict] = []
    fim_mes_first = _first_of_month(fim_max)
    m = _first_of_month(t0)
    if m <= t0:
        m = _next_month(m)
    while m <= fim_mes_first:
        pct = (m - t0).days / total * 100.0
        axis.append({"label": _mes_label(m), "pct": round(pct, 2)})
        m = _next_month(m)

    # "HOJE" — só quando a data atual cai dentro do período do Gantt
    hoje_pct = None
    hoje = date.today()
    if t0 <= hoje <= tN:
        hoje_pct = round((hoje - t0).days / total * 100.0, 2)

    # Legenda por categoria REALMENTE presente (ordem de aparição), com a cor
    # dominante da categoria nas fases (1ª fase da categoria manda).
    legenda: List[Dict] = []
    _vistas = set()
    for fc in fases_ctx:
        if fc["cat_real"] in _vistas:
            continue
        _vistas.add(fc["cat_real"])
        legenda.append({
            "label": CATEGORIA_LABEL.get(fc["cat_real"], fc["cat_real"].title()),
            "cor": fc["cor"],
            "cor_soft": fc["cor_soft"],
        })

    return fases_ctx, axis, hoje_pct, legenda


# ─────────────────────────────────────────────────────────────────────
#  Geometria — Curva S
# ─────────────────────────────────────────────────────────────────────
def build_curva(curva_s: List[Dict]) -> Dict:
    """Constrói area_d, line_d, markers (25/50/75/100) e xlabels.

    x = 70 + i/(n-1)*900 (igual espaçamento); y = 360 - pct/100*340.
    Marcos: onde o pct acumulado cruza cada limiar (interp linear no x).
    Degrada com segurança pra <2 pontos.
    """
    pts = curva_s or []
    n = len(pts)

    def yf(pct: float) -> float:
        return _CURVA_Y_BASE - (max(0.0, min(100.0, pct)) / 100.0) * _CURVA_H

    if n == 0:
        return {"area_d": "", "line_d": "", "markers": [], "xlabels": []}

    coords: List[Tuple[float, float, float]] = []
    xlabels: List[Dict] = []
    for i, p in enumerate(pts):
        try:
            pct = float(p.get("pct_acumulado", 0) or 0)
        except (TypeError, ValueError):
            pct = 0.0
        x = _CURVA_X0 + (i / (n - 1) * (_CURVA_X1 - _CURVA_X0)) if n > 1 else _CURVA_X0
        y = yf(pct)
        coords.append((round(x, 1), round(y, 1), pct))
        lbl = p.get("mes_label") or _mes_label_from_iso(p.get("data_fim_mes"))
        xlabels.append({"x": round(x, 1), "label": lbl})

    if n == 1:
        # Degrade: linha reta horizontal no pct do único ponto
        y = coords[0][1]
        line_d = f"M {_CURVA_X0},{y} L {_CURVA_X1},{y}"
        area_d = (f"{line_d} L {_CURVA_X1},{_CURVA_Y_BASE} "
                  f"L {_CURVA_X0},{_CURVA_Y_BASE} Z")
        xlabels[0]["x"] = _CURVA_X0
        return {"area_d": area_d, "line_d": line_d, "markers": [], "xlabels": xlabels}

    line_d = "M " + " L ".join(f"{x},{y}" for x, y, _ in coords)
    area_d = (f"{line_d} L {_CURVA_X1},{_CURVA_Y_BASE} "
              f"L {_CURVA_X0},{_CURVA_Y_BASE} Z")

    markers: List[Dict] = []
    for thr in (25, 50, 75, 100):
        cx = None
        for i in range(n):
            if coords[i][2] >= thr:
                if i == 0:
                    cx = coords[0][0]
                else:
                    p0, p1 = coords[i - 1][2], coords[i][2]
                    x0, x1 = coords[i - 1][0], coords[i][0]
                    cx = x1 if p1 == p0 else x0 + (thr - p0) / (p1 - p0) * (x1 - x0)
                break
        if cx is None:
            continue  # limiar nunca atingido — pula o marco
        markers.append({
            "cx": round(cx, 1),
            "cy": round(yf(thr), 1),
            "pct": thr,
            "filled": thr == 100,
        })

    return {"area_d": area_d, "line_d": line_d, "markers": markers, "xlabels": xlabels,
            "real_d": ""}


def anexar_curva_realizada(curva_ctx: Dict, curva_realizada: List[Dict]) -> Dict:
    """Sobrepõe a curva REALIZADA (pct_executado informado pelo usuário) à
    prevista, reusando as MESMAS coordenadas x (mesmos meses). Tracejada no
    template, com legenda 'Realizado' — nunca se mistura com o previsto
    (regra nº1: real e estimado sempre distinguíveis). Corta nos meses já
    decorridos (data_fim_mes <= hoje + mês corrente): desenhar o futuro
    estagnado seria uma linha plana mentirosa. Defensivo: qualquer
    incompatibilidade → sem linha, sem erro."""
    try:
        pts = curva_realizada or []
        xl = curva_ctx.get("xlabels") or []
        n = len(xl)
        if n < 2 or len(pts) != n:
            return curva_ctx
        if not any(float(p.get("pct_realizado", 0) or 0) > 0 for p in pts):
            return curva_ctx
        hoje = date.today()
        def yf(pct: float) -> float:
            return _CURVA_Y_BASE - (max(0.0, min(100.0, pct)) / 100.0) * _CURVA_H
        coords = []
        for i, p in enumerate(pts):
            fim_mes = _parse_iso(p.get("data_fim_mes"))
            # inclui meses decorridos + o mês corrente (parcial)
            if fim_mes and (fim_mes.replace(day=1) > hoje.replace(day=1)):
                break
            pct = float(p.get("pct_realizado", 0) or 0)
            coords.append((xl[i]["x"], round(yf(pct), 1)))
        if len(coords) < 2:
            return curva_ctx
        curva_ctx["real_d"] = "M " + " L ".join(f"{x},{y}" for x, y in coords)
    except Exception:
        pass
    return curva_ctx


# ─────────────────────────────────────────────────────────────────────
#  Matriz mensal (página 6) — % da fase executado em cada mês
# ─────────────────────────────────────────────────────────────────────
def build_matriz(cronograma: Dict) -> Dict:
    """Linhas de matriz_pct (label, cor, percentuais_por_mes) + labels dos
    meses, prontas pro template: célula com fundo = cor da fase com alpha
    proporcional ao %, e texto claro quando o fundo satura. Degrada pra
    {'rows': []} sem dados (o template pula a página inteira... não — a
    página sai vazia elegante; quem monta decide)."""
    rows_in = cronograma.get("matriz_pct") or []
    meses = cronograma.get("meses") or []
    labels = [m.get("label", "") for m in meses]
    n = len(labels)
    rows: List[Dict] = []
    for r in rows_in:
        cor = (r.get("cor") or "").strip()
        if not re.match(r"^#[0-9a-fA-F]{6}$", cor):
            cor = _COR_FALLBACK
        cr, cg, cb = _hex_rgb(cor)
        lum = 0.2126 * cr + 0.7152 * cg + 0.0722 * cb
        cells: List[Dict] = []
        for p in (r.get("percentuais_por_mes") or [])[:n]:
            try:
                pct = int(max(0, min(100, float(p or 0))))
            except Exception:
                pct = 0
            if pct <= 0:
                cells.append({"pct": 0, "bg": "transparent", "fg": ""})
                continue
            alpha = round(0.14 + 0.72 * (pct / 100.0), 2)
            # fundo saturado (>55%) usa o texto da fase (branco em cor escura)
            fg = ("#FFFFFF" if lum <= 165 else "#1D1B16") if alpha > 0.55 else ""
            cells.append({"pct": pct, "bg": f"rgba({cr},{cg},{cb},{alpha})", "fg": fg})
        while len(cells) < n:
            cells.append({"pct": 0, "bg": "transparent", "fg": ""})
        rows.append({"label": r.get("label", ""), "cor": cor, "cells": cells})
    return {"labels": labels, "rows": rows, "n_meses": n, "n_fases": len(rows)}


def _moeda_br(v) -> str:
    """R$ 1.234.567,89 — sem depender de locale do sistema (o contêiner do
    Render não tem pt_BR instalado, e locale.setlocale explodiria em produção)."""
    try:
        n = float(v or 0)
    except (TypeError, ValueError):
        n = 0.0
    inteiro, _, dec = f"{abs(n):.2f}".partition(".")
    partes = []
    while len(inteiro) > 3:
        partes.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    partes.insert(0, inteiro)
    return f"{'-' if n < 0 else ''}R$ {'.'.join(partes)},{dec}"


def build_financeiro(cronograma: Dict) -> Dict:
    """Desembolso por mês pro documento. Vazio quando o cliente não informou
    valor — aí o cronograma continua sendo só FÍSICO e o PDF não fala em
    dinheiro em lugar nenhum (nem no título da capa).

    🔒 Regra dura nº5: nada aqui calcula preço. É o número dele, distribuído
    pelo mesmo rateio da parte física."""
    fin = cronograma.get("financeiro") or None
    if not fin or not fin.get("total_informado"):
        return {"tem": False}
    meses = cronograma.get("meses") or []
    labels = [m.get("label", "") for m in meses]
    por_mes = fin.get("por_mes") or []
    acum = fin.get("acumulado") or []
    total = fin.get("total_informado") or 0
    cells = []
    for i, lb in enumerate(labels):
        v = por_mes[i] if i < len(por_mes) else 0
        a = acum[i] if i < len(acum) else 0
        cells.append({
            "label": lb,
            "valor": _moeda_br(v) if v else "·",
            "acumulado": _moeda_br(a),
            "pct": round(100 * a / total, 1) if total else 0,
            "vazio": not v,
        })
    return {
        "tem": True,
        "total": _moeda_br(total),
        "cells": cells,
        "n_meses": len(labels),
        "n_fases_com_valor": fin.get("n_fases_com_valor", 0),
        "n_fases": fin.get("n_fases", 0),
        "parcial": fin.get("n_fases_com_valor", 0) < fin.get("n_fases", 0),
    }


# ─────────────────────────────────────────────────────────────────────
#  Geometria — Caminho crítico
# ─────────────────────────────────────────────────────────────────────
def build_caminho(cronograma: Dict) -> List[Dict]:
    """Top-5 de resumo['caminho_critico'] (ou as 5 fases mais longas).
    c.rank(1..5), c.label, c.dur_dias, c.width_pct(maior=100), c.cat."""
    resumo = cronograma.get("resumo", {}) or {}
    cc = resumo.get("caminho_critico") or []
    if not cc:
        fases = cronograma.get("fases", []) or []
        cc = sorted(fases, key=lambda f: f.get("dur_dias", 0), reverse=True)[:5]
        cc = [{"label": f.get("label", ""), "dur_dias": f.get("dur_dias", 0),
               "categoria": f.get("categoria")} for f in cc]
    cc = cc[:5]
    if not cc:
        return []
    maior = max((c.get("dur_dias", 0) or 0) for c in cc) or 1
    out = []
    for i, c in enumerate(cc, 1):
        dur = c.get("dur_dias", 0) or 0
        cat_real = _real_cat(c.get("categoria"), c.get("label", ""))
        out.append({
            "rank": i,
            "label": c.get("label", ""),
            "dur_dias": int(dur),
            "width_pct": round(dur / maior * 100.0, 1),
            "cat": _norm_cat(c.get("categoria"), c.get("label", "")),
            "cor": (c.get("cor") if re.match(r"^#[0-9a-fA-F]{6}$", str(c.get("cor") or ""))
                    else CATEGORIA_COR.get(cat_real, _COR_FALLBACK)),
        })
    return out


# ─────────────────────────────────────────────────────────────────────
#  Logo → data URI
# ─────────────────────────────────────────────────────────────────────
def _logo_data_uri(branding: Dict) -> str:
    path = (branding or {}).get("logo_local_path")
    if not path or not isinstance(path, str) or not os.path.exists(path):
        return ""
    try:
        ext = os.path.splitext(path)[1].lower()
        mime = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
        }.get(ext, "image/png")
        with open(path, "rb") as fh:
            data = fh.read()
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────
#  build_context — monta o dict EXATO do contrato
# ─────────────────────────────────────────────────────────────────────
def build_context(cronograma: Dict, branding: Dict, template: str) -> Dict:
    cronograma = cronograma or {}
    branding = branding or {}
    template = template if template in TEMPLATES_VALIDOS else "escuro"

    accent = _norm_hex(branding.get("brand_color"))
    resumo = cronograma.get("resumo", {}) or {}

    fases_ctx, axis_ctx, hoje_pct, legenda_ctx = build_gantt(cronograma.get("fases", []))
    curva_ctx = build_curva(cronograma.get("curva_s", []))
    # chave real do gerador = 'curva_s_realizada'; aceita a variante por robustez
    curva_ctx = anexar_curva_realizada(
        curva_ctx, cronograma.get("curva_s_realizada") or cronograma.get("curva_realizada") or [])
    caminho_ctx = build_caminho(cronograma)
    matriz_ctx = build_matriz(cronograma)
    fin_ctx = build_financeiro(cronograma)

    # Branding
    b = {
        "project_name": (branding.get("project_name") or "Projeto sem nome").strip(),
        "architect_name": (branding.get("architect_name") or "").strip(),
        "client_name": (branding.get("client_name") or "").strip(),
        "company": (branding.get("company") or "").strip(),
        "logo_uri": _logo_data_uri(branding),
        "emitido_em": datetime.now().strftime("%d/%m/%Y"),
        "job_id": branding.get("job_id") or "",
    }

    # Resumo pra capa
    dur_dias = resumo.get("duracao_dias_reais")
    if dur_dias is None:
        dur_dias = resumo.get("duracao_dias") or 0
    r = {
        "inicio_br": _iso_to_br(resumo.get("data_inicio")),
        "fim_br": _iso_to_br(resumo.get("data_fim")),
        "duracao_dias": int(dur_dias or 0),
        "n_fases": int(resumo.get("n_fases") or len(cronograma.get("fases", []) or [])),
    }

    # Marcos legais divididos em 2 colunas
    marcos = list(cronograma.get("marcos_legais", []) or [])
    mid = (len(marcos) + 1) // 2
    marcos_col1 = marcos[:mid]
    marcos_col2 = marcos[mid:]

    ressalva = cronograma.get("ressalva", "") or ""

    return {
        "template": template,
        "accent": accent,
        "pal": PALETAS[template],
        "b": b,
        "r": r,
        "fases": fases_ctx,
        "axis": axis_ctx,
        "hoje_pct": hoje_pct,
        "legenda": legenda_ctx,
        "curva": curva_ctx,
        "caminho": caminho_ctx,
        "matriz": matriz_ctx,
        "financeiro": fin_ctx,
        # 02/08 a capa passou a dizer "FÍSICO DA OBRA" porque prometíamos um
        # financeiro que não existia. Com o valor informado pelo cliente, o
        # nome volta a ser verdade — e SÓ nesse caso.
        "titulo_doc": ("CRONOGRAMA FÍSICO-FINANCEIRO DA OBRA"
                       if fin_ctx.get("tem") else "CRONOGRAMA FÍSICO DA OBRA"),
        # total de páginas: 6 com matriz, 5 sem (numeração dos rodapés)
        "n_paginas": 6 if matriz_ctx.get("rows") else 5,
        "marcos_col1": marcos_col1,
        "marcos_col2": marcos_col2,
        "ressalva": ressalva,
    }


# ─────────────────────────────────────────────────────────────────────
#  Jinja + montagem do HTML
# ─────────────────────────────────────────────────────────────────────
_jinja_env = None


def _get_env():
    global _jinja_env
    if _jinja_env is None:
        from jinja2 import Environment, FileSystemLoader
        # autoescape=False de propósito: os templates espelham CSS/HTML VERBATIM
        # (nomes de fonte com aspas simples quebrariam se escapados).
        _jinja_env = Environment(
            loader=FileSystemLoader(_TEMPLATES_DIR),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
    return _jinja_env


def montar_html(cronograma: Dict, branding: Dict, template: str,
                accent: Optional[str] = None) -> str:
    """Renderiza documento.html.j2 e resolve color-mix/var(--accent).
    `accent` sobrescreve branding.brand_color se passado."""
    ctx = build_context(cronograma, branding, template)
    if accent:
        ctx["accent"] = _norm_hex(accent)
    env = _get_env()
    tpl = env.get_template("documento.html.j2")
    html = tpl.render(**ctx)
    return resolver_color_mix(html, ctx["accent"])


# ─────────────────────────────────────────────────────────────────────
#  Render — PDF (WeasyPrint) + PNG por página (pypdfium2)
# ─────────────────────────────────────────────────────────────────────
def render_pdf_bytes(cronograma: Dict, branding: Dict, template: str,
                     accent: Optional[str] = None) -> bytes:
    """HTML → PDF (5 páginas A4 paisagem). Retorna bytes. Lança em falha real
    (o chamador decide o fallback)."""
    from weasyprint import HTML
    html = montar_html(cronograma, branding, template, accent)
    return HTML(string=html, base_url=_TEMPLATES_DIR).write_pdf()


def render_png_paginas(pdf_bytes: bytes, scale: float = 2.0) -> List[bytes]:
    """Rasteriza o PDF página a página → lista de PNGs (bytes), ~scale x.
    Usado pra montar o PPTX (1 imagem full-bleed por slide)."""
    if not pdf_bytes:
        return []
    try:
        import pypdfium2 as pdfium
    except Exception:
        return []
    pngs: List[bytes] = []
    pdf = None
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
        for i in range(len(pdf)):
            try:
                page = pdf[i]
                bitmap = page.render(scale=scale)
                pil = bitmap.to_pil()
                buf = io.BytesIO()
                pil.save(buf, format="PNG")
                pngs.append(buf.getvalue())
            except Exception:
                continue
    except Exception:
        return pngs
    finally:
        try:
            if pdf is not None:
                pdf.close()
        except Exception:
            pass
    return pngs
