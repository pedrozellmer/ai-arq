# -*- coding: utf-8 -*-
"""Parede FINA desenhada em duas linhas a 2–5 cm mede UMA vez.

🩸 06/10/2026 — reforma de escritório: as paredes novas ("a construir") e o
layer da reforma eram divisórias de 4 cm, ~100 % em duas linhas. Abaixo de 5 cm
o motor juntava as duas como "a mesma face" (o reboco da parede composta, H73)
e, sem par, somava as DUAS: "alvenaria 229,70 m × 2,80 = 643,16 m²" contra
~360 pelo eixo.

🔑 A face de DUAS linhas a 2–5 cm, sem paralela a 5–40 cm no trecho, é a
parede fina inteira. Com 3+ linhas (a composta) ou vizinho a 5–40 cm (a face de
outra parede), fica como era; abaixo de 2 cm é linha repetida.

📏 Acervo (342 DXF, 406 layers de parede): 318 iguais; dos que caem ≥ 20 %,
olhados no desenho — platibanda numa planta de cobertura, peitoril de janela,
alvenaria desenhada fina, boxes de sanitário — sempre UM elemento em 2 linhas.

🪤 Nomes FICTÍCIOS (repositório público, regra nº6).
"""
import os
import sys
from types import SimpleNamespace as NS

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402


def _ler(tmp_path, desenha, insunits=6):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = insunits
    desenha(doc.modelspace())
    p = str(tmp_path / "parede.dxf")
    doc.saveas(p)
    return dx.extract_dxf(p)


def _linhas(msp, layer, x0, x1, ys, k=1.0):
    for y in ys:
        msp.add_line((x0 * k, y * k), (x1 * k, y * k), dxfattribs={"layer": layer})


def _m(ex, layer):
    return ex.get_walls_by_layer()[layer]


# ══════════════════════════════════════════════════════════════════════════
#  O caso
# ══════════════════════════════════════════════════════════════════════════
def test_o_caso_divisoria_de_4_cm_mede_uma_vez(tmp_path):
    ex = _ler(tmp_path, lambda m: _linhas(m, "DIVISORIA", 0, 10, (0, 0.04)))
    assert _m(ex, "DIVISORIA") == pytest.approx(10.0, abs=0.05)


def test_varias_divisorias_paralelas_na_mesma_faixa(tmp_path):
    """🪤 06/10 (sintético da medição): o TRECHO do motor junta todas as paralelas
    que se sobrepõem na projeção, mesmo longe. "Uma face só no trecho" nunca
    acontecia; vale "a dupla sem vizinho a 5–40 cm". 10 divisórias a cada 3 m."""
    def d(m):
        for i in range(10):
            _linhas(m, "DIVISORIA", 0, 5, (3.0 * i, 3.0 * i + 0.04))
    ex = _ler(tmp_path, d)
    assert _m(ex, "DIVISORIA") == pytest.approx(50.0, abs=0.1)


@pytest.mark.parametrize("sep,esperado", [(0.035, 10.0), (0.01, 20.0)])
def test_em_milimetro_tambem(tmp_path, sep, esperado):
    """Em mm, a linha repetida a 1 cm (10 unidades) continua sendo duas: o piso de
    2 cm é em METRO, não em unidade do desenho."""
    ex = _ler(tmp_path, lambda m: _linhas(m, "PAREDE", 0, 10, (0, sep), k=1000.0), insunits=4)
    assert _m(ex, "PAREDE") == pytest.approx(esperado, abs=0.05)


@pytest.mark.parametrize("sep,esperado", [(0.02, 10.0), (0.05, 10.0), (0.019, 20.0)])
def test_a_faixa_e_de_2_a_5_cm(tmp_path, sep, esperado):
    ex = _ler(tmp_path, lambda m: _linhas(m, "PAREDE", 0, 10, (0, sep)))
    assert _m(ex, "PAREDE") == pytest.approx(esperado, abs=0.05)


def test_divisoria_fina_e_parede_de_duas_faces_no_mesmo_layer(tmp_path):
    """A parede de 15 cm pareia como sempre; a divisória de 4 cm, longe dela, vira
    eixo também: 10 + 6."""
    def d(m):
        _linhas(m, "PAREDE", 0, 10, (0, 0.15))
        _linhas(m, "PAREDE", 0, 6, (5, 5.04))
    ex = _ler(tmp_path, d)
    assert _m(ex, "PAREDE") == pytest.approx(16.0, abs=0.05)


def test_a_divisoria_fina_tira_o_layer_da_zona_cinza(tmp_path):
    """Layer só de divisória fina: antes 0 % em par (as duplas eram "a mesma
    face") e somava tudo; agora 100 %."""
    ex = _ler(tmp_path, lambda m: [_linhas(m, "PAREDE", 0, 5, (3.0 * i, 3.0 * i + 0.04)) for i in range(4)])
    assert _m(ex, "PAREDE") == pytest.approx(20.0, abs=0.1)
    assert "PAREDE" not in (ex.metadata.get("parede_zona_cinza") or {})


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLES — o que fica como era
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_a_composta_de_4_linhas_fica(tmp_path):
    """Face, reboco a 2,5 cm, face a 14 cm, reboco: as duplas têm vizinho a
    5–40 cm (a outra face) — é o par de sempre, pelo eixo."""
    ex = _ler(tmp_path, lambda m: _linhas(m, "A-WALL", 0, 10, (0, 0.025, 0.14, 0.165)))
    assert _m(ex, "A-WALL") == pytest.approx(10.0, abs=0.05)


def test_CONTROLE_junta_de_dilatacao_fica(tmp_path):
    """Duas paredes de 15 cm com junta de 2 cm: as duas linhas da junta têm
    vizinho a 15 cm dos dois lados — são faces de paredes DIFERENTES."""
    ex = _ler(tmp_path, lambda m: _linhas(m, "PAREDE", 0, 10, (0, 0.15, 0.17, 0.32)))
    assert _m(ex, "PAREDE") == pytest.approx(20.0, abs=0.05)


def test_CONTROLE_linha_repetida_fica(tmp_path):
    """A mesma linha desenhada duas vezes (0,5 cm): não é parede fina."""
    ex = _ler(tmp_path, lambda m: _linhas(m, "PAREDE", 0, 10, (0, 0.005)))
    assert _m(ex, "PAREDE") == pytest.approx(20.0, abs=0.05)


def test_CONTROLE_tres_linhas_finas_ficam(tmp_path):
    """3 linhas TODAS a até 5 cm uma da outra (0 / 2 / 4 cm), sem par: não dá pra
    dizer qual é a parede. (0 / 3 / 6 cm não serve de controle: a 1ª e a 3ª já
    formam um par de 6 cm.)"""
    ex = _ler(tmp_path, lambda m: _linhas(m, "PAREDE", 0, 10, (0, 0.02, 0.04)))
    assert _m(ex, "PAREDE") == pytest.approx(30.0, abs=0.05)


def test_CONTROLE_duto_nao_tem_parede_fina():
    """A régua é da PAREDE (junta_face_fina). Duas bordas de duto a 3 cm seguem
    como a régua do duto manda: abaixo do mínimo, não pareiam."""
    walls = [NS(layer="DUTO AR", start=(0.0, y), end=(10.0, y), length=10.0, pontos=(), curvo=False)
             for y in (0, 0.03)]
    novos, _, _ = dx._corrigir_duto_linha_dupla(walls, 1.0)
    assert sum(w.length for w in novos) == pytest.approx(20.0, abs=0.05)


def test_CONTROLE_layer_que_nao_e_parede_fica(tmp_path):
    ex = _ler(tmp_path, lambda m: _linhas(m, "MOBILIARIO", 0, 10, (0, 0.04)))
    assert _m(ex, "MOBILIARIO") == pytest.approx(20.0, abs=0.05)


def test_parede_grossa_com_reboco_a_marca_do_E12_segue(tmp_path):
    """Parede de 50 cm com reboco de 3 cm dos dois lados (0 / 3 / 53 / 56 cm): cada
    face é uma dupla fina sem vizinho a 40 cm, e vira eixo — a soma cai de 4 pra
    2 linhas (o eixo seria 1). 🔒 A dupla NÃO entra no registro de par do E12:
    a parede grossa continua marcada, e a IA continua avisada."""
    def d(m):
        for i in range(3):
            _linhas(m, "A-WALL", 0, 10, (4.0 * i, 4.0 * i + 0.03, 4.0 * i + 0.53, 4.0 * i + 0.56))
    ex = _ler(tmp_path, d)
    assert _m(ex, "A-WALL") == pytest.approx(60.0, abs=0.1)
    assert "A-WALL" in (ex.metadata.get("parede_espessa_pelas_faces") or {}), ex.metadata.get(
        "parede_espessa_pelas_faces")
