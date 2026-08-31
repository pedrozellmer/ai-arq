# -*- coding: utf-8 -*-
"""Cálculo de preço por prancha real (não por arquivo).

Bug antigo: cliente subia 1 PDF com 15 páginas → cobrava como 1 arquivo
(R$ 97). Pricing tinha pulo perverso 10→11 que incentivava dividir.

Agora:
- Conta páginas reais dentro de PDFs
- Conta layouts de paper-space dentro de DWG/DXF (cada viewport = 1 prancha)
- Modelo linear: max(R$ 97, R$ 20 × pranchas), sem pulos
"""
import os
from pathlib import Path
from typing import Optional


MIN_PRICE_CENTS = 9700  # R$ 97 mínimo (tier Pequeno)

# Três tiers com economia de escala — projetos grandes pagam menos por
# prancha. Checado: em TODAS as bordas, juntar pranchas num só projeto
# sai mais barato que dividir em jobs menores (sem incentivo perverso).
#
#   1-5 pranchas   → R$ 97   (R$ 19,40/prancha)
#   6-10 pranchas  → R$ 157  (R$ 15,70/prancha, -19% vs Pequeno)
#   11-20 pranchas → R$ 247  (R$ 12,35/prancha, -36% vs Pequeno)
#   21+ pranchas   → R$ 247 + R$ 10 × (n-20)  (marginal mais barata ainda)
TIERS = [
    {"max": 5,  "price_cents":  9700, "name": "Pequeno"},
    {"max": 10, "price_cents": 15700, "name": "Médio"},
    {"max": 20, "price_cents": 24700, "name": "Grande"},
]
EXTRA_PRICE_PER_SHEET_CENTS = 1000  # R$ 10/prancha acima de 20


def calculate_price(num_pranchas: int) -> int:
    """Retorna preço em centavos pra N pranchas, com economia de escala
    nos 3 tiers e taxa marginal baixa acima de 20.

    Monotônica (sempre crescente) e sem incentivo a dividir em jobs menores.
    """
    if num_pranchas < 1:
        num_pranchas = 1
    for tier in TIERS:
        if num_pranchas <= tier["max"]:
            return tier["price_cents"]
    # acima do último tier, adiciona R$ 10/prancha pelo excedente
    last = TIERS[-1]
    extra = num_pranchas - last["max"]
    return last["price_cents"] + extra * EXTRA_PRICE_PER_SHEET_CENTS


def get_tier_for(num_pranchas: int) -> dict:
    """Retorna o tier ao qual as pranchas pertencem (ou 'XL' se acima)."""
    for tier in TIERS:
        if num_pranchas <= tier["max"]:
            return tier
    return {"max": None, "price_cents": calculate_price(num_pranchas), "name": "XL"}


def count_pdf_pages(path: str) -> int:
    """Conta páginas reais de um PDF. Tenta pdfplumber primeiro (já no
    requirements.txt), fallback pra pypdfium2. Retorna 1 se falhar."""
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return max(1, len(pdf.pages))
    except Exception:
        pass
    try:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(path)
        n = max(1, len(doc))
        doc.close()
        return n
    except Exception:
        return 1


def count_dwg_layouts(path: str) -> int:
    """Conta paper-space layouts de um DXF SEM carregar o documento no ezdxf.

    Cada paper-space = 1 prancha desenhada com viewport pra impressão.
    Model space sozinho = 1 prancha implícita.

    🔒 Segurança (fix 2026-07-22): esta função roda no /api/estimate-price, que é
    PÚBLICO. `ezdxf.readfile()` expande o DXF em objetos Python — um DXF denso
    (pequeno em disco, milhões de entidades) podia estourar a RAM do worker e
    derrubar o serviço (DoS anônimo). Aqui contamos os marcadores de layout
    direto nos BYTES do arquivo (custo O(tamanho em disco), limitado pelo cap de
    upload), sem materializar entidades. Cada objeto LAYOUT (Model + paper-spaces)
    carrega um subclass marker 'AcDbLayout'. O motor real (processamento pago)
    segue no caminho preciso — aqui é só a estimativa de preço.
    """
    try:
        with open(path, "rb") as f:
            data = f.read(200 * 1024 * 1024)  # cap de leitura (~200MB)
        n_layouts = data.count(b"AcDbLayout")
        if n_layouts <= 0:
            return 1  # DWG binário / sem marcador → 1 prancha implícita
        # Tira o Model space (sempre presente) → sobram os paper-spaces.
        return max(1, n_layouts - 1)
    except Exception:
        # DWG puro ou falha qualquer: conta como 1.
        return 1


def count_real_sheets(file_paths: list[str]) -> dict:
    """Itera os arquivos e conta pranchas reais dentro de cada um.

    Retorna:
        {
          "total_pranchas": int,
          "breakdown": [{filename, type, pranchas}, ...],
          "files_count": int,
        }
    """
    breakdown = []
    total = 0
    for path in file_paths:
        if not os.path.exists(path):
            continue
        name = os.path.basename(path)
        ext = Path(name).suffix.lower()
        if ext == ".pdf":
            n = count_pdf_pages(path)
            ftype = "pdf"
        elif ext == ".dxf":
            n = count_dwg_layouts(path)
            ftype = "dxf"
        elif ext == ".dwg":
            # DWG sem conversão prévia: ezdxf não lê. Conta como 1 (será
            # contado depois quando virar DXF, mas pra estimativa pré-pagamento
            # esse é o melhor que dá).
            n = 1
            ftype = "dwg"
        else:
            n = 1
            ftype = ext.lstrip(".") or "?"
        breakdown.append({"filename": name, "type": ftype, "pranchas": n})
        total += n

    return {
        "total_pranchas": max(1, total),
        "breakdown": breakdown,
        "files_count": len(file_paths),
    }


def estimate_for_files(file_paths: list[str], extra_pranchas: int = 0) -> dict:
    """Conveniência: conta pranchas + calcula preço de uma vez.

    `extra_pranchas` (29/08/2026): pranchas que o cliente JÁ teve contadas em
    chamada anterior — o front manda só os arquivos NOVOS e informa o total
    conhecido, em vez de re-enviar tudo a cada mudança na seleção. O preço é
    calculado sobre a SOMA; a contagem em si continua 100% do servidor (o
    número informado nasceu de contagem nossa — e preço de estimativa é
    preview: o checkout reconta tudo do zero no /api/process).
    """
    if file_paths:
        sheets = count_real_sheets(file_paths)
    else:
        # só reprecificação (cliente removeu arquivo): nada a contar
        sheets = {"total_pranchas": 0, "breakdown": [], "files_count": 0}
    n = max(1, sheets["total_pranchas"] + max(0, int(extra_pranchas or 0)))
    sheets["total_pranchas"] = n
    price_cents = calculate_price(n)
    tier = get_tier_for(n)
    return {
        **sheets,
        "price_cents": price_cents,
        "price_brl": round(price_cents / 100, 2),
        "tier_name": tier["name"],
        "min_price_cents": MIN_PRICE_CENTS,
    }


# ── Precheck de quantificabilidade (QW5, 20/07) ──────────────────────────────
# Roda no /api/estimate-price reaproveitando o arquivo JÁ em disco (alcança
# inclusive quem não vai pagar nada — a "1ª impressão" do cliente novo, que no
# beta é todo mundo, já que é grátis e ilimitado). Avisa ANTES
# de pagar quando o arquivo claramente não vai medir bem. BARATO e conservador:
# só lê amostra/header (sem ezdxf.readfile no arquivo inteiro, que arriscaria
# OOM no worker), e só avisa quando é MUITO claramente imagem/proxy — na dúvida,
# fica calado. O aviso é ADVISORY: não bloqueia o checkout, só orienta.
_PRECHECK_PDF_SAMPLE = 3    # nº de páginas amostradas por PDF
_PRECHECK_MIN_CHARS = 20    # abaixo disso, nas páginas amostradas, cheira a imagem


def _pdf_parece_escaneado(path: str) -> bool:
    """True só quando as primeiras páginas amostradas têm texto vetorial ~zero
    (cheira a escaneado/imagem). PDF exportado do CAD sempre tem cotas/legendas,
    então não dá falso-positivo. Barato: pdfplumber carrega página sob demanda.
    Na dúvida (qualquer erro), retorna False — nunca super-avisa."""
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            paginas = pdf.pages[:_PRECHECK_PDF_SAMPLE]
            if not paginas:
                return False
            total = 0
            for pg in paginas:
                try:
                    total += len((pg.extract_text() or "").strip())
                except Exception:
                    return False  # falha de página não afirma "escaneado"
                if total >= _PRECHECK_MIN_CHARS:
                    return False
            return total < _PRECHECK_MIN_CHARS
    except Exception:
        return False


def precheck_warnings(file_paths: list[str]) -> list[str]:
    """Lista de avisos ANTES de pagar (vazia = nada a apontar). Best-effort —
    nunca levanta. Campo novo/opcional na resposta do estimate: front antigo
    ignora, não muda preço."""
    avisos: list[str] = []
    for p in file_paths or []:
        ext = os.path.splitext(p)[1].lower()
        try:
            if ext == ".pdf":
                if _pdf_parece_escaneado(p):
                    avisos.append(
                        f"⚠ {os.path.basename(p)}: parece um PDF escaneado ou de "
                        f"imagem — o motor mede PDF vetorial exportado direto do CAD "
                        f"(AutoCAD/Revit). Escaneado costuma render poucos itens. Se "
                        f"puder, envie o DWG/DXF ou o PDF vetorial da prancha."
                    )
            elif ext == ".dwg":
                try:
                    from dwg_extractor import dwg_has_aec_markers
                    if dwg_has_aec_markers(p):
                        avisos.append(
                            f"⚠ {os.path.basename(p)}: é um DWG com objetos "
                            f"inteligentes AEC/MEP (AutoCAD Architecture/Revit). Os "
                            f"conversores livres não leem esses objetos — pra medir "
                            f"bem, exporte em DXF ou faça BIND/explode antes de subir."
                        )
                except Exception:
                    pass
        except Exception:
            continue
    return avisos
