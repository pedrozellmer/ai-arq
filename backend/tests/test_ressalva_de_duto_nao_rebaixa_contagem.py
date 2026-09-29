# -*- coding: utf-8 -*-
"""A ressalva do DUTO rebaixa comprimento e área — não a contagem de bloco.

🩸 29/09/2026 (job 6437838e, projeto elétrico de uma loja): a eletrocalha
desenhada pelas duas faces, com 66% dos segmentos abaixo de 0,25 m, ligou
`duto_medicao_suspeita` — e ela rebaixava o DESENHO INTEIRO. "14 INSERTs do
bloco 'tomada força alta'", "2 INSERTs do bloco 'SPLIT 60.000'", os 3 tipos de
carregador veicular: 50 contagens de bloco saíram "extração com ressalva —
quantidade não confirmada", e o projeto terminou com 0 linha medida de 311.
Em 60 dias, 116 linhas de contagem em 9 projetos levaram essa marca.
🔑 A exceção de 17/08 já dizia: 32 janelas são 32 INSERTs contados, meça-se
em milímetro ou em milha. A do duto é a mesma natureza — fala do comprimento
de um layer, não de quantos blocos o desenho tem.
🪤 Estéril e xref continuam atingindo tudo: aí a contagem é que pode estar
incompleta.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import engine_rules as er  # noqa: E402

DUTO = {"duto_medicao_suspeita": "ELETROCALHA: 66% dos segmentos < 0,25 m (hachura) "
                                 "— comprimento NÃO confiável"}


@pytest.mark.parametrize("u", ["un", "pç", "cj", "kg", "vb", "mês"])
def test_o_caso_a_contagem_nao_leva_a_ressalva_do_duto(u):
    assert er.caveat_atinge_unidade(DUTO, u) is False, u


@pytest.mark.parametrize("u", ["m", "ml", "m²", "m2", "m³"])
def test_comprimento_e_area_continuam_rebaixados(u):
    assert er.caveat_atinge_unidade(DUTO, u) is True, u


def test_o_desenho_continua_com_ressalva_pra_quem_olha_o_todo():
    """A promoção cruzada e o registro olham `extraction_has_quality_caveat`:
    a ressalva existe — só não fala de contagem."""
    assert er.extraction_has_quality_caveat(DUTO) is True


@pytest.mark.parametrize("outra", [{"extracao_esteril": True},
                                   {"xref_nao_resolvido": "ARQ-BASE"}])
def test_CONTROLE_esteril_e_xref_continuam_atingindo_a_contagem(outra):
    assert er.caveat_atinge_unidade(outra, "un") is True
    assert er.caveat_atinge_unidade(dict(DUTO, **outra), "un") is True


def test_CONTROLE_duto_junto_com_escala_segue_dimensional():
    md = dict(DUTO, unidade_suspeita="fator corrigido por plausibilidade")
    assert er.caveat_atinge_unidade(md, "un") is False
    assert er.caveat_atinge_unidade(md, "m") is True


def test_CONTROLE_sem_ressalva_nada_e_atingido():
    assert er.caveat_atinge_unidade({}, "m") is False
    assert er.caveat_atinge_unidade({"duto_linha_dupla": "eixo"}, "m") is False
