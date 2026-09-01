# -*- coding: utf-8 -*-
"""Pranchas do MESMO job lidas em escalas diferentes não podem sair MEDIDAS.

🩸 CASO AMANDA — job `349e75a5`, 10/08/2026, 14 pranchas.
O mesmo projeto foi lido em TRÊS escalas:

    2 pranchas (9T-EDA, Cobertura)      fator 0.001    → milímetros
    6 pranchas (9T-ELE-*)               fator 0.0254   → POLEGADAS
    4 pranchas (9T-HAG, forro, ...)     fator 1.0      → metros

Um prédio tem UMA unidade. E uma das pranchas em polegadas entregou:

    "Condutos no teto — eletrodutos/eletrocalhas = 9,92 ml · ✓ MEDIDO do CAD"

Se o desenho está em milímetro o certo seria 0,39 m; se está em metro, 390 m.
Nas duas hipóteses 9,92 está errado — e saiu carimbado como medido, que é a
afirmação mais forte que a planilha faz. Regra dura nº1 furada.

🔑 A CAUSA: a régua de unidade decide POR ARQUIVO, isoladamente, e nada no
motor comparava as pranchas entre si. `fator_para_metros` era gravado uma vez e
lido em apenas dois lugares — a linha de log e a sombra de cômodos. Existe um
pré-passe de consenso, mas ele só propaga fator PROVADO POR COTA; quando
nenhuma prancha prova (que é o caso), ele fica nulo e o portão nunca dispara.

📏 MEDIDO NO ACERVO em 01/09/2026: **6 de 73 jobs de CAD** têm fatores
divergentes, e os 6 divergem **100× ou mais**. Três são entrega real de
cliente (Alan 24/08, Amanda 10/08 ×2).

🪤 A regra NÃO pune quem está bem: 92% dos jobs têm todas as pranchas de acordo
e não são tocados. E contagem ('un', 'pç') nunca entra — contar bloco não
depende de escala (decisão deliberada de 17/08).
"""
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from engine_rules import (  # noqa: E402
    escala_divergente, item_e_de_escala, DIVERGENCIA_MINIMA, REGUAS_QUE_PROVAM)


def _p(nome, fator, regua="nao-decidiu", unidade="?"):
    return {"prancha": nome, "fator": fator, "regua": regua, "unidade": unidade}


# ── Os casos REAIS, como saíram no banco ───────────────────────────────────
def _amanda():
    """349e75a5 — três escalas, nenhuma provada por cota."""
    return ([_p("9T-EDA-PLD-GER0-01_R00", 0.001), _p("Cobertura", 0.001)]
            + [_p("9T-ELE-%d" % i, 0.0254) for i in range(6)]
            + [_p("9T-HAG-PLD-GER0-01-10_R00", 1.0), _p("Detalhamento", 1.0),
               _p("forro", 1.0), _p("Paginacao", 1.0)])


def _alan():
    """e1c48ed7 — uma prancha em mm contra três em metros."""
    return [_p("4366-EL-B", 0.001), _p("4366-EL-E", 1.0),
            _p("4366-IH-E", 1.0), _p("4366-VA-E", 1.0)]


def _tiago():
    """2a42f7ec — 01/09, climatização, 2 em mm e o resto em metros."""
    return ([_p("F01-GER", 0.001), _p("F02-GER", 0.001)]
            + [_p("F%02d" % i, 1.0, "corrigida_plausibilidade") for i in range(3, 20)])


def test_amanda_TRES_escalas_e_ninguem_confiavel():
    """🩸 O caso do dia. Sem árbitro, ninguém sai medido."""
    div, susp, resumo = escala_divergente(_amanda())
    assert div is True, "não viu a divergência de 1000× do caso Amanda"
    assert len(susp) == 12, (
        "com NENHUMA prancha provada por cota não há árbitro — todas as 12 "
        "deveriam entrar, entraram %d" % len(susp))
    assert "9T-ELE-0" in susp, "a prancha em POLEGADAS ficou de fora"
    assert "nenhuma prancha provou" in resumo, resumo


def test_alan_tambem_diverge():
    div, susp, _ = escala_divergente(_alan())
    assert div is True
    assert len(susp) == 4, "sem prova, todas entram"


def test_quando_UMA_prancha_PROVA_por_cota_ela_e_o_arbitro():
    """🔑 O caso bom: se alguém provou a escala, esse fator é a verdade e só
    quem discorda dele é suspeito. O Alan manteria os 20 itens medidos."""
    esc = [_p("4366-EL-B", 0.001),
           _p("4366-EL-E", 1.0, "validada"),
           _p("4366-IH-E", 1.0), _p("4366-VA-E", 1.0)]
    div, susp, resumo = escala_divergente(esc)
    assert div is True, "a divergência continua existindo e o cliente tem que saber"
    assert susp == {"4366-EL-B"}, (
        "só a prancha que discorda da PROVADA deveria ser suspeita, veio %s" % susp)
    assert "provaram a escala por cota" in resumo


def test_tiago_climatizacao():
    div, susp, _ = escala_divergente(_tiago())
    assert div is True
    assert "F01-GER" in susp and "F02-GER" in susp


def test_todas_as_reguas_que_provam_servem_de_arbitro():
    for r in REGUAS_QUE_PROVAM:
        div, susp, _ = escala_divergente(
            [_p("boa", 1.0, r), _p("ruim", 0.001)])
        assert div is True, r
        assert susp == {"ruim"}, "%s não serviu de árbitro: %s" % (r, susp)


def test_plausibilidade_NAO_e_prova():
    """🪤 corrigida_plausibilidade é inferência ('em mm o desenho mediria 2 cm,
    impossível'), não medição. Não pode arbitrar."""
    div, susp, _ = escala_divergente(
        [_p("a", 1.0, "corrigida_plausibilidade"), _p("b", 0.001)])
    assert div is True
    assert susp == {"a", "b"}, "plausibilidade virou árbitro — não é prova"


# ── CONTROLES: o guarda tem que RECUSAR de verdade ─────────────────────────
def test_CONTROLE_projeto_saudavel_NAO_e_tocado():
    """🧪 92% dos jobs. Se este passar como divergente, a regra quebra o produto."""
    esc = [_p("A", 0.001), _p("B", 0.001), _p("C", 0.001)]
    div, susp, resumo = escala_divergente(esc)
    assert div is False and susp == set() and resumo == "", (
        "acusou divergência num projeto com todas as pranchas iguais")


def test_CONTROLE_uma_prancha_so_nunca_diverge():
    """Caso Edvaldo (b5ce23ff/d2bedf82): 1 prancha, fator 0.01, régua validada."""
    div, susp, _ = escala_divergente([_p("TOP-EST-PE-116-FRM-TIP-R00", 0.01, "validada")])
    assert div is False and susp == set()


def test_CONTROLE_diferenca_pequena_nao_conta():
    """🪤 Ruído de arredondamento não é erro de unidade."""
    div, _, _ = escala_divergente([_p("A", 1.0), _p("B", 1.05)])
    assert div is False, "9× ou menos é outra coisa, não erro de unidade"
    # e o limiar existe de verdade
    div2, _, _ = escala_divergente([_p("A", 1.0), _p("B", DIVERGENCIA_MINIMA)])
    assert div2 is True, "o limiar de %s× não está sendo aplicado" % DIVERGENCIA_MINIMA


def test_CONTROLE_lista_vazia_ou_lixo_nao_quebra():
    for entrada in (None, [], [{}], [{"prancha": "x"}], [_p("x", 0)], [_p("x", -1)]):
        div, susp, _ = escala_divergente(entrada)
        assert div is False and susp == set(), entrada


def test_CONTROLE_a_unidade_de_CONTAGEM_nunca_e_de_escala():
    """🪤 Decisão de 17/08: contar bloco não depende de escala. Se 'un' entrasse,
    a regra apagaria a contagem, que é justamente o que o motor faz bem."""
    for u in ("un", "un.", "pç", "pc", "cj", "vb", "verba", "kg", ""):
        assert item_e_de_escala(u) is False, "'%s' virou unidade de escala" % u
    for u in ("m", "m²", "m2", "m³", "m3", "ml", "M²", " m "):
        assert item_e_de_escala(u) is True, "'%s' deixou de ser unidade de escala" % u


def test_CONTROLE_o_item_da_amanda_seria_pego():
    """🧪 O teste que fecha o caso: a linha que ela recebeu carimbada."""
    div, susp, _ = escala_divergente(_amanda())
    item_unidade, item_prancha = "ml", "9T-ELE-IMP-GER0-03_220-127V_R00"
    assert div and item_e_de_escala(item_unidade), "a regra não alcança 'ml'"
    # a prancha dela está entre as suspeitas (nome parcial, como no ref_sheet)
    assert any(s.startswith("9T-ELE") for s in susp), (
        "a prancha em polegadas não entrou na lista de suspeitas: %s" % susp)


def test_CONTROLE_main_py_REALMENTE_chama_o_guarda():
    """🪤 Função perfeita que ninguém chama não guarda nada. Confere no ponto de
    chamada — e o controle abaixo prova que esta checagem sabe reprovar."""
    import io
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    limpo = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    assert "escala_divergente as _esc_div" in limpo, (
        "main.py não importa mais o guarda de escala divergente")
    assert "_esc_div(_escala_por_prancha)" in limpo, (
        "o guarda é importado mas nunca chamado")
    assert "_escala_por_prancha.append(" in limpo, (
        "ninguém alimenta a lista — o guarda receberia [] e nunca dispararia")


def test_CONTROLE_a_checagem_de_chamada_sabe_REPROVAR():
    """🧪 Controle positivo da checagem acima: com a chamada COMENTADA ela tem
    que acusar. Sem isto, o teste anterior passaria com o guarda desligado."""
    import re as _re
    falso = "\n".join([
        "        # _esc_div(_escala_por_prancha)",
        "        from engine_rules import escala_divergente as _esc_div",
    ])
    limpo = "\n".join(l for l in falso.splitlines() if not l.lstrip().startswith("#"))
    assert "_esc_div(_escala_por_prancha)" not in limpo, (
        "a checagem aceita a chamada COMENTADA — não guarda nada")
    assert _re.search(r"escala_divergente as _esc_div", limpo), (
        "o controle não está exercitando o mesmo padrão do teste real")
