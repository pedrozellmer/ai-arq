# -*- coding: utf-8 -*-
"""Viewport com a medida em METRO (e o `/U` calado) deixa de sumir.

🩸 01/10/2026 — estudo do acervo (H68). No PDF do AutoCAD/Revit com o modelo em
metro, a folha de papel sai com `/C` em mm (25,4/72 = 0,35278) e cada viewport de
desenho com `/C` em METRO por ponto: 0,03528 = 1:100, 0,02646 = 1:75, 0,01764 =
1:50, 0,00882 = 1:25. O motor dividia por cm/pt e achava 1:1 / 0,75 / 0,5 /
0,25, que o `_snap_scale` descarta (< 5). O desenho principal sumia, e:
  · sobrava um recorte pequeno como principal — 1:11 no lugar de 1:100 num
    viewport de 85 % da folha; 1:40 no lugar de 1:200;
  · ou a escala caía pro carimbo, e o recorte do desenho principal se perdia.
E um recorte do PAPEL (C = 0,35278, papel 1:1 em mm) era lido como 1:10 em cm,
em 3 folhas de um mesmo projeto cuja folha irmã diz 1:25.

📏 Acervo local, 92 páginas com /VP: 57 ganham escala, 6 trocam de errada pra
certa, 9 ficam iguais (os PDFs com /C em cm de verdade) e 20 seguem sem viewport
útil. Onde a produção tinha carimbo ou cota na mesma folha, bate em 13 de 15.

🪤 Fixture SINTÉTICA (pikepdf), nunca arquivo de cliente.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pikepdf  # noqa: E402
import pdfvec_layers as pl  # noqa: E402

_PAPEL = 25.4 / 72.0                  # 0,35278: papel 1:1 em mm
_M = lambda den: den * 2.54 / 72.0 / 100.0     # noqa: E731  /C em m/pt
_CM = lambda den: den * 2.54 / 72.0            # noqa: E731  /C em cm/pt

_PAG = (2592, 1728)


def _pdf(tmp_path, vps, nome="sintetico.pdf", u=""):
    """`vps` = [(C, (x0, y0, x1, y1)), ...]. Sem desenho: o que está sob teste é a
    leitura do /Measure."""
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=_PAG)
    lista = []
    for c, bb in vps:
        nf = pikepdf.Dictionary(Type=pikepdf.Name("/NumberFormat"), C=float(c))
        nf.U = pikepdf.String(u)
        medida = pikepdf.Dictionary(Type=pikepdf.Name("/Measure"),
                                    Subtype=pikepdf.Name("/RL"), X=pikepdf.Array([nf]))
        lista.append(pikepdf.Dictionary(Type=pikepdf.Name("/Viewport"),
                                        BBox=pikepdf.Array(list(bb)), Measure=medida))
    pdf.pages[0].VP = pikepdf.Array(lista)
    alvo = str(tmp_path / nome)
    pdf.save(alvo)
    return alvo


_FOLHA = (0, 0, _PAG[0], _PAG[1])           # ≥ 90 % da página: a folha
_GRANDE = (100, 100, 2300, 1600)            # ~ 74 % da página
_MEDIO = (100, 100, 1100, 900)
_PEQUENO = (2350, 100, 2550, 400)


def test_desenho_em_metro_le_1_100_e_nao_o_recorte_de_1_11(tmp_path):
    """O caso real: desenho principal a 1:100 em metro e um recorte pequeno
    que, lido como cm, dava 1:11 e virava o principal."""
    arq = _pdf(tmp_path, [(_PAPEL, _FOLHA), (_M(100), _GRANDE), (0.38293, _PEQUENO)])
    r = pl.scale_from_viewport(arq)
    assert r.get("main_scale") == 100, r
    assert r.get("snapped") is True, r
    assert r.get("unidade") == "m", r


def test_em_metro_o_viewport_da_a_escala_mas_NAO_recorta(tmp_path):
    """🪤 Medido no acervo: recortar a medição no maior viewport derrubava área
    PROVADA por cota (294 m² com 3 cotas → 27,8 m²). Na página em metro a
    escala vem do viewport e a região medida fica a de hoje."""
    arq = _pdf(tmp_path, [(_PAPEL, _FOLHA), (_M(100), _GRANDE), (_M(50), _PEQUENO)])
    r = pl.scale_from_viewport(arq)
    assert r.get("main_scale") == 100, r
    assert r.get("main_bbox") is None, r
    assert len(r.get("viewports") or []) == 2, r


def test_CONTROLE_em_centimetro_o_recorte_continua(tmp_path):
    arq = _pdf(tmp_path, [(_PAPEL, _FOLHA), (_CM(100), _GRANDE), (_CM(50), _PEQUENO)])
    r = pl.scale_from_viewport(arq)
    assert r.get("main_bbox") == [float(x) for x in _GRANDE], r


def test_varias_escalas_em_metro_cada_uma_no_seu_lugar(tmp_path):
    arq = _pdf(tmp_path, [(_M(50), _GRANDE), (_M(25), _MEDIO), (_M(100), _PEQUENO)])
    r = pl.scale_from_viewport(arq)
    assert r.get("main_scale") == 50, r
    assert sorted(v["scale"] for v in r["viewports"]) == [25, 50, 100], r


def test_recorte_do_papel_sai_quando_a_folha_e_papel_mm(tmp_path):
    """C = 0,35278 numa folha cujo quadro também é papel-mm é carimbo/legenda,
    não desenho: lido como cm dava 1:10, como metro 1:1000."""
    arq = _pdf(tmp_path, [(_PAPEL, _FOLHA), (_PAPEL, _GRANDE), (_M(25), _MEDIO),
                          (_M(25), _PEQUENO)])
    r = pl.scale_from_viewport(arq)
    assert r.get("main_scale") == 25, r
    assert all(v["scale"] not in (10, 1000) for v in r["viewports"]), r


def test_CONTROLE_sem_folha_o_0_35278_fica_como_era(tmp_path):
    """🪤 Sem a folha pra dizer que o papel é mm, 0,35278 é ambíguo (mm 1:1, cm
    1:10, m 1:1000): fica o que era — 1:10 em cm."""
    arq = _pdf(tmp_path, [(_PAPEL, _GRANDE), (_CM(75), _MEDIO)])
    r = pl.scale_from_viewport(arq)
    assert r.get("main_scale") == 10, r
    assert r.get("unidade") == "cm", r


def test_CONTROLE_pdf_em_centimetro_de_verdade_segue_igual(tmp_path):
    arq = _pdf(tmp_path, [(_PAPEL, _FOLHA), (_CM(100), _GRANDE), (_CM(50), _MEDIO),
                          (_CM(25), _PEQUENO)])
    r = pl.scale_from_viewport(arq)
    assert r.get("main_scale") == 100, r
    assert r.get("unidade") == "cm", r


def test_CONTROLE_empate_fica_no_centimetro(tmp_path):
    """Um casa como cm, outro como metro: não dá pra afirmar — segue como era."""
    arq = _pdf(tmp_path, [(_CM(50), _GRANDE), (_M(100), _MEDIO)])
    r = pl.scale_from_viewport(arq)
    assert r.get("unidade") == "cm", r
    assert r.get("main_scale") == 50, r


def test_o_U_declarado_MANDA(tmp_path):
    """Declaração explícita ganha da maioria, nos dois sentidos."""
    arq = _pdf(tmp_path, [(_M(100), _GRANDE), (_M(50), _MEDIO)], u="cm",
               nome="declarado_cm.pdf")
    r = pl.scale_from_viewport(arq)
    assert r.get("unidade") != "m", (
        "o /U dizia centímetro e a estatística passou por cima: %s" % r)

    arq2 = _pdf(tmp_path, [(_CM(100), _GRANDE), (_M(50), _MEDIO)], u="m",
                nome="declarado_m.pdf")
    r2 = pl.scale_from_viewport(arq2)
    assert r2.get("unidade") == "m" and r2.get("main_scale") == 50, r2


def test_CONTROLE_polegada_continua_polegada(tmp_path):
    imp = 32 / 72.0
    arq = _pdf(tmp_path, [(imp, _GRANDE), (imp, _MEDIO)])
    r = pl.scale_from_viewport(arq)
    assert r.get("unidade") == "polegada" and r.get("main_scale") == 32, r


def test_a_decisao_da_unidade_e_CHAMAVEL():
    m100, m50, cm50 = {"c": _M(100), "u": ""}, {"c": _M(50), "u": ""}, {"c": _CM(50), "u": ""}
    assert pl._pagina_e_metro([m100, m50]) is True
    assert pl._pagina_e_metro([m100, cm50]) is False          # empate
    assert pl._pagina_e_metro([cm50, cm50]) is False
    assert pl._pagina_e_metro([]) is False
    assert pl._pagina_e_metro([{"c": _M(100), "u": "cm"}, {"c": _M(50), "u": "cm"}]) is False
    assert pl._e_papel_mm(0.35278) and not pl._e_papel_mm(_M(100))
