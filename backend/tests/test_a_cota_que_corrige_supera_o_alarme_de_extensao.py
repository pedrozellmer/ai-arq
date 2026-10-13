# -*- coding: utf-8 -*-
"""A cota que CORRIGE a unidade supera o alarme de extensão, como a que valida.

🩸 13/10/2026: um DWG em metros com cabeçalho de milímetros. 200 cotas provaram
o fator (7 com número digitado) e a escala saiu no aviso do cliente como
"conferida pelo próprio desenho" — e nenhum m/m² do arquivo saiu medido. Refeita
com o fator provado, a heurística de extensão achou um traço de 1.101 m e voltou
a avisar "unidade suspeita": a ressalva de escala, contra a prova. Com a régua
"validada" a cota já superava essa heurística; com a "corrigida" (a MESMA prova)
não superava.

Não muda: a correção por DIMLFAC e por plausibilidade (inferência, não prova), a
prancha sem cota, e o texto do aviso — que não vai ao prompt.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import ezdxf  # noqa: E402
import pytest  # noqa: E402

import dwg_extractor as dx  # noqa: E402
import engine_rules as er  # noqa: E402

CHAVE = "COTA_QUE_CORRIGE_SUPERA_EXTENSAO"
RASTRO = "extensao_superada_pela_cota_que_corrigiu"
# 4 digitadas + 2 automáticas, em METROS
COTAS = ((3.5, "3.50"), (1.2, "1.20"), (4.15, "4.15"), (6.2, "6.20"), (2.8, "<>"), (1.9, "<>"))
AUTOMATICAS = tuple((c, "<>") for c in (3.5, 1.2, 4.15, 6.2, 2.8, 1.9, 5.0, 7.3))


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    monkeypatch.delenv(CHAVE, raising=False)


def _extrai(tmp_path, insunits, cotas, traco, lfac=1.0):
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = insunits
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (12, 0), (12, 8), (0, 8)], close=True, dxfattribs={"layer": "PAREDE"})
    for k, (comp, txt) in enumerate(cotas):
        d = msp.add_linear_dim(base=(0, -3 * k - 2), p1=(0, -3 * k - 3), p2=(comp, -3 * k - 3), text=txt,
                               override={"dimlfac": lfac})
        d.render()
    if traco:
        msp.add_line((0, 50), (traco, 50), dxfattribs={"layer": "0"})
    p = str(tmp_path / "x.dxf")
    doc.saveas(p)
    return dx.extract_dxf(p)


def test_o_caso_a_cota_corrigiu_e_o_traco_longo_nao_vira_ressalva(tmp_path):
    md = _extrai(tmp_path, 4, COTAS, 1101).metadata
    assert md["regua_cotas_status"] == "corrigida" and md["fator_para_metros"] == "1.0", md
    assert "alerta_unidade" not in md and "unidade_suspeita" not in md, md
    assert not er.extraction_has_quality_caveat(md)
    assert not er.caveat_atinge_unidade(md, "m") and not er.caveat_atinge_unidade(md, "m²")


def test_o_aviso_superado_fica_de_rastro(tmp_path):
    md = _extrai(tmp_path, 4, COTAS, 1101).metadata
    assert "maior elemento mede 1101m" in md[RASTRO], md


def test_o_rastro_nao_vai_ao_prompt(tmp_path):
    # o texto do aviso manda "tratar quantidades como estimado": é o que foi superado
    prompt = _extrai(tmp_path, 4, COTAS, 1101).to_structured_prompt()
    assert RASTRO not in prompt and "tratar quantidades como estimado" not in prompt
    assert "unidade_corrigida_por_cotas" in prompt        # a prova continua dita


def test_com_a_chave_em_zero_e_como_era(tmp_path, monkeypatch):
    monkeypatch.setenv(CHAVE, "0")
    md = _extrai(tmp_path, 4, COTAS, 1101).metadata
    assert md["regua_cotas_status"] == "corrigida"
    assert "maior elemento mede 1101m" in md["alerta_unidade"] and md.get("unidade_suspeita"), md
    assert RASTRO not in md
    assert er.caveat_atinge_unidade(md, "m")


def test_CONTROLE_sem_traco_longo_nao_ha_rastro(tmp_path):
    md = _extrai(tmp_path, 4, COTAS, 0).metadata
    assert md["regua_cotas_status"] == "corrigida"
    assert RASTRO not in md and "alerta_unidade" not in md, md


def test_CONTROLE_correcao_por_dimlfac_nao_supera(tmp_path):
    # DIMLFAC é inferência: o alarme de extensão continua valendo
    md = _extrai(tmp_path, 4, AUTOMATICAS, 1101, lfac=100.0).metadata
    assert md["regua_cotas_status"] == "corrigida_lfac", md
    assert "maior elemento mede 1101m" in md["alerta_unidade"] and RASTRO not in md, md
    assert er.caveat_atinge_unidade(md, "m")


def test_CONTROLE_sem_cota_o_alarme_continua(tmp_path):
    # cabeçalho em mm, nenhum DIMENSION, um traço de 600 m: nada provou a unidade
    md = _extrai(tmp_path, 4, (), 600000).metadata
    assert md["regua_cotas_status"] not in ("corrigida", "validada"), md
    assert "maior elemento" in (md.get("alerta_unidade") or ""), md
    assert RASTRO not in md


@pytest.mark.parametrize("chave", ["1", "0"])
def test_CONTROLE_a_validada_segue_como_era(tmp_path, monkeypatch, chave):
    monkeypatch.setenv(CHAVE, chave)
    md = _extrai(tmp_path, 6, COTAS, 1101).metadata
    assert md["regua_cotas_status"] == "validada", md
    assert "alerta_unidade" not in md and RASTRO not in md, md
    assert "maior elemento mede 1101m" in md["heuristica_extensao_superada_por_cotas"]


def test_a_chave_e_lida_no_extrator_e_e_avaliavel():
    import main
    assert CHAVE in main._CHAVES_AVALIAVEIS
    with open(dx.__file__, encoding="utf-8") as f:
        assert 'os.environ.get("%s"' % CHAVE in f.read()
