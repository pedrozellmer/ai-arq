# -*- coding: utf-8 -*-
"""Metro que é lado de moldura / limite de obra não sai medido.

🩸 01/10/2026 — H79 do estudo do acervo. Um projeto de incêndio entregou
"ramais secundários 12.642 ml ✓": 72 % do layer eram os lados de retângulos
de ~494 × 461 m (o limite da obra, repetido). O retângulo de lados contínuos
separa; parede e muro (que é quantidade) ficam de fora.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
from engine_rules import layers_que_nao_provam, selo_apos_moldura_ou_limite  # noqa: E402


def _ret(msp, layer, x0, y0, w, h, pedacos=1, poli=False):
    if poli:
        msp.add_lwpolyline([(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)],
                           close=True, dxfattribs={"layer": layer})
        return
    for a, b in (((x0, y0), (x0 + w, y0)), ((x0 + w, y0), (x0 + w, y0 + h)),
                 ((x0 + w, y0 + h), (x0, y0 + h)), ((x0, y0 + h), (x0, y0))):
        for k in range(pedacos):
            p = (a[0] + (b[0] - a[0]) * k / pedacos, a[1] + (b[1] - a[1]) * k / pedacos)
            q = (a[0] + (b[0] - a[0]) * (k + 1) / pedacos, a[1] + (b[1] - a[1]) * (k + 1) / pedacos)
            msp.add_line(p, q, dxfattribs={"layer": layer})


def _rede(msp, layer, n=10, comp=120.0, x0=20.0, y0=20.0):
    """Ramais soltos (sem fechar retângulo)."""
    for i in range(n):
        msp.add_line((x0, y0 + i * 9.0), (x0 + comp, y0 + i * 9.0 + 3.0), dxfattribs={"layer": layer})


def _ler(tmp_path, desenha):
    d = ezdxf.new("R2018")
    d.header["$INSUNITS"] = 6
    desenha(d.modelspace())
    p = str(tmp_path / "obra.dxf")
    d.saveas(p)
    return dx.extract_dxf(p)


def test_o_caso_limite_de_obra_repetido_no_layer_de_ramal(tmp_path):
    def d(m):
        for k in range(3):
            _ret(m, "INC_LIN02", k * 520.0, 0, 494.0, 461.0)
        _rede(m, "INC_LIN02", n=10)                     # ~1.200 m de rede de verdade
    ex = _ler(tmp_path, d)
    mol = ex.metadata.get("layers_moldura_ou_limite") or {}
    assert "INC_LIN02" in mol and mol["INC_LIN02"]["fracao"] >= 0.5, mol
    assert "INC_LIN02" in layers_que_nao_provam(ex.metadata)
    assert "MOLDURA OU LIMITE" in ex.to_structured_prompt()


@pytest.mark.parametrize("pedacos,poli", [(3, False), (1, True)])
def test_moldura_em_pedacos_ou_em_polilinha(tmp_path, pedacos, poli):
    def d(m):
        _ret(m, "BORDAS ESPESSAS", 0, 0, 841.0, 594.0, pedacos=pedacos, poli=poli)
        _rede(m, "REDE", n=5)
    ex = _ler(tmp_path, d)
    assert "BORDAS ESPESSAS" in (ex.metadata.get("layers_moldura_ou_limite") or {})


def test_a_linha_confirmada_em_metro_cai():
    conf, obs, reb = selo_apos_moldura_ou_limite(
        "confirmado", "layer INC_LIN02", "ml", ["INC_LIN02"], {"INC_LIN02": {}})
    assert reb and conf == "estimado" and "MOLDURA OU LIMITE" in obs


def test_o_laco_de_producao_rebaixa_a_linha():
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    item = {"item_num": "1", "description": "Ramais secundários de incêndio",
            "unit": "ml", "quantity": 12642.0, "confidence": "confirmado",
            "observations": "Fonte: comprimento do layer 'INC_LIN02' = 12642.0 m."}
    itens, _e, _ = _laco_de_itens_de_producao(
        [item], areas={}, compr={"INC_LIN02": 12642.0}, extra={"_mol_ly": {"INC_LIN02"}})
    assert itens[0].confidence.value == "estimado" and "MOLDURA OU LIMITE" in itens[0].observations


# ── o que NÃO muda ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("layer", ["MURO DE DIVISA", "CERCA", "PAREDE", "A-WALL"])
def test_CONTROLE_muro_e_parede_ficam(tmp_path, layer):
    ex = _ler(tmp_path, lambda m: (_ret(m, layer, 0, 0, 300.0, 200.0), _rede(m, "REDE", n=3)))
    assert layer not in (ex.metadata.get("layers_moldura_ou_limite") or {})


def test_CONTROLE_rede_sem_retangulo(tmp_path):
    ex = _ler(tmp_path, lambda m: (_ret(m, "0", 0, 0, 300.0, 200.0), _rede(m, "MEIO-FIO", n=12)))
    assert "MEIO-FIO" not in (ex.metadata.get("layers_moldura_ou_limite") or {})


def test_CONTROLE_rua_com_os_dois_meios_fios_paralelos(tmp_path):
    """Duas bordas da mesma extensão, sem os lados verticais: é rua, não moldura."""
    def d(m):
        _ret(m, "0", 0, 0, 400.0, 300.0)
        for k in range(4):
            y = 20.0 + k * 60.0
            m.add_line((10, y), (350, y), dxfattribs={"layer": "MEIO-FIO"})
            m.add_line((10, y + 8.0), (350, y + 8.0), dxfattribs={"layer": "MEIO-FIO"})
    ex = _ler(tmp_path, d)
    assert "MEIO-FIO" not in (ex.metadata.get("layers_moldura_ou_limite") or {})


def test_CONTROLE_retangulos_pequenos_sao_ambientes(tmp_path):
    """Rodapé em volta de salas de 4 × 3 m num desenho de 300 m: lado < 10 %."""
    def d(m):
        _ret(m, "0", 0, 0, 300.0, 200.0)
        for i in range(20):
            _ret(m, "RODAPE", 10 + (i % 5) * 6.0, 10 + (i // 5) * 5.0, 4.0, 3.0)
    ex = _ler(tmp_path, d)
    assert "RODAPE" not in (ex.metadata.get("layers_moldura_ou_limite") or {})


def test_CONTROLE_menos_da_metade_em_retangulo(tmp_path):
    def d(m):
        _ret(m, "INC_LIN02", 0, 0, 300.0, 200.0)          # 1.000 m de retângulo
        _rede(m, "INC_LIN02", n=10, comp=150.0)           # ~1.500 m de rede
    ex = _ler(tmp_path, d)
    assert "INC_LIN02" not in (ex.metadata.get("layers_moldura_ou_limite") or {})
