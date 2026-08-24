# -*- coding: utf-8 -*-
"""O aviso que explica a falha tem que CHEGAR — e ser verdade.

🚨 24/08/2026, caso Alan (job e1c48ed7). Pedro perguntou: *"e quando morrer,
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
import re

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _main():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


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
    src = _main()
    assert 'or [])[:2]:' not in src, (
        "voltou o corte cego em 2 avisos — foi assim que o 'ⓘ 3 pranchas não "
        "entraram' do Alan nunca saiu por e-mail")


def test_o_email_ordena_por_gravidade_e_prancha_faltando_vem_primeiro():
    src = _main()
    assert "def _peso_aviso" in src, "sumiu a ordenação por gravidade"
    # 🪤 Definir não é usar: na primeira versão deste guarda eu conferia só a
    # existência da função. Sabotei o CHAMADOR (troquei o sort por um corte em 2)
    # e o teste passou verde. Guarda que não pega o defeito que motivou ele é
    # enfeite.
    assert "_avisos.sort(key=_peso_aviso)" in _sem_comentarios(src), (
        "a ordenação existe mas não é aplicada — os avisos voltam à ordem "
        "em que o motor calhou de gerar")
    assert "_avisos[:2]" not in _sem_comentarios(src), "voltou o corte em 2"
    i = src.index("def _peso_aviso")
    corpo = src[i:i + 700]
    # prancha inteira faltando tem que pesar MENOS (vir antes) que o resto
    assert "não entraram" in corpo and "return 0" in corpo


def test_o_que_nao_couber_e_anunciado_nunca_sumido():
    """Trocar um corte cego por outro não seria conserto."""
    src = _main()
    assert "e mais {len(_avisos) - _TETO_EMAIL} aviso(s)" in src, (
        "o e-mail volta a descartar avisos em silêncio quando passam do teto")


def test_boa_noticia_vai_por_ultimo():
    """'✅ Escala conferida' é ótimo, mas não pode empurrar 'faltou prancha'
    pra fora do e-mail."""
    src = _main()
    i = src.index("def _peso_aviso")
    assert "return 9" in src[i:i + 700]


# ══════════════════════════════════════════════════════════════════════════
#  2. Conselho impossível
# ══════════════════════════════════════════════════════════════════════════
def test_o_aviso_de_corte_nao_manda_mais_reprocessar():
    src = _main()
    i = src.index("ficou \nINCOMPLETA") if "ficou \nINCOMPLETA" in src else src.index("INCOMPLETA: ela tem itens demais")
    trecho = src[max(0, i - 900):i + 900]
    assert "Reprocessar normalmente NÃO" in trecho, (
        "o aviso de corte voltou a prometer que reprocessar completa a planilha "
        "— na elétrica do Alan cortou 3 de 3 vezes, e a 3ª deu MENOS itens")
    assert "Reprocessar pode completar a planilha" not in _sem_comentarios(src), (
        "o texto antigo ainda é enviado ao cliente (fora de comentário)")


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
    src = _main()
    i = src.index("def _nome_prancha_bonito")
    corpo = src[i:i + 400]
    for suf in ("_libredwg.dxf", ".slim.dxf"):
        assert suf in corpo, "o helper parou de conhecer o sufixo %s" % suf


# ══════════════════════════════════════════════════════════════════════════
#  Controle: o resto do e-mail não pode ter sido derrubado junto
# ══════════════════════════════════════════════════════════════════════════
def test_o_email_continua_montando_o_bloco_de_diagnostico():
    src = _main()
    assert "Como lemos o seu projeto" in src
    assert "_hd.escape(w)" in src, "sumiu o escape de HTML dos avisos"
