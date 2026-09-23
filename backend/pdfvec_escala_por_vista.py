# -*- coding: utf-8 -*-
"""A escala escrita AO LADO DE CADA VISTA — quando o carimbo diz "indicadas".

🩸 POR QUE ESTE MÓDULO EXISTE — 09/09/2026, medido no arquivo REAL de um
cliente (job `aec7cac2`, 47 páginas, 22 delas sem escala). O carimbo daquela
prancha diz, literalmente:

    Escala          Data       Desenho nº
    A3 - A1
    Como se indica  NOV 2025   A3004

*"Como se indica"* é o "ESCALAS INDICADAS" em português de Portugal. E o
`A3 - A1` explica por quê: a folha é feita pra imprimir em DOIS tamanhos, então
a mesma prancha tem duas escalas reais — pôr uma razão no carimbo seria mentira.

🔑 O motor lia o carimbo CERTO e concluía CERTO ("não há escala aqui") — e aí
desistia. Mas `indicadas` não é falha: **é o carimbo dizendo ONDE procurar.**

📏 E o lugar medido é longe de onde a gente olhava. Na única página daquele
arquivo com razão no texto, havia TRÊS — `1:100`, `1:50`, `1:50` — todas em
**x=5% da largura**, na margem ESQUERDA, em três alturas diferentes (uma por
vista). O `pdfvec_carimbo` recorta os **18% da DIREITA**. Nunca ia achar.

🪤 A ARMADILHA DE COORDENADA, que já me mordeu na análise: naquele arquivo o
MediaBox é `[-1192, -842, 1192, 842]` — a folha é **centrada na origem**, não
ancorada em (0,0). Recorte escrito em coordenada absoluta cai fora da página e
devolve papel em branco. Por isso tudo aqui é **fração da caixa da página**, e
há guarda com MediaBox deslocado.

🚫 ALCANCE HONESTO: a geometria do recorte (estender até a margem esquerda) foi
calibrada em UM arquivo real. É o único da população que falha a que tive
acesso. Pode não valer pra outras convenções — por isso o módulo devolve
`por_vista` com a bbox de cada leitura, pra dar pra conferir depois no log.
"""
from __future__ import annotations

import base64
import io
import json
import re
from typing import Optional

import pypdfium2 as pdfium

MODEL = "claude-haiku-4-5-20251001"
MAX_EDGE_PX = 1568
MAX_DPI = 300.0
JPEG_QUALITY = 88

#: Quantas vistas no máximo entram numa chamada. Vista é ordenada por tamanho,
#: então as primeiras são as que importam pro quantitativo.
MAX_VISTAS = 6

#: Folga em volta da vista, em fração da página. O rótulo mora COLADO na vista.
MARGEM_FRAC = 0.03

#: 🔑 Estender o recorte até a margem ESQUERDA da folha. Foi lá que as três
#: razões estavam no arquivo medido (x=5%). Sem isto o recorte para na borda da
#: vista e o rótulo fica de fora.
ATE_A_ESQUERDA = True

_SCALE_RE = re.compile(r"1\s*[:/]\s*(\d{1,4})")

_PROMPT = (
    "Cada imagem e o RECORTE de UMA VISTA (desenho) de uma prancha de "
    "arquitetura — planta, corte, alcado/fachada ou pormenor.\n"
    "Para CADA imagem, na ordem, procure o ROTULO DA VISTA: um texto proximo "
    "ao desenho com o nome da vista e a ESCALA. Formatos comuns: 'ESC 1:50', "
    "'ESCALA 1/100', 'esc. 1:25', 'E: 1:20', ou so '1:50' sozinho perto do "
    "titulo do desenho.\n"
    "🚨 NAO confunda com: numero de cota (medida do desenho), codigo de "
    "prancha, data, numero de revisao, referencia de material.\n"
    "Responda APENAS com JSON, sem texto extra:\n"
    '{"vistas": [{"i": 0, "escala": "1:50"}, {"i": 1, "escala": null}]}\n'
    "Use escala=null quando NAO houver rotulo de escala legivel na imagem. "
    "NAO invente: null e melhor que chute."
)


def _caixa_da_pagina(page) -> tuple:
    """(x0, y0, x1, y1) da página, em pontos, COMO ELA É.

    🪤 Não assume origem em (0,0): há PDF de CAD com a folha centrada na
    origem, e foi exatamente isso que fez a análise de 09/09 ler papel branco.
    """
    try:
        box = page.get_cropbox() or page.get_mediabox()
    except Exception:
        box = None
    if not box:
        w, h = page.get_width(), page.get_height()
        return (0.0, 0.0, float(w), float(h))
    x0, y0, x1, y1 = (float(v) for v in box)
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def recorte_da_vista(caixa, bbox, margem=MARGEM_FRAC, ate_a_esquerda=ATE_A_ESQUERDA):
    """Devolve o recorte em FRAÇÃO da página: (fx0, fy0, fx1, fy1), y pra cima.

    🔑 Decisão pura — sem PDF, sem rede. É ela que a bancada exercita, e é onde
    mora a armadilha da origem deslocada.
    """
    px0, py0, px1, py1 = caixa
    W = float(px1 - px0) or 1.0
    H = float(py1 - py0) or 1.0
    bx0, by0, bx1, by1 = (float(v) for v in bbox)
    fx0 = (min(bx0, bx1) - px0) / W
    fx1 = (max(bx0, bx1) - px0) / W
    fy0 = (min(by0, by1) - py0) / H
    fy1 = (max(by0, by1) - py0) / H
    fx0 -= margem; fx1 += margem
    fy0 -= margem; fy1 += margem
    if ate_a_esquerda:
        fx0 = 0.0
    return (max(0.0, min(1.0, fx0)), max(0.0, min(1.0, fy0)),
            max(0.0, min(1.0, fx1)), max(0.0, min(1.0, fy1)))


def _render_fracao(page, frac) -> Optional[bytes]:
    """Renderiza o retângulo dado em FRAÇÃO da página. JPEG, ou None."""
    fx0, fy0, fx1, fy1 = frac
    pw, ph = float(page.get_width()), float(page.get_height())
    larg, alt = (fx1 - fx0) * pw, (fy1 - fy0) * ph
    if larg <= 4 or alt <= 4:
        return None
    dpi = min(MAX_DPI, MAX_EDGE_PX * 72.0 / max(larg, alt))
    # pypdfium2: crop = quanto CORTAR de cada lado (esq, baixo, dir, cima).
    # Como é corte relativo à própria página, a origem deslocada não atrapalha.
    cortes = (fx0 * pw, fy0 * ph, (1.0 - fx1) * pw, (1.0 - fy1) * ph)
    bmp = page.render(scale=dpi / 72.0, crop=cortes)
    buf = io.BytesIO()
    bmp.to_pil().convert("RGB").save(buf, format="JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def normalizar(bruto, n_imagens) -> list:
    """JSON do modelo -> lista de denominadores (int|None), uma por imagem.

    🪤 Decisão pura, testável sem rede. O modelo pode devolver a lista fora de
    ordem, com índice repetido, ou com texto no lugar do número.
    """
    saida = [None] * max(0, int(n_imagens or 0))
    if not isinstance(bruto, dict):
        return saida
    for item in (bruto.get("vistas") or []):
        if not isinstance(item, dict):
            continue
        try:
            i = int(item.get("i"))
        except (TypeError, ValueError):
            continue
        if not (0 <= i < len(saida)) or saida[i] is not None:
            continue
        m = _SCALE_RE.search(str(item.get("escala") or ""))
        if m:
            try:
                d = int(m.group(1))
            except (TypeError, ValueError):
                continue
            if d > 0:
                saida[i] = d
    return saida


def escala_principal(por_vista, areas=None) -> Optional[int]:
    """A escala da MAIOR vista que teve rótulo lido.

    🔑 Maior vista, não a mais frequente: numa prancha "como se indica" a planta
    grande e o pormenor têm escalas DIFERENTES de propósito, e é a planta que
    manda no quantitativo. Frequência elegeria o pormenor, que costuma repetir.
    """
    cands = [(i, d) for i, d in enumerate(por_vista or []) if d]
    if not cands:
        return None
    if areas:
        cands.sort(key=lambda t: -(areas[t[0]] if t[0] < len(areas) else 0))
    return cands[0][1]


#: O rótulo COM a palavra: "ESC/ 1:50", "ESC. 1:25", "ESCALA 1:100", "esc 1/20".
#: O `[^0-9]{0,6}` engole o separador seja ele qual for — e foi barra (`ESC/`)
#: no arquivo que abriu este caso, não dois-pontos.
_RE_ESC_COM_ROTULO = re.compile(
    r"\bESC(?:ALA)?S?\b[^0-9]{0,6}1\s*[:/]\s*(\d{1,4})\b", re.I)

#: A razão SOZINHA, sem a palavra ao lado. Menos confiável: só vale quando a
#: vista inteira concorda num valor só (ver `escala_do_rotulo`).
_RE_ESC_SOLTA = re.compile(r"\b1\s*[:/]\s*(\d{1,4})\b")


def escala_do_rotulo(texto):
    """Denominador da escala escrita num pedaço de texto de prancha.

    🩸 POR QUE ESTA FUNÇÃO EXISTE — 23/09/2026, prancha de estrutura de um
    cliente (`f57e3dba`). O log dizia `sem escala (viewport, carimbo nem cota)`
    numa página que trazia **`ESC/ 1:50` e `ESC/ 1:25` setenta vezes**, uma por
    viga. O módulo já recortava a vista certa — só que mandava a IMAGEM pro
    Vision perguntar a escala, e o Vision devolveu `None` nas 6 vistas.

    🔑 O texto estava ali o tempo todo, dentro do PDF, extraível em
    milissegundos e de graça. Pagamos uma chamada de IA pra adivinhar um dado
    ESCRITO no arquivo — e erramos.

    Devolve `(denominador, "esc"|"solta")`, ou `(None, None)`.

    🪤 A razão SOLTA (`1:50` sem a palavra "ESC") só é aceita quando a vista
    inteira traz um único valor: número no formato `a:b` também aparece em
    proporção de armadura e referência de detalhe, e um chute aqui vira erro de
    escala — que multiplica TODA a medição da prancha (regra dura nº1).

    Função PURA: sem PDF, sem rede. É o que o guarda consegue CHAMAR.
    """
    if not texto:
        return (None, None)
    com_rotulo = [int(m.group(1)) for m in _RE_ESC_COM_ROTULO.finditer(texto)]
    com_rotulo = [d for d in com_rotulo if d > 0]
    if com_rotulo:
        return (_vence(com_rotulo), "esc")
    soltas = {int(m.group(1)) for m in _RE_ESC_SOLTA.finditer(texto)}
    soltas = {d for d in soltas if d > 0}
    if len(soltas) == 1:
        return (soltas.pop(), "solta")
    return (None, None)


def _vence(denominadores):
    """O denominador que manda, quando a vista traz mais de um rótulo.

    🔑 Critério: o MAIS FREQUENTE; empate resolve no MAIOR denominador. Numa
    prancha de vigas, cada recorte pega a elevação (`ESC/ 1:50`) e a seção A-A
    ao lado (`ESC/ 1:25`) — uma vez cada, empate. O desenho PRINCIPAL é o menos
    ampliado dos dois, e é ele que manda no quantitativo; a seção é o detalhe.
    🚫 Calibrado em UM arquivo real, como o resto deste módulo. Por isso a
    escolha viaja no log (`fonte_da_escala`), pra dar pra conferir depois.
    """
    if not denominadores:
        return None
    contagem = {}
    for d in denominadores:
        contagem[d] = contagem.get(d, 0) + 1
    return sorted(contagem.items(), key=lambda kv: (-kv[1], -kv[0]))[0][0]


def caixa_absoluta(caixa, frac):
    """A fração da página de volta em PONTOS — o que o textpage entende.

    🔑 Usa a MESMA geometria do recorte que iria pro Vision, inclusive o
    "estender até a margem esquerda". Assim o texto lido é exatamente o que a
    imagem mostraria: as duas fontes nunca discordam por olharem lugares
    diferentes. Pura, pelo mesmo motivo que `recorte_da_vista`.
    """
    px0, py0, px1, py1 = caixa
    W = float(px1 - px0) or 1.0
    H = float(py1 - py0) or 1.0
    fx0, fy0, fx1, fy1 = frac
    return (px0 + fx0 * W, py0 + fy0 * H, px0 + fx1 * W, py0 + fy1 * H)


def escalas_do_texto(page, caixa, fracs):
    """Lê a escala ESCRITA dentro de cada recorte. Zero rede, zero token.

    Devolve `(denominadores, fontes)` — uma entrada por recorte, `None` onde
    não havia rótulo legível.

    🪤 PDF de prancha escaneada (imagem pura) não tem texto: devolve tudo
    `None` e o Vision assume, como antes. Esta função ADICIONA um caminho
    barato, nunca tira o que já funcionava.
    """
    dens = [None] * len(fracs)
    fontes = [None] * len(fracs)
    try:
        tp = page.get_textpage()
    except Exception:
        return (dens, fontes)
    for i, frac in enumerate(fracs):
        try:
            l, b, r, t = caixa_absoluta(caixa, frac)
            txt = tp.get_text_bounded(l, b, r, t)
        except Exception:
            continue
        d, fonte = escala_do_rotulo(txt)
        if d:
            dens[i] = d
            fontes[i] = fonte
    return (dens, fontes)


def read_view_scales(pdf_path: str, page_index: int = 0, views=None,
                     max_vistas: int = MAX_VISTAS, _cliente=None) -> dict:
    """Lê a escala ao lado de cada vista. Uma chamada Vision pra todas.

    Devolve {"por_vista": [...], "main_scale": int|None, "n_vistas": int,
             "bboxes": [...]}  — `bboxes` fica no retorno de propósito, pra
    conferir no log DE ONDE veio cada leitura.
    """
    fora = {"por_vista": [], "main_scale": None, "n_vistas": 0, "bboxes": []}
    if views is None:
        try:
            from pdfvec_views import detect_views
            views = detect_views(pdf_path, page_index)
        except Exception as e:
            fora["erro"] = f"{type(e).__name__}: {e}"[:120]
            return fora
    views = list(views or [])[:max_vistas]
    if not views:
        return fora

    doc = pdfium.PdfDocument(pdf_path)
    try:
        if page_index >= len(doc):
            fora["erro"] = "pagina inexistente"
            return fora
        page = doc[page_index]
        caixa = _caixa_da_pagina(page)
        fracs, usadas, areas = [], [], []
        for v in views:
            bb = v.get("bbox") if isinstance(v, dict) else v
            if not bb:
                continue
            fracs.append(recorte_da_vista(caixa, bb))
            usadas.append(bb)
            areas.append(abs((bb[2] - bb[0]) * (bb[3] - bb[1])))
        if not fracs:
            return fora

        # 🔑 1ª FONTE: o TEXTO que já está no PDF (23/09/2026). De graça, em
        # milissegundos, e exato — contra uma chamada de Vision que na prancha
        # que abriu este caso devolveu None nas 6 vistas com a escala escrita
        # 70 vezes ao lado. O Vision continua logo abaixo, como rede de
        # segurança pra prancha escaneada, que não tem texto nenhum.
        do_texto, fontes = escalas_do_texto(page, caixa, fracs)
        faltam = [i for i, d in enumerate(do_texto) if not d]

        # Só renderiza (e só paga) o que o texto NÃO resolveu.
        jpegs, idx_do_jpeg = [], []
        for i in faltam:
            img = _render_fracao(page, fracs[i])
            if img:
                jpegs.append(img); idx_do_jpeg.append(i)
    finally:
        doc.close()

    fora["n_vistas"] = len(fracs)
    fora["bboxes"] = [[round(float(c), 1) for c in b] for b in usadas]
    fora["do_texto"] = list(do_texto)
    fora["fonte_da_escala"] = list(fontes)
    fora["vision_pediu"] = len(jpegs)

    if not jpegs:
        # 🎉 O texto resolveu tudo: nenhuma imagem renderizada, nenhum token.
        fora["por_vista"] = list(do_texto)
        fora["main_scale"] = escala_principal(do_texto, areas)
        return fora

    try:
        cli = _cliente
        if cli is None:
            import anthropic
            from pdfvec_carimbo import _load_api_key
            cli = anthropic.Anthropic(api_key=_load_api_key())
        content = [{"type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg",
                               "data": base64.standard_b64encode(j).decode("ascii")}}
                   for j in jpegs]
        content.append({"type": "text", "text": _PROMPT})
        from llm_retry import call_with_retry
        resp = call_with_retry(
            cli, tag="pdfvec-escala-vista", max_retries=3, base_delay=2.0,
            max_delay=20.0, model=MODEL, max_tokens=500,
            messages=[{"role": "user", "content": content}])
        texto = next((b.text for b in resp.content if b.type == "text"), "")
        m = re.search(r"\{.*\}", texto, re.DOTALL)
        bruto = json.loads(m.group(0)) if m else {}
    except Exception as e:
        # 🪤 Vision caiu — mas o que o TEXTO já leu continua valendo. Antes
        # deste caminho, um erro aqui devolvia a página inteira sem escala.
        fora["erro"] = f"{type(e).__name__}: {e}"[:120]
        fora["por_vista"] = list(do_texto)
        fora["main_scale"] = escala_principal(do_texto, areas)
        return fora

    # A resposta do modelo é sobre as vistas QUE FALTARAM, na ordem em que
    # foram enviadas — volta pro índice original por `idx_do_jpeg`.
    do_vision = normalizar(bruto, len(jpegs))
    junto = list(do_texto)
    for k, i in enumerate(idx_do_jpeg):
        if junto[i] is None and k < len(do_vision) and do_vision[k]:
            junto[i] = do_vision[k]
            fontes[i] = "vision"

    fora["fonte_da_escala"] = list(fontes)
    fora["por_vista"] = junto
    fora["main_scale"] = escala_principal(junto, areas)
    return fora
