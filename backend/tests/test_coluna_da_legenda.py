# -*- coding: utf-8 -*-
"""A COLUNA de símbolos da legenda: o vizinho de coluna também é amostra.

🩸 29/09/2026 (caso 18c57c3c, elétrico): 'SP' ao lado de "SENSOR DE PRESENÇA",
'SI' de "SIRENE", 'CÂMERAS 360°' de "CÂMERA DOME", 'LUM SOM' sem rótulo — o
rótulo não repete o nome e a regra (p) não os pegava; o sensor e a emergência
("ILE") das legendas de tomadas também escaparam (rótulo 14 cm fora da coluna).
A planilha saiu com câmera, luminária com som, 2 sensores e 2 emergências que
só existem na legenda.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402


def _linha(nome, y, rotulo=None, x=0.0, h=0.1, xr=0.40, meia=0.1):
    ins = (nome, (x - meia, y - meia, x + meia, y + meia), (x, y))
    tx = [(rotulo, xr, y - h / 2, h)] if rotulo else []
    return ins, tx


def _montar(linhas):
    ins, tx = [], []
    for li in linhas:
        a, b = _linha(*li[:3], **(li[3] if len(li) > 3 else {}))
        ins.append(a)
        tx += b
    return ins, tx


_SEGURANCA = [
    ("CAMERA CFTV", 0.00, "CÂMERA"),
    ("teclado", -0.45, "TECLADO"),
    ("MÓDULO GPRS", -0.90, "MODULO GPRS"),
    ("CENTRAL DE ALARME", -1.35, "CENTRAL DE ALARME"),
    ("SP", -1.80, "SENSOR DE PRESENÇA"),
    ("SI", -2.25, "SIRENE"),
    ("CÂMERAS 360°", -2.70, "CÂMERA DOME"),
    ("LUM SOM", -3.15, None),
]


def test_o_caso_os_quatro_da_coluna_de_seguranca():
    ins, tx = _montar(_SEGURANCA)
    # as mesmas peças na PLANTA, longe da legenda
    ins += [("SP", (49.9, 49.9, 50.1, 50.1), (50.0, 50.0)),
            ("CÂMERAS 360°", (-0.1, -20.1, 0.1, -19.9), (0.0, -20.0))]
    out = dx.amostras_de_legenda(ins, tx)
    assert out.get("SP") == [(0.0, -1.80)], out
    assert out.get("SI") == [(0.0, -2.25)], out
    assert out.get("CÂMERAS 360°") == [(0.0, -2.70)], out
    assert out.get("LUM SOM") == [(0.0, -3.15)], out
    assert out.get("CAMERA CFTV") == [(0.0, 0.0)], out


def test_rotulo_desalinhado_na_legenda_de_tomadas():
    """O rótulo do sensor começa 14 cm à direita dos outros (h=0,2): a coluna
    de rótulos (c) não o reconhece; a coluna de SÍMBOLOS pega."""
    g = dict(h=0.2, meia=0.1)
    ins, tx = _montar([
        ("TOM. ALTA", 0.0, "TOM. ALTA", g),
        ("TOM. FORRO", -0.5, "TOM. FORRO", g),
        ("TOM. PISO", -1.0, "TOM. PISO", g),
        ("PONTO DE FORÇA", -1.5, "PONTO DE FORÇA.", g),
        ("SENSOR DE PRESENÇA", -2.0, "SENSOR DE PRESENÇA TETO", dict(g, xr=0.54)),
        ("ILUM. EMERGENCIA", -2.6, "ILE", dict(g, xr=0.62)),
    ])
    out = dx.amostras_de_legenda(ins, tx)
    assert out.get("SENSOR DE PRESENÇA") == [(0.0, -2.0)], out
    assert out.get("ILUM. EMERGENCIA") == [(0.0, -2.6)], out


def test_copia_da_legenda_com_os_simbolos_empurrados():
    """2ª cópia da legenda de tomadas: os símbolos não estão no mesmo x
    (-0,04 a +0,10) e a emergência foi empurrada +0,16 — mas o desenho dela
    ainda cai na faixa da coluna."""
    g = dict(h=0.2, meia=0.1)
    ins, tx = _montar([
        ("TOM. ALTA", 0.0, "TOM. ALTA", dict(g, x=0.04)),
        ("TOM. FORRO", -0.5, "TOM. FORRO", dict(g, x=0.04)),
        ("TOM. MOBILIÁRIO", -1.0, "TOM. MOBILIÁRIO", dict(g, x=0.14)),
        ("PONTO DE FORÇA", -1.5, "PONTO DE FORÇA.", g),
        ("ILUM. EMERGENCIA", -2.1, "ILE", dict(g, x=0.20, xr=0.62)),
    ])
    out = dx.amostras_de_legenda(ins, tx)
    assert out.get("ILUM. EMERGENCIA") == [(0.20, -2.1)], out


def test_CONTROLE_sem_a_coluna_o_rotulo_que_nao_repete_o_nome_escapa(monkeypatch):
    """A chave desliga (d) — e prova que o caso depende dela."""
    monkeypatch.setenv("LEGENDA_POR_COLUNA", "0")
    ins, tx = _montar(_SEGURANCA)
    out = dx.amostras_de_legenda(ins, tx)
    assert "SP" not in out and "SI" not in out and "LUM SOM" not in out, out
    assert out.get("CENTRAL DE ALARME") == [(0.0, -1.35)], out


def test_CONTROLE_duas_provas_nao_fazem_coluna():
    ins, tx = _montar([
        ("CAMERA CFTV", 0.00, "CÂMERA"),
        ("teclado", -0.45, "TECLADO"),
        ("SP", -0.90, "SENSOR DE PRESENÇA"),
    ])
    # os rótulos precisam de coluna (c): dois textos soltos acima, sem bloco
    tx += [("OBS 1", 0.40, 0.40, 0.1), ("OBS 2", 0.40, 0.85, 0.1)]
    out = dx.amostras_de_legenda(ins, tx)
    assert "CAMERA CFTV" in out and "teclado" in out, out
    assert "SP" not in out, out


def test_CONTROLE_fora_do_passo_ou_do_x_nao_entra():
    ins, tx = _montar(_SEGURANCA[:4])
    ins += [
        ("SP", (-0.1, -3.1, 0.1, -2.9), (0.0, -3.0)),        # 1,65 abaixo: > 1,5 passo
        ("SI", (0.9, -1.9, 1.1, -1.7), (1.0, -1.8)),          # outro x
        ("QUADRO GERAL", (-3.0, -2.0, 3.0, -1.6), (0.0, -1.8)),  # largo demais (> 12h)
    ]
    out = dx.amostras_de_legenda(ins, tx)
    assert "SP" not in out and "SI" not in out and "QUADRO GERAL" not in out, out
