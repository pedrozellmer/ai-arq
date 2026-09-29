# -*- coding: utf-8 -*-
"""O aviso "é o SÍMBOLO da legenda" fala do bloco de onde veio o NÚMERO.

🩸 29/09/2026. A regra procurava QUALQUER bloco citado na observação com a
contagem igual à quantidade — e a IA cita outros blocos de passagem:
  - pulsador (job 7939350d): "Fonte: 4 INSERTs do bloco 'PULSADOR DE
    CAMPAINHA' − 2 […] = 2 un. Confirmar se há campainha associada (bloco
    'CAMPAINHA PAREDE' …)" → o aviso disse que as 2 eram o símbolo da
    legenda, com o bloco da campainha;
  - botoeira (ev6ad4b5): "Fonte: 1 INSERT do bloco 'BOTOEIRA' […] Verificar se
    é botoeira de interfone…" → casou o bloco 'INTERFONE';
  - câmera (3 projetos): "Fonte: 1 INSERT do bloco 'CÂMERAS 360°'. […] Bloco
    'CAMERA CFTV' (1 INSERT) é flagado como símbolo de legenda e não foi
    contabilizado" → a IA já tinha tirado a da legenda, e o aviso acusou.
(Textos das observações reescritos a partir dos do banco; nomes de bloco
genéricos.)
"""
import ast
import io
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import engine_rules as er  # noqa: E402

PULSADOR = ("Fonte: 4 INSERTs do bloco 'PULSADOR DE CAMPAINHA' − 2 ocorrências identificadas "
            "na legenda = 2 un. Confirmar se há campainha associada (bloco 'CAMPAINHA PAREDE' "
            "resultou em 0 peças após desconto de legenda).")
BOTOEIRA = ("Fonte: 1 INSERT do bloco 'BOTOEIRA' (CONTAGEM DE BLOCOS). Texto FOR-TXT: "
            "'controle acesso'. Verificar se é botoeira de interfone ou controle de acesso.")
CAMERA = ("Fonte: 1 INSERT do bloco 'CÂMERAS 360°'. Sem flag de símbolo de legenda — "
          "quantidade real. Bloco 'CAMERA CFTV' (1 INSERT) é flagado como símbolo de "
          "legenda e não foi contabilizado.")

#: {nome: (contagem, amostras de legenda)} — só os blocos com amostra
AMOSTRAS = {"PULSADOR DE CAMPAINHA": (4, 2), "CAMPAINHA PAREDE": (2, 2),
            "INTERFONE": (1, 1), "CAMERA CFTV": (1, 1)}
#: todos os blocos da extração ({nome: contagem})
BLOCOS = {"PULSADOR DE CAMPAINHA": 4, "CAMPAINHA PAREDE": 2, "INTERFONE": 1,
          "CAMERA CFTV": 1, "BOTOEIRA": 1, "CÂMERAS 360°": 1, "TOMADA": 9}


# ══════════════════════════════════════════════════════════════════════════
#  1. Os três casos
# ══════════════════════════════════════════════════════════════════════════
def test_o_pulsador_e_CONTA_do_proprio_bloco_nao_legenda_da_campainha():
    conf, nova, mexeu = er.selo_apos_amostra_de_legenda(
        "confirmado", PULSADOR, 2, "un", AMOSTRAS, BLOCOS)
    assert (conf, mexeu) == ("estimado", True)
    assert nova.startswith("⚠ Conta, não leitura: 4 inserções menos 2 da LEGENDA — a legenda "
                           "pode ter outros símbolos que o motor não achou (bloco "
                           "'PULSADOR DE CAMPAINHA'). "), nova
    assert "SÍMBOLO desenhado" not in nova


@pytest.mark.parametrize("obs, qtd", [(BOTOEIRA, 1), (CAMERA, 1)])
def test_a_contagem_de_bloco_SEM_amostra_nao_ganha_aviso_de_outro_bloco(obs, qtd):
    assert er.selo_apos_amostra_de_legenda(
        "confirmado", obs, qtd, "un", AMOSTRAS, BLOCOS) == ("confirmado", obs, False)


def test_a_CONTA_tambem_so_vale_pro_bloco_fonte():
    """O aviso "Conta, não leitura" (M − N = quantidade) tem a mesma régua: 4 − 2
    do pulsador citado de passagem não é a conta da botoeira."""
    obs = ("Fonte: 2 INSERTs do bloco 'BOTOEIRA'. O pulsador (bloco 'PULSADOR DE "
           "CAMPAINHA') tem 2 na legenda.")
    blocos = dict(BLOCOS, BOTOEIRA=2)
    assert er.selo_apos_amostra_de_legenda(
        "confirmado", obs, 2, "un", AMOSTRAS, blocos) == ("confirmado", obs, False)


def test_a_fonte_se_acha_na_lista_de_TODOS_os_blocos():
    """🔑 Com a lista só dos blocos com amostra, 'CÂMERAS 360°' não aparece e a
    1ª citação vira a da 'CAMERA CFTV' — o erro de volta."""
    assert er.bloco_fonte_da_linha(CAMERA, BLOCOS) == "CÂMERAS 360°"
    assert er.bloco_fonte_da_linha(CAMERA, AMOSTRAS) == "CAMERA CFTV"


# ══════════════════════════════════════════════════════════════════════════
#  2. A régua da fonte
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("obs, esperado", [
    (PULSADOR, "PULSADOR DE CAMPAINHA"),
    (BOTOEIRA, "BOTOEIRA"),
    # o bloco antes de "Fonte:" é comentário; vale o de depois
    ("Não confundir com o bloco 'INTERFONE'. Fonte: 1 INSERT do bloco 'BOTOEIRA'.", "BOTOEIRA"),
    # "Fonte:" sem bloco depois: vale o primeiro do texto
    ("Bloco 'INTERFONE' = 1. Fonte: CONTAGEM DE BLOCOS.", "INTERFONE"),
    # sem "Fonte:": o primeiro do texto
    ("1 INSERT do bloco 'BOTOEIRA'; ver também o INTERFONE.", "BOTOEIRA"),
    ("fonte: bloco 'botoeira' = 1", "BOTOEIRA"),
    ("Fonte: layer ELE-TXT, sem bloco.", ""),
    ("", ""),
])
def test_bloco_fonte_da_linha(obs, esperado):
    assert er.bloco_fonte_da_linha(obs, BLOCOS) == esperado


def test_nome_dentro_de_nome_no_mesmo_lugar_vale_o_mais_longo():
    blocos = {"TOMADA": 5, "TOMADA BAIXA": 5}
    obs = "Fonte: 5 INSERTs do bloco 'TOMADA BAIXA'."
    assert er.bloco_fonte_da_linha(obs, blocos) == "TOMADA BAIXA"
    assert er.selo_apos_amostra_de_legenda(
        "confirmado", obs, 5, "un", {"TOMADA": (5, 5)}, blocos) == ("confirmado", obs, False)
    assert er.selo_apos_amostra_de_legenda(
        "confirmado", obs, 5, "un", {"TOMADA BAIXA": (5, 2)}, blocos)[2] is True


def test_nome_colado_em_outra_palavra_nao_e_citacao():
    """'INTERFONES' e 'INTERFONE-2' não são o bloco 'INTERFONE'."""
    assert er.bloco_fonte_da_linha("Fonte: INTERFONES e INTERFONE-2.", BLOCOS) == ""


# ══════════════════════════════════════════════════════════════════════════
#  3. CONTROLES — o aviso certo continua saindo
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_a_fonte_com_amostra_continua_rebaixando_mesmo_citando_outro_depois():
    obs = ("Fonte: 2 INSERTs do bloco 'CAMPAINHA PAREDE'. O pulsador (bloco "
           "'PULSADOR DE CAMPAINHA') fica em outra linha.")
    conf, nova, mexeu = er.selo_apos_amostra_de_legenda(
        "confirmado", obs, 2, "un", AMOSTRAS, BLOCOS)
    assert (conf, mexeu) == ("estimado", True)
    assert "na planta: nenhuma (bloco 'CAMPAINHA PAREDE')" in nova


def test_CONTROLE_blocos_vazio_ainda_acha_a_fonte_entre_os_com_amostra():
    obs = "Fonte: 1 INSERT do bloco 'INTERFONE'."
    assert er.selo_apos_amostra_de_legenda(
        "confirmado", obs, 1, "un", AMOSTRAS, {})[2] is True


def test_o_bloco_de_anotacao_so_tira_a_linha_quando_e_a_FONTE():
    """A saída da linha de anotação (WN/C-REV) apaga: casar a marca de fiação
    citada de passagem com o mesmo número tirava a linha das tomadas."""
    anot = {"WN": 9}
    passagem = "Fonte: 9 INSERTs do bloco 'TOMADA'. As marcas 'WN' (9) indicam a fiação."
    assert er.contagem_de_bloco_citada(passagem, 9, "un", anot, todos=BLOCOS) == ""
    fonte = "Fonte: 9 INSERTs do bloco 'WN'."
    assert er.contagem_de_bloco_citada(fonte, 9, "un", anot, todos=BLOCOS) == "WN"
    # sem `todos`, a regra antiga (a trava da anotação de LAYER usa assim)
    assert er.contagem_de_bloco_citada(passagem, 9, "un", anot) == "WN"


# ══════════════════════════════════════════════════════════════════════════
#  4. O MOTOR passa todos os blocos às duas regras
# ══════════════════════════════════════════════════════════════════════════
def _process_job():
    arv = ast.parse(io.open(os.path.join(os.path.dirname(_AQUI), "main.py"),
                            encoding="utf-8").read())
    return next(n for n in ast.walk(arv)
                if isinstance(n, ast.FunctionDef) and n.name == "process_job")


def test_a_saida_da_anotacao_recebe_todos_os_blocos():
    fn = _process_job()
    ch = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
          and getattr(n.func, "id", "") == "_contagem_de_bloco_citada"
          and any(getattr(a, "id", "") == "_blocos_anotacao" for a in n.args)]
    assert len(ch) == 1
    kw = {k.arg: getattr(k.value, "id", None) for k in ch[0].keywords}
    assert kw.get("todos") == "_blocos_n", kw
