# -*- coding: utf-8 -*-
"""O cross-check (DXF_CONFIRM_CROSSCHECK) não passa por cima das marcas.

🩸 04/10/2026 (guarda, pedido do Pedro). O cross-check promove "estimado" →
"confirmado" quando o número da IA bate com uma medida DURA da prancha. As
medidas duras saíam de TODOS os layers de parede/piso: moldura (H79), esteira
(H88), tubo em face dupla (H34/H75), contorno de peça (H76), cota explodida,
zona cinza do eixo, layer sem nome — exatamente o que a chave do selo deixa de
fora. Desligado em produção; mas, se alguém o ligasse, devolvia ✓ a todas as
linhas que essas marcas rebaixam. E promovia mesmo com ressalva de unidade.

Os testes EXECUTAM os statements reais de `process_job` (`_executa`), não leem
o fonte.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import _executa  # noqa: E402
import main  # noqa: E402


class _W:
    def __init__(self, layer, length):
        self.layer, self.length = layer, length


class _Ext:
    def __init__(self, metadata=None, secoes=()):
        self.metadata = metadata or {}
        self.polygon_areas = []
        self._secoes = set(secoes)

    def get_layers_secao_de_parede(self):
        return self._secoes


_PASSOS = ('_cats_geo = identify_architectural_elements(extraction)',
           '_AREA_CATS = {"piso", "forro", "pintura"}',
           '_LEN_CATS = {"paredes", "demolicao"}',
           '_XC_AREA_DENY = ("piscina"',
           '_xc_nao_prova, _xc_cinza, _xc_secoes = _xc_camadas_que_nao_provam(extraction)',
           'def _xc_layer_ok(',
           '_hard_area_by_cat: dict[str, set] = {}',
           '_hard_len_by_cat: dict[str, set] = {}',
           'for _ck, _cd in _cats_geo.items():')


def _medidas_duras(metadata=None, secoes=(), walls=(), hatches=()):
    """Roda, na ordem, os statements REAIS que montam as medidas duras."""
    escopo = dict(vars(main))
    cats = {"paredes": {"walls": list(walls), "hatches": []},
            "piso": {"walls": [], "hatches": list(hatches)}}
    escopo.update({"extraction": _Ext(metadata, secoes),
                   "identify_architectural_elements": lambda _e: cats})
    for marca in _PASSOS:
        _executa.roda("process_job", marca, escopo)
    return escopo["_hard_len_by_cat"], escopo["_hard_area_by_cat"]


_PAREDES = (_W("A-WALL", 100.0), _W("BORDA", 500.0), _W("P-CINZA", 300.0), _W("250", 77.0))


def test_layer_marcado_nao_vira_medida_dura():
    md = {"layers_moldura_ou_limite": {"BORDA": {"m": 500.0}},
          "parede_zona_cinza": {"P-CINZA": {"fracao": 0.3}}}
    comp, _ = _medidas_duras(md, walls=_PAREDES)
    assert comp.get("paredes") == {100.0}, comp


def test_CONTROLE_sem_marca_todos_entram_menos_o_sem_nome():
    comp, _ = _medidas_duras({}, walls=_PAREDES)
    assert comp.get("paredes") == {100.0, 500.0, 300.0}, comp


def test_a_esteira_e_a_face_dupla_tambem_ficam_fora():
    md = {"layers_esteira_por_travessa": {"BORDA": {}},
          "tubos_em_face_dupla": {"P-CINZA": {}}}
    comp, _ = _medidas_duras(md, walls=_PAREDES)
    assert comp.get("paredes") == {100.0}, comp


class _H:
    def __init__(self, layer, area):
        self.layer, self.area = layer, area


def test_secao_de_parede_nao_vira_area_dura():
    _, area = _medidas_duras({}, secoes={"PISO-SECAO"},
                             hatches=(_H("PISO-SALA", 42.0), _H("PISO-SECAO", 0.18)))
    assert area.get("piso") == {42.0}, area


# ── a promoção, no laço de itens de produção ───────────────────────────────────
def _cats_reais():
    """`_AREA_CATS` e `_LEN_CATS` saem dos statements REAIS (montados antes do laço)."""
    d = dict(vars(main))
    _executa.roda("process_job", '_AREA_CATS = {"piso", "forro", "pintura"}', d)
    _executa.roda("process_job", '_LEN_CATS = {"paredes", "demolicao"}', d)
    return {"_AREA_CATS": d["_AREA_CATS"], "_LEN_CATS": d["_LEN_CATS"]}


def _item_alvenaria(qtd):
    return {"item_num": "1", "description": "Alvenaria de vedação em bloco cerâmico",
            "unit": "ml", "quantity": qtd, "confidence": "estimado",
            "observations": "Comprimento de parede da prancha."}


def test_com_ressalva_de_unidade_nao_promove(monkeypatch):
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    monkeypatch.setenv("DXF_CONFIRM_CROSSCHECK", "1")
    itens, _e, _ = _laco_de_itens_de_producao(
        [_item_alvenaria(123.45)], areas={}, compr={},
        extra={**_cats_reais(), "_hard_len_by_cat": {"paredes": {123.45}},
               "extraction": _Ext({"alerta_unidade": "unidade corrigida por plausibilidade"})})
    assert itens[0].confidence.value == "estimado", itens[0].observations


def test_CONTROLE_sem_ressalva_o_cross_check_ainda_promove(monkeypatch):
    """O cross-check continua fazendo o que fazia quando nada o impede."""
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    monkeypatch.setenv("DXF_CONFIRM_CROSSCHECK", "1")
    itens, _e, _ = _laco_de_itens_de_producao(
        [_item_alvenaria(123.45)], areas={}, compr={},
        extra={**_cats_reais(), "_hard_len_by_cat": {"paredes": {123.45}}, "extraction": _Ext({})})
    assert itens[0].confidence.value == "confirmado", itens[0].observations


def test_CONTROLE_desligado_nao_promove_nada(monkeypatch):
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    monkeypatch.setenv("DXF_CONFIRM_CROSSCHECK", "0")
    itens, _e, _ = _laco_de_itens_de_producao(
        [_item_alvenaria(123.45)], areas={}, compr={},
        extra={**_cats_reais(), "_hard_len_by_cat": {"paredes": {123.45}}, "extraction": _Ext({})})
    assert itens[0].confidence.value == "estimado"
