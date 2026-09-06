# -*- coding: utf-8 -*-
"""`S-COLS` é pilar. `AC-Indicação coluna Frigorígenas` NÃO é.

🏗️ 01/09/2026 — arquivo do cliente-23 (RACIONAL), planta de fôrma
`TOP-EST-PE-116-FRM-TIP-R00`: os 54 pilares vivem no layer **`S-COLS`**, que é o
padrão AIA/CAD para pilar estrutural (Structural Columns). O filtro conhecia só
"PILAR" e "COLUMN", e `_has_token` quebra "S-COLS" em ["S","COLS"] — "COLS" não
começa com "COLUMN", então recusava.

🪤 "COLUNA" FOI TESTADO E RECUSADO. O Tiago (METAL-AR) tem o layer
`AC-Indicação coluna Frigorígenas` — coluna frigorígena de ar-condicionado, não
pilar. Aceitar "COLUNA" faria toda prancha de climatização virar candidata a
pilar. O teste abaixo guarda essa decisão pra ninguém "melhorar" o filtro
adicionando COLUNA depois.

⚠️ HONESTIDADE SOBRE O ALCANCE: isto sozinho NÃO destrava o caso do cliente-23. O
detector de pilar só olha polilinha FECHADA e o arquivo dele não tem nenhuma
(2.158 LINE, 448 HATCH, 0 LWPOLYLINE). Medido em 01/09: **210 de 213 pranchas**
da base saem com `pilares=0`. Este conserto é correto por mérito próprio e fica
latente até alguém mandar um S-COLS desenhado com polilinha.
"""
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from structural_extractor import layer_is_pilar  # noqa: E402


def test_o_padrao_AIA_S_COLS_e_pilar():
    """🩸 O layer do cliente-23."""
    for nome in ("S-COLS", "S-COLS-IDEN", "s-cols", "COLS", "A-COLS-STRUCT"):
        assert layer_is_pilar(nome) is True, "recusou layer de pilar: %r" % nome


def test_os_nomes_que_ja_funcionavam_continuam():
    for nome in ("PILAR", "PILARES", "COLUMN", "COLUMNS",
                 "EST-PILAR", "S-COLUMN-IDEN"):
        assert layer_is_pilar(nome) is True, "quebrou nome que já passava: %r" % nome


# ── CONTROLES: o filtro tem que RECUSAR ────────────────────────────────────
def test_CONTROLE_coluna_FRIGORIGENA_nao_e_pilar():
    """🪤 O layer REAL do Tiago. Se este teste falhar, toda prancha de
    climatização passa a ter 'pilar'."""
    for nome in ("AC-Indicação coluna Frigorígenas",
                 "AC-Indicacao coluna Frigorigenas",
                 "COLUNA", "Coluna d'água", "CE-Coluna"):
        assert layer_is_pilar(nome) is False, (
            "'%s' virou layer de pilar — 'COLUNA' não pode entrar na lista" % nome)


def test_CONTROLE_os_layers_reais_do_acervo_continuam_FORA():
    """Nomes colhidos do error_log dos clientes de verdade."""
    reais = ("LAJE", "VIGA", "A-WALL", "S-BEAM-IDEN", "S-STRS", "A-FLOR-IDEN",
             "DT-INS-AC", "EQ-02", "K-LEGEN", "BORDAS ESPESSAS", "Defpoints",
             "Nível 1", "DI-Tabelas", "Markups", "0", "TABELA", "CORTE__",
             "AC-Condutos Exaustão", "ELE-C01", "G-ANNO-TEXT", "A-FLOR-PATT")
    maus = [n for n in reais if layer_is_pilar(n)]
    assert not maus, "esses layers NÃO são de pilar e passaram: %s" % maus


def test_CONTROLE_o_filtro_nao_virou_permissivo():
    """🧪 Se `layer_is_pilar` aceitasse tudo, os testes de cima passariam sem
    provar nada. Aqui ele TEM que recusar."""
    assert layer_is_pilar("") is False
    assert layer_is_pilar(None) is False
    assert layer_is_pilar("QUALQUER COISA") is False
    assert layer_is_pilar("COL") is False, (
        "'COL' sozinho é curto demais — casaria com COLA, COLETOR, COL-01")


def test_CONTROLE_a_lista_de_tokens_e_a_esperada():
    """🪤 Guarda a DECISÃO, não só o comportamento: quem for mexer aqui precisa
    passar por este teste e ler o porquê de COLUNA estar fora."""
    from structural_extractor import _PILAR_TOKENS
    assert set(_PILAR_TOKENS) == {"PILAR", "COLUMN", "COLS"}, (
        "a lista de tokens de pilar mudou para %s — se você adicionou COLUNA, "
        "leia o teste test_CONTROLE_coluna_FRIGORIGENA_nao_e_pilar antes"
        % (_PILAR_TOKENS,))
