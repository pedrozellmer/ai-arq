# -*- coding: utf-8 -*-
"""Piso de banheiro com a área ESCRITA na etiqueta da planta não sai zerado.

🩸 05/11/2026 — casa em PDF de uma página. Os pisos vieram das etiquetas
("SUÍTE A=14,20m²", "GARAGEM A=21,40m²") e oito ficaram com o número pelo ramo
"cabe na geometria". "BWC SUÍTE A=3,37m²" e "BWC SOCIAL A=3,64m²" saíram ZERADOS
só porque "bwc" contém "wc", palavra de `FLOOR_AREA_BLOCK_KW`. 📏 60 dias: ~35
linhas de piso/forro de banheiro com "A=" na linha, em 14 projetos.
🛑 PISO_DE_COMODO_DA_ETIQUETA nasce em 0: só anota (`ultimo_comodo_da_etiqueta`).

Roda a `_apply_area_honesty` REAL pela fatia de `test_area_medida_do_pdf_nao_e_apagada`.
"""
import io
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)
sys.path.insert(0, os.path.dirname(_AQUI))

import engine_rules as er  # noqa: E402
import test_area_medida_do_pdf_nao_e_apagada as _base  # noqa: E402

_CHAVE = "PISO_DE_COMODO_DA_ETIQUETA"
_BWC = "Piso em porcelanato — BWC Suíte (A=3,37 m²) — especificação a definir"
_OBS = "Área extraída da etiqueta da planta baixa: 'BWC SUÍTE A=3,37m² Piso: Porcelanato'."


@pytest.mark.parametrize("desc,obs,q", [
    (_BWC, _OBS, 3.37),
    ("Piso porcelanato — WC 02 — tipo a confirmar", "Área lida da planta: 'A=3,77m²'.", 3.77),
    ("Piso cerâmico — Banheiro Social", "Etiqueta: BANHO A = 3,48 m2", 3.48),
    ("Forro de gesso liso — banheiro da UH padrão", "'BANHO A=3,48m²'", 3.48),
    ("Revestimento de piso — Sanitário PNE", "Sanitário PNE A=3,79 m².", 3.79),
])
def test_piso_de_comodo_com_o_numero_da_etiqueta(desc, obs, q):
    assert er.piso_de_comodo_com_etiqueta(desc, obs, q)


@pytest.mark.parametrize("desc,obs,q", [
    # o número não é o da etiqueta (soma de vários banheiros)
    ("Piso cerâmico antiderrapante — Banheiro", "1 banheiro por unidade (A=3,48 m²)", 22.72),
    # sem etiqueta nenhuma
    ("Piso cerâmico — Banheiro Social", "Estimativa: ~3 m² de piso.", 3.0),
    # outra palavra que barra além da de cômodo
    ("Revestimento de parede do banheiro até o forro", "BWC A=3,37m²", 3.37),
    ("Rodapé do piso do WC", "WC A=3,37m²", 3.37),
    ("Ralo linear no piso do banheiro", "BWC A=3,37m²", 3.37),
    # sem palavra de piso/forro
    ("Bancada do banheiro em granito", "BWC A=3,37m²", 3.37),
    # já é superfície comum: o ramo de sempre cuida
    ("Piso em porcelanato — Suíte (A=14,20 m²)", "SUÍTE A=14,20m²", 14.2),
    # número zero ou ilegível
    (_BWC, _OBS, 0),
    (_BWC, _OBS, "x"),
    # "A=" colado em palavra não é etiqueta ("ÁREA=3,37" não, "PA=3,37" não)
    ("Piso do banheiro", "PA=3,37m²", 3.37),
])
def test_CONTROLE_o_que_nao_e_piso_de_comodo_da_etiqueta(desc, obs, q):
    assert not er.piso_de_comodo_com_etiqueta(desc, obs, q)


def test_as_palavras_de_comodo_sao_as_que_ja_barravam():
    assert set(er.FLOOR_COMODO_KW) <= set(er.FLOOR_AREA_BLOCK_KW)


def _roda(monkeypatch, ligada, desc=_BWC, obs=_OBS, q=3.37):
    if ligada:
        monkeypatch.setenv(_CHAVE, "1")
    else:
        monkeypatch.delenv(_CHAVE, raising=False)
    piso = _base._Item(desc, "m²", q, obs)
    suite = _base._Item("Piso em porcelanato — Suíte (A=14,20 m²)", "m²", 14.2,
                        "Área extraída da etiqueta: 'SUÍTE A=14,20m²'.")
    h = _base._fatia()["_apply_area_honesty"]
    h([piso, suite], total_area=0, total_area_source="", pe_direito=0, pdfvec_m2=90.0)
    return piso, suite, h


def test_desligada_o_banheiro_zera_como_antes_e_a_lista_anota(monkeypatch):
    piso, suite, h = _roda(monkeypatch, ligada=False)
    assert _base._valor(piso) == 0, "a chave em 0 mudou número"
    assert _base._valor(suite) == 14.2
    assert h.ultimo_comodo_da_etiqueta == ([(3.37, _BWC[:60])], False)


def test_ligada_o_banheiro_fica_estimado_como_a_suite(monkeypatch):
    piso, suite, h = _roda(monkeypatch, ligada=True)
    assert _base._valor(piso) == 3.37
    assert str(getattr(piso.confidence, "value", piso.confidence)) == "estimado"
    assert "Área NÃO medida" not in piso.observations
    assert h.ultimo_comodo_da_etiqueta == ([(3.37, _BWC[:60])], True)


def test_ligada_numero_que_nao_cabe_na_prancha_zera(monkeypatch):
    desc = "Piso em porcelanato — BWC (A=300,00 m²)"
    piso, _, h = _roda(monkeypatch, ligada=True, desc=desc, obs="BWC A=300,00m²", q=300.0)
    assert _base._valor(piso) == 0
    assert h.ultimo_comodo_da_etiqueta == ([], True)


def test_ligada_numero_que_nao_e_a_etiqueta_zera(monkeypatch):
    piso, _, h = _roda(monkeypatch, ligada=True, q=7.0)
    assert _base._valor(piso) == 0
    assert h.ultimo_comodo_da_etiqueta == ([], True)


def test_a_chave_e_avaliavel_e_a_etapa_e_diagnostico():
    src = io.open(os.path.join(_base._BACKEND, "main.py"), encoding="utf-8").read()
    assert '_chave_do_job(job_id, "%s")' % _CHAVE in src
    assert '"%s"' % _CHAVE in src[src.index("_CHAVES_AVALIAVEIS = frozenset"):][:5000]
    _lista = src[:src.index('"motor:passo7-ambiguo"')].replace("\r\n", "\n")
    assert '    "motor:piso-de-comodo-da-etiqueta",\n' in _lista
    assert '_log_error("motor:piso-de-comodo-da-etiqueta"' in src
