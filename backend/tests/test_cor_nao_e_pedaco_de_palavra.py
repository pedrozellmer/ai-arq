# -*- coding: utf-8 -*-
"""A COR do caderno de acabamentos não pode ser um pedaço de outra palavra.

🚨 25/08/2026. O extrator de especificação nasceu em 24/08 e a auditoria do dia
seguinte — antes de UMA linha ser gravada — achou dois defeitos meus na mesma
expressão. Ela era `\\bcor\\s*:?\\s*(...)`:

  1) fronteira só ANTES da palavra, nenhuma depois. "cor" casava como PREFIXO:

        "Porta de correr"                        → cor="rer"
        "Massa corrida PVA … Coral Branco"       → cor="rida PVA"
        "Suporte de corrimão"                    → cor="rimão"
        "Rodapé em corte reto"                   → cor="te reto"
        "Massa corrida cor Branco Neve Suvinil"  → cor="rida cor Branco"

     O último é o pior: é o caso que um comentário meu, três linhas acima,
     jurava tratar. A cor real é "Branco Neve" e saía destruída porque o
     "corrida" aparece antes na frase.

  2) sem IGNORECASE. "Cor: Branco Neve" e "COR BRANCA" — a forma mais comum de
     escrever numa prancha — não casavam com nada.

Medido no acervo: **380 dos 679 itens** com cor preenchida eram lixo assim, e
23 deles tinham marca junto — a marca é o que autoriza a gravação, então esses
iriam pro banco, em 8 projetos de 5 clientes.

🪤 Os dois defeitos se protegiam: consertar só a caixa faria "Cortina" virar
cor="tina". Por isso o teste cobre os dois lados na mesma bancada.

🔑 Por que isso é grave e não cosmético: o caderno existe pra o arquiteto MANDAR
PRA ORÇAR. "Coral / cor: rida PVA" chega no fornecedor. Regra dura nº1 na
prática — campo vazio é melhor que campo com cara de especificação e conteúdo
inventado.
"""
import os
import re
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from spec_extract import extrair_spec  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
#  O lixo que saía — cada linha é um caso real do acervo
# ══════════════════════════════════════════════════════════════════════════
LIXO = [
    ("Porta de correr em madeira", "rer"),
    ("Massa corrida PVA sobre paredes internas — preparo para pintura "
     "acrílica Coral Branco Fosco", "rida PVA"),
    ("Suporte de fixação de corrimão para paredes", "rimão"),
    ("Condulete de alumínio fundido tipo LL — completo (corpo + tampa)", "po"),
    ("Rodapé em corte reto 7cm", "te reto"),
    ("Cortina de vidro temperado 10mm", None),
    ("Corte AA da planta baixa", None),
    ("Piso corporativo em manta vinílica", None),
    ("Corrente de aço galvanizado", None),
    ("Perfil corrugado para eletroduto", None),
]


@pytest.mark.parametrize("descricao,lixo_antigo", LIXO)
def test_pedaco_de_palavra_nunca_vira_cor(descricao, lixo_antigo):
    del lixo_antigo
    cor = extrair_spec(descricao)["cor"]
    assert cor is None, (
        "%r virou cor a partir de %r — é pedaço de outra palavra"
        % (cor, descricao[:60]))


# ══════════════════════════════════════════════════════════════════════════
#  E a cor de verdade tem que continuar saindo (senão o conserto é só mudo)
# ══════════════════════════════════════════════════════════════════════════
CERTOS = [
    ("Massa corrida cor Branco Neve Suvinil", "Branco Neve"),
    ("Cor: Branco Neve", "Branco Neve"),
    ("COR BRANCA", "BRANCA"),
    ("Tinta acrílica Cor Palha Suvinil", "Palha"),
    ("cor branca", "branca"),
    ("Revestimento cerâmico cor Cinza Claro Eliane", "Cinza Claro"),
]


@pytest.mark.parametrize("descricao,esperado", CERTOS)
def test_a_cor_escrita_pelo_arquiteto_sai_inteira(descricao, esperado):
    assert extrair_spec(descricao)["cor"] == esperado


@pytest.mark.parametrize("descricao", [
    "cor a definir", "cor conforme projeto", "Cor a definir pelo cliente",
    "cor da legenda", "cor padrão do fabricante",
])
def test_nao_afirmar_cor_quando_o_texto_diz_que_nao_sabe(descricao):
    assert extrair_spec(descricao)["cor"] is None


def test_a_marca_nao_entra_no_nome_da_cor():
    """🪤 "cor Branco Neve Suvinil": o nome da cor acaba onde a MARCA começa."""
    r = extrair_spec("Massa corrida cor Branco Neve Suvinil")
    assert r["cor"] == "Branco Neve"
    assert r["marca"] == "Suvinil"


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO: a bancada tem que REPROVAR a expressão antiga
# ══════════════════════════════════════════════════════════════════════════
_RX_ANTIGA = re.compile(
    r"\bcor\s*:?\s*([A-Za-zÀ-ú][\wÀ-ú]+(?:\s+[A-Za-zÀ-ú]+){0,2})", re.UNICODE)


def test_controle_positivo_a_expressao_antiga_produzia_o_lixo():
    """Sem isto eu não sei se os testes acima medem algo ou se o caso nunca
    aconteceu. Aqui a expressão de ontem roda e o lixo aparece."""
    for descricao, lixo_antigo in LIXO:
        if lixo_antigo is None:
            continue
        m = _RX_ANTIGA.search(descricao)
        assert m, "a expressão antiga nem casava em %r" % descricao[:50]
        # 🪤 O que a expressão captura é ainda MAIOR ("rer em madeira"); quem
        # encurtava pra "rer" era o corte de `_PARA_A_COR` lá na frente. Comparo
        # o começo, que é onde mora o defeito: o pedaço da palavra partida.
        assert m.group(1).startswith(lixo_antigo), (
            "esperava lixo começando em %r, veio %r" % (lixo_antigo, m.group(1)))


def test_controle_positivo_a_expressao_antiga_nao_via_Cor_maiuscula():
    """O segundo defeito: sem IGNORECASE, a forma mais comum não casava."""
    assert not _RX_ANTIGA.search("Cor: Branco Neve")
    assert not _RX_ANTIGA.search("COR BRANCA")


def test_controle_a_expressao_de_hoje_tem_as_DUAS_correcoes():
    """🪤 Consertar só a caixa faz "Cortina" virar cor="tina" — pior que antes.
    As duas correções vivem ou morrem juntas."""
    import spec_extract as sx
    assert sx._RX_COR.flags & re.IGNORECASE, "voltou a perder 'Cor:' maiúsculo"
    assert extrair_spec("Cortina de vidro")["cor"] is None, (
        "com IGNORECASE e sem fronteira, 'Cortina' vira cor")
