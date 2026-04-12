# -*- coding: utf-8 -*-
"""Pipeline de processamento de PDFs de arquitetura."""
import os
import re
import tempfile
from pathlib import Path
import pdfplumber
import pypdfium2 as pdfium
from PIL import Image
from models import SheetType, SheetInfo


# Mapeamento de nomes de arquivo para tipos de prancha
SHEET_PATTERNS = {
    SheetType.DEMOLIR: [r"demolir", r"demoli", r"100\."],
    SheetType.LAYOUT_NOVO: [r"layout\s*novo", r"200\."],
    SheetType.LAYOUT_ATUAL: [r"layout\s*atual", r"201\."],
    SheetType.MOBILIARIO: [r"mobili", r"300\."],
    SheetType.MARCENARIA: [r"marcenaria", r"301\."],
    SheetType.ARQUITETURA: [r"arquitetura", r"400\."],
    SheetType.PONTOS: [r"pontos", r"500\."],
    SheetType.PISO: [r"piso", r"600\."],
    SheetType.FORRO: [r"forro\.?\d*\-", r"forro.*00", r"700\."],
    SheetType.DET_FORRO: [r"det\s*forro", r"701\."],
}

# Regiões de crop por tipo de prancha (frações x1, y1, x2, y2)
CROP_REGIONS = {
    SheetType.ARQUITETURA: {
        "legenda_fechamentos": (0.58, 0.0, 0.95, 0.14),
        "legenda_revestimentos": (0.58, 0.12, 0.82, 0.35),
        "legenda_portas": (0.58, 0.30, 0.82, 0.58),
        "legenda_divisorias": (0.58, 0.55, 0.95, 0.72),
        "planta_esquerda": (0.02, 0.03, 0.30, 0.80),
        "planta_centro": (0.25, 0.03, 0.55, 0.80),
    },
    SheetType.FORRO: {
        "legenda_luminarias": (0.55, 0.75, 1.0, 1.0),
        "legenda_tecnica": (0.55, 0.50, 1.0, 0.78),
        "planta_geral": (0.02, 0.02, 0.55, 0.75),
    },
    SheetType.PISO: {
        "legenda": (0.58, 0.0, 0.90, 0.35),
        "planta": (0.02, 0.02, 0.58, 0.95),
    },
    SheetType.PONTOS: {
        "legenda_completa": (0.58, 0.0, 0.95, 0.70),
        "planta": (0.02, 0.03, 0.55, 0.85),
    },
    SheetType.MOBILIARIO: {
        "legenda_departamentos": (0.58, 0.0, 0.90, 0.18),
        "legenda_moveis": (0.58, 0.18, 0.90, 0.55),
        "legenda_equipamentos": (0.58, 0.55, 0.90, 0.75),
    },
    SheetType.MARCENARIA: {
        "legenda": (0.58, 0.0, 0.90, 0.50),
    },
    SheetType.DEMOLIR: {
        "legenda": (0.58, 0.0, 0.95, 0.25),
        "planta": (0.02, 0.02, 0.58, 0.95),
    },
    SheetType.LAYOUT_NOVO: {
        "legenda": (0.58, 0.0, 0.95, 0.50),
        "planta": (0.02, 0.03, 0.58, 0.90),
    },
    SheetType.LAYOUT_ATUAL: {
        "legenda": (0.58, 0.0, 0.95, 0.50),
        "planta": (0.02, 0.03, 0.58, 0.90),
    },
    SheetType.DET_FORRO: {
        "planta": (0.0, 0.0, 0.45, 0.45),
        "detalhes": (0.45, 0.0, 1.0, 0.45),
    },
}


def identify_sheet_type(filename: str) -> SheetType:
    """Identifica o tipo de prancha pelo nome do arquivo."""
    name_lower = filename.lower()
    for sheet_type, patterns in SHEET_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, name_lower):
                return sheet_type
    return SheetType.DESCONHECIDO


def extract_text(pdf_path: str) -> str:
    """Extrai texto de um PDF usando pdfplumber."""
    text_parts = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if row:
                            cells = [str(c) for c in row if c]
                            if cells:
                                text_parts.append(" | ".join(cells))
    except Exception as e:
        text_parts.append(f"[Erro ao extrair texto: {e}]")
    return "\n".join(text_parts)


def render_crops(pdf_path: str, sheet_type: SheetType, output_dir: str, dpi: int = 120) -> list[str]:
    """Renderiza um PDF e corta regiões de interesse. Otimizado pra baixo consumo de memória."""
    import gc
    crops_config = CROP_REGIONS.get(sheet_type, {})
    if not crops_config:
        crops_config = {"full": (0.0, 0.0, 1.0, 1.0)}

    crop_paths = []
    try:
        pdf = pdfium.PdfDocument(pdf_path)
        page = pdf[0]
        # DPI 120 = ~3300x2300 px por prancha A1 (~30MB RAM vs 80MB em 200 DPI)
        bitmap = page.render(scale=dpi / 72)
        img = bitmap.to_pil()
        w, h = img.size
        # Liberar bitmap imediatamente
        del bitmap
        gc.collect()

        for name, (x1, y1, x2, y2) in crops_config.items():
            crop = img.crop((int(w * x1), int(h * y1), int(w * x2), int(h * y2)))
            # Max 1000px no lado maior (suficiente pra ler legendas, baixo consumo)
            max_side = max(crop.size)
            if max_side > 1000:
                ratio = 1000 / max_side
                crop = crop.resize((int(crop.width * ratio), int(crop.height * ratio)), Image.LANCZOS)

            crop_path = os.path.join(output_dir, f"{Path(pdf_path).stem}_{name}.jpg")
            crop.save(crop_path, "JPEG", quality=80)
            crop_paths.append(crop_path)
            del crop

        pdf.close()
        del img
        gc.collect()
    except Exception as e:
        print(f"Erro ao renderizar {pdf_path}: {e}")

    return crop_paths


def process_pdfs(pdf_paths: list[str], work_dir: str) -> list[SheetInfo]:
    """Processa todos os PDFs: identifica tipo, extrai texto, renderiza crops."""
    sheets = []
    crops_dir = os.path.join(work_dir, "crops")
    os.makedirs(crops_dir, exist_ok=True)

    for pdf_path in pdf_paths:
        filename = os.path.basename(pdf_path)
        sheet_type = identify_sheet_type(filename)

        # Extrair texto
        text = extract_text(pdf_path)

        # Renderizar crops
        crop_paths = render_crops(pdf_path, sheet_type, crops_dir)

        sheet = SheetInfo(
            filename=filename,
            sheet_type=sheet_type,
            text_content=text[:5000],  # Limitar texto
            crops=crop_paths,
        )
        sheets.append(sheet)

    return sheets
