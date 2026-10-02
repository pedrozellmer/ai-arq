# -*- coding: utf-8 -*-
"""O chat não diz que o DWG "não foi convertido" quando o DXF temporário sumiu.

🩸 02/10/2026 (job 72a9aafe): depois do done o DXF do processamento já não
existe; `read_dxf_summary` devolvia `available_dxfs: []` e o chat disse a um
cliente novo que "o DWG não foi convertido", que a planilha era "leitura de
imagem" e que reenviando em DXF "a área sai medida". Os três eram falsos (o
motivo era a unidade e a planta repetida), e ele anexou o PDF à toa.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import agent  # noqa: E402
from test_o_chat_acha_o_item_pelas_palavras import _rodar_ask  # noqa: E402


def test_dxf_temporario_que_sumiu_vem_com_o_aviso(monkeypatch, tmp_path):
    monkeypatch.setattr(agent, "WORK_DIR", str(tmp_path))
    (tmp_path / "job1").mkdir()
    (tmp_path / "job1" / "casa.dwg").write_bytes(b"x")
    r = agent.tool_read_dxf_summary("job1")
    assert r["available_dxfs"] == []
    assert "NÃO quer dizer que o DWG não foi convertido" in r["aviso"], r
    assert "Nunca sugira reenviar em DXF" in r["aviso"], r


def test_pasta_do_job_que_ja_foi_limpa_tambem(monkeypatch, tmp_path):
    monkeypatch.setattr(agent, "WORK_DIR", str(tmp_path))
    r = agent.tool_read_dxf_summary("job-que-nao-existe-mais")
    assert r.get("available_dxfs") == [] and "aviso" in r and "error" not in r, r


def test_o_contexto_de_projeto_com_DWG_proibe_as_tres_frases(monkeypatch):
    system, ferramentas = _rodar_ask(monkeypatch, {"pdf": 0, "dxf": 0, "dwg": 1})
    assert "read_dxf_summary" in ferramentas, ferramentas
    assert "Nunca diga que o DWG não foi convertido" in system, system[-900:]
    assert "nem que as quantidades vieram de imagem" in system, system[-900:]
    assert "nem sugira reenviar em DXF" in system, system[-900:]


# ── o que NÃO muda ─────────────────────────────────────────────────────────────
def test_CONTROLE_com_o_DXF_guardado_lista_sem_aviso(monkeypatch, tmp_path):
    monkeypatch.setattr(agent, "WORK_DIR", str(tmp_path))
    (tmp_path / "job2").mkdir()
    (tmp_path / "job2" / "planta.dxf").write_text("0\nEOF\n")
    r = agent.tool_read_dxf_summary("job2")
    assert r == {"available_dxfs": ["planta.dxf"]}, r


def test_CONTROLE_projeto_so_PDF_continua_sem_DXF_nenhum(monkeypatch):
    system, ferramentas = _rodar_ask(monkeypatch, {"pdf": 1, "dxf": 0, "dwg": 0})
    assert "read_dxf_summary" not in ferramentas, ferramentas
    assert "NENHUM DWG ou DXF" in system, system[-700:]
