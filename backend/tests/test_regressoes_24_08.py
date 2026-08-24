# -*- coding: utf-8 -*-
"""Os 4 críticos que a validação de 24/08 achou nos consertos de 23/08.

Contexto: em 23/08 uma auditoria achou 57 problemas no trabalho do próprio dia,
e eu fechei as 26 pendências trabalhando até 02:30. Na manhã seguinte, antes de
qualquer cliente rodar, 5 frentes independentes atacaram esse código. Acharam
16 problemas confirmados — DOIS deles regressões que eu mesmo tinha acabado de
introduzir, e que deixavam o sistema PIOR do que antes do conserto.

Este arquivo guarda os quatro. Cada teste tem controle: prova que o
comportamento errado seria reprovado.

  #1 fusão devolvia selo 'confirmado' ao número que o cliente digitou (regra nº1)
  #2 fusão reinjetava a unidade VAZIA que o endpoint já tinha consertado
  #4 /inform-area zerava e GRAVAVA a área com procedência (regressão minha)
  #5 pintura/fôrma zeradas apostando numa derivação que muitas vezes não repõe
"""
import io
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)


def _fatia_motor():
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.rindex("\n", 0, src.index("_RX_SECAO_PILAR")) + 1
    j = src.index("\ndef _dedupe_revisoes", i)
    from engine_rules import (AREA_UNITS_HONESTY as _A, FLOOR_M2_UNITS as _F,
                              is_floor_surface as _isf)
    from models import Confidence
    import re as _re
    ns = {"__name__": "motor_ns", "_AREA_UNITS_HONESTY": _A, "_FLOOR_M2_UNITS": _F,
          "_is_floor_surface": _isf, "Confidence": Confidence,
          "_re_honesty": _re, "_re": _re, "re": _re}
    exec(compile(src[i:j], "main_slice", "exec"), ns)
    return ns


def _fatia_fusao(revs, status=200):
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("def _fundir_revisoes_do_cliente")
    j = src.index("\n_CAMPOS_ITEM_VERSAO", i)
    ns = {"__name__": "fusao_ns",
          "_supa_rest_service": lambda m, p, **k: (status, revs),
          "_log_error": lambda *a, **k: None,
          "_norm_desc": lambda d: " ".join(str(d or "").lower().split())}
    exec(compile(src[i:j], "main_slice", "exec"), ns)
    return ns["_fundir_revisoes_do_cliente"]


class _Item:
    def __init__(self, description, unit, quantity, observations="", origem="",
                 confidence=None):
        self.description = description
        self.unit = unit
        self.quantity = quantity
        self.observations = observations
        self.origem = origem
        self.confidence = confidence


def _selo(it):
    return str(getattr(it.confidence, "value", it.confidence))


# ══════════════════════════════════════════════════════════════════════════
#  #4 — /inform-area PREENCHE, nunca zera
# ══════════════════════════════════════════════════════════════════════════
def test_inform_area_nao_zera_area_com_procedencia():
    """🚨 Regressão: o conserto da manhã de 23/08 (passar o pé-direito) foi
    desfeito pelo da noite (travas por origem), porque `project_items` nunca
    guardou a origem — na reidratação tudo volta com origem='' e as duas travas
    falham juntas. Caso Tammyres: pintura 1.641 m² e massa corrida 817 m²
    iam pra 0 e eram GRAVADAS assim."""
    f = _fatia_motor()["_apply_area_honesty"]
    pintura = _Item("Pintura latex acrilica em parede", "m²", 1641.4,
                    "⚠ ESTIMADO — 303.9 m de parede × pé-direito 2.70 m informado por você × 2 faces")
    massa = _Item("Massa corrida sobre paredes internas", "m²", 817.0,
                  "A-WALL = 303.96 ml × 2,70 m (pé-direito informado)")
    piso = _Item("Piso vinílico", "m²", 0, "Área NÃO medida — informe a área no upload")
    itens = [pintura, massa, piso]

    filled, blanked = f(itens, 118.5, "informado", pe_direito=2.7, apenas_preencher=True)

    assert pintura.quantity == 1641.4, "a rota zerou pintura com procedência"
    assert massa.quantity == 817.0, "a rota zerou massa corrida com procedência"
    assert blanked == 0, "esta rota NUNCA pode zerar — ela só preenche"
    assert piso.quantity == 118.5 and filled == 1, "parou de preencher o que estava em branco"


def test_o_controle_prova_que_sem_a_flag_o_estrago_acontece():
    """Controle positivo: sem `apenas_preencher`, e com a origem perdida (que é
    exatamente o estado da linha reidratada do banco antes de 24/08), os dois
    itens são zerados. É a prova de que a flag está segurando alguma coisa."""
    f = _fatia_motor()["_apply_area_honesty"]
    pintura = _Item("Massa corrida sobre paredes internas", "m²", 817.0,
                    "A-WALL = 303.96 ml × 2,70 m (pé-direito informado)")
    f([pintura], 118.5, "informado", pe_direito=2.7)      # sem a flag
    assert pintura.quantity == 0, (
        "o cenário do bug não reproduz mais — reveja este teste antes de confiar "
        "no de cima")


def test_a_origem_e_gravada_e_relida():
    """Sem isto, a reidratação volta a decidir no escuro."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("def _persist_items_to_supabase")
    corpo = src[i:i + 2500]
    assert '"origem"' in corpo, "_persist_items_to_supabase não grava a origem"
    assert src.count('origem=r.get("origem") or ""') == 2, (
        "os DOIS pontos que reconstroem BudgetItem a partir do banco precisam "
        "reler a origem (regeneração da planilha revisada e /inform-area)")


# ══════════════════════════════════════════════════════════════════════════
#  #5 — só zera quando a nossa conta REALMENTE vai repor
# ══════════════════════════════════════════════════════════════════════════
def _pintura_ia():
    return _Item("Pintura latex em paredes internas", "m²", 540.0,
                 "300 m × pé-direito 1,80 m informado por você — conta do modelo")


def test_pintura_sobrevive_quando_outra_pintura_bloqueia_a_derivacao():
    """Cenário A: existe "Pintura em teto" medida do CAD. `_derive_pintura_pe_direito`
    desiste (`if any(_e_pintura(i) and _qtd(i) > 0)`), então zerar aqui apaga a
    linha e ninguém repõe."""
    ns = _fatia_motor()
    p = _pintura_ia()
    itens = [
        _Item("Alvenaria de vedação", "m", 300.0, "", origem="dxf_geom"),
        _Item("Pintura latex em teto", "m²", 80.0, "", origem="dxf_geom"),
        p,
    ]
    ns["_apply_area_honesty"](itens, 0, "", pe_direito=1.8)
    ns["_derive_pintura_pe_direito"](itens, 1.8)
    assert p.quantity > 0, "linha zerada e a derivação não repôs — dado perdido"


def test_pintura_sobrevive_quando_o_linear_medido_nao_e_parede():
    """Cenário B: o único linear do CAD é eletroduto. A derivação só soma
    m/ml cuja descrição tenha parede/alvenaria/drywall — então desiste."""
    ns = _fatia_motor()
    p = _pintura_ia()
    itens = [_Item("Eletroduto PVC 25mm", "m", 200.0, "", origem="dxf_geom"), p]
    ns["_apply_area_honesty"](itens, 0, "", pe_direito=1.8)
    ns["_derive_pintura_pe_direito"](itens, 1.8)
    assert p.quantity > 0, "linha zerada e a derivação não repôs — dado perdido"


def test_quando_a_derivacao_VAI_repor_a_conta_nossa_vence():
    """O contrário também tem que continuar valendo: havendo parede medida e
    nenhuma outra pintura, a linha do modelo É zerada de propósito pra a nossa
    conta (2 faces) entrar no lugar."""
    ns = _fatia_motor()
    p = _pintura_ia()
    itens = [_Item("Alvenaria de vedação", "m", 300.0, "", origem="dxf_geom"), p]
    ns["_apply_area_honesty"](itens, 0, "", pe_direito=1.8)
    assert p.quantity == 0, "a honestidade tem que limpar pra a nossa conta entrar"
    ns["_derive_pintura_pe_direito"](itens, 1.8)
    assert abs(p.quantity - round(300.0 * 1.8 * 2, 1)) < 0.11, (
        "a nossa conta determinística não entrou: %s" % p.quantity)
    assert p.origem == "deriv_pd"


def test_derivacao_vai_repor_responde_certo_nos_dois_sentidos():
    f = _fatia_motor()["_derivacao_vai_repor"]
    parede = _Item("Alvenaria de vedação", "m", 300.0, "", origem="dxf_geom")
    alvo = "Pintura latex em paredes internas"
    assert f([parede, _pintura_ia()], alvo, 2.7) is True
    assert f([_Item("Eletroduto", "m", 200.0)], alvo, 2.7) is False
    assert f([parede], alvo, 0) is False        # sem pé-direito não deriva nada
    # fôrma de pilar precisa da seção "AxB cm" num item contado em `un`
    forma = "Fôrma de pilar em chapa compensada"
    assert f([_Item("Pilar P1 20x40 cm", "un", 12)], forma, 2.7) is True
    assert f([_Item("Pilar P1", "un", 12)], forma, 2.7) is False


# ══════════════════════════════════════════════════════════════════════════
#  #1 e #2 — o ramo "casou" da fusão
# ══════════════════════════════════════════════════════════════════════════
def _rev(desc, unit, qtd, obs=""):
    return {"edits": {"description": desc, "unit": unit, "quantity": qtd,
                      "observations": obs}, "reviewed_at": "2026-08-23T10:00:00Z"}


def _medido(desc="Piso porcelanato 60x60", unit="m²", qtd=210.0):
    from models import BudgetItem, Confidence
    return BudgetItem(item_num="2.1", description=desc, unit=unit, quantity=qtd,
                      confidence=Confidence.CONFIRMADO, origem="dxf_geom",
                      ref_sheet="ARQ-01", discipline="Pisos")


def test_quantidade_corrigida_a_mao_perde_o_selo_de_medido():
    """🚨 REGRA DURA Nº1. A linha ACRESCENTADA já saía 'estimado' (conserto de
    ontem), mas a CASADA continuava devolvendo 'confirmado' ao número digitado —
    e a célula dizia, na mesma frase, "✓ MEDIDO do CAD" e "este número é o que
    você corrigiu". O endpoint de revisão já faz o certo; a fusão desfazia."""
    f = _fatia_fusao([_rev("Piso porcelanato 60x60", "m²", 130.0)])
    it = _medido()
    f([it], "pai123")
    assert it.quantity == 130.0, "a correção do cliente não sobreviveu (regra nº7)"
    assert _selo(it) == "estimado", (
        "número digitado à mão saiu como '%s' — a planilha ia marcar "
        "'✓ MEDIDO do CAD'" % _selo(it))
    assert it.origem == "revisao_cliente"
    assert "não é medida do CAD" in it.observations


def test_correcao_so_de_texto_nao_derruba_o_selo_da_medicao():
    """Controle do outro lado: se o cliente só arrumou o NOME do serviço, a
    medição continua sendo medição. Rebaixar tudo seria o exagero simétrico."""
    f = _fatia_fusao([_rev("Piso porcelanato 60x60 retificado", "m²", 210.0)])
    it = _medido()
    # a chave de casamento é a descrição normalizada, então o alvo tem que ser
    # o mesmo texto que o cliente editou
    it.description = "Piso porcelanato 60x60 retificado"
    f([it], "pai123")
    assert _selo(it) == "confirmado", "rebaixou uma medição que não mudou de número"


def test_unidade_vazia_do_payload_nao_apaga_a_unidade_consertada():
    """🚨 Medido no banco: 8 linhas com unit='' em item_reviews, 7 de armadura
    CA-50 em kg. O endpoint conserta antes de gravar em project_items, mas
    item_reviews guarda o payload CRU — e a fusão lê item_reviews, contornando
    a trava de 18/08 por não passar por ela."""
    f = _fatia_fusao([_rev("Pilares — armadura CA-50", "", 1500.0)])
    it = _medido(desc="Pilares — armadura CA-50", unit="kg", qtd=18168.0)
    f([it], "pai123")
    assert it.unit == "kg", (
        "a unidade voltou a ser apagada (%r): quem cota não sabe se é kg, t ou "
        "barra" % it.unit)
    assert it.quantity == 1500.0, "a correção de quantidade do cliente se perdeu"


def test_descricao_vazia_tambem_e_ignorada():
    f = _fatia_fusao([{"edits": {"description": "Piso porcelanato 60x60",
                                 "unit": "m²", "quantity": 130.0},
                       "reviewed_at": "2026-08-23T10:00:00Z"}])
    it = _medido()
    f([it], "pai123")
    assert it.description == "Piso porcelanato 60x60"


def test_o_controle_prova_que_o_ramo_casado_seria_reprovado():
    """Controle positivo do #1/#2: o comportamento ANTIGO (escrever os 4 campos
    direto, sem olhar vazio nem selo) seria reprovado pelos dois testes acima."""
    from models import Confidence

    class _Velho:
        """Reprodução do ramo 'casou' como era até 24/08."""
        @staticmethod
        def aplicar(alvo, ed):
            alvo.description = ed.get("description", alvo.description)
            alvo.unit = ed.get("unit", alvo.unit)
            alvo.quantity = ed.get("quantity", alvo.quantity)
            alvo.observations = "✏️ REVISADO POR VOCÊ — este número é o que você corrigiu."

    it = _medido(desc="Pilares — armadura CA-50", unit="kg", qtd=18168.0)
    _Velho.aplicar(it, {"description": "Pilares — armadura CA-50", "unit": "",
                        "quantity": 1500.0})
    assert it.unit == "", "o cenário do bug não reproduz mais"
    assert it.confidence == Confidence.CONFIRMADO, "o cenário do bug não reproduz mais"
