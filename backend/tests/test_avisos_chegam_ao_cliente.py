# -*- coding: utf-8 -*-
"""O aviso que explica a falha tem que CHEGAR — e ser verdade.

🚨 24/08/2026, caso cliente-19 (job e1c48ed7). Pedro perguntou: *"e quando morrer,
temos que explicar isso para os clientes né"*. A gente explicava. Mal.

Ele mandou 7 pranchas; 3 morreram (as DUAS de arquitetura entre elas). O motor
gerou 7 avisos. Três defeitos, todos confirmados no banco:

 1. O e-mail mandava `warnings[:2]` — os dois PRIMEIROS, na ordem em que o motor
    calhou de gerar. Saíram "leitura incompleta" e "usamos o leitor alternativo".
    O terceiro, que nunca saiu, era "⚠ 3 prancha(s) não entraram nesta planilha".
    O aviso que explicava metade do projeto sumido ficou só na tela — e só 1 de
    44 clientes volta ao site (medido em 08/08).

 2. O aviso do corte dizia "Reprocessar pode completar a planilha". Conselho
    IMPOSSÍVEL: na prancha de elétrica dele o corte aconteceu nas 3 leituras
    (162, 156, 112 itens). O reprocesso muda ONDE o corte cai, não SE cai — e a
    terceira deu MENOS. Gastaria o único reprocesso grátis dele por nada.

 3. Os avisos citavam '4366-EL-E_libredwg.dxf'. Ele enviou '4366-EL-E.dwg'. O
    "_libredwg" é artefato NOSSO. Ele procuraria na pasta um arquivo inexistente.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 🪤 Janela de tamanho fixo mede o vizinho (ou um pedaço) e passa
# verde por engano — a auditoria de 25/08 achou 17 assim. O recorte
# certo mora num lugar só.
from _corpo import corpo_de  # noqa: E402
import re

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, _BACKEND)

import main  # noqa: E402


_AVISOS_DO_CLIENTE_19 = [
    "A leitura da prancha '4366-EL-E.dwg' ficou INCOMPLETA: ela tem itens demais",
    "Usamos o leitor alternativo nesta prancha",
    "⚠ 3 prancha(s) não entraram nesta planilha",
    "Escala assumida por padrão em 1 prancha",
    "⚠ 2 itens sem unidade reconhecida",
    "Blocos repetidos foram agrupados",
    "✅ Escala conferida pelas cotas",
]


class _ItemFalso(object):
    """O minimo que `_build_reading_diagnostic` le de um item."""

    def __init__(self, confianca):
        self.confidence = confianca
        self.origem = "cad"


def _diagnostico_com(avisos):
    """Monta o bloco 'Como lemos o seu projeto' - a funcao REAL do e-mail."""
    from models import Confidence as _Conf
    itens = [_ItemFalso(_Conf.CONFIRMADO), _ItemFalso(_Conf.ESTIMADO)]
    projeto = type("ProjetoFalso", (), {"warnings": list(avisos)})()
    bloco = main._build_reading_diagnostic(itens, 0, 1, "arquitetura", projeto)
    assert bloco, "o bloco de diagnostico nem foi montado - o e-mail saiu mudo"
    return bloco


def _avisos_no_email(bloco):
    """Os avisos que o cliente REALMENTE le, na ordem em que sairam."""
    import html as _hd
    saiu = []
    for pedaco in bloco.split("<br>&bull;")[1:]:
        texto = pedaco.split("</div>")[0].strip()
        if texto.startswith("<i>e mais"):
            continue
        saiu.append(_hd.unescape(texto))
    return saiu



def _main():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _sem_o_que_e_removido(src: str) -> str:
    """Tira as strings que o código está REMOVENDO, não enviando.

    🪤 3ª vez hoje que um guarda meu tropeça em contexto: primeiro a docstring
    que CITA a frase proibida pra explicar por que ela saiu; depois o prompt do
    chat que a PROÍBE; agora o `.replace("<frase velha>", "<frase nova>")` que a
    apaga dos avisos herdados de jobs antigos.

    Em todos os três, a frase está no arquivo justamente porque alguém a está
    combatendo. Um guarda que não distingue isso me empurra a apagar a defesa
    pra calar o alarme — o oposto do que ele existe pra fazer."""
    import re as _re
    # 🪤 `\s` ja casa quebra de linha — nao preciso de escape nenhum aqui,
    # e foi justamente um escape que quebrou este arquivo na 1a tentativa.
    return _re.sub(r'\.replace\(\s*"[^"]*"', '.replace(<removida>', src)


def _sem_comentarios(src: str) -> str:
    """🪤 O primeiro teste destes reprovou por um motivo bobo e revelador: eu
    CITEI a frase errada dentro do comentário que explica por que ela saiu. Um
    guarda que não separa comentário de mensagem viva ou dá alarme falso, ou
    (pior) me faria apagar a documentação pra calar o alarme."""
    _NL = chr(10)
    return _NL.join(
        l for l in src.splitlines() if not l.strip().startswith("#"))


# ══════════════════════════════════════════════════════════════════════════
#  1. Nada de aviso descartado calado no e-mail
# ══════════════════════════════════════════════════════════════════════════
def test_o_email_nao_corta_mais_nos_dois_primeiros():
    """🩸 O defeito de 24/08 em pessoa: com os 7 avisos do cliente-19, o e-mail
    mandava os DOIS PRIMEIROS na ordem crua do motor.

    🪤 06/09/2026 — ESTE GUARDA ERA CEGO. Ele proibia a string `or [])[:2]:`.
    Reescrevi o mesmo corte com `or list()` no lugar de `or []`: o cliente
    voltava a receber 2 avisos de 7, sem anúncio nenhum, e ele passou verde.
    Agora monta o e-mail e conta o que saiu.
    """
    saiu = _avisos_no_email(_diagnostico_com(_AVISOS_DO_CLIENTE_19))
    assert len(saiu) == 6, (
        "o e-mail levou %d dos 7 avisos (o teto é 6) — voltou o corte cego: %r"
        % (len(saiu), saiu))
    assert any("não entraram" in a for a in saiu), (
        "o aviso '3 prancha(s) não entraram' NÃO saiu no e-mail — é o de "
        "24/08 de novo: metade do projeto sumido e o cliente só sabendo pela "
        "tela, que 43 de 44 nunca reabrem. Saiu: %r" % (saiu,))

def test_o_email_ordena_por_gravidade_e_prancha_faltando_vem_primeiro():
    """🪤 06/09/2026 — o guarda antigo conferia as strings `_avisos.sort(...)` e
    `def _peso_aviso` no fonte. Inverti a condição DENTRO do `_peso_aviso`
    (`in` → `not in`, com a frase e o `return 0` intactos no corpo) e ele
    passou: o aviso de prancha faltando caía pro 7º lugar e era cortado pelo
    teto de 6. Agora a ordem é lida no e-mail montado."""
    saiu = _avisos_no_email(_diagnostico_com(_AVISOS_DO_CLIENTE_19))
    assert "não entraram" in saiu[0], (
        "prancha inteira faltando não é o 1º aviso do e-mail — a ordem voltou "
        "a ser a que o motor calhou de gerar. Ordem que saiu: %r" % (saiu,))
    pos = {a: i for i, a in enumerate(saiu)}
    incompleta = next(i for a, i in pos.items() if "INCOMPLETA" in a)
    alternativo = next(i for a, i in pos.items() if "leitor alternativo" in a)
    assert incompleta < alternativo, (
        "'leitura incompleta' tem que vir antes de aviso neutro — foi um "
        "neutro que ocupou a vaga do aviso grave em 24/08")

def test_o_que_nao_couber_e_anunciado_nunca_sumido():
    """Trocar um corte cego por outro não seria conserto."""
    src = _main()
    assert "e mais {len(_avisos) - _TETO_EMAIL} aviso(s)" in src, (
        "o e-mail volta a descartar avisos em silêncio quando passam do teto")


def test_boa_noticia_vai_por_ultimo():
    """'✅ Escala conferida' é ótimo, mas não pode empurrar 'faltou prancha'
    pra fora do e-mail."""
    assert "return 9" in corpo_de("_peso_aviso")


# ══════════════════════════════════════════════════════════════════════════
#  2. Conselho impossível
# ══════════════════════════════════════════════════════════════════════════
def test_o_aviso_de_corte_nao_manda_mais_reprocessar():
    src = _main()
    i = src.index("ficou \nINCOMPLETA") if "ficou \nINCOMPLETA" in src else src.index("INCOMPLETA: ela tem itens demais")
    trecho = src[max(0, i - 900):i + 900]
    assert "Reprocessar normalmente NÃO" in trecho, (
        "o aviso de corte voltou a prometer que reprocessar completa a planilha "
        "— na elétrica do cliente-19 cortou 3 de 3 vezes, e a 3ª deu MENOS itens")
    assert "Reprocessar pode completar a planilha" not in _sem_o_que_e_removido(
        _sem_comentarios(src)), (
        "o texto antigo ainda é ENVIADO ao cliente (fora de comentário e fora "
        "de um .replace que o remove)")


def test_o_aviso_de_corte_diz_o_que_o_cliente_PODE_fazer():
    """Tirar o conselho errado sem pôr o certo deixa o cliente sem saída."""
    src = _main()
    i = src.index("INCOMPLETA: ela tem itens demais")
    trecho = src[i:i + 900]
    assert "exporte-a em partes" in trecho
    assert "fale com a gente" in trecho


def test_o_aviso_de_corte_nao_assusta_sobre_o_que_veio():
    """Os itens lidos ANTES do corte estão certos. Não dizer isso faria o
    cliente desconfiar da planilha inteira."""
    src = _main()
    i = src.index("INCOMPLETA: ela tem itens demais")
    assert "os que vieram estão " in src[i:i + 900]


# ══════════════════════════════════════════════════════════════════════════
#  3. Nome de arquivo interno não vaza
# ══════════════════════════════════════════════════════════════════════════
def test_o_aviso_de_corte_usa_o_nome_real_da_prancha():
    src = _main()
    i = src.index("INCOMPLETA: ela tem itens demais")
    trecho = src[max(0, i - 400):i]
    assert "_nome_prancha_bonito(dxf_path)" in trecho, (
        "voltou o os.path.basename cru — o cliente lê '_libredwg.dxf', que ele "
        "nunca enviou")


def test_a_lista_de_pranchas_que_faltaram_usa_o_nome_real():
    src = _main()
    assert "_nome_prancha_bonito(e.split(\":\")[0])" in src, (
        "a lista 'Faltaram: ...' voltou a mostrar nome interno de conversão")


def test_o_helper_de_nome_bonito_tira_mesmo_o_sufixo_interno():
    """Controle positivo do helper — se ele não limpar, os dois testes acima
    passam e o cliente continua vendo o nome errado."""
    import sys
    sys.path.insert(0, _BACKEND)
    corpo = corpo_de("_nome_prancha_bonito")
    for suf in ("_libredwg.dxf", ".slim.dxf"):
        assert suf in corpo, "o helper parou de conhecer o sufixo %s" % suf


# ══════════════════════════════════════════════════════════════════════════
#  Controle: o resto do e-mail não pode ter sido derrubado junto
# ══════════════════════════════════════════════════════════════════════════
def test_o_email_continua_montando_o_bloco_de_diagnostico():
    src = _main()
    assert "Como lemos o seu projeto" in src
    assert "_hd.escape(w)" in src, "sumiu o escape de HTML dos avisos"
