# -*- coding: utf-8 -*-
"""A espessura da parede desmente a unidade lida → ressalva de ESCALA.

🩸 30/09/2026 — H51 do estudo do acervo. Desenho em CENTÍMETRO com o cabeçalho
dizendo MILÍMETRO ($INSUNITS = 4): tudo sai 10× menor, e com selo. 4 jobs de
cliente (3 clientes), a régua de cotas "não-decidiu" em todos: "parede de
alvenaria 49,51 ml ✓" (real ≈ 495 m) aprovada pelo cliente, laje ×100; numa
casa de 46,79 m², "tubulação 1,42 m ✓"; num prédio, "condutos 5,28 ml ✓".
Lido em mm, o par de faces desses desenhos dava 1,0–2,0 cm; nos 17 desenhos
certos da varredura do estudo, 16–20 cm.
v1: detecta e vira ressalva de escala (m/m²/m³ sem selo + aviso). Não troca o
fator — um dos arquivos mistura cm e mm.
"""
import math
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import dwg_extractor as dx  # noqa: E402
import engine_rules as er  # noqa: E402


def _faces(u=1.0, esp=15.0, ox=0.0, oy=0.0, xs=(0, 400, 800, 1200), ys=(0, 300, 600)):
    """As duas faces de cada parede de uma grade de cômodos. Medidas em cm;
    `u` = unidades do desenho por cm (cm: 1, mm: 10, m: 0,01)."""
    h = esp * u / 2.0
    out = []
    for y in ys:
        for x0, x1 in zip(xs, xs[1:]):
            for s in (-h, h):
                out.append((((ox + x0) * u, (oy + y) * u + s), ((ox + x1) * u, (oy + y) * u + s)))
    for x in xs:
        for y0, y1 in zip(ys, ys[1:]):
            for s in (-h, h):
                out.append((((ox + x) * u + s, (oy + y0) * u), ((ox + x) * u + s, (oy + y1) * u)))
    return out


def _walls(faces, uf, layer="PAREDE", curvo=False):
    return [dx.WallSegment(layer=layer, length=math.dist(a, b) * uf, start=a, end=b, curvo=curvo)
            for a, b in faces]


def _r(faces, uf, status="nao-decidiu", layer="PAREDE"):
    return dx.unidade_contradita_pela_parede(_walls(faces, uf, layer), uf, status)


# ══════════════════════════════════════════════════════════════════════════
#  1. A régua
# ══════════════════════════════════════════════════════════════════════════
def test_planta_em_cm_lida_em_mm_da_parede_de_1_5_cm():
    r = _r(_faces(), 0.001)
    assert r and r["k"] == 10, r
    assert r["espessura_cm"] == pytest.approx(1.5, abs=0.01), r
    assert r["fracao_fina"] == 1.0 and r["em_par"] == 1.0, r


def test_planta_em_metro_lida_em_cm_e_x100():
    r = _r(_faces(u=0.01), 0.01)
    assert r and r["k"] == 100 and r["espessura_cm"] == pytest.approx(0.15, abs=0.001), r


@pytest.mark.parametrize("u,uf", [(1.0, 0.01), (10.0, 0.001), (0.01, 1.0)])
def test_CONTROLE_unidade_certa_nao_dispara(u, uf):
    assert _r(_faces(u=u), uf) == {}


def test_CONTROLE_grossa_demais_fica_de_fora_na_v1():
    # mm lido como cm: parede de 1,5 m — o sentido "grossa" pegou layer de VISTA
    assert _r(_faces(u=10.0), 0.01) == {}


@pytest.mark.parametrize("status", ["validada", "corrigida", "corrigida_lfac", "provada_por_rotulo"])
def test_CONTROLE_unidade_provada_nao_dispara(status):
    # linha de reboco a 3–4 cm da face: moda "fina" num desenho certo (1 falso
    # alarme na varredura) — lá as cotas provaram o metro
    assert _r(_faces(), 0.001, status=status) == {}


@pytest.mark.parametrize("status", [None, "nao-decidiu", "corrigida_plausibilidade", "ambigua"])
def test_unidade_nao_provada_dispara(status):
    assert _r(_faces(), 0.001, status=status).get("k") == 10


@pytest.mark.parametrize("layer", ["PAREDE-FACHADA", "A-WALL-ELEV", "PAREDES CORTE AA",
                                   "Alvenaria - Vista Frontal", "PAREDE SEÇÃO", "ALV ELEVAÇÃO"])
def test_CONTROLE_layer_de_vista_fica_de_fora(layer):
    assert er.layer_e_parede(layer)          # é parede pelo nome — sai por ser VISTA
    assert _r(_faces(), 0.001, layer=layer) == {}


@pytest.mark.parametrize("layer", ["PAREDE ELEVADOR", "ALV-DETALHAMENTO", "A-WALL"])
def test_layer_de_parede_que_so_parece_vista_entra(layer):
    assert _r(_faces(), 0.001, layer=layer).get("k") == 10


def test_CONTROLE_layer_que_nao_e_parede():
    assert _r(_faces(), 0.001, layer="MOBILIARIO") == {}


def test_CONTROLE_parede_de_linha_unica():
    # sem par de faces, a parceira mais perto é a parede do outro lado do cômodo
    assert _r(sorted(set(_faces(esp=0.0))), 0.001) == {}


def test_CONTROLE_desenho_misto_com_muito_trecho_ja_plausivel():
    # a planta em cm e outra, maior, em mm: nenhum fator serve pro arquivo todo
    assert _r(_faces() + _faces(u=10.0, ox=5000), 0.001) == {}


def test_detalhe_pequeno_em_outra_unidade_nao_segura_a_regua():
    # o caso do estudo: a planta em cm e um detalhe distante em mm (< 20%)
    r = _r(_faces() + _faces(u=10.0, ox=5000, xs=(0, 50), ys=(0,)), 0.001)
    assert r.get("k") == 10, r


def test_CONTROLE_menos_da_metade_em_par():
    soltas = [((0.0, 10000.0 + 2000 * i), (1000.0, 10000.0 + 2000 * i)) for i in range(40)]
    assert _r(_faces() + soltas, 0.001) == {}


def test_CONTROLE_poucos_trechos():
    assert _r(_faces(xs=(0, 400), ys=(0,)), 0.001) == {}


def test_CONTROLE_poucos_pares_mesmo_com_trechos_soltos():
    # 14 faces em par + 8 trechos curtos soltos: passa do piso de trechos,
    # não do de pares
    soltas = [((0.0, 10000.0 + 2000 * i), (50.0, 10000.0 + 2000 * i)) for i in range(8)]
    assert _r(_faces(xs=(0, 400, 800), ys=(0, 300)) + soltas, 0.001) == {}


def test_CONTROLE_desenho_misto_com_um_quarto_ja_plausivel():
    # 25% do que pareou já dá 15 cm: não há um fator que sirva pro arquivo
    assert _r(_faces() + _faces(u=10.0, ox=5000, xs=(0, 60), ys=(0, 40)), 0.001) == {}


def test_CONTROLE_metade_fina_metade_em_nenhuma_faixa():
    # pares a 4,5 cm na unidade lida: nem fina (×10 daria 45 cm) nem plausível
    assert _r(_faces() + _faces(esp=45.0, ox=2000), 0.001) == {}


def test_CONTROLE_curva_fica_de_fora():
    ws = _walls(_faces(), 0.001, curvo=True)
    assert dx.unidade_contradita_pela_parede(ws, 0.001, None) == {}


def test_parede_em_polilinha_fechada_pelos_lados():
    ws = []
    esp = 15.0
    for (a, b) in _faces(esp=0.0)[::2]:                   # um eixo por parede
        (x0, y0), (x1, y1) = a, b
        if y0 == y1:
            q = [(x0, y0 - esp / 2), (x1, y0 - esp / 2), (x1, y0 + esp / 2), (x0, y0 + esp / 2)]
        else:
            q = [(x0 - esp / 2, y0), (x0 + esp / 2, y0), (x0 + esp / 2, y1), (x0 - esp / 2, y1)]
        pts = tuple((x, y, 0.0) for x, y in q + q[:1])
        per = sum(math.dist(p[:2], r[:2]) for p, r in zip(pts, pts[1:]))
        ws.append(dx.WallSegment(layer="PAREDE", length=per * 0.001, start=q[0], end=q[0], pontos=pts))
    r = dx.unidade_contradita_pela_parede(ws, 0.001, None)
    assert r.get("k") == 10 and r["espessura_cm"] == pytest.approx(1.5, abs=0.01), r


# ══════════════════════════════════════════════════════════════════════════
#  2. O texto e o selo
# ══════════════════════════════════════════════════════════════════════════
def test_a_ressalva_diz_a_espessura_e_o_fator():
    t = dx.ressalva_da_parede_fina(_r(_faces(), 0.001), 0.001)
    for pedaco in ("1,5 cm de espessura", "milímetro", "10× maior", "centímetro",
                   "dariam 15 cm", "confira uma medida conhecida"):
        assert pedaco in t, (pedaco, t)


def test_a_ressalva_do_x100():
    t = dx.ressalva_da_parede_fina(_r(_faces(u=0.01), 0.01), 0.01)
    assert "0,15 cm" in t and "100× maior" in t and "metro" in t and "dariam 15 cm" in t, t


def test_sem_achado_sem_texto():
    assert dx.ressalva_da_parede_fina({}, 0.001) == ""


def test_a_ressalva_so_rebaixa_o_que_depende_de_escala():
    md = {"unidade_contradita_pela_parede": "x"}
    assert er.extraction_has_quality_caveat(md)
    assert er.caveat_atinge_unidade(md, "m") is True
    assert er.caveat_atinge_unidade(md, "m²") is True
    assert er.caveat_atinge_unidade(md, "un") is False


def test_o_cliente_le_o_motivo_da_parede():
    import main
    txt = dx.ressalva_da_parede_fina(_r(_faces(), 0.001), 0.001)
    arq = main._resumo_escala_arquivo("prancha.dwg", {"unidade_contradita_pela_parede": txt,
                                                      "unidade_desenho": "Milímetros"})
    assert arq["status"] == "alerta" and "espessura" in arq["alerta"], arq
    linha = next(l for l in main._linhas_escala_projeto([arq]) if l.startswith("⚠ ESCALA SUSPEITA"))
    assert "Motivo: as paredes medem 1,5 cm" in linha, linha
    assert "áreas. Por isso" in linha, linha


@pytest.mark.parametrize("outra", ["unidade_cega", "alerta_unidade", "unidade_por_desempate"])
def test_a_parede_e_o_motivo_mais_concreto(outra):
    import main
    arq = main._resumo_escala_arquivo("prancha.dwg", {"unidade_contradita_pela_parede": "as paredes medem X",
                                                      outra: "outro motivo"})
    assert arq["alerta"].startswith("as paredes medem"), arq


# ══════════════════════════════════════════════════════════════════════════
#  3. De ponta a ponta
# ══════════════════════════════════════════════════════════════════════════
def _dxf(tmp_path, faces, insunits=4, extra=None, doc=None):
    d = doc or ezdxf.new("R2010")
    d.header["$INSUNITS"] = insunits
    msp = d.modelspace()
    for a, b in faces:
        msp.add_line(a, b, dxfattribs={"layer": "PAREDE"})
    if extra:
        extra(msp)
    p = str(tmp_path / "planta.dxf")
    d.saveas(p)
    return p


def test_de_ponta_a_ponta_cm_declarado_como_mm(tmp_path):
    md = dx.extract_dxf(_dxf(tmp_path, _faces())).metadata
    assert float(md["fator_para_metros"]) == 0.001, md.get("fator_para_metros")
    assert "1,5 cm" in (md.get("unidade_contradita_pela_parede") or ""), sorted(md)
    assert er.extraction_has_quality_caveat(md)


def test_CONTROLE_de_ponta_a_ponta_cm_declarado_como_cm(tmp_path):
    md = dx.extract_dxf(_dxf(tmp_path, _faces(), insunits=5)).metadata
    assert not md.get("unidade_contradita_pela_parede"), md.get("unidade_contradita_pela_parede")


def test_de_ponta_a_ponta_cota_que_valida_o_mm_derruba(tmp_path, monkeypatch):
    monkeypatch.setattr(dx, "_validate_unit_by_dimensions", lambda doc, uf: {
        "status": "validada", "n_cotas": 30, "unidade_nome": "milímetro"})
    md = dx.extract_dxf(_dxf(tmp_path, _faces())).metadata
    assert md.get("regua_cotas_status") == "validada", md.get("regua_cotas_status")
    assert not md.get("unidade_contradita_pela_parede"), md.get("unidade_contradita_pela_parede")


def _pisos_em_mm(msp):
    for x, y, w, h, t in ((20000, 0, 4000, 3000, "12,00 m²"), (30000, 0, 5000, 2000, "10,00 m²")):
        msp.add_lwpolyline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], close=True,
                           dxfattribs={"layer": "PISO"})
        msp.add_text(t, dxfattribs={"height": 100, "insert": (x + w / 2, y + h / 2), "layer": "TEXTO"})


def test_de_ponta_a_ponta_rotulo_de_area_que_bate_prova_e_derruba(tmp_path):
    md = dx.extract_dxf(_dxf(tmp_path, _faces(), extra=_pisos_em_mm)).metadata
    assert md.get("unidade_provada_por_rotulo"), sorted(md)
    assert not md.get("unidade_contradita_pela_parede")
    assert md.get("unidade_contradita_pela_parede_superada_por_rotulo")


def test_de_ponta_a_ponta_nota_com_cotas_que_prova_o_mm_derruba(tmp_path):
    from test_unidade_pela_nota_do_desenho import _cotas, _doc
    d = _doc("MEDIDAS EM MILÍMETROS", _cotas(30))
    assert dx._detect_unit_factor(d) == 0.001 and not getattr(d, "_aiarq_unidade_palpite", None)
    md = dx.extract_dxf(_dxf(tmp_path, _faces(oy=5000), insunits=0, doc=d)).metadata
    assert not md.get("unidade_contradita_pela_parede"), md.get("unidade_contradita_pela_parede")


def test_de_ponta_a_ponta_sem_nota_o_palpite_ganha_as_duas(tmp_path):
    from test_unidade_pela_nota_do_desenho import _doc
    md = dx.extract_dxf(_dxf(tmp_path, _faces(oy=5000), insunits=0, doc=_doc(None))).metadata
    assert md.get("unidade_cega") and md.get("unidade_contradita_pela_parede"), sorted(md)
