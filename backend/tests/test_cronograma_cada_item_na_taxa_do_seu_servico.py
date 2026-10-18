# -*- coding: utf-8 -*-
"""Cada item entra na conta do cronograma com a composição do SEU serviço —
ou fica fora. Nunca com a de um serviço parecido.

🩸 18/10/2026 — o /exemplo mostrava, com o código SINAPI ao lado:
  - Revestimentos: pintura de parede e de forro na taxa de EMBOÇO (87794);
  - Ar-condicionado: cassete 36.000 BTU na taxa de split hi-wall 12.000 (103247);
  - Pisos: contrapiso e piso vinílico na taxa de PORCELANATO (87263);
  - Divisórias e vidros: porta de VIDRO na taxa de porta de madeira (90822).
No acervo (cronogramas da base), a mesma doença: ponto elétrico, termostato e
condensadora na taxa do split; pintura de demarcação de quadra, laje
impermeabilizada e deck na de emboço; "piso a definir", intertravado e quadra
na de porcelanato. 18 fases mudaram em 12 cronogramas.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

from cronograma import gerar_cronograma  # noqa: E402

REV, PIS, DIV, AR = "Revestimentos", "Pisos e Rodapés", "Divisórias e Vidros", "Ar-Condicionado"


def _it(disc, desc, unit, qty):
    return {"discipline": disc, "description": desc, "unit": unit,
            "quantity": qty, "confidence": "confirmado"}


def _fase(items, label):
    c = gerar_cronograma(items, "2026-11-02", 3)
    return {f["label"]: f for f in c["fases"]}[label]


# ═══════════════════════════════════════════════════════════════════════════
#  O caso do /exemplo
# ═══════════════════════════════════════════════════════════════════════════

def test_PINTURA_entra_na_taxa_de_pintura_nao_na_de_emboco():
    f = _fase([_it(REV, "Pintura látex acrílica em parede (2 demãos)", "m²", 214),
               _it(REV, "Pintura em forro de gesso", "m²", 101.7)], "Revestimentos")
    d = f["origem_detalhe"]
    assert "87794" not in d, d
    assert "214 m² × 0,218 Hh (SINAPI 88489" in d, d
    assert "101,7 m² × 0,303 Hh (SINAPI 88488" in d, d
    assert f["esforco_hh"] == round(214 * 0.218 + 101.7 * 0.303, 1)


def test_CASSETE_36000_entra_na_taxa_do_cassete_36000():
    f = _fase([_it(AR, "Ar-condicionado split cassete 36.000 BTU", "un", 2)], "Ar-condicionado")
    d = f["origem_detalhe"]
    assert "103247" not in d, d
    assert "2 un × 9,505 Hh (SINAPI 103272" in d, d


def test_CONTRAPISO_sai_e_VINILICO_tem_a_dele():
    f = _fase([_it(PIS, "Contrapiso desempenado e=4cm", "m²", 108.3),
               _it(PIS, "Piso porcelanato retificado 60x60", "m²", 86.1),
               _it(PIS, "Piso vinílico em manta (sala de reunião)", "m²", 22.2)], "Pisos")
    d = f["origem_detalhe"]
    assert "108,3" not in d and "216,6" not in d, d
    assert "86,1 m² × 0,688 Hh (SINAPI 87263" in d, d
    assert "22,2 m² × 0,627 Hh (SINAPI 101728" in d, d


def test_PORTA_DE_VIDRO_nao_entra_na_taxa_da_de_madeira():
    f = _fase([_it(DIV, "Porta de madeira 80x210 com batente e ferragens", "un", 6),
               _it(DIV, "Porta de vidro temperado 90x210", "un", 2)], "Divisórias e vidros")
    assert "6 un × 2,876 Hh (SINAPI 90822" in f["origem_detalhe"], f["origem_detalhe"]


# ═══════════════════════════════════════════════════════════════════════════
#  O que o acervo mostrou — item sem composição própria fica FORA
# ═══════════════════════════════════════════════════════════════════════════

def test_o_que_nao_e_o_servico_da_taxa_fica_fora():
    """Cada um destes entrava na conta, na taxa de outro serviço. Sozinhos na
    fase, a fase não tem conta: volta ao prazo de referência ('padrão')."""
    casos = [
        (AR, "Fornecimento e instalação de ponto elétrico para ar-condicionado", "un", 25, "Ar-condicionado"),
        (AR, "Ar-condicionado split — fornecimento e instalação — capacidade a definir", "un", 1, "Ar-condicionado"),
        (AR, "Termostato de ar-condicionado", "un", 1, "Ar-condicionado"),
        (AR, "Split hi-wall 136.000 BTU", "un", 1, "Ar-condicionado"),       # não é 36.000
        (REV, "Pintura de demarcação de quadra poliesportiva", "m²", 600, "Revestimentos"),
        (REV, "Laje impermeabilizada — impermeabilização de laje de cobertura", "m²", 60, "Revestimentos"),
        (REV, "Pintura acrílica — paredes internas e tetos", "m²", 80, "Revestimentos"),  # 2 taxas
        (REV, "Pintura acrílica em fachadas externas, 2 demãos sobre emboço", "m²", 90, "Revestimentos"),
        (PIS, "Piso em Prainha — especificação a definir (pedra, deck, porcelanato externo)", "m²", 20, "Pisos"),
        (PIS, "Piso externo em bloco intertravado de concreto", "m²", 630, "Pisos"),
        (PIS, "Piso vinílico — tipo e espessura a especificar", "m²", 2.2, "Pisos"),
        (DIV, "Box de banheiro — porta de correr em vidro temperado", "un", 5, "Divisórias e vidros"),
    ]
    for disc, desc, un, q, label in casos:
        f = _fase([_it(disc, desc, un, q)], label)
        assert f["origem"] == "padrão", (desc, f["origem_detalhe"])


def test_o_servico_nomeado_decide_nao_a_palavra_solta():
    """"Reboco liso para pintura — paredes" é reboco, não pintura."""
    f = _fase([_it(REV, "Reboco liso para pintura — paredes externas", "m²", 50)], "Revestimentos")
    assert "50 m² × 0,818 Hh (SINAPI 87794" in f["origem_detalhe"], f["origem_detalhe"]


def test_CERAMICA_de_piso_tem_a_dela():
    f = _fase([_it(PIS, "Revestimento cerâmico de piso interno — cerâmica 45×45 cm, PEI 5", "m²", 100)],
              "Pisos")
    assert "100 m² × 0,385 Hh (SINAPI 87251" in f["origem_detalhe"], f["origem_detalhe"]


def test_ar_condicionado_pelo_tipo_e_pelo_porte():
    pares = [("Split hi-wall 12000 BTUs inverter", "103247", "4,667"),
             ("Ar condicionado hi wall 24.000 BTU/h", "103253", "5,267"),
             ("Split piso-teto 48.000 BTU", "103263", "9,15"),
             ("Ar-condicionado de janela 7.500 BTU", "103282", "0,388")]
    for desc, codigo, hh in pares:
        d = _fase([_it(AR, desc, "un", 1)], "Ar-condicionado")["origem_detalhe"]
        assert f"1 un × {hh} Hh (SINAPI {codigo}" in d, (desc, d)
