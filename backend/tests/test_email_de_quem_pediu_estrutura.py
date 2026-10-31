# -*- coding: utf-8 -*-
"""Quem pediu Estrutura e mandou arquitetura recebe o caminho certo no e-mail.

🩸 31/10/2026 (c14f3ea5): o e-mail abria com "na maioria das vezes é escala" e pedia
DXF, e o aviso de tipo ficava lá embaixo, no diagnóstico. O DXF das mesmas pranchas
não resolve: o que resolve é reler como Arquitetura ou mandar as de estrutura.
🪤 O aviso vem de `_is_likely_wrong_type`, que só olha quantidades: é palpite, e o
texto diz "parecem".
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
import main  # noqa: E402


def _html(**kw):
    return main._build_sem_medida_email("Fulano", "Obra", "j1", 9, 9, "", "e@e.com", **kw)[1]


def test_o_caso_pede_ler_como_arquitetura():
    h = _html(parece_arquitetura=True)
    assert "Ler como" in h and "Arquitetura" in h
    assert "parecem de arquitetura" in h
    assert "pranchas de fôrma e armação em um projeto novo" in h


def test_o_caso_nao_fala_de_escala_nem_de_dxf():
    h = _html(parece_arquitetura=True)
    assert "escala" not in h and "DXF 2013" not in h


def test_CONTROLE_sem_o_aviso_o_texto_e_o_de_sempre():
    h = _html()
    assert "Na maioria das vezes é" in h and "DXF 2013" in h
    assert "Ler como" not in h
    assert h == _html(parece_arquitetura=False)


def test_o_diagnostico_segue_no_email():
    h = main._build_sem_medida_email("F", "O", "j1", 9, 9, "<i>diag</i>", "e@e.com",
                                     parece_arquitetura=True)[1]
    assert "<i>diag</i>" in h


def test_a_marca_e_a_do_aviso_do_motor():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        src = f.read().replace("\r\n", "\n")
    assert '"⚠ Este arquivo parece ser de ARQUITETURA, não de estrutura' in src
    assert main._MARCA_PARECE_ARQUITETURA in "⚠ Este arquivo parece ser de ARQUITETURA, não de"


def test_o_process_job_olha_os_avisos_do_projeto():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        src = f.read().replace("\r\n", "\n")
    i = src.index("_subj_pp, _html_pp = _build_sem_medida_email(")
    trecho = src[i:src.index('_log_error("motor:sem-medida-nenhuma"', i)]
    assert "parece_arquitetura=any(_MARCA_PARECE_ARQUITETURA in str(_w)" in trecho
    assert "project_data.warnings" in trecho
