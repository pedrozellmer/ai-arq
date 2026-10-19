# -*- coding: utf-8 -*-
"""O pilar REDONDO desenhado em arcos conta como o desenhado em CIRCLE.

🩸 19/10/2026. A régua da família de anotação do Revit (FAMILIA_DE_ANOTACAO_DO_REVIT)
foi avaliada numa locação de pilares e a linha certa "Pilar circular Ø25 cm — 7 un"
sumiu. A única contagem dela era a ETIQUETA da coluna ("Identificador Colunas …",
7 INSERTs com texto e nada mais), que a régua tira. O pilar estava no desenho, sim:
14 ARC de 180°, raio 12,5 cm, aos pares no mesmo centro, no layer do pilar. É assim
que o Revit exporta o círculo, e o motor só via CIRCLE.

🔑 Arcos do layer de pilar com o mesmo centro e o mesmo raio que fecham a volta
entram como o CIRCLE: mesma faixa de diâmetro, mesmo `circular=True`. Volta
incompleta não entra. NASCE DESLIGADA (PILAR_DE_ARCOS=1 liga): com a régua do
Revit desligada a etiqueta segue contada, e o pilar viria pelas duas fontes.

Desenho sintético (o repositório é público).
"""
import os
import sys
import tempfile

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

#: as voltas que o arquivo real tinha (dois de 180°), e as outras formas de fechar
_DOIS_DE_180 = ((0, 180), (180, 360))
_DOIS_QUE_CRUZAM_O_ZERO = ((90, 270), (270, 90))     # o 2º passa pelo 0°
_QUATRO_DE_90 = ((0, 90), (90, 180), (180, 270), (270, 0))


def _arcos(msp, centro, raio, voltas, layer):
    for a0, a1 in voltas:
        msp.add_arc(centro, raio, a0, a1, dxfattribs={"layer": layer})


def _prancha(caminho, unidade=6, escala=1.0):
    """Locação sintética. `unidade` = $INSUNITS (6 m, 4 mm); `escala` multiplica as
    medidas (1000 quando o desenho é em mm)."""
    import ezdxf
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = unidade
    msp = doc.modelspace()
    for lay in ("S-COLS-____-OTLN", "PILAR", "EIXOS"):
        doc.layers.add(lay)
    e = escala
    # ✓ os três jeitos de fechar a volta, no layer do pilar (padrão do Revit e o nosso)
    _arcos(msp, (0 * e, 0), 0.125 * e, _DOIS_DE_180, "S-COLS-____-OTLN")          # Ø25
    _arcos(msp, (2 * e, 0), 0.125 * e, _DOIS_QUE_CRUZAM_O_ZERO, "S-COLS-____-OTLN")  # Ø25
    _arcos(msp, (4 * e, 0), 0.20 * e, _QUATRO_DE_90, "PILAR")                    # Ø40
    # ✗ volta incompleta: um arco só, e dois que somam 300°
    _arcos(msp, (6 * e, 0), 0.125 * e, ((0, 180),), "S-COLS-____-OTLN")
    _arcos(msp, (8 * e, 0), 0.125 * e, ((0, 180), (180, 300)), "S-COLS-____-OTLN")
    # ✗ raios diferentes no mesmo centro não fecham um círculo
    msp.add_arc((10 * e, 0), 0.125 * e, 0, 180, dxfattribs={"layer": "PILAR"})
    msp.add_arc((10 * e, 0), 0.15 * e, 180, 360, dxfattribs={"layer": "PILAR"})
    # ✗ fora da faixa de pilar (Ø2 m), e fora do layer de pilar
    _arcos(msp, (12 * e, 0), 1.0 * e, _DOIS_DE_180, "PILAR")
    _arcos(msp, (14 * e, 0), 0.125 * e, _DOIS_DE_180, "EIXOS")
    doc.saveas(caminho)
    return caminho


def _extrair(monkeypatch, liga="1", **kw):
    from dwg_extractor import extract_dxf
    if liga is None:
        monkeypatch.delenv("PILAR_DE_ARCOS", raising=False)
    else:
        monkeypatch.setenv("PILAR_DE_ARCOS", liga)
    cam = os.path.join(tempfile.mkdtemp(prefix="_pilar_arcos_"), "locacao.dxf")
    try:
        return extract_dxf(_prancha(cam, **kw))
    finally:
        try:
            os.remove(cam)
        except OSError:
            pass


def _redondos(ex):
    return sorted((r.layer, round(r.w_m, 3), bool(r.circular))
                  for r in (ex.struct_rects or []))


_ESPERADOS = [("PILAR", 0.4, True),
              ("S-COLS-____-OTLN", 0.25, True), ("S-COLS-____-OTLN", 0.25, True)]


def test_o_pilar_redondo_em_arcos_entra_como_o_circle(monkeypatch):
    assert _redondos(_extrair(monkeypatch)) == sorted(_ESPERADOS), (
        "esperava os 3 círculos fechados por arcos (dois de 180°, dois que cruzam o 0°, "
        "quatro de 90°) e nada da volta incompleta, do raio trocado, do Ø2 m e do EIXOS")


def test_o_desenho_em_milimetro_da_o_mesmo_diametro(monkeypatch):
    """O diâmetro passa pelo fator de unidade, como o do CIRCLE."""
    assert _redondos(_extrair(monkeypatch, unidade=4, escala=1000.0)) == sorted(_ESPERADOS)


@pytest.mark.parametrize("liga", [None, "0", "", "sim"])
def test_CONTROLE_nasce_desligada(monkeypatch, liga):
    """Só "1" liga. Desligada, nada de arco vira pilar (o CIRCLE segue como era)."""
    assert _redondos(_extrair(monkeypatch, liga=liga)) == []


def test_a_contagem_de_pilares_ve_a_secao_redonda(monkeypatch):
    """O que chega na planilha: `count_pillars` agrupa por seção, Ø em cm."""
    from structural_extractor import count_pillars
    cp = count_pillars(_extrair(monkeypatch))
    secoes = {d["secao_cm"]: d["qtd"] for d in cp["por_secao"]}
    assert secoes == {"Ø25 cm": 2, "Ø40 cm": 1}, secoes


def test_circle_e_arcos_no_mesmo_centro_contam_um(monkeypatch, tmp_path):
    """O mesmo pilar desenhado das duas formas (CIRCLE por cima dos arcos): o
    `count_pillars` junta pelo centro, como junta o contorno duplo."""
    import ezdxf
    from dwg_extractor import extract_dxf
    from structural_extractor import count_pillars
    monkeypatch.setenv("PILAR_DE_ARCOS", "1")
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("PILAR")
    msp = doc.modelspace()
    _arcos(msp, (0, 0), 0.15, _DOIS_DE_180, "PILAR")
    msp.add_circle((0, 0), 0.15, dxfattribs={"layer": "PILAR"})
    cam = str(tmp_path / "duplo.dxf")
    doc.saveas(cam)
    ex = extract_dxf(cam)
    assert len(ex.struct_rects) == 2, "os dois desenhos entram no extrator"
    cp = count_pillars(ex)
    assert [(d["secao_cm"], d["qtd"]) for d in cp["por_secao"]] == [("Ø30 cm", 1)]


def test_a_volta_repetida_e_um_pilar_e_a_volta_e_meia_nao(monkeypatch, tmp_path):
    """O mesmo círculo em arcos desenhado duas vezes (720°) é UM pilar; três
    meias-voltas (540°) não fecham nada."""
    import ezdxf
    from dwg_extractor import extract_dxf
    monkeypatch.setenv("PILAR_DE_ARCOS", "1")
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("PILAR")
    msp = doc.modelspace()
    _arcos(msp, (0, 0), 0.15, _DOIS_DE_180 + _DOIS_DE_180, "PILAR")
    _arcos(msp, (3, 0), 0.15, _DOIS_DE_180 + ((0, 180),), "PILAR")
    cam = str(tmp_path / "repetido.dxf")
    doc.saveas(cam)
    assert [(round(r.cx, 3), round(r.w_m, 3)) for r in extract_dxf(cam).struct_rects] == [(0.0, 0.3)]


def test_a_avaliacao_pode_ligar_a_chave():
    import main
    assert "PILAR_DE_ARCOS" in main._CHAVES_AVALIAVEIS
    assert main._chaves_pedidas("PILAR_DE_ARCOS=1") == {"PILAR_DE_ARCOS": "1"}
