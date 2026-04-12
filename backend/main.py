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
    """Processa um job de forma síncrona (roda em background)."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        jobs[job_id].status = "error"
        jobs[job_id].error_message = "API key não configurada"
        return

    try:
        total_steps = 3
        jobs[job_id].total_steps = total_steps

        # PASSO 1: Processar PDFs (extrair texto + renderizar crops)
        jobs[job_id].status = "processing"
        jobs[job_id].progress = 10
        jobs[job_id].current_step = "Extraindo dados dos PDFs..."

        sheets = process_pdfs(pdf_paths, work_dir)

        jobs[job_id].progress = 30
        jobs[job_id].current_step = f"{len(sheets)} pranchas identificadas. Analisando com IA..."

        # PASSO 2: Analisar com Claude API
        def progress_cb(current, total, msg):
            pct = 30 + int((current / max(total, 1)) * 50)
            jobs[job_id].progress = min(pct, 80)
            jobs[job_id].current_step = msg

        project_data, items = analyze_all_sheets(sheets, api_key, progress_cb)

        jobs[job_id].progress = 85
        jobs[job_id].current_step = f"Gerando planilha com {len(items)} itens..."

        # PASSO 3: Gerar planilha
        output_path = os.path.join(work_dir, f"orcamento_{job_id}.xlsx")
        generate_spreadsheet(project_data, items, output_path)

        jobs[job_id].progress = 100
        jobs[job_id].status = "done"
        jobs[job_id].current_step = "Concluído!"
        jobs[job_id].download_url = f"/api/download/{job_id}"

    except Exception as e:
        jobs[job_id].status = "error"
        jobs[job_id].error_message = str(e)
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

    # Iniciar processamento em background
    background_tasks.add_task(process_job, job_id, pdf_paths, work_dir)

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
