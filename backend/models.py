# -*- coding: utf-8 -*-
from pydantic import BaseModel
from enum import Enum
from typing import Optional


class SheetType(str, Enum):
    DEMOLIR = "demolir"
    LAYOUT_NOVO = "layout_novo"
    LAYOUT_ATUAL = "layout_atual"
    MOBILIARIO = "mobiliario"
    MARCENARIA = "marcenaria"
    ARQUITETURA = "arquitetura"
    PONTOS = "pontos"
    PISO = "piso"
    FORRO = "forro"
    DET_FORRO = "det_forro"
    DETALHE_AMBIENTE = "detalhe_ambiente"  # ampliação/detalhe de um ambiente específico (banheiro, cozinha, etc)
    ESTRUTURA = "estrutura"  # prancha de projeto estrutural (fôrma, armadura, fundação)
    DESCONHECIDO = "desconhecido"


class Confidence(str, Enum):
    CONFIRMADO = "confirmado"
    ESTIMADO = "estimado"
    VERIFICAR = "verificar"


class BudgetItem(BaseModel):
    item_num: str
    description: str
    unit: str
    quantity: float
    observations: str = ""
    ref_sheet: str = ""
    confidence: Confidence = Confidence.ESTIMADO
    # Origem do dado: 'dxf_geom' (medido por geometria ezdxf) ou 'vision_pdf'
    # (lido pela IA numa imagem de PDF). Só 'dxf_geom' pode receber o selo
    # BRANCO/MEDIDO na planilha — Vision nunca mede geometria de verdade.
    origem: str = ""
    discipline: str = ""
    # Matches da base SINAPI (Caixa). Preenchido pelo sinapi_matcher antes
    # da geração da planilha. Formato: lista de dicts com codigo, descricao,
    # unidade, familia_id, similarity, opcionalmente _match_level/_match_query.
    sinapi_matches: list = []
    # Matches da base TCPO BIM (composições técnicas de referência).
    tcpo_matches: list[dict] = []


class ProjectData(BaseModel):
    name: str = ""
    address: str = ""
    architect: str = ""
    total_area: float = 0
    layout_area: float = 0
    no_intervention_area: float = 0
    workstations: int = 0
    phase: str = "Anteprojeto"
    departments: list[dict] = []
    demolition_notes: list[str] = []
    new_rooms: list[str] = []
    kept_elements: list[str] = []
    warnings: list[str] = []  # avisos gerados pela IA: prancha órfã, legenda faltante, status indefinido


class ProcessingStatus(BaseModel):
    job_id: str
    status: str = "queued"  # queued, processing, done, error
    progress: int = 0
    current_step: str = ""
    total_steps: int = 0
    error_message: str = ""
    download_url: str = ""


class SheetInfo(BaseModel):
    filename: str
    sheet_type: SheetType
    text_content: str = ""
    crops: list[str] = []  # paths to cropped images
