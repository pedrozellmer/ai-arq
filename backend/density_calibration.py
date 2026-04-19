# -*- coding: utf-8 -*-
"""Calibração por densidade — aprende RATIOS (qty/área) de orçamentos
históricos e ALERTA sobre anomalias em projetos novos.

Regra do produto (feedback_calibracao_por_densidade.md):
- Armazena densidades por tipologia (ex.: luminárias/m² em "office"), NÃO
  quantidades absolutas.
- Projetos novos NUNCA copiam valores de outros; densidade fora de ±2σ
  gera ALERTA (confidence → estimado + observação laranja).
- Calibração NUNCA promove confidence pra "confirmado".

Tabela Supabase `density_benchmarks`:
  (item_type, typology, unit)  [chave composta única]
  mean, stddev, min_value, max_value, n_projects, updated_at
"""
import json
import re
import time
import statistics
import unicodedata
import urllib.request
from typing import Optional

from openpyxl import load_workbook


SUPABASE_URL = "https://kqjabzwgbfuivzlcfvvu.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtxamFiendnYmZ1aXZ6bGNmdnZ1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYwMDg5NzcsImV4cCI6MjA5MTU4NDk3N30.48xSenZlDV0LfD94ZxwGvX41Kf9Je2n-ouZpJrrCSKI"

_benchmarks_cache = {"data": None, "timestamp": 0}
_CACHE_TTL = 300  # 5 min


def _normalize_item_type(description: str) -> str:
    """Normaliza descrição pra chave estável — mesma lógica do calibrator."""
    if not description:
        return ""
    text = description.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:50]


def _parse_float(val) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(",", ".").strip()
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def extract_density_ratios(xlsx_path: str, area_m2: float, typology: str) -> list[dict]:
    """Lê XLSX histórico e computa qty/área pra cada item com qty numérica.

    Retorna lista de dicts: {item_type, description, unit, qty, density, typology}.
    Tolerante a layouts variados — ignora linhas sem desc ou qty inválida.
    """
    if area_m2 <= 0 or not xlsx_path:
        return []

    try:
        wb = load_workbook(xlsx_path, read_only=True, data_only=True)
    except Exception as e:
        print(f"[density] Erro ao abrir {xlsx_path}: {e}")
        return []

    ratios: list[dict] = []
    for sheet_name in wb.sheetnames:
        try:
            ws = wb[sheet_name]
        except Exception:
            continue
        for row in ws.iter_rows(min_row=1, max_col=10, values_only=True):
            if not row or len(row) < 4:
                continue
            # Heurística flexível: procura uma célula-string (desc) e uma
            # célula numérica (qty) dentro das 10 primeiras colunas. Units
            # costumam estar adjacentes à descrição.
            desc = None
            desc_idx = -1
            for i, cell in enumerate(row[:6]):
                if isinstance(cell, str) and len(cell.strip()) >= 5:
                    desc = cell.strip()
                    desc_idx = i
                    break
            if not desc:
                continue

            unit = ""
            qty = 0.0
            # Procura unit (string curta com "m", "m2", "un", "ml"...) e qty
            # (número) nas colunas após a descrição
            for cell in row[desc_idx + 1:desc_idx + 5]:
                if isinstance(cell, str):
                    s = cell.strip().lower()
                    if s in ("m", "m2", "m²", "un", "ml", "pc", "kg", "l", "h", "dia", "vb"):
                        unit = s.replace("m2", "m²")
                elif isinstance(cell, (int, float)) and cell > 0 and qty == 0:
                    qty = float(cell)
            if qty <= 0:
                continue

            density = qty / area_m2
            if density <= 0 or density > 100:  # filtro de outliers grosseiros
                continue

            # Filtra linhas de totais/headers/seções (conteúdo muito genérico)
            desc_lower = desc.lower()
            if any(w in desc_lower for w in (
                "total geral", "subtotal", "soma", "resumo",
                "descrição", "descricao", "item", "discriminação",
            )) and len(desc.strip()) < 25:
                continue

            ratios.append({
                "item_type": _normalize_item_type(desc),
                "description": desc,
                "unit": unit or "vb",
                "qty": round(qty, 4),
                "density": round(density, 6),
                "typology": typology,
            })

    wb.close()
    return ratios


def _supabase_upsert(table: str, record: dict, on_conflict: str) -> bool:
    """Upsert (insert or update) via Supabase REST."""
    try:
        url = f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={on_conflict}"
        body = json.dumps(record).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Prefer", "resolution=merge-duplicates,return=minimal")
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"[density] Upsert error: {e}")
        return False


def _supabase_select(table: str, query: str = "select=*") -> list[dict]:
    try:
        url = f"{SUPABASE_URL}/rest/v1/{table}?{query}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("Accept", "application/json")
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[density] Select error: {e}")
        return []


def ingest_budget(xlsx_path: str, area_m2: float, typology: str,
                  project_label: str = "") -> dict:
    """Parseia XLSX e atualiza os benchmarks agregados.

    Retorna dict de resumo: {items_parsed, benchmarks_updated, new_item_types}.
    """
    ratios = extract_density_ratios(xlsx_path, area_m2, typology)
    if not ratios:
        return {"items_parsed": 0, "benchmarks_updated": 0, "new_item_types": 0,
                "error": "nenhuma linha válida extraída do XLSX"}

    # Busca benchmarks existentes pra esta tipologia
    existing = _supabase_select(
        "density_benchmarks",
        f"select=*&typology=eq.{urllib.request.quote(typology)}",
    )
    existing_by_key = {
        (r["item_type"], r.get("unit") or ""): r for r in existing
    }

    # Também salva a ingestão bruta (rastreabilidade)
    for r in ratios:
        raw_record = {
            "typology": typology,
            "item_type": r["item_type"],
            "description": r["description"][:200],
            "unit": r["unit"],
            "qty": r["qty"],
            "area_m2": area_m2,
            "density": r["density"],
            "project_label": project_label[:100],
        }
        _supabase_upsert(
            "density_ingest_raw", raw_record,
            "typology,item_type,unit,project_label",
        )

    # Agrega por (item_type, unit) pra recomputar média/stddev incluindo este upload
    updated = 0
    new_types = 0
    by_key: dict = {}
    for r in ratios:
        k = (r["item_type"], r["unit"])
        by_key.setdefault(k, []).append(r["density"])

    for (item_type, unit), densities in by_key.items():
        # Puxa histórico desta tipologia+item_type+unit (inclui esta ingestão)
        hist_q = (
            f"select=density,project_label&typology=eq.{urllib.request.quote(typology)}"
            f"&item_type=eq.{urllib.request.quote(item_type)}"
            f"&unit=eq.{urllib.request.quote(unit)}"
        )
        hist = _supabase_select("density_ingest_raw", hist_q)
        # Dedupe por project_label pra não super-representar um único projeto
        seen_labels = set()
        all_densities = []
        for h in hist:
            lab = h.get("project_label") or ""
            if lab in seen_labels:
                # mantém só 1 valor por projeto (média das linhas se múltiplas)
                continue
            seen_labels.add(lab)
            all_densities.append(_parse_float(h.get("density")))
        all_densities = [d for d in all_densities if d > 0]
        if not all_densities:
            continue

        n = len(all_densities)
        mean = statistics.mean(all_densities)
        stddev = statistics.stdev(all_densities) if n >= 2 else 0.0
        mn = min(all_densities)
        mx = max(all_densities)

        record = {
            "typology": typology,
            "item_type": item_type,
            "unit": unit,
            "mean": round(mean, 6),
            "stddev": round(stddev, 6),
            "min_value": round(mn, 6),
            "max_value": round(mx, 6),
            "n_projects": n,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if _supabase_upsert("density_benchmarks", record, "typology,item_type,unit"):
            if (item_type, unit) not in existing_by_key:
                new_types += 1
            updated += 1

    # Invalida cache
    _benchmarks_cache["data"] = None
    _benchmarks_cache["timestamp"] = 0

    return {
        "items_parsed": len(ratios),
        "benchmarks_updated": updated,
        "new_item_types": new_types,
    }


def get_benchmarks(typology: Optional[str] = None) -> dict:
    """Busca benchmarks do Supabase — indexado por (item_type, unit)."""
    now = time.time()
    if (_benchmarks_cache["data"] is not None and
            (now - _benchmarks_cache["timestamp"]) < _CACHE_TTL):
        cached = _benchmarks_cache["data"]
        if typology:
            return {k: v for k, v in cached.items() if v.get("typology") == typology}
        return cached

    query = "select=*"
    if typology:
        query += f"&typology=eq.{urllib.request.quote(typology)}"
    rows = _supabase_select("density_benchmarks", query)
    index: dict = {}
    for r in rows:
        key = (r.get("item_type", ""), r.get("unit", ""))
        index[key] = {
            "typology": r.get("typology", ""),
            "mean": _parse_float(r.get("mean")),
            "stddev": _parse_float(r.get("stddev")),
            "min_value": _parse_float(r.get("min_value")),
            "max_value": _parse_float(r.get("max_value")),
            "n_projects": int(r.get("n_projects") or 0),
        }
    _benchmarks_cache["data"] = index
    _benchmarks_cache["timestamp"] = now
    return index


def check_density_anomaly(item, project_area_m2: float,
                          benchmarks: Optional[dict] = None,
                          typology: str = "office") -> tuple[bool, str]:
    """Verifica se a densidade do item é anômala.

    Retorna (is_anomaly, motivo). Motivo vazio se ok ou sem benchmark.
    Só ALERTA — nunca sobe confidence pra confirmado.

    Critérios:
    - Precisa de n_projects >= 2 (benchmark estatisticamente pobre abaixo disso)
    - Anomalia alta: density > mean + 2σ OU density > max * 1.5
    - Anomalia baixa: density < mean - 2σ (só se threshold > 0)
    """
    if project_area_m2 <= 0:
        return False, ""
    try:
        qty = float(item.quantity or 0)
    except Exception:
        return False, ""
    if qty <= 0:
        return False, ""

    if benchmarks is None:
        benchmarks = get_benchmarks(typology=typology)
    if not benchmarks:
        return False, ""

    item_type = _normalize_item_type(item.description)
    if not item_type:
        return False, ""

    unit = (item.unit or "").strip()
    bench = benchmarks.get((item_type, unit))
    if bench is None:
        # Fallback: procura qualquer unit
        for (it, u), b in benchmarks.items():
            if it == item_type:
                bench = b
                break
    if bench is None:
        return False, ""

    n = bench["n_projects"]
    if n < 2:
        return False, ""

    density = qty / project_area_m2
    mean = bench["mean"]
    stddev = bench["stddev"]
    max_v = bench["max_value"]

    if mean <= 0:
        return False, ""

    # Alta
    threshold_hi = mean + 2 * stddev if stddev > 0 else mean * 2.5
    if density > threshold_hi or (max_v > 0 and density > max_v * 1.5):
        factor = density / mean
        return True, (
            f"densidade {density:.3f} {unit}/m² é {factor:.1f}× maior que "
            f"o típico ({mean:.3f} ± {stddev:.3f}, n={n} projetos) — "
            f"possível dupla contagem"
        )
    # Baixa (só se faz sentido)
    threshold_lo = mean - 2 * stddev if stddev > 0 else mean / 2.5
    if threshold_lo > 0 and density < threshold_lo:
        factor = mean / density if density > 0 else 0
        return True, (
            f"densidade {density:.3f} {unit}/m² é {factor:.1f}× menor que "
            f"o típico ({mean:.3f} ± {stddev:.3f}, n={n} projetos) — "
            f"possível subcontagem"
        )

    return False, ""


def ddl_statements() -> list[str]:
    """Retorna as declarações SQL das tabelas do Supabase — referência/doc."""
    return [
        """CREATE TABLE IF NOT EXISTS density_benchmarks (
            typology text NOT NULL,
            item_type text NOT NULL,
            unit text NOT NULL,
            mean double precision NOT NULL,
            stddev double precision DEFAULT 0,
            min_value double precision DEFAULT 0,
            max_value double precision DEFAULT 0,
            n_projects integer DEFAULT 1,
            updated_at timestamptz DEFAULT now(),
            PRIMARY KEY (typology, item_type, unit)
        );""",
        """CREATE TABLE IF NOT EXISTS density_ingest_raw (
            id bigserial PRIMARY KEY,
            typology text NOT NULL,
            item_type text NOT NULL,
            description text,
            unit text NOT NULL,
            qty double precision,
            area_m2 double precision,
            density double precision,
            project_label text,
            ingested_at timestamptz DEFAULT now(),
            UNIQUE (typology, item_type, unit, project_label)
        );""",
    ]
