# -*- coding: utf-8 -*-
"""A régua da inversão passa a ler o quadro de áreas TAMBÉM do PDF.

🩸 23/09/2026. O passo 1 da inversão compara o que a GEOMETRIA recortou com o
quadro de áreas que o AUTOR escreveu. Medido no acervo:

| | projetos |
|---|---|
| com recorte de ambientes COM número | 89 |
| com quadro de áreas do autor | 26 |
| **com os dois** | **2** |

🔑 E a causa não era falta de tráfego: os dois lados viviam em POPULAÇÕES
DIFERENTES. A geometria recorta ambiente em **73 projetos por PDF** contra 16
por CAD — e o quadro do autor só era lido dentro do laço de DXF. Havia 73
projetos com metade da comparação pronta e a outra metade nunca extraída.

🪤 Os 2 casos que existiam são do formato ANTIGO do log (sem rótulo), que a
própria `linha_do_quadro_de_areas` diz não servir pra conta nenhuma: sem
rótulo, a lista mistura AMBIENTE com as linhas de TOTAL do quadro. Ou seja,
antes disto aqui a régua tinha ZERO casos válidos.

🚨 Só LEITURA: nada entra no consenso de área, nada muda pro cliente. Inverter
o motor é outra obra — esta régua só monta a comparação que decide se ela pode
começar.

🧪 A régua NÃO é reimplementada: `areas_do_texto_da_prancha_rotuladas` já
recebe uma lista de textos e não sabe de onde vêm. O que faltava era passar o
texto do PDF pra ela.
"""
import ast
import io
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main  # noqa: E402

NL = chr(10)

#: Como planta de arquitetura escreve área: o rótulo "A=" colado no número.
#: É o MESMO texto que existe no DXF — por isso ele sobrevive à exportação
#: pra PDF, e por isso a régua do CAD serve aqui sem mudar uma linha.
_PLANTA = NL.join([
    "SALA DE ESTAR", "A=25,40 m2",
    "COZINHA", "A=12,00 m2",
    "DORMITORIO 1", "A=18,60 m2",
    "AREA CONSTRUIDA = 56,00 m2",
])


def test_o_quadro_do_autor_e_lido_do_texto_do_PDF():
    linha = main.quadro_de_areas_do_texto_do_pdf(_PLANTA, "prancha.pdf", 0)
    assert linha, "a régua não leu o quadro do texto do PDF"
    assert "n=4 candidatos" in linha


def test_o_TOTAL_do_quadro_nao_conta_como_AMBIENTE():
    """🔑 O conserto de 20/09: numa lista plana o pai não pode ser irmão do
    filho. São 3 ambientes (25,40 + 12,00 + 18,60 = 56,00); a linha "ÁREA
    CONSTRUÍDA = 56,00" é o total deles, não um quarto cômodo."""
    linha = main.quadro_de_areas_do_texto_do_pdf(_PLANTA, "prancha.pdf", 0)
    assert "AMBIENTES: n=3" in linha, linha
    assert "soma=56.0" in linha, linha


def test_a_linha_diz_a_PRANCHA_e_a_PAGINA():
    """Sem isso não dá pra cruzar com o recorte, que é por página."""
    linha = main.quadro_de_areas_do_texto_do_pdf(_PLANTA, "prancha.pdf", 4)
    assert "arq=prancha.pdf p.5" in linha, "página 1-based, como o cliente vê"


@pytest.mark.parametrize("texto, porque", [
    ("", "texto vazio"),
    (None, "sem texto"),
    (NL.join(["PLANTA BAIXA", "ESCALA 1:50"]), "prancha sem quadro"),
    (NL.join(["AREA DO TERRENO: 350,00 m2"]), "terreno é o lote, não a obra"),
])
def test_CONTROLE_sem_quadro_a_regua_CALA(texto, porque):
    assert main.quadro_de_areas_do_texto_do_pdf(texto, "p.pdf", 0) == "", porque


def test_LIMITE_CONHECIDO_quadro_em_formato_de_tabela_ainda_nao_e_lido():
    """📌 O regex exige "A"/"ÁREA" colado ao número. Quadro escrito como
    tabela ("SALA ........ 25,40 m²") NÃO é lido — e este guarda existe pra
    isso ficar MEDIDO, não esquecido: se um dia o alcance no acervo vier baixo,
    é aqui que está a explicação, e ampliar o regex é decisão com risco de
    falso positivo (a rede de 24/08 nasceu de número solto virando medida)."""
    tabela = NL.join(["SALA DE ESTAR .......... 25,40 m2",
                      "COZINHA ................ 12,00 m2"])
    assert main.quadro_de_areas_do_texto_do_pdf(tabela, "p.pdf", 0) == ""


# ══════════════════════════════════════════════════════════════════════════
#  A ligação existe, e no lugar certo
#  🪤 A doença da miniatura (17/09): cinco meses de código inalcançável atrás
#     de um docstring que jurava funcionar.
# ══════════════════════════════════════════════════════════════════════════
def _process_job_ast():
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    for no in ast.walk(ast.parse(src)):
        if isinstance(no, ast.FunctionDef) and no.name == "process_job":
            return no
    raise AssertionError("não achei process_job")


def _linhas_de(fn, alvo):
    fora = []
    for no in ast.walk(fn):
        if isinstance(no, ast.Call):
            nome = getattr(no.func, "id", None) or getattr(no.func, "attr", None)
            if nome == alvo:
                fora.append(no.lineno)
    return fora


def test_a_regua_e_CHAMADA_no_laco_das_paginas_de_PDF():
    chamadas = _linhas_de(_process_job_ast(), "quadro_de_areas_do_texto_do_pdf")
    assert len(chamadas) == 1, (
        "esperava UMA chamada da régua no process_job e achei %d" % len(chamadas))


def test_a_regua_roda_ANTES_de_o_texto_da_pagina_ser_DESCARTADO():
    """🔑 `_texto_inteiro` é apagado logo depois de guardar os números (é
    grande e o dyno tem pouca RAM). Chamar a régua depois do `del` seria
    NameError — ou, pior, silêncio se alguém envolvesse num try."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i_regua = src.find("quadro_de_areas_do_texto_do_pdf(" + NL)
    if i_regua < 0:
        i_regua = src.find("_lin_quadro = quadro_de_areas_do_texto_do_pdf(")
    i_del = src.find("del _texto_inteiro")
    assert i_regua > 0 and i_del > 0, "sumiu a régua ou o descarte do texto"
    assert i_regua < i_del, (
        "a régua roda DEPOIS de o texto ser descartado — não lê nada")


def test_CONTROLE_a_regua_do_PDF_e_so_LEITURA():
    """🚨 O escopo autorizado pelo Pedro: "é leitura, não inversão — não muda
    nada pro cliente". Ela não pode entrar no consenso de área."""
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = fonte.find("_lin_quadro = quadro_de_areas_do_texto_do_pdf(")
    assert i > 0
    trecho = fonte[i:i + 900]
    for proibido in ("_reg_area(", "_area_readings", ".quantity", ".confidence"):
        assert proibido not in trecho, (
            "a régua do PDF encostou em %r — ela é só leitura" % proibido)
