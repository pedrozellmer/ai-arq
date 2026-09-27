# -*- coding: utf-8 -*-
"""Em folha de papel, a SEÇÃO do pilar não é medida — a contagem é.

🩸 27/09/2026 — job 32a27efc (estrutura, folha A1 desenhada no modelo, vistas
em 1:125 e 1:25). A contagem de retângulos acertou (32 pilares), mas a seção
saiu da geometria × o fator único da prancha: o pilar 19×30 da vista 1:125,
lido com fator 0,1, virou "15x24 cm" — e o prompt dizia "A seção veio da
geometria (medida)". A releitura entregou "Pilar de concreto — seção 15×24".
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import structural_extractor as se  # noqa: E402


def _pilares(papel=None, repetido=False):
    sec = {"secao_cm": "15x24 cm", "qtd": 32, "nomes": ["P1", "P2"]}
    if repetido:
        sec.update(repetidos=["P2"], distintos=31)
    pil = {"rects_qtd": 32, "layers": ["PILAR_CONCRETO"], "por_secao": [sec], "blocos": []}
    if papel:
        pil["escala_de_papel"] = papel
    return {"pilares": pil}


def test_o_caso_em_folha_de_papel_a_secao_nao_sai_como_medida():
    txt = se.structural_prompt_section(_pilares("1:125 (54 cotas), 1:25 (48 cotas)"))
    assert "[MEDIDO] 32 pilares contados" in txt, txt           # a contagem vale
    assert "[MEDIDO] seção 15x24" not in txt, txt
    assert "desenho ≈ 15x24 cm (seção NÃO medida)" in txt, txt
    assert "A seção veio da geometria (medida)" not in txt, txt
    assert "ESCALA DE PAPEL (1:125 (54 cotas), 1:25 (48 cotas))" in txt, txt
    assert "ESCRITA na prancha" in txt and "NUNCA a do '≈'" in txt, txt


def test_o_caso_com_rotulo_repetido_tambem_nao_mede_a_secao():
    txt = se.structural_prompt_section(_pilares("1:125 (69 cotas)", repetido=True))
    assert "[REFERÊNCIA] desenho ≈ 15x24 cm (seção NÃO medida): 32 desenhos" in txt, txt
    assert "seção 15x24 cm:" not in txt, txt


def test_CONTROLE_sem_folha_de_papel_a_secao_segue_medida():
    txt = se.structural_prompt_section(_pilares())
    assert "[MEDIDO] seção 15x24 cm: 32 un" in txt, txt
    assert "A seção veio da geometria (medida)." in txt, txt
    assert "ESCALA DE PAPEL" not in txt and "≈" not in txt, txt


class _Extracao:
    def __init__(self, metadata):
        self.metadata = metadata
        self.texts = []


def _pil_fixo(*a, **k):
    return {"rects_qtd": 32, "layers": ["PILAR_CONCRETO"],
            "por_secao": [{"secao_cm": "15x24 cm", "qtd": 32, "nomes": []}], "blocos": []}


def test_a_extracao_leva_a_ressalva_de_folha_de_papel_aos_pilares(monkeypatch):
    monkeypatch.setattr(se, "count_pillars", _pil_fixo)
    r = se.extract_structural_measurements(_Extracao({"escala_por_vista": "1:125 (119 cotas)"}))
    assert r["pilares"]["escala_de_papel"] == "1:125 (119 cotas)", r


def _folha_de_papel(janela=False):
    """Folha A1 desenhada no modelo (mm de papel) com 6 cotas em 1:125 —
    a mesma receita de test_folha_de_papel_no_modelo."""
    import ezdxf
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4
    doc.header["$EXTMIN"] = (0, 0, 0)
    doc.header["$EXTMAX"] = (841.0, 594.0, 0)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (841, 0), (841, 594), (0, 594)], close=True)
    doc.dimstyles.new("E125", dxfattribs={"dimlfac": 12.5})
    for k in range(6):
        x0 = 20.0 + 30.0 * k
        msp.add_linear_dim(base=(x0, 28), p1=(x0, 20), p2=(x0 + 24, 20),
                           dimstyle="E125").render()
    if janela:
        lay = doc.layouts.new("FOLHA 01")
        vp = lay.add_viewport(center=(400, 300), size=(700, 500),
                              view_center_point=(420, 297), view_height=594)
        vp.dxf.view_target_point = (0, 0, 0)
    return doc


def _prompt_da_folha(tmp_path, monkeypatch, janela):
    """Pelo caminho de produção: extract_dxf grava a ressalva, e o prompt do
    DXFExtraction chama extract_structural_measurements → a seção de pilares.
    🔑 Sem isto, a chave 'escala_por_vista' só existe escrita à mão nos testes:
    se o extrator a renomeasse, o conserto desligaria calado (revisão 27/09)."""
    import dwg_extractor as dx
    monkeypatch.setattr(se, "count_pillars", _pil_fixo)
    p = str(tmp_path / "folha.dxf")
    _folha_de_papel(janela).saveas(p)
    ext = dx.extract_dxf(p)
    return ext.metadata, ext.to_structured_prompt()


def test_ponta_a_ponta_a_folha_de_papel_chega_ao_prompt(tmp_path, monkeypatch):
    md, txt = _prompt_da_folha(tmp_path, monkeypatch, janela=False)
    assert md.get("escala_por_vista"), md
    assert "desenho ≈ 15x24 cm (seção NÃO medida)" in txt, txt[-3000:]
    assert "[MEDIDO] seção 15x24" not in txt


def test_CONTROLE_ponta_a_ponta_folha_no_layout_segue_medindo(tmp_path, monkeypatch):
    md, txt = _prompt_da_folha(tmp_path, monkeypatch, janela=True)
    assert "escala_por_vista" not in md, md
    assert "[MEDIDO] seção 15x24 cm: 32 un" in txt, txt[-3000:]


def test_CONTROLE_sem_a_ressalva_nada_muda(monkeypatch):
    monkeypatch.setattr(se, "count_pillars", _pil_fixo)
    for md in ({}, {"escala_por_vista": ""}, None):
        r = se.extract_structural_measurements(_Extracao(md))
        assert "escala_de_papel" not in r["pilares"], (md, r)
