# -*- coding: utf-8 -*-
"""✓ de contagem cuja IDENTIDADE é palpite pelo nome do bloco não sai medido.

🩸 05/10/2026 — num job de fundação, o MESMO bloco saiu "estaca raiz" ✓ numa
prancha e "marco topográfico" ✓ na outra; a observação da própria IA dizia
"Nome do bloco sugere marco de controle topográfico" / "Bloco interpretado como
locação de estaca". A regra irmã (`item_e_bloco_sem_identidade`) só lê a
DESCRIÇÃO; aqui a descrição tem nome de peça e a dúvida está na OBSERVAÇÃO.
Medido no banco (jobs de cliente): 27 ✓ assim em 13 jobs; 22 palpites, 5 custos.

Regra: linha de CONTAGEM por bloco ("bloco 'X'" na observação), ✓, cuja
observação diz que o que a peça é saiu do nome do bloco → estimado, com o aviso
na linha. Só rebaixa. Nomes de bloco sintéticos.
"""
import pytest

import engine_rules as er
from engine_rules import identidade_e_palpite_pelo_nome as _palpite


class _ItemFalso:
    def __init__(self, description, unit, confidence, observations=""):
        self.description = description
        self.unit = unit
        self.confidence = confidence
        self.observations = observations


def _selo(it):
    return str(getattr(getattr(it, "confidence", None), "value", getattr(it, "confidence", "")) or "")


# as formas medidas na produção (os nomes de bloco trocados por sintéticos)
_PALPITES = [
    "Fonte: 2 INSERTs do bloco 'XYZ1' identificados no DXF (contagem determinística). "
    "Nome do bloco sugere marco de controle topográfico. Confirmar com projeto topográfico.",
    "Fonte: 9 INSERTs do bloco 'XYZ1' (CONTAGEM DE BLOCOS). Bloco interpretado como locação "
    "de estaca tipo 1. Confirmar com a planta de locação.",
    "Fonte: 10 INSERTs do bloco 'AB'. Provavelmente indicador de pressão (manômetro) — confirmar com legenda.",
    "Fonte: 6 INSERTs do bloco 'QRS'. Bloco possivelmente representa máquina de lavar roupa.",
    "Fonte: 1 INSERT do bloco 'xpto' na contagem de blocos do DXF. Nome sugere 'pergolado'. Confirmar.",
    "Fonte: 2 INSERTs do bloco 'EST_X-6'. Nome do bloco sugere 'estação' — pode ser estação de bombagem.",
    "Fonte: CONTAGEM DE BLOCOS — bloco 'QQ': 19 inserções. Provavelmente indica aberturas na laje.",
]

_NAO_SAO_PALPITE_DE_IDENTIDADE = [
    # medida, não identidade
    "Fonte: 4 INSERTs do bloco 'P70'. Nome do bloco indica 70 cm de folga — confirmar se é 0,70 ou 0,80.",
    # unidade, não identidade
    "Fonte: bloco 'VIGA_X' com atributos COMP=678. Comprimento interpretado como 678 cm = 6,78 m.",
    "Fonte: 3 INSERTs do bloco 'XX'. Bloco interpretado como 3 unidades (um por pavimento).",
    # lugar, não identidade
    "Fonte: bloco 'Coifa Industrial' — 1 INSERT na contagem de blocos. Localizada provavelmente na cozinha.",
    "Fonte: 5 INSERTs do bloco 'VASO'. Ambientes: BH SUÍTE, BANHEIRO e possivelmente lavabo.",
    # contagem sem palpite
    "Fonte: 12 INSERTs do bloco 'TOMADA' (CONTAGEM DE BLOCOS).",
    # palpite sem citar o bloco da contagem
    "Nome do bloco sugere marco topográfico.",
]


@pytest.mark.parametrize("obs", _PALPITES)
def test_o_palpite_pelo_nome_e_apontado(obs):
    assert _palpite(obs, "un")


@pytest.mark.parametrize("obs", _NAO_SAO_PALPITE_DE_IDENTIDADE)
def test_CONTROLE_o_que_nao_e_palpite_de_identidade(obs):
    assert not _palpite(obs, "un")


@pytest.mark.parametrize("unit", ["m", "ml", "m²", "kg", "vb"])
def test_CONTROLE_so_contagem(unit):
    assert not _palpite(_PALPITES[0], unit)


def test_o_motor_rebaixa_o_check_com_palpite():
    import main
    from models import Confidence
    it = _ItemFalso("Marco topográfico de locação — tipo XYZ1", "un", Confidence.CONFIRMADO, _PALPITES[0])
    n = main.rebaixar_itens_sem_identidade([it])
    assert n == 1 and _selo(it) == "estimado"
    assert it.observations.startswith(er.MARCA_IDENTIDADE_PALPITE)
    assert er.MARCA_IDENTIDADE_PALPITE in er.MARCAS_DE_REBAIXAMENTO


def test_o_mesmo_bloco_com_duas_identidades_as_duas_caem():
    """O caso: o mesmo bloco, estaca ✓ numa prancha e marco ✓ na outra."""
    import main
    from models import Confidence
    estaca = _ItemFalso("Locação e execução de estacas raiz Ø20 cm", "un", Confidence.CONFIRMADO, _PALPITES[1])
    marco = _ItemFalso("Marco topográfico de locação — tipo XYZ1", "un", Confidence.CONFIRMADO, _PALPITES[0])
    assert main.rebaixar_itens_sem_identidade([estaca, marco]) == 2
    assert _selo(estaca) == _selo(marco) == "estimado"


def test_CONTROLE_o_check_sem_palpite_fica():
    import main
    from models import Confidence
    obs = "Fonte: 12 INSERTs do bloco 'TOMADA' (CONTAGEM DE BLOCOS). Legenda: TOMADA 2P+T 10A."
    it = _ItemFalso("Tomada 2P+T 10A", "un", Confidence.CONFIRMADO, obs)
    assert main.rebaixar_itens_sem_identidade([it]) == 0
    assert _selo(it) == "confirmado" and it.observations == obs


def test_CONTROLE_estimado_com_palpite_fica_como_veio():
    """Só o ✓ cai: a linha que já era estimada não ganha aviso nem conta."""
    import main
    from models import Confidence
    it = _ItemFalso("Marco topográfico — tipo XYZ1", "un", Confidence.ESTIMADO, _PALPITES[0])
    assert main.rebaixar_itens_sem_identidade([it]) == 0
    assert _selo(it) == "estimado" and it.observations == _PALPITES[0]


def test_CONTROLE_a_regra_irma_segue_igual():
    """O item cujo NOME é o bloco continua com o aviso de sempre."""
    import main
    from models import Confidence
    it = _ItemFalso("Elemento não identificado — bloco 'dgcfr' — identificar tipo", "un", Confidence.CONFIRMADO)
    assert main.rebaixar_itens_sem_identidade([it]) == 1
    assert "não sabemos o que é" in it.observations and er.MARCA_IDENTIDADE_PALPITE not in it.observations


def test_CUSTO_DOCUMENTADO_cubeta_de_laje_nervurada_cai():
    """A cubeta pelo nome do bloco provavelmente acerta — mas é palpite (no job
    medido, o mesmo bloco saiu com DUAS contagens ✓ diferentes). Só rebaixa."""
    import main
    from models import Confidence
    obs = ("Fonte: 2.719 INSERTs do bloco 'CUB_065250' (CONTAGEM DE BLOCOS). Nome do bloco sugere "
           "cubeta nervurada com dimensões 65x25, h=55cm.")
    it = _ItemFalso("Cubeta de laje nervurada", "un", Confidence.CONFIRMADO, obs)
    assert main.rebaixar_itens_sem_identidade([it]) == 1 and _selo(it) == "estimado"
