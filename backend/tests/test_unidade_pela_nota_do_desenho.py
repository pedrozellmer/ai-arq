# -*- coding: utf-8 -*-
"""Sem unidade no cabeçalho e sem cota: a NOTA do desenho ("MEDIDAS EM
CENTÍMETROS"), confirmada pelas cotas explodidas, decide a unidade. E, se
nada decidir, o palpite de mm não sai com "✓ MEDIDO".

🩸 30/09/2026 (job 9a2c5d87, alvenaria de embasamento). DWG sem $INSUNITS,
sem nenhuma cota de verdade (DIMENSION), 4.205 unidades de largura: o mm dava
4,2 m, passava no freio de 2 m, e ficou mm. Era CENTÍMETRO — a nota do próprio
desenho dizia "1 - MEDIDAS EM CENTÍMETROS", o bloco de concreto media 19 × 39
e a folha era um A1 a 1:50 em cm. As 3 linhas com "✓ MEDIDO" saíram 10×
pequenas, com o aviso "escala não conferida" no resumo da mesma planilha.
📏 Acervo local (93 DXF): a regra decidiu em 1 (este, cm, certo) e não errou
nenhum. 13 têm a nota; 6 declaram mm e dizem "medidas em cm" — a nota SOZINHA
erraria os 6 (é a cota explodida que liga a nota ao modelo). Produção, 90
dias: o palpite de mm sem prova caiu em 4 projetos.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
import engine_rules as er  # noqa: E402

LARGURA = 4205.0          # A1 (841 mm) × 1:50 em cm — em mm daria 4,2 m e passaria no freio


def _doc(nota=None, cotas=(), insunits=0, n_linhas=600, altura=10.0):
    """`cotas` = [(comprimento da linha, texto escrito), ...] — cota EXPLODIDA."""
    d = ezdxf.new("R2010")
    d.header["$INSUNITS"] = insunits
    msp = d.modelspace()
    passo = LARGURA / n_linhas
    for i in range(n_linhas):
        msp.add_line((i * passo, 0), ((i + 1) * passo, 1))
    for n in ([nota] if isinstance(nota, str) else (nota or [])):
        msp.add_text(n, dxfattribs={"height": altura, "insert": (100, 2500)})
    x, y = 200.0, 1000.0
    for i, (L, txt) in enumerate(cotas):
        yy = y + (i % 20) * 60
        xx = x + (i // 20) * 400
        msp.add_line((xx, yy), (xx + L, yy))
        nch = len(txt)
        msp.add_text(txt, dxfattribs={"height": altura,
                                      "insert": (xx + L / 2 - 0.45 * altura * nch, yy + 0.3 * altura)})
    d.header["$EXTMIN"] = (0.0, 0.0, 0.0)
    d.header["$EXTMAX"] = (LARGURA, 2970.0, 0.0)
    # 🪤 o `saveas` do ezdxf regrava o cabeçalho com a extensão do MODELO
    msp.dxf.extmin = (0.0, 0.0, 0.0)
    msp.dxf.extmax = (LARGURA, 2970.0, 0.0)
    return d


def _cotas(n, k=1.0, comps=(19, 101, 121, 161, 99, 139, 59, 39)):
    """n cotas em que o texto = comprimento × k."""
    out = []
    for i in range(n):
        L = float(comps[i % len(comps)])
        v = L * k
        out.append((L, ("%g" % v)))
    return out


# ══════════════════════════════════════════════════════════════════════════
#  1. A nota + a cota explodida decidem
# ══════════════════════════════════════════════════════════════════════════
def test_o_caso_nota_em_cm_e_cotas_que_batem_decidem_centimetro():
    d = _doc("1 - MEDIDAS EM CENTÍMETROS", _cotas(30))
    assert dx._detect_unit_factor(d) == 0.01
    assert not getattr(d, "_aiarq_unidade_palpite", None)


def test_a_razao_da_cota_entra_na_conta():
    # nota em mm, texto 10× o comprimento: o modelo está em cm (1 un = 10 mm)
    d = _doc("COTAS EM MM", _cotas(30, k=10.0))
    assert dx._detect_unit_factor(d) == 0.01


def test_nota_em_metro_com_cota_que_bate_decide_metro():
    d = _doc("DIMENSÕES EM METROS", [(float(L), "%g" % L) for L in (2, 3, 4, 5, 6, 7, 8, 9, 12, 15)],
             altura=0.2)
    assert dx._detect_unit_factor(d) == 1.0


def test_a_nota_e_as_cotas_vao_pro_log_do_cabecalho():
    d = _doc("1 - MEDIDAS EM CENTÍMETROS", _cotas(30))
    dx._detect_unit_factor(d)
    nc = dx._diag_unidade_cabecalho(d).get("nota_cota") or {}
    assert nc.get("escolha") == 0.01, nc
    assert nc.get("notas") == {"0.01": 1}, nc


# ══════════════════════════════════════════════════════════════════════════
#  2. Controles — sem as DUAS provas, nada muda
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_nota_sozinha_nao_decide():
    # 6 do acervo declaram mm e dizem "medidas em cm": a nota sozinha erraria
    d = _doc("1 - MEDIDAS EM CENTÍMETROS")
    assert dx._detect_unit_factor(d) == 0.001


def test_CONTROLE_cotas_sem_nota_nao_decidem():
    d = _doc(None, _cotas(30))
    assert dx._detect_unit_factor(d) == 0.001


def test_CONTROLE_poucas_cotas_nao_decidem():
    d = _doc("1 - MEDIDAS EM CENTÍMETROS", _cotas(3))
    assert dx._detect_unit_factor(d) == 0.001


def test_CONTROLE_cotas_sem_acordo_nao_decidem():
    d = _doc("1 - MEDIDAS EM CENTÍMETROS", _cotas(10, k=1.0) + _cotas(10, k=10.0))
    assert dx._detect_unit_factor(d) == 0.001


def test_CONTROLE_duas_notas_de_unidades_diferentes_nao_decidem():
    d = _doc(["MEDIDAS EM CENTÍMETROS", "COTAS EM MM"], _cotas(30))
    assert dx._detect_unit_factor(d) == 0.001


def test_CONTROLE_nivel_em_metro_nao_e_nota_de_unidade():
    d = _doc("2 - COTAS DE NÍVEIS EM METROS", _cotas(30))
    assert dx._notas_de_unidade(d.modelspace()) == {}
    assert dx._detect_unit_factor(d) == 0.001


def test_CONTROLE_unidade_declarada_nem_pergunta_a_nota():
    d = _doc("1 - MEDIDAS EM CENTÍMETROS", _cotas(30), insunits=4)
    assert dx._detect_unit_factor(d) == 0.001
    assert getattr(d, "_aiarq_nota_cota", None) is None
    assert not getattr(d, "_aiarq_unidade_palpite", None)


# ══════════════════════════════════════════════════════════════════════════
#  3. O palpite de mm não sai medido
# ══════════════════════════════════════════════════════════════════════════
def test_o_palpite_fica_marcado_no_documento():
    d = _doc(None)
    assert dx._detect_unit_factor(d) == 0.001
    assert getattr(d, "_aiarq_unidade_palpite", None) is True


def test_a_ressalva_do_palpite():
    r = dx.ressalva_da_unidade_cega(True, "nao-decidiu")
    assert "milímetro" in r and "confira uma medida" in r, r
    assert dx.ressalva_da_unidade_cega(True, None)


@pytest.mark.parametrize("palpite,status", [
    (True, "validada"), (True, "corrigida"), (True, "corrigida_lfac"),
    (True, "provada_por_rotulo"), (True, "corrigida_plausibilidade"),
    (False, "nao-decidiu"), (None, None),
])
def test_CONTROLE_cota_que_prova_ou_sem_palpite_nao_ha_ressalva(palpite, status):
    assert dx.ressalva_da_unidade_cega(palpite, status) == ""


def test_a_ressalva_so_rebaixa_o_que_depende_de_escala():
    md = {"unidade_cega": "x"}
    assert er.extraction_has_quality_caveat(md)
    assert er.caveat_atinge_unidade(md, "m") is True
    assert er.caveat_atinge_unidade(md, "m²") is True
    assert er.caveat_atinge_unidade(md, "un") is False


def test_de_ponta_a_ponta_o_palpite_ganha_a_ressalva(tmp_path):
    p = str(tmp_path / "planta.dxf")
    _doc(None).saveas(p)
    md = dx.extract_dxf(p).metadata
    assert float(md.get("fator_para_metros")) == 0.001, md.get("fator_para_metros")
    assert md.get("unidade_cega"), sorted(md)


def test_de_ponta_a_ponta_a_nota_com_cota_decide_e_nao_ha_ressalva(tmp_path):
    p = str(tmp_path / "planta.dxf")
    _doc("1 - MEDIDAS EM CENTÍMETROS", _cotas(30)).saveas(p)
    md = dx.extract_dxf(p).metadata
    assert float(md.get("fator_para_metros")) == 0.01, md.get("fator_para_metros")
    assert not md.get("unidade_cega"), md.get("unidade_cega")


def test_CONTROLE_de_ponta_a_ponta_unidade_declarada_nao_ganha_ressalva(tmp_path):
    p = str(tmp_path / "planta.dxf")
    _doc(None, insunits=4).saveas(p)
    md = dx.extract_dxf(p).metadata
    assert not md.get("unidade_cega"), md.get("unidade_cega")


def test_o_palpite_chega_ao_cliente_como_alerta_de_escala():
    import main
    arq = main._resumo_escala_arquivo("prancha.dxf", {"unidade_cega": dx.ressalva_da_unidade_cega(True, None),
                                                      "unidade_desenho": "Sem unidade"})
    assert arq["status"] == "alerta", arq
    assert "milímetro" in arq["alerta"], arq
