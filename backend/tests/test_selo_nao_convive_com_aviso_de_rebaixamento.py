# -*- coding: utf-8 -*-
"""Selo de medido não convive com o aviso de uma régua que REBAIXOU a linha.

🩸 27/09/2026 (estudo de leitura, item 3): 12 linhas ✓ desde 23/09 traziam na
observação "⚠ SOMA, não leitura direta", "⚠ FONTE = CARIMBO DA PRANCHA",
"⚠ REBAIXADO: item contável", "⚠ A leitura encontrou MENOS parede",
"Procedência: extração com ressalva" — a chave do selo só respeitava a marca
do texto lido, e o selo que a própria IA dá não passava por régua nenhuma.
"""
import os
import sys
import textwrap

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import engine_rules as er  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402

_REAIS = [
    "⚠ SOMA, não leitura direta — a quantidade veio de somar parcelas, então não sai",
    "⚠ FONTE = CARIMBO DA PRANCHA, não o desenho — confirme se este serviço existe",
    "x | ⚠ REBAIXADO: item contável (un) veio com unidade ml — a quantidade pode",
    "⚠ A leitura encontrou MENOS parede do que o mínimo possível pra área deste projeto",
    "x | Procedência: extração com ressalva (estéril/unidade/xref) — quantidade não confirmada",
    "⚠ ESTIMADO — este número foi LIDO de um texto da prancha, não medido da geometria",
]


def test_cada_aviso_real_e_reconhecido():
    for t in _REAIS:
        assert er.marca_de_rebaixamento(t), t
    assert not er.marca_de_rebaixamento("Fonte: comprimento do layer PAT-ALV1 = 545 m.")


def test_quem_escreve_usa_a_constante():
    """A marca que a régua escreve e a que a trava procura são a MESMA string."""
    src = open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8").read()
    for nome in ("_MARCA_CARIMBO + \", não o desenho", "_MARCA_MENOS_PAREDE + \" do que o mínimo",
                 "_MARCA_UNIDADE_DE_CONTAGEM + \" (un) veio com unidade",
                 "| {_MARCA_EXTRACAO_COM_RESSALVA} "):
        assert nome in src, nome
    er_src = open(os.path.join(os.path.dirname(_AQUI), "engine_rules.py"), encoding="utf-8").read()
    assert "aviso = (MARCA_SOMA + \" — a quantidade veio de somar" in er_src


def test_a_chave_nao_promove_linha_com_aviso():
    obs = "⚠ SOMA, não leitura direta — parcelas. Fonte: comprimento do layer 'PAT-LED' = 6,72 m"
    idx = {"comprimento": [("PAT-LED", 6.72)], "area": [], "contagem": []}
    it = {"confidence": "estimado", "origem": "dxf_geom", "quantity": 6.72, "unit": "ml",
          "observations": obs, "description": "Perfil de LED"}
    assert er.selo_com_prova_da_geometria([it], idx) == []
    it["observations"] = "Fonte: comprimento do layer 'PAT-LED' = 6,72 m"
    assert len(er.selo_com_prova_da_geometria([it], idx)) == 1, "CONTROLE: sem aviso promove"


def _fatia_da_trava():
    src = open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8").read()
    a = src.index("            from engine_rules import (marca_de_rebaixamento as _marca_reb,")
    ini = src.rindex("        try:\n", 0, a)
    fim = src.index("        # 🚨 AQUI é o fim da fila de quem rebaixa selo", a)
    return textwrap.dedent(src[ini:fim])


def test_a_trava_final_rebaixa_o_selo_da_ia_com_aviso():
    com = BudgetItem(item_num="1", description="Selo corta-fogo", unit="m²", quantity=0.44,
                     observations="Fonte: layer X. ⚠ FONTE = CARIMBO DA PRANCHA, não o desenho",
                     ref_sheet="a.dxf", confidence=Confidence("confirmado"), origem="dxf_geom")
    sem = BudgetItem(item_num="2", description="Forro", unit="m²", quantity=230.71,
                     observations="Fonte: área do layer PAT-FORRO = 230,71", ref_sheet="a.dxf",
                     confidence=Confidence("confirmado"), origem="dxf_geom")
    logs = []
    ns = {"all_items": [com, sem], "job_id": "t",
          "_log_error": lambda *a, **k: logs.append(" ".join(str(x) for x in a))}
    exec(compile(_fatia_da_trava(), "trava", "exec"), ns)
    assert com.confidence == Confidence("estimado")
    assert sem.confidence == Confidence("confirmado"), "CONTROLE: sem aviso fica"
    assert not [l for l in logs if "FALHOU" in l], logs
