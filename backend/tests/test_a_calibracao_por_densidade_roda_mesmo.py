# -*- coding: utf-8 -*-
"""A regra dura nº3 tem que EXECUTAR — ela passou 142 dias pulada em silêncio.

🩸 09/09/2026. O `process_job` lia a área do projeto em duas variáveis:

    laje_area = project_data.total_area or 0                    (plausibilidade)
    ref_area  = project_data.layout_area or ... or 0            (densidade)

e `project_data.total_area` só é ATRIBUÍDA ~400 linhas ABAIXO, no consenso de
área. O campo nasce 0 (`models.py`), e `mesclar_project_data` só empilha em
`_area_readings` — nunca faz setattr. Logo os dois valiam **ZERO em 100% das
execuções**, e duas coisas nunca aconteceram:

  • a regra 3 de `_check_plausibility` ("m² > 1,5× a laje = possível dupla
    contagem") NUNCA disparou — sobrava só o teto genérico de 50.000 m²;
  • a CALIBRAÇÃO POR DENSIDADE, que é a **REGRA DURA Nº3**, NUNCA executou.

📅 O dia exato: commit `65f95d8`, 20/04/2026 — "Consolidator 5-pass + consenso
de área (fim das duplicatas)". Ele tirou duas atribuições que rodavam DENTRO do
laço de pranchas e pôs uma só no fim. O conserto das duplicatas estava CERTO;
ao mover a atribuição, mordeu o vizinho de cima. A leitura tinha nascido em
`e26f63c` (19/04): viveu **um dia**.

🪤 Por que ninguém viu por 142 dias: o `if HAS_DENSITY_CAL and ref_area > 0:`
não tinha `else`. Pulado calado é indistinguível de "rodou e não achou nada".
Ver [[feedback_escrita_que_falha_calada]].

🔑 Este guarda ancora em TRÊS fatos independentes, porque o defeito tinha três
faces: a ORDEM (ler depois de escrever), a RÉGUA (ela reprova mesmo?) e o
RASTRO (a ausência fala?).
"""
import ast
import io
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import main as m  # noqa: E402


def _arvore_main():
    return ast.parse(io.open(os.path.join(_BACKEND, "main.py"),
                             encoding="utf-8").read())


def _linhas_que_escrevem_a_area(arvore):
    """Onde `project_data.total_area` recebe valor."""
    fora = []
    for n in ast.walk(arvore):
        if not isinstance(n, ast.Assign):
            continue
        for alvo in n.targets:
            if (isinstance(alvo, ast.Attribute) and alvo.attr == "total_area"
                    and getattr(alvo.value, "id", None) == "project_data"):
                fora.append(n.lineno)
    return sorted(fora)


def _linhas_que_leem_a_area_pra_rede(arvore):
    """Onde `laje_area`/`ref_area` são calculadas a partir do project_data."""
    fora = []
    for n in ast.walk(arvore):
        if not isinstance(n, ast.Assign):
            continue
        nomes = {getattr(t, "id", None) for t in n.targets}
        if not (nomes & {"laje_area", "ref_area"}):
            continue
        usa_pd = any(getattr(getattr(x, "value", None), "id", None) == "project_data"
                     for x in ast.walk(n) if isinstance(x, ast.Attribute))
        if usa_pd:
            fora.append(n.lineno)
    return sorted(fora)


# ══════════════════════════════════════════════════════════════════════════
#  🔑 FATO 1 — a rede lê DEPOIS de a área existir
# ══════════════════════════════════════════════════════════════════════════
def test_a_rede_de_area_LE_depois_de_a_area_ser_ESCRITA():
    """🩸 O defeito em pessoa: ler na 11552 o que só é escrito na 11949."""
    arv = _arvore_main()
    escrevem = _linhas_que_escrevem_a_area(arv)
    leem = _linhas_que_leem_a_area_pra_rede(arv)
    assert escrevem, "ninguém mais escreve `project_data.total_area`"
    assert leem, "sumiram `laje_area`/`ref_area` — a rede foi removida?"
    assert min(leem) > min(escrevem), (
        "a rede de área lê na linha %d e a área só é escrita na %d — "
        "`ref_area` vale 0 em TODA execução e a regra dura nº3 não roda. "
        "Foi assim por 142 dias." % (min(leem), min(escrevem)))


def test_CONTROLE_o_detector_de_ORDEM_acha_a_inversao_plantada():
    """🧪 Sem isto, um detector que devolvesse listas vazias (nome trocado,
    atributo errado) passaria no guarda acima para sempre."""
    fonte = (
        "def f():\n"
        "    laje_area = project_data.total_area or 0\n"
        "    project_data.total_area = consenso()\n")
    arv = ast.parse(fonte)
    escrevem = _linhas_que_escrevem_a_area(arv)
    leem = _linhas_que_leem_a_area_pra_rede(arv)
    assert escrevem == [3] and leem == [2], (escrevem, leem)
    assert not (min(leem) > min(escrevem)), "o detector não viu a inversão"


# ══════════════════════════════════════════════════════════════════════════
#  🔑 FATO 2 — a régua REPROVA de verdade
# ══════════════════════════════════════════════════════════════════════════
class _Item:
    def __init__(s, qty, unit="m²", disc="Pisos e Rodapés"):
        s.quantity, s.unit, s.discipline = qty, unit, disc
        s.description, s.observations = "piso cerâmico", ""


def test_a_regra_da_DUPLA_CONTAGEM_reprova_quando_ha_laje():
    """🔑 Item de 500 m² num projeto de 100 m² é dupla contagem. Com a área
    valendo 0 — o mundo dos últimos 142 dias — isto passava batido."""
    ok, motivo = m._check_plausibility(_Item(500.0), 100.0)
    assert ok is False, "a rede não pegou 500 m² numa laje de 100 m²"
    assert "dupla contagem" in motivo, motivo


def test_CONTROLE_com_area_ZERO_a_regra_NAO_tem_como_reprovar():
    """🧪 O controle que EXPLICA o defeito: a mesma régua, o mesmo item, e a
    área em 0 — passa. Não é bug da régua; é bug de quem a alimenta. É por isso
    que o FATO 1 (ordem) é o guarda que importa."""
    ok, _motivo = m._check_plausibility(_Item(500.0), 0)
    assert ok is True, (
        "com área 0 a regra 3 não pode opinar — se ela reprova aqui, passou a "
        "chutar sem base")


def test_CONTROLE_item_plausivel_NAO_e_reprovado():
    ok, motivo = m._check_plausibility(_Item(80.0), 100.0)
    assert ok is True, motivo


@pytest.mark.parametrize("qty,laje,esperado", [
    (149.0, 100.0, True),    # 1,49× — dentro
    (151.0, 100.0, False),   # 1,51× — fora
])
def test_o_corte_de_1_ponto_5_esta_onde_diz_estar(qty, laje, esperado):
    """🪤 Constante de corte sem guarda vira lenda. 1,5× é a fronteira."""
    ok, _ = m._check_plausibility(_Item(qty), laje)
    assert ok is esperado


# ══════════════════════════════════════════════════════════════════════════
#  🔑 FATO 3 — quando é PULADA, a ausência fala
# ══════════════════════════════════════════════════════════════════════════
def test_a_calibracao_PULADA_deixa_rastro():
    """🚨 O silêncio foi o que escondeu isto por 142 dias. Um `if` sem `else`
    torna "não rodou" indistinguível de "rodou e não achou nada" — e a segunda
    leitura é a que a gente faz sozinho.

    🔑 Ancorado na AST: procuro o `if` que guarda a calibração e exijo que o
    ramo `else` dele CHAME `_log_error`. Comentário citando `_log_error` não
    faz isto passar.
    """
    arv = _arvore_main()
    alvos = []
    for n in ast.walk(arv):
        if not isinstance(n, ast.If):
            continue
        teste = ast.dump(n.test)
        if "HAS_DENSITY_CAL" in teste and "ref_area" in teste:
            alvos.append(n)
    assert alvos, "sumiu o `if` que guarda a calibração por densidade"
    for no in alvos:
        assert no.orelse, (
            "o `if` da calibração (linha %d) voltou a não ter `else`: quando "
            "ela é pulada, nada é registrado — foi esse silêncio que escondeu "
            "142 dias de regra dura nº3 desligada" % no.lineno)
        registra = [x for x in ast.walk(ast.Module(body=no.orelse, type_ignores=[]))
                    if isinstance(x, ast.Call)
                    and (getattr(x.func, "id", None)
                         or getattr(x.func, "attr", None)) == "_log_error"]
        assert registra, (
            "o `else` da calibração (linha %d) existe mas não grava nada no "
            "error_log — `print` não é rastro: ninguém lê o stdout do Render "
            "depois." % no.lineno)


def test_CONTROLE_o_detector_do_ELSE_reprova_um_if_sem_else():
    """🧪 Prova que o predicado do FATO 3 reprova o mundo anterior."""
    fonte = ("if HAS_DENSITY_CAL and ref_area > 0:\n"
             "    calibrar()\n")
    arv = ast.parse(fonte)
    ifs = [n for n in ast.walk(arv) if isinstance(n, ast.If)
           and "HAS_DENSITY_CAL" in ast.dump(n.test)]
    assert ifs and not ifs[0].orelse, "o detector não viu o `if` sem `else`"


def test_CONTROLE_o_detector_do_ELSE_reprova_else_que_so_faz_print():
    """🧪 O segundo lado: um `else` que só imprime no stdout NÃO é rastro —
    o Render descarta, e a pergunta 'rodou?' continua sem resposta."""
    fonte = ("if HAS_DENSITY_CAL and ref_area > 0:\n"
             "    calibrar()\n"
             "else:\n"
             "    print('pulei')\n")
    arv = ast.parse(fonte)
    no = [n for n in ast.walk(arv) if isinstance(n, ast.If)][0]
    registra = [x for x in ast.walk(ast.Module(body=no.orelse, type_ignores=[]))
                if isinstance(x, ast.Call)
                and (getattr(x.func, "id", None)
                     or getattr(x.func, "attr", None)) == "_log_error"]
    assert not registra, "o predicado aceitou um `else` que só faz print"
