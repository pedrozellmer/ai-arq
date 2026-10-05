# -*- coding: utf-8 -*-
"""A ponta de cota padrão do AutoCAD não é peça.

🩸 05/10/2026 — E15 do estudo do acervo. Cota ou chamada explodida deixa a
seta solta como INSERT, e a leitura lê o nome: `_Open90` virou "porta de abrir
90°" (13 un com selo), `_DOT` virou "sprinklers" (17 un com selo). Na
produção, 8 linhas entregues em 6 jobs, nenhuma era peça; o guarda da linha
(14/09) só rebaixava 6 depois de escritas e não conhecia o "DOT" sem "_" (2
linhas de 15 un com selo). O que desenham, em
tamanho de unidade: `_DOT` = o ponto (polilinha) + 1 linha, caixa 1,5 × 1,0;
`_Open90` = 3 linhas, caixa 1 × 1. "DOT" sem o "_" é o `_DOT` renomeado na
exportação (definição idêntica) e "TIC" é o traço de cota (barra + cruz, 3
linhas, caixa 2 × 2) — esses dois só valem com a definição de seta.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
import engine_rules as er  # noqa: E402

# a lista vem da constante (a mesma do guarda da linha); a caixa do AutoCAD vem à parte
_SETAS = sorted(er.SETAS_DE_COTA_DO_AUTOCAD)
_CAIXA_DO_AUTOCAD = ["_ArchTick", "_Oblique", "_Dot", "_DotSmall", "_Open90", "_open90", "_None", "_ClosedBlank"]
_PECA = "TOMADA"


def _ponto(b):
    # o `_DOT` do AutoCAD: o ponto (polilinha de 2 vértices com bojo e largura) + a linha do rabo
    b.add_lwpolyline([(-0.25, 0, 0.5, 0.5, 1), (0.25, 0, 0.5, 0.5, 1)], format="xyseb", close=True)
    b.add_line((-0.5, 0), (-1.0, 0))


def _traco(b):
    # o "tic" do acervo: barra + cruz, caixa 2 × 2
    b.add_line((-0.6, -0.6), (0.6, 0.6))
    b.add_line((0, -1.0), (0, 1.0))
    b.add_line((-1.0, 0), (1.0, 0))


def _seta_aberta(b, i=0):
    # `_Open90`: 3 linhas, caixa 1 × 1 (o i muda o desenho: a assinatura não junta dois nomes)
    b.add_line((0, 0), (-1.0, 0.5 + 0.01 * i))
    b.add_line((0, 0), (-1.0, -0.5))
    b.add_line((-1.0, -0.5), (-1.0, 0.5 + 0.01 * i))


def _peca(b):
    b.add_circle((0, 0), 0.04)
    b.add_line((-0.05, 0), (0.05, 0))
    b.add_line((0, -0.05), (0, 0.05))


def _ler(tmp_path, defs, n=6):
    """defs: [(nome, desenha(bloco))]; cada um inserido n vezes."""
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for k, (nome, desenha) in enumerate(defs):
        desenha(doc.blocks.new(nome))
        for i in range(n):
            msp.add_blockref(nome, (3.0 * i, 5.0 * k), dxfattribs={"xscale": 0.1, "yscale": 0.1})
    p = str(tmp_path / "planta.dxf")
    doc.saveas(p)
    return dx.extract_dxf(p)


def _contados(ex):
    return {b.name for b in ex.blocks}


@pytest.mark.parametrize("nome", _SETAS + _CAIXA_DO_AUTOCAD)
def test_seta_de_cota_do_autocad_sai_da_contagem(tmp_path, nome):
    i = len(nome)
    ex = _ler(tmp_path, [(nome, lambda b: _seta_aberta(b, i)), (_PECA, _peca)])
    assert nome not in _contados(ex), _contados(ex)
    assert _PECA in _contados(ex), _contados(ex)
    assert ex.blocos_descartados.get("anotacao", 0) >= 6, ex.blocos_descartados


@pytest.mark.parametrize("nome", ["DOT", "Dot", "dot"])
def test_dot_com_a_definicao_do_ponto_sai(tmp_path, nome):
    ex = _ler(tmp_path, [(nome, _ponto), (_PECA, _peca)])
    assert nome not in _contados(ex), _contados(ex)
    assert _PECA in _contados(ex), _contados(ex)


@pytest.mark.parametrize("nome", ["TIC", "tic"])
def test_tic_com_a_definicao_do_traco_sai(tmp_path, nome):
    ex = _ler(tmp_path, [(nome, _traco), (_PECA, _peca)])
    assert nome not in _contados(ex), _contados(ex)


# ── UMA lista só: o guarda da linha (14/09) e a contagem leem a mesma constante ──
def test_a_lista_tem_os_20_nomes_de_seta_do_autocad():
    assert len(er.SETAS_DE_COTA_DO_AUTOCAD) == 20
    assert {"_OPEN90", "_DOT", "_NONE", "_ARCHTICK", "_CLOSEDFILLED"} <= er.SETAS_DE_COTA_DO_AUTOCAD


_FRASE_DE_PECA = "Porta de abrir — conforme bloco '%s'"


def test_CONTROLE_a_frase_so_cai_pelo_nome_de_seta():
    # 🪤 a frase começa pelo substantivo: a régua antiga ("Elemento…", "Bloco…") não a pega sozinha
    assert not er.item_e_bloco_sem_identidade(_FRASE_DE_PECA % "P90", "un")


@pytest.mark.parametrize("nome", _SETAS)
def test_o_guarda_da_linha_le_a_mesma_lista(nome):
    assert er.item_e_bloco_sem_identidade(_FRASE_DE_PECA % nome, "un"), nome


def test_a_contagem_nao_tem_lista_propria():
    """🪤 Uma segunda lista diverge calada: o nome entra numa e não na outra. O
    motor importa a constante de engine_rules e não escreve nenhum nome de seta."""
    import ast
    import io
    fonte = io.open(dx.__file__, encoding="utf-8").read()
    arv = ast.parse(fonte)
    importa = any(isinstance(n, ast.ImportFrom) and n.module == "engine_rules"
                  and any(a.name == "SETAS_DE_COTA_DO_AUTOCAD" for a in n.names) for n in ast.walk(arv))
    assert importa, "o motor não importa SETAS_DE_COTA_DO_AUTOCAD de engine_rules"
    literais = {n.value.upper() for n in ast.walk(arv) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert not (literais & er.SETAS_DE_COTA_DO_AUTOCAD), sorted(literais & er.SETAS_DE_COTA_DO_AUTOCAD)


# ── o que NÃO muda ─────────────────────────────────────────────────────────────
def test_CONTROLE_luminaria_dot_com_circulo_e_atributo_continua_peca(tmp_path):
    def luminaria(b):
        b.add_circle((0, 0), 0.3)
        b.add_attdef("TIPO", (0.4, 0), dxfattribs={"height": 0.1})

    ex = _ler(tmp_path, [("DOT", luminaria), (_PECA, _peca)])
    assert "DOT" in _contados(ex), _contados(ex)


def test_CONTROLE_dot_so_de_linha_mas_com_atributo_continua_peca(tmp_path):
    def com_atributo(b):
        _ponto(b)
        b.add_attdef("TIPO", (0.4, 0), dxfattribs={"height": 0.1})

    ex = _ler(tmp_path, [("DOT", com_atributo), (_PECA, _peca)])
    assert "DOT" in _contados(ex), _contados(ex)


def test_CONTROLE_tic_com_texto_continua_peca(tmp_path):
    def com_texto(b):
        b.add_line((-1.0, 0), (1.0, 0))
        b.add_text("T1", dxfattribs={"height": 0.2})

    ex = _ler(tmp_path, [("TIC", com_texto), (_PECA, _peca)])
    assert "TIC" in _contados(ex), _contados(ex)


def test_CONTROLE_tic_com_4_linhas_continua_peca(tmp_path):
    def quatro(b):
        _traco(b)
        b.add_line((-1.0, 1.0), (1.0, -1.0))

    ex = _ler(tmp_path, [("TIC", quatro), (_PECA, _peca)])
    assert "TIC" in _contados(ex), _contados(ex)


def test_CONTROLE_dot_grande_continua_peca(tmp_path):
    def placa(b):
        b.add_lwpolyline([(0, 0), (3.0, 0), (3.0, 3.0), (0, 3.0)], close=True)

    ex = _ler(tmp_path, [("DOT", placa), (_PECA, _peca)])
    assert "DOT" in _contados(ex), _contados(ex)


@pytest.mark.parametrize("nome", ["PORTA_OPEN90_80", "_DOTX", "_OPEN90A", "X_DOT", "_OPEN 90", "DOTS", "TIC2",
                                  "PORTA_OPEN90"])
def test_CONTROLE_so_o_nome_inteiro(tmp_path, nome):
    # mesmo desenho de seta: quem decide é o nome inteiro
    ex = _ler(tmp_path, [(nome, _ponto), (_PECA, _peca)])
    assert nome in _contados(ex), (nome, _contados(ex))
