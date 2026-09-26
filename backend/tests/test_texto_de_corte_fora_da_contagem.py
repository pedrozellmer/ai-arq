# -*- coding: utf-8 -*-
"""Etiqueta de corte/detalhe que repete a planta não entra no ×N.

🩸 25/09/2026 — releitura do job `53f0483f`: a etiqueta de cada acessório de
leito ("TH-90°") aparece na planta e de novo nos cortes, e a IA somou as
pranchas. O comprimento e o bloco da vista já saíam; o texto não.
🪤 Medido no acervo: nos cortes de interiores "nicho ×29", "prateleira ×5" e a
"papeleira ×2" da elevação só existem ali. Por isso, como o bloco:
- DETALHE: o texto sai do ×N sempre (recorte típico redesenhado);
- CORTE/ELEVAÇÃO: sai só se o mesmo texto é contado fora da vista no arquivo;
- continua listado (é especificação), à parte e sem ×N;
- prancha só de corte avisa que a planta está em OUTRA prancha.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import dwg_extractor as dx  # noqa: E402
import test_desenho_no_modelo as tdm  # noqa: E402


def _t(msp, texto, x, y):
    msp.add_text(texto, dxfattribs={"height": 0.1, "insert": (x, y), "layer": "ETIQUETA"})


def _prompt(tmp_path, monkeypatch, titulo_detalhe, titulo_planta="PORÃO DE CABOS - PLANTA"):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    p = tdm._folha(tmp_path, titulo_detalhe=titulo_detalhe, titulo_planta=titulo_planta)
    doc = ezdxf.readfile(p)
    msp = doc.modelspace()
    for x in (6, 7):                       # na planta
        _t(msp, "TH-90", x, 25)
        _t(msp, "SUPORTE", x, 24)
    for x in (5, 6, 7):                    # no desenho de baixo (corte ou detalhe)
        _t(msp, "TH-90", x, 11)
        _t(msp, "NICHO", x, 9)
    doc.saveas(p)
    return dx.extract_dxf(p).to_structured_prompt()


def _linha(txt, comeco):
    return next((l.strip() for l in txt.splitlines() if l.strip().startswith(comeco)), "")


def test_etiqueta_do_corte_que_repete_a_planta_nao_soma(tmp_path, monkeypatch):
    txt = _prompt(tmp_path, monkeypatch, '%%UCORTE "A-A"')
    assert _linha(txt, "TH-90").endswith("×2"), _linha(txt, "TH-90")
    assert "SÓ EM CORTE/ELEVAÇÃO/DETALHE" in txt


def test_o_que_so_o_corte_mostra_continua_contado(tmp_path, monkeypatch):
    """O nicho do corte de interiores: único registro — fica com ×N."""
    txt = _prompt(tmp_path, monkeypatch, '%%UCORTE "A-A"')
    assert _linha(txt, "NICHO").endswith("×3"), _linha(txt, "NICHO")


def test_no_detalhe_sai_sempre(tmp_path, monkeypatch):
    txt = _prompt(tmp_path, monkeypatch, '%%UDETALHE "D"')
    assert _linha(txt, "TH-90").endswith("×2"), _linha(txt, "TH-90")
    assert "×3" not in _linha(txt, "NICHO"), "o detalhe é recorte típico: não conta"


def test_CONTROLE_sem_leitura_por_folha_conta_tudo(tmp_path, monkeypatch):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    p = tdm._folha(tmp_path, titulo_detalhe='%%UCORTE "A-A"')
    doc = ezdxf.readfile(p)
    msp = doc.modelspace()
    for x in (6, 7):
        _t(msp, "TH-90", x, 25)
    for x in (5, 6, 7):
        _t(msp, "TH-90", x, 11)
    doc.saveas(p)
    txt = dx.extract_dxf(p).to_structured_prompt()
    assert _linha(txt, "TH-90").endswith("×5")


def test_prancha_so_de_corte_avisa_que_a_planta_e_outra(tmp_path, monkeypatch):
    txt = _prompt(tmp_path, monkeypatch, '%%UCORTE "A-A"', titulo_planta=None)
    assert "NENHUMA planta" in txt


def test_CONTROLE_com_planta_nao_avisa(tmp_path, monkeypatch):
    txt = _prompt(tmp_path, monkeypatch, '%%UCORTE "A-A"')
    assert "NENHUMA planta" not in txt
