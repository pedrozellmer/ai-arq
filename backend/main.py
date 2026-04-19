# -*- coding: utf-8 -*-
"""API Backend AI.arq — Processamento de pranchas de arquitetura."""
import os
import uuid
import shutil
import asyncio
import tempfile
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from dotenv import load_dotenv

# Carregar .env do mesmo diretório do script
_script_dir = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.join(_script_dir, '.env')
if os.path.exists(_env_path):
    with open(_env_path, 'r') as _f:
        for _line in _f:
            _line = _line.strip()
            if '=' in _line and not _line.startswith('#'):
                _k, _v = _line.split('=', 1)
                os.environ[_k.strip()] = _v.strip()
else:
    load_dotenv()

from models import ProcessingStatus
from processor import process_pdfs
from analyzer import analyze_all_sheets
from spreadsheet import generate_spreadsheet
from instagram_webhook import router as instagram_router
# calibrator.py foi desativado: o modelo de "fator absoluto" (real/ai) não
# respeita o isolamento entre projetos. A calibração agora é 100% por
# densidade (density_calibration.py) e só gera alertas.

# Supabase client para salvar projetos
SUPABASE_URL = "https://kqjabzwgbfuivzlcfvvu.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtxamFiendnYmZ1aXZ6bGNmdnZ1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYwMDg5NzcsImV4cCI6MjA5MTU4NDk3N30.48xSenZlDV0LfD94ZxwGvX41Kf9Je2n-ouZpJrrCSKI"

# Log persistente de operações Supabase (só erros + último sucesso por operação)
# pra poder investigar via /api/debug/supa-log quando o log do Render tá fora de alcance.
_SUPA_LOG_PATH = os.path.join(tempfile.gettempdir(), "aiarq_supa_log.txt")


def _supa_log(line: str):
    try:
        with open(_SUPA_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.utcnow().isoformat()}Z {line}\n")
    except Exception:
        pass


def _supabase_insert(table, data):
    """Insere registro no Supabase via REST API."""
    import urllib.request, urllib.error, json
    try:
        url = f"{SUPABASE_URL}/rest/v1/{table}"
        body = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Prefer', 'return=minimal')
        urllib.request.urlopen(req, timeout=20)
        _supa_log(f"INSERT {table} OK  data={json.dumps(data)[:200]}")
        return True
    except urllib.error.HTTPError as e:
        try:
            resp_body = e.read().decode('utf-8', errors='replace')[:500]
        except Exception:
            resp_body = '(unreadable)'
        msg = f"INSERT {table} HTTP {e.code}: {resp_body}  data={json.dumps(data)[:200]}"
        print(f"Supabase insert HTTP {e.code} ({table}): {resp_body}")
        _supa_log(msg)
        return False
    except Exception as e:
        msg = f"INSERT {table} ERR {type(e).__name__}: {e}  data={json.dumps(data)[:200]}"
        print(f"Supabase insert error ({table}): {type(e).__name__}: {e}")
        _supa_log(msg)
        return False


def _supabase_update(table, match_field, match_value, data):
    """Atualiza registro no Supabase via REST API."""
    import urllib.request, urllib.error, json
    try:
        url = f"{SUPABASE_URL}/rest/v1/{table}?{match_field}=eq.{match_value}"
        body = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='PATCH')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Prefer', 'return=minimal')
        urllib.request.urlopen(req, timeout=20)
        _supa_log(f"UPDATE {table} {match_field}={match_value} OK  data={json.dumps(data)[:200]}")
        return True
    except urllib.error.HTTPError as e:
        try:
            resp_body = e.read().decode('utf-8', errors='replace')[:500]
        except Exception:
            resp_body = '(unreadable)'
        msg = f"UPDATE {table} {match_field}={match_value} HTTP {e.code}: {resp_body}  data={json.dumps(data)[:200]}"
        print(f"Supabase update HTTP {e.code} ({table} where {match_field}={match_value}): {resp_body}")
        _supa_log(msg)
        return False
    except Exception as e:
        msg = f"UPDATE {table} {match_field}={match_value} ERR {type(e).__name__}: {e}  data={json.dumps(data)[:200]}"
        print(f"Supabase update error ({table} where {match_field}={match_value}): {type(e).__name__}: {e}")
        _supa_log(msg)
        return False

# ═══════════════════════════════════════════════════════════════
#  Supabase Storage helpers (bucket aiarq-planilhas)
#  Persiste planilhas geradas pra sobreviverem a redeploys do Render.
# ═══════════════════════════════════════════════════════════════

PLANILHAS_BUCKET = "aiarq-planilhas"


def _supabase_storage_upload(local_path: str, remote_key: str) -> bool:
    """Faz upload de um arquivo pro Supabase Storage. Sobrescreve se existe."""
    import urllib.request, urllib.error
    try:
        with open(local_path, "rb") as f:
            body = f.read()
        url = f"{SUPABASE_URL}/storage/v1/object/{PLANILHAS_BUCKET}/{remote_key}"
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("Content-Type",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        req.add_header("x-upsert", "true")
        urllib.request.urlopen(req, timeout=30)
        _supa_log(f"STORAGE upload {remote_key} OK ({len(body)} bytes)")
        return True
    except urllib.error.HTTPError as e:
        try:
            resp_body = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            resp_body = "(unreadable)"
        _supa_log(f"STORAGE upload {remote_key} HTTP {e.code}: {resp_body}")
        print(f"Storage upload {remote_key} HTTP {e.code}: {resp_body}")
        return False
    except Exception as e:
        _supa_log(f"STORAGE upload {remote_key} ERR {type(e).__name__}: {e}")
        print(f"Storage upload error: {e}")
        return False


def _supabase_storage_download(remote_key: str, local_path: str) -> bool:
    """Baixa arquivo do Supabase Storage pra path local. Cria diretório se preciso."""
    import urllib.request
    try:
        url = f"{SUPABASE_URL}/storage/v1/object/{PLANILHAS_BUCKET}/{remote_key}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        resp = urllib.request.urlopen(req, timeout=30)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(resp.read())
        return True
    except Exception as e:
        print(f"Storage download error ({remote_key}): {e}")
        return False


def get_planilha_path(job_id: str) -> Optional[str]:
    """Retorna o path local da planilha de um job. Se sumiu (Render
    /tmp volátil), tenta baixar do Supabase Storage. None se falhou."""
    local = os.path.join(WORK_DIR, job_id, f"orcamento_{job_id}.xlsx")
    if os.path.exists(local):
        return local
    if _supabase_storage_download(f"{job_id}.xlsx", local):
        return local
    return None


app = FastAPI(
    title="AI.arq API",
    description="Motor de processamento de pranchas de arquitetura com IA",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Instagram Agent (desativado por padrão, ativar manualmente via /api/instagram/toggle) ──
app.include_router(instagram_router)

# Armazenamento de jobs em arquivo JSON (sobrevive a restarts)
import json as _json
WORK_DIR = os.path.join(tempfile.gettempdir(), "aiarq_jobs")
os.makedirs(WORK_DIR, exist_ok=True)
JOBS_FILE = os.path.join(WORK_DIR, "_jobs.json")

def _load_jobs() -> dict:
    try:
        if os.path.exists(JOBS_FILE):
            with open(JOBS_FILE, 'r') as f:
                return _json.load(f)
    except: pass
    return {}

def _save_jobs(jobs_dict):
    try:
        with open(JOBS_FILE, 'w') as f:
            _json.dump(jobs_dict, f)
    except: pass

class JobsStore:
    """Armazena jobs em arquivo JSON."""
    def __getitem__(self, key):
        jobs = _load_jobs()
        if key not in jobs:
            raise KeyError(key)
        return ProcessingStatus(**jobs[key])

    def __setitem__(self, key, value):
        jobs = _load_jobs()
        if isinstance(value, ProcessingStatus):
            jobs[key] = value.model_dump()
        else:
            jobs[key] = value
        _save_jobs(jobs)

    def __contains__(self, key):
        return key in _load_jobs()

    def update_field(self, key, **kwargs):
        jobs = _load_jobs()
        if key in jobs:
            jobs[key].update(kwargs)
            _save_jobs(jobs)

jobs = JobsStore()


# Regras determinísticas de unidade por tipo de serviço (pós-IA).
# Se a IA retornar unidade errada pra descrição específica, o código força a
# unidade correta e marca o item como "estimado" (laranja) pra o usuário revisar.
import re as _re
_UNIT_SURFACE_KEYWORDS = _re.compile(
    r"\b(pisos?|forros?|pinturas?|revestimentos?|azulejos?|cer[âa]micas?|"
    r"porcelanatos?|carpetes?|viníl|vinílicos?|tapetes?)\b",
    _re.IGNORECASE,
)
_UNIT_LINEAR_KEYWORDS = _re.compile(
    r"\b(rodap[eé]s?|tabicas?|soleiras?|perfi(?:l|s)|perfilados?|molduras?|"
    r"eletrocalhas?|eletrodutos?|trilhos?|cord[aã]o|cord[õo]es|"
    r"cornijas?)\b",
    _re.IGNORECASE,
)
_UNIT_COUNT_KEYWORDS = _re.compile(
    r"\b(lumin[áa]rias?|spots?|projetores?|pendentes?|arandelas?|"
    r"portas?|janelas?|esquadrias?|tomadas?|interruptores?|sensores?|"
    r"difusores?|grelhas?|sprinklers?|detectores?|c[âa]meras?|cftv|"
    r"quadro|qdf|caixa(?:\s+de\s+som)?|al[çc]ap[ãa]o|al[çc]ap[õo]es|"
    r"chuveiros?|torneiras?)\b",
    _re.IGNORECASE,
)


_GENERIC_WORDS = {
    "de", "do", "da", "dos", "das", "para", "com", "em",
    "nova", "novo", "existente", "existentes",
    "conforme", "especificacao", "especificacoes", "projeto",
    "instalacao", "execucao", "fornecimento", "fornecida",
    "tipo", "tipos", "cor", "modelo", "padrao",
    "altura", "comprimento", "largura", "espessura",
    "ceramico", "ceramica", "ceramicos", "ceramicas",
    "metalico", "metalica", "plastico", "plastica",
    "area", "areas",
    "m2", "m", "un", "ml",
}


def _normalize_description_key(desc: str) -> str:
    """Reduz a descrição a uma chave de comparação — remove acentos, sufixos
    por departamento, números extras, e faz lowercase. Usado pra detectar
    itens similares em consolidação."""
    if not desc:
        return ""
    s = desc.lower()
    # Remover acentos
    import unicodedata
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    # Remover sufixos de departamento/variante
    # Ex.: "painel divisorio - contabilidade" → "painel divisorio"
    # Ex.: "demarcacao de area departamento contabilidade" → "demarcacao de area"
    for sep in (' - ', ' — ', ' / ', ' departamento ', ' deptos ', ' do depto ',
                ' da sala ', ' sala ', ' para sala '):
        s = s.split(sep)[0]
    # Normalizar espaços e pontuação
    s = _re.sub(r"[^a-z0-9]+", " ", s)
    s = _re.sub(r"\s+", " ", s).strip()
    # Remover palavras genéricas que não mudam o significado
    tokens = [t for t in s.split() if t not in _GENERIC_WORDS and len(t) > 1]
    return " ".join(sorted(tokens[:6]))  # primeiras 6 palavras ordenadas


def _primary_noun(desc: str) -> str:
    """Retorna o primeiro token significativo (>3 chars, não-genérico) da
    descrição. Usado pra detectar mesma 'família' (alvenaria, luminária, etc.)
    mesmo quando descrições divergem bastante."""
    if not desc:
        return ""
    import unicodedata
    s = unicodedata.normalize('NFD', desc.lower())
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = _re.sub(r"[^a-z0-9]+", " ", s)
    for t in s.split():
        if len(t) > 3 and t not in _GENERIC_WORDS:
            return t
    return ""


def _pick_best_unit(units: list[str], description: str) -> str:
    """Entre vários units candidatos, escolhe o mais coerente com a descrição.
    Se o normalizer semântico diz algo, usa. Senão, prefere contagem (un) >
    linear (ml) > superfície (m²) > vb — ordem de especificidade crescente."""
    norm, corrected = _normalize_unit_for_item(description, units[0] if units else "vb")
    if corrected:
        return norm
    # Sem opinião semântica: primeiro unidade não-m² presente (m² é o problema usual)
    priority = ["un", "ml", "m²", "m", "vb"]
    for u in priority:
        if u in units:
            return u
    return units[0] if units else "vb"


def _consolidate_items(items: list) -> list:
    """Consolida itens redundantes em duas passadas:

    PASSADA 1 — por (chave_normalizada, unidade):
    - Mesma chave + mesma qty + mesma unidade → mantém 1 (desc mais completa).
    - Mesma chave + mesma unidade + qtys diferentes → mantém todos.
    - Réplica por departamento (4+ itens, qty<2) → funde em 1 estimado.

    PASSADA 2 — fusões mais agressivas (qty+discipline+noun):
    - Mesma qty_arredondada + mesma discipline + units diferentes →
      funde (ex.: LED LINE m² vs ml com qty 222.11). Escolhe melhor unit.
    - Mesma qty_arredondada + mesma discipline + mesma unit + primary_noun
      igual → funde (ex.: alvenaria 491.84 ml × 2 descrições diferentes).
    """
    from models import BudgetItem, Confidence

    # ── Passada 1 ──
    groups: dict = {}
    for item in items:
        key = (_normalize_description_key(item.description), item.unit)
        groups.setdefault(key, []).append(item)

    pass1 = []
    for key, group in groups.items():
        if len(group) == 1:
            pass1.append(group[0])
            continue

        quantities = [round(float(it.quantity), 2) for it in group]
        unique_qtys = set(quantities)

        # Réplica por departamento tem prioridade (4+ itens com qty < 2) —
        # independente de qtys serem idênticas, porque itens "Contabilidade"
        # e "RH" costumam bater mesmo quando são na verdade áreas distintas.
        if max(quantities) < 2.0 and len(group) >= 4:
            best = max(group, key=lambda x: len(x.description or ""))
            clean_desc = best.description
            for sep in (' - ', ' — ', ' departamento ', ' deptos ', ' da sala '):
                clean_desc = clean_desc.split(sep)[0]
            total_qty = round(sum(quantities), 2)
            consolidated = BudgetItem(
                item_num=best.item_num,
                description=f"{clean_desc.strip()} (várias variantes)",
                unit=best.unit,
                quantity=total_qty,
                observations=(
                    f"Consolidado de {len(group)} entradas replicadas por "
                    f"departamento/variante — soma de qtys: {total_qty} {best.unit}. "
                    f"Revisar se faz sentido tratar como item único."
                ),
                ref_sheet=best.ref_sheet,
                confidence=Confidence("estimado"),
                discipline=best.discipline,
            )
            pass1.append(consolidated)
        elif len(unique_qtys) == 1:
            best = max(group, key=lambda x: len(x.description or ""))
            pass1.append(best)
        else:
            pass1.extend(group)

    # ── Passada 2 ──
    # Cada item é reapresentado com fingerprint (discipline, qty_arred). Se
    # mais de um item compartilha fingerprint, avaliamos noun+overlap pra
    # decidir se funde.
    # Qty pequena (< 2) é frequentemente um "un" que se repete por acaso — não
    # fundimos por coincidência de qty+discipline nesse range pra evitar falso
    # positivo (ex.: 1 porta de emergência + 1 porta comum ambas qty=1).
    MIN_QTY_PASS2 = 2.0

    buckets: dict = {}
    for it in pass1:
        try:
            qty_r = round(float(it.quantity or 0), 2)
        except Exception:
            qty_r = 0.0
        if qty_r < MIN_QTY_PASS2:
            buckets.setdefault(("__solo__", id(it)), []).append(it)
            continue
        buckets.setdefault((it.discipline or "", qty_r), []).append(it)

    pass2 = []
    for (disc, qty_r), group in buckets.items():
        if disc == "__solo__" or len(group) == 1:
            pass2.extend(group)
            continue

        # Tenta fundir itens do mesmo bucket em "famílias". Critério de fusão:
        # mesmo primary_noun OU interseção de >= 2 tokens significativos.
        # (1 token só gera FP — ex.: dois itens com "porta" mas sentidos distintos.)
        families: list[list] = []
        for it in group:
            noun = _primary_noun(it.description)
            key_tokens = set(_normalize_description_key(it.description).split())
            placed = False
            for fam in families:
                fam_noun = _primary_noun(fam[0].description)
                fam_tokens = set(_normalize_description_key(fam[0].description).split())
                overlap = key_tokens & fam_tokens
                if noun and noun == fam_noun:
                    fam.append(it); placed = True; break
                if len(overlap) >= 2:
                    fam.append(it); placed = True; break
            if not placed:
                families.append([it])

        for fam in families:
            if len(fam) == 1:
                pass2.append(fam[0])
                continue
            # Fundir família: melhor descrição, melhor unidade, obs combinada
            best = max(fam, key=lambda x: len(x.description or ""))
            units = [it.unit for it in fam]
            chosen_unit = _pick_best_unit(units, best.description)
            unit_changed = len(set(units)) > 1
            variant_count = len(fam)
            obs_parts = [best.observations or ""]
            if unit_changed:
                obs_parts.append(
                    f"Fundido de {variant_count} entradas com units divergentes "
                    f"({'/'.join(sorted(set(units)))}) — mesma qty {qty_r}"
                )
            else:
                obs_parts.append(
                    f"Fundido de {variant_count} entradas com mesma qty "
                    f"{qty_r} {chosen_unit} — descrições similares"
                )
            merged_item = BudgetItem(
                item_num=best.item_num,
                description=best.description,
                unit=chosen_unit,
                quantity=float(qty_r),
                observations=" | ".join(p for p in obs_parts if p).strip(),
                ref_sheet=best.ref_sheet,
                confidence=Confidence("estimado"),
                discipline=best.discipline,
            )
            pass2.append(merged_item)

    return pass2


# Ranges plausíveis por unidade — valores fora disso indicam erro provável.
# Valores em contexto de reforma de escritório corporativo (nosso nicho atual).
_PLAUSIBILITY_RANGES = {
    "un": (0, 5000),   # 5000+ un em uma obra é raro (ex.: difusores AC em torre)
    "ml": (0, 50000),  # 50km de perfil é improvável; mas casos grandes permitidos
    "m²": (0, 50000),  # 50000m² = escritório de 5 andares grandes
    "m": (0, 50000),
    "mês": (0, 60),    # 5 anos de obra é improvável
    "dia": (0, 1000),  # 3 anos em dias
    "%": (0, 100),     # percentual
    "vb": (0, 1),      # verba por definição é 0 ou 1
}
# Combinações disciplina × unidade que não fazem sentido.
# (disciplina, unidade) -> mensagem descritiva do problema
_DISCIPLINE_UNIT_MISMATCHES = {
    ("Iluminação", "m²"): "luminárias se contam em 'un', não em área",
    ("Iluminação", "m"):  "luminárias se contam em 'un', não em metros",
    ("Pisos e Rodapés", "un"): "piso é superfície, deve ser m² — exceção: elementos pontuais como grelhas",
    ("Forros", "un"): "forro é superfície, deve ser m²",
    ("Ar-Condicionado", "m²"): "equipamentos de AC são unidades, não área",
    ("Incêndio e Segurança", "m²"): "sprinklers/detectores são unidades",
    ("Portas e Ferragens", "m²"): "portas são unidades, não área",
}


def _check_plausibility(item, project_total_area_m2: float = 0) -> tuple[bool, str]:
    """Retorna (é_plausível, motivo_se_não). Só avalia — decisão é do caller."""
    if item is None:
        return True, ""
    try:
        qty = float(item.quantity or 0)
    except Exception:
        return False, "quantidade não-numérica"

    # 1. Range plausível pela unidade
    unit = item.unit or "vb"
    if unit in _PLAUSIBILITY_RANGES:
        lo, hi = _PLAUSIBILITY_RANGES[unit]
        if qty > hi:
            return False, f"{qty:.0f} {unit} é alto demais pro tipo (max típico {hi})"
        if qty < lo:
            return False, f"{qty} {unit} é negativo"

    # 2. Disciplina × unidade
    disc = item.discipline or ""
    mismatch_key = (disc, unit)
    if mismatch_key in _DISCIPLINE_UNIT_MISMATCHES:
        return False, _DISCIPLINE_UNIT_MISMATCHES[mismatch_key]

    # 3. Área vs laje (só pra superfícies)
    if unit == "m²" and project_total_area_m2 > 0 and qty > project_total_area_m2 * 1.5:
        return False, (
            f"área {qty:.1f} m² é maior que 1.5× área da laje "
            f"({project_total_area_m2:.0f} m²) — possível dupla contagem"
        )

    return True, ""


def _validate_quantity_for_unit(item) -> tuple[float, bool]:
    """Garante consistência entre unidade e quantidade.
    - 'un' só aceita inteiros positivos (arredonda se frac, ou zera + marca estimado)
    - 'ml' / 'm²' aceita qualquer número >= 0
    Retorna (qty_ajustada, foi_ajustada)"""
    qty = float(item.quantity) if item.quantity is not None else 0
    if item.unit == "un":
        if qty != int(qty):
            # un com decimal é suspeito (ex.: "un=222.11")
            # Se for "quase inteiro" (ex.: 9.0001), arredonda. Senão zera.
            if abs(qty - round(qty)) < 0.01:
                return float(round(qty)), True
            # Valor claramente não é contagem — descartar e marcar estimado
            return 0.0, True
    return qty, False


def _normalize_unit_for_item(description: str, current_unit: str) -> tuple[str, bool]:
    """Ajusta a unidade baseada na descrição do item.
    Retorna (unidade_nova, foi_corrigida).
    - Item com palavra-chave de SUPERFÍCIE (piso/forro/pintura) → m²
    - Item com palavra-chave LINEAR (rodapé/perfil/eletrocalha) → ml
    - Item com palavra-chave CONTÁVEL (luminária/porta) → un
    - Senão, mantém a unidade atual"""
    if not description:
        return current_unit, False
    desc_lower = description.lower()

    # Vb / % / mês / dia são especiais — não corrigir
    if current_unit in ("vb", "%", "mês", "mes", "dia", "h"):
        return current_unit, False

    # Ordem de precedência: contável > linear > superfície (senão piso vira superfície erroneamente)
    if _UNIT_COUNT_KEYWORDS.search(desc_lower):
        if current_unit != "un":
            return "un", True
        return "un", False
    if _UNIT_LINEAR_KEYWORDS.search(desc_lower):
        if current_unit != "ml":
            return "ml", True
        return "ml", False
    if _UNIT_SURFACE_KEYWORDS.search(desc_lower):
        if current_unit != "m²":
            return "m²", True
        return "m²", False
    return current_unit, False


def process_job(job_id: str, file_paths: list[str], work_dir: str,
                typology: str = "office"):
    """Processa um job prancha por prancha. Aceita PDF, DWG e DXF.

    `typology` alimenta a camada de calibração por densidade — alertas
    comparam o projeto contra benchmarks da mesma categoria."""
    import gc
    import anthropic
    from processor import identify_sheet_type, extract_text, render_crops
    from analyzer import analyze_sheet, SYSTEM_PROMPT
    from models import SheetInfo, SheetType, ProjectData, BudgetItem, Confidence

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        jobs.update_field(job_id, status="error")
        jobs.update_field(job_id, error_message="API key não configurada")
        return

    try:
        jobs.update_field(job_id, status="processing")
        jobs.update_field(job_id, progress=3)
        jobs.update_field(job_id, current_step="Iniciando processamento...")

        # Funções auxiliares (definir antes de usar)
        def sf(v):
            if v is None: return 0
            s = str(v).replace('m²','').replace('m2','').replace('cm','').replace(',','').strip()
            try: return float(s)
            except: return 0

        project_data = ProjectData()

        # Separar PDFs de DWG/DXF
        pdf_paths = [f for f in file_paths if f.lower().endswith('.pdf')]
        cad_paths = [f for f in file_paths if f.lower().endswith(('.dwg', '.dxf'))]

        # ── Pesos de progresso alinhados com percepção do usuário ──
        # A fase que o usuário percebe como "cada prancha processada" é a análise
        # IA (CoT + JSON), não a conversão DWG→DXF (rápida, parte invisível).
        # Alocação:
        #   0-5%:    upload/init
        #   5-20%:   conversão DWG→DXF (leve, 15% span pro total dos CADs)
        #   20-X%:   análise DXF (maior fatia — cada DXF = 1/N do span restante)
        #   X-95%:   análise PDFs (se houver)
        #   95-100%: consolidação + planilha
        has_cad = bool(cad_paths)
        has_pdf = bool(pdf_paths)
        # Partição principal do progresso
        if has_cad and has_pdf:
            # CAD conversão 5→15%, análise CAD 15→55%, PDF 55→92%
            conv_end_pct = 15
            cad_analysis_end_pct = 55
        elif has_cad:
            # Só CAD: conversão 5→20%, análise CAD 20→92% (bem maior pra DXF dominar)
            conv_end_pct = 20
            cad_analysis_end_pct = 92
        else:
            # Só PDF: 5→92%
            conv_end_pct = 5
            cad_analysis_end_pct = 92
        cad_end_pct = cad_analysis_end_pct  # compatibilidade com código abaixo

        # Converter DWG→DXF se necessário
        dxf_paths = []
        if cad_paths:
            jobs.update_field(job_id, progress=5)
            jobs.update_field(job_id, current_step="Processando arquivos DWG/DXF...")
            try:
                from dwg_extractor import extract_from_file, generate_budget_data, convert_dwg_to_dxf
                n_cad = len(cad_paths)
                conv_span = conv_end_pct - 5  # ex.: 15 ou 10 pts
                for ci, cad_path in enumerate(cad_paths):
                    base = 5 + int((ci / max(n_cad, 1)) * conv_span)
                    ext = cad_path.lower().rsplit('.', 1)[-1]
                    if ext == 'dwg':
                        jobs.update_field(job_id, progress=base)
                        jobs.update_field(job_id, current_step=f"Convertendo DWG→DXF ({ci+1}/{n_cad}): {os.path.basename(cad_path)}")
                        dxf_path = convert_dwg_to_dxf(cad_path)
                        if dxf_path:
                            dxf_paths.append(dxf_path)
                            jobs.update_field(job_id, current_step=f"DWG convertido: {os.path.basename(dxf_path)}")
                        else:
                            jobs.update_field(job_id, current_step=f"Falha ao converter DWG: {os.path.basename(cad_path)} (seguindo sem)")
                    else:
                        dxf_paths.append(cad_path)
            except Exception as e:
                jobs.update_field(job_id, error_message=f"Erro DWG→DXF: {e}")
                raise

        # Extrair dados de DXF e enviar pro Claude interpretar
        dxf_items = []
        if dxf_paths:
            # Análise DXF começa onde a conversão termina
            extract_start = conv_end_pct
            jobs.update_field(job_id, progress=extract_start)
            jobs.update_field(job_id, current_step="Extraindo geometria dos DXF...")
            try:
                from dwg_extractor import extract_from_file
                from analyzer import SYSTEM_PROMPT
                import json as _j

                n_dxf = len(dxf_paths)
                dxf_span = cad_end_pct - extract_start
                for idx, dxf_path in enumerate(dxf_paths):
                    # Cada DXF ocupa 1/N da faixa. Extração 30% + IA 70% dentro da faixa.
                    dxf_base = extract_start + int((idx / max(n_dxf, 1)) * dxf_span)
                    dxf_next = extract_start + int(((idx + 1) / max(n_dxf, 1)) * dxf_span)
                    dxf_mid = dxf_base + int((dxf_next - dxf_base) * 0.3)

                    jobs.update_field(job_id, progress=dxf_base)
                    jobs.update_field(job_id, current_step=f"DXF {idx+1}/{n_dxf}: Extraindo {os.path.basename(dxf_path)}...")

                    # 1. Extrair dados estruturados do DXF
                    extraction = extract_from_file(dxf_path)
                    structured_text = extraction.to_structured_prompt()

                    # 2. Enviar pro Claude interpretar
                    jobs.update_field(job_id, progress=dxf_mid)
                    jobs.update_field(job_id, current_step=f"DXF {idx+1}/{n_dxf}: Nossa IA está analisando os dados extraídos...")
                    dxf_client = anthropic.Anthropic(api_key=api_key)

                    dxf_prompt = f"""Analise os dados extraídos de um arquivo DXF de projeto de arquitetura.
Os dados abaixo foram extraídos automaticamente do arquivo CAD (blocos, textos, layers, comprimentos, áreas).
Gere itens de orçamento com base nesses dados.

{structured_text}

════════════════════════════════════════════════════════
REGRA CRÍTICA DE CONFIANÇA — NUNCA ESTIMAR, SÓ MEDIR OU SUGERIR
════════════════════════════════════════════════════════

O campo "confidence" TEM apenas duas categorias possíveis:

1. "confirmado" — SÓ quando a quantidade corresponde EXATAMENTE a uma medição objetiva do DXF:
   - Contagem literal de blocos (INSERT) que aparece em "CONTAGEM DE BLOCOS"
   - Contagem literal de esquadrias na seção "ESQUADRIAS" (com dimensão W×H)
   - Comprimento calculado em "COMPRIMENTOS POR LAYER" (valor em metros)
   - Área calculada em "ÁREAS HACHURADAS POR LAYER" (valor em m²)
   - Cota numérica que aparece em "COTAS/DIMENSÕES"
   A quantidade do item TEM que bater com o número extraído. Se você multiplicou, somou
   ou fez qualquer cálculo além de copiar o valor, NÃO é confirmado.

IMPORTANTE — SEÇÃO ESQUADRIAS (quando presente nos dados):
Cada linha tem o formato "NOME: N un | ~Wm × Hm = Xm²". Isso é DADO ESTRUTURADO
de portas/janelas com dimensão REAL extraída do CAD. Use para:
   - Gerar item de portas/janelas com a quantidade e dimensão exatas
   - Aplicar regra TCPO: se área ≤ 2m², NÃO descontar esse vão da pintura;
     se > 2m², descontar o excedente (área_vão - 2m²) da pintura adjacente
   - Toda esquadria extraída aqui pode ser marcada "confirmado" (veio de medição)

2. "estimado" — para todo o resto, SEM EXCEÇÃO:
   - Quantidades derivadas de texto/legenda ("demolir X" → qtd=1)
   - Itens sugeridos de práxis (administração local, limpeza final, instalação de placa)
   - Qualquer item cuja quantidade você não conseguiu ler DIRETO dos dados extraídos
   - Itens "vb" (verba) de valor único
   - Composições inferidas ("se tem drywall, precisa de montante" sem count no CAD)

REGRA DE OURO: **NA DÚVIDA, MARQUE "estimado".** É preferível 100 itens laranja que o
usuário confirma um a um, do que 1 item branco com número inventado. O usuário quer
poder confiar que "branco = aprovado direto", então só marque branco quando não houver
NENHUMA dúvida.

Não existe "verificar" nesta fase — use "estimado" pra qualquer incerteza.

════════════════════════════════════════════════════════
REGRA DE DETERMINISMO — UM ITEM POR BLOCO ÚNICO
════════════════════════════════════════════════════════

Ao gerar os itens a partir de "CONTAGEM DE BLOCOS":
- Cada nome de bloco único = **um item só** na planilha, com a quantidade literal da contagem. Não reagrupar, não dividir, não combinar blocos diferentes.
- Se a contagem listou "lum R4 remanejada: 20 un" e "lum R4 nova: 2 un", gerar DOIS itens separados com essas quantidades exatas. NÃO inferir que "são ambos R4" e somar, nem dividir um único em sub-itens por intuição.
- Se um bloco tem nome genérico/estranho ("BLOCO1", "INSERT_0"), mantenha — marcar como estimado pra o usuário identificar.
- A descrição do item pode ser enriquecida (modelo, fabricante) mas o IDENTIFICADOR e a QUANTIDADE são literais do DXF.

Essa regra garante que subir o mesmo arquivo duas vezes retorne o MESMO resultado.

════════════════════════════════════════════════════════
UNIDADES CORRETAS — ml VS un VS m² VS vb
════════════════════════════════════════════════════════

**A unidade vem do TIPO DE DADO no DXF, não do que parece intuitivo:**
- Valor vindo de "COMPRIMENTOS POR LAYER" → **ml** (metro linear). Use o número LITERAL.
- Valor vindo de "ÁREAS HACHURADAS POR LAYER" → **m²**. Use o número LITERAL.
- Valor vindo de "CONTAGEM DE BLOCOS" → **un**. Use o número LITERAL.
- Valor vindo de "COTAS/DIMENSÕES" → **m** (metro simples). Use o número LITERAL.
- Verba sem medida clara → **vb** com quantity=0 (laranja, usuário preenche).

REGRA GERAL: a unidade vai PARTE COM O DADO EXTRAÍDO. Se você usa um valor de
"ÁREAS HACHURADAS" e coloca unidade "ml", está errado — o valor é m² por definição.

CASO ESPECIAL — lineares aparecem 2× no DXF:
- "LED LINE 45°" ou "perfil linear" podem aparecer em **CONTAGEM DE BLOCOS** (como
  "un") E em **COMPRIMENTOS POR LAYER** (como "ml"). São o mesmo item físico.
  Escolha o COMPRIMENTO (ml), não a contagem, pois é a medida útil pra orçar.
  Exemplo: "LUMINI LED LINE: 2 un" + "layer LUM-LINE: 23.24 m" → gera item com
  ml=23.24 (não un=2).
- Rodapés, tabicas, eletrocalhas, perfis: sempre ml.

PRIORIDADE SEMÂNTICA — a unidade do ITEM é definida pelo TIPO DE SERVIÇO, não só
pelo dado extraído:
- **Pisos** (carpete, cerâmica, porcelanato, vinílico, laminado, madeira) → **SEMPRE m²**
  mesmo que o dado do DXF venha como comprimento de polyline. Pisos se orçam por área.
- **Forros** (modular, gesso, ripado) → **SEMPRE m²**.
- **Pinturas e revestimentos verticais** (parede, azulejo, tijolinho, papel) → **m²**.
- **Rodapés, tabicas, soleiras, perfis, eletrocalhas, molduras** → **ml** (linear).
- **Luminárias, portas, difusores, interruptores, tomadas** → **un** (contagem).

Se o DXF te der um comprimento (em COMPRIMENTOS POR LAYER) pra uma SUPERFÍCIE
como piso/forro/pintura, esse comprimento provavelmente é o perímetro da área,
não uma medida linear pra orçar. Nesse caso, procure a área correspondente em
"ÁREAS HACHURADAS" e use m². Se não houver área hachurada, marque o item como
"estimado" com `quantity=0` e pede confirmação na observação.

════════════════════════════════════════════════════════
QUANDO MARCAR "estimado" (LARANJA)
════════════════════════════════════════════════════════

**NÃO seja tímido com "confirmado" quando o DADO EXISTE.** Se o DXF tem um
comprimento (ex.: "ARQ-DIV: 491.84 m") e você está orçando a divisória dessa
layer, use 491.84 ml como "confirmado" — é uma medição objetiva.

Você só deve marcar "estimado" (laranja) nos casos abaixo:

(a) Quantidade você INFERIU de texto/contexto, não leu direto:
    - "demolir X" → qtd=1 (texto não numérico)
    - "administração local 2 meses" (não vem do arquivo)
    - "retrofit de lâmpadas existentes" (sem contagem)
    → **quantity=0** (vazio na planilha, usuário preenche)

(b) Clara dupla contagem de áreas LEV vs FOR:
    Se "ÁREAS HACHURADAS" tem AMBOS "LEV-X: A m²" E "FOR-X: B m²" e você
    está tentando orçar o mesmo tipo, escolha apenas UM (geralmente o
    "FOR-*" / "NOV-*" / "ARQ-*" = novo projeto) e coloque confirmado.
    Se ficar em dúvida entre os dois, marque estimado.

(c) Área total > área da laje (impossível):
    Se a soma de áreas de um tipo fica > "Área construída" das PREMISSAS,
    suspeite de dupla contagem e marque estimado.

**NÃO marque estimado só por precaução em valores medidos.** Se COMPRIMENTOS
POR LAYER dá 491.84 m pra ARQ-DIV, use 491.84 confirmado. Não desconfie do
número só porque vem de soma de linhas — medir soma de linhas É a medição.

════════════════════════════════════════════════════════
LEV- vs FOR- — convenção de layers em reforma (regra B acima)
════════════════════════════════════════════════════════

Em projetos BR:
- "LEV-" = LEVANTAMENTO (existente no imóvel). Não orçar, exceto como demolição.
- "FOR-" / "NOV-" / "ARQ-" = PROJETO NOVO (a construir).
- "DEM-" = DEMOLIÇÃO.

**Se aparecerem AMBOS (LEV e FOR do mesmo tipo)**, use só o FOR/NOV.
**Se aparecer SÓ UM**, use-o (pode ser o único dado disponível).
**Nunca some LEV + FOR** — são momentos distintos (antes/depois da reforma).

════════════════════════════════════════════════════════
FORMATO DE RESPOSTA — RACIOCÍNIO EXPLÍCITO ANTES DO JSON
════════════════════════════════════════════════════════

Antes de retornar o JSON, PENSE em voz alta em 4 passos. O texto do raciocínio
é obrigatório — ele ajuda você a errar menos e ajuda o revisor humano a
confiar no resultado. Formato:

```
RACIOCÍNIO:

Passo 1 — Inventário de layers:
  Para cada LAYER relevante, uma linha:
    "<nome do layer>: <tipo de dado> — <quantidade extraída> — representa <item>"
  Exemplo: "FOR-MFR: área hachurada — 79.66 m² — forro modular novo"
  Ignore layers de anotação, xrefs e aux.

Passo 2 — Checagem de LEV vs FOR:
  Liste pares conflitantes (mesmo tipo em layer LEV e FOR).
  Para cada par, diga qual escolheu e por quê.
  Exemplo: "LEV-MFR 2150m² vs FOR-MFR 79m² — escolhi FOR-MFR (novo projeto)"

Passo 3 — Plausibilidade:
  Para cada grupo de itens, verifique se a soma faz sentido:
  - Áreas de piso/forro somadas ≤ área da laje construída
  - Contagens (un) são números inteiros
  - Comprimentos e áreas são positivos
  Se algo parece absurdo, marque estimado.

Passo 4 — Geração dos itens:
  Para cada item que vai no JSON, uma linha:
    "<descrição>: <qtd> <un> — fonte: <layer/bloco exato>"
```

Depois do raciocínio, retorne o JSON em bloco de código (```json...```):

{{
  "project_data": {{
    "name": "",
    "total_area": 0,
    "layout_area": 0,
    "workstations": 0,
    "departments": [],
    "demolition_notes": [],
    "new_rooms": [],
    "kept_elements": []
  }},
  "items": [
    {{
      "item_num": "1",
      "description": "Descrição completa",
      "unit": "m²",
      "quantity": 100,
      "observations": "Fonte: <layer/bloco/texto exato da extração>",
      "ref_sheet": "DXF",
      "confidence": "confirmado ou estimado — nunca inventar",
      "discipline": "Categoria"
    }}
  ]
}}

REGRA DA OBSERVATION: o campo "observations" deve SEMPRE citar a fonte exata
do número no DXF — ex.: "Fonte: 85 INSERTs do bloco 'lum. R5 remanejada'"
ou "Fonte: área hachurada do layer FOR-MFR = 79.66 m²". Isso permite que o
revisor humano confirme direto no arquivo."""

                    try:
                        response = dxf_client.messages.create(
                            model="claude-sonnet-4-20250514",
                            max_tokens=16000,  # aumentado pra caber raciocínio (CoT) + JSON
                            temperature=0,
                            system=SYSTEM_PROMPT,
                            messages=[{"role": "user", "content": dxf_prompt}],
                        )

                        text = response.content[0].text
                        # Parser robusto: agora o Claude pode retornar raciocínio ANTES do JSON (CoT).
                        # Tentar em ordem: bloco ```json, bloco ```, último objeto {...} do texto.
                        json_str = None
                        if "```json" in text:
                            json_str = text.split("```json")[-1].split("```")[0].strip()
                        elif "```" in text:
                            # Pegar o último bloco de código (caso tenha múltiplos)
                            parts = text.split("```")
                            if len(parts) >= 3:
                                json_str = parts[-2].strip()
                        if not json_str or not json_str.startswith("{"):
                            # Fallback: regex pra achar último JSON object "compatível" no texto
                            import re as _re_parse
                            # Matches { ... } que contém "items" ou "project_data"
                            candidates = _re_parse.findall(
                                r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}",
                                text, flags=_re_parse.DOTALL
                            )
                            for cand in reversed(candidates):
                                if '"items"' in cand or '"project_data"' in cand:
                                    json_str = cand
                                    break
                        if not json_str:
                            json_str = text.strip()

                        result = _j.loads(json_str)

                        # Extrair project_data
                        if "project_data" in result:
                            pd = result["project_data"]
                            if pd.get("total_area"): project_data.total_area = sf(pd["total_area"])
                            if pd.get("layout_area"): project_data.layout_area = sf(pd["layout_area"])
                            if pd.get("name") and not project_data.name: project_data.name = pd["name"]
                            if pd.get("demolition_notes"): project_data.demolition_notes.extend(pd["demolition_notes"])
                            if pd.get("new_rooms"): project_data.new_rooms.extend(pd["new_rooms"])
                            if pd.get("kept_elements"): project_data.kept_elements.extend(pd["kept_elements"])

                        # Extrair itens
                        for item_data in result.get("items", []):
                            try:
                                desc = item_data.get("description", "")
                                if not desc or len(desc) < 3: continue
                                discipline = item_data.get("discipline", "Complementares")
                                conf = item_data.get("confidence", "estimado")
                                if conf not in ["confirmado", "estimado", "verificar"]: conf = "estimado"
                                qty = sf(item_data.get("quantity", 0))
                                # qty=0 é permitido para itens estimados sem número concreto
                                # (virará vazio na planilha pro usuário preencher).
                                # Só forçamos qty=1 em CONFIRMADO (deveria ter número real).
                                if qty < 0:
                                    qty = 0
                                if qty == 0 and conf == "confirmado":
                                    qty = 1  # defensivo: confirmado sem número cai em vb=1

                                # Normalização pós-IA: força unidade correta pra descrição
                                # (ex.: "piso vinílico" sempre m², nunca ml).
                                original_unit = item_data.get("unit", "vb")
                                normalized_unit, unit_corrected = _normalize_unit_for_item(desc, original_unit)
                                obs_raw = item_data.get("observations", "Fonte: DXF")
                                if unit_corrected:
                                    # IA escolheu unidade inconsistente com o tipo — marcar estimado
                                    # pra usuário conferir o número
                                    conf = "estimado"
                                    obs_raw = (f"{obs_raw} | Unidade ajustada de {original_unit} "
                                               f"para {normalized_unit} (revisar quantidade)")

                                item = BudgetItem(
                                    item_num=str(item_data.get("item_num", "")),
                                    description=desc,
                                    unit=normalized_unit,
                                    quantity=qty,
                                    observations=obs_raw,
                                    ref_sheet="DXF",
                                    confidence=Confidence(conf),
                                    discipline=discipline,
                                )
                                dxf_items.append(item)
                            except: continue

                        print(f"DXF {os.path.basename(dxf_path)}: {len(result.get('items', []))} itens extraídos via Claude")

                    except Exception as e:
                        jobs.update_field(job_id, current_step=f"Erro IA (DXF): {str(e)[:200]}")
                        print(f"Erro Claude DXF: {e}")

                    del structured_text
                    gc.collect()

            except Exception as e:
                jobs.update_field(job_id, error_message=f"Erro extração DXF: {str(e)[:500]}")
                jobs.update_field(job_id, current_step=f"ERRO DXF: {str(e)[:200]}")
                import traceback
                traceback.print_exc()
                raise  # Deixar o erro aparecer

        total = len(pdf_paths)
        client = anthropic.Anthropic(api_key=api_key)
        all_items = list(dxf_items)  # Começar com itens DXF
        crops_dir = os.path.join(work_dir, "crops")
        os.makedirs(crops_dir, exist_ok=True)

        # Ordenar PDFs por prioridade (layout primeiro)
        priority = {"layout_novo": 0, "layout_atual": 1, "demolir": 2, "arquitetura": 3,
                     "forro": 4, "piso": 5, "pontos": 6, "mobiliario": 7, "marcenaria": 8, "det_forro": 9}

        pdf_infos = []
        for pdf_path in pdf_paths:
            filename = os.path.basename(pdf_path)
            sheet_type = identify_sheet_type(filename)
            pdf_infos.append((pdf_path, filename, sheet_type))

        pdf_infos.sort(key=lambda x: priority.get(x[2].value, 99))

        # Faixa de progresso reservada para PDFs: após cad_end_pct (se houver CAD) até 90%
        pdf_start_pct = cad_end_pct if has_cad else 5
        pdf_end_pct = 90
        pdf_span = pdf_end_pct - pdf_start_pct

        for i, (pdf_path, filename, sheet_type) in enumerate(pdf_infos):
            step_pct = pdf_start_pct + int((i / max(total, 1)) * pdf_span)
            jobs.update_field(job_id, progress=step_pct)
            jobs.update_field(job_id, current_step=f"Prancha {i+1}/{total}: {filename}")

            if sheet_type == SheetType.DESCONHECIDO:
                continue

            # 1. Extrair texto
            text = extract_text(pdf_path)

            # 2. Renderizar crops (1 PDF de cada vez)
            crop_paths = render_crops(pdf_path, sheet_type, crops_dir)

            # 3. Analisar com IA
            jobs.update_field(job_id, current_step=f"Prancha {i+1}/{total}: Nossa IA está analisando {filename}...")
            sheet = SheetInfo(
                filename=filename,
                sheet_type=sheet_type,
                text_content=text[:5000],
                crops=crop_paths,
            )
            result = analyze_sheet(client, sheet)

            # 4. Extrair dados do projeto
            if "project_data" in result:
                pd = result["project_data"]
                if pd.get("total_area"): project_data.total_area = sf(pd["total_area"])
                if pd.get("layout_area"): project_data.layout_area = sf(pd["layout_area"])
                if pd.get("no_intervention_area"): project_data.no_intervention_area = sf(pd["no_intervention_area"])
                if pd.get("workstations"):
                    try: project_data.workstations = int(float(str(pd["workstations"]).replace('un','').strip()))
                    except: pass
                if pd.get("departments"): project_data.departments = pd["departments"]
                if pd.get("demolition_notes"): project_data.demolition_notes.extend(pd["demolition_notes"])
                if pd.get("new_rooms"): project_data.new_rooms.extend(pd["new_rooms"])
                if pd.get("kept_elements"): project_data.kept_elements.extend(pd["kept_elements"])
                if pd.get("name") and not project_data.name: project_data.name = pd["name"]
                if pd.get("address") and not project_data.address: project_data.address = pd["address"]
                if pd.get("architect") and not project_data.architect: project_data.architect = pd["architect"]

            # 5. Extrair itens
            valid_disciplines = [
                "Serviços Preliminares", "Demolição e Remoção", "Fechamentos Verticais",
                "Revestimentos", "Pisos e Rodapés", "Forros", "Portas e Ferragens",
                "Divisórias e Vidros", "Persianas e Cortinas", "Iluminação",
                "Instalações Elétricas e Dados", "Ar-Condicionado", "Incêndio e Segurança",
                "Marcenaria", "Mobiliário", "Complementares"
            ]
            for item_data in result.get("items", []):
                try:
                    desc = item_data.get("description", "")
                    if not desc or len(desc) < 3: continue
                    discipline = item_data.get("discipline", "Complementares")
                    if discipline not in valid_disciplines: discipline = "Complementares"
                    conf = item_data.get("confidence", "estimado")
                    if conf not in ["confirmado", "estimado", "verificar"]: conf = "estimado"
                    qty_raw = item_data.get("quantity", 0)
                    qty = sf(qty_raw) if qty_raw else 0
                    # qty=0 permitido em "estimado" (usuário preenche); forçar 1 só em confirmado
                    if qty < 0:
                        qty = 0
                    if qty == 0 and conf == "confirmado":
                        qty = 1

                    # Normalização pós-IA: força unidade consistente com descrição
                    original_unit = item_data.get("unit", "vb")
                    normalized_unit, unit_corrected = _normalize_unit_for_item(desc, original_unit)
                    obs_raw = item_data.get("observations", "")
                    if unit_corrected:
                        conf = "estimado"
                        obs_raw = (f"{obs_raw} | Unidade ajustada de {original_unit} "
                                   f"para {normalized_unit}").strip(" |")

                    item = BudgetItem(
                        item_num=str(item_data.get("item_num", "")),
                        description=desc,
                        unit=normalized_unit,
                        quantity=qty,
                        observations=obs_raw,
                        ref_sheet=item_data.get("ref_sheet", f"Pr.{filename[:7]}"),
                        confidence=Confidence(conf),
                        discipline=discipline,
                    )
                    all_items.append(item)
                except: continue

            # 6. Liberar memória desta prancha
            del text, crop_paths, sheet, result
            gc.collect()

        # ── Consolidação pós-IA ──
        jobs.update_field(job_id, progress=91)
        # Remove duplicatas similares (ex.: "alvenaria nova" × 4 pranchas com
        # mesma qty 491.84 ml), consolida réplicas por departamento (painel
        # 0.72m² × 16 deptos) e valida un=inteiro (corrige "un=222.11").
        jobs.update_field(job_id, current_step="Consolidando itens duplicados...")
        n_before = len(all_items)
        all_items = _consolidate_items(all_items)
        # Validar qty/unit após consolidação
        for it in all_items:
            new_qty, adjusted = _validate_quantity_for_unit(it)
            if adjusted:
                it.quantity = new_qty
                try:
                    from models import Confidence
                    it.confidence = Confidence("estimado")
                except Exception:
                    pass
                it.observations = (
                    (it.observations or "") +
                    " | Qty de un ajustada: valor original não-inteiro"
                ).strip(" |")
        n_after = len(all_items)
        if n_before != n_after:
            print(f"[consolidação] {n_before} → {n_after} itens ({n_before - n_after} consolidados)")

        # ── Validação de plausibilidade ──
        # Detecta disciplina×unidade mismatch, range absurdo, área > laje×1.5.
        # Marca estimado (laranja) e anota o motivo pra usuário revisar.
        jobs.update_field(job_id, current_step="Validando plausibilidade dos itens...")
        flagged_count = 0
        laje_area = project_data.total_area or 0
        for it in all_items:
            plausible, reason = _check_plausibility(it, laje_area)
            if not plausible:
                try:
                    from models import Confidence
                    it.confidence = Confidence("estimado")
                except Exception:
                    pass
                it.observations = (
                    (it.observations or "") + f" | ⚠ Revisar: {reason}"
                ).strip(" |")
                flagged_count += 1
        if flagged_count > 0:
            print(f"[plausibilidade] {flagged_count} itens flagados pra revisão")

        # ── Calibração por DENSIDADE (ratios qty/área) ──
        # Compara a densidade (qty/área) de cada item contra benchmarks
        # agregados de projetos históricos (mesma tipologia). Desvio > ±2σ
        # vira observação laranja. NUNCA promove pra confirmado.
        # Área de referência: layout_area se disponível, senão total_area.
        ref_area = project_data.layout_area or project_data.total_area or 0
        if HAS_DENSITY_CAL and ref_area > 0:
            try:
                from density_calibration import check_density_anomaly
                benchmarks = density_get_benchmarks(typology=typology)
                density_flagged = 0
                for it in all_items:
                    is_anom, reason = check_density_anomaly(
                        it, ref_area, benchmarks=benchmarks, typology=typology,
                    )
                    if is_anom:
                        try:
                            from models import Confidence
                            it.confidence = Confidence("estimado")
                        except Exception:
                            pass
                        it.observations = (
                            (it.observations or "") + f" | ⚠ Calibração: {reason}"
                        ).strip(" |")
                        density_flagged += 1
                if density_flagged > 0:
                    print(f"[densidade] {density_flagged} itens fora do padrão histórico")
            except Exception as e:
                print(f"[densidade] Erro no check de anomalia: {e}")

        # Gerar planilha
        jobs.update_field(job_id, progress=92)
        jobs.update_field(job_id, current_step=f"Gerando planilha com {len(all_items)} itens...")

        # Normalizar nome do projeto: quando há múltiplos arquivos, evitar
        # que o project.name inferido da IA (que geralmente pega o nome do
        # primeiro DXF) dê uma impressão errada de "projeto de só uma coisa".
        # Sempre sobrescreve quando >1 arquivo, pois a IA processa um por vez
        # e escolhe o nome do que viu primeiro.
        if len(file_paths) > 1:
            project_data.name = f"Quantitativos — {len(file_paths)} arquivos processados"

        output_path = os.path.join(work_dir, f"orcamento_{job_id}.xlsx")
        generate_spreadsheet(project_data, all_items, output_path)

        # Persistir no Supabase Storage pra sobreviver redeploy do Render
        # (o /tmp do dyno é volátil — sem isso, agente e download quebram).
        _storage_ok = _supabase_storage_upload(output_path, f"{job_id}.xlsx")
        print(f"[storage] upload {job_id}.xlsx ok={_storage_ok}")

        jobs.update_field(job_id, progress=100)
        jobs.update_field(job_id, status="done")
        jobs.update_field(job_id, current_step="Concluído!")
        jobs.update_field(job_id, download_url=f"/api/download/{job_id}")

        # Atualizar projeto no Supabase (log explícito do resultado pra rastrear
        # falhas que antes passavam silenciosas)
        _supa_ok = _supabase_update("projects", "job_id", job_id, {
            "status": "done",
            "items_count": len(all_items),
            "total_area": project_data.total_area if project_data.total_area else None,
            "layout_area": project_data.layout_area if project_data.layout_area else None,
            "completed_at": datetime.utcnow().isoformat(),
        })
        print(f"[supabase] update job={job_id} status=done items={len(all_items)} "
              f"total_area={project_data.total_area} layout_area={project_data.layout_area} "
              f"ok={_supa_ok}")

    except Exception as e:
        jobs.update_field(job_id, status="error")
        jobs.update_field(job_id, error_message=str(e))
        jobs.update_field(job_id, current_step=f"Erro: {str(e)[:200]}")

        # Atualizar erro no Supabase
        _supabase_update("projects", "job_id", job_id, {
            "status": "error",
            "error_message": str(e)[:500],
        })


@app.get("/")
async def root():
    return {"service": "AI.arq API", "version": "1.0.0", "status": "online"}


_VALID_TYPOLOGIES = {"office", "residential", "retail", "hospital", "educational"}


@app.post("/api/process")
async def process_files(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    typology: str = "office",
    project_name: str = "",
):
    """Recebe PDF, DWG ou DXF e inicia processamento em background.

    - `typology` (opcional, default `office`): usado pela calibração por
      densidade pra comparar o projeto com padrões da mesma categoria.
    - `project_name` (opcional): apelido amigável dado pelo cliente.
    """
    if typology not in _VALID_TYPOLOGIES:
        typology = "office"
    if not files:
        raise HTTPException(400, "Nenhum arquivo enviado")

    # Validar arquivos (aceitar PDF, DWG e DXF)
    valid_extensions = ('.pdf', '.dwg', '.dxf')
    valid_files = [f for f in files if f.filename and f.filename.lower().endswith(valid_extensions)]
    if not valid_files:
        raise HTTPException(400, "Nenhum arquivo válido encontrado. Aceito: PDF, DWG ou DXF.")

    if len(valid_files) > 50:
        raise HTTPException(400, "Máximo de 50 arquivos por projeto")

    # Criar job
    job_id = str(uuid.uuid4())[:8]
    work_dir = os.path.join(WORK_DIR, job_id)
    os.makedirs(work_dir, exist_ok=True)

    # Salvar arquivos
    file_paths = []
    file_types = {'pdf': 0, 'dwg': 0, 'dxf': 0}
    for upload_file in valid_files:
        file_path = os.path.join(work_dir, upload_file.filename)
        with open(file_path, "wb") as f:
            content = await upload_file.read()
            f.write(content)
        file_paths.append(file_path)
        ext = upload_file.filename.lower().rsplit('.', 1)[-1]
        file_types[ext] = file_types.get(ext, 0) + 1

    # Resumo de tipos recebidos
    types_summary = ", ".join(f"{v} {k.upper()}" for k, v in file_types.items() if v > 0)

    # Criar status
    jobs[job_id] = ProcessingStatus(
        job_id=job_id,
        status="queued",
        progress=0,
        current_step=f"Recebidos {len(file_paths)} arquivos ({types_summary}). Iniciando processamento...",
        total_steps=3,
    )

    # Salvar projeto no Supabase
    # Pegar user_id/email do header Authorization (se enviado pelo frontend)
    from fastapi import Request
    user_id = ""
    user_email = ""
    user_name = ""
    # Os dados do usuário vêm como query params opcionais
    _supabase_insert("projects", {
        "job_id": job_id,
        "user_id": user_id or "anonymous",
        "user_email": user_email,
        "user_name": user_name,
        "project_name": project_name or "Sem nome",
        "typology": typology,
        "files_count": len(file_paths),
        "file_types": file_types,
        "status": "queued",
    })

    # Iniciar processamento em thread separada (não bloqueia HTTP)
    import threading
    t = threading.Thread(
        target=process_job,
        args=(job_id, file_paths, work_dir),
        kwargs={"typology": typology},
        daemon=True,
    )
    t.start()

    return {"job_id": job_id, "files_received": len(file_paths),
            "file_types": file_types, "status": "queued", "typology": typology}


@app.get("/api/debug/supa-log")
async def debug_supa_log(tail: int = 50):
    """Últimas N linhas do log de operações Supabase — pra investigar por que
    updates silenciosos falham sem ter acesso direto ao log do Render."""
    try:
        if not os.path.exists(_SUPA_LOG_PATH):
            return {"status": "ok", "lines": [], "note": "log vazio ou ainda não criado"}
        with open(_SUPA_LOG_PATH, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        last = all_lines[-tail:] if tail > 0 else all_lines
        return {"status": "ok", "total_lines": len(all_lines),
                "returned": len(last), "lines": [ln.rstrip("\n") for ln in last]}
    except Exception as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}


@app.get("/api/debug/dwg")
async def debug_dwg():
    """Diagnóstico do suporte DWG."""
    import shutil
    result = {
        "oda_which": shutil.which("ODAFileConverter"),
        "oda_paths_checked": [],
    }
    # Verificar caminhos
    for p in ["/usr/bin/ODAFileConverter", "/usr/local/bin/ODAFileConverter",
              "/opt/ODAFileConverter/ODAFileConverter"]:
        result["oda_paths_checked"].append({"path": p, "exists": os.path.exists(p)})

    # Tentar importar dwg_extractor
    try:
        from dwg_extractor import _find_oda_converter, extract_from_file
        result["dwg_extractor_import"] = True
        oda = _find_oda_converter()
        result["oda_found_by_extractor"] = oda
    except Exception as e:
        result["dwg_extractor_import"] = False
        result["dwg_extractor_error"] = str(e)

    # Listar binários ODA
    try:
        import subprocess
        find_result = subprocess.run(["find", "/", "-name", "ODAFileConverter*", "-type", "f"],
                                     capture_output=True, text=True, timeout=5)
        result["oda_files_found"] = find_result.stdout.strip().split("\n") if find_result.stdout.strip() else []
    except:
        result["oda_files_found"] = "find failed"

    return result


@app.get("/api/debug/oda-log/{job_id}")
async def get_oda_log(job_id: str):
    """Retorna o log do ODA File Converter para um job."""
    log_path = os.path.join(WORK_DIR, job_id, "_oda_log.txt")
    if os.path.exists(log_path):
        with open(log_path, 'r') as f:
            return {"log": f.read()}
    return {"log": "Log não encontrado", "path_checked": log_path}


@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    """Retorna o status de processamento de um job."""
    if job_id not in jobs:
        raise HTTPException(404, "Job não encontrado")
    return jobs[job_id]


@app.get("/api/download/{job_id}")
async def download_file(job_id: str):
    """Baixa a planilha gerada. Tenta cache local primeiro; se sumiu
    (Render redeploy), busca no Supabase Storage."""
    # Suaviza a checagem de job — se o JSON foi limpo no restart mas o
    # arquivo está no Storage, ainda servimos pra não perder o cliente.
    output_path = get_planilha_path(job_id)
    if not output_path:
        raise HTTPException(404, "Planilha não encontrada (nem em cache nem no Storage)")

    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"quantitativos_aiarq_{job_id}.xlsx",
    )


@app.get("/api/health")
async def health():
    """Health check com métricas do sistema."""
    try:
        import psutil
    except ImportError:
        psutil = None
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    stripe_key = os.getenv("STRIPE_SECRET_KEY", "")

    # Métricas de sistema
    if psutil:
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
    else:
        mem = None
        disk = None

    # Contar projetos hoje
    today_count = 0
    try:
        import urllib.request, json
        url = f"{SUPABASE_URL}/rest/v1/projects?select=id&created_at=gte.{datetime.utcnow().strftime('%Y-%m-%d')}T00:00:00"
        req = urllib.request.Request(url)
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req.add_header('Prefer', 'count=exact')
        resp = urllib.request.urlopen(req, timeout=3)
        count_header = resp.headers.get('content-range', '')
        if '/' in count_header:
            today_count = int(count_header.split('/')[1])
        else:
            today_count = len(json.loads(resp.read()))
    except:
        pass

    # Contar totais
    total_projects = 0
    total_users = 0
    try:
        import urllib.request, json
        for table, var_name in [('projects', 'total_projects'), ('profiles', 'total_users')]:
            url = f"{SUPABASE_URL}/rest/v1/{table}?select=id"
            req = urllib.request.Request(url)
            req.add_header('apikey', SUPABASE_KEY)
            req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
            req.add_header('Prefer', 'count=exact')
            resp = urllib.request.urlopen(req, timeout=3)
            count_header = resp.headers.get('content-range', '')
            if '/' in count_header:
                locals()[var_name] = int(count_header.split('/')[1])
            else:
                locals()[var_name] = len(json.loads(resp.read()))
    except:
        pass

    return {
        "status": "healthy",
        "api_key_configured": bool(api_key and api_key.startswith("sk-")),
        "stripe_configured": bool(stripe_key),
        "timestamp": datetime.utcnow().isoformat(),
        "system": {
            "ram_used_pct": round(mem.percent, 1) if mem else 0,
            "ram_used_mb": round(mem.used / 1024 / 1024) if mem else 0,
            "ram_total_mb": round(mem.total / 1024 / 1024) if mem else 0,
            "disk_used_pct": round(disk.percent, 1) if disk else 0,
            "cpu_pct": psutil.cpu_percent(interval=0.5) if psutil else 0,
        },
        "stats": {
            "projects_today": today_count,
            "total_projects": total_projects,
            "total_users": total_users,
        },
        "features": {
            "pdf": True,
            "dxf": True,
            "dwg": shutil.which("ODAFileConverter") is not None,
            "calibrator": HAS_CALIBRATOR if 'HAS_CALIBRATOR' in dir() else False,
        }
    }


# ── STRIPE CHECKOUT ──
@app.post("/api/checkout")
async def create_checkout(num_files: int = 1):
    """Cria sessão de pagamento no Stripe."""
    import stripe
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    if not stripe.api_key:
        raise HTTPException(500, "Stripe não configurado")

    # Definir preço por quantidade de pranchas
    if num_files <= 5:
        price_cents = 9700  # R$ 97
        plan_name = "Projeto Pequeno (até 5 pranchas)"
    elif num_files <= 10:
        price_cents = 19700  # R$ 197
        plan_name = "Projeto Médio (6-10 pranchas)"
    else:
        price_cents = 39700  # R$ 397
        plan_name = "Projeto Grande (11+ pranchas)"

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card", "pix"],
            line_items=[{
                "price_data": {
                    "currency": "brl",
                    "product_data": {
                        "name": f"AI.arq — {plan_name}",
                        "description": f"Planilha de quantitativos para {num_files} pranchas",
                    },
                    "unit_amount": price_cents,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url="https://ai.arq.br/dashboard.html?payment=success&session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://ai.arq.br/dashboard.html?payment=cancelled",
        )
        return {"checkout_url": session.url, "session_id": session.id}
    except Exception as e:
        raise HTTPException(500, f"Erro ao criar checkout: {str(e)}")


@app.get("/api/checkout/verify/{session_id}")
async def verify_payment(session_id: str):
    """Verifica se o pagamento foi concluído."""
    import stripe
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        return {
            "paid": session.payment_status == "paid",
            "status": session.payment_status,
            "amount": session.amount_total,
        }
    except Exception as e:
        raise HTTPException(404, f"Sessão não encontrada: {str(e)}")


# ── CALIBRATION ENDPOINTS ──

@app.post("/api/cashback/upload")
async def cashback_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    job_id: str = "",
):
    """Cashback: recebe a planilha revisada do cliente e alimenta os
    benchmarks de densidade da mesma tipologia.

    A tipologia e a área de referência são resolvidas consultando o
    projeto no Supabase. A lógica é a mesma da ingestão do admin —
    o sistema aprende **proporções típicas** (qty/m²) e apenas
    alerta sobre anomalias em projetos futuros. Nunca copia valores
    absolutos entre projetos.
    """
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Arquivo deve ser .xlsx")
    if not job_id:
        raise HTTPException(400, "job_id é obrigatório")
    if not HAS_DENSITY_CAL:
        raise HTTPException(500, "Módulo density_calibration não carregado")

    project = _get_project_from_supabase(job_id)
    if not project:
        raise HTTPException(404, f"Projeto não encontrado pro job_id={job_id}")

    typology = project.get("typology") or "office"
    ref_area = project.get("layout_area") or project.get("total_area") or 0
    try:
        ref_area = float(ref_area or 0)
    except Exception:
        ref_area = 0
    if ref_area <= 0:
        raise HTTPException(
            400,
            "Projeto não tem área de referência (layout_area ou total_area) — "
            "ainda não foi possível computar a área pelo DWG. "
            "Aguarde o processamento terminar completamente antes de enviar a revisão.",
        )

    label = (project.get("project_name") or f"job_{job_id}")[:100]

    tmp_dir = os.path.join(WORK_DIR, "_density_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    revised_path = os.path.join(tmp_dir, f"cashback_{job_id}_{file.filename}")
    try:
        content = await file.read()
        with open(revised_path, "wb") as f:
            f.write(content)

        from density_calibration import ingest_budget as _ingest
        summary = _ingest(
            revised_path, area_m2=ref_area, typology=typology, project_label=label,
        )
        return {
            "status": "ok",
            "source": "cashback",
            "job_id": job_id,
            "typology": typology,
            "area_m2": ref_area,
            "project_label": label,
            "items_parsed": summary.get("items_parsed", 0),
            "benchmarks_updated": summary.get("benchmarks_updated", 0),
            "new_item_types": summary.get("new_item_types", 0),
            # Legacy fields for UI compat (dashboard shows these)
            "items_compared": summary.get("items_parsed", 0),
            "items_saved": summary.get("benchmarks_updated", 0),
            "avg_deviation_pct": 0,
            "cashback_granted": True,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erro na ingestão da revisão: {str(e)}")
    finally:
        if os.path.exists(revised_path):
            try:
                os.remove(revised_path)
            except Exception:
                pass


# Endpoints /api/calibration/manual e /api/calibration/factors foram removidos
# porque alimentavam o modelo de "fator absoluto" (correction_factor = real/ai),
# que contraria a regra de isolamento de projetos. A mesma ingestão agora é
# feita via /api/calibration/ingest (admin) e /api/cashback/upload (cliente),
# que aprendem RATIOS de densidade (qty/m²) por tipologia e só geram alertas.


# ═══════════════════════════════════════════════
#  Calibração por DENSIDADE (ratios qty/área)
#  — regra: aprende padrões proporcionais pra ALERTAR anomalias,
#  nunca copia valores absolutos entre projetos.
# ═══════════════════════════════════════════════

try:
    from density_calibration import (
        ingest_budget as density_ingest_budget,
        get_benchmarks as density_get_benchmarks,
    )
    HAS_DENSITY_CAL = True
except ImportError:
    HAS_DENSITY_CAL = False
    print("density_calibration.py não disponível — calibração por densidade desativada")


@app.post("/api/calibration/ingest")
async def calibration_ingest_density(
    xlsx: UploadFile = File(...),
    area_m2: float = 0,
    typology: str = "office",
    project_label: str = "",
):
    """Ingere um orçamento-fonte histórico pra enriquecer os benchmarks
    de densidade. `area_m2` é a área de referência do projeto-fonte (layout
    ou laje) usada pra computar qty/área por item.

    Benchmarks são agregados por (typology, item_type, unit) — projetos
    novos só recebem ALERTAS, nunca valores copiados.
    """
    if not HAS_DENSITY_CAL:
        raise HTTPException(500, "Módulo density_calibration não carregado")
    if area_m2 <= 0:
        raise HTTPException(400, "area_m2 deve ser > 0 (área de referência do projeto-fonte)")
    if not typology or len(typology) < 3:
        raise HTTPException(400, "typology obrigatória (ex.: 'office', 'residential')")

    tmp_dir = os.path.join(WORK_DIR, "_density_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    xlsx_path = os.path.join(tmp_dir, f"ingest_{xlsx.filename}")
    try:
        content = await xlsx.read()
        with open(xlsx_path, "wb") as f:
            f.write(content)

        label = project_label or xlsx.filename
        summary = density_ingest_budget(
            xlsx_path, area_m2=area_m2, typology=typology,
            project_label=label,
        )
        return {"status": "ok", "area_m2": area_m2, "typology": typology,
                "project_label": label, **summary}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erro na ingestão: {str(e)}")
    finally:
        if os.path.exists(xlsx_path):
            try:
                os.remove(xlsx_path)
            except Exception:
                pass


def _get_project_from_supabase(job_id: str) -> dict:
    """Busca um projeto pelo job_id — usado pelo cashback pra resolver
    typology + área do projeto revisado."""
    try:
        import urllib.request, json as _json
        url = f"{SUPABASE_URL}/rest/v1/projects?job_id=eq.{job_id}&select=*"
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("Accept", "application/json")
        resp = urllib.request.urlopen(req, timeout=8)
        rows = _json.loads(resp.read().decode("utf-8"))
        return rows[0] if rows else {}
    except Exception as e:
        print(f"Supabase select project error: {e}")
        return {}


@app.post("/api/calibration/ingest-from-review")
async def calibration_ingest_from_review(
    xlsx: UploadFile = File(...),
    job_id: str = "",
):
    """Cashback: cliente sobe a planilha revisada do próprio projeto e o
    backend alimenta os benchmarks de densidade da mesma tipologia. Nunca
    copia valores absolutos pra outros projetos — só aprende proporções
    típicas pra sinalizar anomalias futuras.

    Resolve tipologia + área consultando o `projects` no Supabase pelo
    `job_id` do projeto original.
    """
    if not HAS_DENSITY_CAL:
        raise HTTPException(500, "Módulo density_calibration não carregado")
    if not job_id:
        raise HTTPException(400, "job_id obrigatório")

    project = _get_project_from_supabase(job_id)
    if not project:
        raise HTTPException(404, f"Projeto não encontrado pro job_id={job_id}")

    typology = project.get("typology") or "office"
    ref_area = project.get("layout_area") or project.get("total_area") or 0
    try:
        ref_area = float(ref_area or 0)
    except Exception:
        ref_area = 0
    if ref_area <= 0:
        raise HTTPException(
            400,
            "Projeto não tem área de referência (layout_area ou total_area). "
            "A calibração precisa da área pra computar densidades.",
        )

    label = (project.get("project_name") or f"job_{job_id}")[:100]

    tmp_dir = os.path.join(WORK_DIR, "_density_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    xlsx_path = os.path.join(tmp_dir, f"review_{job_id}_{xlsx.filename}")
    try:
        content = await xlsx.read()
        with open(xlsx_path, "wb") as f:
            f.write(content)

        from density_calibration import ingest_budget as _ingest
        summary = _ingest(
            xlsx_path, area_m2=ref_area, typology=typology, project_label=label,
        )
        return {
            "status": "ok",
            "source": "cashback",
            "job_id": job_id,
            "typology": typology,
            "area_m2": ref_area,
            "project_label": label,
            **summary,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erro na ingestão da revisão: {str(e)}")
    finally:
        if os.path.exists(xlsx_path):
            try:
                os.remove(xlsx_path)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════
#  Agente "tira-dúvidas" — Q&A sobre uma planilha gerada
# ═══════════════════════════════════════════════════════════════

@app.post("/api/agent/ask")
async def agent_ask(job_id: str, question: str = ""):
    """Cliente faz uma pergunta sobre o orçamento de UM job. O agente
    investiga (lê planilha, busca itens, lê DXFs, checa calibração) e
    responde em linguagem natural com referências aos itens.

    Body: pode mandar `question` por query string ou JSON.
    """
    if not job_id:
        raise HTTPException(400, "job_id obrigatório")
    if not question or len(question.strip()) < 2:
        raise HTTPException(400, "pergunta vazia")
    try:
        from agent import ask
        result = ask(job_id=job_id, question=question.strip())
        return {"status": "ok", **result}
    except Exception as e:
        raise HTTPException(500, f"Erro do agente: {type(e).__name__}: {e}")


@app.get("/api/agent/conversations")
async def agent_conversations(job_id: Optional[str] = None, limit: int = 50):
    """Lista conversas do agente — usado pelo admin pra acompanhar uso."""
    try:
        import urllib.request as _ur
        query = f"select=*&order=created_at.desc&limit={int(limit)}"
        if job_id:
            query += f"&job_id=eq.{_ur.quote(job_id)}"
        url = f"{SUPABASE_URL}/rest/v1/agent_conversations?{query}"
        req = _ur.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("Accept", "application/json")
        resp = _ur.urlopen(req, timeout=10)
        rows = _json.loads(resp.read().decode("utf-8"))
        return {"status": "ok", "count": len(rows), "conversations": rows}
    except Exception as e:
        raise HTTPException(500, f"Erro ao listar conversas: {str(e)}")


@app.get("/api/agent/stats")
async def agent_stats():
    """Estatísticas agregadas do uso do agente — pra dashboard admin."""
    try:
        import urllib.request as _ur
        url = (f"{SUPABASE_URL}/rest/v1/rpc/agent_stats_summary")
        # Fallback: faz a agregação aqui via select básico
        url = (f"{SUPABASE_URL}/rest/v1/agent_conversations"
               "?select=id,iterations,duration_ms,error,job_id,created_at")
        req = _ur.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("Accept", "application/json")
        resp = _ur.urlopen(req, timeout=10)
        rows = _json.loads(resp.read().decode("utf-8"))
        total = len(rows)
        with_error = sum(1 for r in rows if r.get("error"))
        unique_jobs = len({r.get("job_id") for r in rows if r.get("job_id")})
        durations = [r.get("duration_ms") or 0 for r in rows]
        avg_dur = int(sum(durations)/len(durations)) if durations else 0
        avg_iter = (sum(r.get("iterations") or 0 for r in rows) / total) if total else 0
        return {
            "status": "ok",
            "total_conversations": total,
            "unique_jobs": unique_jobs,
            "errors": with_error,
            "avg_duration_ms": avg_dur,
            "avg_iterations": round(avg_iter, 2),
        }
    except Exception as e:
        raise HTTPException(500, f"Erro stats: {str(e)}")


@app.post("/api/calibration/reclassify-raws")
async def calibration_reclassify_raws(
    typology: Optional[str] = None,
    limit: Optional[int] = None,
    only_unclassified: bool = True,
):
    """Classifica linhas raw existentes via LLM e recompila benchmarks.

    Útil pra "ativar" raws antigos ingeridos antes do classificador
    existir. Idempotente: por padrão só toca raws sem familia_id.

    Cada raw vira ~3s (chamada Claude Haiku). Lote de 264 leva ~10min
    e custa ~$0.50. Use `limit` pra testar incrementalmente.
    """
    if not HAS_DENSITY_CAL:
        raise HTTPException(500, "Módulo density_calibration não carregado")
    try:
        from density_calibration import reclassify_raws
        result = reclassify_raws(
            typology=typology, limit=limit, only_unclassified=only_unclassified,
        )
        return {"status": "ok", **result}
    except Exception as e:
        raise HTTPException(500, f"Erro na reclassificação: {str(e)}")


@app.get("/api/calibration/benchmarks")
async def calibration_benchmarks(typology: Optional[str] = None):
    """Lista os benchmarks de densidade agregados (mean ± stddev por
    tipologia × item_type × unit). Usado pelo admin pra auditar os
    padrões aprendidos."""
    if not HAS_DENSITY_CAL:
        raise HTTPException(500, "Módulo density_calibration não carregado")
    try:
        raw = density_get_benchmarks(typology=typology)
        rows = []
        for (item_type, unit), data in raw.items():
            rows.append({
                "typology": data.get("typology"),
                "item_type": item_type,
                "unit": unit,
                "mean": data.get("mean"),
                "stddev": data.get("stddev"),
                "min_value": data.get("min_value"),
                "max_value": data.get("max_value"),
                "n_projects": data.get("n_projects"),
            })
        rows.sort(key=lambda r: (-(r["n_projects"] or 0), r["item_type"]))
        return {"status": "ok", "count": len(rows), "benchmarks": rows}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar benchmarks: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
# Trigger autodeploy Mon Apr 13 10:58:57     2026
