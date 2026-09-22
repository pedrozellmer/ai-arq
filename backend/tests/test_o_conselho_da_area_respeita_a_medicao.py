# -*- coding: utf-8 -*-
"""O aviso "não encontramos a área total" não pede o que a régua vai recusar.

🩸 22/09/2026 — job `ee801b82` (estrutura, 7 PDFs, 0 medidos). O topo do
projeto — e o e-mail, que repete os avisos — dizia:

    "⚠ Não encontramos a área total do projeto [...] Os itens medidos em m²
     saíram sem essa base de conferência [...] Pra resolver: reenvie
     informando a área total no campo do envio"

Duas coisas falsas ali:
  · "os itens MEDIDOS em m²" — nenhum item foi medido;
  · o convite: a régua de superfície aceitava a linha "Fôrma … laje" como
    piso, mas o job tinha 1.116,3 m² de medição vetorial — e com medição a
    área digitada não vira número em linha NENHUMA (a outra trava de
    `_area_informada_alcancaria`, dentro de `_apply_area_honesty`). O aviso de
    projeto só olhava a primeira. A cliente reenviaria com a área e nada
    mudaria — é a doença de 08/09 (conselho que a régua recusa) outra vez.

📏 Alcance (90 dias, sem avaliação): 60 jobs de 45 clientes receberam o
convite; em 19 deles (16 clientes) havia medição vetorial > 0 — o log
`pdfvec:por-prancha` só existe desde meados de setembro, então é piso.

🧪 Executa o TRECHO REAL do main.py (do cálculo da medição até o `print`
do aviso), com as peças públicas de `engine_rules` que são a régua.
"""
import io
import os
import sys
import textwrap

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from engine_rules import FLOOR_M2_UNITS, is_floor_surface_para_criar  # noqa: E402

_INICIO = "            try:\n                _pv_alc = float(_pdfvec_area_m2 or 0)\n"
_FIM = 'f"pdfvec={_pv_alc:.1f} m²)")'
_CONVITE = "reenvie informando a área total"


class _It(object):
    def __init__(self, desc, unit):
        self.description, self.unit = desc, unit


class _PD(object):
    def __init__(self):
        self.warnings = []


def _roda(itens, pdfvec_m2=None):
    """`pdfvec_m2=None` = job sem PDF (o nome nem existe, como no motor)."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    assert src.count(_INICIO) == 1, "a âncora de início do trecho mudou"
    assert src.count(_FIM) == 1, "a âncora de fim do trecho mudou"
    i = src.index(_INICIO)
    j = src.index(_FIM, i) + len(_FIM)
    trecho = textwrap.dedent(src[i:j])
    pd = _PD()
    ns = {"all_items": itens, "project_data": pd, "job_id": "ee801b82",
          "_FLOOR_M2_UNITS": FLOOR_M2_UNITS,
          "_is_floor_surface_criar": is_floor_surface_para_criar}
    if pdfvec_m2 is not None:
        ns["_pdfvec_area_m2"] = pdfvec_m2
    exec(compile(trecho, "main_area_ausente_slice", "exec"), ns)
    assert len(pd.warnings) == 1, "o aviso da área ausente tem que sair sempre"
    return pd.warnings[0]


def _itens_do_caso():
    return [_It("Concreto estrutural C30 — estrutura E1", "m³"),
            _It("Fôrma — laje de cobertura circular", "m²"),
            _It("Fôrma de madeira — parede da estrutura E2", "m²"),
            _It("Armadura CA-50 — resumo da prancha", "kg")]


def test_o_caso_ee801b82_nao_convida_a_informar_a_area():
    """🩸 1.116,3 m² de medição vetorial: a área digitada não entraria."""
    txt = _roda(_itens_do_caso(), pdfvec_m2=1116.3)
    assert _CONVITE not in txt, (
        "convidou a reenviar com a área num job em que a medição vetorial a "
        "recusa em todas as linhas:\n" + txt)
    assert "a área digitada no envio não vira número em nenhuma linha" in txt, txt


def test_o_aviso_nao_chama_de_MEDIDO_o_que_nao_foi():
    txt = _roda(_itens_do_caso(), pdfvec_m2=1116.3)
    assert "itens medidos em m²" not in txt, txt
    assert "Não encontramos a área total do projeto" in txt


# ── 🧪 CONTROLES POSITIVOS ────────────────────────────────────────────────
def test_CONTROLE_sem_medicao_vetorial_o_convite_volta():
    """Mesmos itens, PDF sem medição: a área informada preenche a laje."""
    assert _CONVITE in _roda(_itens_do_caso(), pdfvec_m2=0.0)


def test_CONTROLE_job_sem_PDF_tambem_recebe_o_convite():
    """O nome `_pdfvec_area_m2` nem existe num job só de CAD."""
    assert _CONVITE in _roda(_itens_do_caso())


def test_CONTROLE_sem_piso_a_explicacao_antiga_continua():
    txt = _roda([_It("Alvenaria — paredes internas", "m²")], pdfvec_m2=500.0)
    assert "não há item de piso/forro/laje" in txt, txt
    assert _CONVITE not in txt
