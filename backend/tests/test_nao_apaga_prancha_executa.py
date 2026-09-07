# -*- coding: utf-8 -*-
"""O consolidador RODA e nenhuma prancha e apagada (caso cliente-14).

Guarda por EXECUCAO: a versao de fonte (no arquivo irmao) so procurava as
palavras `losers` e `winner = max(group` no corpo da passada 6.
"""
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from models import BudgetItem, Confidence  # noqa: E402
from main import _consolidate_items  # noqa: E402

# A descricao real do caso cliente-14 (job d5e073cf).
ALVENARIA = "Alvenaria de veda\u00e7\u00e3o \u2014 levantamento de parede"


def _it(desc, unit, qty, prancha, conf="confirmado", disc="Alvenaria", obs=""):
    return BudgetItem(item_num="", description=desc, unit=unit, quantity=qty,
                      observations=obs, ref_sheet=prancha,
                      confidence=Confidence(conf), discipline=disc)


def _tres_pavimentos():
    """MESMA grandeza, três pranchas — o grupo que chega até o fim da passada."""
    return [_it(ALVENARIA, "m²", 819.06, "DEMOLIR-CONSTRUIR"),
            _it(ALVENARIA, "m²", 810.36, "LAYOUT"),
            _it(ALVENARIA, "m²", 73.05, "PAV-SUPERIOR")]


def test_a_passada_6_NAO_elege_vencedor_nem_descarta():
    """🚨 O invariante central: nenhuma leitura de prancha é apagada."""
    entrada = _tres_pavimentos()
    saida = _consolidate_items(entrada)
    assert len(saida) == 3, (
        "%d de 3 linhas sobreviveram — a passada voltou a eleger vencedor e "
        "apagar pavimento" % len(saida))
    qtds = sorted(round(float(i.quantity), 2) for i in saida)
    assert qtds == [73.05, 810.36, 819.06], (
        "as quantidades mudaram: %s — alguma medição foi perdida ou somada" % qtds)
    assert {i.ref_sheet for i in saida} == {"DEMOLIR-CONSTRUIR", "LAYOUT",
                                            "PAV-SUPERIOR"}, (
        "uma prancha inteira sumiu da planilha")
