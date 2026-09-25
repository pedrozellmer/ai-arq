# -*- coding: utf-8 -*-
"""A base do pavimento redesenhada em várias plantas temáticas conta UMA vez.

🩸 25/09/2026 — job `befab5aa` (projeto de interiores): 5 plantas do MESMO
apartamento no mesmo DWG — original, luminotécnica, pontos elétricos e duas
opções de layout. Todas 'planta' de um andar: a leitura por folha dizia "nada
muda" e o motor somava as cinco. Guarda-corpo: 25,93 m em CADA planta →
129,64 m "✓ MEDIDO". Janela ×3, parede ×2, cadeira ×3.
Medido no acervo local: plantas-chave "PONTOS / FORRO / PISO / PLANTA BAIXA"
em folhas de elevação repetiam 18–22% do comprimento do arquivo.

Regras que os guardas prendem:
- mesmo layer, mesmo comprimento (±0,5%, ≥ 1 m) em 2+ plantas temáticas → 1×;
- o que só uma planta tem (o circuito da luminotécnica) fica inteiro;
- pavimento/unidade diferente no título NUNCA junta (térreo × superior, bloco A × B);
- títulos diferentes que não são temáticos não juntam; iguais juntam.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402

ALVO = (31.0, 11.0)


def _viewport(lay, janela):
    x0, y0, x1, y1 = janela
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    esc = 10.0
    vp = lay.add_viewport(center=(200, 150), size=((x1 - x0) * esc, (y1 - y0) * esc),
                          view_center_point=(cx, cy), view_height=(y1 - y0))
    vp.dxf.view_target_point = (ALVO[0], ALVO[1], 0)
    vp.dxf.view_center_point = (cx - ALVO[0], cy - ALVO[1])


def _titulo(msp, doc, texto, x, y):
    if "TIT" not in doc.blocks:
        b = doc.blocks.new("TIT")
        b.add_attdef("TITULODODESENHO", (0, 0), dxfattribs={"height": 0.3})
    msp.add_blockref("TIT", (x, y)).add_attrib("TITULODODESENHO", texto, (x, y))


def _arquivo(tmp_path, titulos=("PLANTA DE LAYOUT", "PLANTA LUMINOTÉCNICA", "PLANTA DE PONTOS"),
             guarda=(10.0, 10.0, 10.0), extra_lumi=True, folhas=None):
    """Uma planta por titulo, lado a lado (x = 40·k): a MESMA base (guarda-corpo,
    2 cadeiras, 12 m² de piso) em todas; só a 2ª tem o circuito (7 m)."""
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    cad = doc.blocks.new("CADEIRA")
    cad.add_circle((0, 0), 0.25)
    for k, t in enumerate(titulos):
        ox = 40.0 * k
        msp.add_line((ox + 2, 5), (ox + 2 + guarda[k], 5), dxfattribs={"layer": "GUARDA"})
        msp.add_blockref("CADEIRA", (ox + 4, 8), dxfattribs={"layer": "MOB"})
        msp.add_blockref("CADEIRA", (ox + 6, 8), dxfattribs={"layer": "MOB"})
        h = msp.add_hatch(dxfattribs={"layer": "PISO"})
        h.paths.add_polyline_path([(ox + 2, 10), (ox + 6, 10), (ox + 6, 13), (ox + 2, 13)], is_closed=True)
        if extra_lumi and k == 1:
            msp.add_line((ox + 3, 12), (ox + 10, 12), dxfattribs={"layer": "LUMI"})
        _titulo(msp, doc, t, ox + 5, 1)
        _viewport(doc.layouts.new(folhas[k] if folhas else "F%d" % k), (ox, 0, ox + 20, 15))
    p = str(tmp_path / "interiores.dxf")
    doc.saveas(p)
    return p


def _ler(tmp_path, monkeypatch, liga=True, **kw):
    if liga:
        monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    else:
        monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    ex = dx.extract_dxf(_arquivo(tmp_path, **kw))
    return ex.get_walls_by_layer(), ex.get_block_summary(), ex


# ── o caso ─────────────────────────────────────────────────────────────────────
def test_a_base_repetida_nas_plantas_tematicas_conta_uma_vez(tmp_path, monkeypatch):
    wl, bs, ex = _ler(tmp_path, monkeypatch)
    assert wl.get("GUARDA") == pytest.approx(10.0), "3 plantas do mesmo apto: o guarda-corpo é UM"
    assert bs.get("CADEIRA") == 2
    assert ex.get_areas_by_layer().get("PISO") == pytest.approx(12.0)
    assert ex.folhas.get("aplicada") is True and ex.folhas.get("repetidas")


def test_o_que_so_uma_planta_tem_fica_inteiro(tmp_path, monkeypatch):
    wl, _, _ = _ler(tmp_path, monkeypatch)
    assert wl.get("LUMI") == pytest.approx(7.0)


def test_CONTROLE_a_chave_desliga_e_soma_como_antes(tmp_path, monkeypatch):
    wl, bs, ex = _ler(tmp_path, monkeypatch, liga=False)
    assert wl.get("GUARDA") == pytest.approx(30.0) and bs.get("CADEIRA") == 6
    assert ex.get_areas_by_layer().get("PISO") == pytest.approx(36.0)


# ── o que NUNCA pode juntar ───────────────────────────────────────────────────
@pytest.mark.parametrize("titulos", [
    ("PLANTA TÉRREO", "PLANTA SUPERIOR"),
    ("PLANTA BLOCO A", "PLANTA BLOCO B"),
    ("PLANTA DE LAYOUT 1º PAVIMENTO", "PLANTA DE LAYOUT 2º PAVIMENTO"),
    ("PLANTA CASA 1", "PLANTA CASA 2"),
], ids=["terreo-superior", "bloco-a-b", "pavimentos", "casas"])
def test_CONTROLE_pavimento_ou_unidade_diferente_nunca_junta(tmp_path, monkeypatch, titulos):
    wl, bs, _ = _ler(tmp_path, monkeypatch, titulos=titulos, guarda=(10.0, 10.0), extra_lumi=False)
    assert wl.get("GUARDA") == pytest.approx(20.0), "são dois andares/unidades de verdade"
    assert bs.get("CADEIRA") == 4


def test_CONTROLE_titulos_diferentes_sem_tema_nao_juntam(tmp_path, monkeypatch):
    wl, _, _ = _ler(tmp_path, monkeypatch, titulos=("PLANTA BAIXA", "PLANTA GERAL"),
                    guarda=(10.0, 10.0), extra_lumi=False)
    assert wl.get("GUARDA") == pytest.approx(20.0)


def test_titulos_iguais_juntam(tmp_path, monkeypatch):
    """Planta-chave repetida na folha ("PLANTA BAIXA" duas vezes): é a mesma."""
    wl, _, _ = _ler(tmp_path, monkeypatch, titulos=("PLANTA BAIXA", "PLANTA BAIXA"),
                    guarda=(10.0, 10.0), extra_lumi=False)
    assert wl.get("GUARDA") == pytest.approx(10.0)


@pytest.mark.parametrize("outro, esperado", [(10.04, 10.0), (9.9, 19.9)],
                         ids=["meio-por-cento-junta", "um-por-cento-nao"])
def test_so_o_mesmo_comprimento_e_repeticao(tmp_path, monkeypatch, outro, esperado):
    """A parede nova do layout muda o comprimento: aí não é repetição, fica."""
    wl, _, _ = _ler(tmp_path, monkeypatch, titulos=("PLANTA DE LAYOUT", "PLANTA ORIGINAL"),
                    guarda=(10.0, outro), extra_lumi=False)
    assert wl.get("GUARDA") == pytest.approx(esperado, abs=0.01)


def test_CONTROLE_planta_que_vale_por_andares_fica_fora_da_repeticao(tmp_path, monkeypatch):
    """A folha "4 - 5 E 6 PAV." faz a 1ª planta valer ×3. Ela não entra na conta
    de repetição: juntar e multiplicar ao mesmo tempo é um palpite em cima do
    outro — fica como a leitura por folha já fazia (3×10 + 10)."""
    wl, _, _ = _ler(tmp_path, monkeypatch, titulos=("PLANTA DE LAYOUT", "PLANTA DE PONTOS"),
                    guarda=(10.0, 10.0), extra_lumi=False, folhas=("4 - 5 E 6 PAV.", "PONTOS"))
    assert wl.get("GUARDA") == pytest.approx(40.0)


def test_CONTROLE_trecho_curto_nao_decide(tmp_path, monkeypatch):
    wl, _, _ = _ler(tmp_path, monkeypatch, titulos=("PLANTA DE LAYOUT", "PLANTA DE PONTOS"),
                    guarda=(0.5, 0.5), extra_lumi=False)
    assert wl.get("GUARDA") == pytest.approx(1.0), "abaixo de 1 m não se decide repetição"


# ── o registro ─────────────────────────────────────────────────────────────────
def test_o_log_diz_o_que_saiu_por_repeticao(tmp_path, monkeypatch):
    import main
    _, _, ex = _ler(tmp_path, monkeypatch)
    linha = main._leitura_por_folha_resumo(ex)
    assert "repetidas=[" in linha and "GUARDA 10.0m×3" in linha, linha


def test_a_ia_fica_sabendo_que_a_base_ja_foi_contada_uma_vez(tmp_path, monkeypatch):
    _, _, ex = _ler(tmp_path, monkeypatch)
    txt = ex.to_structured_prompt()
    assert "plantas TEMÁTICAS" in txt and "UMA vez" in txt
