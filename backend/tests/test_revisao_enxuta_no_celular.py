# -*- coding: utf-8 -*-
"""A revisão enxuta no celular não pode tirar ação nem mudar o computador.

31/10/2026: em 375 px a 1ª linha ficava fora da 1ª tela e cada linha ocupava
305 px. No celular, parte das ações foi para o botão "⋯" e as observações para
o toque na descrição. O risco é uma ação sumir de vez ou o recolhimento vazar
para o computador.
"""
import os
import re

import pytest

_RAIZ = os.path.join(os.path.dirname(__file__), "..", "..")


def _src():
    with open(os.path.join(_RAIZ, "revisao.html"), encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def _template_da_linha():
    src = _src()
    i = src.index("function renderItem(it, localIndex)")
    return src[i:src.index("function rvAbreLinha", i)]


def _css_fora_e_dentro_do_celular():
    src = _src()
    i = src.index("@media (max-width:640px) {")
    j = src.index("@media (prefers-reduced-motion", i)
    a = src.rindex("<style>", 0, i)
    return src[a:i], src[i:j]


@pytest.mark.parametrize("acao", [
    "review('${it.id}','approve')", "openEdit('${it.id}')",
    "review('${it.id}','reject')", "markExistente('${it.id}')",
    "openSheet('${it.id}')", "openComment('${it.id}')"])
def test_nenhuma_acao_saiu_da_linha(acao):
    assert acao in _template_da_linha(), "a ação %s sumiu da linha" % acao


@pytest.mark.parametrize("acao", [
    "review('${it.id}','reject')", "markExistente('${it.id}')",
    "openSheet('${it.id}')", "openComment('${it.id}')"])
def test_as_acoes_recolhidas_ficam_dentro_do_mais(acao):
    t = _template_da_linha()
    i, j = t.index('class="rv-extra"'), t.index("</span>\n        </div>\n        </div>")
    assert i < t.index(acao) < j, "%s ficou fora do ⋯" % acao


def test_no_computador_nada_fica_recolhido():
    fora, _ = _css_fora_e_dentro_do_celular()
    assert re.search(r"\.rv-topo, \.rv-extra \{ display:contents; \}", fora)
    assert re.search(r"\.rv-mais, \.rv-so-celular \{ display:none; \}", fora)
    for trava in (".rv-kpis", ".rv-contas", ".rv-meta", ".rv-desc"):
        assert trava not in fora, "%s é recolhido também no computador" % trava


def test_no_celular_as_observacoes_voltam_ao_tocar_na_descricao():
    _, dentro = _css_fora_e_dentro_do_celular()
    assert ".rv-meta { display:none; }" in dentro
    assert ".item-row.aberto .rv-meta { display:block; }" in dentro
    assert "rvAbreLinha(this)" in _template_da_linha()


def test_no_celular_o_mais_abre_as_acoes_e_todo_botao_e_facil_de_tocar():
    _, dentro = _css_fora_e_dentro_do_celular()
    assert ".item-row.mais-aberta .rv-extra { display:flex; }" in dentro
    assert re.search(r"\.rv-acoes > button, \.rv-linha-acoes > button \{ min-height:44px; \}", dentro)
    assert "rvMaisAcoes(this)" in _template_da_linha()


def test_a_linha_em_branco_mostra_a_unidade_no_celular():
    assert 'rv-so-celular text-xs font-semibold text-red-600">${escapeHtml(it.unit)}' in _template_da_linha()
