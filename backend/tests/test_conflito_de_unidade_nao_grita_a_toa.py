# -*- coding: utf-8 -*-
"""A gente dizia "uma das duas está errada" quando nenhuma estava — 56% do tempo.

🩸 04/09/2026, do PRIMEIRO projeto da cliente-22 (Bolognesi). Ela apagou, três
minutos depois de receber a planilha, uma linha que trazia a NOSSA observação:

    "⚠ CONFERIR A UNIDADE: o serviço SINAPI 103689 é medido em M2, e esta
     linha saiu em un. Uma das duas está errada."

Ela agiu certo: a gente entregou a linha admitindo que ela provavelmente está
errada, e deixou o trabalho de descobrir qual para ela.

🔑 MEDIDO na base antes de mexer: **160 itens, 39 projetos, 29 clientes** com
esse aviso — e **89 (56%) são FALSO ALARME**:

    "Janela maxim-ar, 46 un"          contra SINAPI M2
    "Bloco cerâmico 19×39, un"        contra SINAPI M2
    "Estaca _EST60, 187 un"           contra SINAPI M

Contar janela em `un` está CERTO. A SINAPI é que precifica por m². Nenhuma das
duas está errada. Alarme que grita 56% à toa ensina o cliente a ignorar alarme
— e dilui os **27 casos reais** (11 clientes), que são justamente os
"Ripas de madeira 1,18 ml" contra um serviço medido em M2.

🪤 A assimetria NÃO é "contagem nunca conflita" — testei essa hipótese contra a
matriz inteira do banco e ela cai: "Ar-condicionado cassete" saiu em **m²**
contra SINAPI UN, e aí o errado somos nós. O que separa é QUEM mediu: se NÓS
dissemos comprimento/área/volume e o serviço é de outra grandeza, o número é de
outra coisa. Se nós CONTAMOS, contar é base legítima pra qualquer item físico.

🪤 E o selo: a doutrina antiga ("só avisa, nunca rebaixa") continua valendo pro
conflito de BASE — contar janela é medição boa e o match SINAPI é o lado fraco.
Ela NÃO vale quando a grandeza suspeita é a nossa.
"""
import io
import os

import pytest

from engine_rules import (tipo_de_conflito_de_unidade as _tipo,
                          unidade_conflita_com_sinapi as _conflita)

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()

# ── A MATRIZ REAL do banco em 04/09/2026: (nossa, sinapi, n, tipo) ─────────
_MATRIZ = [
    ("un", "M2", 68, "base"),        # janela/bloco contados × preço por m²
    ("ml", "M2", 24, "grandeza"),    # "Alvenaria de fachada 171,36 ml"
    ("un", "M", 20, "base"),         # cabo/estaca contados × preço por metro
    ("m²", "M", 18, "grandeza"),     # "Calha metálica (área projetada)"
    ("m²", "M3", 8, "grandeza"),     # "Demolição de alvenaria"
    ("m²", "UN", 7, "grandeza"),     # "Ar-condicionado cassete" em m² — nosso erro
    ("ml", "UN", 4, "grandeza"),
    ("ml", "M3", 2, "grandeza"),     # "Escada em concreto armado"
    ("un", "M3", 1, "base"),         # "Caçamba para entulho"
    ("m²", "KG", 1, "grandeza"),
    ("m", "M2", 1, "grandeza"),
]


@pytest.mark.parametrize("nossa,sinapi,n,esperado", _MATRIZ)
def test_a_matriz_REAL_e_classificada_certo(nossa, sinapi, n, esperado):
    assert _tipo(nossa, sinapi) == esperado, (
        "%d item(ns) reais em %s contra SINAPI %s deveriam ser %r"
        % (n, nossa, sinapi, esperado))


def test_a_maioria_do_alarme_era_FALSO():
    """🔑 O número que motivou o conserto: 56% do que a gente gritava."""
    base = sum(n for _a, _b, n, t in _MATRIZ if t == "base")
    grand = sum(n for _a, _b, n, t in _MATRIZ if t == "grandeza")
    assert base > grand, (
        "a classificação inverteu: %d de base contra %d de grandeza" % (base, grand))
    assert base / float(base + grand) > 0.5, (
        "menos da metade virou 'base' — a regra deixou de reconhecer o falso "
        "alarme que atingiu 23 clientes")


def test_mesma_grandeza_e_incomparavel_continuam_calados():
    for nossa, sinapi in (("m²", "M2"), ("m", "M"), ("und", "UN"), ("t", "KG"),
                          ("vb", "M2"), ("cj", "M2"), ("m²", "H"), ("m²", "MES"),
                          ("", "M2"), (None, None)):
        assert _tipo(nossa, sinapi) is None, (
            "%r × %r virou conflito — na dúvida a regra cala a boca"
            % (nossa, sinapi))


def test_o_booleano_ANTIGO_nao_mudou_de_comportamento():
    """🪤 `unidade_conflita_com_sinapi` é usado em outro lugar e tem 283 checks
    no `test_engine_rules`. Dividir em tipos não pode mudar o que ele responde."""
    for nossa, sinapi, _n, _t in _MATRIZ:
        assert _conflita(nossa, sinapi) is True
    for nossa, sinapi in (("m²", "M2"), ("m", "M"), ("vb", "M2")):
        assert _conflita(nossa, sinapi) is False


# ══════════════════════════════════════════════════════════════════════════
#  O que o CLIENTE lê
# ══════════════════════════════════════════════════════════════════════════
def _bloco():
    """Do começo da classificação até o log — âncora nos dois extremos, não
    numa janela de N caracteres, que envelhece a cada linha acrescentada."""
    i = _FONTE.index("_tipo_cu = _tipo_conflito_unidade(")
    j = _FONTE.index("[sinapi-unidade] job=", i)
    return _FONTE[i:j + 600]


def test_o_falso_alarme_parou_de_dizer_que_alguem_errou():
    b = _bloco()
    i_base = b.index('if _tipo_cu == "base":')
    i_else = b.index("else:", i_base)
    ramo_base = b[i_base:i_else]
    assert "Uma das duas está errada" not in ramo_base, (
        "o conflito de BASE voltou a afirmar que alguém errou — em 89 casos "
        "reais ninguém errou")
    assert "base de preço" in ramo_base or "BASE DE MEDIÇÃO" in ramo_base, (
        "sumiu a explicação de que é só base diferente")


def test_o_sinal_real_diz_que_o_suspeito_e_NOSSO():
    b = _bloco()
    i_else = b.index("else:", b.index('if _tipo_cu == "base":'))
    ramo = b[i_else:b.index("_obs_u =", i_else)]
    assert "o lado suspeito" in ramo and "NOSSO" in ramo, (
        "o aviso do sinal real voltou a empurrar a dúvida pro cliente em vez "
        "de dizer de quem é a suspeita")
    assert "comprimento de um layer" in ramo, (
        "sumiu a causa concreta — sem ela o cliente não sabe o que conferir")


def test_so_a_classe_GRANDEZA_rebaixa_o_selo():
    b = _bloco()
    assert 'if _tipo_cu == "grandeza":' in b, (
        "o rebaixamento deixou de ser condicionado ao tipo — ou some, ou passa "
        "a punir medição boa por causa de match ruim do SINAPI")
    i_reb = b.index('if _tipo_cu == "grandeza":')
    assert "_CfU.ESTIMADO" in b[i_reb:i_reb + 700]
    assert "_CfU.CONFIRMADO" not in b, "este bloco só pode REBAIXAR"


def test_o_log_conta_os_dois_tipos():
    """Sem isso a gente não consegue medir se o falso alarme sumiu mesmo."""
    b = _bloco()
    assert "base=%d grandeza=%d" in b, (
        "o log voltou a dar só o total — não dá pra saber se o conserto pegou")


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — a regra de ANTES, na MESMA matriz
# ══════════════════════════════════════════════════════════════════════════
def _tipo_ANTIGO(nossa, sinapi):
    """Como era: qualquer grandeza diferente virava "uma das duas está errada"."""
    from engine_rules import grandeza_da_unidade as g
    a, b = g(nossa), g(sinapi)
    if not a or not b or a == b:
        return None
    return "grandeza"        # tudo era tratado como erro de alguém


def test_CONTROLE_a_regra_ANTIGA_chamava_tudo_de_erro():
    antigos = [_tipo_ANTIGO(n, s) for n, s, _q, _t in _MATRIZ]
    atuais = [_tipo(n, s) for n, s, _q, _t in _MATRIZ]
    assert all(a == "grandeza" for a in antigos), "controle mal montado"
    assert atuais != antigos, (
        "a regra de hoje classifica igual à antiga — o conserto não fez nada")
    mudaram = sum(1 for a, b in zip(antigos, atuais) if a != b)
    assert mudaram == 3, (
        "esperava 3 combinações reclassificadas como 'base' (un×M2, un×M, "
        "un×M3) e vieram %d" % mudaram)
