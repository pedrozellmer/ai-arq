# -*- coding: utf-8 -*-
"""Área informada pelo cliente tinha teto, não tinha plausibilidade.

🩸 03/09/2026, FÁBIO SHIRAISHI (job `3eb748e3`). Ele digitou **880.000** no
campo de área total e o número passou — o único filtro era `> 1_000_000`. Foi
pra planilha dele carimbado como "informada por você".

🔑 Teto não é conferência. Medido: TODAS as áreas já informadas por cliente na
história, do maior pro menor:

    880.000 (a do Fábio) · 3.274 · 400 · 378 · 335 · 290 · 192 · 190 · 150 · 73 · 31

A **segunda maior é 3.274 m²**. A dele é **269× isso**. O campo do pé-direito
sempre teve banda plausível (1,8–8,0 m); a área nunca teve.

🪤 E zerar CALADO é a doença do dia inteiro: o cliente digitou, a gente ignorou
e não contou. Agora a resposta do upload devolve `aviso_area`, na tela em que
ele ainda pode corrigir.

🪤 100.000 m² (10 hectares de área construída) é 30× a maior real — generoso de
propósito. O objetivo é pegar dígito a mais e unidade errada, não recusar
projeto grande de verdade.
"""
import io
import os

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()

# As áreas REAIS já informadas por cliente (03/09/2026), a maior primeiro.
_REAIS = [3274.47, 400, 378, 335.4, 290, 192, 190, 150, 73, 31]


# 🩸 03/09, revisão adversarial: a 1ª versão deste arquivo REIMPLEMENTAVA a
# regra aqui dentro (`return not (v < 0 or v > MAX)`) e testava o próprio teste.
# Pior: ele "certificava" que o teto de 1.000.000 tinha sumido com um
# `assert "user_total_area > 1_000_000" not in _FONTE` — e o teto estava VIVO em
# duas outras rotas que escrevem o MESMO campo, escritas com outra grafia
# (`_num("area_total", 5.0, 1_000_000)` e `area > 1_000_000`). O grep passava e
# o defeito continuava. Agora usa a constante REAL do main.
import main as _m  # noqa: E402

MAX = _m._AREA_PLAUSIVEL_MAX


def _passa(valor):
    return not (valor < 0 or valor > MAX)


def test_o_valor_do_fabio_e_recusado():
    """🩸 880.000 m² = 88 hectares, num projeto de rede de estádio."""
    assert not _passa(880000)


def test_CONTROLE_o_teto_ANTIGO_deixava_passar():
    """Sem isto o teste acima não prova que algo mudou."""
    assert not (880000 < 0 or 880000 > 1_000_000), (
        "o controle está errado: o teto antigo TEM que aceitar 880.000")


def test_CONTROLE_toda_area_real_ja_informada_continua_passando():
    """Apertar não pode virar recusar cliente legítimo.

    Estas são todas as áreas que clientes de verdade informaram. Se alguma
    passar a ser recusada, a banda ficou apertada demais.
    """
    for a in _REAIS:
        assert _passa(a), "%s m² é área real de cliente e foi recusada" % a


def test_a_banda_tem_folga_sobre_a_maior_real():
    """O número não pode ser escolhido por gosto — 30× a maior real."""
    maior_real = max(_REAIS)
    assert MAX >= 20 * maior_real, (
        "a banda (%d) tem menos de 20× a maior área real já informada (%.0f) "
        "— folga insuficiente pra projeto grande legítimo" % (MAX, maior_real))
    assert MAX < 880000, "a banda não pega o caso que originou o conserto"


def test_o_codigo_usa_a_banda_e_nao_o_teto_velho():
    assert "_AREA_PLAUSIVEL_MAX = 100_000" in _FONTE, (
        "sumiu a banda de plausibilidade da área informada")
    assert "1_000_000" not in _FONTE, (
        "o teto de 1 km² voltou em algum lugar — ele aceita 880.000")
    assert _FONTE.count("_AREA_PLAUSIVEL_MAX") >= 4, (
        "a banda tem que ser usada nas TRÊS portas que escrevem "
        "user_total_area (upload, inform-area, respostas-processamento), "
        "não só no upload")


def test_o_cliente_e_AVISADO_em_vez_de_ignorado_calado():
    """Zerar sem contar é a falha silenciosa com outro nome."""
    assert '"aviso_area"' in _FONTE, (
        "a resposta do upload voltou a ignorar a área implausível sem avisar")
    assert "upload:area-implausivel" in _FONTE, (
        "sumiu o registro — ninguém saberia quantas vezes isso acontece")


def test_o_numero_e_formatado_sozinho_e_nao_a_frase_toda():
    """🪤 A 1ª versão fazia `.format(...).replace(",", ".")` na frase inteira e
    comeu a vírgula do texto: "…3.274 m²). então NÃO usamos"."""
    assert '.format(aviso_area_implausivel).replace(",", ".")' not in _FONTE, (
        "voltou a trocar vírgula por ponto na frase inteira — estraga a "
        "pontuação do texto que o cliente lê")


def test_o_aviso_CHEGA_na_tela_e_nao_morre_no_JSON():
    """🩸 Eu troquei "zerar calado" por "avisar" e o aviso morria no JSON.

    O backend passou a devolver `resp["aviso_area"]` e NENHUMA tela lia a
    chave — `grep -l aviso_area *.js *.html` não achava nada. É a mesma falha
    silenciosa que o conserto pretendia tirar, um degrau adiante: o teste que
    "cobria" isso lia o FONTE do backend, não a tela.

    🔑 Os três avisos irmãos (aec, estrutural, repetido) são consumidos no
    dashboard; este tinha que estar ao lado deles.
    """
    dash = io.open(os.path.join(os.path.dirname(_BACKEND), "dashboard.html"),
                   encoding="utf-8").read()
    assert "data.aviso_area" in dash, (
        "o dashboard não lê `aviso_area` — o cliente segue com a área ignorada "
        "e sem saber, agora com o aviso montado e jogado fora")
    # e os irmãos continuam lidos, senão alguém trocou um pelo outro
    for irmao in ("data.aviso_aec", "data.aviso_estrutural", "data.aviso_repetido"):
        assert irmao in dash, "sumiu o consumo de %s" % irmao
