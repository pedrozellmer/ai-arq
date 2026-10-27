# -*- coding: utf-8 -*-
"""Esquadrias e Elétrica: a taxa só conta o tipo de item que ela representa.

🩸 26/10/2026 — o mesmo defeito consertado em 18/10 nas fases que tinham
ficado de fora (`test_cronograma_coeficiente_so_pro_item_que_representa`):
um coeficiente só por unidade, sem filtro de descrição. Nos 27 cronogramas
da base, a taxa de PORTA DE MADEIRA levava ferragem, janela, porta de vidro
e portão (Esquadrias 1.596 Hh → 696); a de PONTO DE TOMADA levava quadro,
disjuntor e sensor, e a de ELETRODUTO CORRUGADO levava eletrocalha e
eletroduto aparente (Elétrica 2.430 Hh → 1.292).

Frases reescritas a partir do acervo, sem nome de cliente.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

from cronograma_produtividade import REFS_POR_FASE, _ref_do_item, esforco_por_fase  # noqa: E402
from cronograma import _mapear_fase  # noqa: E402


def _entra(fase, cls, desc):
    return _ref_do_item(REFS_POR_FASE[fase][cls], desc) is not None


PORTAS = [
    "Porta de madeira semi-oca — 80×210cm — com batente, marco e ferragens",
    "Porta P6 — Porta em madeira 01 folha de giro, dimensão 0,60×2,40m",
    "Porta P1 — tipo, dimensões e material não especificados nesta prancha",
    "Porta de correr — dimensões a confirmar no quadro de esquadrias",
]
NAO_PORTAS = [
    "Ferragens para porta de madeira — conjunto completo (dobradiças, fechadura)",
    "Porta P4 — 4,70×2,80m, alumínio e vidro, 04 folhas de correr",
    "Porta P01 pivotante em vidro reflexivo — porta pivotante com eixo",
    "Portão P13 — Portão em gradil 01 folha de giro",
    "Janela de correr — 125×120cm — peitoril 60cm",
    "Barra antipânico — para porta de saída de emergência",
    "Porta de garagem — tipo e material não especificados",
    "Esquadrias de alumínio — especificação a definir",
    # cada uma só sai por UMA palavra (pega o mutante que a apagar)
    "Porta pivotante 1,20×2,40 m — eixo de piso a confirmar",
    "Porta-janela de correr 2 folhas — especificação a definir",
]
TOMADAS = [
    "Tomada 2P+T padrão NBR 14136, 127V, H=1,20m — fornecimento e instalação",
    "Interruptores simples e paralelos — distribuição nos ambientes",
    "Ponto de televisão (TV) — fornecimento e instalação de tomada",
    "Fornecimento e instalação de ponto elétrico para liquidificador",
]
NAO_TOMADAS = [
    "Quadro de Distribuição de Luz e Tomadas e Força (QDF) — fornecimento",
    "Disjuntor tetrapolar termomagnético para quadro terminal",
    "Sensor de presença — tipo a confirmar com a legenda",
    "Caixa de embutir retangular PVC 4×2\" — para tomadas e pontos",
    "Condulete de alumínio — corpo reto (tipo C)",
]
ELETRODUTOS = [
    "Eletroduto flexível corrugado Ø 1\" (25 mm) — instalação embutida em laje",
    "Eletroduto para energia embutido no teto ou parede — instalação",
]
NAO_ELETRODUTOS = [
    "Eletroduto para energia, instalação aparente — fornecimento e instalação",
    "Eletroduto de aço galvanizado — Ø 50 mm",
    "Eletroduto PEAD enterrado — diâmetro a confirmar",
    "Eletrocalha perfurada 100×50 mm — fornecimento e instalação",
    "Eletroduto/eletrocalha — traçado elétrico no teto",
    "Eletroduto para energia (fiação/circuitos) — instalação conforme projeto",
    "Eletroduto de PVC, instalação aparente — fornecimento e instalação",   # só o "aparente" tira
]


@pytest.mark.parametrize("desc", PORTAS)
def test_porta_de_madeira_ou_sem_material_entra(desc):
    assert _entra("Esquadrias", "un", desc), desc


@pytest.mark.parametrize("desc", NAO_PORTAS)
def test_CONTROLE_ferragem_janela_vidro_portao_ficam_fora(desc):
    assert not _entra("Esquadrias", "un", desc), desc


@pytest.mark.parametrize("desc", TOMADAS)
def test_ponto_e_tomada_entram(desc):
    assert _entra("Instalações elétricas", "un", desc), desc


@pytest.mark.parametrize("desc", NAO_TOMADAS)
def test_CONTROLE_quadro_disjuntor_caixa_ficam_fora(desc):
    assert not _entra("Instalações elétricas", "un", desc), desc


@pytest.mark.parametrize("desc", ELETRODUTOS)
def test_eletroduto_corrugado_ou_embutido_entra(desc):
    assert _entra("Instalações elétricas", "m", desc), desc


@pytest.mark.parametrize("desc", NAO_ELETRODUTOS)
def test_CONTROLE_aparente_aco_pead_eletrocalha_ficam_fora(desc):
    assert not _entra("Instalações elétricas", "m", desc), desc


def _mapa(d):
    return (_mapear_fase(d) or [None])[0]


def test_a_ferragem_nao_soma_por_cima_da_porta():
    """🩸 A porta e o jogo de ferragens DELA eram contados como 2 portas."""
    itens = [{"discipline": "Esquadrias", "description": PORTAS[0], "unit": "un", "quantity": 6},
             {"discipline": "Esquadrias", "description": NAO_PORTAS[0], "unit": "cj", "quantity": 6}]
    f = esforco_por_fase(itens, _mapa)["Esquadrias"]
    assert f["qtd_total"] == 6, f
    assert "6 un" in f["detalhe"], f["detalhe"]
