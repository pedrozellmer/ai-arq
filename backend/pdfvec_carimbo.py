# -*- coding: utf-8 -*-
"""pdfvec_carimbo.py — Lê a ESCALA DECLARADA no carimbo da prancha via Claude Vision.

Módulo da "Medição Vetorial de PDF v1" (AI.arq). Complementa pdfvec_scale.py
(derivação geométrica): quando a prancha NÃO tem cota em texto, o carimbo é a
única fonte da escala declarada — e carimbo plotado vira desenho/curva, então
só Vision lê.

Como funciona
-------------
1. Renderiza CROPS da página com pypdfium2 (nunca a folha inteira):
   - faixa direita (~18% da largura), dividida em metade superior e inferior
     (carimbo típico de A1/A0 paisagem);
   - faixa inferior (~12% da altura), metades esquerda/direita (carimbo de
     folha pequena/retrato, ex. A4).
   Cada crop é renderizado no DPI mais alto que mantém o lado longo <=1568 px
   (limite de downscale do Vision — mandar maior só perderia nitidez), capado
   em 300 DPI. Na A1 isso dá ~134 DPI efetivos no crop: suficiente pra texto
   de carimbo.
2. Manda os crops pro claude-haiku-4-5-20251001 (max_tokens 300) pedindo JSON
   {"scales": [...], "indicadas": bool}. Se vier vazio/incerto/não-JSON,
   tenta 1x com claude-sonnet-4-6.
3. Normaliza ("1/100", "1-100", "1:100" -> "1:100") e escolhe main_scale =
   denominador mais frequente (empate: primeiro citado).

Cache: carimbo_cache.json ao lado deste módulo, chave = sha256 do arquivo +
página + versão do prompt. Re-runs não pagam API.

Chave: ANTHROPIC_API_KEY lida do .env do backend (nunca impressa/logada).

Uso:  python pdfvec_carimbo.py [arquivo.pdf ...]   (sem args roda o corpus)
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
from collections import Counter
from typing import Optional

import pypdfium2 as pdfium

# ── configuração ──────────────────────────────────────────────────────────────
_ENV_PATH = r"C:\Users\admin\Desktop\arq\projeto_arq\backend\.env"
_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "carimbo_cache.json")
_PROMPT_VERSION = "v3"          # muda -> invalida cache

MODEL_PRIMARY = "claude-haiku-4-5-20251001"
MODEL_FALLBACK = "claude-sonnet-4-6"

RIGHT_STRIP_FRAC = 0.18         # faixa direita (largura)
BOTTOM_STRIP_FRAC = 0.12        # faixa inferior (altura)
MAX_EDGE_PX = 1568              # acima disso o Vision faz downscale
MAX_DPI = 300.0
JPEG_QUALITY = 88

_PROMPT = (
    "Estas imagens sao recortes (borda direita e borda inferior) de uma "
    "prancha de projeto de arquitetura em PDF. Procure o CARIMBO (selo/"
    "legenda da folha) e leia a ESCALA DECLARADA nele — campos como "
    "'ESCALA', 'ESC.', 'ESCALAS'. Pranchas podem declarar VARIAS escalas "
    "(ex.: '1/100 e 1/50') ou a palavra 'INDICADA'/'INDICADAS' (escala "
    "indicada em cada desenho). Ignore numeros que nao sejam escala "
    "(datas, revisoes, codigos de folha, areas).\n"
    "Responda APENAS com JSON, sem texto extra, neste formato:\n"
    '{"scales": ["1:100", "1:50"], "indicadas": false}\n'
    "- scales: lista das escalas declaradas no carimbo, normalizadas como "
    '"1:N" (se o carimbo mostra "1/75", devolva "1:75"). Lista vazia se '
    "nenhuma escala numerica estiver declarada.\n"
    "- indicadas: true se o carimbo declara escala 'INDICADA(S)'.\n"
    "Se nao encontrar carimbo ou campo de escala, devolva "
    '{"scales": [], "indicadas": false}.'
)

_SCALE_RE = re.compile(r"1\s*[:/\-]\s*(\d{1,4})")


# ── chave da API ─────────────────────────────────────────────────────────────

def _load_api_key() -> str:
    """ANTHROPIC_API_KEY do ambiente (produção/Render) ou do .env local
    (desenvolvimento). NUNCA imprimir o valor."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    try:
        with open(_ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("ANTHROPIC_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if key:
                        return key
    except OSError:
        pass
    raise RuntimeError("ANTHROPIC_API_KEY nao encontrada (env nem .env)")


# ── renderização dos crops ───────────────────────────────────────────────────

def _render_crop(page: "pdfium.PdfPage", left: float, bottom: float,
                 right: float, top: float) -> bytes:
    """Renderiza o retângulo (pontos PDF, y pra cima) como JPEG.

    DPI = o maior que mantém o lado longo <= MAX_EDGE_PX (cap MAX_DPI).
    pypdfium2: crop=(left, bottom, right, top) = quanto CORTAR de cada lado.
    """
    pw, ph = page.get_width(), page.get_height()
    cw, ch = right - left, top - bottom
    if cw <= 1 or ch <= 1:
        raise ValueError("crop degenerado")
    dpi = min(MAX_DPI, MAX_EDGE_PX * 72.0 / max(cw, ch))
    scale = dpi / 72.0
    bitmap = page.render(
        scale=scale,
        crop=(left, bottom, pw - right, ph - top),
    )
    img = bitmap.to_pil().convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def _carimbo_crops(page: "pdfium.PdfPage") -> list[bytes]:
    """Crops candidatos a conter o carimbo, em JPEG.

    Ordem importa (o modelo vê nessa ordem): faixa direita inferior (posição
    mais comum do campo escala em A1/A0), faixa direita superior, faixa
    inferior direita, faixa inferior esquerda.
    """
    w, h = page.get_width(), page.get_height()
    x_strip = w * (1.0 - RIGHT_STRIP_FRAC)
    y_strip = h * BOTTOM_STRIP_FRAC
    rects = [
        (x_strip, 0.0, w, h / 2),        # direita, metade de baixo
        (x_strip, h / 2, w, h),          # direita, metade de cima
        (w / 2, 0.0, w, y_strip),        # inferior, metade direita
        (0.0, 0.0, w / 2, y_strip),      # inferior, metade esquerda
    ]
    return [_render_crop(page, *r) for r in rects]


# ── chamada Vision ───────────────────────────────────────────────────────────

def _ask_model(client, model: str, jpegs: list[bytes]) -> Optional[dict]:
    """Uma chamada Vision. Devolve dict do JSON ou None se não parseável."""
    content: list[dict] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.standard_b64encode(j).decode("ascii"),
            },
        }
        for j in jpegs
    ]
    content.append({"type": "text", "text": _PROMPT})
    # 🚨 Esta é a 3ª e ÚLTIMA fonte de escala do PDF (depois de viewport e
    # cotas). Se ela falhar por um 429 de rajada, a prancha fica SEM ESCALA e
    # não mede nada — medido em 11/08: 14 de 14 skips do motor vetorial são
    # "sem escala". Perder isto por erro transitório sai caro, então retry
    # generoso: roda dentro do processamento, ninguém está esperando na tela.
    from llm_retry import call_with_retry
    response = call_with_retry(
        client,
        tag="pdfvec-carimbo", max_retries=5, base_delay=2.0, max_delay=30.0,
        model=model,
        max_tokens=300,
        messages=[{"role": "user", "content": content}],
    )
    text = next((b.text for b in response.content if b.type == "text"), "")
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _normalize(raw: dict) -> tuple[list[str], bool]:
    """Normaliza a resposta do modelo -> (["1:100", ...], indicadas)."""
    scales: list[str] = []
    for item in raw.get("scales") or []:
        m = _SCALE_RE.search(str(item))
        if m:
            s = f"1:{int(m.group(1))}"
            if s not in scales:
                scales.append(s)
    indicadas = bool(raw.get("indicadas"))
    return scales, indicadas


# ── cache ────────────────────────────────────────────────────────────────────

def _cache_load() -> dict:
    try:
        with open(_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _cache_save(cache: dict) -> None:
    tmp = _CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _CACHE_PATH)


def _cache_key(pdf_path: str, page_index: int) -> str:
    h = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return f"{h.hexdigest()}:{page_index}:{_PROMPT_VERSION}"


# ── API pública ──────────────────────────────────────────────────────────────

def read_carimbo_scale(pdf_path: str, page_index: int = 0,
                       use_cache: bool = True) -> dict:
    """Lê a(s) escala(s) declarada(s) no carimbo da prancha via Claude Vision.

    Retorna dict com:
      declared_scales : ["1:100", ...] — escalas declaradas, normalizadas,
                        na ordem em que o carimbo cita
      main_scale      : int | None — denominador da escala da PLANTA
                        (mais frequente na lista; empate = primeira citada)
      indicadas       : bool — carimbo declara "INDICADA(S)"
      confidence      : "alta" (leitura direta do Haiku) | "media" (precisou
                        do fallback Sonnet) | "baixa" (nada encontrado)
      model_used      : id do modelo que produziu a resposta final
    """
    cache = _cache_load() if use_cache else {}
    key = _cache_key(pdf_path, page_index)
    if key in cache:
        return dict(cache[key])

    doc = pdfium.PdfDocument(pdf_path)
    try:
        if page_index >= len(doc):
            raise IndexError(f"pagina {page_index} inexistente em {pdf_path}")
        jpegs = _carimbo_crops(doc[page_index])
    finally:
        doc.close()

    import anthropic
    client = anthropic.Anthropic(api_key=_load_api_key())

    scales: list[str] = []
    indicadas = False
    confidence = "baixa"
    model_used = MODEL_PRIMARY

    raw = _ask_model(client, MODEL_PRIMARY, jpegs)
    if raw is not None:
        scales, indicadas = _normalize(raw)
        if scales or indicadas:
            confidence = "alta"

    if not scales and not indicadas:          # vazio/incerto -> 1 retry Sonnet
        raw = _ask_model(client, MODEL_FALLBACK, jpegs)
        model_used = MODEL_FALLBACK
        if raw is not None:
            scales, indicadas = _normalize(raw)
            if scales or indicadas:
                confidence = "media"

    denominators = [int(s.split(":")[1]) for s in scales]
    main_scale: Optional[int] = None
    if denominators:
        counts = Counter(denominators)
        best = max(counts.values())
        main_scale = next(d for d in denominators if counts[d] == best)

    result = {
        "declared_scales": scales,
        "main_scale": main_scale,
        "indicadas": indicadas,
        "confidence": confidence,
        "model_used": model_used,
    }
    # 🩸 05/09/2026 — NÃO CACHEAR NEGATIVO. A A08 do cliente-39 (135fdfac) teve a
    # escala lida como 1:75 em cinco chamadas ao longo do dia; na sexta o Haiku
    # respondeu diferente (sem escala), o resultado foi gravado aqui, e a
    # tentativa seguinte NEM PERGUNTOU à Vision — leu o cache e saiu "sem
    # escala", a sombra idem. Uma leitura ruim virava permanente pro arquivo
    # até o próximo deploy (o disco do Render zera no deploy — por isso as
    # cinco anteriores "deram certo": eram todas chamadas novas).
    # Só grava quando LEU uma escala. Negativo (incluindo "indicadas" sem
    # número) é reperguntado na próxima — custa uma chamada do Haiku e dá à
    # segunda tentativa a chance de acertar.
    if use_cache and result["main_scale"] is not None:
        cache[key] = result
        _cache_save(cache)
    return result


# ── auto-teste no corpus ─────────────────────────────────────────────────────

_CORPUS = [
    r"C:\Users\admin\Desktop\arq\0326.CGR.14.100.DEMOLIR.02-A1.pdf",
    r"C:\Users\admin\Desktop\arq\0326.CGR.14.200.LAYOUT.02-A1.pdf",
    r"C:\Users\admin\Desktop\arq\0326.CGR.14.301.MARCENARIA.00-A0.pdf",
    r"C:\Users\admin\Desktop\arq\0326.CGR.14.400.ARQUITETURA.02-A1.pdf",
    r"C:\Users\admin\Desktop\arq\0326.CGR.14.500.PONTOS.02-A1.pdf",
    r"C:\Users\admin\Desktop\arq\0326.CGR.14.600.PISO.02-a1.pdf",
    r"C:\Users\admin\Desktop\arq\0326.CGR.14.700.FORRO.02-A1.pdf",
    r"C:\Users\admin\Desktop\arq\LAYOUT ATENDAS rev 01.pdf",
]

if __name__ == "__main__":
    import sys
    import time
    paths = sys.argv[1:] or _CORPUS
    for path in paths:
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        t0 = time.time()
        try:
            res = read_carimbo_scale(path)
        except Exception as exc:  # noqa: BLE001 — auto-teste não pode abortar
            print(f"{name}: ERRO {type(exc).__name__}: {exc}")
            continue
        res["elapsed_s"] = round(time.time() - t0, 1)
        print(f"{name}: {json.dumps(res, ensure_ascii=False)}")
