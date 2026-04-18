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
import re
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
    # Dimensão aproximada em metros (bbox da definição × escala do INSERT médio).
    # Populado só pra blocos de esquadria (portas/janelas) — permite aplicar
    # regra TCPO de vãos (≤2m² não descontam da pintura).
    width_m: float = 0.0
    height_m: float = 0.0


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

        # Layers — com xref prefix removido e deduplicado pra não poluir o prompt
        clean_layers = set()
        for layer in self.layers:
            # Layers de xref tem formato "xrefname|actual_layer" — usamos só a 2ª parte
            clean_name = layer.split("|", 1)[-1].strip()
            if clean_name:
                clean_layers.add(clean_name)
        lines.append(f"LAYERS ENCONTRADOS ({len(clean_layers)} únicos / {len(self.layers)} com xrefs):")
        for layer in sorted(clean_layers):
            lines.append(f"  - {layer}")
        lines.append("")

        # Block counts — separando esquadrias (com dimensão) dos demais
        block_summary = self.get_block_summary()
        if block_summary:
            # Blocos com dimensão extraída (esquadrias)
            esquadria_blocks = [b for b in self.blocks if b.width_m > 0 and b.height_m > 0]
            if esquadria_blocks:
                lines.append("ESQUADRIAS (dimensões aproximadas do bbox × escala do INSERT):")
                # deduplica por nome
                seen = set()
                for b in sorted(esquadria_blocks, key=lambda x: -x.count):
                    if b.name in seen:
                        continue
                    seen.add(b.name)
                    area = b.width_m * b.height_m
                    lines.append(
                        f"  {b.name}: {b.count} un  |  ~{b.width_m:.2f}m × {b.height_m:.2f}m = {area:.2f} m²"
                    )
                lines.append("  Regra TCPO: vãos com área ≤ 2 m² NÃO se desconta da pintura; > 2 m² desconta o excedente.")
                lines.append("")

            # Demais blocos (contagem simples)
            other = {name: count for name, count in block_summary.items()
                     if not any(b.name == name and b.width_m > 0 for b in self.blocks)}
            if other:
                lines.append(f"CONTAGEM DE BLOCOS ({len(other)} tipos):")
                for name, count in sorted(other.items(), key=lambda x: -x[1]):
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


# Padrões que indicam bloco de esquadria (porta ou janela).
# Matching case-insensitive via startswith OU contains.
_ESQUADRIA_PATTERNS = (
    "PORT", "PRT", "DOOR",
    "JANE", "JN", "JAN",
    "ESQU", "ESQ-",
    "VIDRO", "GLASS", "WIN",
    # Códigos típicos de projeto (P1, P2, PM3, PJ4 etc.)
)
_ESQUADRIA_CODE_RE = re.compile(r"^(PM|PJ|PD|JN|JL|J[0-9]|P[0-9])", re.IGNORECASE)


def _is_esquadria_block(name: str) -> bool:
    if not name:
        return False
    up = name.upper()
    if any(p in up for p in _ESQUADRIA_PATTERNS):
        return True
    if _ESQUADRIA_CODE_RE.match(name):
        return True
    return False


def _compute_block_bbox(block_layout) -> Optional[tuple[float, float]]:
    """Calcula bounding box (width, height) das entidades dentro de uma definição
    de bloco, em unidades de desenho. Retorna None se não conseguir computar."""
    try:
        xs, ys = [], []
        for ent in block_layout:
            dxftype = ent.dxftype()
            try:
                if dxftype == "LINE":
                    xs.extend([ent.dxf.start.x, ent.dxf.end.x])
                    ys.extend([ent.dxf.start.y, ent.dxf.end.y])
                elif dxftype == "LWPOLYLINE":
                    for p in ent.get_points(format="xy"):
                        xs.append(p[0]); ys.append(p[1])
                elif dxftype == "POLYLINE":
                    for v in ent.vertices:
                        xs.append(v.dxf.location.x); ys.append(v.dxf.location.y)
                elif dxftype == "CIRCLE":
                    c = ent.dxf.center
                    r = ent.dxf.radius
                    xs.extend([c.x - r, c.x + r])
                    ys.extend([c.y - r, c.y + r])
                elif dxftype == "ARC":
                    c = ent.dxf.center
                    r = ent.dxf.radius
                    xs.extend([c.x - r, c.x + r])
                    ys.extend([c.y - r, c.y + r])
            except Exception:
                continue
        if not xs or not ys:
            return None
        return (max(xs) - min(xs), max(ys) - min(ys))
    except Exception:
        return None


def _validate_unit_factor(doc, unit_factor: float) -> tuple[float, list[str]]:
    """Sanity-check the detected unit factor against modelspace extent.

    In practice: if the factor is off by 1000× (common when $INSUNITS=0 forces mm
    but the drawing is actually in meters), walls come out as 5000m or 0.003m.
    This function runs a quick pass over LINE entities and flags absurd lengths,
    returning the (possibly adjusted) factor and a list of warning strings.
    """
    warnings: list[str] = []
    try:
        msp = doc.modelspace()
        max_len = 0.0
        for ent in msp.query("LINE")[:200]:  # sample, not full scan
            try:
                dx = ent.dxf.end.x - ent.dxf.start.x
                dy = ent.dxf.end.y - ent.dxf.start.y
                raw_len = (dx * dx + dy * dy) ** 0.5
                converted = raw_len * unit_factor
                if converted > max_len:
                    max_len = converted
            except Exception:
                continue

        # A single architectural drawing rarely has a line > 500m or < 0.01m as *largest*.
        # Flag but don't auto-fix — we want the caller to know.
        if max_len > 500:
            warnings.append(
                f"Unidade suspeita: maior linha mede {max_len:.1f}m "
                f"(>500m), fator {unit_factor} pode estar grande demais."
            )
        elif max_len < 0.05 and max_len > 0:
            warnings.append(
                f"Unidade suspeita: maior linha mede {max_len*1000:.1f}mm "
                f"(<5cm), fator {unit_factor} pode estar pequeno demais."
            )
    except Exception:
        pass
    return unit_factor, warnings


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
    # ODA usa Qt/xcb que precisa de display X11. Usar xvfb-run pra simular.
    env = os.environ.copy()
    # Remover offscreen se estiver setado — queremos xcb com xvfb
    env.pop("QT_QPA_PLATFORM", None)

    # Tentar com xvfb-run (simula display X11)
    import shutil
    if shutil.which("xvfb-run"):
        cmd = ["xvfb-run", "--auto-servernum", "--server-args=-screen 0 1024x768x24"] + cmd

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        # Salvar log do ODA num arquivo pra poder ler via API
        oda_log = f"rc={result.returncode}\nstdout={result.stdout[:500]}\nstderr={result.stderr[:500]}\ncmd={' '.join(cmd)}\noutput_dir={output_dir}\nfiles_in_output={os.listdir(output_dir) if os.path.isdir(output_dir) else 'DIR NOT FOUND'}"
        log_path = os.path.join(os.path.dirname(dwg_path), "_oda_log.txt")
        with open(log_path, 'w') as lf:
            lf.write(oda_log)
        print(f"[ODA] {oda_log}")
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

_MTEXT_FORMAT_CODES_RE = re.compile(
    r"""
    \\[fF][^;]*;       # \fArial|b0|i0|c0|p34;
    | \\[cC][0-9]+;    # \C256; (color)
    | \\[LlOoKk]        # \L \l \O \o \K \k (underline/strike toggles)
    | \\[Pp]            # \P (newline)
    | \\[SsQqHhWwTt][^;]*;   # \S2/3; \H1.5x; \Q15; etc (superscript, height, etc.)
    | \\~               # non-breaking space
    | [{}]              # grupos MTEXT
    """,
    re.VERBOSE,
)


def _strip_mtext_codes(raw: str) -> str:
    """Remove códigos de formatação de MTEXT deixando só o texto legível.
    Fallback pra quando mtext.plain_text() não está disponível."""
    if not raw:
        return ""
    cleaned = _MTEXT_FORMAT_CODES_RE.sub(" ", raw)
    # Converter \P (que pode ter sobrado) em newline
    cleaned = cleaned.replace("\\P", "\n").replace("\\p", "\n")
    # Compactar espaços múltiplos
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()


def _line_length(start, end) -> float:
    """Euclidean distance between two 2D/3D points."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    dz = (end[2] - start[2]) if len(start) > 2 and len(end) > 2 else 0
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _arc_length_from_bulge(p1, p2, bulge: float) -> float:
    """Comprimento real do arco entre dois pontos, dado o parâmetro bulge do DXF.
    bulge = tan(ângulo_de_abertura / 4). bulge=0 → reta."""
    if abs(bulge) < 1e-9:
        return _line_length(p1, p2)
    chord = _line_length(p1, p2)
    if chord < 1e-9:
        return 0.0
    # ângulo de abertura total do arco (em radianos)
    theta = 4.0 * math.atan(abs(bulge))
    # raio via relação chord = 2·r·sin(θ/2)
    try:
        r = chord / (2.0 * math.sin(theta / 2.0))
    except Exception:
        return chord
    return abs(r * theta)


def _lwpolyline_length(entity) -> float:
    """Total length of an LWPOLYLINE incluindo interpolação de bulges (arcos)."""
    try:
        pts = list(entity.get_points(format="xyb"))  # (x, y, bulge)
    except Exception:
        try:
            pts_xy = list(entity.get_points(format="xy"))
            pts = [(p[0], p[1], 0.0) for p in pts_xy]
        except Exception:
            return 0.0
    if len(pts) < 2:
        return 0.0
    total = 0.0
    for i in range(len(pts) - 1):
        p1 = (pts[i][0], pts[i][1])
        p2 = (pts[i + 1][0], pts[i + 1][1])
        bulge = pts[i][2] if len(pts[i]) > 2 else 0.0
        total += _arc_length_from_bulge(p1, p2, bulge)
    if entity.closed and len(pts) >= 3:
        p1 = (pts[-1][0], pts[-1][1])
        p2 = (pts[0][0], pts[0][1])
        bulge = pts[-1][2] if len(pts[-1]) > 2 else 0.0
        total += _arc_length_from_bulge(p1, p2, bulge)
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

    Tries ezdxf built-in path API first (lida bem com arcos/splines),
    faz fallback pra shoelace sobre os vértices das boundary paths
    com aproximação de arcos por amostragem de pontos intermediários.
    """
    # Primeira tentativa: usar ezdxf.path que faz flattening automático de arcos
    try:
        from ezdxf import path as ezdxf_path
        from ezdxf.math import Vec2
        path_result = ezdxf_path.make_path(entity)
        if path_result:
            paths_list = path_result if isinstance(path_result, list) else [path_result]
            total = 0.0
            for p in paths_list:
                try:
                    # flattening com distância de 0.5 unidades (equilibra precisão/custo)
                    vertices = list(p.flattening(0.5))
                    pts = [(v.x, v.y) for v in vertices]
                    if len(pts) >= 3:
                        total += abs(_shoelace_area(pts))
                except Exception:
                    continue
            if total > 0:
                return total
    except Exception:
        pass

    # Fallback: iterar boundary paths manualmente com aproximação de arcos
    total_area = 0.0
    try:
        for bpath in entity.paths:
            pts: list[tuple[float, float]] = []
            if hasattr(bpath, "vertices") and bpath.vertices:
                # PolylinePath: vertices podem ter bulge (arco entre pontos)
                raw = [(v[0], v[1], v[2] if len(v) > 2 else 0.0) for v in bpath.vertices]
                for i in range(len(raw)):
                    p1 = (raw[i][0], raw[i][1])
                    pts.append(p1)
                    # Interpolar arco se bulge != 0
                    bulge = raw[i][2]
                    if abs(bulge) > 1e-9 and i + 1 < len(raw):
                        p2 = (raw[i + 1][0], raw[i + 1][1])
                        # Amostra pontos intermediários do arco (~8 pontos)
                        pts.extend(_sample_arc_from_bulge(p1, p2, bulge, segments=8))
            elif hasattr(bpath, "edges"):
                # EdgePath: mix de Line/Arc/Ellipse/Spline edges
                for edge in bpath.edges:
                    etype = type(edge).__name__.lower()
                    try:
                        if "line" in etype:
                            pts.append((edge.start[0], edge.start[1]))
                        elif "arc" in etype:
                            center = (edge.center[0], edge.center[1])
                            radius = edge.radius
                            start_angle = math.radians(edge.start_angle)
                            end_angle = math.radians(edge.end_angle)
                            if end_angle < start_angle:
                                end_angle += 2 * math.pi
                            # Amostrar pontos no arco
                            segments = 12
                            for k in range(segments + 1):
                                t = k / segments
                                ang = start_angle + (end_angle - start_angle) * t
                                pts.append((
                                    center[0] + radius * math.cos(ang),
                                    center[1] + radius * math.sin(ang),
                                ))
                        elif "ellipse" in etype or "spline" in etype:
                            # Tentar extrair start
                            if hasattr(edge, "start"):
                                pts.append((edge.start[0], edge.start[1]))
                    except Exception:
                        continue
            if len(pts) >= 3:
                total_area += abs(_shoelace_area(pts))
    except Exception:
        pass

    return total_area


def _sample_arc_from_bulge(p1, p2, bulge: float, segments: int = 8) -> list:
    """Retorna pontos intermediários de um arco definido por dois endpoints + bulge.
    Usado na aproximação de área em hatch boundaries com polyline."""
    if abs(bulge) < 1e-9:
        return []
    chord = _line_length(p1, p2)
    if chord < 1e-9:
        return []
    theta = 4.0 * math.atan(abs(bulge))
    try:
        r = chord / (2.0 * math.sin(theta / 2.0))
    except Exception:
        return []
    # ponto médio do chord
    mx = (p1[0] + p2[0]) / 2.0
    my = (p1[1] + p2[1]) / 2.0
    # vetor perpendicular ao chord (direção do centro do arco)
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-9:
        return []
    nx = -dy / length
    ny = dx / length
    # distância do ponto médio até o centro
    h = r * math.cos(theta / 2.0)
    if bulge < 0:
        h = -h
    cx = mx + nx * h
    cy = my + ny * h
    # ângulos dos endpoints relativos ao centro
    a1 = math.atan2(p1[1] - cy, p1[0] - cx)
    a2 = math.atan2(p2[1] - cy, p2[0] - cx)
    # sentido do arco baseado no sinal de bulge
    if bulge > 0:
        if a2 < a1:
            a2 += 2 * math.pi
    else:
        if a2 > a1:
            a2 -= 2 * math.pi
    # amostra pontos (exclui endpoints, esses já foram adicionados pelo chamador)
    result = []
    for k in range(1, segments):
        t = k / segments
        ang = a1 + (a2 - a1) * t
        result.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return result


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
    unit_factor, unit_warnings = _validate_unit_factor(doc, unit_factor)
    for w in unit_warnings:
        logger.warning("[unit-sanity] %s", w)
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
        if unit_warnings:
            metadata["alerta_unidade"] = " | ".join(unit_warnings)
    except Exception:
        pass

    # ---- Layers -----------------------------------------------------------
    layer_names = [layer.dxf.name for layer in doc.layers]

    # ---- Blocks (INSERT entities) -----------------------------------------
    # Nota sobre blocos aninhados: msp.query("INSERT") é NÃO-recursivo — retorna só
    # INSERTs do modelspace. INSERTs dentro de outros blocos (BLOCK_RECORD) ficam
    # na definição daquele bloco, não aqui, então não há dupla contagem.
    # Layers utilitárias do AutoCAD (DEFPOINTS, viewports, etc.) são filtradas
    # pois contêm blocos auxiliares de cotação que não são itens do projeto.
    _UTILITY_LAYERS_UPPER = {
        "DEFPOINTS", "0-DEFPOINTS", "DEFPOINTS_NO_PLOT",
        "VIEWPORTS", "VIEWPORT", "VP",
        "_GRADE", "GRADE", "GRID",
    }
    # Regex pra identificar blocos de ANOTAÇÃO/CALLOUT — não são itens orçáveis.
    # Casa nomes tipo "ANNO_Section_A2", "leg mb", "TAG-porta", "AREA3", etc.
    # Tolera separador _/- ou espaço entre o token e o resto do nome.
    _ANNOTATION_NAME_RE = re.compile(
        r"^(ANNO|ANNOTATION|NOTE|NOTES|"
        r"LEG|LEGEND|LEGENDA|"
        r"TAG|"
        r"SECTION|ELEVATION|DETAIL|DET|"
        r"ARROW|CALLOUT|"
        r"NORTH|NORTE|ROSA_DOS_VENTOS|"
        r"TITLE|TITLEBLOCK|CARIMBO|"
        r"REVISION|REVISAO|"
        r"ADCADD|"
        r"FORMA|FORM|"  # "forma 12", "form-01" — marcadores de formato em plantas
        r"NIVEL|NIV|LEVEL|"  # marcadores de nivel/cota
        r"CHNIVP|CHNIV|CHNIVEL|"  # cota de nível de piso (padrão BR: marcação com triângulo)
        r"AREA[0-9])(?:[\s_\-]|$)",
        re.IGNORECASE
    )
    # Nomes curtos de símbolos de cota/nível que não têm separador no final
    _ANNOTATION_EXACT_NAMES = {
        "CHNIVP", "CHNIV", "CHNIVEL",
        "INDNORTE", "INDNIVEL", "INDCORTE", "INDETALHE",
    }
    # Nomes que são claramente xrefs/referências externas (arquivo com extensão ou GUID no nome)
    _XREF_NAME_RE = re.compile(r"\.(dwg|dxf)$|\.xref|^xref", re.IGNORECASE)

    def _is_annotation_block(name: str) -> bool:
        if not name:
            return False
        if _ANNOTATION_NAME_RE.match(name):
            return True
        if _XREF_NAME_RE.search(name):
            return True
        if name.upper() in _ANNOTATION_EXACT_NAMES:
            return True
        return False

    block_counter: dict[str, dict] = {}  # {name: {"count": n, "layer": l, "positions": [...], "widths": [], "heights": []}}
    # Cache de bbox por nome de bloco (definição) para não recalcular
    _block_def_bbox_cache: dict[str, Optional[tuple[float, float]]] = {}

    def _bbox_for_block_def(bname: str) -> Optional[tuple[float, float]]:
        if bname in _block_def_bbox_cache:
            return _block_def_bbox_cache[bname]
        try:
            block = doc.blocks.get(bname)
            bbox = _compute_block_bbox(block) if block is not None else None
        except Exception:
            bbox = None
        _block_def_bbox_cache[bname] = bbox
        return bbox

    for insert in msp.query("INSERT"):
        try:
            bname = insert.dxf.name
            layer = insert.dxf.layer
            x = insert.dxf.insert.x
            y = insert.dxf.insert.y
        except Exception:
            continue

        # Skip anonymous / internal blocks (names starting with * or contendo $)
        # Blocos dinâmicos do AutoCAD têm sufixos tipo "A$C6BFD6B53" — filtrar.
        if bname.startswith("*") or "$" in bname:
            continue
        # Skip utility / system layers that don't represent real items
        if layer and layer.upper() in _UTILITY_LAYERS_UPPER:
            continue
        # Skip annotation / callout blocks (legendas, TAGs, cortes, elevações)
        if _is_annotation_block(bname):
            continue

        if bname not in block_counter:
            block_counter[bname] = {
                "count": 0, "layer": layer, "positions": [],
                "widths": [], "heights": [],
            }
        block_counter[bname]["count"] += 1
        block_counter[bname]["positions"].append((round(x, 2), round(y, 2)))

        # Se parece ser esquadria (porta/janela), armazena dimensão em metros
        if _is_esquadria_block(bname):
            bbox = _bbox_for_block_def(bname)
            if bbox is not None:
                try:
                    xscale = getattr(insert.dxf, "xscale", 1.0) or 1.0
                    yscale = getattr(insert.dxf, "yscale", 1.0) or 1.0
                    w_m = abs(bbox[0] * xscale * unit_factor)
                    h_m = abs(bbox[1] * yscale * unit_factor)
                    # Sanity: rejeitar bbox absurdos (0 ou >10m) que indicam problema
                    if 0.1 < w_m < 10 and 0.1 < h_m < 10:
                        block_counter[bname]["widths"].append(w_m)
                        block_counter[bname]["heights"].append(h_m)
                except Exception:
                    pass

    def _median(xs: list) -> float:
        if not xs:
            return 0.0
        s = sorted(xs)
        n = len(s)
        return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0

    blocks = [
        BlockCount(
            name=name,
            count=info["count"],
            layer=info["layer"],
            positions=info["positions"],
            width_m=round(_median(info.get("widths", [])), 2),
            height_m=round(_median(info.get("heights", [])), 2),
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

    # ARCs como segmentos (paredes curvas, trechos circulares de circulação)
    for arc in msp.query("ARC"):
        try:
            r = arc.dxf.radius
            start_angle = math.radians(arc.dxf.start_angle)
            end_angle = math.radians(arc.dxf.end_angle)
            if end_angle < start_angle:
                end_angle += 2 * math.pi
            length_raw = abs(r * (end_angle - start_angle))
            length = length_raw * unit_factor
            if length > 0:
                c = arc.dxf.center
                walls.append(WallSegment(
                    layer=arc.dxf.layer,
                    length=length,
                    start=(c.x + r * math.cos(start_angle), c.y + r * math.sin(start_angle)),
                    end=(c.x + r * math.cos(end_angle), c.y + r * math.sin(end_angle)),
                ))
        except Exception:
            continue

    # CIRCLEs fechados (2πr)
    for circle in msp.query("CIRCLE"):
        try:
            r = circle.dxf.radius
            length = (2 * math.pi * r) * unit_factor
            if length > 0:
                c = circle.dxf.center
                walls.append(WallSegment(
                    layer=circle.dxf.layer,
                    length=length,
                    start=(c.x, c.y),
                    end=(c.x, c.y),
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
            # Tentar primeiro o .plain_text() do ezdxf (já strip da formatação)
            try:
                content = mtext.plain_text(split=False).strip()
            except Exception:
                content = _strip_mtext_codes(mtext.text).strip()
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
                # Pular cotas vazias (0 ou muito pequenas — provavelmente dim sem valor real)
                if abs(value_m) < 0.001:
                    continue
                display_label = label if label else "cota"
                dims.append((display_label, f"{value_m:.3f} m"))
            elif label and label != "0" and label != "":
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

# Matching é feito por TOKEN: o nome do layer é dividido em partes (por -, _, ., /
# etc.) e cada parte é comparada aos aliases. Match = token EQUALS alias ou token
# STARTS WITH alias. Isso pega tanto nomes AIA ("A-WALL-INT"), numéricos
# ("04-PAREDES_DRYWALL"), portugueses ("FOR-GESSO") quanto curtos ("LUM-01").
_LAYER_PATTERNS: list[tuple[list[str], str]] = [
    (["LUM", "LUMI", "LUMINARIA", "ILUM", "ILU", "LIGHT", "LT", "LGT"],                           "luminarias"),
    (["PAR", "PARED", "PAREDE", "WALL", "DRY", "DRYWALL", "GESS", "GYP", "DIV", "DVR"],           "paredes"),
    (["FOR", "FORR", "FORRO", "CEIL", "TET", "TETO"],                                             "forro"),
    (["PIS", "PISO", "FLOOR", "FLR", "FLOR", "PAV", "CARPE", "CARPET", "RODA", "RODAP", "SKIRT"], "piso"),
    (["PORT", "PORTA", "PRT", "DOOR", "DR"],                                                      "portas"),
    (["SPK", "SPRINK", "SPRINKLER", "INC", "INCEND", "INCENDIO", "FIRE", "PPCI"],                 "incendio"),
    (["ELET", "ELETR", "ELE", "ELEC", "POWR", "POWER", "TOMAD", "TOM", "TOMADA", "INTER", "CIRC"], "eletrica"),
    (["HVAC", "COND", "CLIMA", "DUTO", "DIFUS", "FRIG", "EVAP", "SPLIT", "CHILL", "ARCOND"],      "ar_condicionado"),
    (["DAD", "DADOS", "DATA", "REDE", "LOG", "VOIP", "RJ", "CAT6", "WIFI", "ACCESS"],             "dados"),
    (["DEM", "DEMOL", "DEMO", "DEMOLIR"],                                                         "demolicao"),
    (["PINT", "PINTURA", "PAINT", "PNT"],                                                         "pintura"),
]

_LAYER_SPLIT_RE = re.compile(r"[-_\s./\\|:]+")


def _layer_matches_category(layer_name: str, keywords: list[str]) -> bool:
    """Return True se algum token do layer_name casa com algum keyword.
    Match via EQUALS ou STARTS WITH (case-insensitive)."""
    if not layer_name:
        return False
    tokens = [t.upper() for t in _LAYER_SPLIT_RE.split(layer_name) if t]
    for tok in tokens:
        for kw in keywords:
            if tok == kw or tok.startswith(kw):
                return True
    return False


def identify_architectural_elements(extraction: DXFExtraction) -> dict:
    """Map extraction data to architectural categories based on layer AND block names.

    Classificação em dois passos:
    1. Layer → categoria (primary)
    2. Block name → categoria (fallback quando o layer é genérico ex. "0" ou xref)

    Returns:
        dict mapping category name to a dict with keys:
            - "layers": list of matching layer names
            - "blocks": list of BlockCount categorized (via layer OR nome)
            - "walls": list of WallSegment on matching layers
            - "hatches": list of HatchArea on matching layers
            - "texts": list of TextAnnotation on matching layers
    """
    result: dict = {}

    for keywords, category in _LAYER_PATTERNS:
        matching_layers = [
            lyr for lyr in extraction.layers
            if _layer_matches_category(lyr, keywords)
        ]
        layer_set = set(matching_layers)

        # Blocks classificados por layer
        blocks_by_layer = [b for b in extraction.blocks if b.layer in layer_set]
        # Blocks classificados pelo NOME (rodape, porta_PM3, lum-R4) — só se
        # o layer ainda não casou, evita dupla categorização
        blocks_by_name = [
            b for b in extraction.blocks
            if b.layer not in layer_set
            and _layer_matches_category(b.name, keywords)
        ]
        blocks_combined = blocks_by_layer + blocks_by_name

        if not matching_layers and not blocks_by_name:
            continue

        result[category] = {
            "layers": matching_layers,
            "blocks": blocks_combined,
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
    "luminarias":        "Iluminação",
    "paredes":           "Fechamentos Verticais",
    "forro":             "Forros",
    "piso":              "Pisos e Rodapés",
    "portas":            "Portas e Ferragens",
    "incendio":          "Prevenção e Combate a Incêndio",
    "eletrica":          "Instalações Elétricas",
    "ar_condicionado":   "Ar-Condicionado",
    "dados":             "Instalações Elétricas e Dados",
    "demolicao":         "Demolição e Remoção",
    "pintura":           "Revestimentos",
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
