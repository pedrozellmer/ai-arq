# -*- coding: utf-8 -*-
"""Metro ou m² de layer DESLIGADO ou CONGELADO no desenho não sai medido.

🩸 19/10/2026 — paisagismo de 15/10: "Área total de pavimentação 2.791,14 m² ✓"
era o contorno de um layer de piso que o projetista desligou: não aparece em
nenhuma prancha impressa, e o extrator mede o modelo inteiro. A IA marcou
"confirmado" sozinha. SÓ REBAIXA e avisa; o índice da chave do selo também deixa
o layer de fora, pra não promover de volta.
"""
import os
import sys

import ezdxf

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
import engine_rules as er  # noqa: E402
import main  # noqa: E402

OBS = ("Fonte: contorno fechado do layer 'PISO PAG EXT' = 1234.56 m². Representa a área total "
       "do pavimento. Usar como referência de controle de área total.")


def _rebaixa(obs, unit, desligados, conf="confirmado"):
    return er.selo_apos_layer_desligado(conf, obs, unit, main._layers_da_obs(obs), desligados)


def test_o_caso_area_de_layer_desligado_volta_a_estimado():
    conf, obs, rb = _rebaixa(OBS, "m²", {"PISO PAG EXT"})
    assert rb is True and conf == "estimado", (conf, obs)
    assert obs.startswith(er.MARCA_LAYER_DESLIGADO) and "'PISO PAG EXT'" in obs and obs.endswith(OBS)


def test_o_metro_tambem():
    obs = "Comprimento do layer 'MURO-RASCUNHO' = 120,00 m (conferido)."
    conf, _o, rb = _rebaixa(obs, "m", {"MURO-RASCUNHO"})
    assert rb is True and conf == "estimado"


def test_CONTROLE_layer_ligado_fica():
    assert _rebaixa(OBS, "m²", {"OUTRO LAYER"}) == ("confirmado", OBS, False)
    assert _rebaixa(OBS, "m²", set()) == ("confirmado", OBS, False)


def test_CONTROLE_contagem_e_estimado_nao_sao_tocados():
    assert _rebaixa(OBS, "un", {"PISO PAG EXT"}) == ("confirmado", OBS, False)
    assert _rebaixa(OBS, "m²", {"PISO PAG EXT"}, conf="estimado") == ("estimado", OBS, False)


def test_a_chave_do_selo_respeita_a_marca_e_o_layer_nao_prova():
    assert er.MARCA_LAYER_DESLIGADO in er.MARCAS_DE_REBAIXAMENTO
    md = {"layers_desligados_medidos": {"PISO PAG EXT": {"m": 0.0, "m2": 1234.56}}}
    assert "PISO PAG EXT" in er.layers_que_nao_provam(md)


def _arquivo(tmp_path, desligar=True):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for nome in ("PISO", "PISO-OFF"):
        doc.layers.add(nome)
    if desligar:
        doc.layers.get("PISO-OFF").off()
    for ly, x0 in (("PISO", 0.0), ("PISO-OFF", 30.0)):
        h = msp.add_hatch(dxfattribs={"layer": ly})
        h.paths.add_polyline_path([(x0, 0), (x0 + 10, 0), (x0 + 10, 10), (x0, 10)], is_closed=True)
        msp.add_line((x0, 12), (x0 + 10, 12), dxfattribs={"layer": ly})
    p = str(tmp_path / ("desligado.dxf" if desligar else "ligado.dxf"))
    doc.saveas(p)
    return p


def test_o_extrator_diz_quais_layers_desligados_tem_medida(tmp_path):
    ex = dx.extract_dxf(_arquivo(tmp_path))
    reg = ex.metadata.get("layers_desligados_medidos") or {}
    assert set(reg) == {"PISO-OFF"}, reg
    assert reg["PISO-OFF"]["m2"] > 0 and reg["PISO-OFF"]["m"] > 0, reg
    assert "layers_desligados_medidos" not in ex.to_structured_prompt()


def test_CONTROLE_sem_layer_desligado_nao_ha_registro(tmp_path):
    ex = dx.extract_dxf(_arquivo(tmp_path, desligar=False))
    assert "layers_desligados_medidos" not in ex.metadata


def _item():
    return {"item_num": "1", "description": "Área total de pavimentação externa",
            "unit": "m²", "quantity": 1234.56, "confidence": "confirmado", "observations": OBS}


def test_o_laco_de_producao_rebaixa_a_linha():
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    itens, _esc, _logs = _laco_de_itens_de_producao(
        [_item()], areas={"PISO PAG EXT": 1234.56}, compr={}, extra={"_desl_ly": {"PISO PAG EXT"}})
    assert itens[0].confidence.value == "estimado" and er.MARCA_LAYER_DESLIGADO in itens[0].observations


def test_CONTROLE_o_laco_com_o_layer_ligado_segue():
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    itens, _esc, _logs = _laco_de_itens_de_producao(
        [_item()], areas={"PISO PAG EXT": 1234.56}, compr={}, extra={"_desl_ly": set()})
    assert er.MARCA_LAYER_DESLIGADO not in (itens[0].observations or "")


def test_o_indice_da_chave_do_selo_tira_a_area_do_layer_desligado():
    with open(main.__file__, encoding="utf-8") as f:
        src = f.read()
    assert "if _lyr in _secoes_ig or str(_lyr).strip().upper() in _desl_ig:" in src
