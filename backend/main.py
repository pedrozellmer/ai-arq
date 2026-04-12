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

# Armazenamento de jobs em memória (produção usaria Redis/DB)
jobs: dict[str, ProcessingStatus] = {}
WORK_DIR = os.path.join(tempfile.gettempdir(), "aiarq_jobs")
os.makedirs(WORK_DIR, exist_ok=True)


def process_job(job_id: str, pdf_paths: list[str], work_dir: str):
    """Processa um job prancha por prancha pra economizar memória."""
    import gc
    import anthropic
    from processor import identify_sheet_type, extract_text, render_crops
    from analyzer import analyze_sheet, SYSTEM_PROMPT
    from models import SheetInfo, SheetType, ProjectData, BudgetItem, Confidence

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        jobs[job_id].status = "error"
        jobs[job_id].error_message = "API key não configurada"
        return

    try:
        jobs[job_id].status = "processing"
        total = len(pdf_paths)
        client = anthropic.Anthropic(api_key=api_key)
        all_items = []
        project_data = ProjectData()
        crops_dir = os.path.join(work_dir, "crops")
        os.makedirs(crops_dir, exist_ok=True)

        # Ordenar por prioridade (layout primeiro)
        priority = {"layout_novo": 0, "layout_atual": 1, "demolir": 2, "arquitetura": 3,
                     "forro": 4, "piso": 5, "pontos": 6, "mobiliario": 7, "marcenaria": 8, "det_forro": 9}

        pdf_infos = []
        for pdf_path in pdf_paths:
            filename = os.path.basename(pdf_path)
            sheet_type = identify_sheet_type(filename)
            pdf_infos.append((pdf_path, filename, sheet_type))

        pdf_infos.sort(key=lambda x: priority.get(x[2].value, 99))

        for i, (pdf_path, filename, sheet_type) in enumerate(pdf_infos):
            step_pct = int((i / total) * 90) + 5
            jobs[job_id].progress = step_pct
            jobs[job_id].current_step = f"Etapa {i+1}/{total}: {filename}"

            if sheet_type == SheetType.DESCONHECIDO:
                continue

            # 1. Extrair texto
            text = extract_text(pdf_path)

            # 2. Renderizar crops (1 PDF de cada vez)
            crop_paths = render_crops(pdf_path, sheet_type, crops_dir)

            # 3. Analisar com IA
            jobs[job_id].current_step = f"Etapa {i+1}/{total}: Analisando {filename} com IA..."
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
                def sf(v):
                    if v is None: return 0
                    s = str(v).replace('m²','').replace('m2','').replace('cm','').replace(',','').strip()
                    try: return float(s)
                    except: return 0
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

        # Gerar planilha
        jobs[job_id].progress = 92
        jobs[job_id].current_step = f"Gerando planilha com {len(all_items)} itens..."

        output_path = os.path.join(work_dir, f"orcamento_{job_id}.xlsx")
        generate_spreadsheet(project_data, all_items, output_path)

        jobs[job_id].progress = 100
        jobs[job_id].status = "done"
        jobs[job_id].current_step = "Concluído!"
        jobs[job_id].download_url = f"/api/download/{job_id}"

    except Exception as e:
        jobs[job_id].status = "error"
        jobs[job_id].error_message = str(e)
        jobs[job_id].current_step = f"Erro: {str(e)[:200]}"
        jobs[job_id].current_step = f"Erro: {str(e)[:200]}"


@app.get("/")
async def root():
    return {"service": "AI.arq API", "version": "1.0.0", "status": "online"}


@app.post("/api/process")
async def process_files(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
):
    """Recebe PDFs e inicia processamento em background."""
    if not files:
        raise HTTPException(400, "Nenhum arquivo enviado")

    # Validar arquivos
    pdf_files = [f for f in files if f.filename and f.filename.lower().endswith('.pdf')]
    if not pdf_files:
        raise HTTPException(400, "Nenhum arquivo PDF encontrado")

    if len(pdf_files) > 20:
        raise HTTPException(400, "Máximo de 20 pranchas por projeto")

    # Criar job
    job_id = str(uuid.uuid4())[:8]
    work_dir = os.path.join(WORK_DIR, job_id)
    os.makedirs(work_dir, exist_ok=True)

    # Salvar PDFs
    pdf_paths = []
    for pdf_file in pdf_files:
        file_path = os.path.join(work_dir, pdf_file.filename)
        with open(file_path, "wb") as f:
            content = await pdf_file.read()
            f.write(content)
        pdf_paths.append(file_path)

    # Criar status
    jobs[job_id] = ProcessingStatus(
        job_id=job_id,
        status="queued",
        progress=0,
        current_step=f"Recebidos {len(pdf_paths)} PDFs. Iniciando processamento...",
        total_steps=3,
    )

    # Iniciar processamento em thread separada (não bloqueia HTTP)
    import threading
    t = threading.Thread(target=process_job, args=(job_id, pdf_paths, work_dir), daemon=True)
    t.start()

    return {"job_id": job_id, "files_received": len(pdf_paths), "status": "queued"}


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
    """Health check."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    return {
        "status": "healthy",
        "api_key_configured": bool(api_key and api_key.startswith("sk-")),
        "timestamp": datetime.utcnow().isoformat(),
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
