# -*- coding: utf-8 -*-
"""API Backend AI.arq — Processamento de pranchas de arquitetura."""
import os
import uuid
import shutil
import asyncio
import tempfile
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
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
# Env vars recomendados no Render: SUPABASE_URL, SUPABASE_KEY (ou SUPABASE_ANON_KEY)
# Fallbacks hardcoded temporários — remover após confirmar env vars em produção.
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://kqjabzwgbfuivzlcfvvu.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
if not SUPABASE_KEY:
    print("[WARN] SUPABASE_KEY não configurado no ambiente — usando fallback hardcoded (remover em breve)")
    SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtxamFiendnYmZ1aXZ6bGNmdnZ1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYwMDg5NzcsImV4cCI6MjA5MTU4NDk3N30.48xSenZlDV0LfD94ZxwGvX41Kf9Je2n-ouZpJrrCSKI"

# Email do admin (tem acesso a /api/admin/*). Pode ser overridado por env.
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "zarelalopes@gmail.com").lower()

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
    """Atualiza registro no Supabase via REST API.

    IMPORTANTE: pra table='projects' com match_field='job_id', usa RPC
    `update_project_status` (SECURITY DEFINER) que bypassa RLS. Sem isso, o
    PATCH volta 200 OK mas 0 rows afetadas — causa do bug silencioso onde
    projetos de usuários logados ficavam 'queued' pra sempre no admin mesmo
    com processamento concluído."""
    import urllib.request, urllib.error, json

    # Caminho especial: atualizar projects por job_id via RPC.
    # Roteia conforme os campos sendo atualizados:
    # - meta editável (project_name/typology/address/phase) → update_project_meta
    # - status/area/warnings/etc → update_project_status (legado)
    if table == "projects" and match_field == "job_id":
        if any(k in _META_FIELDS for k in data.keys()):
            return _rpc_update_project_meta(match_value, data)
        return _rpc_update_project_status(match_value, data)

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
#  AUTH HELPERS — JWT do Supabase para admin e ownership
# ═══════════════════════════════════════════════════════════════

def _get_user_from_request(request):
    """Valida header Authorization: Bearer <jwt> contra /auth/v1/user do Supabase.

    Retorna dict com {"id", "email"} se válido, ou None se inválido/ausente."""
    import urllib.request, urllib.error, json as _j
    try:
        auth_header = request.headers.get("Authorization", "") or request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return None
        token = auth_header[7:].strip()
        if not token:
            return None
        url = f"{SUPABASE_URL}/auth/v1/user"
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {token}")
        resp = urllib.request.urlopen(req, timeout=10)
        data = _j.loads(resp.read().decode("utf-8"))
        uid = data.get("id")
        email = (data.get("email") or "").lower()
        if not uid:
            return None
        return {"id": uid, "email": email}
    except Exception as _e:
        _supa_log(f"AUTH validate fail: {type(_e).__name__}: {_e}")
        return None


def _require_admin(request):
    """Valida JWT + email == ADMIN_EMAIL. Raise HTTPException se falha.

    Retorna o dict do usuário em caso de sucesso."""
    user = _get_user_from_request(request)
    if not user:
        raise HTTPException(401, "Autenticação requerida (Bearer token ausente ou inválido)")
    if user.get("email", "").lower() != ADMIN_EMAIL:
        raise HTTPException(403, "Acesso restrito a administradores")
    return user


def _get_project_owner(job_id: str):
    """Retorna o user_id registrado no projeto (ou None se não existe)."""
    import urllib.request, urllib.error, json as _j
    try:
        url = f"{SUPABASE_URL}/rest/v1/projects?job_id=eq.{job_id}&select=user_id"
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        resp = urllib.request.urlopen(req, timeout=10)
        rows = _j.loads(resp.read().decode("utf-8"))
        if not rows:
            return None
        return rows[0].get("user_id") or "anonymous"
    except Exception:
        return None


def _require_project_owner(request, job_id: str):
    """Valida que quem chamou é dono do projeto.

    Regra de retrocompat:
    - Projeto com user_id='anonymous' (ou vazio/null): libera acesso sem JWT.
    - Projeto com user_id real: exige JWT válido e user.id == project.user_id.
      JWT inválido → 401; válido mas não dono → 403.

    Admin (ADMIN_EMAIL) tem acesso a qualquer projeto.
    Retorna o user_id do projeto."""
    owner = _get_project_owner(job_id)
    if owner is None:
        raise HTTPException(404, "Projeto não encontrado")

    # Projetos anônimos: livres
    if not owner or owner == "anonymous":
        return owner

    # Projetos de usuário logado: exigem JWT
    user = _get_user_from_request(request)
    if not user:
        raise HTTPException(401, "Autenticação requerida para acessar este projeto")
    # Admin liberado
    if user.get("email", "").lower() == ADMIN_EMAIL:
        return owner
    if user.get("id") != owner:
        raise HTTPException(403, "Acesso restrito ao dono do projeto")
    return owner


_DISCIPLINE_TO_SECTION = {
    "Serviços Preliminares":       "1. Serviços Preliminares",
    "Demolição e Remoção":         "2. Demolição e Remoção",
    "Fechamentos Verticais":       "3. Fechamentos Verticais",
    "Revestimentos":               "4. Revestimentos",
    "Pisos e Rodapés":             "5. Pisos e Rodapés",
    "Forros":                      "6. Forros",
    "Iluminação":                  "7. Iluminação",
    "Instalações Elétricas e Dados":"8. Instalações Elétricas e Dados",
    "Instalações Hidráulicas":     "9. Instalações Hidráulicas",
    "Instalações de Gás":          "10. Instalações de Gás",
    "Ar-Condicionado":             "11. Ar-Condicionado",
    "Incêndio e Segurança":        "12. Incêndio e Segurança",
    "Portas e Ferragens":          "13. Portas e Ferragens",
    "Divisórias e Vidros":         "14. Divisórias e Vidros",
    "Persianas e Cortinas":        "15. Persianas e Cortinas",
    "Marcenaria":                  "16. Marcenaria",
    "Mobiliário":                  "17. Mobiliário",
    "Complementares":              "18. Complementares",
}


def _persist_items_to_supabase(job_id: str, items: list) -> int:
    """Insere cada BudgetItem como row em project_items.
    Permite revisão inline no navegador via endpoint /api/items/{job_id}.
    Retorna quantos foram persistidos com sucesso."""
    import urllib.request, urllib.error, json

    rows = []
    for idx, it in enumerate(items):
        disc = getattr(it, "discipline", "") or "Complementares"
        section = _DISCIPLINE_TO_SECTION.get(disc, f"99. {disc}")
        rows.append({
            "job_id": job_id,
            "item_num": str(getattr(it, "item_num", "") or ""),
            "description": (getattr(it, "description", "") or "")[:500],
            "unit": (getattr(it, "unit", "") or "vb")[:20],
            "quantity": float(getattr(it, "quantity", 0) or 0),
            "observations": (getattr(it, "observations", "") or "")[:1000],
            "ref_sheet": (getattr(it, "ref_sheet", "") or "")[:200],
            "confidence": str(getattr(getattr(it, "confidence", None), "value", "estimado"))
                          if hasattr(getattr(it, "confidence", None), "value")
                          else str(getattr(it, "confidence", "estimado") or "estimado"),
            "discipline": disc,
            "section": section,
            "sort_order": idx,
        })

    if not rows:
        _supa_log(f"PERSIST items job={job_id} SKIP (empty)")
        return 0

    # Batch insert — REST do Supabase aceita array
    try:
        url = f"{SUPABASE_URL}/rest/v1/project_items"
        body = json.dumps(rows).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Prefer', 'return=minimal')
        urllib.request.urlopen(req, timeout=30)
        _supa_log(f"PERSIST items job={job_id} OK n={len(rows)}")
        return len(rows)
    except urllib.error.HTTPError as e:
        try:
            resp = e.read().decode('utf-8', errors='replace')[:500]
        except Exception:
            resp = '(unreadable)'
        _supa_log(f"PERSIST items job={job_id} HTTP {e.code}: {resp}")
        print(f"[persist_items] HTTP {e.code}: {resp}")
        return 0
    except Exception as e:
        _supa_log(f"PERSIST items job={job_id} ERR {type(e).__name__}: {e}")
        print(f"[persist_items] err: {e}")
        return 0


def _rpc_update_project_status(job_id: str, data: dict) -> bool:
    """Atualiza uma row de projects via RPC `update_project_status`.
    Retorna True só se a RPC retornou rows_updated >= 1 (detecta silent fail)."""
    import urllib.request, urllib.error, json

    # Converte o dict de colunas → argumentos da RPC
    payload = {
        "p_job_id": job_id,
        "p_status":        data.get("status"),
        "p_items_count":   data.get("items_count"),
        "p_total_area":    data.get("total_area"),
        "p_layout_area":   data.get("layout_area"),
        "p_error_message": data.get("error_message"),
        "p_completed_at":  data.get("completed_at"),
        "p_warnings":      data.get("warnings"),
    }

    try:
        url = f"{SUPABASE_URL}/rest/v1/rpc/update_project_status"
        body = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req.add_header('Content-Type', 'application/json')
        resp = urllib.request.urlopen(req, timeout=20)
        resp_body = resp.read().decode('utf-8', errors='replace')
        rows = 0
        try:
            rows = int(resp_body.strip())
        except (ValueError, TypeError):
            # Pode vir como string JSON: "1" ou como array
            try:
                parsed = json.loads(resp_body)
                if isinstance(parsed, int):
                    rows = parsed
                elif isinstance(parsed, list) and parsed:
                    rows = int(parsed[0]) if isinstance(parsed[0], int) else 0
            except Exception:
                pass

        if rows >= 1:
            _supa_log(f"RPC update_project_status job_id={job_id} OK rows={rows}  data={json.dumps(data)[:200]}")
            return True

        # 0 rows: a row não existe (provável erro de job_id ou race condition)
        _supa_log(f"RPC update_project_status job_id={job_id} ZERO_ROWS  data={json.dumps(data)[:200]}")
        print(f"[supabase] RPC update_project_status job={job_id}: row não encontrada")
        return False

    except urllib.error.HTTPError as e:
        try:
            resp_body = e.read().decode('utf-8', errors='replace')[:500]
        except Exception:
            resp_body = '(unreadable)'
        msg = f"RPC update_project_status job_id={job_id} HTTP {e.code}: {resp_body}  data={json.dumps(data)[:200]}"
        print(f"[supabase] RPC HTTP {e.code}: {resp_body}")
        _supa_log(msg)
        return False
    except Exception as e:
        msg = f"RPC update_project_status job_id={job_id} ERR {type(e).__name__}: {e}  data={json.dumps(data)[:200]}"
        print(f"[supabase] RPC err: {e}")
        _supa_log(msg)
        return False


# Campos editáveis via update_project_meta (RPC criada na migration
# add_project_address_phase_and_meta_rpc_v2). Mantém alinhado com a RPC.
_META_FIELDS = {"project_name", "typology", "address", "phase"}


def _rpc_update_project_meta(job_id: str, data: dict) -> bool:
    """Atualiza metadados editáveis (project_name/typology/address/phase) via
    RPC `update_project_meta`. Mesmo padrão da update_project_status.
    Retorna True só se rows_updated >= 1."""
    import urllib.request, urllib.error, json
    payload = {
        "p_job_id":       job_id,
        "p_project_name": data.get("project_name"),
        "p_typology":     data.get("typology"),
        "p_address":      data.get("address"),
        "p_phase":        data.get("phase"),
    }
    try:
        url = f"{SUPABASE_URL}/rest/v1/rpc/update_project_meta"
        body = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req.add_header('Content-Type', 'application/json')
        resp = urllib.request.urlopen(req, timeout=20)
        resp_body = resp.read().decode('utf-8', errors='replace')
        rows = 0
        try:
            rows = int(resp_body.strip())
        except (ValueError, TypeError):
            try:
                parsed = json.loads(resp_body)
                if isinstance(parsed, int):
                    rows = parsed
                elif isinstance(parsed, list) and parsed:
                    rows = int(parsed[0]) if isinstance(parsed[0], int) else 0
            except Exception:
                pass
        if rows >= 1:
            _supa_log(f"RPC update_project_meta job_id={job_id} OK rows={rows}  data={json.dumps(data)[:200]}")
            return True
        _supa_log(f"RPC update_project_meta job_id={job_id} ZERO_ROWS  data={json.dumps(data)[:200]}")
        return False
    except urllib.error.HTTPError as e:
        try:
            resp_body = e.read().decode('utf-8', errors='replace')[:500]
        except Exception:
            resp_body = '(unreadable)'
        _supa_log(f"RPC update_project_meta job_id={job_id} HTTP {e.code}: {resp_body}  data={json.dumps(data)[:200]}")
        return False
    except Exception as e:
        _supa_log(f"RPC update_project_meta job_id={job_id} ERR {type(e).__name__}: {e}  data={json.dumps(data)[:200]}")
        return False

# ═══════════════════════════════════════════════════════════════
#  Supabase Storage helpers (bucket aiarq-planilhas)
#  Persiste planilhas geradas pra sobreviverem a redeploys do Render.
# ═══════════════════════════════════════════════════════════════

PLANILHAS_BUCKET = "aiarq-planilhas"
PRANCHAS_BUCKET = "aiarq-pranchas"  # PDFs originais pra "abrir prancha" na revisão inline


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


_PRANCHA_MIME = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".dxf": "application/acad",
    ".dwg": "application/acad",
}


def _sanitize_filename_for_storage(filename: str) -> str:
    """Remove acentos e caracteres especiais que quebram upload pro Supabase Storage.

    Bug detectado: PDF com nome 'Planta 1 - Galpão.pdf' dava HTTP 400 no upload
    mesmo com URL-encoding correto (Galp%C3%A3o). O Storage rejeita certos
    bytes UTF-8 multi-byte. Solução: ASCII-only filename pro storage.
    """
    import unicodedata
    # Decompõe acentos (ã = a + ̃) e remove os combinadores
    nfkd = unicodedata.normalize("NFKD", filename)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Mantém só ASCII printáveis seguros pra URL
    safe = "".join(c if (c.isalnum() or c in " ._-()") else "_" for c in ascii_only)
    # Compacta múltiplos underscores
    while "__" in safe:
        safe = safe.replace("__", "_")
    return safe.strip("_ ") or "file"


def _safe_local_filename(filename: str) -> str:
    """Sanitiza filename pra uso em os.path.join local — anti-traversal.

    Aplica _sanitize_filename_for_storage E garante que o resultado:
    - É só basename (sem barras / nem backslashes)
    - Não é '.' nem '..' nem começa com '.'
    - Não é vazio (fallback 'upload')

    Use isso em TODO os.path.join(dir, filename) onde filename vem
    de UploadFile.filename. Sem isso, cliente manda '../../etc/passwd'
    e escreve fora do work_dir.
    """
    import os as _os
    if not filename:
        return "upload"
    # Pega só o último componente (cobre '/foo/bar' e '\\foo\\bar')
    base = _os.path.basename(filename.replace("\\", "/"))
    safe = _sanitize_filename_for_storage(base)
    # Rejeita resultados que ainda seriam traversal ou vazios
    if not safe or safe in (".", "..") or safe.startswith("."):
        return "upload"
    return safe


def _supabase_storage_upload_prancha(local_path: str, job_id: str, filename: str) -> bool:
    """Upload de prancha (PDF, PNG, JPG) pro bucket aiarq-pranchas.
    Key: {job_id}/{filename_sanitizado}. Content-Type derivado da extensão.

    Filename é sanitizado pra remover acentos/especiais — Supabase Storage
    rejeita certos UTF-8 multi-byte mesmo URL-encoded."""
    import urllib.request, urllib.error
    try:
        with open(local_path, "rb") as f:
            body = f.read()
        import urllib.parse as _up
        safe_name = _sanitize_filename_for_storage(filename)
        remote_key = f"{job_id}/{_up.quote(safe_name)}"
        url = f"{SUPABASE_URL}/storage/v1/object/{PRANCHAS_BUCKET}/{remote_key}"
        ext = os.path.splitext(safe_name.lower())[1]
        mime = _PRANCHA_MIME.get(ext, "application/octet-stream")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("Content-Type", mime)
        req.add_header("x-upsert", "true")
        urllib.request.urlopen(req, timeout=60)
        if safe_name != filename:
            _supa_log(f"STORAGE upload prancha OK (saneado: '{filename}' → '{safe_name}')")
        return True
    except Exception as e:
        _supa_log(f"STORAGE upload prancha {filename} ERR {type(e).__name__}: {e}")
        print(f"[storage pranchas] upload {filename} error: {e}")
        return False


# Alias de compatibilidade com código antigo
_supabase_storage_upload_pdf = _supabase_storage_upload_prancha


def _supabase_storage_download_prancha(job_id: str, filename: str) -> Optional[bytes]:
    """Baixa prancha (PDF/PNG/etc) do Storage. Retorna bytes ou None."""
    import urllib.request, urllib.parse as _up
    try:
        remote_key = f"{job_id}/{_up.quote(filename)}"
        url = f"{SUPABASE_URL}/storage/v1/object/{PRANCHAS_BUCKET}/{remote_key}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.read()
    except Exception as e:
        print(f"[storage pranchas] download {filename}: {e}")
        return None


# Alias de compatibilidade
_supabase_storage_download_pdf = _supabase_storage_download_prancha


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
    expose_headers=["X-Filename", "Content-Disposition"],
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


# ═══════════════════════════════════════════════════════════════
#  Startup recovery: jobs travados após redeploy
#
#  O /tmp do Render é volátil: num redeploy, a thread de processamento
#  morre no meio e o `jobs[job_id]` em memória/JSON some, mas o registro
#  no Supabase fica pendurado em status='queued'/'processing' pra sempre.
#  Admin via acumular jobs-fantasma e o usuário final via "processando…"
#  sem nenhuma thread de verdade rodando.
#
#  Fix: no startup, varrer o Supabase atrás de jobs em aberto e marcá-los
#  como error com mensagem clara. Trades-offs:
#  - Não tenta retomar o processamento (seria complexo e caro); só encerra
#    o status pra o usuário poder reenviar.
#  - Só toca em linhas cujo `created_at` é mais velho que RECOVERY_GRACE_MIN
#    (3min) — evita marcar como erro um job que acabou de nascer no mesmo
#    tick do startup.
# ═══════════════════════════════════════════════════════════════

RECOVERY_GRACE_MIN = 3  # minutos: jobs mais novos que isso são ignorados


def _recover_stuck_jobs_on_startup():
    """Marca como 'error' qualquer projeto no Supabase ainda em queued/processing
    que tenha sobrevivido ao redeploy. Roda uma vez no startup do FastAPI.

    Usa RPC `list_stuck_jobs` (SECURITY DEFINER) pra enxergar rows de
    qualquer usuário — o SELECT direto via anon esbarra em RLS."""
    import urllib.request, urllib.error, json
    try:
        url = f"{SUPABASE_URL}/rest/v1/rpc/list_stuck_jobs"
        body = json.dumps({"p_older_than_minutes": RECOVERY_GRACE_MIN}).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=15)
        rows = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[recovery] falha ao buscar jobs pendentes via RPC: {e}")
        _supa_log(f"RECOVERY fetch ERR {type(e).__name__}: {e}")
        return

    if not rows:
        print("[recovery] nenhum job pendente no Supabase — startup limpo")
        return

    now = datetime.utcnow()
    recovered = 0
    skipped_grace = 0

    for row in rows:
        job_id = row.get("job_id")
        created_at = row.get("created_at")
        if not job_id:
            continue

        # Grace period: não marcar jobs que acabaram de nascer
        try:
            if created_at:
                # formato ISO: 2026-04-20T12:34:56.789Z ou +00:00
                clean = created_at.replace("Z", "+00:00")
                dt = datetime.fromisoformat(clean)
                age_min = (now.replace(tzinfo=dt.tzinfo) - dt).total_seconds() / 60
                if age_min < RECOVERY_GRACE_MIN:
                    skipped_grace += 1
                    continue
        except Exception:
            pass  # se data malformada, marca como erro mesmo assim

        # Marca como erro
        ok = _supabase_update("projects", "job_id", job_id, {
            "status": "error",
            "error_message": "Processamento interrompido por reinício do servidor. Reenvie o projeto.",
            "completed_at": now.isoformat(),
        })
        if ok:
            recovered += 1
            # Também atualiza o JobsStore local se ainda estiver lá
            try:
                if job_id in jobs:
                    jobs.update_field(job_id,
                                       status="error",
                                       error_message="Processamento interrompido por reinício do servidor.",
                                       current_step="Erro: reinício do servidor")
            except Exception:
                pass

    print(f"[recovery] startup: {recovered} jobs marcados como erro, "
          f"{skipped_grace} pulados (dentro da janela de graça)")
    _supa_log(f"RECOVERY startup recovered={recovered} grace_skip={skipped_grace}")


@app.on_event("startup")
async def _on_startup_recover_jobs():
    """Hook de startup do FastAPI: limpa jobs travados do redeploy anterior."""
    try:
        _recover_stuck_jobs_on_startup()
    except Exception as e:
        # Nunca deixar o startup falhar por causa da recuperação
        print(f"[recovery] exceção não-fatal no startup: {e}")


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


def _pick_area_consensus(readings: list) -> float:
    """Consenso de área entre leituras de várias pranchas.

    Antes: cada prancha sobrescrevia o valor anterior — bug onde uma prancha
    de detalhe com valor errado (135m² em vez de 270m² ou vice-versa)
    "ganhava" simplesmente por ser a última processada. Resultado: área
    dependia da ordem de processamento.

    Agora: coleta todas as leituras, agrupa por similaridade (±5%), e
    retorna a MODA (valor mais frequente). Empate resolvido pelo maior valor.

    Exemplo:
      leituras = [135.4, 135.4, 270.0, 135.0]  → winner bucket = [135.4, 135.4, 135.0] (3 pranchas)
      → retorna ~135.3
    """
    vals = [float(v) for v in readings if v and float(v) > 0]
    if not vals:
        return 0.0
    if len(vals) == 1:
        return vals[0]

    buckets: list[list[float]] = []
    for v in vals:
        placed = False
        for bucket in buckets:
            median = sum(bucket) / len(bucket)
            if median > 0 and abs(v - median) / median <= 0.05:
                bucket.append(v)
                placed = True
                break
        if not placed:
            buckets.append([v])

    # Mais leituras = mais confiável. Empate: maior valor (laje bruta
    # costuma ser o maior dos candidatos na dúvida).
    buckets.sort(key=lambda b: (-len(b), -max(b)))
    winner = buckets[0]
    return round(sum(winner) / len(winner), 2)


def _dedupe_rooms(rooms: list) -> list:
    """Dedup de ambientes em kept_elements/new_rooms.

    A IA extrai "BANHEIRO" de uma prancha e "Banheiro suíte" de outra; sem
    dedup, ambos aparecem no resumo. Regra:
    - Case-insensitive + remove acentos pra comparar
    - Se um ambiente é substring do outro (ex.: "banheiro" ⊂ "banheiro
      suíte"), mantém só o MAIS específico
    - Preserva a forma original de escrita do item mantido
    - Aceita itens como strings OU dicts (formato usado por new_rooms)
    """
    if not rooms:
        return rooms

    import unicodedata

    def _key(r) -> str:
        if isinstance(r, dict):
            name = r.get("name", "")
        else:
            name = str(r or "")
        s = name.lower().strip()
        s = unicodedata.normalize("NFD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        s = _re.sub(r"[^a-z0-9]+", " ", s).strip()
        return s

    # Ordena por length decrescente — "banheiro suíte" vem antes de "banheiro"
    # pra garantir que a versão mais específica seja mantida
    sorted_rooms = sorted(rooms, key=lambda r: -len(_key(r)))
    seen_keys: list[str] = []
    out = []
    for r in sorted_rooms:
        k = _key(r)
        if not k:
            continue
        # Se já vimos key igual ou key atual é substring de alguma já vista
        # (ex.: "banheiro" enquanto já temos "banheiro suite"), pula
        is_subset = any(k == s or k in s.split() and len(k.split()) == 1
                        for s in seen_keys)
        if is_subset:
            continue
        # Também: se key atual tem substring em comum de >=2 palavras com
        # alguma já vista, considera duplicata (ex.: "sala de estar e jantar"
        # vs "sala de estar" — ambos devem virar 1)
        cur_tokens = set(k.split())
        is_dup = False
        for s in seen_keys:
            overlap = cur_tokens & set(s.split())
            if len(overlap) >= 2 and len(overlap) >= len(cur_tokens) * 0.6:
                is_dup = True
                break
        if is_dup:
            continue
        seen_keys.append(k)
        out.append(r)
    return out


def _consolidate_items(items: list) -> list:
    """Consolida itens redundantes em múltiplas passadas:

    PASSADA 1 — por (chave_normalizada, unidade):
    - Mesma chave + mesma qty + mesma unidade → mantém 1 (desc mais completa).
    - Mesma chave + mesma unidade + qtys diferentes → mantém todos.
    - Réplica por departamento (4+ itens, qty<2) → funde em 1 estimado.

    PASSADA 2 — fusões qty+discipline+noun (qty >= 2):
    - Mesma qty_arredondada + mesma discipline + units diferentes →
      funde. Escolhe melhor unit.
    - Mesma qty_arredondada + mesma discipline + mesma unit + primary_noun
      igual → funde.

    PASSADA 3 — fusões por FAMÍLIA em qty pequena (unit=un, vb, ml):
    - Itens com mesmo primary_noun + mesma discipline + qty <= 2 +
      descrições "quase iguais" (variantes de legenda "conforme
      especificação XX") → consolida em 1 linha "NOUN — N un (várias
      variantes)" somando qtys.
    - Casos típicos: 6 portas "conforme especificação X" qty=1, 5 ralos,
      4 luminárias LM1/LM2 duplicadas cross-prancha.

    PASSADA 4 — agrupar luminárias por código LM*/LN*:
    - Descrições tipo "Luminária LM1" extraídas de pranchas diferentes
      viram 1 linha por código, somando qtys.

    PASSADA 5 — filtrar itens "a definir" sem fonte real:
    - Descrições/obs com "a definir", "por definir", "conforme projeto"
      + qty=1 default + 3+ casos similares → consolida em 1 linha única
      "Itens a especificar em projeto executivo".
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

    # ═══════════════════════════════════════════════════════════════
    #  PASSADA 3 — Famílias em qty pequena (un/ml/vb com qty<=2)
    # ═══════════════════════════════════════════════════════════════
    # Alvo: "Porta conforme especificação 08" qty=1 × 6 duplicadas;
    # "Ralo sifonado" qty=1 × 5 vezes; "Mobilização" qty=1 × 3 vezes.
    # A IA analisa cada prancha em isolamento e cria variantes da mesma
    # família que passada 2 ignora (corte em qty>=2).
    #
    # Regra pra evitar falso-positivo: só funde se as descrições são
    # "quase iguais" (começam com o mesmo noun + mesmas primeiras 3
    # palavras OU todas contêm "especificação"/"conforme" como marca
    # de item-de-legenda).
    def _is_legend_variant(descs: list[str]) -> bool:
        """True se as descrições parecem variações numéricas da mesma
        linha de legenda (ex.: 'Porta conforme especificação 08', 09, 10)."""
        markers = ("conforme especifica", "conforme projeto", "especifica",
                   "a definir", "por definir", "conforme detalhe",
                   "conforme indicado")
        hits = sum(1 for d in descs if any(m in (d or "").lower() for m in markers))
        # Se >=60% têm marca de legenda, trata como variante
        return hits >= max(2, int(len(descs) * 0.6))

    def _same_opening(descs: list[str], n_tokens: int = 3) -> bool:
        """True se todas descrições começam com os mesmos n primeiros tokens
        significativos (>3 chars, não-genéricos)."""
        def _open(d):
            norm = _normalize_description_key(d or "")
            return " ".join(norm.split()[:n_tokens])
        openings = {_open(d) for d in descs}
        return len(openings) == 1 and next(iter(openings)) != ""

    # Código de luminária (LM1, LM2, etc.) — se presente, separa o bucket
    # pra passada 3 não misturar luminárias de códigos diferentes.
    _lum_code_re_p3 = _re.compile(r"\b([LMN][MN]\d{1,2})\b", _re.IGNORECASE)

    buckets_p3: dict = {}
    keep_as_is: list = []
    for it in pass2:
        try:
            qty_r = round(float(it.quantity or 0), 2)
        except Exception:
            qty_r = 0.0
        # Só considera qty pequena (1, 1.5, 2); qty grandes já foram
        # tratadas em passada 2
        if qty_r > 2.0 or qty_r <= 0:
            keep_as_is.append(it)
            continue
        if it.unit not in ("un", "ml", "vb", "cj"):
            keep_as_is.append(it)
            continue
        noun = _primary_noun(it.description)
        if not noun:
            keep_as_is.append(it)
            continue
        # Código de luminária entra no key pra não misturar LM1 com LM2
        code = _lum_code_re_p3.search(it.description or "")
        code_tag = code.group(1).upper() if code else ""
        # Bucket: discipline + primary_noun + unit + código LM (se houver)
        key = (it.discipline or "", noun, it.unit, code_tag)
        buckets_p3.setdefault(key, []).append(it)

    pass3 = list(keep_as_is)
    for (disc, noun, unit, code_tag), group in buckets_p3.items():
        descs = [it.description for it in group]

        # Critério de consolidação por nível de segurança:
        #
        # SEGURO — sempre consolida, mesmo com só 2 itens:
        #   - unit=vb + mesmo noun (ex.: 3 "Mobilização" vb=1 é sempre erro;
        #     vb não faz sentido duplicar)
        #
        # FORTE — consolida com 3+ itens se mesmo noun/disc/unit:
        #   - un + mesmo noun ("Ralo" × 5, "Porta" × 6) são quase sempre
        #     variantes da mesma família em pranchas diferentes
        #
        # BORDERLINE — precisa reforço (legenda-variant ou mesma abertura):
        #   - ml + mesmo noun (rodapé de cozinha ≠ rodapé do banheiro)
        #   - un com só 2 itens (pode ser 2 portas distintas legítimas)
        should_merge = False
        if unit == "vb" and len(group) >= 2:
            should_merge = True  # vb duplicado é sempre erro
        elif unit == "un" and len(group) >= 3:
            should_merge = True  # 3+ un mesma família: provável duplicação
        elif unit == "cj" and len(group) >= 2:
            should_merge = True  # conjuntos duplicados
        elif len(group) >= 3 and (_is_legend_variant(descs) or _same_opening(descs, 3)):
            should_merge = True  # ml/etc só com reforço
        elif len(group) >= 2 and _is_legend_variant(descs):
            # 2 itens ambos com "conforme especificação" também funde
            should_merge = True

        if not should_merge:
            pass3.extend(group)
            continue

        # Consolida
        best = max(group, key=lambda x: len(x.description or ""))
        total_qty = round(sum(float(it.quantity or 0) for it in group), 2)
        # Remove sufixo numérico da legenda pra descrição limpa
        clean = _re.sub(r"\s*(conforme\s+)?(especifica[çc][aã]o\s+\d+|especifica[çc][aã]o\b).*$",
                        "", best.description, flags=_re.IGNORECASE).strip()
        if not clean or len(clean) < 5:
            clean = noun.capitalize()
        consolidated = BudgetItem(
            item_num=best.item_num,
            description=f"{clean} — {len(group)} variantes consolidadas",
            unit=unit,
            quantity=total_qty,
            observations=(
                f"Consolidado de {len(group)} entradas com mesma família "
                f"({noun}) — soma: {total_qty} {unit}. "
                f"Ver legenda do projeto pra especificações individuais."
            ),
            ref_sheet=best.ref_sheet,
            confidence=Confidence("estimado"),
            discipline=disc,
        )
        pass3.append(consolidated)

    # ═══════════════════════════════════════════════════════════════
    #  PASSADA 4 — Luminárias por código LM*/LN*/LU*
    # ═══════════════════════════════════════════════════════════════
    # "Luminária LM1" extraída de 3 pranchas como 3 itens separados
    # (qty 3 + 1 + 1) vira 1 linha (qty 5). Só aplicável em iluminação.
    lum_code_re = _re.compile(r"\b([LMN][MN]\d{1,2})\b", _re.IGNORECASE)

    def _lum_code(desc: str) -> str | None:
        m = lum_code_re.search(desc or "")
        return m.group(1).upper() if m else None

    by_code: dict[str, list] = {}
    pass4 = []
    for it in pass3:
        if (it.discipline or "").lower() != "iluminação".lower():
            pass4.append(it)
            continue
        code = _lum_code(it.description)
        if not code or it.unit != "un":
            pass4.append(it)
            continue
        by_code.setdefault(code, []).append(it)

    for code, group in by_code.items():
        if len(group) == 1:
            pass4.append(group[0])
            continue
        best = max(group, key=lambda x: len(x.description or ""))
        total_qty = round(sum(float(it.quantity or 0) for it in group), 2)
        total_qty_int = int(total_qty) if total_qty == int(total_qty) else total_qty
        consolidated = BudgetItem(
            item_num=best.item_num,
            description=best.description,
            unit="un",
            quantity=float(total_qty_int),
            observations=(
                f"Consolidado — código {code} aparece em {len(group)} pranchas, "
                f"somando {total_qty_int} unidades. Ver quadro de cargas "
                f"do projeto pra confirmar total."
            ),
            ref_sheet=best.ref_sheet,
            confidence=best.confidence,  # preserva confirmado se todos eram
            discipline=best.discipline,
        )
        pass4.append(consolidated)

    # ═══════════════════════════════════════════════════════════════
    #  PASSADA 5 — Consolidar itens "a definir" sem fonte clara
    # ═══════════════════════════════════════════════════════════════
    # "Acabamento elétrico a definir" qty=1 × 3 vezes é noise —
    # orçamentista já sabe que precisa de projeto executivo. Consolida
    # em 1 linha única por disciplina.
    def _is_vague(it) -> bool:
        text = f"{it.description or ''} {it.observations or ''}".lower()
        vague_markers = (
            "a definir", "por definir", "a ser definida",
            "acabamento elétrico a definir", "acabamentos elétricos a definir",
            "especificação a definir",
        )
        has_vague = any(m in text for m in vague_markers)
        short = (it.description or "").strip()
        # Só marca como vago se qty=1/0 e unit vb/un e o texto é genérico
        try:
            qty_r = float(it.quantity or 0)
        except Exception:
            qty_r = 0.0
        return has_vague and qty_r <= 1.0 and it.unit in ("un", "vb", "cj")

    vague_by_disc: dict[str, list] = {}
    pass5 = []
    for it in pass4:
        if _is_vague(it):
            vague_by_disc.setdefault(it.discipline or "Complementares", []).append(it)
        else:
            pass5.append(it)

    for disc, group in vague_by_disc.items():
        if len(group) == 1:
            pass5.append(group[0])
            continue
        # 2+ itens vagos mesma disciplina → consolida em 1 linha
        best = max(group, key=lambda x: len(x.description or ""))
        consolidated = BudgetItem(
            item_num=best.item_num,
            description=f"Itens de {disc.lower()} a especificar em projeto executivo",
            unit="vb",
            quantity=1.0,
            observations=(
                f"Consolidado de {len(group)} entradas genéricas "
                f"(\"a definir\", \"conforme projeto\") sem especificação na "
                f"legenda. Quantificar e especificar no projeto executivo."
            ),
            ref_sheet=best.ref_sheet,
            confidence=Confidence("estimado"),
            discipline=disc,
        )
        pass5.append(consolidated)

    # ═══════════════════════════════════════════════════════════════
    #  PASSADA 6 — DEDUP CROSS-PRANCHA (mesmo elemento em pranchas diferentes)
    # ═══════════════════════════════════════════════════════════════
    # Caso real Weslei (2026-05-08): "Escada metálica" apareceu 2 vezes:
    #   - "PROJETO AMPLIACAO" → qty=8.6, unit=m² (medida REAL da legenda)
    #   - "eletrico.pdf" → qty=1, unit=un (vista da mesma escada na elétrica)
    # Resultado: usuário recebia 2 escadas, sendo a mesma física.
    #
    # Regra: agrupar por (primary_noun, discipline). Pra grupos com 2+ itens
    # vindos de pranchas DIFERENTES (ref_sheet) — provável duplicação.
    # Mantém o item de MAIOR ESPECIFICIDADE (qty>0 vence qty=0, m²>m>un>vb,
    # confirmado vence estimado).

    # Prioridade de unidade (maior = mais específica). m²/m³ vencem un/vb.
    _UNIT_PRIORITY = {
        "m²": 100, "m2": 100, "m³": 100, "m3": 100,
        "m": 80, "ml": 80,
        "kg": 60,
        "un": 40, "cj": 35,
        "mês": 30, "dia": 25,
        "vb": 10, "%": 5,
    }

    def _unit_priority(u: str) -> int:
        return _UNIT_PRIORITY.get((u or "").lower().strip(), 50)

    def _item_score(it) -> tuple:
        """Pra ordenar candidatos a manter — maior = melhor."""
        try:
            qty = float(it.quantity or 0)
        except Exception:
            qty = 0.0
        return (
            1 if qty > 0 else 0,                          # qty>0 vence qty=0
            1 if it.confidence == Confidence("confirmado") else 0,
            _unit_priority(it.unit),                       # m² vence un vence vb
            qty,                                           # qty maior desempata
            len(it.description or ""),                     # descrição mais completa
        )

    buckets_p6: dict[tuple, list] = {}
    for it in pass5:
        noun = _primary_noun(it.description or "")
        if not noun:
            buckets_p6.setdefault(("__solo__", id(it)), []).append(it)
            continue
        key = (noun, it.discipline or "")
        buckets_p6.setdefault(key, []).append(it)

    pass6 = []
    for key, group in buckets_p6.items():
        if key[0] == "__solo__" or len(group) == 1:
            pass6.extend(group)
            continue

        # Pra grupo com 2+ itens, verificar se vêm de pranchas diferentes
        ref_sheets = set((it.ref_sheet or "").strip().lower() for it in group)
        if len(ref_sheets) < 2:
            # Mesma prancha — não é cross-prancha (provavelmente passadas anteriores
            # já trataram). Manter como está.
            pass6.extend(group)
            continue

        # Verificar similaridade de descrições (overlap >= 2 tokens)
        descs_keys = [set(_normalize_description_key(it.description or "").split()) for it in group]
        # Pra todos do grupo, ver se há overlap forte entre TODOS pares
        # (alternativa simplificada: ver se o primary_noun é o mesmo + alguma palavra
        # significativa em comum entre todos)
        common_tokens = set.intersection(*descs_keys) if descs_keys else set()
        sig_common = {t for t in common_tokens if len(t) > 3}  # ignora "de", "e", etc

        if not sig_common:
            # Mesmo noun mas sem outras palavras significativas em comum — provavelmente
            # itens distintos (ex: "porta" em 2 pranchas diferentes = 2 portas diferentes)
            pass6.extend(group)
            continue

        # Confirmada duplicação cross-prancha. Manter o item de MAIOR especificidade.
        winner = max(group, key=_item_score)
        losers = [it for it in group if id(it) != id(winner)]
        total_pranchas = len(ref_sheets)

        # Anota no obs do vencedor que dedupliquei
        loser_summary = "; ".join(
            f"{it.quantity} {it.unit} ({it.ref_sheet[:30] if it.ref_sheet else 'sem ref'})"
            for it in losers
        )
        merged_obs = (winner.observations or "").rstrip(". ") + (". " if winner.observations else "")
        merged_obs += (
            f"Deduplicado: este item aparecia em {total_pranchas} pranchas diferentes "
            f"do mesmo projeto. Versões descartadas: {loser_summary}. "
            f"Versão mantida tem maior especificidade (unidade física, qty>0)."
        )
        merged_item = BudgetItem(
            item_num=winner.item_num,
            description=winner.description,
            unit=winner.unit,
            quantity=winner.quantity,
            observations=merged_obs,
            ref_sheet=winner.ref_sheet,
            confidence=winner.confidence,
            discipline=winner.discipline,
        )
        pass6.append(merged_item)

    return pass6


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
            # un com decimal é suspeito (ex.: IA confunde um comprimento
            # em ml com contagem e devolve un=NNN.NN).
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
                typology: str = "office",
                user_sheet_types: dict[str, str] | None = None,
                user_ambientes: dict[str, str] | None = None):
    """Processa um job prancha por prancha. Aceita PDF, DWG e DXF.

    `typology` alimenta a camada de calibração por densidade — alertas
    comparam o projeto contra benchmarks da mesma categoria.

    `user_sheet_types` (opcional): mapa {caminho_arquivo: sheet_type}
    pra sobrescrever a detecção automática quando o usuário classificou
    a prancha manualmente no dashboard. Sem isso, o classificador por
    nome falha com numerações próprias de cada escritório.

    `user_ambientes` (opcional): mapa {caminho_arquivo: ambiente_canonico}
    quando sheet_type = detalhe_ambiente (banheiro_suite, cozinha, lavabo
    etc). Injeta contexto específico no prompt da IA."""
    user_sheet_types = user_sheet_types or {}
    user_ambientes = user_ambientes or {}
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
        from analyzer import _normalize_br_number as _norm_br
        def sf(v):
            """Converte valor (string ou número) em float, respeitando notação
            PT-BR: vírgula pode ser decimal. Antes usávamos replace(',', '')
            que transformava '135,4' em 1354 — área de casa virava 10x maior."""
            if v is None: return 0
            s = str(v).replace('m²','').replace('m2','').replace('cm','').strip()
            s = _norm_br(s)
            try: return float(s)
            except: return 0

        project_data = ProjectData()
        # Acumulador de áreas: consenso ao final do loop (evita ordem de
        # processamento decidir qual valor sobrevive)
        _area_readings = {"total_area": [], "layout_area": [], "no_intervention_area": []}

        # Separar PDFs de DWG/DXF
        pdf_paths = [f for f in file_paths if f.lower().endswith('.pdf')]
        cad_paths = [f for f in file_paths if f.lower().endswith(('.dwg', '.dxf'))]

        # Persistir TODOS os arquivos originais (PDF + DWG + DXF) no Storage.
        # Serve pra 2 coisas:
        # 1. Botão 👁 "Ver prancha" na revisão inline
        # 2. Reprocessar projeto com motor atualizado (baixa originais, roda de novo)
        # Roda em background pra não atrasar o processamento.
        def _upload_pranchas_bg():
            for _p in file_paths:
                try:
                    _fname = os.path.basename(_p)
                    _supabase_storage_upload_prancha(_p, job_id, _fname)
                except Exception as _e:
                    print(f"[upload-pranchas] erro {_fname}: {_e}")
        try:
            import threading as _t
            _t.Thread(target=_upload_pranchas_bg, daemon=True).start()
        except Exception:
            pass

        # Render DWG/DXF → PNG pra preview na revisão (opção 1 acordada).
        # Só roda se tem CAD no projeto. Matplotlib é pesado, por isso
        # em thread separada.
        if cad_paths:
            def _render_cad_previews_bg():
                try:
                    from dxf_render import render_dxf_to_png_safe
                except Exception as _imp_e:
                    print(f"[cad-preview] import erro: {_imp_e}")
                    return
                for _cad in cad_paths:
                    _fname = os.path.basename(_cad)
                    # Procura o DXF convertido (se era DWG) ou usa direto
                    _dxf_path = _cad
                    if _cad.lower().endswith('.dwg'):
                        # Procurar DXF equivalente em work_dir
                        _base = os.path.splitext(_fname)[0]
                        for _cand in os.listdir(work_dir):
                            if _cand.lower().endswith('.dxf') and _base.lower() in _cand.lower():
                                _dxf_path = os.path.join(work_dir, _cand)
                                break
                        else:
                            continue  # DWG sem DXF convertido — pula
                    # Render
                    _png_path = os.path.join(work_dir, os.path.splitext(_fname)[0] + '.png')
                    if render_dxf_to_png_safe(_dxf_path, _png_path, timeout_s=60):
                        # Upload PNG pro Storage
                        _png_fname = os.path.splitext(_fname)[0] + '.png'
                        _supabase_storage_upload_prancha(_png_path, job_id, _png_fname)
            try:
                import threading as _t2
                _t2.Thread(target=_render_cad_previews_bg, daemon=True).start()
            except Exception:
                pass

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
                dwg_failed = []  # acumular DWGs que falharam pra reportar erro real depois
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
                            dwg_failed.append(os.path.basename(cad_path))
                            jobs.update_field(job_id, current_step=f"Falha ao converter DWG: {os.path.basename(cad_path)} (seguindo sem)")
                    else:
                        dxf_paths.append(cad_path)

                # Se TODOS os DWGs falharam E não tem PDFs, é fim de linha — marca como failed.
                # Mensagem instrutiva pro user resolver sozinho (95% dos casos).
                if dwg_failed and not dxf_paths and not pdf_paths:
                    arquivos = ', '.join(dwg_failed)
                    msg = (
                        f"❌ Não foi possível processar o DWG: {arquivos}. "
                        f"Tentamos com 2 conversores (ODA + libredwg) — ambos falharam. "
                        f"Causa provável: arquivo corrompido (faltam bytes) — pode ter acontecido se o "
                        f"AutoCAD travou na hora de salvar.\n\n"
                        f"📋 COMO RESOLVER (95% dos casos):\n"
                        f"1. Abra o arquivo no AutoCAD ou BricsCAD\n"
                        f"2. Vá em File → Save As\n"
                        f"3. Escolha o tipo: AutoCAD 2010/LT2010 DXF (*.dxf)\n"
                        f"4. Salve com nome novo\n"
                        f"5. Suba o DXF aqui (em vez do DWG)\n\n"
                        f"💡 ALTERNATIVA: se você plotou em PDF antes, mande o PDF — funciona igual."
                    )
                    jobs.update_field(job_id, error_message=msg, current_step="❌ Arquivo CAD inválido — leia mensagem abaixo")
                    raise RuntimeError(msg)
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
Gere itens quantitativos (descrição + unidade + quantidade, SEM preço) com base nesses dados.

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
comprimento somado de polylines de uma layer (ex.: layer de divisória com um
valor em metros), use esse valor como "confirmado" — é uma medição objetiva
direta do arquivo.

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
POR LAYER te dá um valor em metros pra uma layer de projeto, use esse valor
como confirmado. Não desconfie do número só porque vem de soma de linhas —
medir soma de linhas É a medição.

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
  Use os nomes de layer DESTE arquivo. Ignore layers de anotação, xrefs e aux.

Passo 2 — Checagem de LEV vs FOR:
  Liste pares conflitantes (mesmo tipo em layer LEV/existente e FOR/novo).
  Para cada par, diga qual escolheu e por quê (geralmente o layer de projeto
  NOVO vence sobre o de levantamento do existente).

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
    "workstations": 0,  // apenas pra ESCRITÓRIOS; em residencial/clínica etc deixe 0
    "departments": [],  // apenas pra escritório/escola; em residencial use new_rooms
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
do número no DXF, usando os nomes de layer/bloco desta prancha — ex.:
"Fonte: <N> INSERTs do bloco '<nome_bloco_real>'" ou "Fonte: área hachurada
do layer '<nome_layer_real>' = <valor> m²". Nunca invente nomes de layer ou
bloco — só cite os que estão no inventário deste arquivo."""

                    try:
                        from llm_retry import call_with_retry as _llm_retry
                        response = _llm_retry(
                            dxf_client,
                            tag=f"dxf:{os.path.basename(dxf_path)}",
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
                            # Acumula em vez de sobrescrever — resolvido via consenso depois
                            for _fld in ("total_area", "layout_area", "no_intervention_area"):
                                _v = pd.get(_fld)
                                if _v:
                                    _vf = sf(_v)
                                    if _vf > 0:
                                        _area_readings[_fld].append(_vf)
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
                     "forro": 4, "piso": 5, "pontos": 6, "mobiliario": 7, "marcenaria": 8,
                     "det_forro": 9, "detalhe_ambiente": 10}

        pdf_infos = []
        for pdf_path in pdf_paths:
            filename = os.path.basename(pdf_path)
            # Prioridade: escolha manual do usuário no dropdown > detecção por nome.
            # Sem isso, nomes arbitrários tipo "225.AFS.700.DET BANH SUITE" caíam
            # em DESCONHECIDO ou eram misclassificados.
            user_st_str = user_sheet_types.get(pdf_path, "")
            if user_st_str:
                try:
                    sheet_type = SheetType(user_st_str)
                except ValueError:
                    sheet_type = identify_sheet_type(filename)
            else:
                sheet_type = identify_sheet_type(filename)
            pdf_infos.append((pdf_path, filename, sheet_type))

        pdf_infos.sort(key=lambda x: priority.get(x[2].value, 99))

        # Agrupar pranchas IRMÃS: pranchas do mesmo ambiente (ex.: DET LAVABO
        # pode ter planta baixa + elevações em PDFs separados). Saber que
        # existem irmãs evita warning de "prancha órfã" e permite o prompt
        # cruzar informação entre elas (ex.: legenda de códigos 01-14 que
        # está no PDF da planta mas não nas elevações).
        from processor import identify_ambiente as _id_amb_sib
        _siblings_map: dict[str, list[str]] = {}
        for _p, _fn, _st in pdf_infos:
            if _st == SheetType.DETALHE_AMBIENTE:
                _amb = user_ambientes.get(_p, "") or _id_amb_sib(_fn)
                if _amb:
                    _siblings_map.setdefault(_amb, []).append(_fn)

        # Faixa de progresso reservada para PDFs: após cad_end_pct (se houver CAD) até 90%
        pdf_start_pct = cad_end_pct if has_cad else 5
        pdf_end_pct = 90
        pdf_span = pdf_end_pct - pdf_start_pct

        for i, (pdf_path, filename, sheet_type) in enumerate(pdf_infos):
            step_pct = pdf_start_pct + int((i / max(total, 1)) * pdf_span)
            jobs.update_field(job_id, progress=step_pct)
            jobs.update_field(job_id, current_step=f"Prancha {i+1}/{total}: {filename}")

            # Se o auto-detect falhou E o usuário não classificou manualmente:
            # - se o nome contém palavra-chave de AMBIENTE (banh, cozinha, lavabo,
            #   suíte, etc), trata como DETALHE_AMBIENTE e extrai o ambiente do nome.
            # - senão, usa ARQUITETURA como prompt-genérico de fallback.
            if sheet_type == SheetType.DESCONHECIDO:
                from processor import identify_ambiente as _id_amb2
                _auto_amb = _id_amb2(filename)
                if _auto_amb:
                    print(f"[fallback] {filename}: detectado ambiente '{_auto_amb}' — usando PROMPT_DETALHE_AMBIENTE")
                    sheet_type = SheetType.DETALHE_AMBIENTE
                    # Guarda auto-detect no mapa (vai ser lido por user_ambientes.get)
                    user_ambientes.setdefault(pdf_path, _auto_amb)
                    jobs.update_field(job_id, current_step=f"Prancha {i+1}/{total}: {filename} (detalhe de {_auto_amb})")
                else:
                    print(f"[fallback] {filename}: tipo não detectado, usando PROMPT_ARQUITETURA como genérico")
                    sheet_type = SheetType.ARQUITETURA
                    jobs.update_field(job_id, current_step=f"Prancha {i+1}/{total}: {filename} (tipo não identificado — extração genérica)")

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
            # Ambiente: user escolheu manualmente > auto-detect por keyword
            from processor import identify_ambiente as _id_amb
            amb_for_sheet = user_ambientes.get(pdf_path, "") or (
                _id_amb(filename) if sheet_type == SheetType.DETALHE_AMBIENTE else ""
            )
            # Irmãs: outras pranchas do mesmo ambiente (ex: LAVABO em 704+705)
            siblings = []
            if amb_for_sheet and amb_for_sheet in _siblings_map:
                siblings = [s for s in _siblings_map[amb_for_sheet] if s != filename]
            result = analyze_sheet(client, sheet, typology=typology,
                                   ambiente=amb_for_sheet, siblings=siblings)

            # 4. Extrair dados do projeto
            if "project_data" in result:
                pd = result["project_data"]
                # Acumula em vez de sobrescrever — consenso ao final do loop
                for _fld in ("total_area", "layout_area", "no_intervention_area"):
                    _v = pd.get(_fld)
                    if _v:
                        _vf = sf(_v)
                        if _vf > 0:
                            _area_readings[_fld].append(_vf)
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
                "Instalações Elétricas e Dados",
                "Instalações Hidráulicas", "Instalações de Gás",
                "Ar-Condicionado", "Incêndio e Segurança",
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

                    # ref_sheet SEMPRE tem o filename real pra que o botão
                    # "Ver prancha" na revisão inline funcione. Hint da IA
                    # vai entre parênteses se for diferente do nome.
                    ia_hint = (item_data.get("ref_sheet") or "").strip()
                    if ia_hint and ia_hint.lower() not in filename.lower():
                        _ref = f"{filename} ({ia_hint[:60]})"
                    else:
                        _ref = filename
                    item = BudgetItem(
                        item_num=str(item_data.get("item_num", "")),
                        description=desc,
                        unit=normalized_unit,
                        quantity=qty,
                        observations=obs_raw,
                        ref_sheet=_ref,
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
        # Remove duplicatas similares (mesmo item com qty idêntica repetido em
        # múltiplas pranchas), consolida réplicas por departamento/zona e valida
        # un=inteiro (corrige quando a IA devolve un com decimais suspeitos).
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

        # Dedup de ambientes (kept_elements/new_rooms) case-insensitive.
        # A IA extrai de várias pranchas e acaba gerando "BANHEIRO" + "Banheiro"
        # + "Banheiro suíte" como itens separados. Agrupa por forma canônica.
        project_data.kept_elements = _dedupe_rooms(project_data.kept_elements)
        project_data.new_rooms = _dedupe_rooms(project_data.new_rooms)

        # Consenso de área: pega a MODA entre leituras de várias pranchas.
        # Sem isso, a última prancha processada sobrescrevia — uma leitura
        # errada da IA (135 vs 270 m²) dependia da ordem de análise.
        project_data.total_area = _pick_area_consensus(_area_readings["total_area"])
        project_data.layout_area = _pick_area_consensus(_area_readings["layout_area"])
        project_data.no_intervention_area = _pick_area_consensus(_area_readings["no_intervention_area"])
        for _fld, _reads in _area_readings.items():
            if len(set(_reads)) > 1:
                print(f"[area-consensus] {_fld}: leituras={_reads} → "
                      f"escolhido={getattr(project_data, _fld)}")

        # Enriquece itens com matches SINAPI (Caixa) + TCPO BIM (Pini).
        # SINAPI = referência principal (preço oficial gov BR, atualizado mensal).
        # TCPO = referência técnica complementar (insumos detalhados).
        # Ambos best-effort, nunca bloqueiam planilha.
        try:
            from sinapi_matcher import match_item as match_sinapi
            for it in all_items:
                try:
                    ms = match_sinapi(it.description, limit=3)
                    if ms:
                        it.sinapi_matches = ms
                except Exception:
                    pass
        except ImportError:
            pass

        try:
            from tcpo_matcher import match_item as match_tcpo, get_insumos
            for it in all_items:
                try:
                    ms = match_tcpo(it.description, limit=3)
                    if ms:
                        ms[0]['insumos'] = get_insumos(ms[0]['id'])
                        it.tcpo_matches = ms
                except Exception:
                    pass
        except ImportError:
            pass

        # Checa heurísticas de mercado (dispersão, cobertura, share MAT/MO)
        # contra as categorias de cada item. Adiciona alertas nas observations
        # pra ajudar o cliente a saber onde pedir 3 orçamentos / revisar escopo.
        # REGRA DURA: heurísticas são agregadas e anônimas — nunca valor
        # específico de projeto. Vem da tabela market_heuristics.
        try:
            from market_heuristics import check_item_anomaly
            for it in all_items:
                try:
                    alertas = check_item_anomaly(it, typology=typology)
                    if alertas:
                        sep = " | " if it.observations else ""
                        it.observations = (it.observations or "") + sep + " ".join(alertas)
                except Exception:
                    pass  # alertas são best-effort
        except ImportError:
            pass  # market_heuristics opcional

        output_path = os.path.join(work_dir, f"orcamento_{job_id}.xlsx")
        generate_spreadsheet(project_data, all_items, output_path, typology=typology)

        # Persistir itens individuais no Supabase pra permitir revisão inline
        # no navegador (endpoint /api/items/{job_id}). Sem isso, os itens só
        # existem no xlsx — a revisão só poderia ser feita no Excel offline.
        _persist_items_to_supabase(job_id, all_items)

        # Persistir warnings do motor (prancha órfã, legenda ausente) no
        # campo `warnings` da tabela projects — exibido em Meus Projetos
        # como alerta "precisa de complemento".
        if getattr(project_data, 'warnings', None):
            _supabase_update("projects", "job_id", job_id, {
                "warnings": project_data.warnings,
            })

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
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    sheet_types: list[str] = Form(default=[]),
    sheet_ambientes: list[str] = Form(default=[]),
    typology: str = "office",
    project_name: str = "",
    user_id: str = "",
    user_email: str = "",
    user_name: str = "",
    credits_to_consume_cents: int = 0,
):
    """Recebe PDF, DWG ou DXF e inicia processamento em background.

    - `files`: arquivos de prancha.
    - `sheet_types` (opcional): lista paralela a `files`. String vazia
      em uma posição significa "detectar automaticamente". Valor não-vazio
      sobrescreve a detecção e força o prompt do tipo escolhido pelo user.
      Valores aceitos: demolir, layout_novo, layout_atual, arquitetura,
      pontos, piso, forro, det_forro, mobiliario, marcenaria.
    - `typology` (opcional, default `office`): usado pela calibração por
      densidade pra comparar o projeto com padrões da mesma categoria.
    - `project_name` (opcional): apelido amigável dado pelo cliente.
    - `user_id` (opcional): se informado, vincula o projeto ao usuário e
      permite consumo/crédito. Validado contra JWT — não dá pra criar
      projeto em nome de outro usuário.
    - `credits_to_consume_cents` (opcional): se > 0, consome esse valor
      de créditos do user (usado quando checkout retornou is_free=true
      por saldo suficiente).
    """
    # AUTORIZAÇÃO: se o Form passou user_id (não-anônimo), tem que ter JWT
    # correspondente. Sem isso, atacante manda user_id de outro user e
    # cria projeto+consome créditos no nome dele.
    if user_id and user_id != "anonymous":
        jwt_user = _get_user_from_request(request)
        if not jwt_user:
            raise HTTPException(401, "Autenticação requerida quando user_id é informado")
        if jwt_user.get("id") != user_id and jwt_user.get("email", "").lower() != ADMIN_EMAIL:
            raise HTTPException(403, "user_id não corresponde ao token de autenticação")

    if typology not in _VALID_TYPOLOGIES:
        typology = "office"
    if not files:
        raise HTTPException(400, "Nenhum arquivo enviado")

    # Validar arquivos (aceitar PDF, DWG e DXF)
    valid_extensions = ('.pdf', '.dwg', '.dxf')
    # Guarda triplas (arquivo, sheet_type, ambiente) pra manter o mapeamento
    # após filtragem. sheet_types/sheet_ambientes podem estar vazias.
    valid_pairs = []
    for idx, f in enumerate(files):
        if f.filename and f.filename.lower().endswith(valid_extensions):
            st = sheet_types[idx] if idx < len(sheet_types) else ""
            amb = sheet_ambientes[idx] if idx < len(sheet_ambientes) else ""
            valid_pairs.append((f, st, amb))
    if not valid_pairs:
        raise HTTPException(400, "Nenhum arquivo válido encontrado. Aceito: PDF, DWG ou DXF.")

    if len(valid_pairs) > 50:
        raise HTTPException(400, "Máximo de 50 arquivos por projeto")

    # Criar job
    job_id = str(uuid.uuid4())[:8]
    work_dir = os.path.join(WORK_DIR, job_id)
    os.makedirs(work_dir, exist_ok=True)

    # Salvar arquivos + mapas {caminho_local: sheet_type / ambiente}
    file_paths = []
    user_sheet_types: dict[str, str] = {}
    user_ambientes: dict[str, str] = {}
    file_types = {'pdf': 0, 'dwg': 0, 'dxf': 0}
    for upload_file, user_st, user_amb in valid_pairs:
        # Anti path-traversal: nunca confiar em upload_file.filename
        safe_name = _safe_local_filename(upload_file.filename)
        file_path = os.path.join(work_dir, safe_name)
        content = await upload_file.read()

        # Validação de integridade (Bug Rafael 2026-05-04: DWG chegou
        # truncado e backend processou sem detectar, gerando planilha vazia)
        if upload_file.size and len(content) != upload_file.size:
            raise HTTPException(
                400,
                f"Arquivo '{upload_file.filename}' chegou incompleto: "
                f"recebido {len(content)} de {upload_file.size} bytes. "
                f"Provável conexão instável durante upload — tente de novo."
            )
        ext = upload_file.filename.lower().rsplit('.', 1)[-1]
        if ext == "dwg":
            if len(content) < 100:
                raise HTTPException(
                    400,
                    f"DWG '{upload_file.filename}' muito pequeno ({len(content)} bytes) — "
                    f"provavelmente corrompido. Verifique se o arquivo abre no AutoCAD."
                )
            if content[:2] != b"AC":
                raise HTTPException(
                    400,
                    f"DWG '{upload_file.filename}' não tem assinatura válida "
                    f"(esperado iniciar com 'AC10xx'). Arquivo corrompido — "
                    f"verifique no AutoCAD ou exporte como PDF e suba o PDF."
                )

        with open(file_path, "wb") as f:
            f.write(content)
        file_paths.append(file_path)
        if user_st:
            user_sheet_types[file_path] = user_st
        if user_amb:
            user_ambientes[file_path] = user_amb
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
    _supabase_insert("projects", {
        "job_id": job_id,
        "user_id": user_id or "anonymous",
        "user_email": user_email or "",
        "user_name": user_name or "",
        "project_name": project_name or "Sem nome",
        "typology": typology,
        "files_count": len(file_paths),
        "file_types": file_types,
        "status": "queued",
    })

    # Consome créditos de cashback/cupom se o frontend declarou uso
    # (quando crédito cobriu 100% do preço e pulou o Stripe).
    if credits_to_consume_cents > 0 and user_id and user_id != "anonymous":
        consumed = _consume_credits(user_id, credits_to_consume_cents, job_id)
        print(f"[credits] job={job_id} user={user_id} consumed={consumed}/{credits_to_consume_cents}")

    # Iniciar processamento em thread separada (não bloqueia HTTP)
    import threading
    t = threading.Thread(
        target=process_job,
        args=(job_id, file_paths, work_dir),
        kwargs={"typology": typology,
                "user_sheet_types": user_sheet_types,
                "user_ambientes": user_ambientes},
        daemon=True,
    )
    t.start()

    return {"job_id": job_id, "files_received": len(file_paths),
            "file_types": file_types, "status": "queued", "typology": typology}


@app.get("/api/debug/supa-log")
async def debug_supa_log(request: Request, tail: int = 50):
    """Últimas N linhas do log de operações Supabase — pra investigar por que
    updates silenciosos falham sem ter acesso direto ao log do Render.

    Restrito a admin (vaza queries internas com payloads e IDs).
    """
    _require_admin(request)
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
async def debug_dwg(request: Request):
    """Diagnóstico do suporte DWG. Restrito a admin (revela paths do FS)."""
    _require_admin(request)
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

    # libredwg (fallback open-source — opcional)
    result["libredwg_dwg2dxf"] = shutil.which("dwg2dxf")
    # Removido o find recursivo: caro (timeout) e revelador de layout do FS.

    return result


@app.get("/api/debug/oda-log/{job_id}")
async def get_oda_log(request: Request, job_id: str):
    """Retorna o log do ODA File Converter para um job.

    Restrito ao dono do projeto (ou admin) — log pode revelar nomes de
    arquivos enviados pelo usuário.
    """
    _require_project_owner(request, job_id)
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
async def download_file(job_id: str, request: Request):
    _require_project_owner(request, job_id)
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

    # Contar totais via Supabase count=exact.
    # FIX 2026-05-14: antes usava locals()[var_name] = ... que é noop em
    # CPython (locals() não tem write-back). Resultava em total_projects=0
    # e total_users=0 sempre, quebrando dashboard de métrica admin.
    total_projects = 0
    total_users = 0
    try:
        import urllib.request, json
        def _count_table(table):
            url = f"{SUPABASE_URL}/rest/v1/{table}?select=id"
            req = urllib.request.Request(url)
            req.add_header('apikey', SUPABASE_KEY)
            req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
            req.add_header('Prefer', 'count=exact')
            resp = urllib.request.urlopen(req, timeout=3)
            count_header = resp.headers.get('content-range', '')
            if '/' in count_header:
                return int(count_header.split('/')[1])
            return len(json.loads(resp.read()))
        try: total_projects = _count_table('projects')
        except Exception: pass
        try: total_users = _count_table('profiles')
        except Exception: pass
    except Exception:
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


# ── TCPO BIM: busca técnica de composições ──
@app.get("/api/tcpo/search")
async def tcpo_search(q: str, limit: int = 5):
    """Busca composições TCPO BIM por similaridade de descrição.

    Exemplo: /api/tcpo/search?q=luminaria+fluorescente&limit=5

    Retorna top N composições ordenadas por similaridade, com o 1º match
    enriquecido com a lista de insumos (material/mão de obra/equipamento).
    Usado pela UI pra permitir que o revisor busque a referência TCPO ideal
    pra cada item.
    """
    try:
        from tcpo_matcher import match_item, get_insumos
    except ImportError:
        return {"results": [], "error": "tcpo_matcher indisponível"}

    if not q or len(q.strip()) < 2:
        return {"results": []}

    matches = match_item(q.strip(), limit=min(int(limit or 5), 15))
    # Enriquece o 1º com insumos pra UI poder mostrar direto
    if matches:
        matches[0]['insumos'] = get_insumos(matches[0]['id'])
    return {"query": q, "count": len(matches), "results": matches}


@app.get("/api/tcpo/details/{composicao_id}")
async def tcpo_details(composicao_id: str):
    """Retorna detalhes completos de uma composição TCPO — todos os insumos,
    metadados (conteúdo, critério, normas). Usado quando o usuário expande uma
    referência pra ver a composição inteira.
    """
    try:
        from tcpo_matcher import get_insumos, _supabase_rpc
    except ImportError:
        return {"error": "tcpo_matcher indisponível"}

    rows = _supabase_rpc("get_tcpo_details", {"p_id": composicao_id}) or []
    if not rows:
        return {"error": "composição não encontrada"}
    return rows[0] if isinstance(rows, list) else rows


# ── HEURÍSTICAS DE MERCADO: alertas por categoria ──
@app.get("/api/heuristics/check")
async def heuristics_check(description: str, unit: str = "",
                            typology: str = "office"):
    """Retorna alertas de heurística pra um item (descrição + unidade).

    Exemplo: /api/heuristics/check?description=demolicao+de+drywall&typology=office

    Retorna: {
        'category': 'demolicao',
        'alertas': ['💡 variação 103%...'],
        'metrics': {'dispersion': {...}, 'mat_mo_share': {...}, 'coverage': {...}}
    }
    """
    try:
        from market_heuristics import (
            categorize_item, check_item_anomaly,
            get_dispersion_for_category, get_mat_mo_share_for_category,
            get_coverage_pattern_for_category,
        )
    except ImportError:
        return {"error": "market_heuristics indisponível"}

    if not description or len(description.strip()) < 3:
        return {"error": "descrição muito curta"}

    category = categorize_item(description)
    item_dict = {"description": description.strip(), "unit": unit.strip()}
    alertas = check_item_anomaly(item_dict, typology=typology)

    return {
        "category": category,
        "typology": typology,
        "alertas": alertas,
        "metrics": {
            "dispersion": get_dispersion_for_category(category, typology),
            "mat_mo_share": get_mat_mo_share_for_category(category, typology),
            "coverage": get_coverage_pattern_for_category(category, typology),
        },
    }


@app.get("/api/heuristics/summary")
async def heuristics_summary():
    """Retorna resumo do que tem na base de heurísticas (pra debug/transparência)."""
    try:
        from market_heuristics import get_summary
        return get_summary()
    except ImportError:
        return {"error": "market_heuristics indisponível"}


# ═══════════════════════════════════════════════════════════════
#  CHAT PÚBLICO (widget de vendas/dúvidas no site) + CAPTURA DE LEADS
# ═══════════════════════════════════════════════════════════════

# Rate limit simples em memória: max 20 mensagens / 10min por IP
_PUBLIC_CHAT_HITS: dict = {}  # ip → [timestamps]


@app.post("/api/public/chat/lead")
async def save_chat_lead(request: Request):
    """Salva (ou atualiza) um lead do chat widget.

    Chamado quando o visitante preenche nome + email ANTES da primeira
    mensagem. Usa email como chave de dedupe — se já existir, atualiza.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    name = str(body.get("name", "")).strip()[:120]
    email = str(body.get("email", "")).strip().lower()[:200]
    phone = str(body.get("phone", "")).strip()[:40]
    source_page = str(body.get("source_page", "")).strip()[:80]
    first_question = str(body.get("first_question", "")).strip()[:500]
    user_agent = request.headers.get("user-agent", "")[:300]

    if not name or not email or "@" not in email:
        return {"error": "Nome e email válidos são obrigatórios"}

    try:
        import urllib.parse as _up
        # Upsert por email (se já existe, atualiza last_message_at e n_messages)
        # Primeiro tenta achar
        find_url = (f"{SUPABASE_URL}/rest/v1/chat_leads"
                    f"?email=eq.{_up.quote(email)}&select=id,n_messages")
        req = urllib.request.Request(find_url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        resp = urllib.request.urlopen(req, timeout=8)
        existing = json.loads(resp.read().decode("utf-8"))

        now_iso = datetime.utcnow().isoformat()

        if existing:
            # Atualiza existente
            lead_id = existing[0]["id"]
            n_msgs = (existing[0].get("n_messages") or 0) + 1
            upd_url = f"{SUPABASE_URL}/rest/v1/chat_leads?id=eq.{lead_id}"
            upd_payload = {
                "name": name,
                "phone": phone or None,
                "n_messages": n_msgs,
                "last_message_at": now_iso,
            }
            if first_question:
                upd_payload["first_question"] = first_question[:500]
            body_bytes = json.dumps(upd_payload).encode("utf-8")
            upd_req = urllib.request.Request(upd_url, data=body_bytes, method="PATCH")
            upd_req.add_header("apikey", SUPABASE_KEY)
            upd_req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
            upd_req.add_header("Content-Type", "application/json")
            upd_req.add_header("Prefer", "return=minimal")
            urllib.request.urlopen(upd_req, timeout=8)
            return {"status": "ok", "lead_id": lead_id, "new": False}

        # Insere novo
        ins_payload = {
            "name": name,
            "email": email,
            "phone": phone or None,
            "source_page": source_page,
            "user_agent": user_agent,
            "first_question": first_question[:500],
            "n_messages": 1,
        }
        ins_url = f"{SUPABASE_URL}/rest/v1/chat_leads"
        body_bytes = json.dumps(ins_payload).encode("utf-8")
        ins_req = urllib.request.Request(ins_url, data=body_bytes, method="POST")
        ins_req.add_header("apikey", SUPABASE_KEY)
        ins_req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        ins_req.add_header("Content-Type", "application/json")
        ins_req.add_header("Prefer", "return=representation")
        ins_resp = urllib.request.urlopen(ins_req, timeout=8)
        inserted = json.loads(ins_resp.read().decode("utf-8"))
        return {
            "status": "ok",
            "lead_id": inserted[0]["id"] if inserted else None,
            "new": True,
        }
    except Exception as e:
        print(f"[chat_lead] erro: {e}")
        return {"error": str(e)}


@app.get("/api/admin/chat/leads")
async def admin_list_chat_leads(request: Request, limit: int = 200):
    """Lista leads do chat pra painel admin. Requer auth admin."""
    _require_admin(request)
    try:
        url = (f"{SUPABASE_URL}/rest/v1/chat_leads"
               f"?select=*&order=last_message_at.desc&limit={int(limit)}")
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        resp = urllib.request.urlopen(req, timeout=15)
        return {"leads": json.loads(resp.read().decode("utf-8"))}
    except Exception as e:
        return {"error": str(e)}


# ══════════════════════════════════════════════════
#  Formulário de contato (público)
# ══════════════════════════════════════════════════

@app.post("/api/contact")
async def submit_contact(request: Request):
    """Recebe envio do formulário de contato (JSON ou multipart/form-data).

    Aceita arquivo opcional (campo 'file', máx 10MB) que vai pro Supabase
    Storage no bucket 'contact-attachments'. URL pública é salva junto.
    """
    content_type = (request.headers.get("content-type") or "").lower()
    upload_file = None
    upload_filename = None

    # Parse: JSON ou multipart
    if "multipart/form-data" in content_type:
        try:
            form = await request.form()
        except Exception as e:
            return {"ok": False, "error": f"Form inválido: {e}"}
        body = dict(form)
        # Extrai arquivo se vier
        file_obj = form.get("file")
        if file_obj is not None and hasattr(file_obj, "read"):
            try:
                upload_filename = (getattr(file_obj, "filename", "") or "anexo.bin")[:200]
                upload_file = await file_obj.read()
                if len(upload_file) > 10 * 1024 * 1024:
                    return {"ok": False, "error": "Arquivo grande demais (máx 10MB)"}
            except Exception as e:
                print(f"[contact] erro lendo arquivo: {e}")
                upload_file = None
    else:
        try:
            body = await request.json()
        except Exception:
            return {"ok": False, "error": "JSON inválido"}

    name    = str(body.get("name", "")).strip()[:200]
    email   = str(body.get("email", "")).strip().lower()[:200]
    phone   = str(body.get("phone", "")).strip()[:50]
    msg_type = str(body.get("type", "duvida")).strip().lower()
    subject = str(body.get("subject", "")).strip()[:300]
    message = str(body.get("message", "")).strip()[:5000]

    if not name or not email or not message:
        return {"ok": False, "error": "Nome, email e mensagem são obrigatórios"}
    if "@" not in email or "." not in email:
        return {"ok": False, "error": "Email inválido"}
    if msg_type not in ("reclamacao", "sugestao", "duvida", "parceria", "elogio", "outro"):
        msg_type = "outro"

    # Metadados de origem
    source_page = request.headers.get("referer", "")[:500]
    user_agent  = request.headers.get("user-agent", "")[:500]

    # Upload do anexo (se houver) pro Supabase Storage
    attachment_url = None
    attachment_size_kb = None
    if upload_file and upload_filename:
        try:
            import uuid as _uuid
            ext = ""
            if "." in upload_filename:
                ext = "." + upload_filename.rsplit(".", 1)[-1][:10]
            object_key = f"contact/{datetime.utcnow().strftime('%Y%m')}/{_uuid.uuid4()}{ext}"

            up_url = f"{SUPABASE_URL}/storage/v1/object/contact-attachments/{object_key}"
            req = urllib.request.Request(up_url, data=upload_file, method="POST")
            req.add_header("apikey", SUPABASE_KEY)
            req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
            # Detecta content type básico
            ct_map = {
                ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
                ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ".xls": "application/vnd.ms-excel", ".csv": "text/csv",
                ".doc": "application/msword",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".txt": "text/plain",
            }
            req.add_header("Content-Type", ct_map.get(ext.lower(), "application/octet-stream"))
            req.add_header("x-upsert", "true")
            urllib.request.urlopen(req, timeout=30)

            attachment_url = f"{SUPABASE_URL}/storage/v1/object/public/contact-attachments/{object_key}"
            attachment_size_kb = round(len(upload_file) / 1024)
            print(f"[contact] anexo enviado: {attachment_url}")
        except Exception as e:
            print(f"[contact] erro upload Storage: {e}")
            # Não falha a request por causa do anexo — segue sem ele

    payload = {
        "name": name,
        "email": email,
        "phone": phone or None,
        "message_type": msg_type,
        "subject": subject or None,
        "message": message,
        "source_page": source_page or None,
        "user_agent": user_agent or None,
        "status": "new",
        "attachment_url": attachment_url,
        "attachment_filename": upload_filename if attachment_url else None,
        "attachment_size_kb": attachment_size_kb,
    }

    ok = _supabase_insert("contact_messages", payload)
    if not ok:
        return {"ok": False, "error": "Falha ao salvar mensagem"}

    print(f"[contact] nova mensagem: {email} ({msg_type}) — {subject[:50]}")
    return {"ok": True, "message": "Mensagem recebida! Vamos responder em breve."}


@app.get("/api/admin/contact-messages")
async def admin_list_contact_messages(request: Request, limit: int = 200, status: str = ""):
    """Lista mensagens de contato pro admin. Requer auth admin."""
    _require_admin(request)
    try:
        url = f"{SUPABASE_URL}/rest/v1/contact_messages?select=*&order=created_at.desc&limit={int(limit)}"
        if status:
            url += f"&status=eq.{status}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        resp = urllib.request.urlopen(req, timeout=15)
        return {"messages": json.loads(resp.read().decode("utf-8"))}
    except Exception as e:
        return {"error": str(e)}

PUBLIC_CHAT_SYSTEM_PROMPT = """Você é o assistente virtual do AI.arq — uma plataforma brasileira que acelera o levantamento de quantitativos em projetos de arquitetura.

**Sua missão:** responder perguntas de visitantes do site (ai.arq.br) com honestidade e brevidade. Você ajuda a tirar dúvidas sobre o produto, preços e LGPD. Foco em conversão mas SEM vender gordura — o AI.arq é honesto sobre o que faz e o que não faz.

## O QUE O AI.ARQ FAZ

1. **Quantitativo a partir de CAD** — usuário envia PDF/DWG/DXF, IA lê e em ~5 min gera planilha Excel com 18 disciplinas (demolição, alvenaria, elétrica, hidráulica, pintura, pisos, forro, etc). Cada item cita a prancha de origem e tem código de cor:
   - BRANCO = medido direto do CAD (confiável)
   - LARANJA = estimado pela IA (revisar antes de usar)
   - CINZA = metadado do projeto
   - ROXO = custo indireto / gestão (checklist — não sai no CAD mas toda obra tem)

2. **Memória técnica SINAPI + TCPO BIM** — aba extra na planilha com referência oficial pra cada item (composição + insumos + coeficientes). Base carregada: 10.284 composições SINAPI + 54.529 insumos, e 1.333 composições TCPO BIM + 6.733 insumos.

3. **Comparativo de fornecedores** (opcional) — depois que o usuário recebe propostas dos fornecedores, pode fazer upload das planilhas deles e o AI.arq gera XLSX + PPT executivo com ranking, discrepâncias, itens esquecidos.

4. **PPT com a marca do escritório** — logo e cor do escritório aparecem na apresentação. Envio direto pro cliente final via WhatsApp.

## O QUE O AI.ARQ **NÃO** FAZ

- **NÃO precifica** e **NÃO fecha orçamento** — a planilha sai SEM preços preenchidos. Precificação é trabalho do orçamentista do usuário (humano, não IA).
- **NÃO substitui profissional habilitado** — é ferramenta de apoio ao levantamento inicial. Revisão por engenheiro/orçamentista é obrigatória.
- **NÃO adivinha o que não está no CAD** — itens estimados são sinalizados em laranja pra revisão.

## PREÇOS

- **1º projeto: GRÁTIS**
- **Pequeno** (1-5 pranchas): R$ 97
- **Médio** (6-10 pranchas): R$ 157 (mais comum — -19% por prancha vs Pequeno)
- **Grande** (11-20 pranchas): R$ 247 (-36% por prancha)
- **Acima de 20**: R$ 247 + R$ 10/prancha extra
- Pagamento via Stripe (cartão/PIX). **Sem mensalidade.** Paga só quando usa.
- Todas as outras features (memória técnica, comparativo, PPT, cashback) estão INCLUÍDAS no preço do projeto. Sem taxas extras. Cada feature é OPCIONAL — use só se fizer sentido.

## CASHBACK

Programa granular — cada ação que ajuda a calibrar a IA gera crédito automático abatível no próximo projeto:
- Revisão inline (validar item no navegador): crédito por ação
- Upload de planilha revisada offline: +R$ 20
- Upload de cotação de fornecedor: +R$ 5
- Feedback NPS: crédito ao responder

## LGPD E PRIVACIDADE

- Usuário é controlador LGPD dos dados do cliente final (nome, telefone, endereço). AI.arq é operador.
- Valores em R$ de cotações **NUNCA** viram referência pra outros projetos. Só métricas adimensionais anônimas (coeficientes de variação, share MAT/MO) alimentam a base de mercado.
- Dados isolados por projeto. Arquivos processados com criptografia. Transferências internacionais (Anthropic/Supabase/Render/Stripe) com bases legais do art. 33 da LGPD.
- Detalhes em ai.arq.br/privacidade.html e ai.arq.br/termos.html

## COMO USAR

1. Crie conta (grátis) em ai.arq.br → login
2. No dashboard: clique "Novo projeto" → faça upload dos PDFs/DWGs
3. Aguarde ~5 min o processamento
4. Baixe a planilha ou revise no navegador (ganha cashback)
5. Mande pros fornecedores, receba as propostas
6. (Opcional) Faça upload das propostas no projeto → gere comparativo + PPT

## TOM DE VOZ

- Responda em **português brasileiro, informal-profissional**. Sem jargão técnico desnecessário. Sem "caro cliente".
- Seja **objetivo e curto** (2-4 frases geralmente é o suficiente).
- Se a dúvida for específica e técnica (ex: "como o piso é calculado?"), explique resumido e aponte pro FAQ completo: ai.arq.br/faq.html
- Se o usuário quiser testar: direcione pra ai.arq.br → "Comece Grátis"
- Se não souber a resposta com certeza, DIGA QUE NÃO SABE e sugira contato: contato@ai.arq.br

## NÃO INVENTE

Se perguntarem sobre coisas que você não tem certeza (integrações específicas, recursos futuros, planos corporativos), responda honestamente que não tem essa informação e sugira email de contato. NUNCA invente funcionalidades.
"""


@app.post("/api/public/chat")
async def public_chat(request: Request):
    """Chat público do widget no site — sem auth, com rate limit por IP.

    Usado pra visitantes tirarem dúvidas sobre o produto antes de cadastrar.
    """
    # Rate limit: 20 msgs / 10min por IP
    # FIX 2026-05-14: parênteses pra precedência correta de `or ... if ... else`
    # (antes parseava como `(A or B) if C else D` e podia explodir quando request.client é None).
    fwd = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    client_ip = fwd or (request.client.host if request.client else "unknown")
    now_ts = datetime.utcnow().timestamp()
    history = _PUBLIC_CHAT_HITS.get(client_ip, [])
    history = [t for t in history if now_ts - t < 600]  # últimos 10min
    if len(history) >= 20:
        return {
            "error": "rate_limit",
            "message": "Muitas mensagens em pouco tempo. Espere uns minutos e tente de novo.",
        }
    history.append(now_ts)
    _PUBLIC_CHAT_HITS[client_ip] = history

    # FIX 2026-05-14: anti memory-leak. Periodicamente limpa IPs cuja última
    # hit foi há mais de 10min. Sem isso, o dict cresce pra sempre (cada IP
    # novo = entrada nova nunca limpa) e esgota RAM do Render free tier.
    # Trigger barato: 1× a cada ~50 requests.
    if len(_PUBLIC_CHAT_HITS) > 50 and (int(now_ts) % 50) == 0:
        stale = [ip for ip, hits in _PUBLIC_CHAT_HITS.items()
                 if not hits or (now_ts - max(hits)) > 600]
        for ip in stale:
            _PUBLIC_CHAT_HITS.pop(ip, None)

    try:
        body = await request.json()
    except Exception:
        body = {}

    messages = body.get("messages", [])
    if not isinstance(messages, list) or not messages:
        return {"error": "Precisa mandar { messages: [{role, content}, ...] }"}

    # Sanitização: limita tamanho e quantidade de turns
    messages = messages[-10:]  # só os últimos 10 turns (proteção contra prompt inflation)
    clean_msgs = []
    for m in messages:
        role = m.get("role")
        content = str(m.get("content", ""))[:2000]  # max 2k chars por msg
        if role in ("user", "assistant") and content.strip():
            clean_msgs.append({"role": role, "content": content})

    if not clean_msgs:
        return {"error": "Nenhuma mensagem válida"}

    # Chama Claude Haiku (mais barato e rápido pra chat de vendas)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"error": "Chat indisponível no momento."}

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=600,
            system=PUBLIC_CHAT_SYSTEM_PROMPT,
            messages=clean_msgs,
        )
        reply = resp.content[0].text if resp.content else "Desculpe, não consegui responder agora."
        return {
            "status": "ok",
            "reply": reply,
            "tokens_used": (resp.usage.input_tokens if resp.usage else 0) + (resp.usage.output_tokens if resp.usage else 0),
        }
    except Exception as e:
        print(f"[public_chat] erro: {e}")
        return {
            "error": "Erro temporário",
            "message": "Desculpe, algo deu errado. Tente de novo em instantes ou mande e-mail pra contato@ai.arq.br",
        }


# ═══════════════════════════════════════════════════════════════
#  COTAÇÕES DE FORNECEDORES (supplier quotes)
# ═══════════════════════════════════════════════════════════════

@app.post("/api/projects/{job_id}/quotes/upload")
async def upload_supplier_quote(
    request: Request,
    job_id: str,
    supplier_name: str = Form(...),
    file: UploadFile = File(...),
    parser_mode: str = Form("auto"),
    user_id: str = Form(""),
):
    """Recebe uma planilha de orçamento de fornecedor, parseia e salva no banco.

    Quem chama tem que ser o dono do projeto (ou admin) — senão atacante
    sobe cotação no projeto alheio + ganha R$5 de cashback no nome dele.
    """
    # Valida que JWT == dono do projeto (ou admin)
    _require_project_owner(request, job_id)
    # Se passou user_id no Form, ele tem que casar com o JWT (cashback fica
    # registrado no nome certo, não no que o atacante quiser)
    if user_id:
        jwt_user = _get_user_from_request(request)
        if jwt_user and jwt_user.get("email", "").lower() != ADMIN_EMAIL:
            if jwt_user.get("id") != user_id:
                raise HTTPException(403, "user_id não corresponde ao token")

    try:
        from supplier_quote_parser import parse_supplier_quote
    except ImportError:
        return {"error": "supplier_quote_parser indisponível"}

    # Salva temporariamente (anti path-traversal)
    work_dir = os.path.join(WORK_DIR, job_id, "quotes")
    os.makedirs(work_dir, exist_ok=True)
    safe_name = _safe_local_filename(file.filename)
    temp_path = os.path.join(work_dir, safe_name)
    with open(temp_path, "wb") as f:
        f.write(await file.read())

    # Parseia
    parsed = parse_supplier_quote(temp_path, supplier_name, mode=parser_mode)
    if "error" in parsed:
        return {"status": "error", "error": parsed["error"]}

    # Grava no Supabase
    payload = {
        "job_id": job_id,
        "supplier_name": supplier_name,
        "original_filename": file.filename,
        "storage_path": temp_path,
        "parser_mode": parsed.get("parser_mode_used", "strict"),
        "n_items_quoted": parsed["n_items_quoted"],
        "total_bruto": parsed["total_bruto"],
        "total_material": parsed["total_material"],
        "total_mao_obra": parsed["total_mao_obra"],
        "items": parsed["items"],
        "status": "parsed",
        "uploaded_by": user_id or "",
    }

    try:
        url = f"{SUPABASE_URL}/rest/v1/project_supplier_quotes"
        body = json.dumps(payload, default=str).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Prefer", "return=representation")
        resp = urllib.request.urlopen(req, timeout=20)
        inserted = json.loads(resp.read().decode("utf-8"))
        quote_id = inserted[0]["id"] if inserted else None
    except Exception as e:
        return {"status": "error", "error": f"Erro ao gravar: {e}"}

    # Cria evento de cashback: R$ 10 por cotação, MAX 3 cotações por projeto.
    # Política nova (2026-05-13): subiu de R$ 5 → R$ 10 mas com cap de 3 — incentiva
    # diversificação de cotações sem virar farm.
    cashback_status = None
    if user_id:
        # Conta quantos uploads já tiveram cashback nesse projeto
        try:
            cnt_url = (f"{SUPABASE_URL}/rest/v1/project_cashback_events"
                       f"?job_id=eq.{job_id}"
                       f"&event_type=eq.supplier_quote_upload"
                       f"&select=id")
            cnt_req = urllib.request.Request(cnt_url, method="GET")
            cnt_req.add_header("apikey", SUPABASE_KEY)
            cnt_req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
            cnt_resp = urllib.request.urlopen(cnt_req, timeout=8)
            existing_count = len(json.loads(cnt_resp.read().decode("utf-8")))
        except Exception:
            existing_count = 0

        if existing_count >= 3:
            cashback_status = "capped"
        else:
            try:
                cb_payload = {
                    "job_id": job_id,
                    "user_id": user_id,
                    "event_type": "supplier_quote_upload",
                    "credit_cents": 1000,  # R$ 10 por cotação (max 3 = R$ 30)
                    "description": f"Upload cotação {supplier_name}",
                    "ref_id": quote_id,
                    "approved_at": datetime.utcnow().isoformat(),
                    "approved_by": "auto",
                }
                cb_url = f"{SUPABASE_URL}/rest/v1/project_cashback_events"
                cb_body = json.dumps(cb_payload).encode("utf-8")
                cb_req = urllib.request.Request(cb_url, data=cb_body, method="POST")
                cb_req.add_header("apikey", SUPABASE_KEY)
                cb_req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
                cb_req.add_header("Content-Type", "application/json")
                cb_req.add_header("Prefer", "return=minimal")
                urllib.request.urlopen(cb_req, timeout=8)
                cashback_status = "credited"
            except Exception:
                cashback_status = "error"  # best-effort, não bloqueia upload

    return {
        "status": "ok",
        "quote_id": quote_id,
        "supplier_name": supplier_name,
        "n_items_quoted": parsed["n_items_quoted"],
        "total_bruto": parsed["total_bruto"],
        "parser_mode_used": parsed.get("parser_mode_used"),
        "cashback": cashback_status,  # 'credited' | 'capped' | 'error' | None
    }


@app.get("/api/projects/{job_id}/quotes")
async def list_supplier_quotes(job_id: str, request: Request):
    _require_project_owner(request, job_id)
    """Lista cotações de fornecedores de um projeto."""
    try:
        url = (f"{SUPABASE_URL}/rest/v1/project_supplier_quotes"
               f"?job_id=eq.{job_id}"
               f"&select=id,supplier_name,original_filename,parser_mode,"
               f"n_items_quoted,total_bruto,total_material,total_mao_obra,"
               f"status,uploaded_at"
               f"&order=uploaded_at.asc")
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        resp = urllib.request.urlopen(req, timeout=8)
        return {"quotes": json.loads(resp.read().decode("utf-8"))}
    except Exception as e:
        return {"error": str(e)}


@app.delete("/api/projects/{job_id}/quotes/{quote_id}")
async def delete_supplier_quote(job_id: str, quote_id: str, request: Request):
    _require_project_owner(request, job_id)
    """Remove uma cotação."""
    try:
        url = (f"{SUPABASE_URL}/rest/v1/project_supplier_quotes"
               f"?id=eq.{quote_id}&job_id=eq.{job_id}")
        req = urllib.request.Request(url, method="DELETE")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        urllib.request.urlopen(req, timeout=8)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/projects/{job_id}/quotes/compare")
async def compare_supplier_quotes(job_id: str, request: Request, include_reference: int = 1):
    _require_project_owner(request, job_id)
    """Compara todas as cotações de um projeto, gera XLSX+PPT, retorna URLs."""
    try:
        from supplier_quote_compare import (compare_quotes,
                                             generate_comparative_xlsx,
                                             generate_comparative_pptx)
    except ImportError:
        return {"error": "supplier_quote_compare indisponível"}

    # Busca quotes
    url = (f"{SUPABASE_URL}/rest/v1/project_supplier_quotes"
           f"?job_id=eq.{job_id}&select=*&order=uploaded_at.asc")
    req = urllib.request.Request(url, method="GET")
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        quotes_raw = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": f"erro buscando quotes: {e}"}

    if len(quotes_raw) < 2:
        return {"error": "precisa de pelo menos 2 cotações pra comparar"}

    # Converte pra formato esperado pelo compare
    quotes = []
    for q in quotes_raw:
        quotes.append({
            "supplier_name": q["supplier_name"],
            "n_items_quoted": q.get("n_items_quoted", 0),
            "total_bruto": float(q.get("total_bruto") or 0),
            "total_material": float(q.get("total_material") or 0),
            "total_mao_obra": float(q.get("total_mao_obra") or 0),
            "items": q.get("items") or [],
        })

    # Busca reference items do quantitativo original
    reference_items = None
    if include_reference:
        try:
            ref_url = (f"{SUPABASE_URL}/rest/v1/project_items"
                       f"?job_id=eq.{job_id}&select=description,unit,quantity"
                       f"&limit=500")
            ref_req = urllib.request.Request(ref_url, method="GET")
            ref_req.add_header("apikey", SUPABASE_KEY)
            ref_req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
            ref_resp = urllib.request.urlopen(ref_req, timeout=10)
            reference_items = json.loads(ref_resp.read().decode("utf-8"))
        except Exception:
            pass

    analysis = compare_quotes(quotes, reference_items=reference_items)

    # Busca project_clients + project data + logo do escritório pro cabeçalho
    project_name = ""
    architect_name = ""
    client_name = ""
    logo_url = ""
    project_user_id = ""
    try:
        pj_url = (f"{SUPABASE_URL}/rest/v1/projects"
                  f"?job_id=eq.{job_id}&select=project_name,user_name,user_id")
        pj_req = urllib.request.Request(pj_url, method="GET")
        pj_req.add_header("apikey", SUPABASE_KEY)
        pj_req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        pj_resp = urllib.request.urlopen(pj_req, timeout=8)
        pj_data = json.loads(pj_resp.read().decode("utf-8"))
        if pj_data:
            project_name = pj_data[0].get("project_name", "")
            architect_name = pj_data[0].get("user_name", "")
            project_user_id = pj_data[0].get("user_id", "")

        cl_url = (f"{SUPABASE_URL}/rest/v1/project_clients"
                  f"?job_id=eq.{job_id}&select=client_name,client_company")
        cl_req = urllib.request.Request(cl_url, method="GET")
        cl_req.add_header("apikey", SUPABASE_KEY)
        cl_req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        cl_resp = urllib.request.urlopen(cl_req, timeout=8)
        cl_data = json.loads(cl_resp.read().decode("utf-8"))
        if cl_data:
            client_name = cl_data[0].get("client_name", "")
            if cl_data[0].get("client_company"):
                client_name = f"{client_name} ({cl_data[0]['client_company']})" \
                    if client_name else cl_data[0]["client_company"]

        # Logo e cor de marca do escritório (perfil do dono do projeto)
        if project_user_id:
            pr_url = (f"{SUPABASE_URL}/rest/v1/profiles"
                       f"?user_id=eq.{project_user_id}"
                       f"&select=logo_url,company,company_brand_color")
            pr_req = urllib.request.Request(pr_url, method="GET")
            pr_req.add_header("apikey", SUPABASE_KEY)
            pr_req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
            pr_resp = urllib.request.urlopen(pr_req, timeout=8)
            pr_data = json.loads(pr_resp.read().decode("utf-8"))
            if pr_data:
                logo_url = pr_data[0].get("logo_url", "") or ""
                brand_color = pr_data[0].get("company_brand_color", "") or ""
                if not architect_name and pr_data[0].get("company"):
                    architect_name = pr_data[0]["company"]
            else:
                brand_color = ""
        else:
            brand_color = ""
    except Exception:
        brand_color = ""

    # Download logo temporariamente pra embutir no PPT
    logo_path = None
    if logo_url:
        try:
            work_dir_lg = os.path.join(WORK_DIR, job_id)
            os.makedirs(work_dir_lg, exist_ok=True)
            logo_path = os.path.join(work_dir_lg, "logo_escritorio.png")
            lg_req = urllib.request.Request(logo_url, method="GET")
            with urllib.request.urlopen(lg_req, timeout=10) as resp:
                with open(logo_path, "wb") as f:
                    f.write(resp.read())
        except Exception:
            logo_path = None

    # Gera XLSX
    work_dir = os.path.join(WORK_DIR, job_id)
    os.makedirs(work_dir, exist_ok=True)
    xlsx_path = os.path.join(work_dir, f"comparativo_{job_id}.xlsx")
    generate_comparative_xlsx(
        analysis, xlsx_path,
        project_name=project_name,
        architect_name=architect_name,
        client_name=client_name,
    )

    # Gera PPT
    pptx_path = os.path.join(work_dir, f"comparativo_{job_id}.pptx")
    try:
        generate_comparative_pptx(
            analysis, pptx_path,
            project_name=project_name,
            architect_name=architect_name,
            client_name=client_name,
            logo_path=logo_path,
            brand_color_hex=brand_color,
        )
        pptx_ok = True
    except Exception as e:
        print(f"[quotes/compare] erro PPT: {e}")
        pptx_ok = False

    # ═══ ALIMENTA MOTOR ANONIMAMENTE ═══
    # Extrai heurísticas do comparativo (sem dados do projeto) e insere
    # em market_heuristics. Loop de aprendizado do motor.
    try:
        _extract_and_save_heuristics(analysis, "office")
    except Exception as e:
        print(f"[quotes/compare] erro extração heurísticas: {e}")

    return {
        "status": "ok",
        "xlsx_url": f"/api/projects/{job_id}/quotes/download/xlsx",
        "pptx_url": f"/api/projects/{job_id}/quotes/download/pptx" if pptx_ok else None,
        "summary": {
            "n_suppliers": len(analysis["suppliers"]),
            "ranking": [{"supplier": s, "paired_total": t}
                        for s, t in analysis["ranking"]],
            "n_discrepancies_above_100pct":
                len([d for d in analysis["biggest_discrepancies"]
                     if d["pct_diff"] > 100]),
            "reference_check_summary":
                analysis.get("reference_check", {}).get("summary")
                if analysis.get("reference_check") else None,
        },
    }


@app.get("/api/projects/{job_id}/quotes/download/xlsx")
async def download_quotes_xlsx(job_id: str, request: Request):
    _require_project_owner(request, job_id)
    """Baixa o comparativo XLSX gerado."""
    path = os.path.join(WORK_DIR, job_id, f"comparativo_{job_id}.xlsx")
    if not os.path.exists(path):
        return {"error": "comparativo não gerado ainda — chamar /quotes/compare primeiro"}
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"comparativo_fornecedores_{job_id}.xlsx",
    )


@app.get("/api/projects/{job_id}/quotes/download/pptx")
async def download_quotes_pptx(job_id: str, request: Request):
    _require_project_owner(request, job_id)
    """Baixa o comparativo PPT gerado."""
    path = os.path.join(WORK_DIR, job_id, f"comparativo_{job_id}.pptx")
    if not os.path.exists(path):
        return {"error": "PPT não gerado ainda — chamar /quotes/compare primeiro"}
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=f"comparativo_fornecedores_{job_id}.pptx",
    )


def _extract_and_save_heuristics(analysis: dict, typology: str = "office"):
    """Extrai heurísticas adimensionais do comparativo e salva em market_heuristics.

    REGRA DURA: zero valores absolutos, zero nomes de projeto/fornecedor.
    Fornecedores são anonimizados como fornecedor_1/2/3 (ordem aleatória).

    Inclui:
      - dispersion: CV por categoria dos top itens divergentes
      - coverage_pattern: contagem por categoria (anonimizada)
      - mat_mo_share: ratio médio MAT/MO por categoria
    """
    from collections import defaultdict
    from statistics import mean, stdev
    import unicodedata
    import re as _re
    import hashlib
    import random

    def _norm(s):
        if not s: return ""
        s = str(s).strip().lower()
        s = unicodedata.normalize("NFKD", s)
        s = "".join(c for c in s if not unicodedata.combining(c))
        s = _re.sub(r"[^\w\s]", " ", s)
        return _re.sub(r"\s+", " ", s).strip()

    categorias_kw = {
        "demolicao": ["demolicao", "remocao", "retirada", "demolir"],
        "drywall": ["drywall", "gesso", "septo", "sept"],
        "eletrica": ["eletr", "tomada", "interruptor", "luminaria"],
        "hidraulica": ["hidr", "tubulacao", "bacia", "torneira"],
        "piso": ["piso", "carpete", "laminado", "vinil"],
        "pintura": ["pintura", "tinta", "selador", "verniz"],
        "forro": ["forro"],
        "esquadria": ["porta", "janela", "esquadria"],
        "ar_condicionado": ["ar condicionado", "hvac", "condicionado"],
        "mobiliario": ["mobiliar", "armario", "marcenar"],
        "preliminares": ["mobilizacao", "canteiro", "tapume", "protecao"],
    }

    def _cat(desc):
        n = _norm(desc)
        for cat, keys in categorias_kw.items():
            for k in keys:
                if k in n:
                    return cat
        return "outros"

    # Source hash anônimo pra não repetir dados
    ranking_key = "_".join(sorted(analysis["paired_totals"].keys()))
    source = "auto_" + hashlib.md5(ranking_key.encode()).hexdigest()[:10]

    rows = []
    n_sup = len(analysis["suppliers"])

    # 1. Dispersão por categoria
    cat_disp = defaultdict(list)
    for d in analysis["biggest_discrepancies"][:30]:
        cat = _cat(d["desc"])
        cat_disp[cat].append(d["pct_diff"] / 100)  # normaliza pra 0-1

    for cat, cvs in cat_disp.items():
        if len(cvs) < 1:
            continue
        avg_cv = mean(cvs)
        if avg_cv < 0.2:
            continue
        rows.append({
            "heuristic_type": "dispersion",
            "typology": typology,
            "category": cat,
            "unit": "",
            "keywords": "",
            "metric_name": "cv_total",
            "metric_value": round(avg_cv, 3),
            "stddev": round(stdev(cvs), 3) if len(cvs) > 1 else 0,
            "n_observations": len(cvs),
            "source_anonimo": source,
        })

    # 2. Cobertura por categoria (n itens por fornecedor anônimo)
    cov_by_cat = defaultdict(lambda: defaultdict(int))
    suppliers_shuffled = list(analysis["suppliers"])
    random.shuffle(suppliers_shuffled)  # anonimiza posição
    sup_alias = {s: i + 1 for i, s in enumerate(suppliers_shuffled)}

    for m in analysis["merged_items"]:
        cat = _cat(m["desc"])
        for sup in analysis["suppliers"]:
            if m.get(sup) and m[sup].get("total"):
                cov_by_cat[cat][sup_alias[sup]] += 1

    for cat, supcov in cov_by_cat.items():
        cobertura = sum(1 for i in range(1, n_sup + 1) if supcov.get(i, 0) > 0)
        rows.append({
            "heuristic_type": "coverage_pattern",
            "typology": typology,
            "category": cat,
            "unit": "",
            "keywords": "",
            "metric_name": "cobertura_completa",
            "metric_value": cobertura,
            "stddev": 0,
            "n_observations": n_sup,
            "source_anonimo": source,
        })

    # 3. Share MAT/MO por categoria
    cat_shares = defaultdict(list)
    for m in analysis["merged_items"]:
        cat = _cat(m["desc"])
        for sup in analysis["suppliers"]:
            it = m.get(sup)
            if not it or not it.get("qtd"):
                continue
            mat = (it.get("unit_mat") or 0) * it["qtd"]
            mo = (it.get("unit_mo") or 0) * it["qtd"]
            soma = mat + mo
            if soma <= 0:
                continue
            cat_shares[cat].append(mat / soma)

    for cat, shares in cat_shares.items():
        if len(shares) < 3:
            continue
        share_mat_avg = mean(shares)
        stddev_mat = stdev(shares) if len(shares) > 1 else 0
        rows.append({
            "heuristic_type": "mat_mo_share",
            "typology": typology,
            "category": cat,
            "unit": "",
            "keywords": "",
            "metric_name": "share_mat",
            "metric_value": round(share_mat_avg, 3),
            "stddev": round(stddev_mat, 3),
            "n_observations": len(shares),
            "source_anonimo": source,
        })
        rows.append({
            "heuristic_type": "mat_mo_share",
            "typology": typology,
            "category": cat,
            "unit": "",
            "keywords": "",
            "metric_name": "share_mo",
            "metric_value": round(1 - share_mat_avg, 3),
            "stddev": 0,
            "n_observations": len(shares),
            "source_anonimo": source,
        })

    if not rows:
        return

    # Audita antes de inserir
    for r in rows:
        v = r.get("metric_value")
        if v and abs(v) > 100 and r["metric_name"] not in (
                "cobertura_completa",) and not r["metric_name"].startswith("n_itens"):
            print(f"[heuristics] ALERTA valor suspeito: {r}")
            return  # não insere se tem valor absoluto vazado

    # Insere
    try:
        url = f"{SUPABASE_URL}/rest/v1/market_heuristics"
        body = json.dumps(rows).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Prefer", "return=minimal")
        urllib.request.urlopen(req, timeout=15)
        print(f"[heuristics] +{len(rows)} métricas anônimas inseridas")
    except Exception as e:
        print(f"[heuristics] erro insert: {e}")


# ═══════════════════════════════════════════════════════════════
#  UPLOAD DE PLANILHA REVISADA (cashback)
# ═══════════════════════════════════════════════════════════════

@app.post("/api/projects/{job_id}/revised-sheet/upload")
async def upload_revised_sheet(
    request: Request,
    job_id: str,
    file: UploadFile = File(...),
    user_id: str = Form(""),
):
    """Recebe planilha revisada offline. Salva na pasta do job e dá cashback.

    Dono do projeto (ou admin) apenas — senão atacante ganha R$20 de
    cashback no nome de outro user.
    """
    _require_project_owner(request, job_id)
    if user_id:
        jwt_user = _get_user_from_request(request)
        if jwt_user and jwt_user.get("email", "").lower() != ADMIN_EMAIL:
            if jwt_user.get("id") != user_id:
                raise HTTPException(403, "user_id não corresponde ao token")

    # Salva o arquivo (anti path-traversal)
    work_dir = os.path.join(WORK_DIR, job_id, "revised")
    os.makedirs(work_dir, exist_ok=True)
    safe_name = _safe_local_filename(file.filename)
    dst = os.path.join(work_dir, safe_name)
    with open(dst, "wb") as f:
        f.write(await file.read())

    # Evento de cashback: R$ 30 (2026-05-13: subiu de R$ 20 → R$ 30 pra
    # incentivar mais uploads de planilha revisada — feedback alimenta calibração)
    credit_cents = 3000
    if user_id:
        try:
            cb_payload = {
                "job_id": job_id,
                "user_id": user_id,
                "event_type": "planilha_upload",
                "credit_cents": credit_cents,
                "description": f"Upload planilha revisada ({file.filename})",
                "approved_at": datetime.utcnow().isoformat(),
                "approved_by": "auto",
            }
            cb_url = f"{SUPABASE_URL}/rest/v1/project_cashback_events"
            cb_body = json.dumps(cb_payload).encode("utf-8")
            cb_req = urllib.request.Request(cb_url, data=cb_body, method="POST")
            cb_req.add_header("apikey", SUPABASE_KEY)
            cb_req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
            cb_req.add_header("Content-Type", "application/json")
            cb_req.add_header("Prefer", "return=minimal")
            urllib.request.urlopen(cb_req, timeout=8)
        except Exception as e:
            print(f"[revised-sheet] erro cashback: {e}")

    return {
        "status": "ok",
        "filename": file.filename,
        "credit_cents": credit_cents,
    }


# ═══════════════════════════════════════════════════════════════
#  CASHBACK EVENTS POR PROJETO
# ═══════════════════════════════════════════════════════════════

@app.get("/api/user/{user_id}/cashback-all")
async def get_user_cashback_all(request: Request, user_id: str):
    """Retorna cashback agregado de TODOS os projetos do usuário.

    Usa pra mostrar o resumo na tela de cashback (total geral + por projeto).
    Só dono (ou admin) — saldo de cashback é dado financeiro.
    """
    jwt_user = _get_user_from_request(request)
    if not jwt_user:
        raise HTTPException(401, "Autenticação requerida")
    if jwt_user.get("id") != user_id and jwt_user.get("email", "").lower() != ADMIN_EMAIL:
        raise HTTPException(403, "Só é possível consultar seu próprio cashback")
    try:
        # Busca todos eventos do user
        url = (f"{SUPABASE_URL}/rest/v1/project_cashback_events"
               f"?user_id=eq.{user_id}"
               f"&select=*&order=created_at.desc&limit=1000")
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        resp = urllib.request.urlopen(req, timeout=8)
        events = json.loads(resp.read().decode("utf-8"))

        # Busca nome dos projetos envolvidos
        job_ids = list({e["job_id"] for e in events})
        projects_map = {}
        if job_ids:
            ids_filter = ",".join(f'"{j}"' for j in job_ids)
            pj_url = (f"{SUPABASE_URL}/rest/v1/projects"
                      f"?job_id=in.({','.join(job_ids)})&select=job_id,project_name")
            pj_req = urllib.request.Request(pj_url, method="GET")
            pj_req.add_header("apikey", SUPABASE_KEY)
            pj_req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
            try:
                pj_resp = urllib.request.urlopen(pj_req, timeout=8)
                for p in json.loads(pj_resp.read().decode("utf-8")):
                    projects_map[p["job_id"]] = p.get("project_name", "Projeto sem nome")
            except Exception:
                pass

        # Agrupa por projeto
        from collections import defaultdict
        by_proj = defaultdict(lambda: {
            "job_id": "", "project_name": "", "total_cents": 0,
            "n_events": 0, "event_types": set(),
        })
        for e in events:
            p = by_proj[e["job_id"]]
            p["job_id"] = e["job_id"]
            p["project_name"] = projects_map.get(e["job_id"], "Projeto sem nome")
            p["total_cents"] += e.get("credit_cents", 0)
            p["n_events"] += 1
            p["event_types"].add(e.get("event_type", ""))

        by_project_list = []
        for p in by_proj.values():
            by_project_list.append({
                "job_id": p["job_id"],
                "project_name": p["project_name"],
                "total_cents": p["total_cents"],
                "n_events": p["n_events"],
                "event_types": sorted(p["event_types"]),
            })
        by_project_list.sort(key=lambda x: -x["total_cents"])

        return {
            "total_cents": sum(e.get("credit_cents", 0) for e in events),
            "n_events": len(events),
            "by_project": by_project_list,
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/projects/{job_id}/cashback")
async def get_project_cashback(job_id: str):
    """Retorna eventos de cashback + total acumulado desse projeto."""
    try:
        url = (f"{SUPABASE_URL}/rest/v1/project_cashback_events"
               f"?job_id=eq.{job_id}"
               f"&select=*&order=created_at.desc")
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        resp = urllib.request.urlopen(req, timeout=8)
        events = json.loads(resp.read().decode("utf-8"))
        total_cents = sum(e.get("credit_cents", 0) for e in events)
        return {
            "events": events,
            "total_cents": total_cents,
            "total_reais": total_cents / 100.0,
            "count": len(events),
        }
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════
#  DADOS DO CLIENTE FINAL POR PROJETO
# ═══════════════════════════════════════════════════════════════

@app.get("/api/projects/{job_id}/client")
async def get_project_client(job_id: str, request: Request):
    """Retorna dados do cliente final de um projeto.

    LGPD: project_clients contém PII (nome, email, telefone, endereço).
    Só o dono do projeto (ou admin) pode ler.
    """
    _require_project_owner(request, job_id)
    try:
        url = (f"{SUPABASE_URL}/rest/v1/project_clients"
               f"?job_id=eq.{job_id}&select=*")
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        resp = urllib.request.urlopen(req, timeout=8)
        data = json.loads(resp.read().decode("utf-8"))
        return data[0] if data else {}
    except Exception as e:
        print(f"[get_project_client] erro: {e}")
        return {"error": "Falha interna ao buscar cliente"}


class ProjectMetaPayload(BaseModel):
    project_name: Optional[str] = None
    typology: Optional[str] = None
    address: Optional[str] = None
    phase: Optional[str] = None


@app.post("/api/projects/{job_id}/meta")
async def update_project_meta(job_id: str, payload: ProjectMetaPayload, request: Request):
    """Edita metadados do projeto: nome amigável, tipologia, endereço, fase.

    Só dono do projeto (ou admin) pode editar. Validação de tipologia, e
    aceita campos opcionais — só atualiza o que foi informado.
    """
    _require_project_owner(request, job_id)

    updates: dict = {}
    if payload.project_name is not None:
        name = payload.project_name.strip()
        if not name:
            raise HTTPException(400, "Nome do projeto não pode ser vazio")
        if len(name) > 120:
            raise HTTPException(400, "Nome do projeto excede 120 caracteres")
        updates["project_name"] = name
    if payload.typology is not None:
        if payload.typology not in _VALID_TYPOLOGIES:
            raise HTTPException(400, f"Tipologia inválida. Aceitas: {sorted(_VALID_TYPOLOGIES)}")
        updates["typology"] = payload.typology
    if payload.address is not None:
        updates["address"] = (payload.address or "").strip()[:240]
    if payload.phase is not None:
        updates["phase"] = (payload.phase or "").strip()[:60]

    if not updates:
        raise HTTPException(400, "Nenhum campo a atualizar")

    ok = _supabase_update("projects", "job_id", job_id, updates)
    if not ok:
        raise HTTPException(500, "Erro ao salvar no banco")
    return {"status": "ok", "job_id": job_id, "updated": list(updates.keys())}


@app.post("/api/projects/{job_id}/client")
async def upsert_project_client(
    job_id: str,
    request: Request,
    client_name: str = Form(""),
    client_company: str = Form(""),
    client_email: str = Form(""),
    client_phone: str = Form(""),
    address_site: str = Form(""),
    internal_notes: str = Form(""),
):
    """Cria ou atualiza dados do cliente final de um projeto.

    LGPD: só o dono do projeto (ou admin) pode escrever — antes era aberto,
    qualquer atacante podia sobrescrever PII alheia conhecendo o job_id.
    """
    _require_project_owner(request, job_id)
    payload = {
        "job_id": job_id,
        "client_name": client_name,
        "client_company": client_company,
        "client_email": client_email,
        "client_phone": client_phone,
        "address_site": address_site,
        "internal_notes": internal_notes,
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        # Checa se já existe
        check_url = (f"{SUPABASE_URL}/rest/v1/project_clients"
                     f"?job_id=eq.{job_id}&select=id")
        req = urllib.request.Request(check_url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        resp = urllib.request.urlopen(req, timeout=8)
        existing = json.loads(resp.read().decode("utf-8"))

        if existing:
            # UPDATE
            up_url = (f"{SUPABASE_URL}/rest/v1/project_clients"
                      f"?id=eq.{existing[0]['id']}")
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(up_url, data=body, method="PATCH")
            req.add_header("apikey", SUPABASE_KEY)
            req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
            req.add_header("Content-Type", "application/json")
            req.add_header("Prefer", "return=minimal")
            urllib.request.urlopen(req, timeout=8)
        else:
            # INSERT
            in_url = f"{SUPABASE_URL}/rest/v1/project_clients"
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(in_url, data=body, method="POST")
            req.add_header("apikey", SUPABASE_KEY)
            req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
            req.add_header("Content-Type", "application/json")
            req.add_header("Prefer", "return=minimal")
            urllib.request.urlopen(req, timeout=8)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}


# ── STRIPE CHECKOUT ──
@app.post("/api/estimate-price")
async def estimate_price(files: list[UploadFile] = File(...)):
    """Conta pranchas REAIS (páginas dentro de PDFs + layouts dentro de DWG/DXF)
    e devolve preço calculado. Usado antes do checkout pra mostrar preview
    transparente pro cliente.
    """
    if not files:
        raise HTTPException(400, "Nenhum arquivo enviado")
    tmp_dir = os.path.join(WORK_DIR, "_estimate_tmp", str(uuid.uuid4())[:8])
    os.makedirs(tmp_dir, exist_ok=True)
    saved_paths = []
    try:
        for f in files:
            if not f.filename:
                continue
            safe_name = _safe_local_filename(f.filename)
            p = os.path.join(tmp_dir, safe_name)
            with open(p, "wb") as out:
                out.write(await f.read())
            saved_paths.append(p)
        from pricing import estimate_for_files
        result = estimate_for_files(saved_paths)
        return {"status": "ok", **result}
    finally:
        # Limpa
        for p in saved_paths:
            try: os.remove(p)
            except Exception: pass
        try: os.rmdir(tmp_dir)
        except Exception: pass


# ═══════════════════════════════════════════════════════════════
#  Créditos de usuário (cashback, cupom, referral)
# ═══════════════════════════════════════════════════════════════

def _get_available_credits(user_id: str) -> list[dict]:
    """Retorna créditos disponíveis (used_at IS NULL e não expirados),
    ordenados por expires_at asc (expira primeiro consome primeiro)."""
    if not user_id or user_id == "anonymous":
        return []
    try:
        import urllib.request as _ur, urllib.parse as _up
        query = (f"select=id,amount_cents,source,source_ref,description,expires_at,created_at"
                 f"&user_id=eq.{_up.quote(user_id)}&used_at=is.null"
                 f"&order=expires_at.asc.nullslast,created_at.asc")
        url = f"{SUPABASE_URL}/rest/v1/user_credits?{query}"
        req = _ur.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("Accept", "application/json")
        resp = _ur.urlopen(req, timeout=8)
        rows = _json.loads(resp.read().decode("utf-8"))
        now = datetime.utcnow().isoformat()
        # Filtra expirados
        return [r for r in rows if not r.get("expires_at") or r["expires_at"] > now]
    except Exception as e:
        print(f"credits query error: {e}")
        return []


def _total_available_credit(user_id: str) -> int:
    """Soma dos créditos disponíveis em centavos."""
    return sum(int(c.get("amount_cents") or 0) for c in _get_available_credits(user_id))


def _grant_credit(user_id: str, amount_cents: int, source: str,
                  source_ref: str = "", description: str = "",
                  expires_days: Optional[int] = None) -> bool:
    """Cria um crédito novo pro user."""
    if not user_id or user_id == "anonymous" or amount_cents <= 0:
        return False
    record = {
        "user_id": user_id,
        "amount_cents": int(amount_cents),
        "source": source,
        "source_ref": (source_ref or "")[:100],
        "description": (description or "")[:200],
    }
    if expires_days:
        record["expires_at"] = (datetime.utcnow() + __import__("datetime").timedelta(
            days=expires_days)).isoformat() + "Z"
    return _supabase_insert("user_credits", record)


def _consume_credits(user_id: str, amount_cents: int, job_id: str) -> int:
    """Consome créditos até somar amount_cents. Marca used_at nos usados.
    Retorna o TOTAL efetivamente consumido (pode ser menor se saldo insuficiente)."""
    available = _get_available_credits(user_id)
    if not available:
        return 0
    consumed = 0
    now_iso = datetime.utcnow().isoformat() + "Z"
    import urllib.request as _ur
    for cr in available:
        if consumed >= amount_cents:
            break
        # Marca used_at
        try:
            url = f"{SUPABASE_URL}/rest/v1/user_credits?id=eq.{cr['id']}&used_at=is.null"
            body = _json.dumps({"used_at": now_iso, "used_on_job_id": job_id}).encode("utf-8")
            req = _ur.Request(url, data=body, method="PATCH")
            req.add_header("apikey", SUPABASE_KEY)
            req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
            req.add_header("Content-Type", "application/json")
            req.add_header("Prefer", "return=minimal")
            _ur.urlopen(req, timeout=8)
            consumed += int(cr.get("amount_cents") or 0)
        except Exception as e:
            print(f"consume credit error: {e}")
    return consumed


@app.get("/api/credits/balance")
async def credits_balance(user_id: str):
    """Retorna saldo de crédito disponível pro usuário."""
    credits = _get_available_credits(user_id)
    total = sum(int(c.get("amount_cents") or 0) for c in credits)
    return {
        "status": "ok",
        "user_id": user_id,
        "total_cents": total,
        "total_brl": round(total / 100, 2),
        "credits": credits,
    }


@app.post("/api/checkout")
async def create_checkout(request: Request, num_pranchas: int = 1, num_files: int = 0,
                          user_id: str = ""):
    """Cria sessão de pagamento no Stripe baseado em PRANCHAS REAIS.

    Aplica automaticamente créditos disponíveis do usuário (cashback,
    cupom, etc.) reduzindo o valor cobrado. Se o saldo cobrir 100%,
    pula Stripe e retorna direto `is_free=true`.

    Aceita `num_pranchas` (preferido — vem de /api/estimate-price). Mantém
    `num_files` como fallback compatibilidade.

    Auth: se `user_id` é informado e não é 'anonymous', exige JWT do dono.
    Senão atacante consome créditos da vítima via `_total_available_credit`.
    """
    # Validação JWT vs user_id (mesmo padrão do /api/process)
    if user_id and user_id != "anonymous":
        jwt_user = _get_user_from_request(request)
        if not jwt_user:
            raise HTTPException(401, "Autenticação requerida quando user_id é informado")
        if jwt_user.get("id") != user_id and jwt_user.get("email", "").lower() != ADMIN_EMAIL:
            raise HTTPException(403, "user_id não corresponde ao token de autenticação")

    import stripe
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    if not stripe.api_key:
        raise HTTPException(500, "Stripe não configurado")

    n = num_pranchas if num_pranchas > 0 else (num_files or 1)
    from pricing import calculate_price, get_tier_for
    price_cents = calculate_price(n)
    tier = get_tier_for(n)
    plan_name = f"Plano {tier['name']} — {n} pranchas"

    # Aplica créditos disponíveis (se houver user_id)
    credit_cents = min(price_cents, _total_available_credit(user_id)) if user_id else 0
    final_cents = max(0, price_cents - credit_cents)

    # Se crédito cobriu 100%, pula Stripe
    if final_cents == 0 and credit_cents > 0:
        return {
            "is_free": True,
            "checkout_url": None,
            "session_id": None,
            "num_pranchas": n,
            "price_cents": price_cents,
            "credit_applied_cents": credit_cents,
            "credit_applied_brl": round(credit_cents / 100, 2),
            "final_cents": 0,
            "final_brl": 0.0,
            "message": "Coberto pelo saldo de créditos — processe direto sem pagamento",
        }

    # Descrição do produto inclui o desconto aplicado se houver
    description = plan_name
    if credit_cents > 0:
        description += f" (R$ {credit_cents/100:.2f} de desconto aplicado)"

    line_items = [{
        "price_data": {
            "currency": "brl",
            "product_data": {
                "name": f"AI.arq — Planilha de quantitativos",
                "description": description,
            },
            "unit_amount": final_cents,
        },
        "quantity": 1,
    }]
    base_params = {
        "line_items": line_items,
        "mode": "payment",
        "success_url": "https://ai.arq.br/dashboard.html?payment=success&session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": "https://ai.arq.br/dashboard.html?payment=cancelled",
        "metadata": {
            "user_id": user_id or "anonymous",
            "num_pranchas": str(n),
            "price_cents": str(price_cents),
            "credit_applied_cents": str(credit_cents),
        },
    }

    # Tenta com PIX+card primeiro. Se o Stripe não tiver PIX ativado
    # (típico em conta nova ou ainda não configurada), cai pra card-only
    # automaticamente — evita quebrar o fluxo do cliente.
    session = None
    methods_used = []
    try:
        session_params = {**base_params, "payment_method_types": ["card", "pix"]}
        session = stripe.checkout.Session.create(**session_params)
        methods_used = ["card", "pix"]
    except stripe.error.InvalidRequestError as e:
        msg = str(e).lower()
        if "pix" in msg or "payment_method_types" in msg:
            print(f"[checkout] PIX indisponível ({e}); caindo pra card-only")
            try:
                session_params = {**base_params, "payment_method_types": ["card"]}
                session = stripe.checkout.Session.create(**session_params)
                methods_used = ["card"]
            except Exception as e2:
                raise HTTPException(500, f"Erro Stripe (card-only fallback): {str(e2)}")
        else:
            raise HTTPException(500, f"Erro ao criar checkout: {str(e)}")
    except Exception as e:
        raise HTTPException(500, f"Erro ao criar checkout: {str(e)}")

    if not session:
        raise HTTPException(500, "Erro ao criar checkout: session não foi criada")
    return {
        "is_free": False,
        "checkout_url": session.url,
        "session_id": session.id,
        "num_pranchas": n,
        "price_cents": price_cents,
        "credit_applied_cents": credit_cents,
        "credit_applied_brl": round(credit_cents / 100, 2),
        "final_cents": final_cents,
        "final_brl": round(final_cents / 100, 2),
        "payment_methods": methods_used,
    }


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
    request: Request,
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
    _require_project_owner(request, job_id)
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
    safe_name = _safe_local_filename(file.filename)
    revised_path = os.path.join(tmp_dir, f"cashback_{job_id}_{safe_name}")
    try:
        content = await file.read()
        with open(revised_path, "wb") as f:
            f.write(content)

        from density_calibration import ingest_budget as _ingest
        summary = _ingest(
            revised_path, area_m2=ref_area, typology=typology, project_label=label,
        )

        # Concede crédito de R$ 20 de cashback pro usuário — idempotente
        # por job_id (só libera uma vez por projeto revisado). Expira em
        # 180 dias pra evitar credit acumulando pra sempre sem uso.
        CASHBACK_CENTS = 2000  # R$ 20
        CASHBACK_EXPIRE_DAYS = 180
        cashback_granted = False
        user_id = project.get("user_id") or ""
        if user_id and user_id != "anonymous" and summary.get("items_parsed", 0) > 0:
            # Evita duplicar crédito pra mesma revisão
            already = _get_available_credits(user_id)
            duplicate = any(c.get("source") == "cashback" and c.get("source_ref") == job_id
                            for c in already)
            if not duplicate:
                cashback_granted = _grant_credit(
                    user_id=user_id,
                    amount_cents=CASHBACK_CENTS,
                    source="cashback",
                    source_ref=job_id,
                    description=f"Cashback revisão do projeto {label}",
                    expires_days=CASHBACK_EXPIRE_DAYS,
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
            "cashback_granted": cashback_granted,
            "cashback_amount_brl": CASHBACK_CENTS / 100 if cashback_granted else 0,
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
    safe_name = _safe_local_filename(xlsx.filename)
    xlsx_path = os.path.join(tmp_dir, f"ingest_{safe_name}")
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


# REMOVIDO 2026-05-14: /api/calibration/ingest-from-review era duplicata
# zumbi de /api/cashback/upload (mesma lógica de calibração por densidade).
# O frontend nunca chamou /calibration/ingest-from-review — só usa o
# /cashback/upload. Eliminado pra reduzir surface area e clarear o código.


# ═══════════════════════════════════════════════════════════════
#  Agente "tira-dúvidas" — Q&A sobre uma planilha gerada
# ═══════════════════════════════════════════════════════════════

@app.post("/api/agent/ask")
async def agent_ask(request: Request, job_id: str, question: str = ""):
    """Cliente faz uma pergunta sobre o quantitativo de UM job. O agente
    investiga (lê planilha, busca itens, lê DXFs, checa calibração) e
    responde em linguagem natural com referências aos itens.

    Body opcional (JSON): {"history": [{"role": "user|assistant", "content": "..."}]}
    pra manter contexto de conversação contínua.
    """
    if not job_id:
        raise HTTPException(400, "job_id obrigatório")
    if not question or len(question.strip()) < 2:
        raise HTTPException(400, "pergunta vazia")
    _require_project_owner(request, job_id)

    # History opcional via JSON body
    history = None
    try:
        body_bytes = await request.body()
        if body_bytes:
            import json as _j
            body = _j.loads(body_bytes.decode("utf-8"))
            if isinstance(body, dict) and isinstance(body.get("history"), list):
                history = body["history"]
    except Exception:
        history = None

    try:
        from agent import ask
        result = ask(job_id=job_id, question=question.strip(), history=history)
        return {"status": "ok", **result}
    except Exception as e:
        raise HTTPException(500, f"Erro do agente: {type(e).__name__}: {e}")


@app.get("/api/agent/conversations")
async def agent_conversations(request: Request, job_id: Optional[str] = None, limit: int = 50):
    # Se passou job_id, valida ownership; senão, exige admin (lista global de conversas)
    if job_id:
        _require_project_owner(request, job_id)
    else:
        _require_admin(request)
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
        # FIX 2026-05-14: antes definia URL pra RPC `agent_stats_summary` e
        # sobrescrevia logo na linha seguinte com fallback. RPC nunca era
        # chamada. Mantém apenas o select agregado (consistente com a RPC
        # se um dia existir).
        import urllib.request as _ur
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
    request: Request,
    typology: Optional[str] = None,
    limit: Optional[int] = None,
    only_unclassified: bool = True,
):
    """Classifica linhas raw existentes via LLM e recompila benchmarks.

    Requer auth admin — chamadas em massa consomem créditos Anthropic.

    Útil pra "ativar" raws antigos ingeridos antes do classificador
    existir. Idempotente: por padrão só toca raws sem familia_id.

    Cada raw vira ~3s (chamada Claude Haiku). Lote de 264 leva ~10min
    e custa ~$0.50. Use `limit` pra testar incrementalmente.
    """
    _require_admin(request)
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


# ═══════════════════════════════════════════════════════════════
#  REVISÃO INLINE DE ITENS (feedback loop)
# ═══════════════════════════════════════════════════════════════

@app.get("/api/items/{job_id}")
async def get_project_items(job_id: str, request: Request):
    """Retorna lista de itens individuais de um job pra revisão inline.
    Usa RPC `list_project_items` pra bypassar RLS."""
    _require_project_owner(request, job_id)
    import urllib.request, urllib.error, json
    try:
        url = f"{SUPABASE_URL}/rest/v1/rpc/list_project_items"
        body = json.dumps({"p_job_id": job_id}).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req.add_header('Content-Type', 'application/json')
        resp = urllib.request.urlopen(req, timeout=15)
        items = json.loads(resp.read().decode('utf-8'))
        return {"status": "ok", "job_id": job_id, "items": items, "count": len(items)}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar itens: {str(e)}")


# ═══════════════════════════════════════════════════════════════
#  CRONOGRAMA FÍSICO-FINANCEIRO (Fase 2 do roadmap)
# ═══════════════════════════════════════════════════════════════

class CronogramaPayload(BaseModel):
    data_inicio: str       # ISO YYYY-MM-DD
    duracao_meses: int     # 1..36


class CronogramaSavePayload(BaseModel):
    data_inicio: str
    duracao_meses: int
    k_sigmoid: Optional[int] = 10
    fases_custom: Optional[list] = []   # array de {label, inicio, fim, cor?, ambiente?, ordem?, manual?}
    notas: Optional[str] = ""


@app.get("/api/cronograma/{job_id}/sugestao")
async def cronograma_sugestao(job_id: str, request: Request):
    _require_project_owner(request, job_id)
    """Sugere duração de obra baseada em tipologia + área + n disciplinas
    detectadas. Chamado pelo frontend ANTES do "Gerar cronograma" pra
    preencher o slider com valor inteligente.
    """
    import urllib.request, json as _json

    # Busca o projeto pra pegar typology + area + files_count
    try:
        url = (f"{SUPABASE_URL}/rest/v1/projects?job_id=eq.{job_id}"
               "&select=typology,layout_area,total_area,files_count")
        req = urllib.request.Request(url, method='GET')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req.add_header('Accept', 'application/json')
        resp = urllib.request.urlopen(req, timeout=10)
        rows = _json.loads(resp.read().decode('utf-8'))
        if not rows:
            raise HTTPException(404, "Projeto não encontrado")
        proj = rows[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar projeto: {e}")

    # Busca disciplinas ativas via items
    try:
        url2 = f"{SUPABASE_URL}/rest/v1/rpc/list_project_items"
        body = _json.dumps({"p_job_id": job_id}).encode('utf-8')
        req2 = urllib.request.Request(url2, data=body, method='POST')
        req2.add_header('apikey', SUPABASE_KEY)
        req2.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req2.add_header('Content-Type', 'application/json')
        resp2 = urllib.request.urlopen(req2, timeout=15)
        items = _json.loads(resp2.read().decode('utf-8'))
    except Exception:
        items = []

    disciplinas = set()
    for it in items:
        d = (it.get('discipline') or '').strip().upper()
        if d and 'PREMISSA' not in d:
            disciplinas.add(d)
    n_disc = len(disciplinas)

    # Aplica heurística
    from cronograma import sugerir_duracao
    typology = proj.get('typology')
    area = proj.get('layout_area') or proj.get('total_area') or 0
    files_count = proj.get('files_count') or 0

    sugestao = sugerir_duracao(
        typology=typology,
        area_m2=area,
        files_count=files_count,
        n_disciplinas=n_disc,
    )
    return {"status": "ok", "job_id": job_id, **sugestao}


@app.post("/api/cronograma/{job_id}/generate")
async def generate_cronograma(job_id: str, payload: CronogramaPayload, request: Request):
    _require_project_owner(request, job_id)
    """Gera cronograma físico-financeiro a partir do quantitativo do projeto.

    Devolve JSON com fases + Gantt + curva S, pronto pra renderizar no
    frontend. Não persiste (recalcula a cada chamada — UX live).

    NÃO precifica. Distribui esforço no tempo seguindo sequenciamento
    construtivo padrão BR (16 etapas alinhadas com NBR 16636).
    """
    # 1. Busca os items do projeto via mesma RPC do get_project_items
    import urllib.request, json as _json
    try:
        url = f"{SUPABASE_URL}/rest/v1/rpc/list_project_items"
        body = _json.dumps({"p_job_id": job_id}).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req.add_header('Content-Type', 'application/json')
        resp = urllib.request.urlopen(req, timeout=15)
        items = _json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar itens do projeto: {e}")

    if not items:
        raise HTTPException(404, "Projeto sem itens — gere a planilha primeiro.")

    # 2. Valida inputs
    try:
        from datetime import date as _date
        _date.fromisoformat(payload.data_inicio)
    except Exception:
        raise HTTPException(400, "data_inicio deve estar no formato YYYY-MM-DD")

    if payload.duracao_meses < 1 or payload.duracao_meses > 60:
        raise HTTPException(400, "duracao_meses deve estar entre 1 e 60")

    # 3. Gera cronograma
    try:
        from cronograma import gerar_cronograma
        resultado = gerar_cronograma(
            items=items,
            data_inicio=payload.data_inicio,
            duracao_meses=payload.duracao_meses,
        )
        return {"status": "ok", "job_id": job_id, **resultado}
    except Exception as e:
        import traceback
        print(f"[cronograma] erro: {e}")
        print(traceback.format_exc())
        raise HTTPException(500, f"Erro ao gerar cronograma: {e}")


def _get_branding_context(job_id: str) -> dict:
    """Padrão de co-branding pra TODAS as exportações (PDF/PPTX/XLSX).

    Centraliza a busca de:
    - project_name (sempre amigável, nunca o hash do job_id)
    - architect_name (do projeto OU company do profile)
    - client_name (project_clients.client_name + client_company)
    - logo_url + logo_local_path (baixa pra arquivo temp pra embedar)
    - brand_color (hex; default = indigo AI.arq se vazio)
    - company (nome do escritório)

    Retorna dict pronto pra passar pra funções de export.
    """
    import urllib.request, json as _json
    import tempfile

    ctx = {
        'job_id': job_id,
        'project_name': '',
        'architect_name': '',
        'client_name': '',
        'company': '',
        'logo_url': '',
        'logo_local_path': None,
        'brand_color': '#4F46E5',  # default indigo AI.arq
    }

    project_user_id = ''

    # 1. projects: nome amigável + arquiteto
    try:
        pj_url = (f"{SUPABASE_URL}/rest/v1/projects"
                  f"?job_id=eq.{job_id}&select=project_name,user_name,user_id")
        pj_req = urllib.request.Request(pj_url, method="GET")
        pj_req.add_header("apikey", SUPABASE_KEY)
        pj_req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        pj_resp = urllib.request.urlopen(pj_req, timeout=8)
        pj_data = _json.loads(pj_resp.read().decode("utf-8"))
        if pj_data:
            ctx['project_name'] = (pj_data[0].get('project_name') or '').strip()
            ctx['architect_name'] = (pj_data[0].get('user_name') or '').strip()
            project_user_id = pj_data[0].get('user_id') or ''
    except Exception as e:
        print(f"[branding] erro projects: {e}")

    # 2. project_clients: cliente final
    try:
        cl_url = (f"{SUPABASE_URL}/rest/v1/project_clients"
                  f"?job_id=eq.{job_id}&select=client_name,client_company")
        cl_req = urllib.request.Request(cl_url, method="GET")
        cl_req.add_header("apikey", SUPABASE_KEY)
        cl_req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        cl_resp = urllib.request.urlopen(cl_req, timeout=8)
        cl_data = _json.loads(cl_resp.read().decode("utf-8"))
        if cl_data:
            cn = (cl_data[0].get('client_name') or '').strip()
            cc = (cl_data[0].get('client_company') or '').strip()
            if cn and cc:
                ctx['client_name'] = f"{cn} ({cc})"
            else:
                ctx['client_name'] = cn or cc
    except Exception as e:
        print(f"[branding] erro project_clients: {e}")

    # 3. profiles: logo + cor + company
    if project_user_id:
        try:
            pr_url = (f"{SUPABASE_URL}/rest/v1/profiles"
                      f"?user_id=eq.{project_user_id}"
                      f"&select=logo_url,company,company_brand_color")
            pr_req = urllib.request.Request(pr_url, method="GET")
            pr_req.add_header("apikey", SUPABASE_KEY)
            pr_req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
            pr_resp = urllib.request.urlopen(pr_req, timeout=8)
            pr_data = _json.loads(pr_resp.read().decode("utf-8"))
            if pr_data:
                ctx['logo_url'] = (pr_data[0].get('logo_url') or '').strip()
                ctx['company'] = (pr_data[0].get('company') or '').strip()
                bc = (pr_data[0].get('company_brand_color') or '').strip()
                if bc and bc.startswith('#') and len(bc) in (4, 7):
                    ctx['brand_color'] = bc
                if not ctx['architect_name'] and ctx['company']:
                    ctx['architect_name'] = ctx['company']
        except Exception as e:
            print(f"[branding] erro profiles: {e}")

    # 4. Fallback project_name
    if not ctx['project_name']:
        ctx['project_name'] = 'Projeto sem nome'

    # 5. Baixa logo pra arquivo temp (se houver)
    if ctx['logo_url']:
        try:
            req = urllib.request.Request(ctx['logo_url'], method="GET",
                                          headers={'User-Agent': 'AI.arq/1.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            ext = '.png'
            if '.jpg' in ctx['logo_url'].lower() or '.jpeg' in ctx['logo_url'].lower():
                ext = '.jpg'
            tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
            tmp.write(data)
            tmp.close()
            ctx['logo_local_path'] = tmp.name
        except Exception as e:
            print(f"[branding] erro download logo: {e}")
            ctx['logo_local_path'] = None

    return ctx


def _supabase_get_cronograma(job_id: str) -> Optional[dict]:
    """Busca cronograma salvo do job. Retorna None se não existir."""
    import urllib.request, json as _json
    try:
        url = (f"{SUPABASE_URL}/rest/v1/cronogramas"
               f"?job_id=eq.{job_id}&select=*&limit=1")
        req = urllib.request.Request(url, method='GET')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req.add_header('Accept', 'application/json')
        resp = urllib.request.urlopen(req, timeout=10)
        rows = _json.loads(resp.read().decode('utf-8'))
        return rows[0] if rows else None
    except Exception as e:
        print(f"[cronograma get] erro: {e}")
        return None


def _supabase_upsert_cronograma(job_id: str, data: dict) -> bool:
    """Insere ou atualiza cronograma. Usa Prefer: resolution=merge-duplicates."""
    import urllib.request, json as _json
    payload = {"job_id": job_id, **data}
    try:
        url = f"{SUPABASE_URL}/rest/v1/cronogramas"
        body = _json.dumps(payload, default=str).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Prefer', 'resolution=merge-duplicates,return=minimal')
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"[cronograma upsert] erro: {e}")
        return False


@app.get("/api/cronograma/{job_id}")
async def get_cronograma(job_id: str, request: Request):
    """Retorna cronograma salvo do projeto (config + fases custom se houver).

    Se não houver salvo, devolve sugestão de duração + flag indicando que
    cliente ainda não gerou cronograma. Frontend usa essa info pra decidir
    se mostra inputs (gerar primeiro) ou já renderiza o salvo.
    """
    _require_project_owner(request, job_id)
    saved = _supabase_get_cronograma(job_id)
    if not saved:
        return {"status": "empty", "job_id": job_id, "saved": None}
    return {"status": "ok", "job_id": job_id, "saved": saved}


@app.post("/api/cronograma/{job_id}/save")
async def save_cronograma(job_id: str, payload: CronogramaSavePayload, request: Request):
    """Salva (upsert) cronograma com config + fases editadas."""
    _require_project_owner(request, job_id)
    # Valida data
    try:
        from datetime import date as _date
        _date.fromisoformat(payload.data_inicio)
    except Exception:
        raise HTTPException(400, "data_inicio deve estar no formato YYYY-MM-DD")
    if payload.duracao_meses < 1 or payload.duracao_meses > 60:
        raise HTTPException(400, "duracao_meses entre 1 e 60")

    data = {
        "data_inicio": payload.data_inicio,
        "duracao_meses": payload.duracao_meses,
        "k_sigmoid": payload.k_sigmoid or 10,
        "fases_custom": payload.fases_custom or [],
        "notas": payload.notas or "",
        "updated_at": "now()",
    }
    ok = _supabase_upsert_cronograma(job_id, data)
    if not ok:
        raise HTTPException(500, "Erro ao salvar no banco")
    return {"status": "ok", "job_id": job_id}


@app.get("/api/cronograma/{job_id}/full")
async def get_cronograma_full(job_id: str, request: Request):
    """Retorna o cronograma já renderizado (Gantt+CurvaS+Matriz+PPC) pra
    abrir a página sem precisar clicar em 'Gerar'.

    Se o cliente já salvou (com ou sem fases_custom), reusa a config salva.
    Se não há salvo, retorna 404 — frontend mostra o form pra gerar pela
    primeira vez.
    """
    _require_project_owner(request, job_id)
    saved = _supabase_get_cronograma(job_id)
    if not saved:
        raise HTTPException(404, "Cronograma ainda não gerado para este projeto")
    try:
        cron, _branding = _build_cronograma_for_export(job_id)
        return cron
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[cronograma full] erro: {e}")
        print(traceback.format_exc())
        raise HTTPException(500, f"Erro ao montar cronograma: {e}")


def _build_cronograma_for_export(job_id: str) -> tuple:
    """Monta o JSON do cronograma usando fases_custom se houver, senão gera
    automaticamente. Retorna (cronograma_dict, branding_context)."""
    import urllib.request, json as _json
    saved = _supabase_get_cronograma(job_id)

    # Branding co-branded (nome projeto + cliente + logo + cor + arquiteto)
    branding = _get_branding_context(job_id)

    from cronograma import gerar_cronograma, gerar_cronograma_de_fases_custom

    if saved and saved.get('fases_custom'):
        # Usa fases editadas pelo cliente
        cron = gerar_cronograma_de_fases_custom(
            fases_custom=saved['fases_custom'],
            data_inicio=str(saved['data_inicio']),
            duracao_meses=saved['duracao_meses'],
        )
    else:
        # Gera automaticamente a partir dos items
        try:
            url = f"{SUPABASE_URL}/rest/v1/rpc/list_project_items"
            body = _json.dumps({"p_job_id": job_id}).encode('utf-8')
            req = urllib.request.Request(url, data=body, method='POST')
            req.add_header('apikey', SUPABASE_KEY)
            req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
            req.add_header('Content-Type', 'application/json')
            resp = urllib.request.urlopen(req, timeout=15)
            items = _json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            raise HTTPException(500, f"Erro ao buscar items: {e}")

        if not items:
            raise HTTPException(404, "Projeto sem itens")

        # Se há config salva mas sem fases_custom, usa config; senão default
        if saved:
            data_inicio = str(saved['data_inicio'])
            duracao = saved['duracao_meses']
        else:
            from datetime import date as _date, timedelta as _td
            data_inicio = (_date.today() + _td(days=30)).isoformat()
            duracao = 6
        cron = gerar_cronograma(items, data_inicio, duracao)

    return cron, branding


def _slug_filename(name: str) -> str:
    """Converte nome do projeto pra filename amigável (sem acentos/especiais)."""
    import re, unicodedata
    s = unicodedata.normalize('NFKD', name)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r'[^a-zA-Z0-9_-]+', '_', s).strip('_')
    return s[:60] or 'cronograma'


@app.get("/api/cronograma/{job_id}/export/pdf")
async def export_cronograma_pdf(job_id: str, request: Request):
    """Exporta cronograma como PDF co-branded (logo + cor + nome cliente)."""
    _require_project_owner(request, job_id)
    import tempfile, os
    from fastapi.responses import FileResponse
    cron, branding = _build_cronograma_for_export(job_id)
    try:
        from cronograma_export import exportar_pdf
        tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        tmp.close()
        exportar_pdf(cron, tmp.name, branding=branding)
        fname = f"cronograma_{_slug_filename(branding['project_name'])}.pdf"
        return FileResponse(tmp.name, media_type='application/pdf',
                             filename=fname)
    except Exception as e:
        import traceback
        print(f"[export pdf] erro: {e}")
        print(traceback.format_exc())
        raise HTTPException(500, f"Erro ao gerar PDF: {e}")


@app.get("/api/cronograma/{job_id}/export/pptx")
async def export_cronograma_pptx(job_id: str, request: Request):
    """Exporta cronograma como PPTX co-branded (5 slides pra apresentar)."""
    _require_project_owner(request, job_id)
    import tempfile
    from fastapi.responses import FileResponse
    cron, branding = _build_cronograma_for_export(job_id)
    try:
        from cronograma_export import exportar_pptx
        tmp = tempfile.NamedTemporaryFile(suffix='.pptx', delete=False)
        tmp.close()
        exportar_pptx(cron, tmp.name, branding=branding)
        fname = f"cronograma_{_slug_filename(branding['project_name'])}.pptx"
        return FileResponse(
            tmp.name,
            media_type='application/vnd.openxmlformats-officedocument.presentationml.presentation',
            filename=fname)
    except Exception as e:
        import traceback
        print(f"[export pptx] erro: {e}")
        print(traceback.format_exc())
        raise HTTPException(500, f"Erro ao gerar PPTX: {e}")


class ReviewPayload(BaseModel):
    action: str                              # 'approve' | 'reject' | 'edit'
    edits: Optional[dict] = None             # {description?, unit?, quantity?, discipline?, observations?}
    comment: Optional[str] = ""
    reviewed_by: Optional[str] = ""


@app.post("/api/items/{job_id}/review/{item_id}")
async def submit_item_review(job_id: str, item_id: str, payload: ReviewPayload, request: Request):
    _require_project_owner(request, job_id)
    """Registra uma revisão pra um item específico.
    Se action='edit', também aplica os edits à row em project_items.
    Insere sempre uma linha em item_reviews pra histórico/aprendizado."""
    import urllib.request, urllib.error, json

    action = (payload.action or "").strip().lower()
    if action not in ("approve", "reject", "edit"):
        raise HTTPException(400, "action inválida (use approve/reject/edit)")

    # 1) Log da revisão
    review_row = {
        "job_id": job_id,
        "item_id": item_id,
        "action": action,
        "edits": payload.edits or None,
        "comment": payload.comment or "",
        "reviewed_by": payload.reviewed_by or "",
    }
    _supabase_insert("item_reviews", review_row)

    # 2) Aplicar edits à row original (se action=edit)
    if action == "edit" and payload.edits:
        safe_edits = {}
        allowed = {"description", "unit", "quantity", "discipline", "observations"}
        for k, v in payload.edits.items():
            if k in allowed and v is not None:
                safe_edits[k] = v
        if safe_edits:
            try:
                url = f"{SUPABASE_URL}/rest/v1/project_items?id=eq.{item_id}"
                body = json.dumps(safe_edits).encode('utf-8')
                req = urllib.request.Request(url, data=body, method='PATCH')
                req.add_header('apikey', SUPABASE_KEY)
                req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
                req.add_header('Content-Type', 'application/json')
                req.add_header('Prefer', 'return=minimal')
                urllib.request.urlopen(req, timeout=15)
            except Exception as e:
                _supa_log(f"REVIEW edit item={item_id} ERR {e}")

    # 3) Se rejeitado, deleta row do item (mantém review pra histórico)
    if action == "reject":
        try:
            url = f"{SUPABASE_URL}/rest/v1/project_items?id=eq.{item_id}"
            req = urllib.request.Request(url, method='DELETE')
            req.add_header('apikey', SUPABASE_KEY)
            req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
            req.add_header('Prefer', 'return=minimal')
            urllib.request.urlopen(req, timeout=15)
        except Exception as e:
            _supa_log(f"REVIEW reject item={item_id} ERR {e}")

    return {"status": "ok", "action": action}


@app.post("/api/items/{job_id}/finalize")
async def finalize_review(job_id: str, request: Request):
    _require_project_owner(request, job_id)
    """Regenera o .xlsx com as revisões aplicadas e sobe pro Storage.
    Busca items atuais do Supabase (já com edits/rejects aplicados) e
    passa pro generate_spreadsheet. Retorna URL de download."""
    import urllib.request, urllib.error, json
    from models import BudgetItem, Confidence, ProjectData
    from spreadsheet import generate_spreadsheet

    # 1) Buscar project metadata
    try:
        url = f"{SUPABASE_URL}/rest/v1/projects?job_id=eq.{job_id}&select=*"
        req = urllib.request.Request(url, method='GET')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        resp = urllib.request.urlopen(req, timeout=15)
        projects = json.loads(resp.read().decode('utf-8'))
        if not projects:
            raise HTTPException(404, "Projeto não encontrado")
        proj = projects[0]
    except urllib.error.HTTPError as e:
        raise HTTPException(500, f"Erro Supabase: {e}")

    # 2) Buscar items atuais (já revisados)
    try:
        url = f"{SUPABASE_URL}/rest/v1/rpc/list_project_items"
        body = json.dumps({"p_job_id": job_id}).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req.add_header('Content-Type', 'application/json')
        resp = urllib.request.urlopen(req, timeout=15)
        rows = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar itens: {e}")

    # 3) Reconstituir ProjectData + BudgetItems
    pd = ProjectData(
        name=proj.get("project_name", "") or "Projeto",
        total_area=proj.get("total_area") or 0,
        layout_area=proj.get("layout_area") or 0,
    )
    items = []
    for r in rows:
        try:
            items.append(BudgetItem(
                item_num=r.get("item_num", "") or "",
                description=r.get("description", "") or "",
                unit=r.get("unit", "vb") or "vb",
                quantity=float(r.get("quantity") or 0),
                observations=r.get("observations", "") or "",
                ref_sheet=r.get("ref_sheet", "") or "",
                confidence=Confidence(r.get("confidence", "estimado") or "estimado"),
                discipline=r.get("discipline", "Complementares") or "Complementares",
            ))
        except Exception:
            continue

    # 4) Gerar xlsx revisado — também enriquece com matches TCPO + heurísticas
    try:
        from tcpo_matcher import match_item, get_insumos
        for it in items:
            try:
                ms = match_item(it.description, limit=3)
                if ms:
                    ms[0]['insumos'] = get_insumos(ms[0]['id'])
                    it.tcpo_matches = ms
            except Exception:
                pass
    except ImportError:
        pass

    typology = proj.get("typology") or "office"

    # Heurísticas de mercado (alertas agregados anônimos)
    try:
        from market_heuristics import check_item_anomaly
        for it in items:
            try:
                alertas = check_item_anomaly(it, typology=typology)
                if alertas:
                    sep = " | " if it.observations else ""
                    it.observations = (it.observations or "") + sep + " ".join(alertas)
            except Exception:
                pass
    except ImportError:
        pass

    work_dir = os.path.join(WORK_DIR, job_id)
    os.makedirs(work_dir, exist_ok=True)
    output_path = os.path.join(work_dir, f"orcamento_{job_id}_revisado.xlsx")
    generate_spreadsheet(pd, items, output_path, typology=typology)

    # 5) Subir pra Storage sobrescrevendo o antigo
    _storage_ok = _supabase_storage_upload(output_path, f"{job_id}.xlsx")

    return {
        "status": "ok",
        "job_id": job_id,
        "items_count": len(items),
        "download_url": f"/api/download/{job_id}",
        "storage_uploaded": _storage_ok,
    }


# ═══════════════════════════════════════════════════════════════
#  STATUS EDITÁVEL + NOTAS POR ITEM
# ═══════════════════════════════════════════════════════════════

class StatusPayload(BaseModel):
    user_status: str


@app.post("/api/project/{job_id}/status")
async def update_project_user_status(job_id: str, payload: StatusPayload, request: Request):
    """Atualiza o status editável do projeto (em_analise, enviado_cliente,
    aprovado, fechado, arquivado)."""
    _require_project_owner(request, job_id)
    import urllib.request, urllib.error, json
    valid = {"em_analise", "enviado_cliente", "aprovado", "fechado", "arquivado"}
    if payload.user_status not in valid:
        raise HTTPException(400, f"status inválido. Aceito: {valid}")
    try:
        url = f"{SUPABASE_URL}/rest/v1/rpc/update_user_status"
        body = json.dumps({
            "p_job_id": job_id,
            "p_user_status": payload.user_status,
        }).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req.add_header('Content-Type', 'application/json')
        resp = urllib.request.urlopen(req, timeout=15)
        return {"status": "ok", "user_status": payload.user_status}
    except Exception as e:
        raise HTTPException(500, f"Erro: {e}")


class NotePayload(BaseModel):
    note: str
    author: Optional[str] = ""


@app.post("/api/items/{job_id}/note/{item_id}")
async def save_item_note(job_id: str, item_id: str, payload: NotePayload, request: Request):
    """Salva (upsert) nota de um item. Vazio deleta a nota."""
    _require_project_owner(request, job_id)
    import urllib.request, urllib.error, json
    text = (payload.note or "").strip()
    try:
        if not text:
            # Delete
            url = f"{SUPABASE_URL}/rest/v1/item_notes?item_id=eq.{item_id}"
            req = urllib.request.Request(url, method='DELETE')
            req.add_header('apikey', SUPABASE_KEY)
            req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
            urllib.request.urlopen(req, timeout=10)
            return {"status": "ok", "deleted": True}

        # Upsert: try update first, insert on 0 rows
        url = f"{SUPABASE_URL}/rest/v1/item_notes?item_id=eq.{item_id}"
        body = json.dumps({
            "note": text,
            "author": payload.author or "",
            "updated_at": datetime.utcnow().isoformat(),
        }).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='PATCH')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Prefer', 'return=representation')
        resp = urllib.request.urlopen(req, timeout=10)
        rows = json.loads(resp.read().decode('utf-8') or '[]')
        if not rows:
            # Insert novo
            _supabase_insert("item_notes", {
                "job_id": job_id,
                "item_id": item_id,
                "note": text,
                "author": payload.author or "",
            })
        return {"status": "ok", "saved": True}
    except Exception as e:
        raise HTTPException(500, f"Erro: {e}")


@app.get("/api/items/{job_id}/notes")
async def list_job_notes(job_id: str, request: Request):
    _require_project_owner(request, job_id)
    """Lista todas as notas de itens de um job — restaura estado na revisão."""
    import urllib.request, urllib.error, json
    try:
        url = f"{SUPABASE_URL}/rest/v1/rpc/list_item_notes"
        body = json.dumps({"p_job_id": job_id}).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req.add_header('Content-Type', 'application/json')
        resp = urllib.request.urlopen(req, timeout=15)
        notes = json.loads(resp.read().decode('utf-8'))
        # Retorna como mapa {item_id: {note, author, updated_at}}
        state = {n["item_id"]: {
            "note": n.get("note", ""),
            "author": n.get("author", ""),
            "updated_at": n.get("updated_at"),
        } for n in notes}
        return {"status": "ok", "notes": state}
    except Exception as e:
        raise HTTPException(500, f"Erro: {e}")


@app.get("/api/projects/by-user/{user_id}")
async def list_my_projects(user_id: str, request: Request):
    """Lista projetos de um usuário (pra tela 'Meus projetos').
    Usa RPC list_user_projects (SECURITY DEFINER).

    Auth: user_id='anonymous' é livre (retrocompat). Para user_id real,
    exige JWT Bearer do próprio usuário (ou admin)."""
    if user_id and user_id != "anonymous":
        user = _get_user_from_request(request)
        if not user:
            raise HTTPException(401, "Autenticação requerida")
        if user.get("id") != user_id and user.get("email", "").lower() != ADMIN_EMAIL:
            raise HTTPException(403, "Só é possível listar seus próprios projetos")
    import urllib.request, urllib.error, json
    try:
        url = f"{SUPABASE_URL}/rest/v1/rpc/list_user_projects"
        body = json.dumps({"p_user_id": user_id}).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req.add_header('Content-Type', 'application/json')
        resp = urllib.request.urlopen(req, timeout=15)
        projects = json.loads(resp.read().decode('utf-8'))
        return {"status": "ok", "user_id": user_id, "projects": projects, "count": len(projects)}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar projetos: {str(e)}")


# ═══════════════════════════════════════════════════════════════
#  NPS (Net Promoter Score)
# ═══════════════════════════════════════════════════════════════

class NPSPayload(BaseModel):
    user_id: str
    score: int                               # 0-10
    comment: Optional[str] = ""
    context: Optional[str] = "manual"        # 'after_download' | 'after_review' | 'manual' | 'first_project'
    user_email: Optional[str] = ""
    user_name: Optional[str] = ""
    job_id: Optional[str] = ""


@app.post("/api/nps")
async def submit_nps(payload: NPSPayload):
    """Registra uma resposta NPS. Score 0-10 obrigatório, comentário opcional."""
    if payload.score < 0 or payload.score > 10:
        raise HTTPException(400, "score deve estar entre 0 e 10")
    if not payload.user_id:
        raise HTTPException(400, "user_id obrigatório")

    row = {
        "user_id": payload.user_id,
        "user_email": payload.user_email or "",
        "user_name": payload.user_name or "",
        "score": int(payload.score),
        "comment": (payload.comment or "")[:2000],
        "context": (payload.context or "manual")[:50],
        "job_id": payload.job_id or "",
    }
    ok = _supabase_insert("nps_responses", row)
    category = "promoter" if payload.score >= 9 else "passive" if payload.score >= 7 else "detractor"
    return {"status": "ok" if ok else "error", "category": category}


@app.get("/api/nps/check/{user_id}")
async def should_show_nps(user_id: str):
    """Verifica se o usuário já respondeu NPS recentemente (últimos 60 dias).
    Frontend usa isso pra não mostrar o widget repetidamente."""
    import urllib.request, urllib.error, json
    try:
        url = (f"{SUPABASE_URL}/rest/v1/nps_responses"
               f"?user_id=eq.{user_id}&select=created_at"
               f"&order=created_at.desc&limit=1")
        req = urllib.request.Request(url, method='GET')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        resp = urllib.request.urlopen(req, timeout=10)
        rows = json.loads(resp.read().decode('utf-8'))
        if not rows:
            return {"should_show": True, "last_answered": None}
        last = rows[0].get("created_at")
        # 60 dias de cooldown
        from datetime import timedelta
        try:
            dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
            days_since = (datetime.utcnow().replace(tzinfo=dt.tzinfo) - dt).days
            return {"should_show": days_since >= 60, "last_answered": last, "days_since": days_since}
        except Exception:
            return {"should_show": False, "last_answered": last}
    except Exception as e:
        return {"should_show": False, "error": str(e)}


@app.get("/api/admin/nps/summary")
async def admin_nps_summary(request: Request, days: int = 30):
    """Dashboard admin: resumo agregado de NPS."""
    _require_admin(request)
    import urllib.request, urllib.error, json
    try:
        url = f"{SUPABASE_URL}/rest/v1/rpc/get_nps_summary"
        body = json.dumps({"p_days": days}).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req.add_header('Content-Type', 'application/json')
        resp = urllib.request.urlopen(req, timeout=10)
        rows = json.loads(resp.read().decode('utf-8'))
        return rows[0] if rows else {}
    except Exception as e:
        raise HTTPException(500, f"Erro: {e}")


@app.get("/api/admin/nps/responses")
async def admin_nps_responses(request: Request, limit: int = 50):
    """Dashboard admin: respostas recentes com comentários (insights qualitativos)."""
    _require_admin(request)
    import urllib.request, urllib.error, json
    try:
        url = f"{SUPABASE_URL}/rest/v1/rpc/list_nps_responses"
        body = json.dumps({"p_limit": limit}).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req.add_header('Content-Type', 'application/json')
        resp = urllib.request.urlopen(req, timeout=10)
        return {"responses": json.loads(resp.read().decode('utf-8'))}
    except Exception as e:
        raise HTTPException(500, f"Erro: {e}")


# ═══════════════════════════════════════════════════════════════
#  SERVIR PRANCHA (pra revisão inline abrir em nova aba)
# ═══════════════════════════════════════════════════════════════

def _find_prancha_file(job_id: str, ref: str) -> Optional[str]:
    """Dado um ref_sheet (que pode vir como nome exato, descrição da IA, ou
    concatenação 'filename (hint)'), encontra o filename real do PDF:

    1. Se `ref` termina em .pdf e existe no hot cache → usa direto.
    2. Se `ref` tem formato "filename.pdf (hint)" → extrai o filename antes do "(".
    3. Fuzzy match: lista PDFs do job no /tmp OU no Storage, escolhe o que
       tem maior substring overlap com `ref`.

    Retorna o filename encontrado ou None.
    """
    import urllib.request
    ref_clean = (ref or "").strip()
    if not ref_clean:
        return None

    # Remover sufixo "(hint da IA)" se houver
    if "(" in ref_clean and ref_clean.endswith(")"):
        ref_clean = ref_clean.split("(")[0].strip()

    # Caso direto: já é um filename .pdf válido
    if ref_clean.lower().endswith(".pdf"):
        candidate = os.path.basename(ref_clean)
        # Verificar se existe
        if os.path.exists(os.path.join(WORK_DIR, job_id, candidate)):
            return candidate
        # Senão, tenta no Storage (via list)
        try:
            url = f"{SUPABASE_URL}/storage/v1/object/list/{PRANCHAS_BUCKET}"
            import json as _j
            body = _j.dumps({"prefix": f"{job_id}/", "limit": 200}).encode("utf-8")
            req = urllib.request.Request(url, data=body, method="POST")
            req.add_header("apikey", SUPABASE_KEY)
            req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
            req.add_header("Content-Type", "application/json")
            resp = urllib.request.urlopen(req, timeout=10)
            files = _j.loads(resp.read().decode("utf-8"))
            names = [f.get("name", "") for f in files]
            for n in names:
                # Storage keys são URL-encoded
                from urllib.parse import unquote
                if unquote(n) == candidate:
                    return candidate
        except Exception:
            pass

    # Fuzzy match: lista PDFs locais + Storage, acha melhor match
    candidates = set()
    local_dir = os.path.join(WORK_DIR, job_id)
    if os.path.isdir(local_dir):
        for fn in os.listdir(local_dir):
            if fn.lower().endswith(".pdf"):
                candidates.add(fn)
    try:
        from urllib.parse import unquote
        url = f"{SUPABASE_URL}/storage/v1/object/list/{PRANCHAS_BUCKET}"
        import json as _j2
        body = _j2.dumps({"prefix": f"{job_id}/", "limit": 200}).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=10)
        for f in _j2.loads(resp.read().decode("utf-8")):
            n = unquote(f.get("name", ""))
            if n.lower().endswith(".pdf"):
                candidates.add(n)
    except Exception:
        pass

    if not candidates:
        return None

    # Tokeniza o ref e cada candidato; retorna o candidato com mais tokens
    # em comum (case-insensitive, ignorando caracteres não-alfanum).
    import re as _re
    def _tokens(s):
        return set(t for t in _re.split(r"[^a-z0-9]+", s.lower()) if len(t) > 1)
    ref_tok = _tokens(ref_clean)
    if not ref_tok:
        return None
    best, best_score = None, 0
    for c in candidates:
        score = len(ref_tok & _tokens(c))
        if score > best_score:
            best_score = score
            best = c
    return best if best_score >= 1 else None


@app.get("/api/sheet/{job_id}")
async def get_sheet_pdf(job_id: str, ref: str = ""):
    """Serve a prancha (PDF, PNG, etc) inline pro viewer. Pra DWG/DXF
    tenta servir o PNG renderizado (render server-side) antes."""
    from fastapi.responses import Response

    if not ref:
        raise HTTPException(400, "parâmetro 'ref' obrigatório")

    filename = _find_prancha_file(job_id, ref)
    if not filename:
        raise HTTPException(404, f"Prancha correspondente a '{ref}' não encontrada")

    ext = os.path.splitext(filename.lower())[1]
    preview_filename = filename
    mime = _PRANCHA_MIME.get(ext, "application/octet-stream")

    # DWG/DXF: preferir PNG renderizado se existe
    if ext in ('.dwg', '.dxf'):
        _png_name = os.path.splitext(filename)[0] + '.png'
        _png_local = os.path.join(WORK_DIR, job_id, _png_name)
        if os.path.exists(_png_local):
            preview_filename = _png_name
            mime = "image/png"
        else:
            _png_data = _supabase_storage_download_prancha(job_id, _png_name)
            if _png_data:
                return Response(
                    content=_png_data, media_type="image/png",
                    headers={
                        "Content-Disposition": "inline",
                        "X-Filename": _png_name,
                        "Cache-Control": "private, max-age=3600",
                    }
                )

    # Hot cache local
    local_path = os.path.join(WORK_DIR, job_id, preview_filename)
    if os.path.exists(local_path):
        try:
            with open(local_path, "rb") as f:
                data = f.read()
            return Response(
                content=data, media_type=mime,
                headers={
                    "Content-Disposition": "inline",
                    "X-Filename": preview_filename,
                    "Cache-Control": "private, max-age=3600",
                }
            )
        except Exception:
            pass

    # Storage
    data = _supabase_storage_download_prancha(job_id, preview_filename)
    if data:
        return Response(
            content=data, media_type=mime,
            headers={
                "Content-Disposition": "inline",
                "X-Filename": preview_filename,
                "Cache-Control": "private, max-age=3600",
            }
        )

    raise HTTPException(404, f"Prancha '{preview_filename}' não encontrada no Storage")


# ═══════════════════════════════════════════════════════════════
#  REPROCESSAR PROJETO (motor atualizado)
# ═══════════════════════════════════════════════════════════════

REPROCESS_FREE_LIMIT = 1  # 1 reprocessamento grátis por projeto


@app.post("/api/project/{job_id}/reprocess")
async def reprocess_project(job_id: str, request: Request):
    """Baixa os arquivos originais do Storage e cria novo job com os mesmos
    arquivos + tipologia. Usa a última versão do motor (prompts + regras).

    Política: 1 reprocessamento grátis por projeto. Tentativas adicionais
    retornam 402 (Payment Required) com mensagem orientando o user."""
    _require_project_owner(request, job_id)
    import urllib.request, urllib.error, json, shutil

    # 1) Buscar projeto original + checar contador
    try:
        url = f"{SUPABASE_URL}/rest/v1/projects?job_id=eq.{job_id}&select=*"
        req = urllib.request.Request(url, method='GET')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        resp = urllib.request.urlopen(req, timeout=15)
        projects = json.loads(resp.read().decode('utf-8'))
        if not projects:
            raise HTTPException(404, "Projeto original não encontrado")
        orig = projects[0]
    except urllib.error.HTTPError as e:
        raise HTTPException(500, f"Erro ao buscar projeto: {e}")

    # Política: 1 reprocessamento grátis por projeto
    current_count = int(orig.get("reprocess_count") or 0)
    if current_count >= REPROCESS_FREE_LIMIT:
        raise HTTPException(
            402,  # Payment Required
            f"Este projeto já foi reprocessado {current_count}× — o limite "
            f"gratuito é {REPROCESS_FREE_LIMIT} por projeto. Crie um novo "
            f"projeto pra processar com o motor atualizado."
        )

    # 2) Listar arquivos originais no Storage
    from urllib.parse import unquote
    try:
        list_url = f"{SUPABASE_URL}/storage/v1/object/list/{PRANCHAS_BUCKET}"
        body = json.dumps({"prefix": f"{job_id}/", "limit": 100}).encode("utf-8")
        req = urllib.request.Request(list_url, data=body, method="POST")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=20)
        storage_files = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise HTTPException(500, f"Erro ao listar Storage: {e}")

    valid_ext = ('.pdf', '.dwg', '.dxf')
    original_filenames = []
    for f in storage_files:
        n = unquote(f.get("name", ""))
        if n.lower().endswith(valid_ext):
            original_filenames.append(n)
    if not original_filenames:
        raise HTTPException(400,
            "Arquivos originais não disponíveis no Storage. "
            "Projetos anteriores a 21/04/2026 não tiveram upload automático — "
            "suba novamente pra reprocessar.")

    # 3) Criar novo job_id + work dir + baixar arquivos
    new_job_id = str(uuid.uuid4())[:8]
    new_work_dir = os.path.join(WORK_DIR, new_job_id)
    os.makedirs(new_work_dir, exist_ok=True)

    new_file_paths = []
    file_types = {'pdf': 0, 'dwg': 0, 'dxf': 0}
    for fname in original_filenames:
        local_path = os.path.join(new_work_dir, fname)
        data = _supabase_storage_download_prancha(job_id, fname)
        if not data:
            continue
        with open(local_path, "wb") as f:
            f.write(data)
        new_file_paths.append(local_path)
        ext = fname.lower().rsplit('.', 1)[-1]
        file_types[ext] = file_types.get(ext, 0) + 1

    if not new_file_paths:
        shutil.rmtree(new_work_dir, ignore_errors=True)
        raise HTTPException(500, "Falha ao baixar arquivos do Storage")

    # 4) Criar novo projeto + status
    types_summary = ", ".join(f"{v} {k.upper()}" for k, v in file_types.items() if v > 0)
    jobs[new_job_id] = ProcessingStatus(
        job_id=new_job_id, status="queued", progress=0,
        current_step=f"Reprocessamento: {len(new_file_paths)} arquivos recuperados ({types_summary})",
        total_steps=3,
    )

    typology = orig.get("typology") or "office"
    _supabase_insert("projects", {
        "job_id": new_job_id,
        "user_id": orig.get("user_id") or "anonymous",
        "user_email": orig.get("user_email") or "",
        "user_name": orig.get("user_name") or "",
        "project_name": f"{orig.get('project_name','Projeto')} (reprocessado)",
        "typology": typology,
        "files_count": len(new_file_paths),
        "file_types": file_types,
        "status": "queued",
        "parent_job_id": job_id,  # rastreabilidade: novo projeto é filho do original
    })

    # Incrementar contador do ORIGINAL via RPC atômica
    try:
        inc_url = f"{SUPABASE_URL}/rest/v1/rpc/increment_reprocess_count"
        inc_body = json.dumps({"p_job_id": job_id}).encode('utf-8')
        inc_req = urllib.request.Request(inc_url, data=inc_body, method='POST')
        inc_req.add_header('apikey', SUPABASE_KEY)
        inc_req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        inc_req.add_header('Content-Type', 'application/json')
        urllib.request.urlopen(inc_req, timeout=10)
    except Exception as _inc_e:
        print(f"[reprocess] Erro ao incrementar contador: {_inc_e}")

    # 5) Disparar em thread
    import threading
    t = threading.Thread(
        target=process_job,
        args=(new_job_id, new_file_paths, new_work_dir),
        kwargs={"typology": typology},
        daemon=True,
    )
    t.start()

    return {
        "status": "ok",
        "original_job_id": job_id,
        "new_job_id": new_job_id,
        "files_count": len(new_file_paths),
        "typology": typology,
    }


@app.post("/api/items/{job_id}/review-finalize")
async def finalize_review(job_id: str, request: Request):
    """Marca a revisão inline como concluída e credita cashback (R$0,10 por
    ação, teto R$ 20,00 por projeto).

    Chamado quando o usuário clica "Concluir revisão" na tela de revisão.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    user_id = body.get("user_id", "")

    # Cashback inline removido em 2026-05-13. Política nova:
    # - Revisar itens dentro do site: agradecimento, sem cashback (treinava IA
    #   mas era cognição confusa: R$ 0,10/item raramente atingia o teto).
    # - Cashback fica concentrado em ações de MAIOR sinal pra IA:
    #     * Upload de planilha revisada offline → R$ 30
    #     * Upload de cotação de fornecedor → R$ 10 (max 3 = R$ 30)
    # Total possível por projeto: R$ 60.
    try:
        # Ainda conta reviews pra retornar n_actions ao frontend (pra UI mostrar
        # progresso do usuário), mas não cria evento de cashback.
        rv_url = (f"{SUPABASE_URL}/rest/v1/item_reviews"
                  f"?job_id=eq.{job_id}&select=item_id&limit=5000")
        req = urllib.request.Request(rv_url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        resp = urllib.request.urlopen(req, timeout=10)
        reviews = json.loads(resp.read().decode("utf-8"))
        n_actions = len({r["item_id"] for r in reviews if r.get("item_id")})
    except Exception as e:
        n_actions = 0

    return {
        "status": "ok",
        "n_actions": n_actions,
        "credit_cents": 0,
        "credit_brl": 0.0,
        "message": "Obrigado pela revisão — suas correções treinam a IA pro próximo projeto.",
    }


@app.get("/api/items/{job_id}/review-state")
async def get_review_state(job_id: str, request: Request):
    """Retorna as revisões já feitas nesse job pra restaurar o estado no
    browser quando o user volta pra terminar depois.

    Retorna mapa {item_id: {action, edits, comment, reviewed_at}} com a
    última review de cada item."""
    _require_project_owner(request, job_id)
    import urllib.request, urllib.error, json
    try:
        url = (f"{SUPABASE_URL}/rest/v1/item_reviews"
               f"?job_id=eq.{job_id}"
               f"&select=item_id,action,edits,comment,reviewed_at"
               f"&order=reviewed_at.desc&limit=2000")
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        resp = urllib.request.urlopen(req, timeout=15)
        reviews = json.loads(resp.read().decode("utf-8"))
        # Manter só a MAIS RECENTE por item (supabase retorna ordenado desc)
        state = {}
        for r in reviews:
            iid = r.get("item_id")
            if iid and iid not in state:
                state[iid] = {
                    "action": r.get("action"),
                    "comment": r.get("comment") or "",
                    "reviewed_at": r.get("reviewed_at"),
                }
        return {"status": "ok", "job_id": job_id, "state": state, "count": len(state)}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar state: {e}")


# ═══════════════════════════════════════════════════════════════
#  INSIGHTS DE REVISÕES (pra admin entender o que ajustar no motor)
# ═══════════════════════════════════════════════════════════════

@app.get("/api/admin/review-insights")
async def admin_review_insights(request: Request, days: int = 30, limit: int = 30):
    """Agrega revisões recentes pra identificar padrões de erro do motor:
    - Quais tipos de item são mais rejeitados (alucinação)?
    - Quais edits são mais comuns (qty errada, unidade errada)?
    - Quais comentários o usuário deixou (insights qualitativos)?

    Serve pra eu (humano ou Claude) olhar e decidir o que ajustar no
    SYSTEM_PROMPT ou nas regras de consolidação."""
    _require_admin(request)
    import urllib.request, urllib.error, json

    # 1) Busca reviews recentes (com JOIN manual pra pegar description do item)
    try:
        url = (f"{SUPABASE_URL}/rest/v1/item_reviews"
               f"?select=id,job_id,item_id,action,edits,comment,reviewed_at"
               f"&reviewed_at=gte.{(datetime.utcnow() - timedelta(days=days)).isoformat()}"
               f"&order=reviewed_at.desc&limit=1000")
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        resp = urllib.request.urlopen(req, timeout=20)
        reviews = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar reviews: {e}")

    # 2) Enrich com descrição original do item (se ainda existe).
    # FIX 2026-05-14: N+1 eliminado — antes fazia 1 GET por review (até 1000
    # requests sequenciais ao Supabase, timeout em pico). Agora 1 GET batch
    # com `item_id=in.(id1,id2,...)`. Reduz pra 1 chamada (até 100 ids).
    from collections import Counter
    rejected_patterns = Counter()
    edit_patterns = Counter()
    comments = []
    by_typology = Counter()

    # Pré-busca descrições em batch
    item_descs = {}
    item_ids_uniq = [r.get("item_id") for r in reviews if r.get("item_id")]
    item_ids_uniq = list({i for i in item_ids_uniq if i})
    for i in range(0, len(item_ids_uniq), 100):
        chunk = item_ids_uniq[i:i+100]
        try:
            ids_csv = ",".join(str(x) for x in chunk)
            durl = (f"{SUPABASE_URL}/rest/v1/project_items"
                    f"?id=in.({ids_csv})&select=id,description,discipline")
            dreq = urllib.request.Request(durl, method="GET")
            dreq.add_header("apikey", SUPABASE_KEY)
            dreq.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
            dresp = urllib.request.urlopen(dreq, timeout=10)
            for row in json.loads(dresp.read().decode('utf-8')):
                item_descs[row.get("id")] = row.get("description", "")
        except Exception:
            pass

    for r in reviews:
        action = r.get("action", "")
        comment = (r.get("comment") or "").strip()
        if comment:
            comments.append({
                "comment": comment[:300],
                "action": action,
                "job_id": r.get("job_id"),
                "at": r.get("reviewed_at"),
            })

        item_id = r.get("item_id")
        item_desc = item_descs.get(item_id) if item_id else None

        if action == "reject" and item_desc:
            # Normaliza pra primeiras 3 palavras significativas
            key = " ".join(item_desc.lower().split()[:3])
            rejected_patterns[key] += 1

        if action == "edit":
            edits = r.get("edits") or {}
            if isinstance(edits, dict):
                for field in edits.keys():
                    edit_patterns[field] += 1

    return {
        "period_days": days,
        "total_reviews": len(reviews),
        "rejected_top": [
            {"pattern": k, "count": v}
            for k, v in rejected_patterns.most_common(limit)
        ],
        "edit_fields_top": [
            {"field": k, "count": v}
            for k, v in edit_patterns.most_common(limit)
        ],
        "comments_recent": comments[:limit],
    }


# ═══════════════════════════════════════════════════════════════
#  CLEANUP AUTOMÁTICO — retenção de 90 dias (LGPD)
#  Chamado diariamente via GitHub Actions cron. Deleta arquivos do
#  Storage e marca projetos como archived=true.
# ═══════════════════════════════════════════════════════════════

CLEANUP_RETENTION_DAYS = 90
CLEANUP_SECRET = os.getenv("CLEANUP_SECRET", "")


def _supabase_storage_delete(bucket: str, object_path: str) -> bool:
    """Deleta um objeto do Storage. Retorna True se OK (ou se já não existia)."""
    import urllib.request, urllib.error
    try:
        url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{object_path}"
        req = urllib.request.Request(url, method="DELETE")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        urllib.request.urlopen(req, timeout=15)
        return True
    except urllib.error.HTTPError as e:
        # 404 = já não existe (tudo ok)
        if e.code == 404:
            return True
        return False
    except Exception:
        return False


def _supabase_storage_list(bucket: str, prefix: str) -> list:
    """Lista objetos no bucket com o prefix dado. Retorna lista de nomes."""
    import urllib.request, json as _j
    try:
        url = f"{SUPABASE_URL}/storage/v1/object/list/{bucket}"
        body = _j.dumps({"prefix": prefix, "limit": 500}).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=15)
        files = _j.loads(resp.read().decode("utf-8"))
        return [f.get("name", "") for f in files if f.get("name")]
    except Exception as e:
        print(f"[cleanup] list {bucket}/{prefix}: {e}")
        return []


@app.get("/api/admin/cleanup-secret-check")
async def cleanup_secret_check(request: Request):
    """Debug: confirma se CLEANUP_SECRET está configurado no Render (sem
    expor o valor). Requer auth admin — anteriormente vazava first_4/last_4
    do segredo, reduzindo entropia pra brute-force do header X-Cleanup-Secret."""
    _require_admin(request)
    if not CLEANUP_SECRET:
        return {
            "configured": False,
            "message": "CLEANUP_SECRET NÃO está setado no Render. "
                       "Adicione em Environment e dê 'Save, rebuild, and deploy'."
        }
    return {
        "configured": True,
        "length": len(CLEANUP_SECRET),
        "message": "Secret configurada no Render."
    }


@app.post("/api/admin/cleanup-old-projects")
async def cleanup_old_projects(request: Request):
    """Deleta arquivos originais + planilha de projetos com 90+ dias.
    Marca projeto como archived=true pra preservar histórico no DB.

    Autenticação: header 'X-Cleanup-Secret' deve bater com env var
    CLEANUP_SECRET. Se CLEANUP_SECRET não estiver setado no Render, o
    endpoint responde 503.

    Chamado por GitHub Action cron diariamente."""
    # Auth
    provided_secret = request.headers.get("X-Cleanup-Secret", "")
    if not CLEANUP_SECRET:
        raise HTTPException(503, "CLEANUP_SECRET não configurado no ambiente")
    if provided_secret != CLEANUP_SECRET:
        raise HTTPException(401, "Secret inválido")

    # Query days pode customizar pra testes (default 90)
    import urllib.request, json as _j
    try:
        days = int(request.query_params.get("days", CLEANUP_RETENTION_DAYS))
    except Exception:
        days = CLEANUP_RETENTION_DAYS

    # 1) Lista projetos elegíveis via RPC
    try:
        url = f"{SUPABASE_URL}/rest/v1/rpc/list_expired_projects"
        body = _j.dumps({"p_days": days}).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=15)
        expired = _j.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar projetos expirados: {e}")

    stats = {
        "days_threshold": days,
        "total_expired": len(expired),
        "archived": 0,
        "files_deleted": 0,
        "errors": [],
        "jobs": [],
    }

    # 2) Pra cada projeto: deletar arquivos do Storage + marcar archived
    for proj in expired:
        job_id = proj.get("job_id")
        if not job_id:
            continue

        # 2a) Arquivos originais (bucket aiarq-pranchas/{job_id}/)
        pranchas_list = _supabase_storage_list(PRANCHAS_BUCKET, f"{job_id}/")
        files_ok = 0
        for obj in pranchas_list:
            # list retorna "nome.pdf" (sem prefix). Delete precisa do path completo.
            path = f"{job_id}/{obj}"
            if _supabase_storage_delete(PRANCHAS_BUCKET, path):
                files_ok += 1

        # 2b) Planilha (bucket aiarq-planilhas/{job_id}.xlsx)
        if _supabase_storage_delete(PLANILHAS_BUCKET, f"{job_id}.xlsx"):
            files_ok += 1

        # 2c) Marcar projeto como archived
        try:
            mark_url = f"{SUPABASE_URL}/rest/v1/rpc/mark_project_archived"
            mark_body = _j.dumps({"p_job_id": job_id}).encode("utf-8")
            mark_req = urllib.request.Request(mark_url, data=mark_body, method="POST")
            mark_req.add_header("apikey", SUPABASE_KEY)
            mark_req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
            mark_req.add_header("Content-Type", "application/json")
            urllib.request.urlopen(mark_req, timeout=10)
            stats["archived"] += 1
            stats["files_deleted"] += files_ok
            stats["jobs"].append({"job_id": job_id, "files_deleted": files_ok})
        except Exception as e:
            stats["errors"].append({"job_id": job_id, "error": str(e)[:200]})

    _supa_log(f"CLEANUP archived={stats['archived']} files={stats['files_deleted']} "
              f"errors={len(stats['errors'])}")
    print(f"[cleanup] {stats['archived']} projetos arquivados, "
          f"{stats['files_deleted']} arquivos deletados, "
          f"{len(stats['errors'])} erros")

    # Registra execução no cleanup_log pra monitoramento no admin
    _supabase_insert("cleanup_log", {
        "days_threshold": days,
        "total_expired": stats["total_expired"],
        "archived": stats["archived"],
        "files_deleted": stats["files_deleted"],
        "errors_count": len(stats["errors"]),
        "details": {"jobs": stats["jobs"][:50]},  # limita tamanho
    })

    return stats


@app.get("/api/admin/cleanup-log")
async def admin_cleanup_log(request: Request, limit: int = 30):
    """Retorna últimas execuções do cleanup pra dashboard admin."""
    _require_admin(request)
    import urllib.request, json as _j
    try:
        url = f"{SUPABASE_URL}/rest/v1/rpc/list_cleanup_runs"
        body = _j.dumps({"p_limit": limit}).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=10)
        return {"runs": _j.loads(resp.read().decode("utf-8"))}
    except Exception as e:
        raise HTTPException(500, f"Erro: {e}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
# Trigger autodeploy Mon Apr 13 10:58:57     2026
