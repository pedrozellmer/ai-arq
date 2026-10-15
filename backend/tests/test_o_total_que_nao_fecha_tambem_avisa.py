# -*- coding: utf-8 -*-
"""A linha de TOTAL ao lado das partes é marcada mesmo quando os números não fecham.

🩸 15/10/2026 (3cc04055): "Armadura CA-50 — Total geral" 379 kg ao lado de
"— Ø 8,0 mm" 316 e "— Ø 10,0 mm" 271. A soma (587) passou 35 % do total e a
regra dos 100 % ficou quieta: somar a coluna contava o aço duas vezes, sem aviso.
Quando não fecha, vale o total com o MESMO nome das partes, na MESMA prancha, e
maior que cada uma delas. 📏 90 dias de cliente: 15 linhas em 12 projetos.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

from engine_rules import linhas_pai_e_filho  # noqa: E402

_PR = "prancha-01.pdf (p2 · Estrutura)"


def _i(d, u, q, disc="Estrutura", ref=_PR):
    return {"description": d, "unit": u, "quantity": q, "discipline": disc, "ref_sheet": ref}


def test_o_caso_o_total_de_aco_que_nao_fecha_e_marcado():
    a = linhas_pai_e_filho([
        _i("Concreto fck=20MPa — Sapatas", "m³", 0),
        _i("Armadura CA-50 — Ø 8,0 mm (cintas/estribos e barras longitudinais)", "kg", 316),
        _i("Armadura CA-50 — Ø 10,0 mm (barras longitudinais)", "kg", 271),
        _i("Armadura CA-50 — Total geral (conforme resumo de aço da prancha)", "kg", 379),
    ])
    assert len(a) == 1 and a[0]["indice"] == 3, a
    assert a[0]["fecha"] is False and a[0]["n_partes"] == 2 and a[0]["soma_partes"] == 587, a


@pytest.mark.parametrize("itens,n_partes", [
    # 📏 do banco: o total do quadro ao lado de UMA bitola
    ([_i("Aço CA-50 — TOTAL GERAL de armação de pilares, conforme quadro", "kg", 14803),
      _i("Aço CA-50 — Ø 10,0 mm — pilares", "kg", 1025)], 1),
    # 📏 do banco: forro "área total geral" ao lado dos forros por tipo
    ([_i("Forro de interiores — área total geral (todos os tipos)", "m²", 6643.69, "Forros"),
      _i("Forro de interiores — gesso liso — sala", "m²", 143.4, "Forros"),
      _i("Forro de interiores — mineral — escritório", "m²", 120.0, "Forros")], 2),
])
def test_o_total_com_o_mesmo_nome_e_maior_que_as_partes(itens, n_partes):
    a = linhas_pai_e_filho(itens)
    assert len(a) == 1 and a[0]["indice"] == 0 and a[0]["n_partes"] == n_partes, a
    assert a[0]["fecha"] is False


def test_CONTROLE_o_total_que_fecha_continua_como_era():
    a = linhas_pai_e_filho([
        _i("SUBTOTAL — Concreto C25/30 — Todas as sapatas", "m³", 12.4),
        _i("Concreto C25/30 — Sapata S1", "m³", 7.1),
        _i("Concreto C25/30 — Sapata S2", "m³", 7.2),
    ])
    assert len(a) == 1 and a[0]["fecha"] is True and a[0]["n_partes"] == 2, a


def test_CONTROLE_a_area_do_proprio_item_nao_e_total_das_vizinhas():
    # 📏 do banco: cada quadra tem a sua "área total"; outro piso é maior que ela
    assert linhas_pai_e_filho([
        _i("Revestimento de piso — Quadra (10,94×20m) — área total da quadra", "m²", 218.8, "Pisos"),
        _i("Revestimento de piso — Beach Tennis (11×20m) — área total da quadra", "m²", 220, "Pisos"),
        _i("Revestimento de piso — Estacionamento — piso intertravado", "m²", 380, "Pisos"),
        _i("Revestimento de piso — Calçada — concreto", "m²", 90, "Pisos"),
    ]) == []


def test_CONTROLE_a_altura_total_da_peca_nao_e_total():
    # 📏 do banco: "altura total" da janela; as outras janelas têm 1 un cada
    assert linhas_pai_e_filho([
        _i("Janela em alumínio — J01, 100×60/210 cm (largura × peitoril/altura total)", "un", 1, "Esquadrias"),
        _i("Janela em alumínio — J02, 120×100", "un", 1, "Esquadrias"),
        _i("Janela em alumínio — J03, 150×100", "un", 1, "Esquadrias"),
    ]) == []


def test_CONTROLE_nome_diferente_nao_e_parte():
    # a regra antiga já dizia: "Área total dos quartos" × "Quarto 1" fica quieta
    assert linhas_pai_e_filho([_i("Área total dos quartos", "m²", 124.4, "Pisos"),
                               _i("Quarto 1", "m²", 12.0, "Pisos")]) == []


def test_CONTROLE_outra_prancha_nao_e_parte():
    assert linhas_pai_e_filho([
        _i("Armadura CA-50 — Total geral", "kg", 379, ref="prancha-01.pdf (p2 · Estrutura)"),
        _i("Armadura CA-50 — Ø 8,0 mm", "kg", 316, ref="prancha-02.pdf (p1 · Estrutura)"),
        _i("Armadura CA-50 — Ø 10,0 mm", "kg", 271, ref="prancha-02.pdf (p1 · Estrutura)"),
    ]) == []


def test_CONTROLE_a_regra_nao_mexe_nos_itens():
    itens = [_i("Armadura CA-50 — Total geral", "kg", 379), _i("Armadura CA-50 — Ø 8,0 mm", "kg", 316)]
    antes = [dict(x) for x in itens]
    linhas_pai_e_filho(itens)
    assert itens == antes


def test_o_aviso_diz_que_nao_fecha():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        src = f.read()
    i = src.index('_a.get("fecha") is False')
    assert "os números não fecham" in src[i:i + 900] and "confira qual está certa" in src[i:i + 900]
