# -*- coding: utf-8 -*-
"""Código de legenda colado (LMN02, LMN05A, AL004) é item DIFERENTE.

🩸 24/09/2026, job b6df4f3d (DTZ): 23 luminárias distintas — LMN02 a LMN24,
1 un cada — viraram "Luminária tipo Lum_2_PL — 23 variantes consolidadas",
23 un. O reconhecedor de código só aceitava prefixos fixos (PM, LM, P, V…) e
"LMN" (3 letras) passava despercebido: a trava de atributo achou que era o
mesmo item. Regra dura nº4: tipo específico nunca some.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import _consolidate_items  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402
from engine_rules import atributos_distintivos, pode_fundir  # noqa: E402


@pytest.mark.parametrize("a, b", [
    ("Luminária tipo LMN02 — especificação a confirmar com quadro",
     "Luminária tipo LMN03 — especificação a confirmar com quadro"),
    ("Luminária LMN05 — plafon", "Luminária LMN05A — plafon"),
    ("Caixilho AL004 — por definir", "Caixilho AL007 — por definir"),
])
def test_codigos_colados_diferentes_nao_fundem(a, b):
    assert not pode_fundir(a, b)


def test_o_mesmo_codigo_colado_continua_fundivel():
    assert pode_fundir("Luminária LMN12 — plafon", "Luminária tipo LMN12 embutida")


def test_o_codigo_antigo_continua_reconhecido_primeiro():
    """PM-01/PV-01 continuam pela regra antiga (com hífen)."""
    assert atributos_distintivos("Porta de madeira PM-01")["codigo"] == "pm-01"


def _it(desc, qty=1.0, unit="un", sheet="1026.ARR.700.FORRO.00.dxf"):
    return BudgetItem(item_num="1", description=desc, unit=unit, quantity=qty,
                           observations="", ref_sheet=sheet,
                           confidence=Confidence("estimado"), discipline="Iluminação")


def test_o_consolidador_nao_junta_as_23_luminarias():
    itens = [_it("Luminária tipo LMN%02d — especificação a confirmar com quadro" % n)
             for n in range(2, 25)]
    fora = _consolidate_items(list(itens))
    assert len(fora) == 23, [i.description for i in fora][:5]
    assert not any("variantes consolidadas" in (i.description or "") for i in fora)


def test_CONTROLE_luminaria_IGUAL_repetida_ainda_funde():
    """A mesma LMN12 lida 3 vezes (3 pranchas) continua uma linha só — se
    isto quebrar, a trava nova virou "nunca funde"."""
    itens = [_it("Luminária tipo LMN12 — especificação a confirmar com quadro",
                 sheet="p%d.dxf" % k) for k in range(3)]
    fora = _consolidate_items(list(itens))
    assert len(fora) < 3, [i.description for i in fora]
