# -*- coding: utf-8 -*-
"""Corte fora do comprimento, planta-chave fora da soma, leito pela LEGENDA.

🩸 25/09/2026 — job `53f0483f` (subestação, 3 DWG, folha inteira no modelo).
O cliente respondeu que "os cortes e as duas bordas de leito continuam
errados". Estudado no arquivo:
- 2 das 3 pranchas eram só CORTES; o leito visto de lado somou ~1,4 km ao da
  planta, e a laje CORTADA virou "laje 31 m²";
- o corte A-A corre 57% da folha — a régua "linha > 40% do lado é moldura"
  jogava fora o próprio leito e a caixa do corte virava um pedaço de 6 m;
- o título "CORTE 'D-D'" começa 1,4 m à esquerda do desenho: nada acima dele;
- a PLANTA-CHAVE (o contorno do prédio em escala pequena) estava no layer do
  leito, e na folha da planta uma divisória emendava tudo num bloco de 85%;
- o leito estava no layer "K-04" (código do cliente) e era desenhado pelas
  DUAS bordas; a SIMBOLOGIA dizia: "- LEITO PARA CABOS" com 2 linhas K-04;
- a borda de um lado corria inteira e a do outro vinha quebrada em cada
  caixa; e polilinha entrava como UMA reta do 1º ao último vértice.
Resultado no caso: leito 1.064 m (brancos) → 130 m de eixo, só da planta.
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
from dwg_extractor import BlockCount, HatchArea, WallSegment  # noqa: E402
from engine_rules import tipo_do_desenho, vista_e_corte  # noqa: E402

G = 0.175          # letra de título (m)


# ── tipos de desenho ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("titulo", ["PLANTA CHAVE", "PLANTA-CHAVE", "Planta chave", "KEY PLAN"])
def test_planta_chave_sai_da_soma(titulo):
    assert tipo_do_desenho(titulo) == "fora"


@pytest.mark.parametrize("titulo, esperado", [
    ("PLANTA BAIXA TÉRREO", "planta"), ("CORTE 'B-B'", "vista"), ("ELEVAÇÃO 1", "vista")])
def test_CONTROLE_o_resto_continua_como_era(titulo, esperado):
    assert tipo_do_desenho(titulo) == esperado


@pytest.mark.parametrize("titulo, corte", [
    ("CORTE 'B-B'", True), ('%%UCORTE "A-A"', True), ("SEÇÃO TRANSVERSAL", True),
    ("ELEVAÇÃO 1", False), ("FACHADA NORTE", False), ("VISTA LATERAL", False)])
def test_corte_se_distingue_de_elevacao(titulo, corte):
    assert vista_e_corte(titulo) is corte


# ── a regra da vista ──────────────────────────────────────────────────────────
def _mapa():
    return {"folhas": [
        {"tipo": "vista", "titulo": "CORTE A-A", "caixa": (0, 0, 10, 10)},
        {"tipo": "vista", "titulo": "ELEVAÇÃO 1", "caixa": (20, 0, 30, 10)},
        {"tipo": "planta", "titulo": "PLANTA", "caixa": (40, 0, 50, 10), "andares": 1},
        {"tipo": "planta", "titulo": "PLANTA 2", "caixa": (8, 0, 12, 10), "andares": 1},
        {"tipo": "fora", "titulo": "DETALHE", "caixa": (60, 0, 70, 10)},
    ]}


def _w(lay, x, L):
    return WallSegment(layer=lay, length=L, start=(x - 0.5, 5), end=(x + 0.5, 5))


def _aplica():
    walls = [_w("CORTE", 5, 10.0), _w("ELEV", 25, 4.0), _w("PLANTA", 45, 7.0),
             _w("SOLTA", 80, 3.0), _w("DUAS", 9, 2.0), _w("DET", 65, 1.0)]
    hatches = [HatchArea(layer="LAJE", area=2.7, bbox=(0.5, 4, 9.5, 4.3)),     # 9 × 0,3 m
               HatchArea(layer="AZULEJO", area=9.0, bbox=(3, 3, 6, 6)),        # ao fundo do corte
               HatchArea(layer="PAINEL", area=10.125, bbox=(0.5, 1, 9.5, 2.125)),  # 9 × 1,125: comprido, grosso
               HatchArea(layer="PASTILHA", area=0.16, bbox=(2, 7, 2.4, 7.4)),  # 0,4 × 0,4: fina, não comprida
               HatchArea(layer="REVEST", area=6.0, bbox=(24, 4, 26, 6)),
               HatchArea(layer="RODAPE", area=0.9, bbox=(21, 1, 30, 1.1))]     # faixa na elevação
    blocks = [BlockCount(name="PIA", count=2, positions=[(5, 5), (45, 5)]),
              BlockCount(name="PAPELEIRA", count=1, positions=[(25, 5)])]
    res = dx.aplicar_leitura_por_folha(walls, hatches, [], blocks, _mapa())
    return res, {w.layer: w.length * w.peso for w in walls}, {h.layer: h.area for h in hatches}, \
        {b.name: b.count for b in blocks}


def test_na_vista_o_comprimento_sai():
    _, m, _, _ = _aplica()
    assert "CORTE" not in m and "ELEV" not in m


def test_no_corte_sai_so_a_secao_cortada():
    """A faixa fina do corte é a laje/parede CORTADA (a "laje 31 m²")."""
    _, _, a, _ = _aplica()
    assert "LAJE" not in a


def test_revestimento_da_vista_fica():
    """O azulejo ao fundo do corte e o revestimento da elevação (24/09) —
    e na elevação nem a faixa fina sai (não há nada cortado nela)."""
    _, _, a, _ = _aplica()
    assert a["AZULEJO"] == pytest.approx(9.0) and a["REVEST"] == pytest.approx(6.0)
    assert a["PAINEL"] == pytest.approx(10.125), "comprido mas GROSSO: não é seção cortada"
    assert a["PASTILHA"] == pytest.approx(0.16), "pequeno mas não é FAIXA"
    assert a["RODAPE"] == pytest.approx(0.9)


def test_bloco_da_vista_sai_so_se_aparece_fora_dela():
    _, _, _, b = _aplica()
    assert b["PIA"] == 1, "a pia da elevação é a mesma da planta"
    assert b["PAPELEIRA"] == 1, "só a elevação mostra a papeleira: é o único registro"


def test_CONTROLE_o_que_nao_e_so_vista_segue_a_regra_de_antes():
    _, m, _, _ = _aplica()
    assert m["PLANTA"] == pytest.approx(7.0) and m["SOLTA"] == pytest.approx(3.0)
    assert m["DUAS"] == pytest.approx(2.0), "vista + planta: discordam, fica como era"
    assert "DET" not in m


def test_o_que_a_vista_tirou_vai_pro_log():
    res, *_ = _aplica()
    assert res["vista"] == {"m": 14.0, "m2": 2.7, "blocos": 1}


# ── achar o desenho no modelo ─────────────────────────────────────────────────
def _moldura(msp):
    c = [(0, 0), (42, 0), (42, 29.7), (0, 29.7), (0, 0)]
    for a, b in zip(c, c[1:]):
        msp.add_line(a, b, dxfattribs={"layer": "MOLDURA"})


def _texto(msp, t, x, y, h=G, lay="0"):
    msp.add_text(t, dxfattribs={"height": h, "insert": (x, y), "layer": lay})


def _doc():
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    _moldura(msp)
    _texto(msp, "nota", 40, 1, 0.08)
    return doc, msp


def test_corte_comprido_e_um_desenho_so():
    """Leito do corte correndo 57% da folha: não é moldura."""
    doc, msp = _doc()
    for y in (17.0, 17.3):
        msp.add_line((3, y), (27, y), dxfattribs={"layer": "LEITO"})
    for x in range(4, 27, 3):                    # pilaretes, 3 m um do outro
        msp.add_line((x, 16), (x, 17), dxfattribs={"layer": "SUPORTE"})
    _texto(msp, "CORTE A-A", 8, 15.5)
    cx = next(f["caixa"] for f in dx._desenhos_no_modelo(msp) if f["tipo"] == "vista")
    assert cx[0] <= 3.3 and cx[2] >= 26.7, cx


def test_titulo_que_comeca_antes_do_desenho():
    """'CORTE D-D' inserido 1,4 m à esquerda do desenho."""
    doc, msp = _doc()
    for a, b in [((11, 8), (17, 8)), ((17, 8), (17, 13)), ((17, 13), (11, 13)), ((11, 13), (11, 8))]:
        msp.add_line(a, b, dxfattribs={"layer": "LEITO"})
    _texto(msp, "CORTE 'D-D'", 9.6, 7.6)
    fs = dx._desenhos_no_modelo(msp)
    assert any(f["tipo"] == "vista" and f["caixa"][0] <= 11.0 and f["caixa"][2] >= 17.0 for f in fs), fs


def _planta_e_chave(msp, vao_linhas):
    """Planta grande em cima; planta-chave embaixo, `vao_linhas` células vazias
    entre as duas (célula = 42/150 = 0,28 m)."""
    for a, b in [((3, 12.2), (37, 12.2)), ((37, 12.2), (37, 29)), ((37, 29), (3, 29)), ((3, 29), (3, 12.2))]:
        msp.add_line(a, b, dxfattribs={"layer": "PLANTA"})
    topo = 12.2 - 0.28 * (vao_linhas + 1)
    for a, b in [((28, 3), (38, 3)), ((38, 3), (38, topo)), ((38, topo), (28, topo)), ((28, topo), (28, 3))]:
        msp.add_line(a, b, dxfattribs={"layer": "LEITO"})
    _texto(msp, "PLANTA CHAVE", 30, topo - 0.8)
    return topo


def test_planta_chave_emendada_na_planta_ainda_e_achada():
    """Uma célula de vão emenda planta e planta-chave num bloco de 73% da folha;
    a 2ª tentativa, sem tolerar vão, acha a planta-chave sozinha."""
    doc, msp = _doc()
    topo = _planta_e_chave(msp, 1)
    fs = [f for f in dx._desenhos_no_modelo(msp) if f["tipo"] == "fora"]
    assert fs and fs[0]["caixa"][3] <= topo + 0.3, fs


def test_CONTROLE_planta_chave_separada_acha_de_primeira():
    doc, msp = _doc()
    topo = _planta_e_chave(msp, 4)
    fs = [f for f in dx._desenhos_no_modelo(msp) if f["tipo"] == "fora"]
    assert fs and fs[0]["caixa"][3] <= topo + 0.3, fs


# ── o eixo do leito ───────────────────────────────────────────────────────────
class W:
    def __init__(self, layer, a, b, pontos=(), length=None):
        self.layer, self.start, self.end, self.pontos = layer, a, b, pontos
        self.curvo = False
        self.length = length if length is not None else math.dist(a, b)


def _soma(ws, lay):
    return sum(w.length for w in ws if w.layer == lay)


def test_borda_inteira_de_um_lado_e_quebrada_do_outro():
    ws = [W("EL-LEITO", (0, 0), (9, 0)), W("EL-LEITO", (0, 0.6), (4.5, 0.6)),
          W("EL-LEITO", (4.5, 0.6), (9, 0.6))]
    novos, rel, _ = dx._corrigir_duto_linha_dupla(ws, 1.0)
    assert _soma(novos, "EL-LEITO") == pytest.approx(9.0), rel


def test_retangulo_fechado_em_polilinha_vira_eixo():
    """Antes: início = fim, nem entrava; e as tampas contavam."""
    pts = ((0, 0, 0), (10, 0, 0), (10, 0.6, 0), (0, 0.6, 0), (0, 0, 0))
    ws = [W("ELETROCALHA", (0, 0), (0, 0), pontos=pts, length=21.2)]
    novos, rel, _ = dx._corrigir_duto_linha_dupla(ws, 1.0)
    assert _soma(novos, "ELETROCALHA") == pytest.approx(10.0), rel


def test_layer_que_a_legenda_aponta_pareia_sem_o_nome_dizer():
    ws = [W("K-04", (0, 0), (10, 0)), W("K-04", (0, 0.6), (10, 0.6))]
    assert _soma(dx._corrigir_duto_linha_dupla(ws, 1.0)[0], "K-04") == pytest.approx(20.0)
    novos, _, _ = dx._corrigir_duto_linha_dupla(ws, 1.0, layers_extra={"K-04"})
    assert _soma(novos, "K-04") == pytest.approx(10.0)


def test_dois_leitos_lado_a_lado_sao_dois():
    ws = [W("LEITO", (0, y), (10, y)) for y in (0.0, 0.6, 0.9, 1.5)]
    novos, _, _ = dx._corrigir_duto_linha_dupla(ws, 1.0)
    assert _soma(novos, "LEITO") == pytest.approx(20.0)


def test_dois_leitos_e_uma_linha_ao_lado_sao_tres():
    """Vizinha com vizinha, e quem já pareou não pareia de novo: em corrente,
    a linha do meio de cada leito casaria com o leito do lado."""
    ws = [W("LEITO", (0, y), (10, y)) for y in (0.0, 0.6, 0.9, 1.5, 2.1)]
    novos, _, _ = dx._corrigir_duto_linha_dupla(ws, 1.0)
    assert _soma(novos, "LEITO") == pytest.approx(30.0)


def test_CONTROLE_traco_curto_solto_nao_e_tampa():
    ws = [W("LEITO", (0, 0), (10, 0)), W("LEITO", (0, 0.6), (10, 0.6)),
          W("LEITO", (20, 0), (20, 0.5))]
    novos, _, _ = dx._corrigir_duto_linha_dupla(ws, 1.0)
    assert _soma(novos, "LEITO") == pytest.approx(10.5)


def test_CONTROLE_eletroduto_continua_linha_unica():
    ws = [W("ELETRODUTO", (0, 0), (10, 0)), W("ELETRODUTO", (0, 0.6), (10, 0.6))]
    assert _soma(dx._corrigir_duto_linha_dupla(ws, 1.0)[0], "ELETRODUTO") == pytest.approx(20.0)


# ── a legenda ─────────────────────────────────────────────────────────────────
H = 0.1


def _linha(msp, lay, y, x0=24.5, x1=25.9):
    msp.add_line((x0, y), (x1, y), dxfattribs={"layer": lay})


def _legenda(msp, lay_leito="K-04", texto_leito="- LEITO PARA CABOS", x=26.0):
    """Como no arquivo: linhas a ~4,1 alturas; a 2ª abaixo do leito a 8,2."""
    _texto(msp, texto_leito, x, 14.80, H)
    _linha(msp, lay_leito, 14.97)
    _linha(msp, lay_leito, 14.77)
    _texto(msp, "- ELETROCALHA DE REDE", x, 14.39, H)
    _linha(msp, "K-04", 14.56)
    _linha(msp, "K-04", 14.36)
    _texto(msp, "- ELETRODUTO RÍGIDO, INSTALAÇÃO APARENTE.", x, 13.98, H)
    _linha(msp, "ELL5", 14.03)
    _texto(msp, '- CONDULETE TIPO "C".', x, 13.57, H)
    if "CONDULETE" not in msp.doc.blocks:
        msp.doc.blocks.new("CONDULETE").add_line((0, 0), (0.1, 0))
    msp.add_blockref("CONDULETE", (25.0, 13.62))


def test_a_legenda_diz_o_que_o_layer_e():
    doc, msp = _doc()
    _legenda(msp)
    assert dx._legenda_de_linha_dupla(msp) == {"K-04": ["LEITO PARA CABOS", "ELETROCALHA DE REDE"]}


def test_CONTROLE_a_palavra_tem_que_ser_a_cabeca():
    """"DIÂMETRO DO DUTO/LARGURA" explica a etiqueta — não é duto."""
    doc, msp = _doc()
    _legenda(msp, lay_leito="X-09", texto_leito="DIÂMETRO DO DUTO/LARGURA")
    assert "X-09" not in dx._legenda_de_linha_dupla(msp)


def test_CONTROLE_amostra_em_layer_de_anotacao_nao_vale():
    doc, msp = _doc()
    _legenda(msp, lay_leito="CHAMADA")
    assert "CHAMADA" not in dx._legenda_de_linha_dupla(msp)


def test_CONTROLE_amostra_tracejada_e_linha_unica():
    """Tracejado = vários traços NA MESMA linha, não duas bordas."""
    doc, msp = _doc()
    _legenda(msp, lay_leito="DT-1", texto_leito="- DUTO DE AR")
    for e in list(msp.query('LINE[layer=="DT-1"]')):
        msp.delete_entity(e)
    for x0 in (24.5, 25.0, 25.5):
        _linha(msp, "DT-1", 14.87, x0, x0 + 0.35)
    assert "DT-1" not in dx._legenda_de_linha_dupla(msp)


def test_CONTROLE_anotacao_solta_na_planta_nao_e_legenda():
    """'ELETROCALHA' escrito ao lado do desenho, sem coluna de legenda."""
    doc, msp = _doc()
    _texto(msp, "ELETROCALHA", 26.0, 14.8, H)
    _linha(msp, "PISO", 14.97)
    _linha(msp, "PISO", 14.77)
    assert dx._legenda_de_linha_dupla(msp) == {}


def test_CONTROLE_coluna_de_notas_sem_amostra_nao_e_legenda():
    """Notas alinhadas (sem desenho ao lado) — a do meio fala de eletrocalha e
    o leito da planta passa logo à esquerda dela."""
    doc, msp = _doc()
    _texto(msp, "NOTAS GERAIS DO PROJETO", 26.0, 15.2, H)
    _texto(msp, "ELETROCALHA FIXADA NA LAJE A CADA 1,5 M", 26.0, 14.8, H)
    _linha(msp, "PISO", 14.97)
    _linha(msp, "PISO", 14.77)
    _texto(msp, "VER MEMORIAL DESCRITIVO", 26.0, 14.4, H)
    assert dx._legenda_de_linha_dupla(msp) == {}


# ── de ponta a ponta ──────────────────────────────────────────────────────────
def _arquivo(tmp_path, com_legenda):
    doc, msp = _doc()
    if com_legenda:
        _legenda(msp)
    msp.add_lwpolyline([(2, 20), (12, 20), (12, 20.6), (2, 20.6)], close=True,
                       dxfattribs={"layer": "K-04"})
    p = str(tmp_path / ("com.dxf" if com_legenda else "sem.dxf"))
    doc.saveas(p)
    return p


def test_de_ponta_a_ponta_o_leito_sai_pelo_eixo_e_a_ia_sabe_o_que_e(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path, True))
    # retângulo 10 × 0,6 → 10 m; amostras da legenda: 2 pares de 1,4 m → 2,8 m
    assert ex.get_walls_by_layer()["K-04"] == pytest.approx(12.8, abs=0.05)
    assert "LEITO PARA CABOS" in ex.metadata.get("legenda_linha_dupla", "")
    assert "LEITO PARA CABOS" in ex.to_structured_prompt()


def test_CONTROLE_sem_legenda_o_layer_de_codigo_fica_como_era(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path, False))
    assert ex.get_walls_by_layer()["K-04"] == pytest.approx(21.2, abs=0.05)
    assert "legenda_linha_dupla" not in ex.metadata


# ── a IA e o log ficam sabendo ────────────────────────────────────────────────
def test_a_ia_e_o_log_sabem_que_o_corte_saiu(tmp_path, monkeypatch):
    import test_desenho_no_modelo as tdm
    import main as M
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(tdm._folha(tmp_path, titulo_detalhe='%%UCORTE "A-A"'))
    assert "visto DE LADO" in ex.to_structured_prompt()
    assert "vista_fora=[-36.0m" in M._leitura_por_folha_resumo(ex)
