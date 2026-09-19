# -*- coding: utf-8 -*-
"""A régua de cobrança separa "com CAD" de "só-PDF" — mudança de mistura não é queda.

🩸 18/09/2026 — item 11 da fila. Medido na base da própria RPC:

    mês   com CAD: entregas / cobráveis / R$ por dia     só-PDF: entregas / cobráveis
    jul   21 / 15 / 46,94                                16 / 0
    ago   38 / 26 / 81,35                                 9 / 0
    set   32 / 23 / 123,94 (18 dias)                     21 / 0 (regra)

Só-PDF é 0% cobrável POR REGRA (70f98a2). Quando ele cresce (9 → 21 entregas),
a régua misturada "cai" sem o motor ter piorado — e dentro do CAD a receita
por dia subiu 52%. É a mesma armadilha do post de hoje de manhã (composição da
amostra lida como regressão).

A RPC `admin_regua_cobranca` ganhou `dias`, `receita_por_dia`, `com_cad` e
`so_pdf` em cada mês (aplicada; cópia comentada em `migrations_pendentes/`).
Aqui se cobra a TELA, rodando o JavaScript real no dukpy: a sub-linha diz as
duas populações e o R$/dia; com a RPC velha (sem os campos) devolve vazio e a
tabela continua de pé — nunca inventa.

🚫 Não cobre a SQL (a bancada não roda SQL).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _jsbancada import funcao_js, motor  # noqa: E402

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ADMIN = os.path.join(_RAIZ, "admin.html")


def _js():
    # costFmt é global do admin.html; aqui um dublê que devolve "R$ x,xx"
    js = motor("function costFmt(v){ return 'R$ ' + Number(v||0).toFixed(2).replace('.', ','); } true;")
    js.evaljs(funcao_js("subLinhaPopulacoes", _ADMIN))
    return js


_SET = {"mes": "2026-09", "entregas": 53, "cobraveis": 23, "nao_avaliadas": 0,
        "receita_a_97": 2231, "dias": 18, "receita_por_dia": 123.94,
        "com_cad": {"entregas": 32, "cobraveis": 23, "receita_a_97": 2231, "receita_por_dia": 123.94},
        "so_pdf": {"entregas": 21, "cobraveis": 0}}


def test_a_sub_linha_diz_as_duas_populacoes_e_o_por_dia():
    out = _js().evaljs("subLinhaPopulacoes(%s)" % json.dumps(_SET))
    assert "com CAD" in out and "<b>32</b>" in out and "<b>23</b>" in out and "72%" in out, out
    assert "R$ 123,94" in out and "/dia" in out, out
    assert "só-PDF: 21 entregas, 0 cobráveis" in out and "PDF não mede" in out, out


def test_so_PDF_cobravel_de_antes_da_regra_e_DITO_e_nao_somado_calado():
    """🩸 11 projetos só-PDF entraram na lista de cobráveis antes de 15/09."""
    m = dict(_SET, so_pdf={"entregas": 9, "cobraveis": 2})
    out = _js().evaljs("subLinhaPopulacoes(%s)" % json.dumps(m))
    assert "2 cobráveis de antes da regra de 15/09" in out, out
    assert "text-amber-700" in out, "o resquício não está destacado"


def test_CONTROLE_sem_os_campos_da_RPC_nova_a_sub_linha_e_VAZIA():
    """RPC velha → nada de inventar populações; a linha do mês continua."""
    js = _js()
    for velho in (json.dumps({"mes": "2026-08", "entregas": 47, "cobraveis": 26}), "null", "{}"):
        assert js.evaljs("subLinhaPopulacoes(%s)" % velho) == "", velho


def test_sem_dias_a_sub_linha_nao_mostra_por_dia():
    m = dict(_SET); m.pop("dias"); m["com_cad"] = dict(_SET["com_cad"], receita_por_dia=None)
    out = _js().evaljs("subLinhaPopulacoes(%s)" % json.dumps(m))
    assert "/dia" not in out, out
    assert "com CAD" in out


def test_CONTROLE_o_bloco_da_regua_continua_lendo_as_nao_avaliadas():
    """O guarda antigo (test_regua_de_cobranca) exige isto dentro de _blocoRegua;
    a sub-linha nova não pode ter levado o texto embora."""
    import io
    src = io.open(_ADMIN, encoding="utf-8").read()
    i = src.index("function _blocoRegua(")
    bloco = src[i:src.index("\nfunction ", i + 10)]
    assert "nao_avaliadas" in bloco and "não avaliada" in bloco
    assert "subLinhaPopulacoes(m)" in bloco, "a tabela parou de chamar a sub-linha"
    assert "R$/dia" in bloco, "a coluna R$/dia sumiu do cabeçalho"
