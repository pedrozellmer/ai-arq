# -*- coding: utf-8 -*-
"""O anexo confere o CONTEÚDO do CAD antes de deixar "DXF vencer DWG do mesmo nome".

🩸 05/09/2026, William, 3º anexo do dia (job 8b7a2b71, 19:24). O /add-file tinha
a regra "DXF vence o DWG do mesmo nome", julgada pelo NOME: um .dxf que era DWG
renomeado "venceu" o .dwg de verdade e o jogou fora. Em seguida, no process_job,
a checagem pelo conteúdo (conserto da manhã do mesmo dia) viu que o "DXF" era
DWG com o irmão .dwg no disco e descartou a cópia. Sobrou ZERO arquivo: zero
item em 0,3 s, sem erro, sem e-mail, e um aviso na tela dizendo que o arquivo
dele "não rendeu nenhum item". Duas regras certas, na ordem errada — o conserto
fechou o processamento normal e deixou a porta do anexo com a mesma doença.

Regra: no anexo, o conteúdo vem PRIMEIRO (`_escolher_cads_do_anexo`); só então
"DXF vence DWG do mesmo nome" enxerga DXF de verdade.
🧪 Controles: DXF de verdade continua vencendo o DWG (forro MEP do Pedro, 15/07);
DWG disfarçado sozinho vira .dwg e o cliente é avisado; e a ORDEM ANTIGA, rodada
sobre o mesmo par, devolve ZERO — a prova de que o defeito era a ordem.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main  # noqa: E402
from _corpo import corpo_de  # noqa: E402

DWG = b"AC1027" + b"\x00" * 58                      # DWG do AutoCAD 2013 (cabeçalho real)
DXF = b"0\r\nSECTION\r\n2\r\nHEADER\r\n0\r\nENDSEC\r\n0\r\nEOF\r\n"


def _arq(tmp_path, nome, conteudo):
    p = tmp_path / nome
    p.write_bytes(conteudo)
    return str(p)


def _nomes(paths):
    return sorted(os.path.basename(p) for p in paths)


@pytest.fixture
def silencio(monkeypatch):
    """`_normalizar_extensao_cad` registra no error_log; aqui vira lista."""
    logs = []
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: logs.append(a))
    return logs


def test_PRECONDICAO_os_fixtures_sao_lidos_como_dwg_e_dxf(tmp_path):
    assert main._formato_cad_pelo_conteudo(_arq(tmp_path, "a.bin", DWG)) == "dwg"
    assert main._formato_cad_pelo_conteudo(_arq(tmp_path, "b.bin", DXF)) == "dxf"


# ── a regra ────────────────────────────────────────────────────────────────
def test_dwg_disfarcado_de_dxf_NAO_mata_o_dwg_de_verdade(tmp_path, silencio):
    falso = _arq(tmp_path, "x.dxf", DWG)
    real = _arq(tmp_path, "x.dwg", DWG)
    cads, _avisos = main._escolher_cads_do_anexo([falso, real], "job-t")
    assert cads, "o reprocesso rodaria com ZERO arquivo — o defeito do William"
    assert _nomes(cads) == ["x.dwg"], cads


def test_dxf_de_verdade_continua_vencendo_o_dwg_do_mesmo_nome(tmp_path, silencio):
    dxf = _arq(tmp_path, "y.dxf", DXF)
    dwg = _arq(tmp_path, "y.dwg", DWG)
    cads, _ = main._escolher_cads_do_anexo([dxf, dwg], "job-t")
    assert _nomes(cads) == ["y.dxf"], "o DXF re-exportado tem que seguir vencendo o DWG que falhava"


def test_dwg_disfarcado_sozinho_vira_dwg_e_o_cliente_e_avisado(tmp_path, silencio):
    falso = _arq(tmp_path, "z.dxf", DWG)
    cads, avisos = main._escolher_cads_do_anexo([falso], "job-t")
    assert _nomes(cads) == ["z.dwg"] and os.path.exists(cads[0])
    assert len(avisos) == 1 and ".dxf" in avisos[0] and "DWG" in avisos[0], avisos


def test_lista_vazia_nao_quebra(silencio):
    assert main._escolher_cads_do_anexo([], "job-t") == ([], [])


# ── controle positivo: a ORDEM ANTIGA reproduz o zero ─────────────────────
def test_CONTROLE_a_ordem_antiga_devolvia_ZERO_no_mesmo_par(tmp_path, silencio):
    falso = _arq(tmp_path, "x.dxf", DWG)
    real = _arq(tmp_path, "x.dwg", DWG)
    # 1) pelo NOME (a regra antiga do /add-file): o .dxf "vence" e o .dwg sai
    stems = {"x"}
    depois_do_nome = [p for p in (falso, real)
                      if not (p.endswith(".dwg") and os.path.splitext(os.path.basename(p))[0] in stems)]
    assert _nomes(depois_do_nome) == ["x.dxf"]
    # 2) pelo CONTEÚDO (process_job): a cópia é descartada porque x.dwg existe no disco
    sobrou, _, _ = main._normalizar_extensao_cad(depois_do_nome, "job-t")
    assert sobrou == [], "a ordem antiga não reproduz o zero — os testes de cima não provam nada"


# ── o /add-file usa o seletor; o alerta diz a verdade ─────────────────────
def test_o_add_file_usa_o_seletor_e_nao_a_regra_pelo_nome():
    c = corpo_de("add_file_and_reprocess")
    assert "_escolher_cads_do_anexo(_cads, job_id)" in c
    assert "_dxf_stems" not in c, "a regra pelo nome voltou pro /add-file, antes do conteúdo"
    assert "_avisos_com(job_id, _avisos_ext)" in c, "o aviso da extensão não chega ao cliente"


def test_o_alerta_diz_o_que_a_pessoa_anexou_E_o_que_vai_rodar():
    c = corpo_de("add_file_and_reprocess")
    assert "_enviados.append(safe_local)" in c
    assert "for n in _enviados[:4]" in c, "o alerta voltou a listar file_paths como 'anexados agora'"
    assert "Arquivos anexados agora:</b> {_novos}" in c
    assert "Vai processar:</b> {_vai}" in c
