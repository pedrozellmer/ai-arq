# -*- coding: utf-8 -*-
"""A amostra da legenda (o quadradinho de cada material) não é piso da obra.

🩸 24/09/2026, job b6df4f3d (prancha de PISO): 15 hachuras de exatamente
1,73 m² em 15 layers diferentes — as amostras de carpete, cerâmica, vinílico…
da legenda. A planilha saiu com "Piso vinílico 1,73 m² ✓ MEDIDO" (não existe
vinílico na obra) e o porcelanato com 28,39 m² (real: 24,92 + 2 amostras).
No arquivo real, com o conserto: 23 → 7 hachuras; porcelanato 24,92 m²; as
outras 4 pranchas do projeto não mudam.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dwg_extractor import HatchArea, separar_amostras_de_legenda as separar  # noqa: E402


def _h(layer, area, fill=1.0):
    return HatchArea(layer=layer, area=area, pattern="ANSI31", bbox=(0, 0, 1, 1),
                     preenchimento=fill)


def test_o_caso_real_as_amostras_saem_e_o_piso_fica():
    amostras = [_h("PIS-CAR-%02d" % k, 1.73) for k in range(1, 10)] + \
               [_h("PIS-VINIL", 1.73), _h("PIS-CER-03", 1.7301)]
    piso = _h("PIS-CER-03", 24.92, fill=0.83)
    fica, fora = separar(amostras + [piso])
    assert fica == [piso]
    assert len(fora) == 11


def test_CONTROLE_mesma_area_no_MESMO_layer_fica():
    """10 banheiros iguais de hotel: mesma área, UM layer — é obra."""
    banheiros = [_h("PIS-BWC", 3.2) for _ in range(10)]
    assert separar(banheiros) == (banheiros, [])


def test_CONTROLE_dois_layers_iguais_nao_bastam():
    a = [_h("PISO-A", 2.0), _h("PISO-B", 2.0)]
    assert separar(a)[1] == []


def test_CONTROLE_area_grande_repetida_fica():
    """Três salas iguais de 12 m² em três acabamentos: acima de 5 m², fica."""
    a = [_h("PISO-A", 12.0), _h("PISO-B", 12.0), _h("PISO-C", 12.0)]
    assert separar(a)[1] == []


def test_CONTROLE_nao_retangular_fica():
    a = [_h("PISO-A", 1.73, fill=0.7), _h("PISO-B", 1.73, fill=0.7), _h("PISO-C", 1.73, fill=0.7)]
    assert separar(a)[1] == []


def test_CONTROLE_areas_diferentes_ficam():
    a = [_h("PISO-A", 1.73), _h("PISO-B", 1.90), _h("PISO-C", 2.10)]
    assert separar(a)[1] == []


def test_o_extrator_CHAMA_o_filtro(tmp_path):
    """Guarda de call site: DXF de verdade com 3 amostras iguais em 3 layers +
    o piso real. Só o piso real pode sobrar em `hatches`."""
    import ezdxf
    from dwg_extractor import extract_dxf
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for k, ly in enumerate(("PIS-CAR-01", "PIS-CER-01", "PIS-VINIL")):
        h = msp.add_hatch(dxfattribs={"layer": ly})
        x = 100 + k * 3
        h.paths.add_polyline_path([(x, 0), (x + 1.3, 0), (x + 1.3, 1.33), (x, 1.33)], is_closed=True)
    h = msp.add_hatch(dxfattribs={"layer": "PIS-CER-03"})
    h.paths.add_polyline_path([(0, 0), (6, 0), (6, 4), (3, 4), (3, 5), (0, 5)], is_closed=True)
    p = tmp_path / "piso.dxf"
    doc.saveas(p)
    ext = extract_dxf(str(p))
    assert [x.layer for x in ext.hatches] == ["PIS-CER-03"], [(x.layer, x.area) for x in ext.hatches]
    assert "amostras_legenda" in ext.metadata


def test_vazio():
    assert separar([]) == ([], [])
    assert separar(None) == ([], [])
