# -*- coding: utf-8 -*-
"""O e-mail da leitura nova tem que contar o que REALMENTE falhou.

🚨 24/08/2026, caso Alan (job e1c48ed7). Ele mandou 7 pranchas; 3 morreram no
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

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
    """Controle negativo: no caso do Giovani (15/08) o filhote bom tinha as
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
    """No caso do Alan o saldo e +59 medidos — e mesmo assim a prancha de
    ELETRICA caiu de 77 para 49 medidos (103 -> 60 itens). Um e-mail que diz so
    "melhoramos" faz o cliente trocar a planilha e descobrir a perda no meio do
    orcamento. Regra da copy publica: nao afirmar o que nao se mede."""
    corpo = _corpo("_email_leitura_nova")
    assert "_piores" in corpo, "o e-mail nao sabe o que piorou"
    assert 'medidos", 0) < _va.get("medidos", 0)' in corpo, (
        "a comparacao por prancha sumiu — volta a ser so o saldo global")


def test_o_aviso_do_que_piorou_aparece_no_corpo_do_email():
    """Calcular e nao mostrar seria pior que nao calcular."""
    corpo = _corpo("_email_leitura_nova")
    # o texto do alarme so pode existir DEPOIS de calcular quem piorou
    assert corpo.index("_piores.sort(") < corpo.index("E o que <b>piorou</b>")


def test_sem_piora_o_email_nao_inventa_alarme():
    """Controle negativo: projeto em que tudo melhorou nao pode receber um
    quadro amarelo vazio."""
    corpo = _corpo("_email_leitura_nova")
    assert "if _piores:" in corpo, (
        "o alarme do que piorou saiu de baixo da condicao: passaria a sair sempre, ate onde nada piorou")


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
