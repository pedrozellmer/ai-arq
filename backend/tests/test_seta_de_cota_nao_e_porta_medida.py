# -*- coding: utf-8 -*-
"""Ponta de seta de cota do AutoCAD não pode sair com selo de MEDIDO.

🩸 14/09/2026 — MEDIDO na base: **7 linhas em 5 projetos de cliente, 5 delas
`confirmado`, 40 unidades** entregues como MEDIDAS do CAD — de 17/07 até o dia
em que isto foi escrito. Num projeto, dois itens sozinhos eram **52,6% de tudo
que a planilha vendia como medido**:

  · "Pontos de conexão / sprinklers / derivações — bloco _DOT"      17 un ✓
  · "Esquadrias gerais — bloco _Open90 (portas com abertura 90°)"   13 un ✓

🔑 `_DOT` e `_OPEN90` NÃO são blocos do projetista: são os nomes reservados que
o próprio AutoCAD instala para as PONTAS DE SETA de cota. A prancha tinha 59
cotas. A CONTAGEM de INSERTs está certa — o que é falso é a IDENTIDADE, e o
selo branco diz ao cliente que aquilo foi medido do projeto dele. Regra dura
nº1: o cliente precifica sprinkler onde havia seta.

🪤 O guarda `item_e_bloco_sem_identidade` já existia e rebaixou 7 itens da mesma
natureza NESTE mesmo job. Os dois maiores escaparam pela FORMA da frase: a
régua exigia que a descrição COMEÇASSE com "Bloco"/"Elemento", e estas começam
pelo substantivo. Ancorar no FATO (o nome é de sistema) em vez da forma.

🚫 A fronteira antiga continua valendo e NÃO foi alargada: "Janela j3 —
conforme bloco 'j3'" tem item real e só falta o tipo. A régua nova é uma lista
FECHADA de nomes de sistema, com fronteira dos dois lados — bloco de projetista
chamado `PORTA_OPEN90` ou `DOT-01` não pode ser pego junto.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine_rules import item_e_bloco_sem_identidade as _sem_ident  # noqa: E402


# ── as linhas que saíram ERRADAS em produção ─────────────────────────────
def test_as_linhas_reais_que_sairam_com_selo_branco_agora_sao_pegas():
    reais = [
        "Porta de abrir 90° — conforme bloco '_OPEN90'",
        "Pontos de conexão / sprinklers / derivações — bloco _DOT "
        "(identificar tipo com legenda da prancha)",
        "Esquadrias gerais — bloco _Open90 (portas com abertura 90°) — "
        "identificar tipo",
        "Marcadores de referência topográfica — bloco _Dot (vértices de lote)",
        "Bloco de referência '_Dot' — 4 inserções identificadas no arquivo DXF",
    ]
    escaparam = [d for d in reais if not _sem_ident(d, "un")]
    assert not escaparam, (
        "linha de produção que vendia seta de cota como item medido continua "
        "escapando: %r" % escaparam)


def test_a_familia_toda_de_pontas_de_seta_do_autocad():
    """São ~20 nomes e o acervo já trouxe 3 deles. Pegar um a um conforme
    aparece é garantir que o próximo cliente pague pelo mesmo defeito."""
    for nome in ("_DOT", "_DOTSMALL", "_DOTBLANK", "_ORIGIN", "_ORIGIN2",
                 "_OPEN", "_OPEN30", "_OPEN90", "_CLOSED", "_CLOSEDBLANK",
                 "_CLOSEDFILLED", "_SMALL", "_NONE", "_OBLIQUE", "_BOXFILLED",
                 "_BOXBLANK", "_DATUMFILLED", "_DATUMBLANK", "_INTEGRAL",
                 "_ARCHTICK"):
        assert _sem_ident("Elemento contado — bloco %s do desenho" % nome, "un"), (
            "ponta de seta %s não foi reconhecida como bloco de sistema" % nome)


def test_minuscula_e_maiuscula_dao_no_mesmo():
    assert _sem_ident("Tomada — bloco _open90 do CAD", "un")
    assert _sem_ident("Tomada — bloco _OPEN90 do CAD", "un")


# ── controles: bloco do PROJETISTA não pode ser levado junto ─────────────
def test_CONTROLE_nome_de_projetista_que_CONTEM_o_termo_nao_e_pego():
    """🪤 A fronteira ESQUERDA: `PORTA_OPEN90` e `DOT-01` são nomes legítimos de
    biblioteca de escritório e não podem ser rebaixados junto."""
    for d in ("Porta de madeira — bloco PORTA_OPEN90 do projeto",
              "Luminária — bloco DOT-01 da legenda",
              "Difusor — conforme bloco 'DOTSMALL2'",
              "Grelha — bloco ARCHTICK2 do fabricante"):
        assert not _sem_ident(d, "un"), (
            "bloco de projetista foi rebaixado por engano: %r" % d)


def test_CONTROLE_nome_que_COMECA_igual_mas_continua_nao_e_pego():
    """🪤 A fronteira DIREITA, e ela não é teórica: `_OPENING` (abertura) e
    `_SMALLPARTS` começam com underscore e contêm um nome de sistema inteiro
    dentro. Sem esta trava, um bloco real do projetista perderia o selo.

    🩸 Este caso nasceu de um mutante SOBREVIVENTE: apagar `(?![A-Za-z0-9_])`
    da régua deixava a bancada verde, porque todo controle que eu tinha escrito
    era barrado antes, pela fronteira esquerda. Guarda que não reprova não
    guarda nada.
    """
    for d in ("Vão de passagem — bloco _OPENING do arquitetônico",
              "Kit de peças — bloco _SMALLPARTS do fabricante",
              "Referência — bloco _DOT2 da prancha",
              "Marcação — bloco _NONE1 do desenho",
              "Detalhe — bloco _ORIGINAL da biblioteca"):
        assert not _sem_ident(d, "un"), (
            "nome de projetista que só COMEÇA como bloco de sistema foi "
            "rebaixado por engano: %r" % d)


def test_CONTROLE_a_fronteira_antiga_continua_de_pe():
    """Estes quatro estavam FORA de propósito, conferidos item a item quando a
    régua antiga foi calibrada. Alargar aqui levaria item legítimo junto."""
    for d in ("Janela j3 — conforme bloco 'j3'",
              "Mobiliário — bloco e48",
              "Portas não identificadas por bloco específico",
              "Difusor/Grelha — conforme bloco do projeto"):
        assert not _sem_ident(d, "un"), (
            "a fronteira calibrada foi alargada sem querer: %r" % d)


def test_CONTROLE_o_que_a_regua_antiga_pegava_continua_pego():
    assert _sem_ident("Bloco 'XPTO' — 12 inserções", "un")
    assert _sem_ident("Elementos de bloco não identificados no layer", "un")


def test_CONTROLE_so_vale_para_unidade_de_CONTAGEM():
    """Em m²/ml "bloco" costuma falar do material, e o item existe."""
    assert not _sem_ident("Piso — bloco _DOT", "m²")
    assert not _sem_ident("Rodapé — bloco _OPEN90", "ml")


def test_CONTROLE_entrada_vazia_nao_quebra():
    assert not _sem_ident(None, "un")
    assert not _sem_ident("", "un")
    assert not _sem_ident("Porta comum sem citar bloco", "un")
    assert not _sem_ident("Bloco 'XPTO'", None)


# ── o motor CHAMA o guarda e REBAIXA (senão a régua nasce morta) ─────────
def test_o_motor_rebaixa_o_selo_e_avisa_o_cliente():
    """🪤 A régua só APONTA — quem rebaixa é o chamador em `main.py`. Sem este
    caso, dava pra apagar o rebaixamento e a bancada seguiria verde."""
    import ast
    import io
    caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "main.py")
    fonte = io.open(caminho, encoding="utf-8").read()
    arv = ast.parse(fonte)

    fn = None
    for n in ast.walk(arv):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in ast.walk(n):
                if (isinstance(d, ast.ImportFrom) and d.module == "engine_rules"
                        and any(a.name == "item_e_bloco_sem_identidade"
                                for a in d.names)):
                    fn = n
                    break
        if fn is not None:
            break
    assert fn is not None, ("ninguém importa `item_e_bloco_sem_identidade` — a "
                            "régua não é usada pelo motor")

    corpo = ast.get_source_segment(fonte, fn) or ""
    assert "ESTIMADO" in corpo, (
        "quem chama a régua não REBAIXA o selo — a seta de cota continua saindo "
        "branca")
    assert "não sabemos o que é" in corpo, (
        "o cliente não é avisado de que a identidade do item não veio do projeto")
