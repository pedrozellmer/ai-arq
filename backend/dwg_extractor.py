# -*- coding: utf-8 -*-
"""Extrator de dados estruturados de arquivos DWG/DXF para orçamento.

Parte do backend ai.arq.br — gera dados quantitativos a partir de plantas
arquitetônicas em formato DWG/DXF usando a biblioteca ezdxf.

Suporta:
  - Arquivos .dxf diretamente
  - Arquivos .dwg via conversão com ODA File Converter
"""

import ezdxf
import logging
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BlockCount:
    """Contagem de blocos (luminárias, portas, tomadas, etc.)"""
    name: str
    count: int
    layer: str = ""
    positions: list = field(default_factory=list)  # [(x,y)] coordinates


@dataclass
class WallSegment:
    """Segmento de parede/linha com comprimento."""
    layer: str
    length: float  # in meters
    start: tuple = (0, 0)
    end: tuple = (0, 0)


@dataclass
class HatchArea:
    """Área hachurada (pintura, piso, forro)."""
    layer: str
    area: float  # in m²
    pattern: str = ""


@dataclass
class TextAnnotation:
    """Texto/legenda extraído."""
    layer: str
    text: str
    position: tuple = (0, 0)
    height: float = 0


@dataclass
class DXFExtraction:
    """Resultado completo da extração."""
    filename: str
    blocks: list  # list of BlockCount
    walls: list  # list of WallSegment
    hatches: list  # list of HatchArea
    texts: list  # list of TextAnnotation
    layers: list  # list of layer names
    dimensions: list  # list of (label, value) tuples
    metadata: dict = field(default_factory=dict)

    # -- convenience helpers ------------------------------------------------

    def get_block_summary(self) -> dict:
        """Returns {block_name: total_count}."""
        summary: Counter = Counter()
        for b in self.blocks:
            summary[b.name] += b.count
        return dict(summary)

    def get_walls_by_layer(self) -> dict:
        """Returns {layer_name: total_length_meters}."""
        result: dict[str, float] = defaultdict(float)
        for w in self.walls:
            result[w.layer] += w.length
        return dict(result)

    def get_areas_by_layer(self) -> dict:
        """Returns {layer_name: total_area_m2}."""
        result: dict[str, float] = defaultdict(float)
        for h in self.hatches:
            result[h.layer] += h.area
        return dict(result)

    def get_texts_by_layer(self) -> dict:
        """Returns {layer_name: [text1, text2, ...]}."""
        result: dict[str, list] = defaultdict(list)
        for t in self.texts:
            result[t.layer].append(t.text)
        return dict(result)

    # -- prompt generation --------------------------------------------------

    def to_structured_prompt(self) -> str:
        """Converts extraction to a structured text prompt for Claude."""
        lines: list[str] = []
        lines.append(f"=== DADOS EXTRAÍDOS DO DXF: {self.filename} ===\n")

        # Metadata
        if self.metadata:
            lines.append("METADADOS DO ARQUIVO:")
            for k, v in self.metadata.items():
                lines.append(f"  {k}: {v}")
            lines.append("")

        # Layers
        lines.append(f"LAYERS ENCONTRADOS ({len(self.layers)}):")
        for layer in sorted(self.layers):
            lines.append(f"  - {layer}")
        lines.append("")

        # Block counts
        block_summary = self.get_block_summary()
        if block_summary:
            lines.append(f"CONTAGEM DE BLOCOS ({len(block_summary)} tipos):")
            for name, count in sorted(block_summary.items(), key=lambda x: -x[1]):
                lines.append(f"  {name}: {count} un")
            lines.append("")

        # Wall lengths
        walls_by_layer = self.get_walls_by_layer()
        if walls_by_layer:
            lines.append("COMPRIMENTOS POR LAYER:")
            for layer, length in sorted(walls_by_layer.items()):
                lines.append(f"  {layer}: {length:.2f} m")
            lines.append("")

        # Hatch areas
        areas_by_layer = self.get_areas_by_layer()
        if areas_by_layer:
            lines.append("ÁREAS HACHURADAS POR LAYER:")
            for layer, area in sorted(areas_by_layer.items()):
                lines.append(f"  {layer}: {area:.2f} m²")
            lines.append("")

        # Key texts
        texts_by_layer = self.get_texts_by_layer()
        if texts_by_layer:
            lines.append("TEXTOS/LEGENDAS:")
            for layer, texts in sorted(texts_by_layer.items()):
                unique_texts = list(set(t.strip() for t in texts if len(t.strip()) > 2))
                if unique_texts:
                    lines.append(f"  [{layer}]:")
                    for t in sorted(unique_texts)[:50]:
                        lines.append(f"    {t}")
            lines.append("")

        # Dimensions
        if self.dimensions:
            lines.append("COTAS/DIMENSÕES:")
            for label, value in self.dimensions:
                lines.append(f"  {label}: {value}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Unit detection / conversion
# ---------------------------------------------------------------------------

# ezdxf header variable $INSUNITS values
_INSUNITS_TO_METERS: dict[int, float] = {
    0: 1.0,       # Unitless — assume meters
    1: 0.0254,    # Inches
    2: 0.3048,    # Feet
    3: 1609.344,  # Miles
    4: 0.001,     # Millimeters
    5: 0.01,      # Centimeters
    6: 1.0,       # Meters
    7: 1000.0,    # Kilometers
    8: 0.0000254, # Microinches
    9: 0.001,     # Mils (= mm)
    10: 0.9144,   # Yards
    11: 1.0e-10,  # Angstroms
    12: 1.0e-9,   # Nanometers
    13: 1.0e-6,   # Microns
    14: 0.01,     # Decimeters (actually 0.1 m)
}
# Fix decimeters
_INSUNITS_TO_METERS[14] = 0.1


def _detect_unit_factor(doc) -> float:
    """Return the multiplier to convert drawing units to meters.

    Heuristic order:
      1. $INSUNITS header variable (most reliable)
      2. $MEASUREMENT (0 = imperial, 1 = metric)
      3. Fallback: assume millimeters (most common in Brazilian arch. drawings)
    """
    try:
        insunits = doc.header.get("$INSUNITS", 0)
        if insunits in _INSUNITS_TO_METERS and insunits != 0:
            return _INSUNITS_TO_METERS[insunits]
    except Exception:
        pass

    # Fallback: $MEASUREMENT
    try:
        measurement = doc.header.get("$MEASUREMENT", 1)
        if measurement == 0:
            # Imperial — assume feet
            return 0.3048
    except Exception:
        pass

    # Default for Brazilian architecture: millimeters
    return 0.001


# ---------------------------------------------------------------------------
# DWG -> DXF conversion via ODA File Converter
# ---------------------------------------------------------------------------

_ODA_SEARCH_PATHS = [
    # Linux (servidor Render)
    "/usr/bin/ODAFileConverter",
    "/usr/local/bin/ODAFileConverter",
    "/opt/ODAFileConverter/ODAFileConverter",
    # Windows (desenvolvimento local)
    r"C:\Program Files\ODA\ODAFileConverter 27.1.0\ODAFileConverter.exe",
    r"C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe",
    r"C:\Program Files (x86)\ODA\ODAFileConverter\ODAFileConverter.exe",
]


def _find_oda_converter() -> Optional[str]:
    """Locate ODAFileConverter executable on disk."""
    import shutil
    # Primeiro tentar via PATH (funciona em Linux e Windows)
    which = shutil.which("ODAFileConverter")
    if which:
        return which
    # Depois tentar caminhos conhecidos
    for p in _ODA_SEARCH_PATHS:
        path = Path(p)
        if path.is_file():
            return str(path)
        if path.is_dir():
            for name in ["ODAFileConverter", "ODAFileConverter.exe"]:
                exe = path / name
                if exe.is_file():
                    return str(exe)
    return None


def convert_dwg_to_dxf(dwg_path: str) -> Optional[str]:
    """Attempt to convert a DWG file to DXF using ODA File Converter.

    Returns:
        Path to the resulting .dxf file, or None if conversion failed.
    """
    dwg_path = os.path.abspath(dwg_path)
    if not os.path.isfile(dwg_path):
        logger.error("Arquivo DWG não encontrado: %s", dwg_path)
        return None

    oda_exe = _find_oda_converter()
    if oda_exe is None:
        logger.warning(
            "ODA File Converter não encontrado. "
            "Para converter arquivos .dwg, instale o ODA File Converter gratuito em: "
            "https://www.opendesign.com/guestfiles/oda_file_converter  "
            "Instale em C:\\Program Files\\ODA\\ODAFileConverter"
        )
        return None

    input_dir = os.path.dirname(dwg_path)
    output_dir = tempfile.mkdtemp(prefix="arq_dxf_")
    filename = os.path.basename(dwg_path)

    # ODAFileConverter <input_dir> <output_dir> <output_version> <output_type>
    #   <recurse> <audit> [filter]
    # output_type: 0 = DWG, 1 = DXF, 2 = DXB
    # output_version: "ACAD2018" is safe for ezdxf
    cmd = [
        oda_exe,
        input_dir,
        output_dir,
        "ACAD2018",  # output version
        "DXF",       # output file type
        "0",         # no recurse
        "1",         # audit & fix
        filename,    # filter — only this file
    ]

    logger.info("Convertendo DWG -> DXF: %s", " ".join(cmd))
    # ODA precisa de QT_QPA_PLATFORM=offscreen em Linux sem display
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        print(f"[ODA] returncode={result.returncode} stdout={result.stdout[:200]} stderr={result.stderr[:200]}")
        if result.returncode != 0:
            logger.error(
                "ODA File Converter falhou (code %d): %s",
                result.returncode,
                result.stderr or result.stdout,
            )
            return None
    except FileNotFoundError:
        logger.error("Executável ODA não acessível: %s", oda_exe)
        return None
    except subprocess.TimeoutExpired:
        logger.error("Conversão DWG excedeu o tempo limite de 120s.")
        return None

    # Look for the converted file
    stem = Path(filename).stem
    dxf_path = os.path.join(output_dir, stem + ".dxf")
    if os.path.isfile(dxf_path):
        logger.info("DXF gerado em: %s", dxf_path)
        return dxf_path

    # Try case-insensitive search in output dir
    for f in os.listdir(output_dir):
        if f.lower().endswith(".dxf"):
            found = os.path.join(output_dir, f)
            logger.info("DXF gerado em: %s", found)
            return found

    logger.error("Nenhum arquivo .dxf gerado no diretório de saída: %s", output_dir)
    return None


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

def _line_length(start, end) -> float:
    """Euclidean distance between two 2D/3D points."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    dz = (end[2] - start[2]) if len(start) > 2 and len(end) > 2 else 0
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _lwpolyline_length(entity) -> float:
    """Total length of an LWPOLYLINE (sum of segment lengths)."""
    try:
        points = list(entity.get_points(format="xy"))
    except Exception:
        return 0.0
    if len(points) < 2:
        return 0.0
    total = 0.0
    for i in range(len(points) - 1):
        total += _line_length(points[i], points[i + 1])
    if entity.closed and len(points) >= 3:
        total += _line_length(points[-1], points[0])
    return total


def _polyline_length(entity) -> float:
    """Total length of a 2D/3D POLYLINE."""
    try:
        points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
    except Exception:
        return 0.0
    if len(points) < 2:
        return 0.0
    total = 0.0
    for i in range(len(points) - 1):
        total += _line_length(points[i], points[i + 1])
    if entity.is_closed and len(points) >= 3:
        total += _line_length(points[-1], points[0])
    return total


def _hatch_area(entity) -> float:
    """Calculate area of a HATCH entity.

    Tries ezdxf built-in methods first, falls back to Shoelace formula on
    the boundary path vertices.
    """
    # ezdxf >= 0.18 exposes paths that can be converted to areas
    try:
        from ezdxf import path as ezdxf_path
        paths = ezdxf_path.make_path(entity)
        if paths:
            # Use the ezdxf built-in area from the control vertices
            from ezdxf.math import area as math_area
            bbox_paths = ezdxf_path.to_polylines2d(
                [paths] if not isinstance(paths, list) else paths
            )
            total = 0.0
            for poly_pts in bbox_paths:
                pts = [(p.x, p.y) for p in poly_pts]
                if len(pts) >= 3:
                    total += abs(_shoelace_area(pts))
            if total > 0:
                return total
    except Exception:
        pass

    # Fallback: iterate boundary paths manually
    total_area = 0.0
    try:
        for bpath in entity.paths:
            if hasattr(bpath, "vertices") and bpath.vertices:
                pts = [(v[0], v[1]) for v in bpath.vertices]
                if len(pts) >= 3:
                    total_area += abs(_shoelace_area(pts))
            elif hasattr(bpath, "edges"):
                # Edge-type boundary — collect endpoints
                pts = []
                for edge in bpath.edges:
                    if hasattr(edge, "start"):
                        pts.append((edge.start[0], edge.start[1]))
                if len(pts) >= 3:
                    total_area += abs(_shoelace_area(pts))
    except Exception:
        pass

    return total_area


def _shoelace_area(points: list) -> float:
    """Shoelace formula for polygon area from a list of (x, y) tuples."""
    n = len(points)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1]
        area -= points[j][0] * points[i][1]
    return area / 2.0


def extract_dxf(filepath: str) -> DXFExtraction:
    """Main extraction function — reads a .dxf file and returns structured data.

    Args:
        filepath: Path to a .dxf file.

    Returns:
        DXFExtraction with all extracted elements.

    Raises:
        FileNotFoundError: if the file does not exist.
        ezdxf.DXFError: if the file is not a valid DXF.
    """
    filepath = os.path.abspath(filepath)
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"Arquivo não encontrado: {filepath}")

    # Try UTF-8 first, then latin-1 (common in Brazilian CAD files)
    doc = None
    for encoding in ("utf-8", "latin-1", None):
        try:
            kwargs = {}
            if encoding is not None:
                kwargs["encoding"] = encoding
            doc = ezdxf.readfile(filepath, **kwargs)
            break
        except UnicodeDecodeError:
            continue
        except Exception as exc:
            # For non-encoding errors, re-raise immediately
            if encoding is None:
                raise
            # On last attempt (None), let ezdxf pick encoding
            if encoding == "latin-1":
                try:
                    doc = ezdxf.readfile(filepath)
                    break
                except Exception:
                    raise exc
            continue

    if doc is None:
        raise RuntimeError(f"Não foi possível abrir o DXF com nenhum encoding: {filepath}")

    msp = doc.modelspace()
    unit_factor = _detect_unit_factor(doc)
    area_factor = unit_factor * unit_factor  # for m² conversion

    # ---- Metadata ---------------------------------------------------------
    metadata: dict = {}
    try:
        metadata["versão_dxf"] = doc.dxfversion
    except Exception:
        pass
    try:
        acad_ver = doc.header.get("$ACADVER", "")
        if acad_ver:
            metadata["versão_autocad"] = acad_ver
    except Exception:
        pass
    try:
        insunits = doc.header.get("$INSUNITS", 0)
        unit_names = {
            0: "Sem unidade", 1: "Polegadas", 2: "Pés", 4: "Milímetros",
            5: "Centímetros", 6: "Metros", 7: "Quilômetros",
        }
        metadata["unidade_desenho"] = unit_names.get(insunits, f"Código {insunits}")
        metadata["fator_para_metros"] = f"{unit_factor}"
    except Exception:
        pass

    # ---- Layers -----------------------------------------------------------
    layer_names = [layer.dxf.name for layer in doc.layers]

    # ---- Blocks (INSERT entities) -----------------------------------------
    block_counter: dict[str, dict] = {}  # {name: {"count": n, "layer": l, "positions": [...]}}
    for insert in msp.query("INSERT"):
        try:
            bname = insert.dxf.name
            layer = insert.dxf.layer
            x = insert.dxf.insert.x
            y = insert.dxf.insert.y
        except Exception:
            continue

        # Skip anonymous / internal blocks (names starting with *)
        if bname.startswith("*"):
            continue

        if bname not in block_counter:
            block_counter[bname] = {"count": 0, "layer": layer, "positions": []}
        block_counter[bname]["count"] += 1
        block_counter[bname]["positions"].append((round(x, 2), round(y, 2)))

    blocks = [
        BlockCount(
            name=name,
            count=info["count"],
            layer=info["layer"],
            positions=info["positions"],
        )
        for name, info in block_counter.items()
    ]

    if not blocks:
        logger.warning("Nenhum bloco (INSERT) encontrado no DXF: %s", filepath)

    # ---- Lines / polylines (wall segments) --------------------------------
    walls: list[WallSegment] = []

    for line in msp.query("LINE"):
        try:
            start = (line.dxf.start.x, line.dxf.start.y)
            end = (line.dxf.end.x, line.dxf.end.y)
            length = _line_length(start, end) * unit_factor
            if length > 0:
                walls.append(WallSegment(
                    layer=line.dxf.layer,
                    length=length,
                    start=start,
                    end=end,
                ))
        except Exception:
            continue

    for lwpoly in msp.query("LWPOLYLINE"):
        try:
            length = _lwpolyline_length(lwpoly) * unit_factor
            if length > 0:
                pts = list(lwpoly.get_points(format="xy"))
                start = pts[0] if pts else (0, 0)
                end = pts[-1] if pts else (0, 0)
                walls.append(WallSegment(
                    layer=lwpoly.dxf.layer,
                    length=length,
                    start=start,
                    end=end,
                ))
        except Exception:
            continue

    for poly in msp.query("POLYLINE"):
        try:
            length = _polyline_length(poly) * unit_factor
            if length > 0:
                verts = [(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                start = verts[0] if verts else (0, 0)
                end = verts[-1] if verts else (0, 0)
                walls.append(WallSegment(
                    layer=poly.dxf.layer,
                    length=length,
                    start=start,
                    end=end,
                ))
        except Exception:
            continue

    # ---- Hatches ----------------------------------------------------------
    hatches: list[HatchArea] = []

    for hatch in msp.query("HATCH"):
        try:
            area = _hatch_area(hatch) * area_factor
            pattern = ""
            try:
                pattern = hatch.dxf.pattern_name
            except Exception:
                pass
            if area > 0:
                hatches.append(HatchArea(
                    layer=hatch.dxf.layer,
                    area=area,
                    pattern=pattern,
                ))
        except Exception:
            continue

    # ---- Texts ------------------------------------------------------------
    texts: list[TextAnnotation] = []

    for text in msp.query("TEXT"):
        try:
            content = text.dxf.text.strip()
            if content:
                pos = (text.dxf.insert.x, text.dxf.insert.y)
                height = text.dxf.height if hasattr(text.dxf, "height") else 0
                texts.append(TextAnnotation(
                    layer=text.dxf.layer,
                    text=content,
                    position=pos,
                    height=height,
                ))
        except Exception:
            continue

    for mtext in msp.query("MTEXT"):
        try:
            content = mtext.text.strip()
            # Strip MTEXT formatting codes  {\fArial|...; }  etc.
            if content:
                pos = (mtext.dxf.insert.x, mtext.dxf.insert.y)
                height = mtext.dxf.char_height if hasattr(mtext.dxf, "char_height") else 0
                texts.append(TextAnnotation(
                    layer=mtext.dxf.layer,
                    text=content,
                    position=pos,
                    height=height,
                ))
        except Exception:
            continue

    # ---- Dimensions -------------------------------------------------------
    dims: list[tuple] = []

    for dim in msp.query("DIMENSION"):
        try:
            measurement = None
            label = ""
            # Try to get the actual measurement value
            try:
                measurement = dim.dxf.actual_measurement
            except Exception:
                pass
            # Try to get overridden text
            try:
                label = dim.dxf.text.strip()
            except Exception:
                pass
            if measurement is not None:
                value_m = measurement * unit_factor
                display_label = label if label else "cota"
                dims.append((display_label, f"{value_m:.3f} m"))
            elif label:
                dims.append((label, label))
        except Exception:
            continue

    return DXFExtraction(
        filename=os.path.basename(filepath),
        blocks=blocks,
        walls=walls,
        hatches=hatches,
        texts=texts,
        layers=layer_names,
        dimensions=dims,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Architectural element identification via layer naming conventions
# ---------------------------------------------------------------------------

# (keyword_fragments, category_name)
_LAYER_PATTERNS: list[tuple[list[str], str]] = [
    (["LUM", "LIGHT", "ILUM"],          "luminarias"),
    (["PAREDE", "WALL", "DRY"],         "paredes"),
    (["FORRO", "CEIL"],                  "forro"),
    (["PISO", "FLOOR"],                  "piso"),
    (["PORTA", "DOOR"],                  "portas"),
    (["SPK", "SPRINK", "INCEND"],        "incendio"),
    (["ELET", "ELEC", "TOMADA"],         "eletrica"),
    (["DEMOL"],                          "demolicao"),
    (["PINT", "PAINT"],                  "pintura"),
]


def identify_architectural_elements(extraction: DXFExtraction) -> dict:
    """Map extraction data to architectural categories based on layer names.

    Returns:
        dict mapping category name to a dict with keys:
            - "layers": list of matching layer names
            - "blocks": list of BlockCount on matching layers
            - "walls": list of WallSegment on matching layers
            - "hatches": list of HatchArea on matching layers
            - "texts": list of TextAnnotation on matching layers
    """
    result: dict = {}

    for keywords, category in _LAYER_PATTERNS:
        matching_layers = [
            lyr for lyr in extraction.layers
            if any(kw in lyr.upper() for kw in keywords)
        ]
        if not matching_layers:
            continue

        layer_set = set(matching_layers)

        result[category] = {
            "layers": matching_layers,
            "blocks": [b for b in extraction.blocks if b.layer in layer_set],
            "walls": [w for w in extraction.walls if w.layer in layer_set],
            "hatches": [h for h in extraction.hatches if h.layer in layer_set],
            "texts": [t for t in extraction.texts if t.layer in layer_set],
        }

    return result


# ---------------------------------------------------------------------------
# Entry point — handles both .dxf and .dwg
# ---------------------------------------------------------------------------

def extract_from_file(filepath: str) -> DXFExtraction:
    """High-level entry point: extract structured data from a DWG or DXF file.

    Args:
        filepath: Path to .dwg or .dxf file.

    Returns:
        DXFExtraction with all extracted elements.

    Raises:
        ValueError: If the file extension is not .dwg or .dxf.
        FileNotFoundError: If the file does not exist.
        RuntimeError: If DWG conversion fails and no DXF is available.
    """
    filepath = os.path.abspath(filepath)
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"Arquivo não encontrado: {filepath}")

    ext = Path(filepath).suffix.lower()

    if ext == ".dxf":
        return extract_dxf(filepath)

    if ext == ".dwg":
        dxf_path = convert_dwg_to_dxf(filepath)
        if dxf_path is None:
            raise RuntimeError(
                f"Não foi possível converter o arquivo DWG: {filepath}. "
                "Instale o ODA File Converter (gratuito) para converter arquivos .dwg, "
                "ou exporte o arquivo como .dxf no AutoCAD/BricsCAD."
            )
        try:
            return extract_dxf(dxf_path)
        finally:
            # Clean up the temporary DXF
            try:
                os.unlink(dxf_path)
            except OSError:
                pass

    raise ValueError(
        f"Formato de arquivo não suportado: '{ext}'. "
        "Use arquivos .dxf ou .dwg."
    )


# ---------------------------------------------------------------------------
# Budget data generation
# ---------------------------------------------------------------------------

# Map architectural category -> discipline name (matching models.py)
_CATEGORY_TO_DISCIPLINE: dict[str, str] = {
    "luminarias": "Iluminação",
    "paredes":    "Fechamentos Verticais",
    "forro":      "Forros",
    "piso":       "Pisos e Rodapés",
    "portas":     "Portas e Ferragens",
    "incendio":   "Prevenção e Combate a Incêndio",
    "eletrica":   "Instalações Elétricas",
    "demolicao":  "Demolição e Remoção",
    "pintura":    "Revestimentos",
}


def generate_budget_data(extraction: DXFExtraction) -> dict:
    """Convert extracted DXF data into a budget-ready dict of items.

    The output format is compatible with the BudgetItem model defined in
    models.py (fields: description, unit, quantity, discipline, confidence).

    Returns:
        dict with key "items" containing a list of budget item dicts.
    """
    items: list[dict] = []
    elements = identify_architectural_elements(extraction)

    # --- Blocks: count by category -----------------------------------------
    for category, data in elements.items():
        discipline = _CATEGORY_TO_DISCIPLINE.get(category, category.title())
        for block in data["blocks"]:
            items.append({
                "description": f"{block.name}",
                "unit": "un",
                "quantity": block.count,
                "discipline": discipline,
                "confidence": "confirmado",
                "source": "DXF block count",
            })

    # --- Walls: sum lengths by category ------------------------------------
    for category, data in elements.items():
        discipline = _CATEGORY_TO_DISCIPLINE.get(category, category.title())
        total_length = sum(w.length for w in data["walls"])
        if total_length > 0:
            desc_map = {
                "paredes": "Parede drywall nova",
                "demolicao": "Demolição de parede existente",
            }
            description = desc_map.get(category, f"Comprimento linear — {category}")
            items.append({
                "description": description,
                "unit": "m",
                "quantity": round(total_length, 2),
                "discipline": discipline,
                "confidence": "confirmado",
                "source": "DXF line measurement",
            })

    # --- Hatches: sum areas by category ------------------------------------
    for category, data in elements.items():
        discipline = _CATEGORY_TO_DISCIPLINE.get(category, category.title())
        total_area = sum(h.area for h in data["hatches"])
        if total_area > 0:
            desc_map = {
                "pintura": "Pintura (área hachurada)",
                "piso": "Piso (área hachurada)",
                "forro": "Forro (área hachurada)",
            }
            description = desc_map.get(category, f"Área — {category}")
            items.append({
                "description": description,
                "unit": "m²",
                "quantity": round(total_area, 2),
                "discipline": discipline,
                "confidence": "confirmado",
                "source": "DXF hatch area",
            })

    # --- Uncategorized blocks (not on recognized layers) -------------------
    categorized_block_names = set()
    for data in elements.values():
        for b in data["blocks"]:
            categorized_block_names.add(b.name)

    for block in extraction.blocks:
        if block.name not in categorized_block_names:
            items.append({
                "description": f"{block.name}",
                "unit": "un",
                "quantity": block.count,
                "discipline": "",
                "confidence": "verificar",
                "source": "DXF block count (sem categoria identificada)",
            })

    # --- Dimension texts: look for room area annotations -------------------
    for label, value in extraction.dimensions:
        items.append({
            "description": f"Cota: {label}",
            "unit": "m",
            "quantity": 0,
            "discipline": "",
            "confidence": "verificar",
            "source": f"DXF dimension: {value}",
        })

    return {"items": items}


# ---------------------------------------------------------------------------
# CLI testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) > 1:
        target = sys.argv[1]
        result = extract_from_file(target)
        print(result.to_structured_prompt())
        print(f"\n=== RESUMO ===")
        print(f"Blocos: {len(result.blocks)} tipos")
        print(f"Paredes: {len(result.walls)} segmentos")
        print(f"Áreas: {len(result.hatches)} hachuras")
        print(f"Textos: {len(result.texts)} anotações")

        budget = generate_budget_data(result)
        if budget["items"]:
            print(f"\n=== ITENS DE ORÇAMENTO ({len(budget['items'])}) ===")
            for item in budget["items"]:
                print(f"  [{item['discipline'] or '?'}] {item['description']}: "
                      f"{item['quantity']} {item['unit']} "
                      f"({item['confidence']})")
    else:
        print("Uso: python dwg_extractor.py <arquivo.dxf|dwg>")
