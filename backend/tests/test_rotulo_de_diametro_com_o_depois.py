# -*- coding: utf-8 -*-
"""O diâmetro rotulado com o ø DEPOIS do número ("75mmø") também vale.

🩸 02/10/2026 — H34b. O Revit em português rotula o tubo como "75mmø",
"110mmø", "160mmø". O H34 só lia o ø ANTES ("ø75", "%%c100"), então
`_diametros_rotulados` dava [] e a face dupla não era decidida: uma piscina
saiu "tubulação PVC 1.157,34 + 1.543,75 ml ✓" com o P-PIPE desenhado pelas
duas paredes (91 e 98 % do layer em par).
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import dwg_extractor as dx  # noqa: E402
from test_tubo_em_face_dupla import T, _feixe  # noqa: E402


def test_le_o_o_depois_do_numero():
    ds = dx._diametros_rotulados([T("75mmø"), T("110mmø"), T("160 mm Ø"), T("32MM%%c")])
    assert ds == [32, 75, 110, 160], ds


def test_o_caso_real_p_pipe_rotulado_so_com_o_depois():
    fd = dx.tubos_em_face_dupla(_feixe(d=0.075), [T("75mmø"), T("110mmø"), T("150mm")])
    assert "P-PIPE" in fd and fd["P-PIPE"]["fracao"] >= 0.8, fd
    assert 75 in fd["P-PIPE"]["diametros_mm"], fd


def test_o_formato_antigo_continua():
    assert dx._diametros_rotulados([T("ø150"), T("PVC-ø75"), T("%%c100")]) == [75, 100, 150]


# ── o que NÃO vale como rótulo de diâmetro ─────────────────────────────────────
def test_CONTROLE_mm_sem_o_e_nota_ou_cota():
    """'150mm' sozinho é nota/cota (112 DXF do acervo têm 'NNmm' em nota)."""
    assert dx._diametros_rotulados([T("150mm"), T("espessura 20 mm"), T("ESP. 100MM")]) == []


def test_CONTROLE_numero_quebrado_nao_vira_diametro():
    """'1.75mmø' / '2,50mmø' não são ø75 / ø50."""
    assert dx._diametros_rotulados([T("1.75mmø"), T("2,50mmø")]) == []


def test_CONTROLE_sem_rotulo_nao_decide():
    """Sem diâmetro escrito no desenho, o H34 continua sem decidir."""
    assert dx.tubos_em_face_dupla(_feixe(d=0.075), [T("150mm")]) == {}
