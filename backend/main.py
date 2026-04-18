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
try:
    from calibrator import (
        compare_spreadsheets,
        save_calibration_data,
        get_correction_factors,
        apply_corrections,
    )
    HAS_CALIBRATOR = True
except ImportError:
    HAS_CALIBRATOR = False
    print("calibrator.py não disponível — calibração desativada")

# Supabase client para salvar projetos
SUPABASE_URL = "https://kqjabzwgbfuivzlcfvvu.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtxamFiendnYmZ1aXZ6bGNmdnZ1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYwMDg5NzcsImV4cCI6MjA5MTU4NDk3N30.48xSenZlDV0LfD94ZxwGvX41Kf9Je2n-ouZpJrrCSKI"

def _supabase_insert(table, data):
    """Insere registro no Supabase via REST API."""
    try:
        import urllib.request, json
        url = f"{SUPABASE_URL}/rest/v1/{table}"
        body = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Prefer', 'return=minimal')
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception as e:
        print(f"Supabase insert error: {e}")
        return False

def _supabase_update(table, match_field, match_value, data):
    """Atualiza registro no Supabase via REST API."""
    try:
        import urllib.request, json
        url = f"{SUPABASE_URL}/rest/v1/{table}?{match_field}=eq.{match_value}"
        body = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='PATCH')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Prefer', 'return=minimal')
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception as e:
        print(f"Supabase update error: {e}")
        return False

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


def process_job(job_id: str, file_paths: list[str], work_dir: str):
    """Processa um job prancha por prancha. Aceita PDF, DWG e DXF."""
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

        # Pesos de progresso conforme tipos de arquivo
        has_cad = bool(cad_paths)
        has_pdf = bool(pdf_paths)
        # Se só CAD: CAD vai de 5% a 90%. Se só PDF: PDF vai de 5% a 95%. Misto: CAD 5-45%, PDF 45-95%.
        cad_end_pct = 45 if has_pdf else 90

        # Converter DWG→DXF se necessário
        dxf_paths = []
        if cad_paths:
            jobs.update_field(job_id, progress=8)
            jobs.update_field(job_id, current_step="Processando arquivos DWG/DXF...")
            try:
                from dwg_extractor import extract_from_file, generate_budget_data, convert_dwg_to_dxf
                n_cad = len(cad_paths)
                # Conversão DWG→DXF usa primeiros 35% da fase CAD (8% → cad_end_pct*0.4)
                conv_span = int((cad_end_pct - 8) * 0.4)
                for ci, cad_path in enumerate(cad_paths):
                    base = 8 + int((ci / max(n_cad, 1)) * conv_span)
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
            extract_start = 8 + int((cad_end_pct - 8) * 0.4)
            jobs.update_field(job_id, progress=extract_start)
            jobs.update_field(job_id, current_step="Extraindo geometria dos DXF...")
            try:
                from dwg_extractor import extract_from_file
                from analyzer import SYSTEM_PROMPT
                import json as _j

                n_dxf = len(dxf_paths)
                dxf_span = cad_end_pct - extract_start  # espaço restante até cad_end_pct
                for idx, dxf_path in enumerate(dxf_paths):
                    # Cada DXF ocupa uma faixa: extração 40%, IA 60% da faixa
                    dxf_base = extract_start + int((idx / max(n_dxf, 1)) * dxf_span)
                    dxf_next = extract_start + int(((idx + 1) / max(n_dxf, 1)) * dxf_span)
                    dxf_mid = dxf_base + int((dxf_next - dxf_base) * 0.4)

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
   - Comprimento calculado em "COMPRIMENTOS POR LAYER" (valor em metros)
   - Área calculada em "ÁREAS HACHURADAS POR LAYER" (valor em m²)
   - Cota numérica que aparece em "COTAS/DIMENSÕES"
   A quantidade do item TEM que bater com o número extraído. Se você multiplicou, somou
   ou fez qualquer cálculo além de copiar o valor, NÃO é confirmado.

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

Retorne APENAS JSON válido no formato:
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
      "observations": "Fonte: DXF bloco X / área layer Y / comprimento layer Z (cite a fonte EXATA dos dados extraídos)",
      "ref_sheet": "DXF",
      "confidence": "confirmado ou estimado — nunca inventar",
      "discipline": "Categoria"
    }}
  ]
}}"""

                    try:
                        response = dxf_client.messages.create(
                            model="claude-sonnet-4-20250514",
                            max_tokens=8000,
                            temperature=0,
                            system=SYSTEM_PROMPT,
                            messages=[{"role": "user", "content": dxf_prompt}],
                        )

                        text = response.content[0].text
                        if "```json" in text:
                            json_str = text.split("```json")[1].split("```")[0].strip()
                        elif "```" in text:
                            json_str = text.split("```")[1].split("```")[0].strip()
                        else:
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
                                qty = sf(item_data.get("quantity", 1))
                                if qty <= 0: qty = 1

                                item = BudgetItem(
                                    item_num=str(item_data.get("item_num", "")),
                                    description=desc,
                                    unit=item_data.get("unit", "vb"),
                                    quantity=qty,
                                    observations=item_data.get("observations", "Fonte: DXF"),
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
                    qty_raw = item_data.get("quantity", 1)
                    qty = sf(qty_raw) if qty_raw else 1
                    if qty <= 0: qty = 1

                    item = BudgetItem(
                        item_num=str(item_data.get("item_num", "")),
                        description=desc,
                        unit=item_data.get("unit", "vb"),
                        quantity=qty,
                        observations=item_data.get("observations", ""),
                        ref_sheet=item_data.get("ref_sheet", f"Pr.{filename[:7]}"),
                        confidence=Confidence(conf),
                        discipline=discipline,
                    )
                    all_items.append(item)
                except: continue

            # 6. Liberar memória desta prancha
            del text, crop_paths, sheet, result
            gc.collect()

        # ── Auto-calibração: aplicar fatores de correção ──
        jobs.update_field(job_id, progress=91)
        jobs.update_field(job_id, current_step="Aplicando calibração baseada em projetos anteriores...")
        try:
            cal_factors = get_correction_factors()
            if cal_factors:
                all_items = apply_corrections(all_items, cal_factors)
        except Exception as e:
            print(f"[calibrator] Erro ao aplicar correções: {e}")

        # Gerar planilha
        jobs.update_field(job_id, progress=92)
        jobs.update_field(job_id, current_step=f"Gerando planilha com {len(all_items)} itens...")

        output_path = os.path.join(work_dir, f"orcamento_{job_id}.xlsx")
        generate_spreadsheet(project_data, all_items, output_path)

        jobs.update_field(job_id, progress=100)
        jobs.update_field(job_id, status="done")
        jobs.update_field(job_id, current_step="Concluído!")
        jobs.update_field(job_id, download_url=f"/api/download/{job_id}")

        # Atualizar projeto no Supabase
        _supabase_update("projects", "job_id", job_id, {
            "status": "done",
            "items_count": len(all_items),
            "total_area": project_data.total_area if project_data.total_area else None,
            "completed_at": datetime.utcnow().isoformat(),
        })

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


@app.post("/api/process")
async def process_files(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
):
    """Recebe PDF, DWG ou DXF e inicia processamento em background."""
    if not files:
        raise HTTPException(400, "Nenhum arquivo enviado")

    # Validar arquivos (aceitar PDF, DWG e DXF)
    valid_extensions = ('.pdf', '.dwg', '.dxf')
    valid_files = [f for f in files if f.filename and f.filename.lower().endswith(valid_extensions)]
    if not valid_files:
        raise HTTPException(400, "Nenhum arquivo válido encontrado. Aceito: PDF, DWG ou DXF.")

    if len(valid_files) > 20:
        raise HTTPException(400, "Máximo de 20 arquivos por projeto")

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
        "files_count": len(file_paths),
        "file_types": file_types,
        "status": "queued",
    })

    # Iniciar processamento em thread separada (não bloqueia HTTP)
    import threading
    t = threading.Thread(target=process_job, args=(job_id, file_paths, work_dir), daemon=True)
    t.start()

    return {"job_id": job_id, "files_received": len(file_paths), "file_types": file_types, "status": "queued"}


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
    """Baixa a planilha gerada."""
    if job_id not in jobs:
        raise HTTPException(404, "Job não encontrado")

    if jobs[job_id].status != "done":
        raise HTTPException(400, f"Job ainda não concluído. Status: {jobs[job_id].status}")

    work_dir = os.path.join(WORK_DIR, job_id)
    output_path = os.path.join(work_dir, f"orcamento_{job_id}.xlsx")

    if not os.path.exists(output_path):
        raise HTTPException(404, "Arquivo não encontrado")

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
    """Receive a user-revised XLSX, compare with original, and store calibration data."""
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Arquivo deve ser .xlsx")

    if not job_id:
        raise HTTPException(400, "job_id e obrigatorio")

    # Save revised file temporarily
    tmp_dir = os.path.join(WORK_DIR, "_calibration_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    revised_path = os.path.join(tmp_dir, f"revised_{job_id}_{file.filename}")
    try:
        content = await file.read()
        with open(revised_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(500, f"Erro ao salvar arquivo: {str(e)}")

    # Find the original XLSX for this job_id
    work_dir = os.path.join(WORK_DIR, job_id)
    original_path = os.path.join(work_dir, f"orcamento_{job_id}.xlsx")

    if not os.path.exists(original_path):
        # Clean up
        if os.path.exists(revised_path):
            os.remove(revised_path)
        raise HTTPException(404, f"Planilha original do job {job_id} nao encontrada")

    try:
        # Compare spreadsheets
        comparisons = compare_spreadsheets(original_path, revised_path)

        # Save to Supabase
        inserted = 0
        if comparisons:
            inserted = save_calibration_data(
                comparisons, source="user", project_id=job_id
            )

        # Calculate summary stats
        avg_deviation = 0
        if comparisons:
            avg_deviation = sum(c["deviation_pct"] for c in comparisons) / len(comparisons)

        return {
            "status": "ok",
            "items_compared": len(comparisons),
            "items_saved": inserted,
            "avg_deviation_pct": round(avg_deviation, 2),
            "comparisons": comparisons[:20],  # Return first 20 for UI display
            "cashback_granted": True,
        }

    except Exception as e:
        raise HTTPException(500, f"Erro na comparacao: {str(e)}")

    finally:
        # Clean up temp file
        if os.path.exists(revised_path):
            try:
                os.remove(revised_path)
            except:
                pass


@app.post("/api/calibration/manual")
async def calibration_manual(
    original: UploadFile = File(...),
    revised: UploadFile = File(...),
    source: str = "admin",
):
    """Admin endpoint: compare two XLSX files and store calibration data."""
    tmp_dir = os.path.join(WORK_DIR, "_calibration_tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    orig_path = os.path.join(tmp_dir, f"orig_{original.filename}")
    rev_path = os.path.join(tmp_dir, f"rev_{revised.filename}")

    try:
        orig_content = await original.read()
        with open(orig_path, "wb") as f:
            f.write(orig_content)

        rev_content = await revised.read()
        with open(rev_path, "wb") as f:
            f.write(rev_content)

        comparisons = compare_spreadsheets(orig_path, rev_path)

        inserted = 0
        if comparisons:
            inserted = save_calibration_data(
                comparisons, source=source, project_id="manual"
            )

        avg_deviation = 0
        if comparisons:
            avg_deviation = sum(c["deviation_pct"] for c in comparisons) / len(comparisons)

        return {
            "status": "ok",
            "items_compared": len(comparisons),
            "items_saved": inserted,
            "avg_deviation_pct": round(avg_deviation, 2),
            "comparisons": comparisons,
        }

    except Exception as e:
        raise HTTPException(500, f"Erro na comparacao manual: {str(e)}")

    finally:
        for p in [orig_path, rev_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except:
                    pass


@app.get("/api/calibration/factors")
async def calibration_factors():
    """Return current correction factors from the calibration system."""
    try:
        factors = get_correction_factors()
        # Convert to list for JSON response
        factors_list = []
        for item_type, data in factors.items():
            factors_list.append({
                "item_type": item_type,
                "discipline": data.get("discipline", ""),
                "unit": data.get("unit", ""),
                "factor": data.get("factor", 1.0),
                "data_points": data.get("data_points", 0),
                "deviation": data.get("deviation", 0),
                "stddev": data.get("stddev"),
                "min_factor": data.get("min_factor"),
                "max_factor": data.get("max_factor"),
            })
        # Sort by data_points descending
        factors_list.sort(key=lambda x: x["data_points"], reverse=True)
        return {"status": "ok", "count": len(factors_list), "factors": factors_list}
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar fatores: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
# Trigger autodeploy Mon Apr 13 10:58:57     2026
