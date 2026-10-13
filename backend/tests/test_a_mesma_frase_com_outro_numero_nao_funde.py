# -*- coding: utf-8 -*-
"""A mesma frase com um NÚMERO diferente são dois itens — a fusão não junta.

🩸 13/10/2026: uma prancha de locação de fundação. "Bloco de coroamento de
estaca — altura H.B. = 1,50 m" (3 un) absorveu "… altura H.B. = 1,30 m" (3 un):
três blocos sumiram da planilha. A régua da altura lê "h=1,50" e "altura 1,50 m",
não "altura H.B. = 1,50 m" — dependia da redação. O que não depende: a frase é a
mesma e só o número muda.

No banco (90 dias de cliente): 182 fusões com "absorveu", em 25 projetos; com a
frase igual e só o número diferente, uma — a do caso.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import engine_rules as er  # noqa: E402
import main  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402

_HB = "Bloco de coroamento de estaca — altura H.B. = %s m"
_SO_O_NUMERO = "só o número difere"


def _it(desc, qtd, k=0, unit="un", disc="Estrutura", prancha="locacao.dxf"):
    return BudgetItem(item_num=str(k + 1), description=desc, unit=unit, quantity=qtd,
                      ref_sheet=prancha, confidence=Confidence("estimado"), discipline=disc)


def _blocos(out):
    return sorted((i.description, i.quantity) for i in out if "coroamento" in i.description)


def test_o_caso_as_duas_alturas_com_a_mesma_quantidade_ficam_separadas():
    out = main._consolidate_items([_it(_HB % "1,50", 3, 0), _it(_HB % "1,30", 3, 1)])
    assert _blocos(out) == [(_HB % "1,30", 3), (_HB % "1,50", 3)], _blocos(out)


def test_as_cinco_alturas_da_prancha_ficam_as_cinco():
    alturas = (("1,00", 31), ("1,20", 25), ("0,80", 7), ("1,50", 3), ("1,30", 3))
    out = main._consolidate_items([_it(_HB % h, q, k) for k, (h, q) in enumerate(alturas)])
    assert _blocos(out) == sorted((_HB % h, q) for h, q in alturas), _blocos(out)
    assert sum(q for _d, q in _blocos(out)) == 69


def test_o_motivo_diz_os_dois_numeros():
    m = er.motivo_para_nao_fundir(_HB % "1,50", _HB % "1,30")
    assert m.startswith(_SO_O_NUMERO) and "1.5" in m and "1.3" in m, m


@pytest.mark.parametrize("a,b", [
    (_HB % "1,50", "Bloco de coroamento de estaca — altura H.B. = 1,30m"),      # sem espaço antes da unidade
    ("Laje maciça e = 12 cm", "Laje maciça e = 15 cm"),
    ("Sapata isolada S1 tipo — cota de assentamento -1,20", "Sapata isolada S1 tipo — cota de assentamento -1,80"),
])
def test_a_mesma_frase_com_outro_numero_nao_funde(a, b):
    assert er.motivo_para_nao_fundir(a, b), (a, b)
    out = main._consolidate_items([_it(a, 4, 0), _it(b, 4, 1)])
    assert len([i for i in out if i.quantity == 4]) == 2, [(i.description, i.quantity) for i in out]


def test_CONTROLE_o_mesmo_numero_escrito_de_outro_jeito_continua_juntando():
    # "1,5" e "1,50" são a mesma altura: a mesma linha lida duas vezes
    assert not er.motivo_para_nao_fundir(_HB % "1,5", _HB % "1,50")
    out = main._consolidate_items([_it(_HB % "1,5", 3, 0), _it(_HB % "1,50", 3, 1)])
    assert len(_blocos(out)) == 1 and _blocos(out)[0][1] == 3, _blocos(out)


def test_CONTROLE_a_linha_repetida_continua_juntando():
    out = main._consolidate_items([_it(_HB % "1,50", 3, 0), _it(_HB % "1,50", 3, 1)])
    assert _blocos(out) == [(_HB % "1,50", 3)], _blocos(out)


def test_CONTROLE_numero_de_referencia_nao_distingue():
    # "nota 4" × "nota 5": o número é da referência, não do item
    a = "Concreto magro sob os blocos — conforme nota 4"
    b = "Concreto magro sob os blocos — conforme nota 5"
    assert er.frase_e_numeros(a) == er.frase_e_numeros(b)
    assert not er.motivo_para_nao_fundir(a, b).startswith(_SO_O_NUMERO)


def test_CONTROLE_frase_diferente_nao_e_desta_regua():
    # outra frase: quem decide são as réguas de sempre
    m = er.motivo_para_nao_fundir("Forro de gesso liso — Varanda (37,98 m²)", "Forro — Varanda — a confirmar")
    assert not m.startswith(_SO_O_NUMERO), m


def test_CONTROLE_a_regua_que_sabe_o_que_o_numero_e_continua_dando_o_motivo():
    assert er.motivo_para_nao_fundir("Tomada 2P+T 10A a 0,30 m do piso",
                                     "Tomada 2P+T 10A a 1,10 m do piso").startswith("altura")
    assert not er.pode_fundir("Armadura CA-50 Ø8 mm — vigas", "Armadura CA-50 Ø16 mm — vigas")


def test_a_frase_e_os_numeros():
    f, n = er.frase_e_numeros("Bloco de coroamento — altura H.B. = 1,50 m (3×)")
    assert n == ("1.5", "3") and "#" in f and " " not in f, (f, n)
    assert er.frase_e_numeros("Bloco — H.B. = 01,50m")[1] == ("1.5",)
    assert er.frase_e_numeros("Pilar 30x90")[1] == ("30", "90")
    assert er.frase_e_numeros("")[0] == "" and er.frase_e_numeros(None) == ("", ())


def test_perfil_antigo_sem_a_chave_nao_quebra():
    # perfis montados por fora (sem `frase_e_numeros`) seguem valendo
    a = er.perfil_de_fusao(_HB % "1,50")
    b = er.perfil_de_fusao(_HB % "1,30")
    a.pop("frase_e_numeros")
    assert er.motivo_para_nao_fundir(a, b) == ""
