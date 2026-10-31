# -*- coding: utf-8 -*-
"""O aviso do teto de área diz se o limite é a maior prancha ou a soma delas.

🩸 31/10/2026 (01e6bfad): 3 de 5 pranchas não foram medidas, então o teto voltou à soma
das outras duas (2.577 m²), de propósito. O aviso chamava isso de "maior prancha
medida", e a maior tinha 1.692,9 m².
"""
import os
import textwrap
from types import SimpleNamespace

_AQUI = os.path.dirname(os.path.abspath(__file__))
_INICIO = "        try:\n            _apt = int(getattr(_apply_area_honesty, \"ultimo_apertou_teto\""
_FIM = "                           job_id, severity=\"warning\")\n        except Exception:\n            pass\n"


def _bloco():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        src = f.read().replace("\r\n", "\n")
    i = src.index(_INICIO)
    return src[i:src.index(_FIM, i) + len(_FIM)]


def _rodar(teto=2577.1, soma=2577.1, pranchas=2, apt=2, com_mapa=True):
    logs = []
    pd = SimpleNamespace(warnings=[])
    ns = {"_apply_area_honesty": SimpleNamespace(ultimo_apertou_teto=apt, ultimo_teto_m2=teto),
          "project_data": pd, "_pv_m2": soma, "job_id": "t1", "cad_paths": [],
          "_log_error": lambda st, msg, job=None, severity="error": logs.append((st, msg))}
    if com_mapa:
        ns["_pdfvec_por_prancha"] = {i: {} for i in range(pranchas)}
    exec(textwrap.dedent(_bloco()), ns)
    return pd.warnings, logs


def test_teto_na_soma_diz_soma():
    avisos, logs = _rodar()
    assert "cabe na soma das pranchas medidas (2577 m²)" in avisos[0]
    assert "maior prancha" not in avisos[0]
    assert logs == [("motor:teto-por-prancha",
                     "zerei 2 item(ns) de área: não cabem na soma das pranchas medidas "
                     "(2577.10 m²; soma 2577.10 m²)")]


def test_teto_na_maior_prancha_segue_dizendo_maior_prancha():
    avisos, logs = _rodar(teto=1692.9)
    assert "cabe na maior prancha medida (1693 m²)" in avisos[0]
    assert "soma" not in avisos[0]
    assert "maior prancha medida (1692.90 m²; soma 2577.10 m²)" in logs[0][1]


def test_uma_prancha_so_e_a_maior():
    assert "maior prancha medida" in _rodar(pranchas=1)[0][0]


def test_sem_o_mapa_nao_quebra():
    assert "maior prancha medida" in _rodar(com_mapa=False)[0][0]


def test_borda_da_diferenca():
    assert "soma das pranchas" in _rodar(teto=2577.095)[0][0]
    assert "maior prancha" in _rodar(teto=2577.0)[0][0]


def test_CONTROLE_sem_item_acima_do_teto_nao_avisa():
    assert _rodar(apt=0) == ([], [])
