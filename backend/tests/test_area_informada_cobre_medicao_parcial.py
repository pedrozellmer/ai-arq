# -*- coding: utf-8 -*-
"""Área escrita na planta não some por causa de medição nossa que falhou.

🩸 03/11/2026 (job adf132c1): PDF de uma página, a cliente informou 94,53 m² e o
quadro do desenho dava 90,55. A nossa medição achou 19,6 m² de ambientes. Dois
defeitos apagaram as áreas que estavam escritas na planta (Eclusa 10,75 m²,
Circulação 18,53 m²…):
  1. o hint da IA começava com o código da prancha, "(P03 — 02/P03 …)", e foi
     lido como página 3 de um PDF de uma página → "a medição é de outra prancha";
  2. o teto da prancha (1,3 × 19,6) apagava o que passava dele, mesmo cabendo
     com folga na área que a cliente informou.
🔑 AREA_INFORMADA_COBRE_MEDICAO_PARCIAL=1: com a área informada e a medição menor
que a metade dela, a área informada também serve de teto. Segue estimado.
🪤 Nome de arquivo FICTÍCIO: repositório público.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
from analyzer import _pagina_do_ref_sheet, monta_ref_sheet  # noqa: E402

ARQ = "blocos cliente-nn.pdf"
_CHAVE = "AREA_INFORMADA_COBRE_MEDICAO_PARCIAL"


class _Item:
    def __init__(self, desc, qty, ref_sheet, obs="Área lida da tag na planta."):
        self.description = desc
        self.unit = "m²"
        self.quantity = qty
        self.ref_sheet = ref_sheet
        self.observations = obs
        self.origem = ""
        self.confidence = "estimado"


def _pp(m2):
    return {"p0": {"arquivo": ARQ, "rooms_m2": m2, "n_rooms": 9, "walls_m": 29.6,
                   "n_walls": 11, "grupo_maior_m2": m2, "scale": 100,
                   "scale_src": "carimbo", "escala_validada": True, "pagina": 0}}


def _roda(itens, medido=19.6, informada=94.53, fonte="informado"):
    main._apply_area_honesty(itens, total_area=informada, total_area_source=fonte,
                             pdfvec_m2=medido, pdfvec_por_prancha=_pp(medido),
                             job_id="job-de-teste")
    return main._apply_area_honesty.ultimo_informada_cobre


# ── 1. a página do ref_sheet ──────────────────────────────────────────────────
@pytest.mark.parametrize("ref,pagina", [
    ("x.pdf (p3)", 2), ("x.pdf (p3 · Planta Baixa)", 2), ("x.pdf (p12)", 11),
    ("x.pdf (P03 — 02/P03 Planta Baixa Bloco 1)", None), ("x.pdf (p03)", None),
    ("x.pdf (p2 do bloco)", None), ("x.pdf (p0)", None), ("x.pdf (planta p2)", None),
    ("x.pdf", None), ("", None), (None, None)])
def test_so_vale_a_pagina_que_o_motor_escreve(ref, pagina):
    assert _pagina_do_ref_sheet(ref) == pagina
    if ref:
        assert _pagina_do_ref_sheet(ref.lower()) == pagina


def test_o_que_o_motor_escreve_volta_igual():
    for pagina, hint in ((0, ""), (4, "P03 — Planta"), (9, "corte")):
        ref = monta_ref_sheet("a.pdf", pagina, 12, hint)
        assert _pagina_do_ref_sheet(ref) == pagina
    assert _pagina_do_ref_sheet(monta_ref_sheet("a.pdf", 0, 1, "P03 — Planta")) is None


def test_codigo_da_prancha_no_hint_nao_apaga_a_area_escrita(monkeypatch):
    monkeypatch.setenv(_CHAVE, "0")
    eclusa = _Item("Revestimento de piso — Eclusa", 10.75,
                   ARQ + " (P03 — 02/P03 Planta Baixa Bloco 1)")
    _roda([eclusa])
    assert eclusa.quantity == 10.75


# ── 2. a área informada como teto ─────────────────────────────────────────────
def _contrapiso(q=63.59, ref=ARQ):
    return _Item("Contrapiso de regularização do piso — Bloco 1", q, ref)


def test_com_a_chave_em_0_a_linha_some_como_antes_e_e_contada(monkeypatch):
    monkeypatch.setenv(_CHAVE, "0")
    it = _contrapiso()
    assert _roda([it]) == (1, False, 19.6, 94.53)
    assert it.quantity == 0


def test_com_a_chave_em_1_a_area_escrita_fica_estimada_e_diz_por_que(monkeypatch):
    monkeypatch.setenv(_CHAVE, "1")
    it = _contrapiso()
    assert _roda([it]) == (1, True, 19.6, 94.53)
    assert it.quantity == 63.59 and getattr(it.confidence, "value", it.confidence) == "estimado"
    assert "área total que você informou (94,53 m²)" in it.observations
    assert "só 19,60 m²" in it.observations and "geometria" not in it.observations.lower()


def test_o_que_passa_da_area_informada_continua_saindo(monkeypatch):
    monkeypatch.setenv(_CHAVE, "1")
    it = _contrapiso(q=95.0)
    assert _roda([it])[0] == 0 and it.quantity == 0


def test_o_que_cabe_na_nossa_medicao_segue_pela_regua_de_sempre(monkeypatch):
    monkeypatch.setenv(_CHAVE, "1")
    it = _contrapiso(q=20.0)
    assert _roda([it])[0] == 0 and it.quantity == 20.0
    assert "você informou" not in it.observations


@pytest.mark.parametrize("medido", [47.265, 47.27, 60.0])
def test_medicao_de_metade_ou_mais_nao_e_parcial(monkeypatch, medido):
    monkeypatch.setenv(_CHAVE, "1")
    it = _contrapiso(q=90.0)
    assert _roda([it], medido=medido)[0] == 0 and it.quantity == 0


def test_medicao_logo_abaixo_da_metade_ja_e_parcial(monkeypatch):
    monkeypatch.setenv(_CHAVE, "1")
    it = _contrapiso(q=90.0)
    assert _roda([it], medido=47.26)[0] == 1 and it.quantity == 90.0


def test_sem_area_informada_nada_muda(monkeypatch):
    monkeypatch.setenv(_CHAVE, "1")
    it = _contrapiso()
    assert _roda([it], fonte="")[0] == 0 and it.quantity == 0


def test_sem_nenhuma_medicao_a_regua_nao_entra(monkeypatch):
    monkeypatch.setenv(_CHAVE, "1")
    it = _contrapiso()
    main._apply_area_honesty([it], total_area=94.53, total_area_source="informado",
                             pdfvec_m2=0, pdfvec_por_prancha={}, job_id="job-de-teste")
    assert main._apply_area_honesty.ultimo_informada_cobre[0] == 0


def test_o_contador_zera_a_cada_chamada(monkeypatch):
    monkeypatch.setenv(_CHAVE, "0")
    _roda([_contrapiso()])
    assert _roda([_contrapiso(q=20.0)])[0] == 0


def test_chave_avaliavel_etapa_de_diagnostico_e_nasce_desligada():
    assert _CHAVE in main._CHAVES_AVALIAVEIS
    assert "motor:area-informada-cobre" in main._STAGES_DIAGNOSTICO
    assert main._chave_do_job("job-sem-avaliacao", _CHAVE) == "0"


def test_o_projeto_ganha_o_aviso_e_o_registro():
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "main.py"), encoding="utf-8") as f:
        fonte = f.read()
    bloco = fonte[fonte.index('"ultimo_informada_cobre", (0, False, 0.0, 0.0))'):]
    bloco = bloco[:bloco.index("# 🩸 11/09 — QUEM CAIU PELA PRANCHA")]
    assert "if _aic_liga:" in bloco and "Você informou" in bloco
    assert '_log_error("motor:area-informada-cobre"' in bloco
