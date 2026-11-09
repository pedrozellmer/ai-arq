# -*- coding: utf-8 -*-
"""O ArchiCAD que guarda cada parede num bloco `Parede_N`: as paredes sumiam.

🩸 09/11/2026 (cliente nova, 1º projeto, reforma de 68 m²): 44 blocos
`Parede_N` + 6 `Laje_N`, cada um inserido uma vez, com as linhas dentro (layer
"ARQ - Parede"). No modelo solto: cotas, textos e 8 linhas. O motor lê o modelo
e só abria bloco `A$C`: 0 parede, 288 linhas / 0 medidas. Abertos: 130 m de
face de parede e 12,4 m de parede a demolir. 📏 120 d: 2 jobs de 2 clientes.

🔑 Abre SÓ elemento + número (Parede_N, Laje_N, Pilar_N…), e só com ≥ 5 deles.
Móvel e louça seguem contados pelo nome. Chave ABRIR_ELEMENTO_ARCHICAD (nasce
0): com 0 só conta. Com 0 o prompt sai idêntico (provado no arquivo real).
"""
import os
import sys
import tempfile

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import ezdxf  # noqa: E402
import pytest  # noqa: E402

import dwg_extractor as dx  # noqa: E402

_CHAVE = "ABRIR_ELEMENTO_ARCHICAD"


def _doc(n=6, nome="Parede_{}", com_porta=True):
    """Um apartamento em que cada parede é um bloco inserido uma vez (mm)."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    for lay in ("ARQ - Parede", "Janelas"):
        if lay not in doc.layers:
            doc.layers.add(lay)
    porta = doc.blocks.new("Porta 27[1]")
    porta.add_line((0, 0), (800, 0), dxfattribs={"layer": "Janelas"})
    msp = doc.modelspace()
    for i in range(1, n + 1):
        b = doc.blocks.new(nome.format(i))
        b.add_line((0, 0), (4000, 0), dxfattribs={"layer": "ARQ - Parede"})
        b.add_line((0, 150), (4000, 150), dxfattribs={"layer": "ARQ - Parede"})
        if com_porta and i == 1:
            b.add_blockref("Porta 27[1]", (1000, 0), dxfattribs={"layer": "Janelas"})
        msp.add_blockref(nome.format(i), (0, i * 5000))
    return doc


def _linhas_soltas(doc, layer="ARQ - Parede"):
    return [e for e in doc.modelspace() if e.dxftype() == "LINE" and e.dxf.layer == layer]


def test_chave_em_0_so_conta(monkeypatch):
    monkeypatch.setenv(_CHAVE, "0")
    doc = _doc()
    r = dx.abrir_elementos_do_archicad(doc)
    assert r == {"candidatos": 6, "liga": 0, "abertos": 0, "falhas": 0}, r
    assert not _linhas_soltas(doc), "abriu com a chave em 0"


def test_sem_chave_e_desligada(monkeypatch):
    monkeypatch.delenv(_CHAVE, raising=False)
    doc = _doc()
    assert dx.abrir_elementos_do_archicad(doc)["liga"] == 0
    assert not _linhas_soltas(doc), "a regra nasceu LIGADA"


def test_chave_em_1_abre_e_leva_pro_lugar(monkeypatch):
    monkeypatch.setenv(_CHAVE, "1")
    doc = _doc()
    r = dx.abrir_elementos_do_archicad(doc)
    assert r["abertos"] == 6 and r["liga"] == 1, r
    soltas = _linhas_soltas(doc)
    assert len(soltas) == 12, len(soltas)
    # a transformação do pai vale: Parede_3 foi inserida em y=15000
    assert any(abs(e.dxf.start.y - 15000) < 1e-6 for e in soltas)
    nomes = [e.dxf.name for e in doc.modelspace().query("INSERT")]
    assert not any(n.startswith("Parede_") for n in nomes), nomes
    # a porta que morava dentro da parede vira INSERT do modelo, UMA vez
    assert nomes.count("Porta 27[1]") == 1, nomes


def test_poucos_blocos_nao_e_o_padrao(monkeypatch):
    monkeypatch.setenv(_CHAVE, "1")
    doc = _doc(n=4)
    assert dx.abrir_elementos_do_archicad(doc) == {}
    assert not _linhas_soltas(doc)


@pytest.mark.parametrize("nome", ["Cadeira_{}", "Cama_{}", "Parede{}", "PAREDE_A{}",
                                  "Parede_{}_copia"])
def test_bloco_de_gente_nao_abre(monkeypatch, nome):
    monkeypatch.setenv(_CHAVE, "1")
    doc = _doc(nome=nome)
    assert dx.abrir_elementos_do_archicad(doc) == {}
    assert not _linhas_soltas(doc), nome


@pytest.mark.parametrize("nome", ["Laje_{}", "Pilar_{}", "Viga_{}", "Wall_{}", "parede_{}"])
def test_os_outros_elementos_abrem(monkeypatch, nome):
    monkeypatch.setenv(_CHAVE, "1")
    doc = _doc(nome=nome)
    assert dx.abrir_elementos_do_archicad(doc)["abertos"] == 6


def test_nunca_lanca():
    assert dx.abrir_elementos_do_archicad(None) == {}


def _extrair(doc):
    d = tempfile.mkdtemp(prefix="_archicad_")
    p = os.path.join(d, "p.dxf")
    doc.saveas(p)
    return dx.extract_dxf(p)


def test_extracao_inteira_chave_0_e_1(monkeypatch):
    monkeypatch.setenv(_CHAVE, "0")
    r0 = _extrair(_doc())
    monkeypatch.setenv(_CHAVE, "1")
    r1 = _extrair(_doc())
    assert r0.metadata.get("elementos_archicad") == "candidatos=6 liga=0 abertos=0 falhas=0"
    assert r1.metadata.get("elementos_archicad") == "candidatos=6 liga=1 abertos=6 falhas=0"
    p0 = sum(w.length for w in r0.walls if w.layer == "ARQ - Parede")
    p1 = sum(w.length for w in r1.walls if w.layer == "ARQ - Parede")
    assert p0 == 0 and p1 > 0, (p0, p1)
    for r in (r0, r1):
        assert "elementos_archicad" not in r.to_structured_prompt(), (
            "registro do log foi pro prompt (ver _METADADOS_FORA_DO_PROMPT)")


def test_a_chave_e_avaliavel_e_o_log_mostra():
    src = open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8").read()
    ini = src.index("_CHAVES_AVALIAVEIS = frozenset({")
    assert '"ABRIR_ELEMENTO_ARCHICAD"' in src[ini:src.index("})", ini)]
    assert "elem_archicad=[{_md_u.get('elementos_archicad')" in src
