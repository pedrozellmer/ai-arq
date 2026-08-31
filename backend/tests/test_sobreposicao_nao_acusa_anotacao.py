# -*- coding: utf-8 -*-
"""Aviso de sobreposição não dispara em layer de ANOTAÇÃO (31/08/2026).

🩸 CASO PROF. MOAB (job 2de6625f, cliente novo de 31/08). Quatro itens
diferentes — forro de madeira (55 m²), laje impermeabilizada (15), piso tátil
direcional (2) e piso tátil de alerta (0,5) — foram acusados de possível
duplicação entre si. O motivo alegado: "compartilham o mesmo layer
'G-ANNO-TEXT'".

`G-ANNO-TEXT` é o layer de TEXTO da prancha (padrão AIA: General-Annotation-
Text). É onde os RÓTULOS moram — todos eles, por definição. A regra de dedup
assume que dois itens no mesmo layer podem ser a mesma geometria contada duas
vezes: verdade num layer de parede, sem sentido num layer de anotação.

📊 Medido no banco no mesmo dia: **553 avisos de sobreposição, 138 (26%) em
layer de anotação**, em 22 projetos. Um em cada quatro é falso.

🩸 E é caro: em 31/08 um cliente APAGOU um item por causa de um aviso desses.
Aviso falso manda o cliente apagar linha certa — e a exclusão é justamente o
sinal que a gente acabou de destravar pra aprender com o erro do motor.

🪤 O que NÃO fazer: desligar a regra. Ela é útil — no mesmo dia ela pegou uma
parede de 115 m² desenhada em dois layers, e o cliente confirmou apagando uma.
O conserto é não aplicá-la onde ela não faz sentido.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


class _Item:
    def __init__(self, desc, unit, qty, layer, conf="estimado"):
        self.description = desc
        self.unit = unit
        self.quantity = qty
        self.observations = "Fonte: geometria do layer '%s'." % layer
        self.confidence = conf
        self.origem = ""
        self.discipline = ""


def _rodar(itens):
    """🪤 Na 1a versao eu chamei `_pos_processa_itens`, que NAO EXISTE, com um
    fallback que devolvia os itens intocados. Os testes de "nao avisa" passaram
    a toa (nada rodou!) e so os CONTROLES denunciaram. Guarda que nao prova que
    executou nao vale nada — por isso a chamada aqui e direta, sem fallback."""
    saida, _n = main._apply_post_consolidation_rules(itens)
    return saida


def _tem_aviso(it):
    return "sobreposi" in (it.observations or "").lower()


def test_layer_de_TEXTO_nao_gera_aviso_de_sobreposicao():
    """O caso do Prof. Moab, reduzido."""
    itens = [
        _Item("Forro de madeira colonial", "m²", 55, "G-ANNO-TEXT"),
        _Item("Laje de concreto armado impermeabilizada", "m²", 15, "G-ANNO-TEXT"),
        _Item("Piso tátil direcional", "m²", 2, "G-ANNO-TEXT"),
        _Item("Piso tátil de alerta", "m²", 0.5, "G-ANNO-TEXT"),
    ]
    _rodar(itens)
    acusados = [i.description for i in itens if _tem_aviso(i)]
    assert not acusados, (
        "acusou sobreposição em layer de anotação: " + str(acusados))


def test_CONTROLE_layer_de_GEOMETRIA_continua_acusando():
    """🧪 O controle que impede o conserto de virar 'desligar a regra'.

    Este é o caso REAL do Luiz (31/08): parede de 115 m² no layer 00_PAREDE e
    outra no layer ARQ-ALV. Ele apagou uma — o aviso estava certo."""
    itens = [
        _Item("Parede — alvenaria", "m²", 115.32, "ARQ-ALV"),
        _Item("Parede — vedação", "m²", 42.72, "ARQ-ALV"),
    ]
    _rodar(itens)
    assert any(_tem_aviso(i) for i in itens), (
        "o aviso de sobreposição parou de funcionar em layer de geometria — "
        "o conserto virou 'desligar a regra'")


def test_varios_nomes_de_layer_de_anotacao_sao_reconhecidos():
    """Os nomes reais que aparecem no nosso banco: G-ANNO-TEXT, TEXTO,
    TEXTOS 02, A-DETL-GENF, 02 - COTAS, PDF_TEXT, A-ANNO-TEXT."""
    # 🪤 Só os que o extrator de layer REALMENTE reconhece. `_LAYER_RE`
    # (main.py:4718) exige começar com LETRA, então "02 - COTAS" e "00_PAREDE"
    # nem chegam aqui — layer numerado é invisível pra esta regra inteira,
    # limitação pré-existente e medida em 31/08 (ver project_motor_layer_numerado).
    for layer in ("G-ANNO-TEXT", "TEXTO", "TEXTOS", "A-DETL-GENF",
                  "PDF_TEXT", "A-ANNO-TEXT", "ELE-TEXTOS"):
        itens = [_Item("Item A", "m²", 50, layer),
                 _Item("Item B", "m²", 10, layer)]
        _rodar(itens)
        assert not any(_tem_aviso(i) for i in itens), (
            "layer de anotação nao reconhecido: " + layer)


def test_CONTROLE_layers_de_obra_de_verdade_nao_sao_confundidos():
    """🪤 A peneira casa por substring. 'anno' não pode pegar layer legítimo.
    Estes TÊM que continuar sendo tratados como geometria."""
    for layer in ("A-WALL", "ARQ-ALV", "A-FLOR-PATT",
                  "A-CLNG", "PISO", "FORRO", "ALVENARIA"):
        itens = [_Item("Item A", "m²", 50, layer),
                 _Item("Item B", "m²", 10, layer)]
        _rodar(itens)
        assert any(_tem_aviso(i) for i in itens), (
            "layer de obra virou 'anotação' por engano: " + layer)
