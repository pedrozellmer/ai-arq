# -*- coding: utf-8 -*-
"""Metro de layer de esteira que é peça curta solta não sai medido.

🩸 02/10/2026 — H88 do estudo do acervo. Um layout de fábrica entregou
"esteira 999,31 ml ✓" e "543,19 ml ✓": os layers de esteira traziam roletes,
travessas (em 2 linhas, de comprimentos diferentes) e caixas com X — peças
curtas soltas —, e o comprimento da esteira era ~60 m. Não existe no acervo
esteira legítima em layer de esteira: os controles são sintéticos (bordas e
eixo inteiros, em módulos, com folga, em curva, em perfil duplo).
"""
import math
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
from engine_rules import layers_que_nao_provam, selo_apos_travessa_de_esteira  # noqa: E402


def _linha(m, layer, y, x0, comp, modulo=None, folga=0.0, esc=1.0):
    """Linha ao longo de X — inteira, ou em módulos colineares (com folga)."""
    if not modulo:
        m.add_line((x0 * esc, y * esc), ((x0 + comp) * esc, y * esc), dxfattribs={"layer": layer})
        return
    x = x0
    while x < x0 + comp - 1e-9:
        m.add_line((x * esc, y * esc), ((min(x + modulo, x0 + comp) - folga) * esc, y * esc),
                   dxfattribs={"layer": layer})
        x += modulo


def _esteira(m, layer, comp=60.0, larg=2.0, passo=0.3, x0=0.0, y0=0.0, roletes=True,
             bordas=False, eixo=False, modulo=None, folga=0.0, perfil=0.0, esc=1.0):
    """Esteira ao longo de X. `perfil`: cada borda em 2 linhas a essa distância."""
    if roletes:
        k = 0
        while k * passo <= comp + 1e-9:
            x = x0 + k * passo
            m.add_line((x * esc, (y0 - larg / 2) * esc), (x * esc, (y0 + larg / 2) * esc),
                       dxfattribs={"layer": layer})
            k += 1
    if bordas:
        for y in (y0 - larg / 2, y0 + larg / 2):
            _linha(m, layer, y, x0, comp, modulo, folga, esc)
            if perfil:
                _linha(m, layer, y + perfil * (1 if y > y0 else -1), x0, comp, modulo, folga, esc)
    if eixo:
        _linha(m, layer, y0, x0, comp, modulo, folga, esc)


def _travessas_e_caixas(m, layer):
    """O desenho da esteira proposta: travessas de ~2 m em 2 linhas a 4,4 cm, a
    1,3 m uma da outra, de comprimentos DIFERENTES; caixas com X; e algum
    detalhe longo."""
    compr = (1.96, 2.01, 2.12, 2.17, 2.41)
    for k in range(46):
        x, L = k * 1.3, compr[k % 5]
        for dx_ in (0.0, 0.044):
            m.add_line((x + dx_, -L / 2), (x + dx_, L / 2), dxfattribs={"layer": layer})
    for k in range(10):
        x0, y0, w, h = k * 3.0, 8.0, 1.8, 2.2
        m.add_lwpolyline([(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)], close=True,
                         dxfattribs={"layer": layer})
        m.add_line((x0, y0), (x0 + w, y0 + h), dxfattribs={"layer": layer})
        m.add_line((x0 + w, y0), (x0, y0 + h), dxfattribs={"layer": layer})
    for y in (20.0, 22.0, 24.0):
        m.add_line((0, y), (60.0, y), dxfattribs={"layer": layer})


def _ler(tmp_path, desenha, insunits=6):
    d = ezdxf.new("R2018")
    d.header["$INSUNITS"] = insunits
    m = d.modelspace()
    desenha(m)
    p = str(tmp_path / "fabrica.dxf")
    d.saveas(p)
    return dx.extract_dxf(p)


def _marcados(ex):
    return ex.metadata.get("layers_esteira_por_travessa") or {}


def test_o_caso_so_roletes_no_layer_de_esteira(tmp_path):
    ex = _ler(tmp_path, lambda m: _esteira(m, "Conveyor_Proposed"))
    est = _marcados(ex)
    assert "Conveyor_Proposed" in est, est
    assert est["Conveyor_Proposed"]["fracao"] >= 0.9
    assert abs(est["Conveyor_Proposed"]["peca_m"] - 2.0) < 0.01
    assert "CONVEYOR_PROPOSED" in layers_que_nao_provam(ex.metadata)
    assert "ROLETES/TRAVESSAS" in ex.to_structured_prompt()


def test_o_caso_travessas_em_2_linhas_e_caixas_com_x(tmp_path):
    """A esteira que a régua de fileira perdia: as travessas não são gêmeas
    (comprimentos diferentes, longe uma da outra) — mas são soltas. E o picado
    de 3 cm (mil pedacinhos) não manda na peça típica: a mediana é pelo metro."""
    def d(m):
        _travessas_e_caixas(m, "Conveyor_Proposed")
        for k in range(1000):
            x, y = (k % 50) * 0.5, 30.0 + (k // 50) * 0.5
            m.add_line((x, y), (x + 0.03, y + 0.01), dxfattribs={"layer": "Conveyor_Proposed"})
    ex = _ler(tmp_path, d)
    est = _marcados(ex)
    assert "Conveyor_Proposed" in est and 0.5 <= est["Conveyor_Proposed"]["fracao"] < 0.9, est
    assert est["Conveyor_Proposed"]["peca_m"] >= 1.5, est


def test_o_caso_roletes_de_faixas_empilhadas(tmp_path):
    """A esteira existente: faixas empilhadas a 17 cm uma da outra, e o rolete de
    cada faixa cai na MESMA reta do rolete da vizinha — "emenda" pela folga.
    Não é solto; é escada (passo de 16 cm em roletes de 2,13 m)."""
    def d(m):
        for y0 in (0.0, 2.3, 4.6):
            _esteira(m, "Conveyor_Existing", comp=30.0, larg=2.13, passo=0.16, y0=y0,
                     bordas=True)
    ex = _ler(tmp_path, d)
    est = _marcados(ex)
    assert "Conveyor_Existing" in est and est["Conveyor_Existing"]["fracao"] >= 0.5, est


def test_bordas_mais_roletes_tambem_marca(tmp_path):
    """A existente tinha as bordas desenhadas e o total ainda era 9× o eixo."""
    ex = _ler(tmp_path, lambda m: _esteira(m, "Conveyor_Existing", larg=2.13, passo=0.5,
                                           bordas=True))
    est = _marcados(ex)
    assert "Conveyor_Existing" in est and 0.5 <= est["Conveyor_Existing"]["fracao"] < 0.9, est


def test_em_milimetro(tmp_path):
    ex = _ler(tmp_path, lambda m: _esteira(m, "ESTEIRA TRANSPORTADORA", esc=1000.0), insunits=4)
    assert "ESTEIRA TRANSPORTADORA" in _marcados(ex)


def test_layer_acima_do_teto_de_trechos_nao_roda(tmp_path, monkeypatch, caplog):
    """Um layer de esteira gigante não pode prender o worker: acima do teto,
    não mede e diz no log (a linha fica como estava)."""
    monkeypatch.setattr(dx, "_ESTEIRA_MAX_TRECHOS", 50)
    with caplog.at_level("WARNING"):
        ex = _ler(tmp_path, lambda m: _esteira(m, "Conveyor_Proposed"))
    assert "Conveyor_Proposed" not in _marcados(ex)
    assert "acima do teto" in caplog.text


def test_a_linha_confirmada_em_metro_cai():
    conf, obs, reb = selo_apos_travessa_de_esteira(
        "confirmado", "layer Conveyor_Proposed", "ml", ["Conveyor_Proposed"],
        {"Conveyor_Proposed": {}})
    assert reb and conf == "estimado" and "ROLETES/TRAVESSAS" in obs


def test_a_contagem_nao_cai():
    conf, _obs, reb = selo_apos_travessa_de_esteira(
        "confirmado", "", "un", ["Conveyor_Proposed"], {"Conveyor_Proposed": {}})
    assert not reb and conf == "confirmado"


def test_o_laco_de_producao_rebaixa_a_linha():
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    item = {"item_num": "1", "description": "Esteira transportadora proposta",
            "unit": "ml", "quantity": 999.31, "confidence": "confirmado",
            "observations": "Fonte: comprimento do layer 'Conveyor_Proposed' = 999.31 m."}
    itens, _e, _ = _laco_de_itens_de_producao(
        [item], areas={}, compr={"Conveyor_Proposed": 999.31},
        extra={"_est_ly": {"CONVEYOR_PROPOSED"}})
    assert itens[0].confidence.value == "estimado"
    assert "ROLETES/TRAVESSAS" in itens[0].observations


# ── o que NÃO muda: esteira de verdade, em todas as formas de desenhar ──────────
def test_CONTROLE_esteira_so_pelas_bordas(tmp_path):
    ex = _ler(tmp_path, lambda m: _esteira(m, "Conveyor", roletes=False, bordas=True, larg=1.8))
    assert "Conveyor" not in _marcados(ex)


def test_CONTROLE_esteira_so_pelo_eixo(tmp_path):
    ex = _ler(tmp_path, lambda m: _esteira(m, "Conveyor", roletes=False, eixo=True))
    assert "Conveyor" not in _marcados(ex)


@pytest.mark.parametrize("eixo", [False, True])
def test_CONTROLE_bordas_em_modulos_colineares(tmp_path, eixo):
    """Módulos de 2,4 m emendados em fila: cada um continua no seguinte."""
    ex = _ler(tmp_path, lambda m: _esteira(m, "Conveyor", roletes=False, bordas=True,
                                           eixo=eixo, larg=1.8, modulo=2.4))
    assert "Conveyor" not in _marcados(ex)


def test_CONTROLE_modulos_com_folga_de_2_cm(tmp_path):
    """Os módulos não se tocam (2 cm entre um e outro): continuam na mesma reta."""
    ex = _ler(tmp_path, lambda m: _esteira(m, "Conveyor", roletes=False, bordas=True,
                                           larg=1.8, modulo=2.4, folga=0.02))
    assert "Conveyor" not in _marcados(ex)


@pytest.mark.parametrize("folga", [0.0, 0.02])
def test_CONTROLE_modulos_desalinhados_3_mm(tmp_path, folga):
    """Desenho à mão: um módulo sim, outro não, 3 mm fora da reta — encostado
    ou com folga, ainda é a mesma borda."""
    def d(m):
        for y in (-0.9, 0.9):
            for k in range(25):
                yy = y + (0.003 if k % 2 else 0.0)
                m.add_line((k * 2.4, yy), ((k + 1) * 2.4 - folga, yy),
                           dxfattribs={"layer": "Conveyor"})
    ex = _ler(tmp_path, d)
    assert "Conveyor" not in _marcados(ex)


def test_CONTROLE_bordas_em_perfil_duplo(tmp_path):
    """Cada borda em 2 linhas a 3 cm, em módulos de 2,4 m: a linha de perfil
    continua no módulo seguinte, não é travessa."""
    ex = _ler(tmp_path, lambda m: _esteira(m, "Conveyor", roletes=False, bordas=True,
                                           larg=1.8, modulo=2.4, perfil=0.03))
    assert "Conveyor" not in _marcados(ex)


def test_CONTROLE_eixo_em_curva_de_polilinha(tmp_path):
    """Eixo que faz curva em trechos de 1 m girando 10° a cada vértice."""
    def d(m):
        pts, x, y, a = [(0.0, 0.0)], 0.0, 0.0, 0.0
        for _k in range(40):
            x, y = x + math.cos(math.radians(a)), y + math.sin(math.radians(a))
            pts.append((x, y))
            a += 10.0
        m.add_lwpolyline(pts, dxfattribs={"layer": "Conveyor"})
    ex = _ler(tmp_path, d)
    assert "Conveyor" not in _marcados(ex)


@pytest.mark.parametrize("trecho", [1.0, 1.55])
def test_CONTROLE_eixo_em_curva_suave(tmp_path, trecho):
    """Curva de raio grande: trechos girando 1° — quase paralelos e perto de
    lado, mas um DEPOIS do outro, não ao lado: não é escada. Dois tamanhos de
    trecho, que caem em níveis diferentes da grade de busca."""
    def d(m):
        pts, x, y, a = [(0.0, 0.0)], 0.0, 0.0, 0.0
        for _k in range(60):
            x, y = (x + trecho * math.cos(math.radians(a)),
                    y + trecho * math.sin(math.radians(a)))
            pts.append((x, y))
            a += 1.0
        m.add_lwpolyline(pts, dxfattribs={"layer": "Conveyor"})
    ex = _ler(tmp_path, d)
    assert "Conveyor" not in _marcados(ex)


@pytest.mark.parametrize("copia", [False, True])
def test_CONTROLE_esteira_estreita_bordas_e_eixo_em_modulos(tmp_path, copia):
    """Esteira de 60 cm: as duas bordas e o eixo em módulos de 2,4 m ficam a
    0,125 L — 3 posições de lado, não escada. Colada de novo a 5 mm, continuam 3."""
    def d(m):
        _esteira(m, "Conveyor", roletes=False, bordas=True, eixo=True, larg=0.6, modulo=2.4)
        if copia:
            _esteira(m, "Conveyor", roletes=False, bordas=True, eixo=True, larg=0.6,
                     modulo=2.4, y0=0.005)
    ex = _ler(tmp_path, d)
    assert "Conveyor" not in _marcados(ex)


def test_CONTROLE_layer_de_cota_da_esteira(tmp_path):
    """Conveyor_DIM é anotação: não entra na régua (o prompt já diz ANOTAÇÃO)."""
    ex = _ler(tmp_path, lambda m: _esteira(m, "Conveyor_DIM"))
    assert "Conveyor_DIM" not in _marcados(ex)


def test_CONTROLE_borda_em_modulos_copiada_quase_em_pilha(tmp_path):
    def d(m):
        _esteira(m, "Conveyor", roletes=False, bordas=True, larg=1.8, modulo=2.4)
        _esteira(m, "Conveyor", roletes=False, bordas=True, larg=1.8, modulo=2.4, y0=0.005)
    ex = _ler(tmp_path, d)
    assert "Conveyor" not in _marcados(ex)


def test_CONTROLE_esteiras_paralelas_pelas_bordas_em_modulos(tmp_path):
    def d(m):
        for k in range(4):
            _esteira(m, "Conveyor", roletes=False, bordas=True, larg=1.8, modulo=2.4,
                     y0=3.0 * k)
    ex = _ler(tmp_path, d)
    assert "Conveyor" not in _marcados(ex)


def test_CONTROLE_transportadores_curtos_de_5_m_pelo_eixo(tmp_path):
    """Doze transportadores de 5 m, cada um uma linha solta: são comprimento
    (passam da largura máxima de esteira)."""
    def d(m):
        for k in range(12):
            m.add_line((k * 8.0, 0), (k * 8.0 + 5.0, 0), dxfattribs={"layer": "Conveyor"})
    ex = _ler(tmp_path, d)
    assert "Conveyor" not in _marcados(ex)


def test_CONTROLE_roletes_colados_duas_vezes_contam_uma(tmp_path):
    """40 % do metro em rolete (bordas de 2 × 150 m + 30 m de roletes), com os
    roletes colados 2× no mesmo lugar: o total conta a cópia uma vez (H84), e o
    rolete também — senão viraria 80 %."""
    def d(m):
        _esteira(m, "Conveyor", comp=150.0, roletes=False, bordas=True)
        _esteira(m, "Conveyor", comp=30.0, y0=10.0)
        _esteira(m, "Conveyor", comp=30.0, y0=10.0)
    ex = _ler(tmp_path, d)
    assert "Conveyor" not in _marcados(ex)


@pytest.mark.parametrize("layer", ["TESTEIRA", "ESCADA", "GUARDA-CORPO"])
def test_CONTROLE_nome_que_nao_e_esteira(tmp_path, layer):
    """Degrau de escada e montante de guarda-corpo também são peças soltas:
    o nome segura. "testeira" tem "esteira" dentro."""
    ex = _ler(tmp_path, lambda m: _esteira(m, layer))
    assert layer not in _marcados(ex)
