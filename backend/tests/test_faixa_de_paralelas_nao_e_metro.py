# -*- coding: utf-8 -*-
"""Metro de layer desenhado como FAIXA de linhas paralelas não sai medido (E07).

🩸 05/10/2026 — conferência da lista de dano, E07. Uma eletrocalha desenhada
como faixas de 9 e 17 linhas a 25 mm (o preenchimento da rota) somava
1.058,79 m contra ~111 m de eixo; com a unidade provada, a chave do selo a
promovia a ✓, e o relato do eixo dizia "JÁ pelo EIXO" sem ter reduzido nada.

Regras:
- faixa = ≥ 5 paralelas a passo constante, passo ≤ 3 % do comprimento,
  largura ≤ 1,0 m; ≥ 60 % do layer em faixas → ressalva do layer: fora da
  chave do selo e do resgate, ⚠ no prompt, relato sem "eixo", e a linha ✓ em
  metro que cita o layer cai para estimado;
- numerador e denominador do msp (a mesma população); fora anotação;
- SÓ REBAIXA: nenhuma soma muda.
Todos os desenhos e nomes são sintéticos.
"""
import math
import os
import re
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import dwg_extractor as dx  # noqa: E402
import engine_rules as er  # noqa: E402


def _faixa(m, layer, x0, y0, L, n, passo, ang=0.0, poli=False):
    """n linhas paralelas de comprimento L, a `passo` uma da outra, na direção `ang` (graus)."""
    ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    nx, ny = -uy, ux
    for i in range(n):
        a = (x0 + i * passo * nx, y0 + i * passo * ny)
        b = (a[0] + L * ux, a[1] + L * uy)
        if poli:
            m.add_lwpolyline([a, b], dxfattribs={"layer": layer})
        else:
            m.add_line(a, b, dxfattribs={"layer": layer})


def _rota(m, layer, n=9, passo=0.025):
    """A rota da eletrocalha: 4 trechos de 25 m em L, cada um em faixa de n linhas."""
    _faixa(m, layer, 0.0, 0.0, 25.0, n, passo)
    _faixa(m, layer, 30.0, 0.0, 25.0, n, passo)
    _faixa(m, layer, 0.0, 10.0, 25.0, n, passo, ang=90.0)
    _faixa(m, layer, 60.0, 5.0, 25.0, n, passo, ang=90.0)


def _rede(m, layer, n=10, comp=120.0, x0=200.0, y0=20.0):
    """Ramais soltos, longe uns dos outros (não fazem faixa)."""
    for i in range(n):
        m.add_line((x0, y0 + i * 9.0), (x0 + comp, y0 + i * 9.0 + 3.0), dxfattribs={"layer": layer})


def _lados(e):
    if e.dxftype() == "LINE":
        return [((e.dxf.start[0], e.dxf.start[1]), (e.dxf.end[0], e.dxf.end[1]))]
    p = [(q[0], q[1]) for q in e.get_points("xy")]
    if e.closed:
        p.append(p[0])
    return list(zip(p, p[1:]))


def _faixas(desenha, uf=1.0):
    """Roda o detector (walls = a soma crua de cada layer, em metro)."""
    doc = ezdxf.new("R2018")
    m = doc.modelspace()
    desenha(m)
    tot = {}
    for e in m.query("LINE LWPOLYLINE"):
        for a, b in _lados(e):
            tot[e.dxf.layer] = tot.get(e.dxf.layer, 0.0) + math.dist(a, b) * uf
    return dx.layers_em_faixa_de_paralelas(m, [dx.WallSegment(layer=ly, length=v) for ly, v in tot.items()], uf)


def _ler(tmp_path, desenha):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    desenha(doc.modelspace())
    p = str(tmp_path / "prancha.dxf")
    doc.saveas(p)
    return dx.extract_dxf(p)


# ══════════════════════════════════════════════════════════════════════════
#  1. O caso e as formas
# ══════════════════════════════════════════════════════════════════════════
def test_o_caso_a_eletrocalha_em_faixa_de_9_linhas(tmp_path):
    ex = _ler(tmp_path, lambda m: (_rota(m, "E-CALHA-X"), _rede(m, "REDE-OUTRA", n=12, comp=900.0)))
    fx = ex.metadata.get("layers_em_faixa") or {}
    assert "E-CALHA-X" in fx, fx
    v = fx["E-CALHA-X"]
    assert v["fracao"] >= 0.99 and v["linhas"] == 9 and abs(v["passo_mm"] - 25.0) < 0.5, v
    assert 99.0 <= v["eixo_m"] <= 101.0, v                     # a rota, uma vez: 4 × 25 m
    assert "E-CALHA-X" in er.layers_que_nao_provam(ex.metadata)
    assert "REDE-OUTRA" not in fx
    prompt = ex.to_structured_prompt()
    linha = next(l for l in prompt.splitlines() if l.strip().startswith("E-CALHA-X:"))
    assert "⚠ FAIXA DE ~9 LINHAS PARALELAS a 25.0 mm" in linha
    assert not re.search(r"(?i)\blayers?\s+\w", linha.split("⚠", 1)[1])
    assert "layers_em_faixa" not in prompt


def test_so_marca_nao_muda_a_soma(tmp_path, monkeypatch):
    def d(m):
        _rota(m, "E-CALHA-X")
        _rede(m, "REDE-OUTRA", n=12, comp=900.0)
    a = _ler(tmp_path, d)
    monkeypatch.setattr(dx, "layers_em_faixa_de_paralelas", lambda *x, **k: {})
    b = _ler(tmp_path, d)
    assert "E-CALHA-X" in (a.metadata.get("layers_em_faixa") or {})
    assert "layers_em_faixa" not in b.metadata
    assert a.get_walls_by_layer() == b.get_walls_by_layer()


@pytest.mark.parametrize("ang", [0.0, 30.0, 90.0, 179.95])
def test_qualquer_direcao(ang):
    """Inclusive a que encosta no 180° (o grupo de ângulo dá a volta)."""
    tab = _faixas(lambda m: _faixa(m, "CALHA-Y", 0.0, 0.0, 30.0, 9, 0.025, ang=ang))
    assert "CALHA-Y" in tab, (ang, tab)


def test_o_grupo_de_angulo_da_a_volta_no_180():
    """8 linhas quase horizontais, alternando +0,05° e −0,05° (179,95°): é UMA
    faixa. Sem juntar as duas pontas do ângulo, viram 2 grupos de 4 (não marca)."""
    def d(m):
        for i in range(8):                                   # girada em torno do meio: o passo fica 25 mm
            y, dy = i * 0.025, 15.0 * math.tan(math.radians(0.05 if i % 2 == 0 else -0.05))
            m.add_line((0.0, y - dy), (30.0, y + dy), dxfattribs={"layer": "CALHA-Y"})
    assert "CALHA-Y" in _faixas(d)


def test_a_faixa_em_polilinha():
    assert "CALHA-Y" in _faixas(lambda m: _faixa(m, "CALHA-Y", 0.0, 0.0, 30.0, 9, 0.025, poli=True))


@pytest.mark.parametrize("n,marca", [(5, True), (4, False)])
def test_cinco_linhas_marcam_quatro_nao(n, marca):
    """A eletrocalha de 5 linhas a 25 mm é o menor caso medido."""
    assert ("CALHA-Y" in _faixas(lambda m: _faixa(m, "CALHA-Y", 0.0, 0.0, 30.0, n, 0.025))) is marca


def test_desenho_em_milimetro():
    """Largura em metro real pelo fator: 9 linhas a 25 unidades (mm) = 0,2 m."""
    tab = _faixas(lambda m: _faixa(m, "CALHA-Y", 0.0, 0.0, 30000.0, 9, 25.0), uf=0.001)
    assert "CALHA-Y" in tab and abs(tab["CALHA-Y"]["passo_mm"] - 25.0) < 0.5, tab


def test_a_copia_exata_conta_uma_vez():
    """A faixa colada 2× no mesmo lugar não vira 'mais faixa' nem muda a fração."""
    def d(m):
        _faixa(m, "CALHA-Y", 0.0, 0.0, 30.0, 9, 0.025)
        _faixa(m, "CALHA-Y", 0.0, 0.0, 30.0, 9, 0.025)
    tab = _faixas(d)
    assert tab["CALHA-Y"]["faixas"] == 1 and tab["CALHA-Y"]["linhas"] == 9, tab


# ══════════════════════════════════════════════════════════════════════════
#  2. O que NÃO marca
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_feixe_de_3_eletrodutos_no_mesmo_tracado():
    """3 eletrodutos lado a lado a 13 cm: ali a soma É a medida."""
    assert "ELE-T-X" not in _faixas(lambda m: _faixa(m, "ELE-T-X", 0.0, 0.0, 80.0, 3, 0.13))


def test_CONTROLE_escada():
    """12 degraus de 1,2 m a 28 cm: passo de 23 % do lance (≫ 3 %)."""
    assert "ESCADA-X" not in _faixas(lambda m: _faixa(m, "ESCADA-X", 0.0, 0.0, 1.2, 12, 0.28))


def test_CONTROLE_brise_de_laminas_curtas():
    """10 lâminas de 1 m a 10 cm: largura 0,9 m (passa), mas o passo é 10 % da
    lâmina — é a peça (ali a soma das lâminas É a medida), não preenchimento."""
    assert "BRISE-X" not in _faixas(lambda m: _faixa(m, "BRISE-X", 0.0, 0.0, 1.0, 10, 0.10))


def test_a_corrente_curta_devolve_a_linha():
    """Uma linha a 6 cm da faixa (passo de 25 mm) começa uma corrente que para no
    2º passo: a corrente curta devolve a 2ª linha, que é a 1ª da faixa — sem
    devolver, a faixa ficaria com 4 linhas e não marcaria."""
    def d(m):
        ys = [0.0, 0.06] + [0.06 + 0.025 * k for k in range(1, 5)]
        for y in ys:
            m.add_line((0.0, y), (30.0, y), dxfattribs={"layer": "CALHA-Y"})
    tab = _faixas(d)
    assert "CALHA-Y" in tab and tab["CALHA-Y"]["linhas"] == 5, tab


def test_CONTROLE_linhas_deslocadas_ao_longo_nao_sao_faixa():
    """Lado a lado a 25 mm, mas cada uma escorregada meio comprimento (50 % de
    sobreposição): é escalonado, não preenchimento."""
    def d(m):
        for i in range(9):
            m.add_line((5.0 * i, i * 0.025), (5.0 * i + 10.0, i * 0.025), dxfattribs={"layer": "ESCAL-X"})
    assert "ESCAL-X" not in _faixas(d)


def test_CONTROLE_comprimentos_alternados_nao_sao_faixa():
    """8 linhas lado a lado a 25 mm, centradas, alternando 10 m e 5 m (razão
    0,5): as longas sozinhas são 4 (a 50 mm), as curtas também — nenhuma faixa
    de 5. (Com 9 linhas, as 5 longas a 50 mm SÃO uma faixa, e marcam.)"""
    def d(m):
        for i in range(8):
            L = 10.0 if i % 2 == 0 else 5.0
            m.add_line((5.0 - L / 2.0, i * 0.025), (5.0 + L / 2.0, i * 0.025), dxfattribs={"layer": "ALT-X"})
    assert "ALT-X" not in _faixas(d)


def test_CONTROLE_paralelas_largas_demais():
    """6 linhas de 100 m a 30 cm: passo pequeno pro comprimento, mas 1,5 m de largura."""
    assert "PISTA-X" not in _faixas(lambda m: _faixa(m, "PISTA-X", 0.0, 0.0, 100.0, 6, 0.30))


def test_CONTROLE_passo_irregular():
    """Linhas lado a lado com passo alternando 25 e 40 mm: a corrente para no 3º."""
    def d(m):
        y = 0.0
        for i in range(10):
            m.add_line((0.0, y), (30.0, y), dxfattribs={"layer": "CALHA-Y"})
            y += 0.025 if i % 2 == 0 else 0.040
    assert "CALHA-Y" not in _faixas(d)


@pytest.mark.parametrize("n_rede,marca", [(5, False), (1, True)])
def test_a_fracao_minima_de_60_por_cento(n_rede, marca):
    """A faixa (9 × 30 = 270 m) no layer com ramais de 120 m: com 5 ramais ela é
    31 % (fica); com 1, 69 % (marca)."""
    tab = _faixas(lambda m: (_faixa(m, "CALHA-Y", 0.0, 0.0, 30.0, 9, 0.025), _rede(m, "CALHA-Y", n=n_rede)))
    assert ("CALHA-Y" in tab) is marca, tab


def test_CONTROLE_anotacao_fica_de_fora():
    assert er.layer_is_anotacao("A-ANNO-TEXT")
    assert "A-ANNO-TEXT" not in _faixas(lambda m: _faixa(m, "A-ANNO-TEXT", 0.0, 0.0, 30.0, 9, 0.025))


def test_CONTROLE_lado_em_arco_nao_e_linha():
    def d(m):
        for i in range(9):
            m.add_lwpolyline([(0.0, i * 0.025, 0, 0, 0.3), (30.0, i * 0.025)], format="xyseb",
                             dxfattribs={"layer": "ARCO-Y"})
        _faixa(m, "ARCO-Y", 0.0, 50.0, 10.0, 1, 0.025)
    assert "ARCO-Y" not in _faixas(d)


def test_CONTROLE_layer_acima_do_teto_nao_e_medido(monkeypatch):
    monkeypatch.setattr(dx, "_TUBO_MAX_SEG", 5)
    assert "CALHA-Y" not in _faixas(lambda m: _faixa(m, "CALHA-Y", 0.0, 0.0, 30.0, 9, 0.025))


def test_a_falha_do_detector_nao_derruba_a_extracao(tmp_path, monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("sabotagem do teste")
    monkeypatch.setattr(dx, "layers_em_faixa_de_paralelas", quebra)
    ex = _ler(tmp_path, lambda m: (_rota(m, "E-CALHA-X"), _rede(m, "REDE-OUTRA", n=12, comp=900.0)))
    assert "layers_em_faixa" not in ex.metadata and ex.get_walls_by_layer()


# ══════════════════════════════════════════════════════════════════════════
#  3. O relato do eixo não chama a faixa de eixo
# ══════════════════════════════════════════════════════════════════════════
_W = [dx.WallSegment(layer="CALHA-Y", length=900.0, start=(0, 0), end=(1, 0)),
      dx.WallSegment(layer="DUTO-Z", length=50.0, start=(0, 0), end=(1, 0))]
_CRU = "CALHA-Y: 1800.0m de face -> 900.0m de eixo (9 par(es)) | DUTO-Z: 100.0m de face -> 50.0m de eixo (3 par(es))"


def test_o_relato_da_faixa_nao_diz_eixo():
    r = dx._relato_do_eixo_na_soma(_CRU, _W, faixas={"CALHA-Y": {}})
    calha, duto = r.split(" | ")
    assert "FAIXA" in calha and "EIXO" not in calha and "eixo" not in calha
    assert "JÁ pelo EIXO" in duto


def test_sem_a_folha_so_a_faixa_e_reescrita():
    r = dx._relato_do_eixo_na_soma(_CRU, _W, faixas={"CALHA-Y": {}}, so_faixas=True)
    calha, duto = r.split(" | ")
    assert "FAIXA" in calha and duto == "DUTO-Z: 100.0m de face -> 50.0m de eixo (3 par(es))"


def test_CONTROLE_sem_faixa_o_relato_segue_como_era():
    r = dx._relato_do_eixo_na_soma(_CRU, _W)
    assert r.count("JÁ pelo EIXO") == 2


def test_no_extract_o_relato_da_eletrocalha_em_faixa_nao_diz_eixo(tmp_path):
    """Layer de eletrocalha em faixa a 60 mm (o par de faces do duto roda a
    partir de 5 cm e escreve o relato): o relato não pode dizer eixo."""
    ex = _ler(tmp_path, lambda m: (_rota(m, "ELE-ELETROCALHA", passo=0.06),
                                   _rede(m, "REDE-OUTRA", n=12, comp=900.0)))
    assert "ELE-ELETROCALHA" in (ex.metadata.get("layers_em_faixa") or {})
    rel = " | ".join(str(ex.metadata.get(k) or "") for k in ("duto_linha_dupla", "parede_linha_dupla"))
    trechos = [t for t in rel.split(" | ") if t.startswith("ELE-ELETROCALHA:")]
    assert trechos, rel                                      # o relato existe (o teste não é vazio)
    for trecho in trechos:
        assert "FAIXA" in trecho and "EIXO" not in trecho and "eixo" not in trecho, trecho


def test_sem_a_leitura_por_folha_o_relato_cru_da_faixa_tambem_sai(tmp_path, monkeypatch):
    """LEITURA_POR_FOLHA=0: o relato fica cru ("de face -> de eixo"); o da faixa é
    reescrito mesmo assim, e o de outro duto fica cru."""
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    def d(m):
        _rota(m, "ELE-ELETROCALHA", passo=0.06)
        for k in range(4):                                   # outro duto, pelas 2 faces (não faixa)
            m.add_line((300.0, 50.0 + k * 20.0), (340.0, 50.0 + k * 20.0), dxfattribs={"layer": "DUTO-AR"})
            m.add_line((300.0, 50.3 + k * 20.0), (340.0, 50.3 + k * 20.0), dxfattribs={"layer": "DUTO-AR"})
        _rede(m, "REDE-OUTRA", n=12, comp=900.0)
    ex = _ler(tmp_path, d)
    rel = " | ".join(str(ex.metadata.get(k) or "") for k in ("duto_linha_dupla", "parede_linha_dupla"))
    calha = [t for t in rel.split(" | ") if t.startswith("ELE-ELETROCALHA:")]
    assert calha and all("FAIXA" in t and "eixo" not in t.lower() for t in calha), rel
    duto = [t for t in rel.split(" | ") if t.startswith("DUTO-AR:")]
    assert duto and all("de face ->" in t for t in duto), rel


# ══════════════════════════════════════════════════════════════════════════
#  4. O selo
# ══════════════════════════════════════════════════════════════════════════
def test_a_linha_confirmada_em_metro_cai():
    conf, obs, reb = er.selo_apos_faixa_de_paralelas(
        "confirmado", "layer E-CALHA-X", "ml", ["E-CALHA-X"], {"E-CALHA-X"})
    assert reb and conf == "estimado" and er.MARCA_FAIXA_DE_PARALELAS in obs
    assert er.MARCA_FAIXA_DE_PARALELAS in er.MARCAS_DE_REBAIXAMENTO


@pytest.mark.parametrize("conf,unit,citado", [
    ("confirmado", "m²", ["E-CALHA-X"]),
    ("confirmado", "un", ["E-CALHA-X"]),
    ("confirmado", "ml", ["OUTRO"]),
    ("estimado", "ml", ["E-CALHA-X"]),
])
def test_CONTROLE_area_contagem_outro_layer_ou_ja_estimado_seguem(conf, unit, citado):
    c, obs, reb = er.selo_apos_faixa_de_paralelas(conf, "x", unit, citado, {"E-CALHA-X"})
    assert not reb and c == conf and er.MARCA_FAIXA_DE_PARALELAS not in obs


@pytest.mark.parametrize("layer,obs", [
    ("XYZ_PISO.XYZ_3D", "Fonte: comprimento do layer 'XYZ_Piso.XYZ_3D' = 41,20 m."),   # ponto no nome
    ("-ABC-07", "Fonte: comprimento do layer '-ABC-07' = 72,30 m."),                   # '-' no começo
])
def test_a_trava_acha_o_layer_que_o_leitor_da_observacao_corta(layer, obs):
    from main import _layers_da_obs
    conf, o, reb = er.selo_apos_faixa_de_paralelas("confirmado", obs, "ml", _layers_da_obs(obs), {layer})
    assert reb and conf == "estimado", (layer, _layers_da_obs(obs))


def test_o_laco_de_producao_rebaixa_a_linha():
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    item = {"item_num": "1", "description": "Eletrocalha metálica",
            "unit": "ml", "quantity": 1058.79, "confidence": "confirmado",
            "observations": "Fonte: comprimento do layer 'E-CALHA-X' = 1058.79 m."}
    itens, _e, _ = _laco_de_itens_de_producao(
        [item], areas={}, compr={"E-CALHA-X": 1058.79}, extra={"_fx_ly": {"E-CALHA-X"}})
    assert itens[0].confidence.value == "estimado" and "FAIXA DE PARALELAS" in itens[0].observations


def test_CONTROLE_o_laco_sem_a_marca_segue_como_veio():
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    item = {"item_num": "1", "description": "Eletrocalha metálica",
            "unit": "ml", "quantity": 1058.79, "confidence": "confirmado",
            "observations": "Fonte: comprimento do layer 'E-CALHA-X' = 1058.79 m."}
    itens, _e, _ = _laco_de_itens_de_producao(
        [item], areas={}, compr={"E-CALHA-X": 1058.79}, extra={"_fx_ly": set()})
    assert "FAIXA DE PARALELAS" not in itens[0].observations


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


def _roda(marcador, escopo):
    import _executa
    import main
    esc = dict(vars(main))
    esc.update(escopo)
    return _executa.roda("process_job", marcador, esc, tamanho=1)


_MD = {"layers_em_faixa": {"E-CALHA-X": {"m": 1058.79, "fracao": 0.99, "faixas": 12, "linhas": 9,
                                         "passo_mm": 25.0, "eixo_m": 111.3}}}


def test_a_chave_do_selo_nao_indexa_o_layer():
    """Sem a marca, a estimada com o número do layer seria PROMOVIDA (controle)."""
    obs = "Fonte: layer 'E-CALHA-X' = 1058,79 m"
    ex = _Extr(dict(_MD), {"E-CALHA-X": 1058.79, "REDE": 300.0})
    esc = _roda("_nao_prova_ig = _layers_que_nao_provam(extraction.metadata)",
                {"extraction": ex, "_indice_geom": {"comprimento": [], "area": [], "contagem": []}})
    assert dict(esc["_indice_geom"]["comprimento"]) == {"REDE": 300.0}
    assert er.prova_da_geometria(1058.79, "ml", obs, esc["_indice_geom"]) == ""
    sem = _roda("_nao_prova_ig = _layers_que_nao_provam(extraction.metadata)",
                {"extraction": _Extr({}, {"E-CALHA-X": 1058.79, "REDE": 300.0}),
                 "_indice_geom": {"comprimento": [], "area": [], "contagem": []}})
    assert er.prova_da_geometria(1058.79, "ml", obs, sem["_indice_geom"]) != ""


def test_o_resgate_automatico_nao_preenche_com_o_layer():
    ex = _Extr(dict(_MD), {"E-CALHA-X": 1058.79, "REDE": 300.0})
    esc = _roda("_nao_prova_rs = _layers_que_nao_provam(extraction.metadata)", {"extraction": ex})
    assert set(esc["_compr_ly"]) == {"REDE"}, esc["_compr_ly"]


def test_o_laco_le_os_layers_marcados_da_extracao():
    ex = _Extr(dict(_MD), {})
    esc = _roda("_fx_ly = {str(_k).strip().upper() for _k in", {"extraction": ex})
    assert esc["_fx_ly"] == {"E-CALHA-X"}


def _cats_do_cross_check():
    import _executa
    esc = {}
    _executa.roda("process_job", "_AREA_CATS = {", esc)
    _executa.roda("process_job", "_LEN_CATS = {", esc)
    return {"_AREA_CATS": esc["_AREA_CATS"], "_LEN_CATS": esc["_LEN_CATS"]}


def _item_parede(conf):
    return {"item_num": "1", "description": "Parede de alvenaria",
            "unit": "ml", "quantity": 347.9, "confidence": conf,
            "observations": "Fonte: comprimento do layer 'A-WALL' = 347.90 m."}


def test_CONTROLE_com_o_cross_check_ligado_a_parede_que_bate_vira_medida(monkeypatch):
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    monkeypatch.setenv("DXF_CONFIRM_CROSSCHECK", "1")
    itens, _e, _ = _laco_de_itens_de_producao(
        [_item_parede("estimado")], areas={}, compr={"A-WALL": 347.9},
        extra={"_fx_ly": set(), "_hard_len_by_cat": {"paredes": {347.9}}, **_cats_do_cross_check()})
    assert itens[0].confidence.value == "confirmado", itens[0].observations


def test_com_o_cross_check_ligado_a_linha_rebaixada_nao_volta(monkeypatch):
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    monkeypatch.setenv("DXF_CONFIRM_CROSSCHECK", "1")
    itens, _e, _ = _laco_de_itens_de_producao(
        [_item_parede("confirmado")], areas={}, compr={"A-WALL": 347.9},
        extra={"_fx_ly": {"A-WALL"}, "_hard_len_by_cat": {"paredes": {347.9}}, **_cats_do_cross_check()})
    assert itens[0].confidence.value == "estimado" and "FAIXA DE PARALELAS" in itens[0].observations


def test_o_layer_marcado_nao_vira_medida_dura_do_cross_check():
    from test_crosscheck_respeita_as_marcas import _W as _Wx, _medidas_duras
    walls = (_Wx("A-WALL", 347.9), _Wx("PAREDE-INT", 30.0))
    comp, _ = _medidas_duras({"layers_em_faixa": {"A-WALL": {"fracao": 0.9}}}, walls=walls)
    assert comp.get("paredes") == {30.0}, comp
    comp0, _ = _medidas_duras({}, walls=walls)
    assert comp0.get("paredes") == {347.9, 30.0}, comp0
