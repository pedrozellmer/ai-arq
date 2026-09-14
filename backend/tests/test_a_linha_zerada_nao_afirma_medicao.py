# -*- coding: utf-8 -*-
"""Linha zerada não pode AFIRMAR que foi medida na geometria.

🩸 14/09/2026 — no job de um cliente do dia (loja de varejo, 3 PDFs), uma linha
de drywall com quantidade ZERO trazia, no mesmo texto:

    "... Medido do desenho com escala 1:50 lida do carimbo da prancha — confira
    a escala do seu PDF. | Fundido de 2 entradas com mesma qty 20.0 m² |
    Área NÃO medida (lida de PDF por IA, não da geometria) — preencha a
    metragem ou envie o DXF pra medir."

📏 Medido na base (30 dias, 8.941 linhas): 424 linhas em 29 jobs se contradizem
assim, 349 delas zeradas. Por forma: 352 são a frase que a IA escreve porque o
NOSSO prompt manda escrever a procedência, 66 são a nossa frase antiga e 6 são
outras formas.

🔑 É o espelho do achado 7 (05/08), que gerou `_limpa_aviso_nao_medida`: lá a
linha COM número trazia a instrução que destrói o número; aqui a linha SEM
número afirma que foi medida. O comentário daquele conserto vale igual —
"mensagem contraditória queima a confiança do cliente mais rápido que erro de
número".

🚫 Nada aqui muda número: zerar continua certo (regra dura nº1). Muda o texto.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

_IA = ("Código PA09 identificado na legenda. Área estimada. Medido do desenho "
       "com escala 1:50 lida do carimbo da prancha — confira a escala do seu PDF.")
_NOSSA_ANTIGA = ("Medido da GEOMETRIA do PDF, com escala lida do carimbo e NÃO "
                 "confirmada por cota — confira a escala do seu PDF antes de orçar.")
_NOSSA_NOVA = ("Medido da GEOMETRIA do PDF (o carimbo DECLARA a escala). Prancha "
               "planta cliente-nn.pdf: 120.00 m², escala 1:50 do carimbo. "
               "Confira antes de orçar.")


def _afirma(txt):
    t = (txt or "").lower()
    return "medido do desenho com escala" in t or "medido da geometria do pdf" in t


# ── a limpeza, chamada de verdade ────────────────────────────────────────
def test_a_frase_que_a_IA_escreve_sai_e_o_resto_do_texto_FICA():
    """A afirmação mora no meio do parágrafo da IA: sai a SENTENÇA, não o
    parágrafo — senão some 'Código PA09 identificado na legenda'."""
    saida = main._limpa_afirmacao_de_medida(
        "⚠ A leitura encontrou MENOS parede do que o mínimo. " + _IA
        + " | Fundido de 2 entradas com mesma qty 20.0 m²")
    assert not _afirma(saida), saida
    assert "Código PA09 identificado na legenda" in saida
    assert "Área estimada" in saida
    assert "MENOS parede" in saida
    assert "Fundido de 2 entradas" in saida


def test_a_NOSSA_frase_sai_inteira_com_prancha_escala_e_conselho():
    """A nossa é um segmento próprio, e a prancha/escala/'confira antes de
    orçar' só fazem sentido junto dela — órfãos, viram enfeite confuso."""
    for nossa in (_NOSSA_ANTIGA, _NOSSA_NOVA):
        saida = main._limpa_afirmacao_de_medida(
            "Piso cerâmico. | " + nossa + " | Fundido de 2 entradas")
        assert not _afirma(saida), saida
        assert "Piso cerâmico." in saida and "Fundido de 2 entradas" in saida
        assert "Prancha" not in saida and "Confira antes de orçar" not in saida
        assert "confira a escala do seu PDF" not in saida


def test_CONTROLE_texto_que_so_NEGA_passa_intacto():
    """Prova que a limpeza sabe deixar quieto: o aviso honesto não é tocado."""
    nega = ("Área NÃO medida (lida de PDF por IA, não da geometria) — preencha "
            "a metragem ou envie o DXF pra medir.")
    assert main._limpa_afirmacao_de_medida(nega) == nega


def test_CONTROLE_texto_sem_afirmacao_nenhuma_passa_intacto():
    t = "Código PA09 identificado na legenda. Área estimada. | Fundido de 2 entradas"
    assert main._limpa_afirmacao_de_medida(t) == t


def test_CONTROLE_vazio_e_None_nao_explodem():
    assert main._limpa_afirmacao_de_medida("") == ""
    assert main._limpa_afirmacao_de_medida(None) == ""


# ── o motor CHAMA a limpeza quando zera (senão nasce morta) ──────────────
class _It:
    def __init__(self, desc, unit, qty, obs, ref_sheet=""):
        self.description, self.unit, self.quantity = desc, unit, qty
        self.observations, self.ref_sheet = obs, ref_sheet
        self.confidence = "estimado"
        self.category = "Vedações"


def test_ZERANDO_de_verdade_o_texto_para_de_afirmar_medicao():
    """🪤 Guarda de ponto de chamada, rodando `_apply_area_honesty`: a linha
    entra com a frase da IA e um número que a medição não sustenta, sai zerada —
    e o texto não pode continuar dizendo que foi medida."""
    it = _It("Drywall tipo PA09 — placa estruturada", "m²", 5000.0,
             "Código PA09 identificado na legenda. " + _IA)
    main._apply_area_honesty([it], total_area=0, total_area_source="",
                             pdfvec_m2=278.8)
    assert float(it.quantity or 0) == 0, "o cenário não zerou — o guarda não prova nada"
    assert not _afirma(it.observations), (
        "a linha foi zerada e o texto continua afirmando medição: %s" % it.observations)
    assert "não medida" in (it.observations or "").lower(), (
        "sumiu também o aviso honesto: %s" % it.observations)
    assert "Código PA09 identificado na legenda" in it.observations, (
        "a limpeza levou junto o que a IA sabia do item: %s" % it.observations)
