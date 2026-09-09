# -*- coding: utf-8 -*-
"""Item não some da planilha sem rastro — e "mesma peça" só vale na MESMA prancha.

🩸 09/09/2026, job 43c52488 (pórtico, 3 DWG). As pranchas renderam **35 + 23 =
58 itens** e a planilha saiu com **53**. Os cinco que sumiram não eram
atribuíveis a ninguém: entre `motor:prancha-itens` e `motor:consolida-tipo`
rodam CINCO removedores e **só um gravava no banco** — os outros deixavam
`print()`, que o Render descarta.

🪤 E o log que existia enganava: `motor:consolida-tipo` dizia `fundidos=0
grupos=0`, o que parece "nada foi fundido". Ele mede só
`_consolidate_by_type_code`, que exige código de divisória (DRY/DW/DIV/PAR/PV)
— um pórtico não tem nenhum, então zero era o resultado CORRETO daquele passo e
péssimo como evidência dos outros quatro.

🩸 O outro defeito: `_dedupe_by_block` agrupava só por nome do bloco, sem olhar
a PRANCHA, rodava DEPOIS da passada 6 do consolidador e usava `max()`. Ou seja,
desfazia num arquivo ao lado a decisão que a passada 6 tinha tomado em 06/09 —
*não fundir entre pranchas, manter as duas linhas e avisar* — e ainda escrevia
na observação **"mesma peça do CAD"**, afirmação que ela não tinha como provar.
No job real, 'Pilar metálico' tinha 4 INSERTs numa prancha e 7 na outra.

🔑 A razão da política de 06/09, que este arquivo protege:
    duplicar é um erro que o arquiteto VÊ; apagar é um erro que ele NÃO vê.
"""
import ast
import io
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import main as m  # noqa: E402


class _It:
    def __init__(s, desc, prancha, qty, conf="estimado"):
        s.description, s.ref_sheet, s.quantity = desc, prancha, qty
        s.confidence, s.observations = conf, ""
        s.unit, s.discipline, s.item_num = "un", "Complementares", "1"


def _dedupe(itens):
    fora, _n = m._dedupe_by_block(itens)
    return fora


# ══════════════════════════════════════════════════════════════════════════
#  🔑 Mesma prancha funde; pranchas diferentes NÃO
# ══════════════════════════════════════════════════════════════════════════
def test_mesmo_bloco_em_PRANCHAS_DIFERENTES_nao_e_fundido():
    """🩸 O defeito em pessoa: 4 pilares numa prancha e 7 na outra viravam uma
    linha de 7, e a leitura da primeira sumia — com o cliente lendo uma frase
    afirmando que era a mesma peça."""
    itens = [_It("Pilar metálico — bloco 'PIL-MET'", "PTC-101", 4),
             _It("Pilar metálico — bloco 'PIL-MET'", "PTC-102", 7)]
    fora = _dedupe(itens)
    assert len(fora) == 2, (
        "o dedup fundiu entre pranchas e apagou uma leitura: %s"
        % [(i.ref_sheet, i.quantity) for i in fora])
    assert sorted(i.quantity for i in fora) == [4, 7]


def test_CONTROLE_mesmo_bloco_na_MESMA_prancha_continua_fundindo():
    """🧪 O caso que criou a função (a IA cria o mesmo bloco em 2-3
    disciplinas: 14 viravam 28). Sem este controle, "não fundir nunca" passaria
    no teste acima e a contagem voltaria a inflar."""
    itens = [_It("Cadeira para escritório — bloco 'cad-escr-02'", "P-01", 14),
             _It("Mobiliário de escritório — bloco 'cad-escr-02'", "P-01", 14)]
    fora = _dedupe(itens)
    assert len(fora) == 1, "o mesmo bloco na mesma prancha voltou a duplicar"
    assert fora[0].quantity == 14, "usou soma em vez de max: %s" % fora[0].quantity
    assert "MESMA PRANCHA" in fora[0].observations, (
        "a observação ainda afirma 'mesma peça' sem dizer que é da mesma "
        "prancha: %r" % fora[0].observations)


def test_o_dedup_devolve_QUANTO_descartou():
    """🔑 Sem o número, o descarte não tem como virar log — foi assim que 5
    itens sumiram sem dono."""
    itens = [_It("X — bloco 'B1'", "P-01", 3),
             _It("Y — bloco 'B1'", "P-01", 5),
             _It("Z — bloco 'B2'", "P-01", 1)]
    fora, n = m._dedupe_by_block(itens)
    assert n == 1, n
    assert len(fora) == 2


def test_bloco_sem_prancha_nao_funde_com_bloco_COM_prancha():
    """🪤 `ref_sheet` vazio é 'não sei de onde veio' — não é prova de que é a
    mesma prancha. Fundir aí seria inventar a informação que falta."""
    itens = [_It("W — bloco 'B9'", "", 2),
             _It("W — bloco 'B9'", "P-07", 6)]
    assert len(_dedupe(itens)) == 2


# ══════════════════════════════════════════════════════════════════════════
#  🔑 O que sai da planilha vira LINHA NO BANCO, não print
# ══════════════════════════════════════════════════════════════════════════
def test_a_remocao_de_itens_e_REGISTRADA_no_banco():
    """🪤 Ancorado na AST: procuro a chamada de `_log_error` com o stage novo.
    `print` não é rastro — ninguém lê o stdout do Render depois.

    🔑 E o registro tem que dizer QUANTO cada passo tirou. Um total sozinho
    responde "sumiu gente" e não responde "quem levou".
    """
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    achou = []
    for n in ast.walk(ast.parse(fonte)):
        if not isinstance(n, ast.Call):
            continue
        if (getattr(n.func, "id", None) or getattr(n.func, "attr", None)) != "_log_error":
            continue
        if n.args and isinstance(n.args[0], ast.Constant) \
                and n.args[0].value == "motor:itens-removidos":
            achou.append(n)
    assert achou, (
        "não existe `_log_error('motor:itens-removidos', ...)` — a remoção de "
        "item voltou a ser silenciosa, e foi assim que 5 itens sumiram do job "
        "43c52488 sem dono")
    texto = " ".join(
        x.value for no in achou for x in ast.walk(no)
        if isinstance(x, ast.Constant) and isinstance(x.value, str))
    for passo in ("consolidacao", "bloco", "sem-sentido"):
        assert passo in texto, (
            "o registro não separa o passo %r — sem isso o log diz que sumiu "
            "gente e não diz quem levou" % passo)


def test_CONTROLE_o_detector_do_log_reprova_um_stage_diferente():
    """🧪 Prova que o predicado acima não passaria com qualquer `_log_error`."""
    fonte = "_log_error('motor:outra-coisa', 'x', job_id)\n"
    achou = [n for n in ast.walk(ast.parse(fonte)) if isinstance(n, ast.Call)
             and (getattr(n.func, "id", None) or getattr(n.func, "attr", None)) == "_log_error"
             and n.args and isinstance(n.args[0], ast.Constant)
             and n.args[0].value == "motor:itens-removidos"]
    assert not achou
