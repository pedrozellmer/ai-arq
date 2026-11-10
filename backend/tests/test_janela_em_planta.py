# -*- coding: utf-8 -*-
"""Bloco de janela em PLANTA mede largura × espessura da parede, não altura.

🩸 03/11/2026 (job 5a1ee9d4): "J15: ~1,64m × 0,22m = 0,36 m²" virou "Janela J15 —
dimensão aproximada 1,64×0,22 m" na planilha, e o cliente manteve a linha.
🔑 JANELA_EM_PLANTA=1 (lida na extração) faz o texto da IA dizer só a largura e
que a outra medida é a parede; com 0 o texto é o de antes e o motor só conta.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dwg_extractor as dx  # noqa: E402
import main  # noqa: E402


def _bloco(nome, w, h, n=8):
    return dx.BlockCount(name=nome, count=n, layer="ESQUADRIAS", width_m=w, height_m=h)


def _extracao(blocos, liga):
    return dx.DXFExtraction(filename="planta cliente-nn.dxf", blocks=blocos, walls=[],
                            hatches=[], texts=[], layers=["ESQUADRIAS"], dimensions=[],
                            janela_em_planta=liga)


@pytest.mark.parametrize("w,h,em_planta", [
    (1.64, 0.22, True), (0.22, 1.64, True), (1.00, 0.13, True), (1.05, 0.35, True),
    (0.75, 0.25, True), (0.74, 0.25, False),
    (1.20, 0.36, False), (0.90, 0.35, False), (0.60, 0.30, False),
    (1.20, 1.00, False), (0.80, 2.10, False), (0, 0.2, False), (1.5, 0, False)])
def test_quando_o_bloco_e_simbolo_em_planta(w, h, em_planta):
    assert dx.esquadria_em_planta(_bloco("J", w, h)) is em_planta


def test_medida_que_nao_e_numero_nao_e_planta():
    assert dx.esquadria_em_planta(_bloco("J", "x", 0.2)) is False


def test_com_a_chave_em_0_o_texto_e_o_de_antes():
    txt = _extracao([_bloco("J15", 1.64, 0.22)], False).to_structured_prompt()
    assert "J15: 8 un  |  ~1.64m × 0.22m = 0.36 m²" in txt
    assert "espessura da parede" not in txt


def test_com_a_chave_em_1_so_a_largura_e_o_aviso():
    txt = _extracao([_bloco("J15", 1.64, 0.22), _bloco("P80", 0.80, 2.10, n=2)],
                    True).to_structured_prompt()
    assert ("J15: 8 un  |  bloco FINO ~1.64m × 0.22m: o 0.22m é a espessura da parede "
            "(esquadria vista de lado: planta, corte ou fachada); o 1.64m é a largura "
            "em planta ou a altura em corte/fachada. NÃO dá a área do vão") in txt
    assert "0.36 m²" not in txt
    assert "P80: 2 un  |  ~0.80m × 2.10m = 1.68 m²" in txt


def test_bloco_de_pe_tambem_poe_a_maior_medida_primeiro():
    txt = _extracao([_bloco("J9", 0.20, 1.10)], True).to_structured_prompt()
    assert "J9: 8 un  |  bloco FINO ~1.10m × 0.20m: o 0.20m é a espessura" in txt


def test_porta_cortada_no_corte_nao_vira_largura_em_planta():
    """🪤 10/11: "Porta Pivotante 90x210-Corte 1" (Revit) caiu na régua — no corte o
    bloco é espessura × ALTURA. O texto não pode chamar os 2,10 m de largura."""
    txt = _extracao([_bloco("Porta Pivotante 90x210-Corte 1", 0.12, 2.10, n=1)],
                    True).to_structured_prompt()
    assert "em PLANTA (" not in txt and "largura ~2.10m" not in txt
    assert "o 2.10m é a largura em planta ou a altura em corte/fachada" in txt


def test_a_chave_vem_do_ambiente_da_extracao(monkeypatch):
    with open(dx.__file__, encoding="utf-8") as f:
        fonte = f.read()
    assert 'janela_em_planta=os.environ.get("JANELA_EM_PLANTA", "0") == "1",' in fonte
    assert dx.DXFExtraction(filename="a", blocks=[], walls=[], hatches=[], texts=[],
                            layers=[], dimensions=[]).janela_em_planta is False


def _logs(monkeypatch):
    logs = []
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: logs.append(a))
    return logs


def test_o_registro_conta_os_blocos_em_planta(monkeypatch):
    logs = _logs(monkeypatch)
    ext = _extracao([_bloco("J15", 1.64, 0.22), _bloco("J15", 1.64, 0.22, n=2),
                     _bloco("j10", 1.0, 0.13), _bloco("P80", 0.8, 2.1)], False)
    main._registra_janela_em_planta(ext, "planta.dxf", "j")
    assert logs == [("motor:janela-em-planta", "planta.dxf: 2 bloco(s) liga=0 | J15, j10", "j")]


def test_registro_com_a_chave_ligada_e_no_maximo_8_nomes(monkeypatch):
    logs = _logs(monkeypatch)
    ext = _extracao([_bloco("J%02d" % i, 1.5, 0.2) for i in range(10)], True)
    main._registra_janela_em_planta(ext, "p.dxf", "j")
    assert logs[0][1].startswith("p.dxf: 10 bloco(s) liga=1 | J00")
    assert "J07" in logs[0][1] and "J08" not in logs[0][1]


def test_sem_bloco_em_planta_nao_registra_e_falha_nao_derruba(monkeypatch):
    logs = _logs(monkeypatch)
    main._registra_janela_em_planta(_extracao([_bloco("P80", 0.8, 2.1)], False), "p", "j")
    main._registra_janela_em_planta(object(), "p", "j")
    main._registra_janela_em_planta(None, "p", "j")
    assert logs == []


def test_o_laco_do_dxf_registra_depois_dos_quadros():
    with open(main.__file__, encoding="utf-8") as f:
        fonte = f.read().replace("\r\n", "\n")
    assert ("extraction, structured_text, _quadros_do_job, _dxf_nome, job_id)\n"
            "                    _registra_janela_em_planta(extraction, _dxf_nome, job_id)") in fonte


def test_chave_avaliavel_e_etapa_de_diagnostico():
    assert "JANELA_EM_PLANTA" in main._CHAVES_AVALIAVEIS
    assert "motor:janela-em-planta" in main._STAGES_DIAGNOSTICO
