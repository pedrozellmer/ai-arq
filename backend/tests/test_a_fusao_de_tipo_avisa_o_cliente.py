# -*- coding: utf-8 -*-
"""199 linhas sumiram da planilha e o único registro era um print() no servidor.

🩸 03/09/2026. `_consolidate_by_type_code` funde o MESMO tipo de divisória
(DRY 07, DW-12…) que aparece em várias pranchas: soma as quantidades e mantém
UMA linha. A decisão é certa — o caso cliente-24 tinha 191 itens de drywall
fragmentados, 156 zerados.

**Esconder que fundiu é que não era.** Medido no acervo:

    75 itens fundidos, em 4 projetos
    274 entradas engolidas  →  199 linhas a menos na planilha do cliente
    registro disso: 1 print() no log do Render, que ninguém lê

O cliente abre a planilha, conta menos linhas do que a planta tem, e não tem
como saber por quê. É a mesma família do dia inteiro: o motor sabe a coisa
certa e o cliente recebe outra — ver [[project_seis_consertos_20260901]].

🪤 O stage novo entrou em `_STAGES_DIAGNOSTICO`. Sem isso o `_log_error` grava
com severity="error" e o painel do admin passa a mostrar operação NORMAL como
erro — alarme que grita sem motivo é alarme que se aprende a ignorar.

⏭️ NÃO consertado hoje, e de propósito: a aritmética. Somar o mesmo tipo entre
pranchas pode contar a MESMA parede duas vezes (o item do job 43b26b58 gravou
12.496 ml declarando fonte de 975 m — 12,8×). Mas só 12 dos 75 itens declaram
fonte e só 1 contradiz: não dá pra desenhar regra com um caso. O caminho que
esse número alimentava (pintura derivada) já está travado desde 02/09.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main as m                                       # noqa: E402
from _corpo import fonte, sem_comentarios                  # noqa: E402


class _It:
    def __init__(self, desc, qty, unit="ml", disc="Vedações", num="1.1"):
        self.description, self.quantity, self.unit = desc, qty, unit
        self.discipline, self.item_num = disc, num
        self.observations, self.confidence, self.origem = "", "estimado", ""


class _Proj:
    def __init__(self):
        self.warnings = []


def _tipo(n, qty):
    return _It("Parede drywall tipo DRY %02d — espessura 82,5 mm" % n, qty)


# ── O aviso, que é o conserto ──────────────────────────────────────────────
def test_fundir_AVISA_o_cliente():
    """🩸 As 199 linhas. Se este teste cair, elas voltam a sumir caladas."""
    pd = _Proj()
    m._consolidate_by_type_code([_tipo(7, 10), _tipo(7, 20), _tipo(7, 30)], pd)
    assert pd.warnings, "fundiu 3 linhas em 1 e não avisou ninguém"
    aviso = pd.warnings[0]
    assert "somados" in aviso.lower(), aviso
    assert "3 linha" in aviso and "viraram 1" in aviso, (
        "o aviso não diz os números reais: %r" % aviso)


def test_CONTROLE_sem_fusao_NAO_inventa_aviso():
    """🧪 Alarme que acende sem motivo é alarme que o Pedro aprende a ignorar."""
    pd = _Proj()
    m._consolidate_by_type_code([_tipo(7, 10), _tipo(8, 20)], pd)
    assert pd.warnings == [], "avisou fusão que não aconteceu: %r" % pd.warnings


def test_o_aviso_NAO_apaga_avisos_que_ja_existiam():
    """🪤 `project_data.warnings` é lista compartilhada — sobrescrever some com
    o aviso de outro passo do motor."""
    pd = _Proj()
    pd.warnings = ["aviso anterior do motor"]
    m._consolidate_by_type_code([_tipo(7, 10), _tipo(7, 20)], pd)
    assert "aviso anterior do motor" in pd.warnings, pd.warnings
    assert len(pd.warnings) == 2, pd.warnings


def test_sem_project_data_nao_estoura():
    """A função é chamada de outros lugares; aviso é bônus, nunca requisito."""
    saida = m._consolidate_by_type_code([_tipo(7, 10), _tipo(7, 20)])
    assert len(saida) == 1


# ── O contador que o chamador registra ─────────────────────────────────────
def test_a_funcao_EXPOE_quantas_fundiu():
    m._consolidate_by_type_code([_tipo(7, 10), _tipo(7, 20), _tipo(7, 5)])
    assert m._consolidate_by_type_code.ultimo_fundidos == 2
    assert m._consolidate_by_type_code.ultimo_grupos == 1


def test_CONTROLE_o_contador_ZERA_quando_nao_funde():
    """🪤 Atributo de função sobrevive entre chamadas: se não zerar, o job
    seguinte herda o número do anterior e o log passa a mentir."""
    m._consolidate_by_type_code([_tipo(7, 10), _tipo(7, 20)])
    m._consolidate_by_type_code([_tipo(7, 10), _tipo(8, 20)])
    assert m._consolidate_by_type_code.ultimo_fundidos == 0, (
        "o contador ficou com o valor da chamada anterior")


# ── Regressão: fundir continua fazendo o que fazia ─────────────────────────
def test_CONTROLE_a_fusao_continua_SOMANDO_e_marcando_estimado():
    """🧪 O conserto é de visibilidade. Se ele mudou o número entregue, virou
    outra coisa — e regra dura nº1 exige o selo de estimado na soma."""
    saida = m._consolidate_by_type_code([_tipo(7, 10), _tipo(7, 20), _tipo(7, 30)])
    assert len(saida) == 1
    assert saida[0].quantity == 60.0, saida[0].quantity
    assert str(getattr(saida[0].confidence, "value", saida[0].confidence)) == "estimado"
    assert "somado de 3 entradas" in saida[0].observations


def test_CONTROLE_tipos_DIFERENTES_nao_se_misturam():
    saida = m._consolidate_by_type_code([_tipo(7, 10), _tipo(8, 20), _tipo(8, 5)])
    assert len(saida) == 2
    assert sorted(round(i.quantity, 2) for i in saida) == [10.0, 25.0]


# ── O chamador ─────────────────────────────────────────────────────────────
def test_o_chamador_PASSA_o_project_data():
    """🪤 Guarda de ponto de chamada: a função pode avisar perfeitamente e
    nunca receber o projeto — foi o caso da derivação de pintura, que existia
    e a rota não chamava."""
    src = sem_comentarios(fonte("main.py"))
    assert "_consolidate_by_type_code(all_items, project_data)" in src, (
        "o motor voltou a fundir sem passar o projeto — o aviso não chega")


def test_o_chamador_REGISTRA_no_log_inclusive_com_zero():
    src = sem_comentarios(fonte("main.py"))
    assert '_log_error("motor:consolida-tipo"' in src, (
        "a fusão voltou a existir só num print() do servidor")
    assert "ultimo_fundidos" in src and "itens_depois" in src, (
        "o log não diz quanto fundiu nem quantos itens sobraram")


def test_o_stage_novo_e_DIAGNOSTICO_e_nao_erro():
    """🪤 `_log_error` não filtra stage, mas stage fora de _STAGES_DIAGNOSTICO
    entra como severity='error' — operação normal viraria alarme vermelho no
    painel do admin."""
    assert "motor:consolida-tipo" in m._STAGES_DIAGNOSTICO, (
        "o stage novo não foi registrado como diagnóstico — cada job vai "
        "acender um erro falso no painel")


def test_CONTROLE_a_checagem_do_stage_sabe_REPROVAR():
    assert "motor:stage-que-nao-existe" not in m._STAGES_DIAGNOSTICO
