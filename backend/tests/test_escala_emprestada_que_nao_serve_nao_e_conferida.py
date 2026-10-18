# -*- coding: utf-8 -*-
"""A escala emprestada de outra prancha, que o próprio desenho desmente, não é "conferida".

🩸 18/10/2026: um projeto com 9 pranchas de estrutura sem unidade e sem cota, e uma
planta de arquitetura em metros com 714 cotas que conferem. O consenso do
projeto emprestou o metro às pranchas de estrutura — e nelas o maior elemento
mediria 5.900 m. O extrator alarmou ("Unidade suspeita … escala pode estar
errada") e rebaixou os selos, mas o resumo da escala testava o consenso ANTES
do alarme: o cliente leu "✅ Escala conferida pelo próprio desenho" nas 9.
📏 90 dias: um projeto (9 pranchas).
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import main  # noqa: E402

_ALARME = "Unidade suspeita: maior elemento mede 5900m (>500m) — escala pode estar errada; tratar quantidades como estimado."


def test_o_caso_emprestada_e_desmentida_vira_alerta():
    r = main._resumo_escala_arquivo("/x/PE-001-R00.dxf", {
        "unidade_por_consenso_projeto": True, "unidade_nome_provada": "metro",
        "alerta_unidade": _ALARME, "unidade_desenho": "Sem unidade"})
    assert r["status"] == "alerta", r
    assert "outra prancha" in r["alerta"] and "5900m" in r["alerta"], r


def test_o_cliente_le_o_alarme_e_nao_o_conferida():
    a = [main._resumo_escala_arquivo("/x/PE-001-R00.dxf", {
        "unidade_por_consenso_projeto": True, "alerta_unidade": _ALARME, "unidade_desenho": "Sem unidade"}),
         main._resumo_escala_arquivo("/x/ARQ.dxf", {"unidade_validada_por_cotas": 714, "unidade_nome_provada": "metros"})]
    linhas = main._linhas_escala_projeto(a, n_medidos=10)
    junto = " ".join(linhas)
    assert "ESCALA SUSPEITA em PE-001-R00" in junto, linhas
    assert "PE-001-R00: usa a escala provada" not in junto, linhas
    assert "ARQ: 714 cotas batem" in junto, linhas        # a que foi conferida continua conferida


def test_CONTROLE_emprestada_sem_alarme_continua_consenso():
    r = main._resumo_escala_arquivo("/x/PE-002.dxf", {
        "unidade_por_consenso_projeto": True, "unidade_nome_provada": "metro"})
    assert r["status"] == "consenso", r


def test_CONTROLE_cota_propria_vence_o_alarme_como_antes():
    r = main._resumo_escala_arquivo("/x/A.dxf", {"unidade_validada_por_cotas": 40, "alerta_unidade": _ALARME})
    assert r["status"] == "cotas", r
