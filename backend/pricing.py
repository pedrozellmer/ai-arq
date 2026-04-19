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


PRICE_PER_SHEET_CENTS = 2000  # R$ 20 por prancha
MIN_PRICE_CENTS = 9700        # R$ 97 mínimo (cobre 4-5 pranchas pequenas)


def calculate_price(num_pranchas: int) -> int:
    """Retorna preço em centavos."""
    if num_pranchas < 1:
        num_pranchas = 1
    raw = num_pranchas * PRICE_PER_SHEET_CENTS
    return max(MIN_PRICE_CENTS, raw)


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
    """Conta paper-space layouts de um DXF (ou DWG convertido pra DXF).

    Cada paper-space = 1 prancha desenhada com viewport pra impressão.
    Model space sozinho = 1 prancha implícita. ezdxf expõe `doc.layouts`
    com a lista — 'Model' + paper-spaces (Layout1, Layout2, ...).
    """
    try:
        import ezdxf
        doc = ezdxf.readfile(path)
        # ezdxf.layouts é um LayoutManager — len() funciona
        names = [name for name in doc.layouts.names() if name.lower() != "model"]
        # Pelo menos 1 (model space sempre existe)
        return max(1, len(names))
    except Exception:
        # Se for DWG (não DXF) ou falha qualquer, conta como 1
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


def estimate_for_files(file_paths: list[str]) -> dict:
    """Conveniência: conta pranchas + calcula preço de uma vez."""
    sheets = count_real_sheets(file_paths)
    n = sheets["total_pranchas"]
    price_cents = calculate_price(n)
    return {
        **sheets,
        "price_cents": price_cents,
        "price_brl": round(price_cents / 100, 2),
        "price_per_sheet_cents": PRICE_PER_SHEET_CENTS,
        "min_price_cents": MIN_PRICE_CENTS,
    }
