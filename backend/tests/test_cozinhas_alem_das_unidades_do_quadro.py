# -*- coding: utf-8 -*-
"""Cozinhas além das unidades que o quadro de áreas declara: as contagens
de bloco perdem o selo.

🩸 28/09/2026 (job dd52081b, prédio de apartamentos): o quadro do projeto
dizia "NÚMERO TOTAL DE UNIDADES 22"; a planilha saiu com 41 cozinhas, 101
vasos e 160 portas, com selo. A mesma unidade estava desenhada na planta do
pavimento, na tipologia ampliada e em bloco colado. O número fica (repetição
legítima existe); o selo sai e o aviso diz por quê.
"""
import os
import sys
import textwrap

import ezdxf

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
from engine_rules import MARCA_ACIMA_DO_QUADRO, unidades_do_quadro  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402

QUADRO = [("NÚMERO DE UNIDADES", -51.0, 36.1, 0.4), ("TÉRREO", -49.3, 35.3, 0.4),
          ("10", -35.2, 35.4, 0.4), ("1º PAVIMENTO (DUPLEX)", -49.3, 34.6, 0.4),
          ("12", -35.2, 34.7, 0.4), ("NÚMERO TOTAL DE UNIDADES", -49.2, 33.9, 0.4),
          ("22", -35.1, 34.0, 0.4)]


def test_o_total_de_unidades_e_o_da_linha_do_rotulo():
    assert unidades_do_quadro(QUADRO) == 22           # não o 10 nem o 12 de cima


def test_CONTROLE_sem_rotulo_de_total_nao_le():
    assert unidades_do_quadro([t for t in QUADRO if "TOTAL" not in t[0]]) is None


def test_CONTROLE_dois_totais_diferentes_e_ambiguo():
    outro = [("TOTAL DE UNIDADES", 100.0, 50.0, 0.4), ("30", 115.0, 50.1, 0.4)]
    assert unidades_do_quadro(QUADRO + outro) is None


def test_o_extrator_le_o_quadro(tmp_path, monkeypatch):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    for txt, x, y, h in QUADRO:
        msp.add_text(txt, dxfattribs={"height": h, "insert": (x, y)})
    msp.add_line((0, 0), (10, 0))
    p = str(tmp_path / "quadro.dxf")
    doc.saveas(p)
    assert dx.extract_dxf(p).metadata.get("unidades_do_quadro") == 22


def _fatia():
    src = open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8").read()
    a = src.index("# 🩸 COZINHAS ALÉM DAS UNIDADES DO QUADRO")
    ini = src.index("        try:\n", a)
    fim = src.index("        # 🚨 AQUI é o fim da fila de quem rebaixa selo", a)
    return textwrap.dedent(src[ini:fim])


def _item(desc, qtd, obs, conf="confirmado", prancha="Prefeitura - R16.dxf", unit="un"):
    return BudgetItem(item_num="1", description=desc, unit=unit, quantity=qtd, observations=obs,
                      ref_sheet=prancha, confidence=Confidence(conf), origem="dxf_geom")


def _roda(itens, unidades):
    ns = {"all_items": itens, "job_id": "t", "os": os, "_log_error": lambda *a, **k: None,
          "_unidades_do_quadro": unidades}
    exec(compile(_fatia(), "cozinhas", "exec"), ns)
    return itens


def _caso():
    return [
        _item("Cuba de aço inox para cozinha", 41, "Fonte: 41 INSERTs do bloco 'CUBA-COZ' (CONTAGEM DE BLOCOS)."),
        _item("Fogão 4 bocas de embutir", 41, "Fonte: 41 INSERTs do bloco 'FOGAO-4B' (CONTAGEM DE BLOCOS)."),
        _item("Vaso sanitário — louça branca", 101, "Fonte: 101 INSERTs do bloco 'VASO' (CONTAGEM DE BLOCOS)."),
        _item("Porta de madeira 0,60 × 2,10", 76, "Fonte: 76 INSERTs do bloco 'P-60X210' (CONTAGEM DE BLOCOS)."),
        _item("Placa de obra", 1, "Exigência municipal.", conf="estimado"),
        _item("Piso permeável", 493.61, "✓ MEDIDO — área do layer 'AR-PISOS'.", unit="m²"),
    ]


def test_o_caso_as_contagens_perdem_o_selo_e_o_numero_fica():
    itens = _roda(_caso(), {"Prefeitura - R16.dxf": 22})
    coz, fogao, vaso, porta, placa, piso = itens
    for it, qtd in ((coz, 41), (fogao, 41), (vaso, 101), (porta, 76)):
        assert it.confidence == Confidence("estimado") and it.quantity == qtd, it
        assert it.observations.startswith(MARCA_ACIMA_DO_QUADRO) and "22 unidades" in it.observations
    assert placa.observations == "Exigência municipal.", "não é contagem de bloco"
    assert piso.confidence == Confidence("confirmado"), "área medida não é contagem"


def test_CONTROLE_cozinhas_dentro_das_unidades_ficam():
    itens = _roda(_caso(), {"Prefeitura - R16.dxf": 40})
    assert all(MARCA_ACIMA_DO_QUADRO not in (it.observations or "") for it in itens)
    assert itens[2].confidence == Confidence("confirmado")


def test_CONTROLE_sem_quadro_nada_muda():
    itens = _roda(_caso(), {})
    assert itens[0].confidence == Confidence("confirmado")


def test_CONTROLE_outra_prancha_nao_e_tocada():
    itens = _caso()
    itens.append(_item("Vaso sanitário", 8, "Fonte: 8 INSERTs do bloco 'VASO'.", prancha="outra.dxf"))
    _roda(itens, {"Prefeitura - R16.dxf": 22})
    assert itens[-1].confidence == Confidence("confirmado")
