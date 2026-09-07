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


def _portas_cruas(src: str) -> int:
    """Toda forma de chamar `ezdxf.readfile` sem a rede embaixo.

    🪤 A 1ª versão só via o ATRIBUTO literal `ezdxf.readfile`. Trocar por um
    `from ezdxf import readfile as _rf` deixava a porta invisível — mesmo
    defeito, apelido novo.
    🪤 06/09/2026: e a 2ª versão só aprendeu ESSE apelido. Continuava cega pra
    `import ezdxf as _ez` (uma linha, e a porta some do radar) e pra
    `getattr(ezdxf, "readfile")` — as duas formas que um refactor de import
    produz sem querer. Agora conta as QUATRO.

    Comentário e docstring continuam não contando: é AST, não texto (o
    `pricing.py` cita a função num parágrafo).
    """
    n = 0
    modulos = {"ezdxf"}      # nomes pelos quais o MÓDULO ezdxf é alcançável
    apelidos = set()         # nomes pelos quais a FUNÇÃO readfile é alcançável
    arvore = ast.parse(src)
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for a in no.names:
                # 🪤 `import ezdxf.recover as _rec` NÃO entra: `_rec.readfile` é
                # o recover, que é exatamente o que a gente QUER que se use.
                if a.name == "ezdxf" and a.asname:
                    modulos.add(a.asname)
        elif isinstance(no, ast.ImportFrom) and no.module == "ezdxf":
            for a in no.names:
                if a.name == "readfile":
                    apelidos.add(a.asname or a.name)
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        f = no.func
        if (isinstance(f, ast.Attribute) and f.attr == "readfile"
                and isinstance(f.value, ast.Name) and f.value.id in modulos):
            n += 1
        elif isinstance(f, ast.Name) and f.id in apelidos:
            n += 1
        elif (isinstance(f, ast.Name) and f.id == "getattr" and len(no.args) >= 2
              and isinstance(no.args[0], ast.Name) and no.args[0].id in modulos
              and isinstance(no.args[1], ast.Constant)
              and no.args[1].value == "readfile"):
            n += 1
    return n


def _chama_o_abridor_com_rede(src: str) -> bool:
    """O arquivo IMPORTA e CHAMA `dxf_open.abrir_dxf`/`recuperar_dxf`?

    🪤 06/09/2026 — o guarda das duas proibidas conferia `"dxf_open" in src`.
    Um import que sobrou de refactor, uma menção em comentário ou o nome do
    módulo dentro de uma mensagem de log satisfazem isso: o arquivo pode ter
    parado de usar a rede e a frase continua lá. Aqui é AST, e é CHAMADA.
    """
    arvore = ast.parse(src)
    nomes = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and no.module == "dxf_open":
            for a in no.names:
                nomes.add(a.asname or a.name)
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        f = no.func
        if isinstance(f, ast.Name) and f.id in nomes:
            return True
        if (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
                and f.value.id == "dxf_open"
                and f.attr in ("abrir_dxf", "recuperar_dxf")):
            return True
    return False


def _todo_py_de_producao(raiz_base=None):
    """Todo .py do backend, RECURSIVO — com o caminho relativo como chave.

    🪤 06/09/2026 — a varredura era `os.listdir(_BACKEND)`: só a RAIZ. Módulo
    novo em qualquer subpasta abriria DXF na mão com o guarda verde, e subpasta
    é justamente onde módulo novo costuma nascer.
    🪤 `tests/` fica de fora de propósito: bancada não é porta de produção — dois
    guardas legítimos daqui chamam `ezdxf.readfile` pra montar cenário.
    """
    base = raiz_base or _BACKEND
    for raiz, dirs, arqs in os.walk(base):
        dirs[:] = [d for d in dirs
                   if d not in ("__pycache__", "tests", "venv", "node_modules")
                   and not d.startswith(".")]
        for nome in sorted(arqs):
            if nome.endswith(".py"):
                caminho = os.path.join(raiz, nome)
                yield os.path.relpath(caminho, base).replace("\\", "/"), caminho


# ══════════════════════════════════════════════════════════════════════════
#  🧪 O guarda tem que provar que REPROVA antes de eu confiar nele
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("fonte,esperado", [
    # as QUATRO formas de abrir a porta
    ("import ezdxf\ndoc = ezdxf.readfile(p)\n", 1),
    ("from ezdxf import readfile as _rf\ndoc = _rf(p)\n", 1),
    ("import ezdxf as _ez\ndoc = _ez.readfile(p)\n", 1),
    ('import ezdxf\ndoc = getattr(ezdxf, "readfile")(p)\n', 1),
    # e o que NÃO pode virar alarme falso
    ("# doc = ezdxf.readfile(p)\n", 0),
    ('"""usa `ezdxf.readfile()` e expande tudo"""\n', 0),
    ("import ezdxf.recover\nd,a = ezdxf.recover.readfile(p)\n", 0),
    ("import ezdxf.recover as _rec\nd,a = _rec.readfile(p)\n", 0),
    ("from dxf_open import abrir_dxf\ndoc = abrir_dxf(p)\n", 0),
])
def test_CONTROLE_o_detector_ve_TODAS_as_formas_da_porta(fonte, esperado):
    """🧪 Cego pra uma forma, o guarda inteiro é enfeite — e a porta nº 8 abre
    calada com a bancada verde."""
    assert _portas_cruas(fonte) == esperado, fonte


@pytest.mark.parametrize("fonte,esperado", [
    ("from dxf_open import abrir_dxf\ndoc = abrir_dxf(p)\n", True),
    ("import dxf_open\ndoc = dxf_open.abrir_dxf(p)\n", True),
    ("from dxf_open import recuperar_dxf\nd = recuperar_dxf(p)\n", True),
    # 🪤 os três casos que o `"dxf_open" in src` aprovava sem a rede existir
    ("from dxf_open import abrir_dxf\ndoc = ezdxf.readfile(p)\n", False),
    ("# antes isto vinha do dxf_open\ndoc = ezdxf.readfile(p)\n", False),
    ('print("dxf_open falhou")\n', False),
])
def test_CONTROLE_o_uso_da_rede_e_CHAMADA_nao_mencao(fonte, esperado):
    assert _chama_o_abridor_com_rede(fonte) is esperado, fonte


def test_CONTROLE_a_varredura_alcanca_subpasta(tmp_path):
    """🧪 A varredura só olhava a RAIZ. Este controle põe uma porta nova numa
    SUBPASTA — com apelido de módulo, a forma que o detector velho não via — e
    exige que ela seja encontrada."""
    (tmp_path / "modulo_raiz.py").write_text("x = 1\n", encoding="utf-8")
    sub = tmp_path / "subpasta"
    sub.mkdir()
    (sub / "porta_nova.py").write_text(
        "import ezdxf as _ez\ndoc = _ez.readfile(p)\n", encoding="utf-8")
    vistos = dict(_todo_py_de_producao(str(tmp_path)))
    assert "subpasta/porta_nova.py" in vistos, (
        "a varredura não desce em subpasta: viu %r" % sorted(vistos))
    assert _portas_cruas(
        io.open(vistos["subpasta/porta_nova.py"], encoding="utf-8").read()) == 1


# ══════════════════════════════════════════════════════════════════════════
#  O guarda de verdade
# ══════════════════════════════════════════════════════════════════════════
def test_nenhuma_porta_nova_abriu_calada():
    achados = {}
    for rel, caminho in _todo_py_de_producao():
        try:
            n = _portas_cruas(io.open(caminho, encoding="utf-8").read())
        except SyntaxError:
            continue
        if n:
            achados[rel] = n
    novas = sorted(set(achados) - set(_PORTAS_DELIBERADAS))
    assert not novas, (
        "estes arquivos abrem DXF na mão e não estão na lista consciente: %s.\n"
        "Use `from dxf_open import abrir_dxf` (tem o recover embaixo) ou "
        "acrescente o arquivo a _PORTAS_DELIBERADAS explicando por quê." % novas)


@pytest.mark.parametrize("nome", _PROIBIDAS)
def test_as_duas_que_regrediram_nao_voltam(nome):
    """🚨 O preview do cliente-19 morreu em dxf_render.py com o mesmo KeyError que eu
    já tinha consertado. Regressão aqui é a falha se repetindo, não uma nova.

    🪤 06/09/2026: este guarda usava o detector VELHO (cego pra apelido) e
    aceitava `"dxf_open" in src` como prova de rede. Agora usa o MESMO detector
    do guarda de cima e exige a CHAMADA."""
    caminho = os.path.join(_BACKEND, nome)
    src = io.open(caminho, encoding="utf-8").read()
    assert _portas_cruas(src) == 0, (
        "%s voltou a abrir DXF sem rede — foi exatamente assim que a prancha "
        "do cliente-19 perdeu o preview" % nome)
    assert _chama_o_abridor_com_rede(src), (
        "%s não CHAMA o abridor com recover — ter o nome do módulo escrito no "
        "arquivo não abre prancha nenhuma" % nome)


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
