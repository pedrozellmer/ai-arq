# -*- coding: utf-8 -*-
"""O e-mail dizia "medimos boa parte" com 6,7% das linhas medidas.

🩸 18/09/2026. O e-mail de "planilha pronta" imprime o placar exato:

    "✓ 7 medido(s) direto do CAD (em branco na planilha) e ⚠ 30 pra você
     confirmar (em laranja)."

e a frase logo abaixo dizia, para QUALQUER projeto de CAD com pelo menos UM
item medido:

    "Seu arquivo veio em CAD (DWG/DXF), então medimos boa parte direto da
     geometria do desenho (os itens em branco)."

A condição no código era `medidos > 0`. O texto afirmava PROPORÇÃO. Os dois
não têm nada a ver um com o outro, e por isso o mesmo e-mail se desmentia em
duas linhas — o número em cima, o adjetivo embaixo.

📏 O TAMANHO, medido no acervo em 18/09 (jobs de cliente concluídos com
DWG/DXF que recebem esta frase):

    faixa de medido   jobs   média
    1 a 9%              7     6,7%
    10 a 24%           25    17,2%
    25 a 49%           31    36,6%
    50% ou mais         9    66,9%

**63 das 72 entregas diziam "boa parte" com menos da metade medida.** Em 32
delas, menos de um quarto. A frase era verdadeira em 9 de 72.

🔑 A regra dura nº1 diz para nunca apresentar estimativa como medição. Ela
costuma ser lida como regra de SELO, mas o selo estava certo o tempo todo: o
que mentia era a prosa, no canal que o cliente mais lê. Vender proporção que
não existe é a mesma violação, escrita por extenso.

🪤 POR QUE ESTE GUARDA EXECUTA O MONTADOR DE E-MAIL, e não lê o fonte: em
18/09 uma revisão adversarial provou que 19 guardas meus passavam verdes
sobre código morto, porque liam a AST em vez de rodar a decisão. A régua mora
em `engine_rules.frase_do_quanto_mediu` (função pura, chamável) e aqui a
gente monta o e-mail DE VERDADE e lê o texto que sairia pro cliente.
"""
import os
import re
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

#: Palavras que afirmam PROPORÇÃO. Se alguma aparecer, ela precisa ser verdade.
_PALAVRAS_DE_PROPORCAO = ("boa parte", "maior parte", "quase tudo",
                          "a maioria", "grande parte")

#: Pares (medidos, total) que o produto entrega de verdade — incluindo as
#: bordas exatas, que é onde adjetivo escorrega.
_CASOS = [
    (1, 200), (7, 37), (35, 534), (2, 30), (262, 1580),      # o mundo real
    (1, 2), (1, 3), (49, 100), (50, 100), (51, 100),          # a borda da metade
    (99, 100), (100, 100), (1, 1),                            # o topo
]


def _itens(medidos, total):
    """Itens de um job: `medidos` com selo branco, o resto laranja."""
    from models import BudgetItem, Confidence
    return [BudgetItem(item_num="1.%d" % k, description="Serviço %d" % k,
                       unit="m²", quantity=10.0 + k,
                       confidence=(Confidence.CONFIRMADO if k < medidos
                                   else Confidence.ESTIMADO),
                       origem="dxf_geom")
            for k in range(total)]


def _email_de(medidos, total, n_cad=1, n_pdf=0):
    """O bloco 'Como lemos o seu projeto' REAL — o mesmo que vai pro cliente."""
    import main
    from _fim_do_job import ProjetoFake
    return main._build_reading_diagnostic(
        _itens(medidos, total), n_pdf, n_cad, "", ProjetoFake(warnings=[]))


def _proporcao_afirmada(html):
    """Qual palavra de proporção o texto usou, se usou alguma."""
    baixo = (html or "").lower()
    return [p for p in _PALAVRAS_DE_PROPORCAO if p in baixo]


def _pares_de_numero(html):
    """Todos os 'N de M' que o texto afirma."""
    return [(int(a), int(b)) for a, b in re.findall(r"(\d+) de (\d+)", html or "")]


# ══════════════════════════════════════════════════════════════════════════
#  O julgamento: rodar o montador e ler o que sairia pro cliente
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("medidos,total", _CASOS,
                         ids=["%dde%d" % c for c in _CASOS])
def test_o_email_so_afirma_proporcao_quando_ela_e_VERDADE(medidos, total):
    """Palavra de proporção só pode aparecer acima da metade.

    Este é o guarda que o defeito de 18/09 teria reprovado: com 7 de 37 o
    e-mail dizia "boa parte", e 7/37 é 18,9%.
    """
    html = _email_de(medidos, total)
    usadas = _proporcao_afirmada(html)
    if not usadas:
        return
    fracao = medidos / float(total)
    assert fracao > 0.5, (
        "o e-mail afirma %r com %d de %d medidos (%.1f%%) — proporção que não "
        "existe, dita ao cliente. Texto: %r"
        % (usadas, medidos, total, 100.0 * fracao, html[:400]))


@pytest.mark.parametrize("medidos,total", _CASOS,
                         ids=["%dde%d" % c for c in _CASOS])
def test_os_numeros_da_frase_batem_com_os_itens_entregues(medidos, total):
    """Todo 'N de M' que o e-mail escreve tem que ser o que a planilha tem.

    🪤 Não basta a frase ser vaga o bastante pra não mentir: se ela cita
    número, o número é conferível — foi assim que o e-mail de 04/09 disse
    5 e 6 para o mesmo fato.
    """
    html = _email_de(medidos, total)
    for a, b in _pares_de_numero(html):
        assert (a, b) == (medidos, total), (
            "o e-mail afirma '%d de %d' mas a planilha tem %d medidos de %d. "
            "Texto: %r" % (a, b, medidos, total, html[:400]))


@pytest.mark.parametrize("medidos,total", _CASOS,
                         ids=["%dde%d" % c for c in _CASOS])
def test_o_email_DIZ_os_numeros_quando_houve_medida(medidos, total):
    """Calar não é honestidade — é o outro jeito de não informar.

    🪤 Este guarda nasceu de um buraco meu, achado ao preparar a sabotagem:
    os outros testes deste arquivo passam TODOS se a régua devolver texto
    vazio, porque aí não há palavra de proporção para conferir nem par de
    número para bater. Um mutante que apagasse a frase inteira sairia vivo,
    e o cliente perderia a informação sem nada ficar vermelho.
    """
    html = _email_de(medidos, total)
    assert _pares_de_numero(html), (
        "o e-mail não disse NENHUM par de número tendo %d medidos de %d — "
        "a frase sumiu. Texto: %r" % (medidos, total, html[:400]))


def test_a_frase_VELHA_nao_sobreviveu_em_lugar_nenhum():
    """'boa parte' era a frase do defeito. Ela não pode voltar por nenhum caso.

    🪤 Cobre o acervo inteiro de casos, não um: o defeito antigo disparava em
    QUALQUER `medidos > 0`, então um caso só poderia não pegá-lo.
    """
    voltou = [(m, t) for m, t in _CASOS if "boa parte" in _email_de(m, t).lower()]
    assert not voltou, (
        "a frase 'boa parte' voltou ao e-mail nos casos %r" % voltou)


def test_medir_TUDO_nao_tem_ramo_proprio_porque_nunca_aconteceu():
    """🪤 O caminho que eu quase defendi sem medir.

    Escrevi um ramo "medimos todas as N linhas" e, antes de escrever guarda
    pra ele, fui ao banco: em **101 jobs de CAD de cliente, zero** saíram 100%
    medidos; o máximo já visto é 86,3%. Ramo inalcançável é código morto, e
    guarda sobre código morto é o verde falso que a revisão de 18/09 já tinha
    me mostrado uma vez nesse mesmo dia.

    Este teste fica no lugar dele para registrar a decisão: 100% cai no ramo
    normal, que é honesto ali também ("a maior parte", com os dois números).
    Se um dia acontecer de verdade, o texto não mente — só fica menos elegante,
    e o placar dirá "⚠ 0 pra você confirmar", que é o que valeria consertar.
    """
    html = _email_de(12, 12)
    assert not [p for p in _proporcao_afirmada(html) if p != "maior parte"], (
        "apareceu palavra de proporção nova no caso 100%%: %r" % html[:400])
    assert "12 de 12" in html, (
        "mesmo medindo tudo, o e-mail tem que dizer os dois números: %r"
        % html[:400])


def test_o_projeto_so_PDF_continua_dizendo_que_nao_mediu():
    """🪤 Controle de vizinhança: o conserto não pode ter mexido no ramo do PDF.

    Esse ramo é o que sustenta a regra "PDF nunca sai medido" no texto.
    """
    html = _email_de(0, 20, n_cad=0, n_pdf=3)
    assert "estimativa" in html.lower(), (
        "o e-mail de projeto só-PDF parou de dizer que saiu tudo como "
        "estimativa: %r" % html[:400])
    assert not _proporcao_afirmada(html), (
        "o e-mail de só-PDF afirma proporção medida: %r" % html[:400])


def test_a_regua_e_CHAMADA_pelo_montador_do_email():
    """Prova de consequência: trocar o que a régua devolve muda o e-mail.

    🪤 É o guarda que a revisão de 18/09 me ensinou a escrever. Procurar a
    chamada no fonte provaria que o ingrediente existe; trocar a régua e ver o
    prato mudar prova que ela está no caminho de verdade.
    """
    import engine_rules
    original = engine_rules.frase_do_quanto_mediu
    marca = "MARCA-DA-REGUA-NO-CAMINHO"
    try:
        engine_rules.frase_do_quanto_mediu = lambda m, t: marca
        html = _email_de(7, 37)
    finally:
        engine_rules.frase_do_quanto_mediu = original
    assert marca in html, (
        "troquei a régua e o e-mail não mudou — ou ele não a chama, ou "
        "descarta o retorno. Texto: %r" % html[:400])


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLES — provar que este arquivo sabe REPROVAR
# ══════════════════════════════════════════════════════════════════════════

def test_CONTROLE_o_texto_de_ANTES_seria_reprovado():
    """A frase exata que estava no ar, com os números exatos do acervo."""
    velho = ("Seu arquivo veio em <b>CAD (DWG/DXF)</b>, então medimos boa parte "
             "direto da geometria do desenho (os itens em branco).")
    assert _proporcao_afirmada(velho), (
        "a conferência não enxerga 'boa parte' — ela não mede nada")
    assert 7 / 37.0 <= 0.5, "aritmética do caso real mudou"


def test_CONTROLE_a_regua_sozinha_nao_promete_o_que_nao_tem():
    """A régua pura, sem o e-mail em volta — as duas pontas da borda."""
    from engine_rules import frase_do_quanto_mediu as frase
    assert "maior parte" not in frase(50, 100), (
        "metade exata não é 'a maior parte'")
    assert "maior parte" in frase(51, 100), (
        "51 de 100 É a maior parte e a frase não diz")
    assert frase(0, 10) == "" and frase(5, 0) == "", (
        "sem medida, ou sem planilha, a régua tem que calar")
