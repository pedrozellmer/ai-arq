# -*- coding: utf-8 -*-
"""Uma obra tem UMA administração local — a planilha entregava até seis.

🩸 15/09/2026 — estudo dos itens repetidos (item 2 da fila autorizada). A IA
sugere "Administração local de obra" como item de práxis EM CADA PRANCHA, cada
vez com outra redação. A consolidação não junta porque as descrições diferem.

📏 Medido em 70 projetos de cliente concluídos (60 dias): 60 com uma linha,
10 repetindo (5 com 2, 2 com 3, 2 com 4, 1 com 6 — todas "vb 1" pra uma obra
só). E com 4+ réplicas de mesma chave a passada 1 SOMAVA: "(várias variantes)
— 4 vb".

🔑 O conserto não apaga em silêncio: fica uma linha de 1 vb, estimada, e a
observação lista NO COMEÇO as redações juntadas.
🚫 Nunca junta: linha do cliente (regra nº7), prazo "informado por você",
linha confirmada, linha que não é verba. Os outros preliminares não são alvo.

Todos os testes CHAMAM as funções — nenhum procura palavra no fonte, exceto o
guarda do ponto de chamada, que lê a árvore (AST) do `process_job`.
"""
import ast
import io
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from engine_rules import (administracao_local_com_prazo_chutado as _chutou,  # noqa: E402
                          e_administracao_local as _e_al)

_MARCA = "Uma obra tem uma administração local só"

_REDACOES = [
    "Administração local de obra — encarregado/mestre de obras durante execução",
    "Administração local de obra — equipe de gestão, encarregado e segurança",
    "Administração local de obra — encarregado, equipe de apoio, EPI e sinalização",
    "Administração local de obra — encarregado, mestre de obras e equipe de apoio",
    "Administração local de obra — engenheiro residente e equipe de gestão",
    "Administração local de obra — equipe de gestão e fiscalização no canteiro",
]


class _Item(object):
    def __init__(self, description, unit="vb", quantity=1.0, observations="",
                 origem="", confidence="estimado", ref_sheet="prancha-1.pdf"):
        self.description = description
        self.unit = unit
        self.quantity = quantity
        self.observations = observations
        self.origem = origem
        self.confidence = confidence
        self.ref_sheet = ref_sheet
        self.discipline = "Serviços Preliminares"


def _adm(itens):
    return [i for i in itens if _e_al(i.description)]


# ══════════════════════════════════════════════════════════════════════════
#  1. O CASO MEDIDO: seis redações, uma obra
# ══════════════════════════════════════════════════════════════════════════
def test_as_seis_redacoes_viram_UMA_linha_de_1_vb():
    import main as _m
    itens = [_Item(d, ref_sheet="prancha-%d.pdf" % k) for k, d in enumerate(_REDACOES)]
    itens += [_Item("Piso cerâmico 60x60", "m²", 48.5),
              _Item("Mobilização e desmobilização de obra", "vb", 1.0)]
    n = _m._juntar_admin_local(itens)
    assert n == 5, "saíram %r linhas, esperava 5 (6 viram 1)" % n
    adm = _adm(itens)
    assert len(adm) == 1, "sobraram %d linhas de administração local" % len(adm)
    fica = adm[0]
    assert fica.unit == "vb" and fica.quantity == 1.0, (fica.unit, fica.quantity)
    assert fica.observations.startswith(_MARCA), (
        "a nota não está no começo da observação: %r" % fica.observations[:120])
    for d in _REDACOES:
        if d != fica.description:
            assert d[:60] in fica.observations, (
                "a redação juntada %r sumiu da vista do arquiteto" % d[:60])
    # quem não é o alvo continua lá, intacto
    assert any(i.description.startswith("Piso cerâmico") and i.quantity == 48.5 for i in itens)
    assert any(i.description.startswith("Mobilização") and i.quantity == 1.0 for i in itens)


def test_a_soma_de_replicas_da_consolidacao_REAL_volta_a_1_verba():
    """🩸 A passada 1 funde 4+ réplicas de mesma chave SOMANDO — uma obra
    virava "4 vb". Aqui roda a consolidação de verdade e depois o conserto."""
    import main as _m
    from models import BudgetItem, Confidence
    brutos = [BudgetItem(item_num=str(k + 1),
                         description="Administração local de obra — encarregado e equipe de apoio",
                         unit="vb", quantity=1.0, ref_sheet="prancha-%d.pdf" % k,
                         confidence=Confidence("estimado"),
                         discipline="Serviços Preliminares")
              for k in range(4)]
    consolidados = _m._consolidate_items(brutos)
    adm = _adm(consolidados)
    # 🧪 controle do cenário: se a consolidação parar de somar, este teste não mede mais nada
    assert len(adm) == 1 and adm[0].quantity > 1.0 and "consolidado de" in adm[0].observations.lower(), (
        "a consolidação não produziu mais a soma de réplicas — o cenário mudou: %r"
        % [(i.description, i.quantity) for i in adm])
    _m._aplicar_admin_local(consolidados)
    _m._juntar_admin_local(consolidados)
    adm = _adm(consolidados)
    assert len(adm) == 1 and adm[0].quantity == 1.0, (
        "a soma de réplicas continuou: %r" % [(i.quantity, i.unit) for i in adm])
    assert _MARCA in adm[0].observations


# ══════════════════════════════════════════════════════════════════════════
#  2. O QUE NUNCA É JUNTADO (controles)
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_a_linha_do_cliente_fica_como_ele_deixou():
    import main as _m
    cliente = _Item(_REDACOES[0], quantity=2.0, origem="revisao_cliente")
    itens = [cliente, _Item(_REDACOES[1]), _Item(_REDACOES[2])]
    n = _m._juntar_admin_local(itens)
    assert n == 1, "juntou %r (esperava só as 2 da IA viram 1)" % n
    assert cliente in itens and cliente.quantity == 2.0 and _MARCA not in cliente.observations, (
        "mexeu na linha que o cliente editou — regra dura nº7")


def test_CONTROLE_prazo_informado_por_voce_fica():
    import main as _m
    informado = _Item(_REDACOES[0], unit="vb", quantity=12.0,
                      observations="⚠ ESTIMADO — prazo de 12 mês(es) informado por você durante o processamento.")
    itens = [informado, _Item(_REDACOES[1])]
    assert _m._juntar_admin_local(itens) == 0
    assert informado in itens and informado.quantity == 12.0


def test_CONTROLE_confirmado_e_outra_unidade_ficam():
    import main as _m
    confirmado = _Item(_REDACOES[0], confidence="confirmado")
    em_un = _Item(_REDACOES[1], unit="un", quantity=3.0)
    itens = [confirmado, em_un, _Item(_REDACOES[2])]
    assert _m._juntar_admin_local(itens) == 0, "juntou linha confirmada ou fora de verba"
    assert confirmado in itens and em_un in itens and em_un.quantity == 3.0


def test_CONTROLE_uma_linha_so_nao_muda_nada():
    import main as _m
    unica = _Item(_REDACOES[0], observations="Item de práxis.")
    itens = [unica]
    assert _m._juntar_admin_local(itens) == 0
    assert unica.observations == "Item de práxis." and unica.quantity == 1.0


def test_CONTROLE_os_outros_preliminares_nao_sao_alvo():
    import main as _m
    itens = [_Item("Limpeza final de obra", quantity=1.0),
             _Item("Limpeza final de obra — remoção de entulho", quantity=1.0),
             _Item("Mobilização e desmobilização de obra", quantity=1.0)]
    assert _m._juntar_admin_local(itens) == 0
    assert len(itens) == 3


# ══════════════════════════════════════════════════════════════════════════
#  3. ROBUSTEZ
# ══════════════════════════════════════════════════════════════════════════
def test_rodar_DUAS_vezes_nao_duplica_a_nota():
    """🪤 A planilha é refeita (regra nº7) e pode passar aqui de novo."""
    import main as _m
    itens = [_Item(d) for d in _REDACOES[:3]]
    assert _m._juntar_admin_local(itens) == 2
    assert _m._juntar_admin_local(itens) == 0
    assert _adm(itens)[0].observations.count(_MARCA) == 1


def test_a_nota_sobrevive_ao_corte_de_1000_caracteres():
    import main as _m
    longa = "x" * 995
    itens = [_Item(_REDACOES[0], observations=longa), _Item(_REDACOES[1], observations=longa)]
    _m._juntar_admin_local(itens)
    fica = _adm(itens)[0]
    assert len(fica.observations) <= 1000
    assert fica.observations.startswith(_MARCA), "o corte levou a nota embora"


def test_a_regua_de_reconhecimento_e_UMA_so():
    """🔑 A junção e o prazo chutado perguntam a mesma coisa. Se um dia
    divergirem, uma linha em mês vira verba e escapa da junção (ou o contrário)."""
    amostras = ["Administração local de obra", "Administracao local da obra",
                "ADMINISTRAÇÃO LOCAL — equipe", "Custos com administração local no canteiro",
                "Locação de container de obra", "Mobilização e desmobilização de obra",
                "Serventia — ajudante geral"]
    for d in amostras:
        assert _chutou(d, "mês") == _e_al(d), "as duas réguas divergem em %r" % d
    assert _e_al("Administração local de obra") and not _e_al("Locação de container de obra")


# ══════════════════════════════════════════════════════════════════════════
#  4. O MOTOR CHAMA, NA ORDEM CERTA, COM A LISTA DO JOB
# ══════════════════════════════════════════════════════════════════════════
def test_e_chamada_no_process_job_DEPOIS_de_normalizar_e_com_all_items():
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    arvore = ast.parse(fonte)
    proc = [n for n in ast.walk(arvore)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "process_job"]
    assert len(proc) == 1, "não achei o process_job"
    chamadas = {}
    for n in ast.walk(proc[0]):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in (
                "_aplicar_admin_local", "_juntar_admin_local"):
            chamadas.setdefault(n.func.id, []).append(n)
    assert "_juntar_admin_local" in chamadas, (
        "`_juntar_admin_local` existe e o process_job não chama — o conserto não roda")
    assert "_aplicar_admin_local" in chamadas
    j = min(chamadas["_juntar_admin_local"], key=lambda c: c.lineno)
    a = min(chamadas["_aplicar_admin_local"], key=lambda c: c.lineno)
    assert j.lineno > a.lineno, (
        "a junção roda ANTES de normalizar — as linhas em mês ainda não são verba e escapam")
    assert j.args and isinstance(j.args[0], ast.Name) and j.args[0].id == "all_items", (
        "a junção é chamada com outra lista, não com os itens do job")
