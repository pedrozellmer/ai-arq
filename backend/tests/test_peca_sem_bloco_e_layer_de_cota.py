# -*- coding: utf-8 -*-
"""A peça desenhada UMA A UMA (sem bloco) chega à IA como CONTAGEM; o layer
que é só COTA explodida, ou só a BORDA dessas peças, não prova comprimento.

🩸 30/09/2026 (job 9a2c5d87, planta de modulação de alvenaria da 1ª fiada).
Os layers eram nomeados pela cor ("1", "218", "250", "205"). A IA só via o
COMPRIMENTO de cada um e montou "linhas de modulação" com 3 deles — e as 3
saíram "✓ MEDIDO", porque o número batia com o layer:
  · "250" = 276 linhas de COTA explodida (o valor escrito ao lado de cada uma);
  · "218" = a borda de 787 quadrados de 14 × 14 cm (os furos com graute e aço);
  · "205" = os eixos.
O que se orça — 776 blocos de 19 × 39, 31 de 19 × 19, 18 de 14 × 19, os 787
grautes — estava desenhado peça por peça, como retângulo, e não chegava.
📏 Acervo local (93 DXF): peça repetida sem bloco em 30 desenhos (placa de
forro 62,5 × 125, luminária 24 × 24 desenhada como quadrado, paver 10 × 20,
caixa elétrica, vaga 230 × 420); layer de cota explodida sem nome de cota, só
este. Produção, 90 dias: comprimento de layer SEM NOME com "✓ MEDIDO", só este.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

import dwg_extractor as dx  # noqa: E402
import engine_rules as er  # noqa: E402


def _ret(msp, x, y, a, b, layer, fechar=True):
    pts = [(x, y), (x + b, y), (x + b, y + a), (x, y + a)]
    if fechar:
        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})
    else:
        msp.add_lwpolyline(pts, close=False, dxfattribs={"layer": layer})


def _doc_pecas():
    d = ezdxf.new("R2010")
    msp = d.modelspace()
    for i in range(12):
        _ret(msp, i * 50, 0, 19, 39, "1")                    # 12 blocos 19 × 39 (cm)
    for i in range(5):
        _ret(msp, i * 50, 100, 19, 19, "1")                  # 5 meios-blocos: abaixo do mínimo
    for i in range(11):
        msp.add_circle((i * 50, 200), 2.0, dxfattribs={"layer": "226"})
    for i in range(15):
        _ret(msp, i * 50, 300, 14, 14, "CHAMADA")            # balão de chamada: anotação
    for i in range(12):                                      # losango (diagonais 20 e 10): não é retângulo
        msp.add_lwpolyline([(i * 50, 400), (i * 50 + 10, 405), (i * 50, 410), (i * 50 - 10, 405)],
                           close=True, dxfattribs={"layer": "1"})
    for i in range(12):                                      # quadrado GIRADO 45°: é peça (outra medida)
        msp.add_lwpolyline([(i * 50, 600), (i * 50 + 10, 610), (i * 50, 620), (i * 50 - 10, 610)],
                           close=True, dxfattribs={"layer": "GIRADO"})
    for i in range(12):
        _ret(msp, i * 50, 500, 19, 39, "ABERTO", fechar=False)   # polilinha aberta
    return d


# ══════════════════════════════════════════════════════════════════════════
#  1. A peça repetida sem bloco
# ══════════════════════════════════════════════════════════════════════════
def test_o_caso_o_bloco_desenhado_como_retangulo_vira_contagem():
    ob = dx.objetos_repetidos_sem_bloco(_doc_pecas().modelspace(), 0.01)
    assert ob.get("1") == [{"forma": "retângulo", "a_cm": 19.0, "b_cm": 39.0, "n": 12,
                            "borda_m": 13.92, "concentrada": False}], ob.get("1")


def test_circulo_repetido_tambem():
    ob = dx.objetos_repetidos_sem_bloco(_doc_pecas().modelspace(), 0.01)
    assert ob.get("226") and ob["226"][0]["forma"] == "círculo" and ob["226"][0]["n"] == 11, ob.get("226")
    assert ob["226"][0]["r_cm"] == 2.0


@pytest.mark.parametrize("layer", ["CHAMADA", "ABERTO"])
def test_CONTROLE_anotacao_e_polilinha_aberta_nao_sao_peca(layer):
    ob = dx.objetos_repetidos_sem_bloco(_doc_pecas().modelspace(), 0.01)
    assert layer not in ob, ob.get(layer)


def test_CONTROLE_losango_e_poucas_pecas_nao_contam():
    ob = dx.objetos_repetidos_sem_bloco(_doc_pecas().modelspace(), 0.01)
    assert len(ob.get("1") or []) == 1, ob.get("1")      # nem os 5 meios-blocos, nem o losango


def test_peca_girada_tambem_conta():
    ob = dx.objetos_repetidos_sem_bloco(_doc_pecas().modelspace(), 0.01)
    assert (ob.get("GIRADO") or [{}])[0].get("n") == 12, ob.get("GIRADO")


def test_a_borda_das_pecas_marca_o_layer():
    ob = {"1": [{"forma": "retângulo", "a_cm": 19.0, "b_cm": 39.0, "n": 776, "borda_m": 900.16}]}
    assert dx.layers_de_borda_de_objeto(ob, {"1": 939.17}) == {"1": 0.96}


def test_CONTROLE_layer_com_obra_alem_das_pecas_nao_e_borda():
    ob = {"PAREDE": [{"forma": "retângulo", "a_cm": 19.0, "b_cm": 39.0, "n": 10, "borda_m": 11.6}]}
    assert dx.layers_de_borda_de_objeto(ob, {"PAREDE": 120.0}) == {}


# ══════════════════════════════════════════════════════════════════════════
#  2. O layer de cota explodida
# ══════════════════════════════════════════════════════════════════════════
def _doc_cotas(n_cotas=12, extra_m=0.0, layer="250"):
    d = ezdxf.new("R2010")
    msp = d.modelspace()
    for i in range(n_cotas):
        y = i * 60.0
        L = 101.0 + i
        msp.add_line((0, y), (L, y), dxfattribs={"layer": layer})
        msp.add_text("%g" % L, dxfattribs={"height": 10, "insert": (L / 2 - 0.45 * 10 * 3, y + 3),
                                          "layer": "216"})
    if extra_m:
        msp.add_line((0, -500), (extra_m, -500), dxfattribs={"layer": layer})
    return d


def test_o_caso_o_layer_de_cotas_explodidas_e_de_cota():
    lc = dx.layers_de_cota_explodida(_doc_cotas().modelspace())
    assert lc.get("250", {}).get("cotas") == 12, lc
    assert lc["250"]["fracao"] == 1.0


def test_CONTROLE_layer_com_cota_mas_quase_tudo_obra_nao_e_de_cota():
    lc = dx.layers_de_cota_explodida(_doc_cotas(extra_m=5000.0).modelspace())
    assert "250" not in lc, lc


def test_CONTROLE_poucas_cotas_nao_fazem_layer_de_cota():
    assert dx.layers_de_cota_explodida(_doc_cotas(n_cotas=4).modelspace()) == {}


def test_a_unidade_e_o_layer_usam_a_mesma_regua():
    msp = _doc_cotas().modelspace()
    cas = dx._cotas_explodidas_casadas(msp)
    assert len(cas) == 12 and {c[0] for c in cas} == {"250"} and {c[2] for c in cas} == {1.0}, cas
    assert dx._cotas_explodidas(msp) == {1.0: 12}


# ══════════════════════════════════════════════════════════════════════════
#  3. O que a IA lê
# ══════════════════════════════════════════════════════════════════════════
def _extracao(md, walls):
    Parede = type("Parede", (), {})
    ws = []
    for ly, L in walls.items():
        w = Parede()
        w.layer, w.length = ly, L
        ws.append(w)
    return dx.DXFExtraction(filename="p.dxf", blocks=[], walls=ws, hatches=[], texts=[],
                            layers=list(walls), dimensions=[], metadata=md)


_MD = {"objetos_sem_bloco": {"1": [{"forma": "retângulo", "a_cm": 19.0, "b_cm": 39.0, "n": 776,
                                    "borda_m": 900.16}],
                             "226": [{"forma": "círculo", "r_cm": 1.3, "n": 817, "borda_m": 66.7}]},
       "layers_de_cota": {"250": {"cotas": 276, "fracao": 0.73}},
       "layers_de_borda": {"1": 0.96}}


def test_a_ia_le_a_contagem_das_pecas():
    p = _extracao(dict(_MD), {"1": 939.17, "250": 787.27, "PAREDE": 30.0}).to_structured_prompt()
    assert "OBJETOS DESENHADOS PEÇA POR PEÇA" in p
    assert "1: 776 retângulos de 19 × 39 cm" in p, p
    assert "817 círculos de raio 1,3 cm" in p, p


def test_a_ia_le_que_o_layer_e_cota_e_que_o_outro_e_borda():
    p = _extracao(dict(_MD), {"1": 939.17, "250": 787.27, "PAREDE": 30.0}).to_structured_prompt()
    linha_250 = next(l for l in p.splitlines() if l.strip().startswith("250:"))
    linha_1 = next(l for l in p.splitlines() if l.strip().startswith("1: 939"))
    linha_par = next(l for l in p.splitlines() if l.strip().startswith("PAREDE:"))
    assert "LINHAS DE COTA" in linha_250 and "276" in linha_250, linha_250
    assert "BORDAS das peças" in linha_1, linha_1
    assert "⚠" not in linha_par, linha_par


def test_os_registros_de_maquina_nao_vao_crus_pro_prompt():
    p = _extracao(dict(_MD), {"1": 939.17}).to_structured_prompt()
    for k in ("objetos_sem_bloco:", "layers_de_cota:", "layers_de_borda:"):
        assert k not in p, k


def test_com_a_planta_repetida_a_ia_e_avisada_que_a_contagem_soma_as_copias():
    md = dict(_MD, planta_repetida="a planta aparece 5 vezes")
    p = _extracao(md, {"1": 939.17}).to_structured_prompt()
    assert "estas contagens podem somar as cópias" in p, p
    assert "NÃO divida" in p


def test_CONTROLE_sem_planta_repetida_nao_ha_aviso_de_copia():
    p = _extracao(dict(_MD), {"1": 939.17}).to_structured_prompt()
    assert "podem somar as cópias" not in p


# ══════════════════════════════════════════════════════════════════════════
#  4. O selo: o que não prova comprimento
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("nome,esperado", [("250", True), ("218", True), ("0", True),
                                           ("ARQ-250", False), ("PAREDE", False), ("", False), (None, False)])
def test_layer_sem_nome(nome, esperado):
    assert er.layer_sem_nome(nome) is esperado


def test_os_layers_que_nao_provam_vem_da_extracao():
    assert er.layers_que_nao_provam(_MD) == {"250", "1"}
    assert er.layers_que_nao_provam({}) == set()


class _Extr:
    def __init__(self, md, walls):
        self.metadata = md
        self._w = walls

    def get_walls_by_layer(self):
        return dict(self._w)

    def get_layers_secao_de_parede(self):
        return set()

    def get_areas_by_layer(self):
        return {}

    def get_polygon_areas_by_layer(self):
        return {}


def _roda(marcador, escopo, tamanho=1):
    import _executa
    import main
    esc = dict(vars(main))
    esc.update(escopo)
    return _executa.roda("process_job", marcador, esc, tamanho=tamanho)


def test_o_caso_a_chave_do_selo_nao_indexa_cota_borda_nem_layer_sem_nome():
    ex = _Extr(dict(_MD), {"250": 787.27, "1": 939.17, "205": 265.99, "PAREDE": 30.0})
    esc = _roda("_nao_prova_ig = _layers_que_nao_provam(extraction.metadata)",
                {"extraction": ex, "_indice_geom": {"comprimento": [], "area": [], "contagem": []}})
    idx = dict(esc["_indice_geom"]["comprimento"])
    assert idx == {"PAREDE": 30.0}, idx


def test_o_resgate_automatico_nao_preenche_com_cota_borda_nem_layer_sem_nome():
    ex = _Extr(dict(_MD), {"250": 787.27, "1": 939.17, "205": 265.99, "PAREDE": 30.0})
    esc = _roda("_nao_prova_rs = _layers_que_nao_provam(extraction.metadata)", {"extraction": ex})
    assert set(esc["_compr_ly"]) == {"PAREDE"}, esc["_compr_ly"]


def test_a_prova_da_geometria_com_o_indice_novo():
    # o número do layer "250" (787,27) bateria com a linha da IA — sem o índice, não prova
    ex = _Extr(dict(_MD), {"250": 787.27, "PAREDE": 30.0})
    esc = _roda("_nao_prova_ig = _layers_que_nao_provam(extraction.metadata)",
                {"extraction": ex, "_indice_geom": {"comprimento": [], "area": [], "contagem": []}})
    obs = "Fonte: comprimento calculado do layer 250 = 787,27 m (linhas de modulação)"
    assert er.prova_da_geometria(787.27, "m", obs, esc["_indice_geom"]) == ""
    assert er.prova_da_geometria(30.0, "m", "comprimento do layer PAREDE = 30 m", esc["_indice_geom"])


def test_de_ponta_a_ponta_no_desenho(tmp_path):
    d = _doc_cotas()
    msp = d.modelspace()
    for i in range(12):
        _ret(msp, 2000 + i * 50, 0, 19, 39, "1")
    d.header["$INSUNITS"] = 5
    p = str(tmp_path / "p.dxf")
    d.saveas(p)
    md = dx.extract_dxf(p).metadata
    assert "250" in (md.get("layers_de_cota") or {}), sorted(md)
    assert (md.get("objetos_sem_bloco") or {}).get("1"), sorted(md)
    assert "1" in (md.get("layers_de_borda") or {}), md.get("layers_de_borda")


def _item_confirmado_do_layer(layer):
    return {"item_num": "1", "description": "Linhas auxiliares do desenho",
            "unit": "ml", "quantity": 50.0, "confidence": "confirmado",
            "observations": "Fonte: comprimento do layer '%s' = 50.00 m." % layer}


def test_o_laco_rebaixa_a_linha_que_vem_de_layer_de_cota():
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    itens, _esc, _ = _laco_de_itens_de_producao(
        [_item_confirmado_do_layer("LINHAS-AUX")], areas={}, compr={"LINHAS-AUX": 50.0},
        extra={"_ly_cota": {"LINHAS-AUX"}})
    assert itens[0].confidence.value == "estimado", itens[0].observations
    assert "ANOTAÇÃO DO DESENHO" in itens[0].observations


def test_CONTROLE_o_mesmo_layer_sem_ser_de_cota_segue_como_veio():
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    itens, _esc, _ = _laco_de_itens_de_producao(
        [_item_confirmado_do_layer("LINHAS-AUX")], areas={}, compr={"LINHAS-AUX": 50.0},
        extra={"_ly_cota": set()})
    assert "ANOTAÇÃO DO DESENHO" not in itens[0].observations, itens[0].observations


def test_o_resgate_barra_cota_e_borda_mesmo_com_nome_de_letra():
    # o nome não diz nada (nem cota, nem anotação) — quem decide é a prova do desenho
    md = {"layers_de_cota": {"AUX-LINHAS": {"cotas": 30, "fracao": 0.7}},
          "layers_de_borda": {"BLOCOS": 0.99}}
    ex = _Extr(md, {"AUX-LINHAS": 120.0, "BLOCOS": 939.17, "PAREDE": 30.0})
    esc = _roda("_nao_prova_rs = _layers_que_nao_provam(extraction.metadata)", {"extraction": ex})
    assert set(esc["_compr_ly"]) == {"PAREDE"}, esc["_compr_ly"]
    esc = _roda("_nao_prova_ig = _layers_que_nao_provam(extraction.metadata)",
                {"extraction": ex, "_indice_geom": {"comprimento": [], "area": [], "contagem": []}})
    assert dict(esc["_indice_geom"]["comprimento"]) == {"PAREDE": 30.0}


# ══════════════════════════════════════════════════════════════════════════
#  5. 🩸 30/09 — o filhote evefe9af: balão não é pilar; peça sem bloco e
#     layer sem nome não saem ✓ (nem quando é a IA que marca)
# ══════════════════════════════════════════════════════════════════════════
def _doc_circulos(n_com_texto, n_total=12, texto="VISTA"):
    d = ezdxf.new("R2010")
    msp = d.modelspace()
    for i in range(n_total):
        msp.add_circle((i * 100, 0), 25.3, dxfattribs={"layer": "230"})
        if i < n_com_texto:
            msp.add_text(texto, dxfattribs={"height": 8, "insert": (i * 100 - 10, -4)})
    return d


def test_o_caso_balao_de_vista_nao_e_peca():
    assert "230" not in dx.objetos_repetidos_sem_bloco(_doc_circulos(12).modelspace(), 0.01)


def test_CONTROLE_circulo_sem_texto_e_peca():
    ob = dx.objetos_repetidos_sem_bloco(_doc_circulos(0).modelspace(), 0.01)
    assert ob.get("230") and ob["230"][0]["n"] == 12, ob


def test_CONTROLE_poucos_com_texto_ainda_e_peca():
    ob = dx.objetos_repetidos_sem_bloco(_doc_circulos(4).modelspace(), 0.01)
    assert ob.get("230") and ob["230"][0]["n"] == 12, ob


def _doc_legenda(espalhado, titulo="FAMÍLIA DE BLOCOS", titulo_longe=False):
    d = ezdxf.new("R2010")
    msp = d.modelspace()
    for i in range(12):
        x = i * 300 if espalhado else i * 30
        _ret(msp, x, 0 if espalhado else 10, 12, 12, "238")
    if titulo:
        msp.add_text(titulo, dxfattribs={"height": 10, "insert": (3500, 2800) if titulo_longe else (0, 60)})
    d.header["$EXTMIN"] = (0.0, 0.0, 0.0)
    d.header["$EXTMAX"] = (4000.0, 3000.0, 0.0)
    return d


def test_o_caso_pecas_no_canto_da_legenda_sao_marcadas():
    ob = dx.objetos_repetidos_sem_bloco(_doc_legenda(False).modelspace(), 0.01)
    assert ob["238"][0].get("concentrada") is True, ob
    md = {"objetos_sem_bloco": ob}
    p = _extracao(md, {"238": 5.0}).to_structured_prompt()
    assert "provável LEGENDA ou DETALHE" in p, p


def test_CONTROLE_pecas_espalhadas_nao_sao_legenda():
    ob = dx.objetos_repetidos_sem_bloco(_doc_legenda(True).modelspace(), 0.01)
    assert ob["238"][0].get("concentrada") is False, ob


def test_CONTROLE_grupo_pequeno_sem_titulo_de_legenda_nao_e_legenda():
    # as luminárias de uma sala pequena num desenho grande também cabem num canto
    ob = dx.objetos_repetidos_sem_bloco(_doc_legenda(False, titulo="SALA 12").modelspace(), 0.01)
    assert ob["238"][0].get("concentrada") is False, ob


def test_CONTROLE_titulo_de_legenda_longe_do_grupo_nao_marca():
    ob = dx.objetos_repetidos_sem_bloco(_doc_legenda(False, titulo_longe=True).modelspace(), 0.01)
    assert ob["238"][0].get("concentrada") is False, ob


def test_CONTROLE_sem_extensao_no_cabecalho_nada_e_legenda():
    d = _doc_legenda(False)
    d.header["$EXTMIN"] = (1e20, 1e20, 1e20)
    d.header["$EXTMAX"] = (-1e20, -1e20, -1e20)
    ob = dx.objetos_repetidos_sem_bloco(d.modelspace(), 0.01)
    assert ob["238"][0].get("concentrada") is False, ob


def test_a_contagem_de_peca_sem_bloco_nao_sai_confirmada():
    c, o, r = er.selo_apos_peca_sem_bloco(
        "confirmado", "Fonte: 26 círculos de raio 25,3cm contados no layer 230", 26, "un", {26, 776})
    assert (c, r) == ("estimado", True) and o.startswith(er.MARCA_PECA_SEM_BLOCO), o


@pytest.mark.parametrize("conf,obs,q,unit", [
    ("confirmado", "Fonte: 14 INSERTs do bloco 'tomada'", 14, "un"),        # não cita a peça
    ("confirmado", "Fonte: 26 INSERTs do bloco 'pilar'", 26, "un"),          # número de grupo, fonte é bloco
    ("confirmado", "Fonte: 27 retângulos no layer 1", 27, "un"),           # número de outro grupo
    ("estimado", "Fonte: 26 círculos", 26, "un"),                          # já é laranja
    ("confirmado", "Fonte: 26 círculos", 26, "m"),                         # não é contagem
])
def test_CONTROLE_o_que_nao_e_contagem_de_peca_segue(conf, obs, q, unit):
    assert er.selo_apos_peca_sem_bloco(conf, obs, q, unit, {26, 776}) == (conf, obs, False)


def test_o_comprimento_de_layer_sem_nome_nao_sai_confirmado():
    c, o, r = er.selo_apos_layer_sem_nome(
        "confirmado", "Fonte: comprimento total do layer 205 = 265,99m", "ml", [])
    assert (c, r) == ("estimado", True) and "('205')" in o, o


@pytest.mark.parametrize("conf,obs,unit,com_nome", [
    ("confirmado", "Fonte: comprimento do layer PAREDE = 30 m", "ml", ["PAREDE"]),
    ("confirmado", "Fonte: layer PAREDE = 30 m (o layer 205 é o eixo)", "ml", ["PAREDE"]),
    ("confirmado", "Fonte: comprimento do layer 205A = 30 m", "ml", []),
    ("confirmado", "Fonte: layer 205 com 12 peças", "un", []),
    ("estimado", "Fonte: comprimento do layer 205 = 30 m", "ml", []),
])
def test_CONTROLE_layer_com_nome_ou_contagem_segue(conf, obs, unit, com_nome):
    assert er.selo_apos_layer_sem_nome(conf, obs, unit, com_nome) == (conf, obs, False)


def test_as_marcas_novas_travam_a_chave_do_selo():
    assert er.MARCA_PECA_SEM_BLOCO in er.MARCAS_DE_REBAIXAMENTO
    assert er.MARCA_LAYER_SEM_NOME in er.MARCAS_DE_REBAIXAMENTO


def test_o_laco_de_producao_aplica_as_duas_regras():
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    itens, _esc, _ = _laco_de_itens_de_producao([
        {"item_num": "1", "description": "Pilar circular", "unit": "un", "quantity": 26,
         "confidence": "confirmado",
         "observations": "Fonte: 26 círculos de raio 25,3cm contados no layer 230 (OBJETOS DESENHADOS PEÇA POR PEÇA)."},
        {"item_num": "2", "description": "Comprimento de paredes", "unit": "ml", "quantity": 265.99,
         "confidence": "confirmado",
         "observations": "Fonte: comprimento total do layer 205 = 265,99m (COMPRIMENTOS POR LAYER)."},
    ], areas={}, compr={}, extra={"_objetos_n": {26, 776}})
    assert [i.confidence.value for i in itens] == ["estimado", "estimado"], [i.observations for i in itens]
    assert itens[0].observations.startswith(er.MARCA_PECA_SEM_BLOCO)
    assert itens[1].observations.startswith(er.MARCA_LAYER_SEM_NOME)


def test_as_contagens_das_pecas_vem_da_extracao():
    ex = _Extr(dict(_MD), {})
    esc = _roda('_objetos_n = {int(_p.get("n") or 0) for _ps in', {"extraction": ex})
    assert esc["_objetos_n"] == {776, 817}, esc["_objetos_n"]
