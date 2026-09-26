# -*- coding: utf-8 -*-
"""Comprimento recuperado não responde linha de volume, e não sobe a medido.

🩸 26/09/2026 — job 32a27efc (muro de arrimo, 7 DXF). A IA deixou
"Concreto armado — Rampa (novo) — volume" em 0 m³ e escreveu por quê: os
90,85 m do layer 'Rampa' são o contorno, e o volume precisa de largura e
espessura que a prancha não isola. Aí:

  1. a recuperação de comprimento copiou os 90,85, trocou m³ por m e marcou
     ESTIMADO ("a soma do layer pode incluir traço que não é deste item");
  2. a chave do selo conferiu o número contra o layer — bate, foi copiado de
     lá — e promoveu a "✓ MEDIDO".

O cliente recebeu 90,85 m de concreto, com selo branco, e uma observação que
dizia ESTIMADO e MEDIDO ao mesmo tempo.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine_rules import (  # noqa: E402
    MARCA_QUANTIDADE_RECUPERADA,
    corrigir_comprimento_medido,
    selo_com_prova_da_geometria,
)

_DESC = "Concreto armado — Rampa (novo) — volume"
_OBS = ("Layer 'Rampa' apresenta comprimento total de linhas = 90.85 m. Trata-se "
        "provavelmente do contorno/geometria da rampa em planta ou corte. Para "
        "calcular volume: comprimento da rampa × largura × espessura da laje de "
        "rampa — nenhum desses valores está isolado de forma confiável nesta prancha.")
_INDICE = {"comprimento": [("Rampa", 90.85)], "area": [], "contagem": []}


# ══════════════════════════════════════════════════════════════════════════
#  1) A recuperação não responde volume com comprimento
# ══════════════════════════════════════════════════════════════════════════
def test_o_caso_linha_de_volume_zerada_fica_como_a_IA_deixou():
    for u in ("m³", "m3", "M³"):
        assert corrigir_comprimento_medido(_DESC, u, 0, _OBS) == {}, u


def test_CONTROLE_a_mesma_observacao_em_m2_ainda_recupera_no_CAD():
    """Só VOLUME saiu. Área em CAD fica como estava (22/09: 'lá o layer
    existe') — e prova que a observação do caso dispara a regra."""
    fix = corrigir_comprimento_medido(_DESC, "m²", 0, _OBS)
    assert fix.get("quantity") == 90.85 and fix.get("unit") == "m", fix


def test_CONTROLE_linha_de_comprimento_zerada_ainda_recupera():
    fix = corrigir_comprimento_medido("Meio-fio de concreto — rampa", "m", 0, _OBS)
    assert fix.get("quantity") == 90.85 and fix.get("confidence") == "estimado", fix


# ══════════════════════════════════════════════════════════════════════════
#  2) A chave do selo não promove a cópia
# ══════════════════════════════════════════════════════════════════════════
def _linha(obs, unidade="m", qtd=90.85):
    return {"description": _DESC, "unit": unidade, "quantity": qtd,
            "confidence": "estimado", "origem": "dxf_geom", "observations": obs}


def test_o_numero_recuperado_nao_sobe_a_medido():
    """Pela esteira de verdade: o aviso que a recuperação ESCREVE, na frente da
    observação, como o main faz — se alguém mudar a redação do aviso sem mudar
    a marca, este teste pega."""
    fix = corrigir_comprimento_medido("Meio-fio de concreto — rampa", "m", 0, _OBS)
    obs = fix["motivo"] + " | " + _OBS
    assert MARCA_QUANTIDADE_RECUPERADA in obs
    assert selo_com_prova_da_geometria([_linha(obs)], _INDICE) == []


def test_CONTROLE_sem_o_aviso_a_mesma_linha_sobe():
    """A linha que a IA preencheu citando o layer continua subindo — a trava
    é só da cópia, não da prova."""
    prom = selo_com_prova_da_geometria([_linha(_OBS)], _INDICE)
    assert [p["indice"] for p in prom] == [0], prom
