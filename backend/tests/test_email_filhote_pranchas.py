# -*- coding: utf-8 -*-
"""O e-mail da leitura nova tem que contar o que REALMENTE falhou.

🚨 24/08/2026, caso cliente-19 (job e1c48ed7). Ele mandou 7 pranchas; 3 morreram no
KeyError de layout do libredwg — entre elas as DUAS de arquitetura. Depois do
conserto, o filhote leu as 7.

O e-mail automático dizia: "O que mudou: 147 → 263 itens e 92 → 151 medidos".
Verdade, e ainda assim a história errada: item é CONSEQUÊNCIA. A causa — e o
que o cliente reclamaria — é que quase metade do projeto dele não tinha sido
lida. Quem lê "263 itens" não entende que perdeu prancha.

Pedro, 24/08, sobre falha do motor: *"e quando morrer, temos que explicar isso
para os clientes né"*. Explicar é dizer o que morreu, não só o saldo.
"""
import io
import os
import re
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import main                                              # noqa: E402


def _email(antes, depois):
    """Monta o e-mail real e devolve o HTML que sairia pro cliente."""
    _assunto, html = main._build_leitura_nova_email(
        "cliente-19", "Casa de praia", "ev000001", antes, depois)
    return html


def _mesmas_pranchas():
    """Caso do filhote bom de 15/08: MESMAS pranchas, números um pouco
    melhores em todas. Nada piorou e nada entrou."""
    antes = {"itens": 40, "medidos": 12, "pranchas": 3,
             "por_prancha": {"planta-a.dxf": {"itens": 20, "medidos": 6},
                             "planta-b.dxf": {"itens": 10, "medidos": 3},
                             "planta-c.dxf": {"itens": 10, "medidos": 3}}}
    depois = {"itens": 44, "medidos": 15, "pranchas": 3,
              "por_prancha": {"planta-a.dxf": {"itens": 22, "medidos": 8},
                              "planta-b.dxf": {"itens": 11, "medidos": 4},
                              "planta-c.dxf": {"itens": 11, "medidos": 3}}}
    return antes, depois


def _caso_cliente_19():
    """24/08, job e1c48ed7: 3 das 7 pranchas tinham morrido (as duas de
    arquitetura entre elas) e o saldo global é +59 medidos — MAS pranchas
    antigas PERDERAM medição.

    🪤 06/09 (cético): até aqui as duas pranchas do fixture moviam `itens` e
    `medidos` na MESMA direção, então trocar a comparação do `_piores` de
    `medidos` por `itens` deixava o guarda verde. Agora a ELÉTRICA é o caso
    clássico da releitura — **GANHA item (103 → 140) e PERDE medição
    (77 → 49)** — e só quem compara `medidos` a enxerga. A HIDRÁULICA perde nos
    dois, pra que o quadro tenha DUAS linhas: assim `_piores[:1]` (além de
    `[:0]` e `[3:]`) também reprova."""
    antes = {"itens": 177, "medidos": 112, "pranchas": 4,
             "por_prancha": {"4366-AR-A_libredwg.dxf": {"itens": 44, "medidos": 15},
                             "4366-EL-E_libredwg.dxf": {"itens": 103, "medidos": 77},
                             "4366-HI-H_libredwg.dxf": {"itens": 30, "medidos": 20}}}
    depois = {"itens": 325, "medidos": 165, "pranchas": 7,
              "por_prancha": {"4366-AR-A_libredwg.dxf": {"itens": 160, "medidos": 102},
                              "4366-EL-E_libredwg.dxf": {"itens": 140, "medidos": 49},
                              "4366-HI-H_libredwg.dxf": {"itens": 25, "medidos": 14}}}
    return antes, depois


def _ganhou_prancha_sem_piorar():
    """O caso NORMAL do filhote — e o motivo de o e-mail existir: pranchas que
    não tinham entrado entraram, e NENHUMA das antigas perdeu medição.

    `planta-a` fica com os MESMOS 15 medidos de propósito: empate não é piora,
    então trocar o `<` do `_piores` por `<=` também tem que reprovar."""
    antes = {"itens": 44, "medidos": 15, "pranchas": 1,
             "por_prancha": {"planta-a.dxf": {"itens": 44, "medidos": 15}}}
    depois = {"itens": 263, "medidos": 151, "pranchas": 4,
              "por_prancha": {"planta-a.dxf": {"itens": 46, "medidos": 15},
                              "planta-b.dxf": {"itens": 117, "medidos": 66},
                              "planta-c.dxf": {"itens": 100, "medidos": 70}}}
    return antes, depois


def _main():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _corpo(nome):
    src = _main()
    i = src.index("def " + nome)
    j = src.index("\n@app.", i) if "\n@app." in src[i:] else i + 6000
    return src[i:min(j, i + 6000)]


def test_a_contagem_do_filhote_inclui_pranchas():
    """Sem contar prancha, o e-mail não tem como falar dela."""
    corpo = _corpo("admin_liberar_filhote") if "def admin_liberar_filhote" in _main() else _main()
    assert '"select": "confidence,ref_sheet"' in corpo, (
        "o _conta voltou a ler só confidence — o e-mail perde a prancha")
    assert '"pranchas": len(_pr)' in corpo


def test_o_email_fala_de_prancha_antes_de_falar_de_item():
    """Ordem importa: é a primeira linha que o cliente lê."""
    corpo = _corpo("_email_leitura_nova")
    assert "ganho_pr" in corpo, "o e-mail não sabe quantas pranchas entraram"
    i_pr = corpo.index("if ganho_pr > 0:")
    i_it = corpo.index("if ganho_itens > 0:")
    assert i_pr < i_it, (
        "a linha de itens vem antes da de pranchas — o cliente lê a "
        "consequência antes da causa")


def test_o_texto_diz_que_a_prancha_NAO_TINHA_ENTRADO():
    """Eufemismo aqui é mentira por omissão: 'lemos mais pranchas' esconde que
    elas tinham sido perdidas em silêncio na primeira vez."""
    corpo = _corpo("_email_leitura_nova")
    assert "n&atilde;o tinham entrado" in corpo


def test_sem_ganho_de_prancha_o_email_nao_inventa_uma():
    """Controle negativo: no caso do cliente-53 (15/08) o filhote bom tinha as
    MESMAS pranchas e números menores. Se o texto de prancha aparecesse sempre,
    seria afirmação falsa — e copy pública sem fonte é regra dura."""
    corpo = _corpo("_email_leitura_nova")
    m = re.search(r"if ganho_pr > 0:", corpo)
    assert m, "a linha de prancha não está sob condição — sairia sempre"


def test_o_email_continua_dizendo_que_o_original_fica():
    """Regra nº7: nunca dar a entender que a versão nova substitui a dele."""
    corpo = _corpo("_email_leitura_nova")
    assert "continua no painel" in corpo


# ══════════════════════════════════════════════════════════════════════════
#  🚨 Honestidade dos DOIS lados
# ══════════════════════════════════════════════════════════════════════════
def test_o_email_conta_tambem_o_que_PIOROU():
    """No caso do cliente-19 o saldo e +59 medidos — e mesmo assim a prancha de
    ELETRICA caiu de 77 para 49 medidos (103 -> 60 itens). Um e-mail que diz so
    "melhoramos" faz o cliente trocar a planilha e descobrir a perda no meio do
    orcamento. Regra da copy publica: nao afirmar o que nao se mede."""
    corpo = _corpo("_email_leitura_nova")
    assert "_piores" in corpo, "o e-mail nao sabe o que piorou"
    assert 'medidos", 0) < _va.get("medidos", 0)' in corpo, (
        "a comparacao por prancha sumiu — volta a ser so o saldo global")


def test_o_aviso_do_que_piorou_aparece_no_corpo_do_email():
    """Calcular e nao mostrar seria pior que nao calcular.

    🪤 06/09: o guarda comparava a POSIÇÃO de duas strings no fonte. Trocar o
    `corpo += (` do quadro amarelo por `_alarme_morto = (` mantém as duas
    strings na mesma ordem — a conta continua sendo feita, o cliente nunca vê.
    Agora o teste confere o HTML ENTREGUE."""
    html = _email(*_caso_cliente_19())
    i_alarme = html.find("E o que <b>piorou</b>")
    assert i_alarme > 0, (
        "o quadro do que piorou foi calculado e NÃO entrou no corpo do e-mail")
    # o quadro amarelo é o quadro amarelo — e vem antes do rodapé das 2 versões
    i_box = html.rfind("background:#FFFBEB", 0, i_alarme)
    assert i_box > 0, "o alarme perdeu o destaque visual"
    quadro = html[i_box:html.index("</div>", i_alarme)]

    # 🪤 06/09: alarme ACESO com quadro VAZIO é pior que alarme nenhum —
    # `_piores[:0]`, `[3:]` ou `[:1]` mantinham "E o que piorou" e o
    # background amarelo, e o cliente via o susto sem saber QUAL prancha.
    # Por isso a conferência é do CONTEÚDO, prancha por prancha.
    assert "<b>4366-EL-E</b> (77 &rarr; 49 medidos)" in quadro, (
        "a prancha que GANHOU item (103 → 140) e PERDEU medição (77 → 49) "
        "não foi avisada — é o caso clássico da releitura, e quem compara "
        "`itens` em vez de `medidos` não a enxerga: " + quadro)
    assert "<b>4366-HI-H</b> (20 &rarr; 14 medidos)" in quadro, (
        "a segunda prancha que piorou sumiu do quadro — o corte do `_piores` "
        "está mostrando menos do que calculou: " + quadro)
    assert "4366-AR-A" not in quadro, (
        "a prancha que MELHOROU (15 → 102 medidos) foi acusada de piorar")

    assert i_alarme < html.index("A sua vers&atilde;o original continua no painel"), (
        "o aviso do que piorou caiu depois do rodapé — o cliente lê 'ficou "
        "melhor' e para de ler")


@pytest.mark.parametrize("cenario,ganhou_prancha", [
    ("mesmas_pranchas", False),
    ("ganhou_prancha", True),
])
def test_sem_piora_o_email_nao_inventa_alarme(cenario, ganhou_prancha):
    """Controle negativo: projeto em que nada piorou nao pode receber um
    quadro amarelo.

    🪤 06/09 (cetico): o guarda lia o fonte (`"if _piores:" in corpo`) e o
    UNICO cenario que ele conhecia tinha ganho_pr == 0. Quem acendesse o alarme
    so no ramo "ganhou prancha" — que e o caso NORMAL do filhote e o motivo de
    o e-mail existir — passava batido. Agora ele EXECUTA o builder nos dois
    ramos.
    """
    antes, depois = (_ganhou_prancha_sem_piorar() if ganhou_prancha
                     else _mesmas_pranchas())
    html = _email(antes, depois)

    # o e-mail tem que ter saido de verdade (senao o controle negativo passa a vacuo)
    assert "Refizemos a leitura" in html
    _entrou = "prancha(s) que n&atilde;o tinham entrado agora entraram"
    if ganhou_prancha:
        assert _entrou in html, (
            "o ramo 'ganhou prancha' nem foi exercitado — o cenario nao vale como controle")
    else:
        assert _entrou not in html

    assert "E o que <b>piorou</b>" not in html, (
        "quadro do que piorou apareceu num projeto em que NENHUMA prancha "
        "perdeu medicao (%s)" % cenario)
    assert "#FFFBEB" not in html, (
        "o destaque amarelo do alarme saiu sem alarme nenhum (%s)" % cenario)


def test_a_prancha_que_piorou_sai_com_nome_de_gente():
    corpo = _corpo("_email_leitura_nova")
    assert "_nome_prancha_bonito(_k)" in corpo, (
        "o cliente leria '4366-EL-E_libredwg.dxf', que ele nunca enviou")


def test_o_email_explica_POR_QUE_as_duas_versoes_ficam():
    """Se piorou em algo, o motivo de manter as duas deixa de ser cortesia e
    vira necessidade — e o texto tem que dizer isso."""
    corpo = _corpo("_email_leitura_nova")
    assert "lado a lado no seu painel" in corpo


def test_a_contagem_por_prancha_existe_no_conta():
    src = _main()
    assert '"por_prancha": _det' in src
