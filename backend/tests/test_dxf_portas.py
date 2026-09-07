# -*- coding: utf-8 -*-
"""Toda porta que abre DXF tem que escolher um lado — conscientemente.

🚨 24/08/2026. Em 23/08 eu consertei o KeyError de layout do caso cliente-19 no
`dwg_extractor` e dei o caso por encerrado. No dia seguinte, o log do MESMO
cliente, no MESMO job:

    [dxf_render] Erro ao abrir 4366-LO-E_libredwg.dxf: 'LAYOUT'

O mesmo bug, pela segunda porta. O backend abre DXF em vários lugares e eu
tinha consertado UM. "Consertado" virou uma frase sobre um arquivo, não sobre
o produto.

Este guarda existe pra que a porta nº 7 não abra calada: qualquer `ezdxf.readfile`
novo, em arquivo fora da lista abaixo, reprova o teste. Quem adicionar escolhe:
usa `dxf_open.abrir_dxf` (com rede) ou entra na lista com o motivo escrito.
"""
import ast
import io
import os

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quem pode chamar `ezdxf.readfile` cru — e POR QUÊ.
_PORTAS_DELIBERADAS = {
    "dxf_open.py":
        "é a implementação: readfile e, se falhar, ezdxf.recover",
    "dwg_extractor.py":
        "laço de encodings do extrator; cai em dxf_open.recuperar_dxf se falhar",
    "main.py":
        "diagnóstico de conversor: o 'abre no ezdxf CRU' É a medição — pôr "
        "recover aqui cegaria a comparação entre libredwg e ODA",
}

# Estas duas regrediram em 24/08. Não podem voltar a abrir DXF na mão.
_PROIBIDAS = ("dxf_render.py", "dxf_rooms_shadow.py")


def _chamadas_cruas(src: str) -> int:
    """Conta `ezdxf.readfile(...)` de VERDADE — via AST, então comentário e
    docstring não contam (o pricing.py cita a função num texto)."""
    n = 0
    for no in ast.walk(ast.parse(src)):
        if not isinstance(no, ast.Call):
            continue
        f = no.func
        if (isinstance(f, ast.Attribute) and f.attr == "readfile"
                and isinstance(f.value, ast.Name) and f.value.id == "ezdxf"):
            n += 1
    return n


def _varrer():
    achados = {}
    for nome in sorted(os.listdir(_BACKEND)):
        if not nome.endswith(".py"):
            continue
        try:
            src = io.open(os.path.join(_BACKEND, nome), encoding="utf-8").read()
            n = _chamadas_cruas(src)
        except SyntaxError:
            continue
        if n:
            achados[nome] = n
    return achados


# ══════════════════════════════════════════════════════════════════════════
#  🧪 O guarda tem que provar que REPROVA antes de eu confiar nele
# ══════════════════════════════════════════════════════════════════════════
def test_controle_positivo_o_detector_enxerga_porta_nova():
    """Se este teste passa mas o detector é cego, o guarda inteiro é enfeite."""
    assert _chamadas_cruas("import ezdxf\ndoc = ezdxf.readfile(p)\n") == 1


def test_controle_negativo_nao_confunde_comentario_com_chamada():
    """`pricing.py` CITA a função num texto. Contar isso daria alarme falso e
    eu acabaria afrouxando o guarda pra calar o ruído."""
    assert _chamadas_cruas('"""usa `ezdxf.readfile()` e expande tudo"""\n') == 0
    assert _chamadas_cruas("# doc = ezdxf.readfile(p)\n") == 0


def test_controle_negativo_recover_nao_conta_como_porta_crua():
    assert _chamadas_cruas("import ezdxf.recover\nd,a = ezdxf.recover.readfile(p)\n") == 0


# ══════════════════════════════════════════════════════════════════════════
#  O guarda de verdade
# ══════════════════════════════════════════════════════════════════════════
def _portas_cruas(src: str) -> int:
    """`ezdxf.readfile(...)` E `from ezdxf import readfile as X; X(...)`.

    🪤 A 1ª versão só via o ATRIBUTO `ezdxf.readfile`. Trocar por um
    `from ezdxf import readfile as _rf` deixava a porta invisível — mesmo
    defeito, apelido novo. Comentário e docstring continuam não contando
    (é AST, não texto).
    """
    import ast
    n = 0
    apelidos = set()
    arvore = ast.parse(src)
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and no.module == "ezdxf":
            for a in no.names:
                if a.name == "readfile":
                    apelidos.add(a.asname or a.name)
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        f = no.func
        if (isinstance(f, ast.Attribute) and f.attr == "readfile"
                and isinstance(f.value, ast.Name) and f.value.id == "ezdxf"):
            n += 1
        elif isinstance(f, ast.Name) and f.id in apelidos:
            n += 1
    return n


def test_CONTROLE_o_detector_ve_a_porta_com_APELIDO():
    """🧪 Sem este controle o detector volta a ser cego pro apelido."""
    assert _portas_cruas("import ezdxf\ndoc = ezdxf.readfile(p)\n") == 1
    assert _portas_cruas("from ezdxf import readfile as _rf\ndoc = _rf(p)\n") == 1
    assert _portas_cruas("# doc = ezdxf.readfile(p)\n") == 0
    assert _portas_cruas("import ezdxf.recover\nd,a = ezdxf.recover.readfile(p)\n") == 0


def test_nenhuma_porta_nova_abriu_calada():
    import io, os
    achados = {}
    for nome in sorted(os.listdir(_BACKEND)):
        if not nome.endswith(".py"):
            continue
        try:
            n = _portas_cruas(io.open(os.path.join(_BACKEND, nome),
                                      encoding="utf-8").read())
        except SyntaxError:
            continue
        if n:
            achados[nome] = n
    novas = sorted(set(achados) - set(_PORTAS_DELIBERADAS))
    assert not novas, (
        "estes arquivos abrem DXF na mão e não estão na lista consciente: %s.\n"
        "Use `from dxf_open import abrir_dxf` (tem o recover embaixo) ou "
        "acrescente o arquivo a _PORTAS_DELIBERADAS explicando por quê." % novas)


@pytest.mark.parametrize("nome", _PROIBIDAS)
def test_as_duas_que_regrediram_nao_voltam(nome):
    """🚨 O preview do cliente-19 morreu em dxf_render.py com o mesmo KeyError que eu
    já tinha consertado. Regressão aqui é a falha se repetindo, não uma nova."""
    caminho = os.path.join(_BACKEND, nome)
    src = io.open(caminho, encoding="utf-8").read()
    assert _chamadas_cruas(src) == 0, (
        "%s voltou a abrir DXF sem rede — foi exatamente assim que a prancha "
        "do cliente-19 perdeu o preview" % nome)
    assert "dxf_open" in src, "%s não usa o abridor com recover" % nome


def test_a_lista_deliberada_nao_incha_sem_querer():
    """Se um dia a lista virar 'todo mundo', o guarda deixou de guardar."""
    assert len(_PORTAS_DELIBERADAS) <= 4, (
        "a lista de exceções cresceu — cada item aí é uma porta sem rede")


# ══════════════════════════════════════════════════════════════════════════
#  E o abridor precisa realmente salvar a prancha
# ══════════════════════════════════════════════════════════════════════════
ezdxf = pytest.importorskip("ezdxf")


@pytest.fixture
def dxf_valido(tmp_path):
    doc = ezdxf.new("R2010")
    doc.modelspace().add_line((0, 0), (10, 0), dxfattribs={"layer": "A-WALL"})
    caminho = str(tmp_path / "ok.dxf")
    doc.saveas(caminho)
    return caminho


def test_controle_o_arquivo_bom_abre_pelo_caminho_normal(dxf_valido, capsys):
    import sys
    sys.path.insert(0, _BACKEND)
    from dxf_open import abrir_dxf
    assert abrir_dxf(dxf_valido) is not None
    assert "recover" not in capsys.readouterr().out.lower(), (
        "passou pelo recover num arquivo são — o teste abaixo não provaria nada")


@pytest.mark.parametrize("nome_layout", ["DO", "LAYOUT", "00-Ã\x8dNDICE DO PROJETO"])
def test_abrir_dxf_recupera_o_keyerror_do_caso_alan(
        nome_layout, dxf_valido, monkeypatch, capsys):
    """Reproduz os três KeyError reais do job e1c48ed7.

    🪤 Os três vieram do MESMO cliente e só UM tem acento — por isso o teste
    não pode ancorar em acento, e sim na CLASSE do erro."""
    import sys
    sys.path.insert(0, _BACKEND)
    import dxf_open

    def _morre(*a, **kw):
        raise KeyError(nome_layout)

    monkeypatch.setattr(dxf_open.ezdxf, "readfile", _morre)
    doc = dxf_open.abrir_dxf(dxf_valido)
    assert doc is not None, "a prancha morreu — é o caso cliente-19 de novo"
    assert "recover" in capsys.readouterr().out.lower()
