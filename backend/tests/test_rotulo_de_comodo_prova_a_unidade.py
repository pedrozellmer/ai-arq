# -*- coding: utf-8 -*-
"""O rótulo de área de CÔMODO prova a unidade da prancha (H94, 02/10/2026).

A 5ª régua (rótulo de área × região que ele rotula, ±2 %, ≥ 2 rótulos distintos)
provava a unidade em 3 de 94 desenhos do acervo com rótulo "m²". Três peneiras
jogavam fora o resto, cada uma medida num desenho real:
  (1) o FORMATO — só o texto inteiro "57,16 m²" valia; a loja escrevia
      "MODA ESPORTIVA ÁREA=9,99m²" (100 rótulos) e o sobrado
      "QUARTO 1 Ar = 12.34 m²";
  (2) a ALLOWLIST de nome de layer do contorno fechado — o cômodo do sobrado
      estava no layer "INVISIVEIS";
  (3) o NOME ocupava a região antes do rótulo (1 texto por região) — o
      "43,11 m²" do apartamento ficava sem par.
Abertas as três: 21 provas; em ×100/÷100, nenhuma. 🩸 E rótulo/contorno de LOTE
não prova a prancha: num projeto de prefeitura a implantação estava em cm e o prédio em mm.
O contorno sem allowlist é SÓ região de prova: nenhuma quantidade muda.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import dwg_extractor as dx  # noqa: E402
import engine_rules as er  # noqa: E402
from test_parede_desmente_a_unidade import _dxf, _faces  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
#  1. O leitor do rótulo
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("texto, valor", [
    ("MODA ESPORTIVA ÁREA=9,99m²", 9.99),
    ("QUARTO 1 Ar = 12.34 m²", 12.34),
    ("COZINHA\nAr = 9.00 m²", 9.0),
    ("SALÃO ÁREA: 1.234,56 m²", 1234.56),
    ("CIRC. Ar = 4.50m2", 4.5),
    ("57,16m²", 57.16),
])
def test_leitor_aceita_o_numero_no_fim_depois_do_igual(texto, valor):
    assert er.rotulo_area_de_comodo(texto) == pytest.approx(valor)


def test_formato_puro_le_igual_a_regua_de_hoje():
    for t in ("57,16m²", "12,00 m²", "9 m2"):
        assert er.rotulo_area_de_comodo(t) == er.rotulo_area_como_numero(t), t


@pytest.mark.parametrize("texto", [
    "ÁREA REAL: 360,00 m²", "C.P. = 362,50 m²", "CP: 360,00 m²", "Área do Terreno = 360,00 m²",
    "LOTE 9 QUADRA 3 REAL=360,00m²", "IMPLANTAÇÃO ÁREA=300,00m²", "DIVISA = 30,00 m²",
    "Real = 360,00 m² C.P. = 362,50 m²",
])
def test_rotulo_de_lote_nao_e_de_comodo(texto):
    assert er.rotulo_area_de_comodo(texto) is None


@pytest.mark.parametrize("texto", ["SALA 12,50", "SALA 12,50 m² (ver nota)", "COTA 2,50", "Ar = 0,50 m²",
                                   "ÁREA 12,50 m²", "SALA ÁREA=12,50 m² (ver nota)", ""])
def test_sem_m2_no_fim_ou_sem_igual_nao_e_rotulo(texto):
    assert er.rotulo_area_de_comodo(texto) is None


# ══════════════════════════════════════════════════════════════════════════
#  2. Os pares de prova
# ══════════════════════════════════════════════════════════════════════════
def _reg(layer, x0, y0, x1, y1, area):
    return {"layer": layer, "bbox": (x0, y0, x1, y1), "area": area, "preenchimento": 1.0}


def _txt(s, x, y):
    return {"text": s, "position": (x, y), "layer": "TEXTO"}


def test_o_nome_nao_ocupa_a_regiao_antes_do_rotulo():
    regs = [_reg("PISO", 0, 0, 4, 3, 12.0), _reg("PISO", 10, 0, 15, 2, 10.0)]
    txts = [_txt("SALA", 2, 2), _txt("12,00 m²", 2, 1), _txt("QUARTO", 12, 1.5), _txt("10,00 m²", 12, 0.5)]
    # CONTROLE: a régua de hoje dá a região ao nome e não prova
    assert not er.unidade_provada_por_rotulo(er.casar_texto_com_regiao(txts, regs))["provada"]
    v = er.unidade_provada_por_rotulo(er.pares_de_prova_por_rotulo(txts, regs), leitor=er.rotulo_area_de_comodo)
    assert v["provada"] and v["n_batem"] == 2, v


@pytest.mark.parametrize("layer", ["_Divisa", "IMPLANTAÇÃO", "LOTE", "Terreno"])
def test_regiao_de_lote_nao_prova(layer):
    regs = [_reg(layer, 0, 0, 4, 3, 12.0), _reg(layer, 10, 0, 15, 2, 10.0)]
    txts = [_txt("ÁREA=12,00m²", 2, 1), _txt("ÁREA=10,00m²", 12, 0.5)]
    assert er.pares_de_prova_por_rotulo(txts, regs) == []
    # CONTROLE: o mesmo desenho num layer de cômodo prova
    regs2 = [_reg("SALAO", 0, 0, 4, 3, 12.0), _reg("SALAO", 10, 0, 15, 2, 10.0)]
    v = er.unidade_provada_por_rotulo(er.pares_de_prova_por_rotulo(txts, regs2), leitor=er.rotulo_area_de_comodo)
    assert v["provada"], v


# ══════════════════════════════════════════════════════════════════════════
#  3. De ponta a ponta (extract_dxf)
#  Desenho em cm declarado mm: a parede de 1,5 cm dá a ressalva (H51); os
#  cômodos estão em mm de verdade e o rótulo prova o mm (como no teste da 5ª
#  régua de hoje, `test_de_ponta_a_ponta_rotulo_de_area_que_bate_prova_e_derruba`).
# ══════════════════════════════════════════════════════════════════════════
_COMODOS = ((20000, 0, 4000, 3000, 12.0), (30000, 0, 5000, 2000, 10.0), (40000, 0, 3000, 3000, 9.0))


def _comodos(layer, rotulo, nome_antes=False, so=None):
    """Cômodos (polilinha fechada em mm) com o rótulo no meio; `rotulo(area)` dá o texto."""
    def _f(msp):
        for x, y, w, h, a in (_COMODOS if so is None else _COMODOS[:so]):
            msp.add_lwpolyline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], close=True,
                               dxfattribs={"layer": layer})
            if nome_antes:
                msp.add_text("SALA", dxfattribs={"height": 100, "insert": (x + w / 2, y + h * 0.7), "layer": "TEXTO"})
            msp.add_text(rotulo(a), dxfattribs={"height": 100, "insert": (x + w / 2, y + h / 2), "layer": "TEXTO"})
    return _f


def _md(tmp_path, extra):
    ext = dx.extract_dxf(_dxf(tmp_path, _faces(), extra=extra))
    return ext, ext.metadata


def test_CONTROLE_sem_rotulo_a_ressalva_fica(tmp_path):
    _, md = _md(tmp_path, _comodos("INVISIVEIS", lambda a: "SALA"))
    assert md.get("unidade_contradita_pela_parede") and not md.get("unidade_provada_por_rotulo"), sorted(md)


def test_formato_com_igual_prova_e_derruba_a_ressalva(tmp_path):
    _, md = _md(tmp_path, _comodos("PISO", lambda a: "SALA ÁREA=%.2fm²" % a))
    assert md.get("unidade_provada_por_rotulo"), sorted(md)
    assert md.get("prova_por_rotulo_de_comodo", {}).get("batem") == 3, md.get("prova_por_rotulo_de_comodo")
    assert not md.get("unidade_contradita_pela_parede")
    assert md.get("unidade_contradita_pela_parede_superada_por_rotulo")


def test_contorno_fora_da_allowlist_prova_mas_nao_mede(tmp_path):
    ext, md = _md(tmp_path, _comodos("INVISIVEIS", lambda a: "%.2f m²" % a))
    assert md.get("unidade_provada_por_rotulo"), sorted(md)
    # 🔑 só região de prova: nenhuma área de contorno nova, a recusa continua contada
    assert not any(p.layer == "INVISIVEIS" for p in ext.polygon_areas), ext.polygon_areas
    assert "INVISIVEIS" not in ext.get_polygon_areas_by_layer()
    assert ext.poly_recusa.get("fora_da_allowlist") == 3, ext.poly_recusa
    assert ext.poly_layers_recusados.get("INVISIVEIS") == 3


def test_contorno_de_prova_nao_muda_nenhuma_soma(tmp_path):
    """A mesma prancha sem prova e com prova: paredes, hachuras e contornos iguais."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    sem, md0 = _md(tmp_path / "a", _comodos("INVISIVEIS", lambda a: "SALA"))
    com, md = _md(tmp_path / "b", _comodos("INVISIVEIS", lambda a: "%.2f m²" % a))
    assert md.get("unidade_provada_por_rotulo") and not md0.get("unidade_provada_por_rotulo")
    assert sum(w.length for w in com.walls) == pytest.approx(sum(w.length for w in sem.walls))
    assert [(h.layer, h.area) for h in com.hatches] == [(h.layer, h.area) for h in sem.hatches]
    assert [(p.layer, p.area) for p in com.polygon_areas] == [(p.layer, p.area) for p in sem.polygon_areas]


def test_nome_antes_do_rotulo_ainda_prova(tmp_path):
    _, md = _md(tmp_path, _comodos("PISO", lambda a: "%.2f m²" % a, nome_antes=True))
    assert md.get("unidade_provada_por_rotulo"), sorted(md)
    assert md.get("prova_por_rotulo_de_comodo"), "a régua de hoje provaria sozinha — o nome não roubou"


def test_CONTROLE_formato_puro_ja_provava_e_o_h94_nem_roda(tmp_path):
    _, md = _md(tmp_path, _comodos("PISO", lambda a: "%.2f m²" % a))
    assert md.get("unidade_provada_por_rotulo"), sorted(md)
    assert not md.get("prova_por_rotulo_de_comodo"), md.get("prova_por_rotulo_de_comodo")


def _lote(layer="_Divisa", textos=("ÁREA REAL: 360,00 m²", "C.P. = 362,50 m²")):
    """O lote do evaa4391: os rótulos BATEM com o contorno da divisa no fator lido."""
    def _f(msp):
        for x, h, t in zip((60000, 90000), (18000.0, 18125.0), textos):
            msp.add_lwpolyline([(x, 0), (x + 20000, 0), (x + 20000, h), (x, h)], close=True,
                               dxfattribs={"layer": layer})
            msp.add_text(t, dxfattribs={"height": 100, "insert": (x + 10000, h / 2), "layer": "TEXTO"})
    return _f


def test_lote_nao_prova_a_prancha(tmp_path):
    """evaa4391: a implantação em cm, o prédio em mm — o lote não pode provar o arquivo."""
    _, md = _md(tmp_path, _lote())
    assert not md.get("unidade_provada_por_rotulo"), md.get("unidade_provada_por_rotulo")
    assert md.get("unidade_contradita_pela_parede")


def test_CONTROLE_o_mesmo_contorno_com_rotulo_de_comodo_prova(tmp_path):
    """Sem as palavras de lote (texto E layer), as mesmas áreas provam — é a exclusão que barra."""
    _, md = _md(tmp_path, _lote(layer="SALAO", textos=("SALÃO ÁREA=360,00m²", "GALPÃO ÁREA=362,50m²")))
    assert md.get("unidade_provada_por_rotulo"), sorted(md)


def test_moldura_de_implantacao_nao_prova(tmp_path):
    _, md = _md(tmp_path, _comodos("IMPLANTAÇÃO", lambda a: "ÁREA=%.2fm²" % a))
    assert not md.get("unidade_provada_por_rotulo"), md.get("unidade_provada_por_rotulo")


def test_rotulo_de_lote_em_layer_de_comodo_nao_prova(tmp_path):
    _, md = _md(tmp_path, _comodos("SALAO", lambda a: "ÁREA DO TERRENO = %.2f m²" % a))
    assert not md.get("unidade_provada_por_rotulo"), md.get("unidade_provada_por_rotulo")


def test_rotulo_que_nao_bate_nao_prova(tmp_path):
    _, md = _md(tmp_path, _comodos("INVISIVEIS", lambda a: "SALA ÁREA=%.2fm²" % (a * 1.05)))
    assert not md.get("unidade_provada_por_rotulo"), md.get("unidade_provada_por_rotulo")


def test_um_rotulo_so_nao_prova(tmp_path):
    _, md = _md(tmp_path, _comodos("INVISIVEIS", lambda a: "SALA ÁREA=%.2fm²" % a, so=1))
    assert not md.get("unidade_provada_por_rotulo"), md.get("unidade_provada_por_rotulo")


def _com_rotulos_que_nao_batem(n):
    """Os 3 cômodos que batem + `n` cômodos cujo rótulo NÃO bate (12 m² × 20+k)."""
    base = _comodos("INVISIVEIS", lambda a: "SALA ÁREA=%.2fm²" % a)

    def _f(msp):
        base(msp)
        for k in range(n):
            x = 60000 + k * 6000
            msp.add_lwpolyline([(x, 0), (x + 4000, 0), (x + 4000, 3000), (x, 3000)], close=True,
                               dxfattribs={"layer": "INVISIVEIS"})
            msp.add_text("DEP %d ÁREA=%.2fm²" % (k, 20.0 + k),
                         dxfattribs={"height": 100, "insert": (x + 2000, 1500), "layer": "TEXTO"})
    return _f


def test_poucos_rotulos_batendo_entre_muitos_nao_prova(tmp_path):
    """3 de 33 (9 %): com contorno de qualquer layer, par por acaso fica mais
    fácil — abaixo de 10 % dos rótulos batendo, a prova nova não vale."""
    _, md = _md(tmp_path, _com_rotulos_que_nao_batem(30))
    assert not md.get("unidade_provada_por_rotulo"), md.get("unidade_provada_por_rotulo")


def test_CONTROLE_acima_de_dez_por_cento_prova(tmp_path):
    """3 de 23 (13 %): prova."""
    _, md = _md(tmp_path, _com_rotulos_que_nao_batem(20))
    assert md.get("unidade_provada_por_rotulo"), sorted(md)


def test_o_rastro_do_h94_nao_vai_pro_prompt(tmp_path):
    ext, md = _md(tmp_path, _comodos("INVISIVEIS", lambda a: "%.2f m²" % a))
    assert md.get("prova_por_rotulo_de_comodo")
    assert "prova_por_rotulo_de_comodo" not in ext.to_structured_prompt()
