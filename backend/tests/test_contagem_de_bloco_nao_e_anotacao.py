# -*- coding: utf-8 -*-
"""A contagem que veio do BLOCO não é rebaixada por citar um layer de texto.

🩸 24/09/2026, filhote ev900daf (job 09e2e640). A IA escreveu: "bloco P70,
72 un, bbox ~1.35m×1.33m. Texto layer TEXTO-02 confirma '0,70 x 2,10'". O
número é do bloco (a extração contou 72 P70); o layer de texto só confirmou a
especificação. A trava "LAYER DE ANOTAÇÃO NÃO É OBRA" olha só os LAYERS
citados — o único era TEXTO-02 — e rebaixou 72/57/34 portas certas.
Em 90 dias: 39 linhas de contagem citando bloco, em 10 projetos.

🔑 A saída NÃO é a palavra "bloco": é o par nome-do-bloco-contado +
quantidade IGUAL à contagem da extração.
"""
import ast
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

from engine_rules import contagem_de_bloco_citada as prova  # noqa: E402

BLOCOS = {"P70": 72, "P80": 57, "P90": 34, "CAMA80": 32, "E": 72}
OBS_P70 = ("Fonte: seção ESQUADRIAS — bloco P70, 72 un, bbox ~1.35m×1.33m. "
           "Texto layer TEXTO-02 confirma '0,70 x 2,10', 'DE ABRIR'.")


def test_o_caso_real_a_porta_P70_tem_prova_no_bloco():
    assert prova(OBS_P70, 72, "un", BLOCOS) == "P70"


@pytest.mark.parametrize("obs, q, unit", [
    ("Fonte: 57 INSERTs do bloco 'P80'.", 57, "un"),
    ("bloco cama80 contado: 32", 32.0, "pç"),
])
def test_outras_formas_de_citar_o_bloco(obs, q, unit):
    assert prova(obs, q, unit, BLOCOS)


# ── controles: o que NÃO livra da trava ─────────────────────────────────────
def test_CONTROLE_numero_diferente_da_contagem_nao_prova():
    """72 é do P70; a linha diz 80 — a IA pode ter somado/estimado."""
    assert prova(OBS_P70, 80, "un", BLOCOS) == ""


def test_CONTROLE_bloco_que_a_extracao_NAO_contou_nao_prova():
    assert prova("bloco P120, 72 un", 72, "un", BLOCOS) == ""


def test_CONTROLE_sem_a_palavra_bloco_nao_prova():
    """Só citar 'P70' num texto de legenda não diz que o número veio do bloco."""
    assert prova("Texto layer TEXTO-02: P70 aparece 72 vezes", 72, "un", BLOCOS) == ""


@pytest.mark.parametrize("unit", ["m", "m²", "ml", "kg", "vb"])
def test_CONTROLE_so_vale_pra_CONTAGEM(unit):
    assert prova(OBS_P70, 72, unit, BLOCOS) == ""


def test_CONTROLE_nome_de_bloco_curto_nao_casa_por_acaso():
    """Bloco 'E' com 72 não pode casar com a letra 'e' da frase."""
    assert prova("bloco de porta e janela, 72 un", 72, "un", {"E": 72}) == ""


def test_CONTROLE_nome_por_prefixo_nao_casa():
    """'P70' não pode casar dentro de 'P700'."""
    assert prova("bloco P700, 72 un", 72, "un", {"P70": 72}) == ""


@pytest.mark.parametrize("q", [0, -1, 72.5, None, "x"])
def test_CONTROLE_quantidade_que_nao_e_contagem(q):
    assert prova(OBS_P70, q, "un", BLOCOS) == ""


def test_sem_blocos_na_extracao_nao_prova():
    assert prova(OBS_P70, 72, "un", {}) == ""
    assert prova(OBS_P70, 72, "un", None) == ""


# ── a trava de anotação CHAMA a régua, com a contagem da extração ───────────
_MAIN = os.path.join(os.path.dirname(_AQUI), "main.py")


def _fonte():
    with open(_MAIN, encoding="utf-8") as f:
        return f.read()


def test_a_trava_de_anotacao_consulta_a_contagem_de_bloco():
    """Guarda de call site: a régua pode estar certa e nunca ser chamada."""
    achou = False
    for n in ast.walk(ast.parse(_fonte())):
        if not isinstance(n, ast.If):
            continue
        chamadas = {getattr(c.func, "id", None) for c in ast.walk(n.test)
                    if isinstance(c, ast.Call)}
        if "_layer_is_anotacao" in chamadas and "_contagem_de_bloco_citada" in chamadas:
            nomes = {x.id for x in ast.walk(n.test) if isinstance(x, ast.Name)}
            assert "_blocos_n" in nomes, "a régua tem que receber a contagem da extração"
            achou = True
    assert achou, "a trava de anotação não consulta a contagem de bloco"


def test_a_contagem_vem_da_extracao_e_nao_de_outro_lugar():
    fonte = _fonte()
    assert "_blocos_n = extraction.get_block_summary()" in fonte
