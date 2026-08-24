# -*- coding: utf-8 -*-
"""Os avisos que o cliente lê no topo do projeto não podem se contradizer.

🚨 Caso Karlla (24/08/2026, job 503fe0d7). Ela recebeu, um embaixo do outro:

    ⚠ "nenhuma quantidade foi medida da geometria"
    ✅ "Escala conferida pelo próprio desenho — 304 cotas batem COM A GEOMETRIA"

Do ponto de vista dela: "vocês conferiram a escala contra a geometria e não
mediram nada dela?". A pergunta é justa, e a contradição é real — provar a
escala e atribuir a medida a um item são passos diferentes, e o motor para no
segundo (mesmo gargalo do caso Eng. Silveira, 14/08).

Esconder o ✅ seria pior: a conferência aconteceu e é informação verdadeira. O
conserto é o ✅ dizer onde a gente parou.
"""
import io
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)


def _fn():
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("def _linhas_escala_projeto(")
    j = src.index("\ndef ", i + 10)
    ns = {"__name__": "escala_ns"}
    exec(compile(src[i:j], "main_slice", "exec"), ns)
    return ns["_linhas_escala_projeto"]


def _provada(n=304):
    return [{"nome": "PLANTA", "status": "cotas", "n": n, "unidade": "metros"}]


def test_escala_provada_sem_medicao_explica_o_buraco():
    linhas = _fn()(_provada(), n_medidos=0)
    txt = " ".join(linhas)
    assert "Escala conferida" in txt
    assert "NENHUM item" in txt, (
        "o ✅ saiu sozinho num projeto que não mediu nada — foi o que a Karlla leu:\n"
        + txt)
    assert "outro" in txt.lower() or "outra" in txt.lower(), (
        "não explica que saber a escala e medir são passos diferentes")


def test_escala_provada_COM_medicao_nao_ganha_ressalva():
    """Controle negativo: num projeto que mediu, o ✅ é só ✅."""
    txt = " ".join(_fn()(_provada(), n_medidos=27))
    assert "Escala conferida" in txt
    assert "NENHUM item" not in txt, "poluiu o aviso de um projeto que mediu bem"


def test_quando_nao_da_pra_saber_nao_afirma_nada():
    """`n_medidos = -1` significa 'não consegui contar'. Nesse caso o aviso não
    pode afirmar nem que mediu nem que não mediu."""
    txt = " ".join(_fn()(_provada(), n_medidos=-1))
    assert "Escala conferida" in txt
    assert "NENHUM item" not in txt


def test_o_padrao_continua_sendo_nao_afirmar():
    """Chamada antiga, sem o parâmetro, não pode virar acusação."""
    txt = " ".join(_fn()(_provada()))
    assert "NENHUM item" not in txt


def test_o_controle_prova_que_o_caso_da_karlla_seria_reprovado():
    """Controle positivo: a combinação exata que ela viu."""
    linhas = _fn()(_provada(304), n_medidos=0)
    assert linhas, "sem linha nenhuma não dá pra testar"
    ressalva = [l for l in linhas if "NENHUM item" in l]
    assert ressalva, "o aviso que ela leu voltaria a sair sozinho"
    assert "304 cotas batem" in ressalva[0], (
        "a ressalva perdeu o dado concreto que dá credibilidade ao aviso")
