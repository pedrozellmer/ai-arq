# -*- coding: utf-8 -*-
"""O MAPA-CHAVE do ArchiCAD fica fora das medidas — pelo campo do desenho no prefixo do layer.

🩸 13/10/2026 — no projeto do corte lido como planta, em TODA prancha o layer
"001_MAPA CHAVE_2_0" (a obra inteira redesenhada numa vista minúscula) tinha ~69
a 70 km de linha na medição: 85,7 % do comprimento da planta térrea e 88,8 % do
arquivo de corte.
🔑 O ArchiCAD prefixa os layers de cada desenho posto na folha com
"<id>_<nome do desenho>_<n>_": quem diz que é mapa-chave é o 2º campo.
🪤 Só a convenção do ArchiCAD: o layer comum chamado "MAPA CHAVE" e o layer DA
PLANTA cujo nome fala em mapa-chave ficam como estão. A legenda também.

🪤 Nomes FICTÍCIOS, com a mesma forma dos medidos (repositório público).
"""
import io
import os
import re
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import dwg_extractor as dx  # noqa: E402

CHAVE = "MAPA_CHAVE_DO_ARCHICAD_FORA"
MAPA = "001_MAPA CHAVE_2_0"

E_MAPA = [MAPA, "9_Mapa-Chave_12_Linhas", "K_PLANTA CHAVE_2_0", "K_Planta-chave térreo_3_ARQ - Parede",
          "X_Key Plan_1_0", "X_KEYPLAN_7_0", "xpto - mc_mapa chave do pavimento_4_0"]
NAO_E = ["MAPA CHAVE", "A-MAPA-CHAVE", "ARQ_MAPA CHAVE_X", "MAPA_CHAVE_1",
         # o layer DA PLANTA cujo nome fala em mapa-chave: o desenho é a planta
         "1_PLANTA BAIXA_1_ARQ - Mapa chave", "1_PLANTA BAIXA_1_Key plan",
         # o prefixo é o COMEÇO do nome, e o id é curto (até 12 letras)
         "PAVIMENTO TERREO_MAPA CHAVE_2_0",
         "LG_Acabamentos_11_0", "A_Corte AA_1_0", "2_Pav.tipo 1_1_ARQ - Parede", "9_Chaveiro_2_0", "9_Mapa de riscos_2_0",
         "0", "", None]


@pytest.fixture(autouse=True)
def _chave(monkeypatch):
    monkeypatch.delenv(CHAVE, raising=False)


@pytest.mark.parametrize("layer", E_MAPA)
def test_o_layer_e_de_mapa_chave(layer):
    assert dx.layer_de_mapa_chave_do_archicad(layer) is True, layer


@pytest.mark.parametrize("layer", NAO_E)
def test_CONTROLE_o_layer_nao_e_de_mapa_chave(layer):
    assert dx.layer_de_mapa_chave_do_archicad(layer) is False, layer


# ── as listas ────────────────────────────────────────────────────────────────
def _parede(layer, m):
    return dx.WallSegment(layer=layer, length=m, start=(0, 0), end=(m, 0))


def _area(layer, m2):
    return dx.HatchArea(layer=layer, area=m2)


def test_o_que_esta_no_layer_do_mapa_chave_sai_das_tres_listas():
    walls = [_parede("ARQ - Parede", 12.0), _parede(MAPA, 700.0), _parede(MAPA, 300.5), _parede("0", 1.0)]
    hatches = [_area("ARQ - Piso", 50.0), _area(MAPA, 8.2)]
    contornos = [_area(MAPA, 1.5), _area("ARQ - Forro", 40.0)]
    r = dx.tirar_o_mapa_chave(walls, hatches, contornos)
    assert r == {"layers": [MAPA], "m": 1000.5, "m2": 9.7}
    assert [(w.layer, w.length) for w in walls] == [("ARQ - Parede", 12.0), ("0", 1.0)]
    assert [(h.layer, h.area) for h in hatches] == [("ARQ - Piso", 50.0)]
    assert [(h.layer, h.area) for h in contornos] == [("ARQ - Forro", 40.0)]


def test_CONTROLE_sem_mapa_chave_as_listas_nem_sao_tocadas():
    walls = [_parede("ARQ - Parede", 12.0), _parede("MAPA CHAVE", 700.0)]
    hatches, contornos = [_area("1_PLANTA BAIXA_1_ARQ - Mapa chave", 50.0)], []
    antes = (list(walls), list(hatches))
    assert dx.tirar_o_mapa_chave(walls, hatches, contornos) == {}
    assert (walls, hatches, contornos) == (antes[0], antes[1], [])
    assert dx.tirar_o_mapa_chave([], [], []) == {}
    assert dx.tirar_o_mapa_chave(None, None, None) == {}


def test_dois_mapas_chave_e_so_area():
    outro = "K_Planta chave_5_0"
    r = dx.tirar_o_mapa_chave([_parede(outro, 10.0)], [_area(MAPA, 2.0)], [])
    assert r == {"layers": sorted([MAPA, outro]), "m": 10.0, "m2": 2.0}


# ── do DXF à medição ─────────────────────────────────────────────────────────
def _hachura(msp, layer, x0, y0, w, h):
    hx = msp.add_hatch(dxfattribs={"layer": layer})
    hx.paths.add_polyline_path([(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)], is_closed=True)


def _dxf(tmp_path, mapa=MAPA, nome="planta.dxf", bloco_no_mapa=True):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for n in ("ARQ - Parede", "ARQ - Piso", "ARQ - Fixo", mapa):
        doc.layers.add(n)
    # a planta, com os layers SEM prefixo (como na planta térrea do caso)
    for y in (0.0, 4.0, 8.0, 12.0):
        msp.add_line((0, y), (30, y + 0.5), dxfattribs={"layer": "ARQ - Parede"})
    _hachura(msp, "ARQ - Piso", 2.0, 1.0, 10.0, 2.0)                 # 20 m²
    b = doc.blocks.new(name="BACIA 01")
    b.add_circle((0, 0), 0.2)
    b.add_line((-0.3, 0), (0.3, 0))
    for i in range(3):
        msp.add_blockref("BACIA 01", (5 + 4 * i, 6), dxfattribs={"layer": "ARQ - Fixo"})
    # o mapa-chave: 1.000 m de linha, uma hachura e uma inserção, tudo no layer dele
    for k in range(20):
        msp.add_line((200, 3.0 * k), (250, 3.0 * k + 0.5), dxfattribs={"layer": mapa})
    _hachura(msp, mapa, 200.0, 70.0, 4.0, 3.0)                       # 12 m²
    if bloco_no_mapa:
        msp.add_blockref("BACIA 01", (210, 80), dxfattribs={"layer": mapa})
    p = str(tmp_path / nome)
    doc.saveas(p)
    return p


def _metros(ex):
    return {k: round(float(v), 1) for k, v in ex.get_walls_by_layer().items()}


def _m2(ex):
    return round(sum(float(h.area) for h in ex.hatches), 2)


def test_na_planta_o_mapa_chave_sai_e_o_resto_fica(tmp_path):
    p = _dxf(tmp_path)
    ex = dx.extract_dxf(p)
    assert MAPA not in _metros(ex) and _metros(ex)["ARQ - Parede"] > 100
    assert _m2(ex) == 20.0
    assert {b.name: b.count for b in ex.blocks} == {"BACIA 01": 3}
    mc = ex.metadata["mapa_chave_fora"]
    assert mc["layers"] == [MAPA] and 990 < mc["m"] < 1010 and mc["m2"] == 12.0 and mc["blocos"] == 1
    assert "mapa_chave_fora" not in ex.to_structured_prompt()


def test_CONTROLE_com_a_chave_em_zero_e_como_hoje(tmp_path, monkeypatch):
    p = _dxf(tmp_path)
    com = dx.extract_dxf(p)
    monkeypatch.setenv(CHAVE, "0")
    sem = dx.extract_dxf(p)
    assert 990 < _metros(sem)[MAPA] < 1010 and _m2(sem) == 32.0
    assert {b.name: b.count for b in sem.blocks} == {"BACIA 01": 4}
    assert "mapa_chave_fora" not in sem.metadata
    # e a planta mede o mesmo dos dois jeitos
    assert _metros(com)["ARQ - Parede"] == _metros(sem)["ARQ - Parede"]


def test_CONTROLE_o_layer_comum_chamado_mapa_chave_fica_como_esta(tmp_path, monkeypatch):
    p = _dxf(tmp_path, mapa="MAPA CHAVE", nome="comum.dxf")
    com = dx.extract_dxf(p)
    monkeypatch.setenv(CHAVE, "0")
    sem = dx.extract_dxf(p)
    assert "mapa_chave_fora" not in com.metadata
    assert _metros(com) == _metros(sem) and _m2(com) == _m2(sem) == 32.0
    assert com.to_structured_prompt() == sem.to_structured_prompt()


def test_sem_insercao_no_mapa_chave_o_registro_diz_zero_blocos(tmp_path):
    ex = dx.extract_dxf(_dxf(tmp_path, bloco_no_mapa=False))
    mc = ex.metadata["mapa_chave_fora"]
    assert mc["layers"] == [MAPA] and mc["blocos"] == 0 and mc["m2"] == 12.0
    assert {b.name: b.count for b in ex.blocks} == {"BACIA 01": 3}


def test_so_a_insercao_no_mapa_chave_tambem_fica_no_registro(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    doc.layers.add(MAPA)
    msp.add_lwpolyline([(0, 0), (40, 0), (40, 30), (0, 30)], close=True, dxfattribs={"layer": "ARQ - Parede"})
    b = doc.blocks.new(name="BACIA 01")
    b.add_circle((0, 0), 0.2)
    for i in range(2):
        msp.add_blockref("BACIA 01", (200 + i, 5), dxfattribs={"layer": MAPA})
    msp.add_blockref("BACIA 01", (5, 5), dxfattribs={"layer": "ARQ - Parede"})
    p = str(tmp_path / "so_bloco.dxf")
    doc.saveas(p)
    ex = dx.extract_dxf(p)
    assert {b.name: b.count for b in ex.blocks} == {"BACIA 01": 1}
    assert ex.metadata["mapa_chave_fora"] == {"layers": [], "m": 0.0, "m2": 0.0, "blocos": 2}


# ── o log e a chave ──────────────────────────────────────────────────────────
def test_o_log_diz_o_que_saiu(tmp_path):
    import main

    class _Ex:
        metadata = {"mapa_chave_fora": {"layers": [MAPA], "m": 68890.8, "m2": 12.0, "blocos": 3}}

    assert main._mapa_chave_fora_resumo(_Ex()) == " | mapa_chave_fora=[001_MAPA CHAVE_2_0: 68890.8m 12.0m2 3bl]"

    class _Sem:
        metadata = {}

    assert main._mapa_chave_fora_resumo(_Sem()) == "" and main._mapa_chave_fora_resumo(None) == ""
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    linha = fonte[fonte.index('"motor:parede-medida",\n                            "arq=%s layers_de_parede'):][:600]
    assert "_mapa_chave_fora_resumo(extraction)" in linha


def test_a_chave_e_lida_no_extrator_e_e_avaliavel():
    fonte = io.open(os.path.join(_BACKEND, "dwg_extractor.py"), encoding="utf-8").read()
    assert fonte.count('os.environ.get("%s"' % CHAVE) == 1
    main = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    bloco = re.search(r"_CHAVES_AVALIAVEIS = frozenset\(\{(.*?)\}\)", main, re.S).group(1)
    assert '"%s"' % CHAVE in bloco
