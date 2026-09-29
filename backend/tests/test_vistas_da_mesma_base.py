# -*- coding: utf-8 -*-
"""A mesma peça em vistas temáticas do MESMO pavimento conta 1× — e só nesse caso.

🩸 28/09/2026 — caso 18c57c3c: quatro vistas do mesmo pavimento (alimentadores,
iluminação, sistemas, tomadas), a base de arquitetura inserida em cada uma. O
QDF-ADM1 e o QDF-MANUT aparecem em três vistas, no mesmo ponto da planta: a
planilha disse 11 quadros "✓ medido" e são 7.

🪤 Medido no acervo ANTES: a regra ingênua ("bloco grande inserido 2×, mesmo
deslocamento") apagava mesas de escritório em grade e as cópias do elétrico ×3.
Aqui ficam o caso e os quatro que NÃO podem mudar: andares, planta copiada,
grade de mesas e a peça que só está PERTO (não no mesmo ponto).
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402


def _novo():
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6            # metros
    base = doc.blocks.new("BASE_ARQ")
    base.add_lwpolyline([(0, 0), (100, 0), (100, 40), (0, 40)], close=True, dxfattribs={"layer": "ARQ"})
    for x in range(10, 100, 10):
        base.add_line((x, 0), (x, 40), dxfattribs={"layer": "ARQ"})
    for nome, r in (("TOMADA", 0.15), ("INTERRUPTOR", 0.1), ("PONTO_FORCA", 0.2), ("QUADRO", 0.3)):
        b = doc.blocks.new(nome)
        b.add_circle((0, 0), r)
        b.add_line((-r, 0), (r, 0))
    return doc


def _poe(msp, nome, origem, rel):
    for x, y in rel:
        msp.add_blockref(nome, (origem[0] + x, origem[1] + y), dxfattribs={"layer": "ELE"})


def _salva(doc, pasta, nome):
    p = os.path.join(str(pasta), nome)
    doc.saveas(p)
    return p


def _contagem(caminho):
    e = dx.extract_from_file(caminho)
    return {b.name: b.count for b in e.blocks}, e.metadata.get("vistas_da_mesma_base") or {}, e


_QUADROS = [(10, 10), (20, 10), (30, 30)]
_VISTAS = [(0, 0), (150, 0), (0, -100), (150, -100)]      # alimentadores, iluminação, sistemas, tomadas


def _tematicas(pasta, desvio=0.0):
    doc = _novo()
    msp = doc.modelspace()
    for o in _VISTAS:
        msp.add_blockref("BASE_ARQ", o, dxfattribs={"layer": "BASE"})
    _poe(msp, "PONTO_FORCA", _VISTAS[0], [(5 + 5 * i, 35) for i in range(15)])
    _poe(msp, "INTERRUPTOR", _VISTAS[1], [(5 + 4 * i, 20) for i in range(20)])
    _poe(msp, "TOMADA", _VISTAS[3], [(3 + 3 * i, 5 + (i % 3) * 10) for i in range(30)])
    for k, v in enumerate((0, 1, 3)):                     # o quadro nas vistas que o mostram
        rel = list(_QUADROS)
        if desvio and k == 2:
            rel[0] = (rel[0][0] + desvio, rel[0][1])
        _poe(msp, "QUADRO", _VISTAS[v], rel)
    return _salva(doc, pasta, "tematicas.dxf")


def test_o_quadro_repetido_nas_vistas_conta_uma_vez(tmp_path):
    c, v, _e = _contagem(_tematicas(tmp_path))
    assert c.get("QUADRO") == 3, (c, v)
    assert (c.get("TOMADA"), c.get("INTERRUPTOR"), c.get("PONTO_FORCA")) == (30, 20, 15), c
    assert v.get("aplicada") is True and v.get("repetidos", {}).get("QUADRO") == 6, v
    assert v.get("vistas") == 4
    assert c.get("BASE_ARQ") == 4, "a base é a VISTA, não peça — não se deduplica"


def test_perto_nao_e_o_mesmo_ponto(tmp_path):
    """A 0,3 m do outro não é a mesma peça (os conduletes do caso real ficaram 78)."""
    c, v, _e = _contagem(_tematicas(tmp_path, desvio=0.3))
    assert c.get("QUADRO") == 4, (c, v)


def test_o_log_de_producao_conta_o_que_saiu(tmp_path):
    import main
    _c, _v, e = _contagem(_tematicas(tmp_path))
    linha = main._procedencia_dos_blocos(e)
    assert "vistas=[aplicada n=4" in linha and "QUADRO=6" in linha, linha


def test_chave_desligada_nao_mexe(tmp_path, monkeypatch):
    monkeypatch.setenv("VISTAS_DA_MESMA_BASE", "0")
    c, v, _e = _contagem(_tematicas(tmp_path))
    assert c.get("QUADRO") == 9 and not v, (c, v)


def test_CONTROLE_andares_com_quadro_no_mesmo_shaft(tmp_path):
    """Prédio: a mesma base por andar, o quadro no MESMO ponto (shaft) em todos —
    são três quadros. As tomadas aparecem em todos os andares: não é vista temática."""
    doc = _novo()
    msp = doc.modelspace()
    andares = [(0, 0), (150, 0), (300, 0)]
    for k, o in enumerate(andares):
        msp.add_blockref("BASE_ARQ", o, dxfattribs={"layer": "BASE"})
        _poe(msp, "TOMADA", o, [(3 + 7 * i + k, 5 + (i % 3) * 10) for i in range(10)])
        _poe(msp, "QUADRO", o, [(50, 20)])
    c, v, _e = _contagem(_salva(doc, tmp_path, "andares.dxf"))
    assert c.get("QUADRO") == 3 and c.get("TOMADA") == 30, (c, v)
    assert v.get("aplicada") is False and "andares" in v.get("motivo", ""), v


def test_CONTROLE_planta_copiada_inteira(tmp_path):
    """Tudo repetido nas duas: é a planta copiada (terreno do D1), não vista temática."""
    doc = _novo()
    msp = doc.modelspace()
    for o in ((0, 0), (150, 0)):
        msp.add_blockref("BASE_ARQ", o, dxfattribs={"layer": "BASE"})
        _poe(msp, "TOMADA", o, [(3 + 7 * i, 5 + (i % 3) * 10) for i in range(10)])
        _poe(msp, "QUADRO", o, [(50, 20)])
    c, v, _e = _contagem(_salva(doc, tmp_path, "copiada.dxf"))
    assert c.get("TOMADA") == 20 and c.get("QUADRO") == 2, (c, v)
    assert v.get("aplicada") is False and "copiada" in v.get("motivo", ""), v


def test_CONTROLE_mesas_em_grade_nao_viram_base(tmp_path):
    """Escritório: 20 mesas iguais em grade. Mesa não é planta — nada muda."""
    doc = _novo()
    msp = doc.modelspace()
    mesa = doc.blocks.new("MESA")
    mesa.add_lwpolyline([(0, 0), (1.6, 0), (1.6, 0.8), (0, 0.8)], close=True)
    for i in range(20):
        o = (2.0 * (i % 5), 2.0 * (i // 5))
        msp.add_blockref("MESA", o)
        _poe(msp, "TOMADA", o, [(0.8, 0.4)])
    msp.add_blockref("BASE_ARQ", (-5, -5), dxfattribs={"layer": "BASE"})
    c, v, _e = _contagem(_salva(doc, tmp_path, "mesas.dxf"))
    assert c.get("MESA") == 20 and c.get("TOMADA") == 20 and not v.get("aplicada"), (c, v)


def test_CONTROLE_bloco_pequeno_repetido_nao_e_vista(tmp_path):
    """Só a trava da BASE segura: um detalhe de 0,5 m inserido 2× longe um do outro,
    com as tomadas todas perto de um deles e um quadro junto de cada. Sem a trava,
    os dois quadros (um em cada pilar) viravam um."""
    doc = _novo()
    msp = doc.modelspace()
    det = doc.blocks.new("DETALHE_PILAR")
    det.add_lwpolyline([(0, 0), (0.5, 0), (0.5, 0.5), (0, 0.5)], close=True)
    for o in ((0, 0), (60, 0)):
        msp.add_blockref("DETALHE_PILAR", o)
        _poe(msp, "QUADRO", o, [(0.1, 0.1)])
    _poe(msp, "TOMADA", (0, 0), [(0.02 + 0.04 * i, 0.3) for i in range(10)])
    c, v, _e = _contagem(_salva(doc, tmp_path, "pilares.dxf"))
    assert c.get("QUADRO") == 2 and not v.get("aplicada"), (c, v)


def test_CONTROLE_bases_sobrepostas_nao_sao_vistas(tmp_path):
    """Só a trava da SEPARAÇÃO segura: a base inserida 2× com 10 m de diferença
    (100 m de largura) — não são duas vistas, é a mesma área."""
    doc = _novo()
    msp = doc.modelspace()
    for o in ((0, 0), (10, 0)):
        msp.add_blockref("BASE_ARQ", o, dxfattribs={"layer": "BASE"})
    _poe(msp, "TOMADA", (0, 0), [(0.5 + 0.3 * i, 5 + (i % 3)) for i in range(30)])
    _poe(msp, "QUADRO", (0, 0), [(20, 20), (30, 20)])
    c, v, _e = _contagem(_salva(doc, tmp_path, "sobrepostas.dxf"))
    assert c.get("QUADRO") == 2 and not v.get("aplicada"), (c, v)


def test_base_girada_fica_de_fora(tmp_path):
    """A caixa da vista é calculada sem rotação: base girada não entra (conservador)."""
    doc = _novo()
    msp = doc.modelspace()
    for o in _VISTAS:
        msp.add_blockref("BASE_ARQ", o, dxfattribs={"layer": "BASE", "rotation": 90})
    _poe(msp, "PONTO_FORCA", _VISTAS[0], [(5 + 5 * i, 35) for i in range(15)])
    _poe(msp, "INTERRUPTOR", _VISTAS[1], [(5 + 4 * i, 20) for i in range(20)])
    _poe(msp, "TOMADA", _VISTAS[3], [(3 + 3 * i, 5 + (i % 3) * 10) for i in range(30)])
    for v_ in (0, 1, 3):
        _poe(msp, "QUADRO", _VISTAS[v_], _QUADROS)
    c, v, _e = _contagem(_salva(doc, tmp_path, "girada.dxf"))
    assert c.get("QUADRO") == 9 and not v.get("aplicada"), (c, v)


def test_pouca_prova_dentro_das_vistas_nao_age(tmp_path):
    """Com menos de 10 símbolos DENTRO das vistas não dá pra dizer que cada tipo
    mora na sua: os 60 do diagrama (fora das vistas) não contam como prova."""
    doc = _novo()
    msp = doc.modelspace()
    for o in ((0, 0), (150, 0)):
        msp.add_blockref("BASE_ARQ", o, dxfattribs={"layer": "BASE"})
        _poe(msp, "QUADRO", o, [(50, 20)])
    _poe(msp, "TOMADA", (150, 0), [(5 + 3 * i, 10) for i in range(5)])
    _poe(msp, "TOMADA", (0, -60), [(4 * i, 0) for i in range(60)])
    c, v, _e = _contagem(_salva(doc, tmp_path, "pouca_prova.dxf"))
    assert c.get("QUADRO") == 2 and not v.get("aplicada"), (c, v)


@pytest.mark.parametrize("trava", ["_VISTAS_PARCELA_MAX", "_VISTAS_EXCLUSIVIDADE_MIN"])
def test_as_travas_tem_valor_de_verdade(trava):
    assert 0 < getattr(dx, trava) < 1
