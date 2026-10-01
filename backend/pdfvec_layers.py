# -*- coding: utf-8 -*-
"""Extração de geometria de PDF POR LAYER do CAD (Optional Content Groups).

Descoberta 07/07: PDF exportado de CAD preserva os layers como OCG, e o
content stream marca cada objeto com /OC /BDC ... EMC. Rastreando a matriz de
transformação (q/Q/cm) + a pilha de OC, dá pra extrair a geometria de cada
layer em coordenadas reais de página. Isso separa parede (ARQ-ALV) de
mobiliário de texto, e permite CONTAR símbolos (IND-*, LUM-*) — impossível na
"sopa de linhas" indiferenciada.

Só pikepdf (MPL-2.0, já instalável) — NÃO PyMuPDF (AGPL, contamina licença).
"""
from __future__ import annotations

import re
from collections import defaultdict

import pikepdf
from pikepdf import parse_content_stream

# xref vira prefixo "0326.CGR.14.xref.06|ARQ-ALV" — normaliza pro nome do layer.
_XREF_RE = re.compile(r"^.*\|")


def _norm_layer(name: str) -> str:
    return _XREF_RE.sub("", str(name or "")).strip().upper()


def _compose(a, b):
    """Matriz afim A seguida de B (ponto-linha [x y 1] · M). 6-tupla (a,b,c,d,e,f)."""
    a1, b1, c1, d1, e1, f1 = a
    a2, b2, c2, d2, e2, f2 = b
    return (
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    )


def _apply(m, x, y):
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


_IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def extract_layers(pdf_path: str, page_index: int = 0) -> dict[str, list]:
    """Devolve {LAYER_NORMALIZADO: [segmentos]} em pontos de página (y-up).
    Segmento = ((x0,y0),(x1,y1)). Beziers reduzidos a corda; retângulos a 4 lados.
    Ignora XObjects (blocos/xrefs) nesta v1 — a geometria principal (paredes,
    pontos) está no stream da página."""
    pdf = pikepdf.open(pdf_path)
    page = pdf.pages[page_index]

    # mapa nome-local -> nome do OCG (via Resources/Properties)
    props = {}
    try:
        for k, v in dict(page.Resources.Properties).items():
            try:
                props[str(k)] = str(v.Name)
            except Exception:
                props[str(k)] = None
    except Exception:
        pass

    out: dict[str, list] = defaultdict(list)
    ctm = _IDENTITY
    ctm_stack: list = []
    oc_stack: list = []          # pilha de layers (BDC/EMC)
    cur = (0.0, 0.0)             # ponto corrente (raw, pré-CTM)
    start = (0.0, 0.0)

    def num(o):
        try:
            return float(o)
        except Exception:
            return 0.0

    def layer_now():
        for l in reversed(oc_stack):
            if l:
                return l
        return None

    def emit(x0, y0, x1, y1):
        lay = layer_now()
        if not lay:
            return
        p0 = _apply(ctm, x0, y0)
        p1 = _apply(ctm, x1, y1)
        out[lay].append((p0, p1))

    for instr in parse_content_stream(page):
        op = str(instr.operator)
        o = instr.operands
        if op == "q":
            ctm_stack.append(ctm)
        elif op == "Q":
            if ctm_stack:
                ctm = ctm_stack.pop()
        elif op == "cm" and len(o) >= 6:
            m = tuple(num(x) for x in o[:6])
            ctm = _compose(m, ctm)
        elif op == "BDC":
            lay = None
            if len(o) >= 2 and str(o[0]) == "/OC":
                tag = o[1]
                nm = props.get(str(tag)) or props.get(str(tag).lstrip("/"))
                if nm is None:
                    try:
                        nm = str(tag.Name)
                    except Exception:
                        nm = None
                lay = _norm_layer(nm) if nm else None
            oc_stack.append(lay)
        elif op == "BMC":
            oc_stack.append(None)
        elif op == "EMC":
            if oc_stack:
                oc_stack.pop()
        elif op == "m" and len(o) >= 2:
            cur = (num(o[0]), num(o[1]))
            start = cur
        elif op == "l" and len(o) >= 2:
            nxt = (num(o[0]), num(o[1]))
            emit(cur[0], cur[1], nxt[0], nxt[1])
            cur = nxt
        elif op in ("c", "v", "y"):
            # bezier -> corda (endpoint são os 2 últimos operandos)
            if len(o) >= 2:
                nxt = (num(o[-2]), num(o[-1]))
                emit(cur[0], cur[1], nxt[0], nxt[1])
                cur = nxt
        elif op == "re" and len(o) >= 4:
            x, y, w, h = (num(o[0]), num(o[1]), num(o[2]), num(o[3]))
            emit(x, y, x + w, y); emit(x + w, y, x + w, y + h)
            emit(x + w, y + h, x, y + h); emit(x, y + h, x, y)
            cur = (x, y); start = cur
        elif op == "h":
            emit(cur[0], cur[1], start[0], start[1])
            cur = start
    return dict(out)


import math as _math

PT_TO_M = 0.0254 / 72.0

# Layers que são PAREDE (alvenaria/divisória) vs SÍMBOLO contável vs TEXTO (ignorar).
_WALL_HINT = re.compile(r"ALV|PAR(?:ED)?|DIV(?:IS)?", re.I)
_TEXT_HINT = re.compile(r"TXT|TEXT|LEG|DIM|COTA|HACH|ANNO", re.I)
_SYMBOL_HINT = re.compile(r"^IND-|^LUM|^ELE|PTA|PTM|PTF|PTP|INT|TOM|LUMIN|ANTENA|WIFI|ACS", re.I)


def _seg_len_m(segs, mpp):
    return sum(_math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs) * mpp


def count_symbols(segs, mpp, tol=3.0, lo_cm=3.0, hi_cm=40.0):
    """Conta instâncias de símbolo por componentes conexos (endpoints compartilhados).
    Filtra por tamanho real (símbolo elétrico ~5-20cm) pra cortar leader/texto."""
    n = len(segs)
    if not n:
        return 0
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    grid = defaultdict(list)

    def key(p):
        return (round(p[0] / tol), round(p[1] / tol))

    for i, (a, b) in enumerate(segs):
        for p in (a, b):
            kx, ky = key(p)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j in grid[(kx + dx, ky + dy)]:
                        parent[find(i)] = find(j)
            grid[key(p)].append(i)
    comps = defaultdict(list)
    for i in range(n):
        comps[find(i)].append(i)
    cnt = 0
    for idxs in comps.values():
        xs = []
        ys = []
        for i in idxs:
            for p in segs[i]:
                xs.append(p[0])
                ys.append(p[1])
        d = max(max(xs) - min(xs), max(ys) - min(ys)) * mpp * 100
        if lo_cm <= d <= hi_cm:
            cnt += 1
    return cnt


def summarize_layers(pdf_path: str, page_index: int, scale_denominator: float,
                     region_bbox=None) -> dict:
    """Resumo por layer pra shadow: comprimento de parede (layers ALV/DIV) e
    contagem de símbolos (layers IND-*/LUM-*). region_bbox (x0,y0,x1,y1) filtra
    a view principal. Tudo determinístico, sem IA."""
    mpp = PT_TO_M * float(scale_denominator)
    layers = extract_layers(pdf_path, page_index)

    def in_region(seg):
        if region_bbox is None:
            return True
        (x0, y0, x1, y1) = region_bbox
        mx = (seg[0][0] + seg[1][0]) / 2
        my = (seg[0][1] + seg[1][1]) / 2
        return x0 <= mx <= x1 and y0 <= my <= y1

    walls = {}
    symbols = {}
    sym_inv = {}  # inventário BRUTO (seg count) dos layers de símbolo — sempre confiável
    for lay, segs in layers.items():
        if region_bbox is not None:
            segs = [s for s in segs if in_region(s)]
        if not segs:
            continue
        if _WALL_HINT.search(lay) and not _TEXT_HINT.search(lay):
            walls[lay] = round(_seg_len_m(segs, mpp), 1)
        elif _SYMBOL_HINT.search(lay) and not _TEXT_HINT.search(lay):
            sym_inv[lay] = len(segs)
            c = count_symbols(segs, mpp)
            if c:
                symbols[lay] = c

    wall_stroke = round(sum(walls.values()), 1)
    return {
        "n_layers": len(layers),
        "wall_layers": dict(sorted(walls.items(), key=lambda t: -t[1])[:6]),
        "wall_centerline_m": round(wall_stroke / 2, 1),  # ALV = 2 faces
        "symbols": dict(sorted(symbols.items(), key=lambda t: -t[1])[:10]),
        "symbol_layers": dict(sorted(sym_inv.items(), key=lambda t: -t[1])[:12]),
    }


# ── Escala EXATA embutida no PDF (descoberta 07/07, achado #2 do estudo) ──
# PDF exportado de CAD traz /VP (viewports) com /Measure /X /C = fator de
# conversão real por view. denom = C / (2.54/72). Resolve escala + multi-view
# + "INDICADAS" de forma DETERMINÍSTICA, sem Vision. Só pikepdf.
_CM_PER_PT = 2.54 / 72.0            # 0.0352778 — 1 ponto em escala 1:1
_STD_SCALES = [10, 20, 25, 33, 50, 75, 100, 125, 150, 200, 250, 500, 1000]


#: 🩸 11/09/2026, job b0fa9104 — PDF DE LOJA AMERICANA LIDO COMO SE FOSSE
#: CENTÍMETRO. O `/C` do `/Measure` é um fator de conversão, e a unidade dele
#: mora no `/U` do mesmo dicionário. Aqui o `/U` nunca foi lido: o código dividia
#: por `_CM_PER_PT` sempre. Num PDF do AutoCAD americano o `/C` vem em POLEGADA
#: por ponto, e `C × 72` é o próprio denominador da escala (1/2/4/8/12/16/24/32/
#: 48/64/96/120 — o "3/8\" = 1'-0\"" da prancha é 1:32).
#: 📏 Medido nos 71 viewports daquele arquivo: `C × 72` caía nesses valores com
#: erro ≤0,064%, e a cota ESCRITA de 13.997 mm confirmou 1:32 (−0,002%). Lido
#: como cm o motor usou 1:13 — comprimento ÷2,46 e área ÷6,06.
#: 🧪 CONTROLE, rodado nos 14 PDFs brasileiros locais (47 viewports): 7 saem
#: hoje com `snapped=False` (1:433, 1:581, 1:579, 1:158 — escala que não existe
#: em arquitetura) e NENHUM deles casa como polegada; ZERO viewports ambíguos.
#: Ou seja, esta regra não muda nada do que a gente já lia certo.
_IMPERIAL_DENOMS = [1, 2, 4, 8, 12, 16, 24, 32, 48, 64, 96, 120]
_TOL_IMPERIAL = 0.003     # 0,3% — o caso real errou 0,064%
_U_METRICA = ("cm", "m", "mm", "metro", "metros", "centimetro", "centímetro")
_U_IMPERIAL = ("in", "inch", "inches", "ft", "feet", '"', "'")


def _denominador_imperial(c: float):
    """`C` em POLEGADA por ponto → denominador da escala, ou None.

    Adimensional de propósito: quem converte ponto→metro adiante multiplica
    pelo denominador, e essa conta é a mesma em qualquer unidade. O defeito era
    só o NÚMERO — 12,6 no lugar de 32.
    """
    try:
        v = float(c) * 72.0
    except (TypeError, ValueError):
        return None
    for d in _IMPERIAL_DENOMS:
        if abs(v - d) <= _TOL_IMPERIAL * d:
            return d
    return None


def _unidade_declarada(u: str):
    """(metrica?, imperial?) do que o `/U` do viewport diz. ("", "") = calado."""
    t = str(u or "").strip().strip("()").lower()
    if not t:
        return False, False
    return (any(t == m or t.startswith(m) for m in _U_METRICA),
            any(t == i or t.startswith(i) for i in _U_IMPERIAL))


def _pagina_e_imperial(brutos) -> bool:
    """A PÁGINA inteira está em polegada?

    🪤 Decisão por PÁGINA, não por viewport: um viewport solto cujo número caia
    por acaso na faixa imperial não pode virar unidade nova. Exige DOIS, e que
    nenhum outro da mesma página case com escala métrica padrão — prancha não
    mistura sistema de unidade.
    🔑 O `/U` manda quando existe: declaração explícita ganha da estatística nos
    dois sentidos. Nos 47 viewports locais, NENHUM declarava — por isso a regra
    de baixo existe.
    """
    metricas = imperiais = 0
    for b in brutos:
        m, i = _unidade_declarada(b.get("u"))
        metricas += 1 if m else 0
        imperiais += 1 if i else 0
    if metricas:
        return False
    if imperiais:
        return True
    casam_imperial = sum(1 for b in brutos if _denominador_imperial(b.get("c")) is not None)
    casam_metrico = sum(1 for b in brutos
                        if (_snap_scale(float(b.get("c") or 0) / _CM_PER_PT) or (0, False))[1])
    return casam_imperial >= 2 and casam_metrico == 0


#: 🩸 01/10/2026 — H68 do estudo do acervo: o `/C` do viewport de DESENHO vem em
#: METRO por ponto, com o `/U` em branco. É o PDF do AutoCAD/Revit com o modelo
#: em metro: a folha de papel sai em mm (C = 25,4/72 = 0,35278) e cada desenho
#: na unidade do modelo — 0,03528 = 1:100, 0,02646 = 1:75, 0,01764 = 1:50,
#: 0,00882 = 1:25. Lido como cm, dá 1:1 / 0,75 / 0,5 / 0,25: o `_snap_scale`
#: descarta (< 5) e o viewport some. Aí sobra um recorte pequeno como principal
#: (1:11 no lugar de 1:100 num viewport de 85 % da folha; 1:40 no lugar de 1:200)
#: ou a escala cai pro carimbo.
#: 📏 Acervo local, 92 páginas com /VP em 16 jobs: 57 ganham escala, 6 trocam
#: de escala errada pra certa, 9 ficam iguais e 20 seguem sem viewport útil. Onde
#: a produção tinha carimbo ou cota na MESMA folha, a escala em metro bate em 13
#: de 15 (2 delas provadas por cota). As 2 que divergem são a favor do viewport:
#: plantas a 1:125 que o rótulo deu como 1:100, e folha de detalhes a 1:25
#: medida a 1:100.
#: 🪤 C = 0,35278 é AMBÍGUO: papel 1:1 em mm, 1:10 em cm e 1:1000 em m dão o
#: MESMO número. Só sai da conta quando a FOLHA da página também é papel em mm —
#: aí é recorte do papel (carimbo, legenda), não desenho. Sem a folha pra dizer,
#: fica como era (1:10).
_PAPEL_MM = 25.4 / 72.0     # /C da folha de papel 1:1 em milímetro
_TOL_PAPEL = 0.001          # 0,1 %
_M_PARA_CM = 100.0
_U_METRO = ("m", "metro", "metros", "meter", "meters", "metre", "metres")


def _e_papel_mm(c) -> bool:
    try:
        return abs(float(c) - _PAPEL_MM) <= _TOL_PAPEL * _PAPEL_MM
    except (TypeError, ValueError):
        return False


def _pagina_e_metro(brutos) -> bool:
    """A medida dos viewports da PÁGINA está em METRO (com o `/U` calado)?

    🔑 Decisão por PÁGINA, pela maioria: lidos como metro, MAIS viewports caem em
    escala padrão do que lidos como cm. Empate fica no cm (o que era). As duas
    leituras diferem 100×, então o mesmo viewport quase nunca casa nas duas.
    🔒 `/U` declarado manda, como na polegada: "m"/"metro" é metro, qualquer
    outro fica como era. Nos 658 viewports do acervo local NENHUM declarava.
    """
    declarados = [str(b.get("u") or "").strip().strip("()").lower() for b in brutos]
    declarados = [u for u in declarados if u]
    if declarados:
        return all(u in _U_METRO for u in declarados)

    def _casa(c, mult):
        return bool((_snap_scale(float(c or 0) * mult / _CM_PER_PT) or (0, False))[1])

    em_cm = sum(1 for b in brutos if _casa(b.get("c"), 1.0))
    em_m = sum(1 for b in brutos if _casa(b.get("c"), _M_PARA_CM))
    return em_m > em_cm


def _snap_scale(raw: float):
    """Aproxima pra escala padrão de arquitetura se estiver a ≤5%. C é cm/pt
    (padrão do /RL). NÃO tenta unidades alternativas — isso fazia a folha 1:1
    (raw≈1) casar errado com 1:10. Retorna (denom, snapped_bool) ou None."""
    if raw <= 0:
        return None
    for s in _STD_SCALES:
        if abs(raw - s) / s <= 0.05:
            return s, True
    if 5 <= raw <= 2000:
        return int(round(raw)), False
    return None


def scale_from_viewport(pdf_path: str, page_index: int = 0) -> dict:
    """Lê a escala exata de cada viewport do PDF. Retorna:
      {main_scale, main_bbox, snapped, viewports:[{bbox, scale, snapped}]}.
    main = maior viewport que não é a folha inteira. {} se não houver /VP."""
    try:
        pdf = pikepdf.open(pdf_path)
        page = pdf.pages[page_index]
        vps = page.get("/VP")
        if not vps:
            return {}
        pw = float(page.MediaBox[2]) - float(page.MediaBox[0])
        ph = float(page.MediaBox[3]) - float(page.MediaBox[1])
        page_area = pw * ph
        # 1ª passada: junta o que cada viewport DIZ, sem decidir unidade ainda —
        # a unidade é da página, e pra saber dela é preciso ver todas.
        brutos = []
        folha_papel_mm = False
        for v in vps:
            try:
                meas = v.get("/Measure")
                bbox = [float(x) for x in v.get("/BBox")]
                x0 = meas.get("/X")[0]
                c = float(x0.get("/C"))
            except Exception:
                continue
            area = abs(bbox[2] - bbox[0]) * abs(bbox[3] - bbox[1])
            # ignora a viewport da folha inteira (é o quadro do papel, não um
            # desenho) — sempre por ÁREA, nunca pelo denominador.
            if area >= 0.9 * page_area:
                folha_papel_mm = folha_papel_mm or _e_papel_mm(c)
                continue
            try:
                u = str(x0.get("/U") or "")
            except Exception:
                u = ""
            brutos.append({"bbox": bbox, "c": c, "area": area, "u": u})

        # H68: com a folha em papel-mm, recorte com o MESMO /C é papel, não desenho
        if folha_papel_mm:
            brutos = [b for b in brutos if not _e_papel_mm(b["c"])]
        imperial = _pagina_e_imperial(brutos)
        metro = not imperial and _pagina_e_metro(brutos)
        mult = _M_PARA_CM if metro else 1.0
        views = []
        for b in brutos:
            if imperial:
                denom = _denominador_imperial(b["c"])
                if denom is None:
                    continue      # numa página imperial, o que não é imperial não entra
                snapped = True
            else:
                snap = _snap_scale(b["c"] * mult / _CM_PER_PT)
                if not snap:
                    continue
                denom, snapped = snap
            views.append({"bbox": b["bbox"], "scale": denom, "snapped": snapped,
                          "area": b["area"],
                          "unidade": "polegada" if imperial else ("m" if metro else "cm")})
        if not views:
            return {}
        main = max(views, key=lambda x: x["area"])
        for x in views:
            x.pop("area", None)
        # 🪤 H68: na página em METRO o viewport traz a ESCALA, não o RECORTE.
        # Medido no acervo (01/10): recortar no maior viewport derrubava área
        # que hoje sai PROVADA por cota — 294 m² (3 cotas) → 27,8 m² numa folha
        # cujo maior viewport cobre 16 % do papel; 1.512 m² (4 cotas) → 1.002.
        # A região medida fica a de hoje (o agrupamento das vistas); recortar é
        # outra decisão, com medida própria.
        return {"main_scale": main["scale"], "main_bbox": None if metro else main["bbox"],
                "snapped": main["snapped"], "viewports": views,
                "unidade": main.get("unidade", "cm"),
                "page_size": (pw, ph)}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"[:100]}
