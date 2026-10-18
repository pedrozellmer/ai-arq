# -*- coding: utf-8 -*-
"""A linha de cada fase na matriz física (% por mês) soma 100%.

🩸 18/10/2026 — no /exemplo, Revestimentos saía 94% + 12% = 106%, Forros
108%, Pisos 107%. A fase ocupa [inicio, fim) — `fim = inicio + dur_dias` —,
mas o overlap contava os dias com `+ 1`: toda fase que cruzava a virada do
mês ganhava um dia em cada mês. Saía assim no .xlsx, no PDF e na tela de
todo cliente, nas duas montagens (gerar_cronograma e a das fases editadas).
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

from cronograma import (gerar_cronograma, gerar_cronograma_de_fases_custom,  # noqa: E402
                        _percentuais_por_mes, _parse_date)


def _it(disc, desc, unit, qty):
    return {"discipline": disc, "description": desc, "unit": unit,
            "quantity": qty, "confidence": "confirmado"}


ITENS = [
    _it("Serviços Preliminares", "Tapume", "m", 40),
    _it("Revestimentos", "Emboço em parede", "m2", 120),
    _it("Pisos", "Porcelanato 60x60", "m2", 118),
    _it("Forros", "Forro de gesso", "m2", 101),
    _it("Pintura", "Pintura látex em parede", "m2", 214),
    _it("Instalações Elétricas", "Ponto de tomada", "un", 30),
    _it("Esquadrias", "Porta de madeira 80x210", "un", 6),
    _it("Marcenaria", "Bancada", "un", 2),
]


def _soma_por_fase(c):
    return {l["label"]: sum(l["percentuais_por_mes"]) for l in c["matriz_pct"]}


def test_toda_fase_soma_100_em_qualquer_prazo_e_data():
    for meses in (1, 2, 3, 5, 8, 12):
        for inicio in ("2026-11-02", "2026-01-15", "2027-02-27", "2026-12-31"):
            c = gerar_cronograma(ITENS, inicio, meses)
            for label, soma in _soma_por_fase(c).items():
                assert soma == 100, (meses, inicio, label, soma, c["matriz_pct"])


def test_fase_que_cruza_o_mes_nao_ganha_dia():
    """Controle positivo: esta fase, pela conta antiga (overlap `+ 1`), dava
    16 + 88 = 104%. 25 dias de [27/11, 22/12): 4 em novembro, 21 em dezembro."""
    fase = {"inicio": "2026-11-27", "fim": "2026-12-22"}
    meses = [{"inicio": "2026-11-01", "fim": "2026-11-30"},
             {"inicio": "2026-12-01", "fim": "2026-12-31"}]
    assert _percentuais_por_mes(fase, meses) == [16, 84]

    # A conta antiga, reproduzida — prova que o caso pega o defeito.
    f_ini, f_fim = _parse_date(fase["inicio"]), _parse_date(fase["fim"])
    antiga = []
    for m in meses:
        a, b = max(f_ini, _parse_date(m["inicio"])), min(f_fim, _parse_date(m["fim"]))
        antiga.append(round(100 * ((b - a).days + 1) / (f_fim - f_ini).days))
    assert sum(antiga) > 100, antiga


def test_fase_que_termina_no_dia_1_nao_aparece_no_mes_seguinte():
    """`fim` é exclusivo: a fase de [02/11, 01/12) acaba em 30/11."""
    fase = {"inicio": "2026-11-02", "fim": "2026-12-01"}
    meses = [{"inicio": "2026-11-01", "fim": "2026-11-30"},
             {"inicio": "2026-12-01", "fim": "2026-12-31"}]
    assert _percentuais_por_mes(fase, meses) == [100, 0]


def test_arredondamento_fecha_em_100():
    """Três meses quase iguais: mês a mês dava 34 + 36 + 31 = 101."""
    fase = {"inicio": "2026-11-02", "fim": "2027-01-29"}  # 88 dias
    meses = [{"inicio": "2026-11-01", "fim": "2026-11-30"},
             {"inicio": "2026-12-01", "fim": "2026-12-31"},
             {"inicio": "2027-01-01", "fim": "2027-01-31"}]
    p = _percentuais_por_mes(fase, meses)
    assert sum(p) == 100, p
    assert all(abs(v - 100 * d / 88) <= 1 for v, d in zip(p, (29, 31, 28))), p


def test_marco_vale_100_no_mes_em_que_cai():
    fase = {"inicio": "2026-12-10", "fim": "2026-12-10"}
    meses = [{"inicio": "2026-11-01", "fim": "2026-11-30"},
             {"inicio": "2026-12-01", "fim": "2026-12-31"}]
    assert _percentuais_por_mes(fase, meses) == [0, 100]


def test_fases_editadas_tambem_somam_100():
    """A 2ª montagem (Gantt editado pelo cliente) tinha a mesma conta copiada."""
    fases = [
        {"label": "Revestimentos", "inicio": "2026-11-20", "fim": "2026-12-12", "ordem": 1},
        {"label": "Pisos", "inicio": "2026-12-15", "fim": "2027-01-20", "ordem": 2},
        {"label": "Entrega", "inicio": "2027-01-25", "fim": "2027-01-25", "ordem": 3,
         "is_milestone": True},
    ]
    c = gerar_cronograma_de_fases_custom(fases, "2026-11-02", 3)
    for label, soma in _soma_por_fase(c).items():
        assert soma == 100, (label, soma, c["matriz_pct"])
