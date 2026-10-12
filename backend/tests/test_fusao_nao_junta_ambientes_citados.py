# -*- coding: utf-8 -*-
"""Dois ambientes com a MESMA área não viram uma linha só.

🩸 12/10/2026 — com a seção AMBIENTE ↔ ÁREA ESCRITA a IA entrega uma linha de
piso por ambiente. Dois ambientes de 23,67 m² ("… GRAD" e "… PÓS") fundiam na
passada 2: o nome fica no meio da descrição, fora da cabeça, e o resto é igual.
Um ambiente inteiro saía da planilha — em 2 de 3 avaliações com a seção.

A régua lê o que não depende da redação da descrição: a etiqueta que a
observação cita como fonte ("etiqueta de ambiente 'NOME = 23,67 m²'").
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import BudgetItem, Confidence  # noqa: E402
from main import _consolidate_items  # noqa: E402
from engine_rules import (ambientes_citados, motivo_para_nao_fundir,  # noqa: E402
                          perfil_de_fusao, prova_de_mesmo_item)

_PISOS = "Pisos e Revestimentos"
_REF = "planta.dxf"
_RESTO = "especificação de material, cor e fabricante a definir em memorial descritivo"


def mk(desc, qty, obs, unit="m²", ref=_REF):
    return BudgetItem(item_num="", description=desc, unit=unit, quantity=qty,
                      observations=obs, ref_sheet=ref, confidence=Confidence("estimado"),
                      discipline=_PISOS, origem="vision_pdf")


def _linha(servico, nome, area="23,67"):
    return mk("%s — %s — %s" % (servico, nome, _RESTO), float(area.replace(",", ".")),
              "Fonte: etiqueta de ambiente '%s = %s m²' — folha PLANTA BAIXA." % (nome, area))


# ── o que conta como etiqueta citada ─────────────────────────────────────────
@pytest.mark.parametrize("obs, esperado", [
    ("Fonte: etiqueta de ambiente 'SALA DE ESTUDO = 23,67 m²' — folha PLANTA BAIXA.", {"sala de estudo"}),
    ('Fonte: etiqueta "Depósito 02 = 8,37 m2".', {"deposito 02"}),
    ("etiquetas 'CIRCULAÇÃO = 26,20 m²' + 'CIRCULAÇÃO = 30,50 m²' = 56,70 m²", {"circulacao"}),
    ("etiquetas 'COPA = 14,45 m²' e 'D.M.L = 4,63 m²'", {"copa", "d.m.l"}),
    ("‘Recepção = 1.055,92 m²’", {"recepcao"}),
])
def test_a_etiqueta_citada(obs, esperado):
    assert ambientes_citados(obs) == frozenset(esperado)


@pytest.mark.parametrize("obs", [
    "", None,
    "Fonte: comprimento do layer 'ARQ-ALVENARIA' = 1.581,39 m (medido pelo eixo)",   # metro, não m²
    "Fonte: bloco 'PORTA 80' = 12 un (CONTAGEM DE BLOCOS)",
    "soma das áreas: SALA(16,16) + COPA(8,73) = 24,89 m²",                           # sem aspas: não é citação
    "área 'a definir'; total = 23,67 m²",                                           # o = está fora das aspas
    "rótulo 'FORRO DE GESSO' casado com hachura de 23,67 m²",
    "cota 'VÃO = 0,80 m' na planta",                                                 # metro dentro das aspas
    "texto 'QTD = 12 un' no quadro",
])
def test_CONTROLE_o_que_nao_e_etiqueta_citada(obs):
    assert ambientes_citados(obs) == frozenset()


# ── a régua ──────────────────────────────────────────────────────────────────
def _perfil(it):
    return perfil_de_fusao(it.description, it.unit, it.ref_sheet, it.observations)


def test_ambientes_diferentes_com_a_mesma_area_tem_motivo():
    a, b = _linha("Piso", "SALA DE ESTUDO GRAD"), _linha("Piso", "SALA DE ESTUDO PÓS")
    assert prova_de_mesmo_item(_perfil(a), _perfil(b)), "sem a régua nova as duas fundem: o caso é este"
    motivo = motivo_para_nao_fundir(_perfil(a), _perfil(b))
    assert motivo.startswith("ambientes citados"), motivo


def test_CONTROLE_sem_a_observacao_a_descricao_sozinha_nao_separa():
    """É por isso que a régua lê a observação: pela descrição, as duas são a mesma."""
    a, b = _linha("Piso", "SALA DE ESTUDO GRAD"), _linha("Piso", "SALA DE ESTUDO PÓS")
    assert motivo_para_nao_fundir(perfil_de_fusao(a.description, "m²", _REF),
                                  perfil_de_fusao(b.description, "m²", _REF)) == ""


def test_o_mesmo_ambiente_escrito_de_dois_jeitos_continua_fundindo():
    a = _linha("Piso", "QUARTO", "10,80")
    b = mk("Piso — revestimento de piso (%s) — QUARTO" % _RESTO, 10.80,
           "Fonte: etiqueta de ambiente 'Quarto = 10,80 m²' (folha LAYOUT).")
    assert motivo_para_nao_fundir(_perfil(a), _perfil(b)) == ""


def test_etiqueta_de_um_lado_so_nao_bloqueia():
    a = _linha("Piso", "QUARTO", "10,80")
    b = mk("Piso — QUARTO — %s" % _RESTO, 10.80, "Área conforme planta; especificação a confirmar.")
    assert motivo_para_nao_fundir(_perfil(a), _perfil(b)) == ""


def test_uma_etiqueta_em_comum_nao_bloqueia():
    a = mk("Piso — circulação — %s" % _RESTO, 56.70,
           "etiquetas 'CIRCULAÇÃO = 26,20 m²' + 'HALL = 30,50 m²'")
    b = mk("Piso — circulação e hall — %s" % _RESTO, 56.70, "etiqueta 'HALL = 30,50 m²' e a vizinha")
    assert not motivo_para_nao_fundir(_perfil(a), _perfil(b)).startswith("ambientes citados")


# ── de ponta a ponta, pelo consolidador ──────────────────────────────────────
def test_os_dois_ambientes_de_mesma_area_ficam_na_planilha():
    entrada = [_linha("Piso", "SALA DE ESTUDO GRAD"), _linha("Piso", "SALA DE ESTUDO PÓS"),
               _linha("Forro", "SALA DE ESTUDO GRAD"), _linha("Forro", "SALA DE ESTUDO PÓS"),
               _linha("Piso", "COPA", "14,45")]
    saida = _consolidate_items(entrada)
    pisos = [i for i in saida if i.description.startswith("Piso — SALA")]
    forros = [i for i in saida if i.description.startswith("Forro — SALA")]
    assert len(pisos) == 2 and len(forros) == 2, [(i.description[:40], i.quantity) for i in saida]
    assert round(sum(i.quantity for i in pisos), 2) == 47.34
    assert not any("Fundido" in (i.observations or "") for i in saida)


def test_CONTROLE_a_mesma_linha_lida_duas_vezes_continua_virando_uma():
    """A fusão existe pra isto: o MESMO ambiente, a mesma etiqueta, duas leituras."""
    a = _linha("Piso", "QUARTO", "10,80")
    b = mk("Piso — revestimento de piso (%s) — QUARTO" % _RESTO, 10.80,
           "Fonte: etiqueta de ambiente 'QUARTO = 10,80 m²' (folha LAYOUT).")
    saida = _consolidate_items([a, b])
    quartos = [i for i in saida if "QUARTO" in i.description]
    assert len(quartos) == 1, [(i.description[:50], i.quantity) for i in saida]
    assert quartos[0].quantity == 10.80
