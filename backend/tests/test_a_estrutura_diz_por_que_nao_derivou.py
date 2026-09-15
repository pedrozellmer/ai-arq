# -*- coding: utf-8 -*-
"""A derivação de estrutura tem que dizer POR QUE recusou.

🩸 14/09/2026 — `motor:pd-estrutura` tem **ZERO registros em toda a base**: a
função nunca produziu um item. E não havia como saber por quê — o log de
`motor:pe-direito` conta os derivados da PINTURA e as áreas anotadas, e **cala
sobre a estrutura**. A lição de 03/08 está escrita no próprio arquivo, três
linhas acima, e foi aplicada só à pintura:

  *"Trava que recusa em silêncio é indistinguível de trava que não existe — e
  foi assim que a feature passou 33 dias com 0 derivados sem ninguém saber se
  era falta de uso ou defeito."*

📏 O funil que explica o zero (medido antes de escrever isto):
  31 projetos com pilar contado em `un` (507 pilares)
  17 deles com a seção "AxB cm" na descrição
   5 com pé-direito informado
   1 com item-ALVO (pilar+concreto em m³, ou pilar+fôrma em m²)
O gargalo é o ALVO, não a conta.

🚫 Este guarda protege o INSTRUMENTO, não muda comportamento nenhum. Duas
saídas óbvias estão barradas de propósito:
  · criar a linha — o item de pilar em `un` JÁ é o mesmo pilar; linha nova vira
    dupla contagem no orçamento;
  · anotar no item de pilar em vez do alvo — `_derivacao_vai_repor` APOSTA nesta
    função pra decidir se preserva uma linha, e em 24/08 a aposta errada zerou
    uma linha de 540 m².
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

_deriva = main._derive_estrutura_pe_direito


class _It:
    def __init__(self, descricao, unidade, qtd, conf="estimado"):
        self.description = descricao
        self.unit = unidade
        self.quantity = qtd
        self.confidence = conf
        self.observations = ""
        self.discipline = "Estrutura"
        self.origem = None


_PILAR = "Pilar de concreto armado — seção 14×30 cm"


# ── cada recusa tem um motivo PRÓPRIO ────────────────────────────────────
def test_sem_pe_direito_diz_isso():
    assert _deriva([_It(_PILAR, "un", 171)], 0) == 0
    assert "pé-direito" in _deriva.ultimo_motivo, _deriva.ultimo_motivo


def test_sem_secao_no_formato_diz_isso():
    """🪤 No acervo real existe "20cm × 60cm" (o `cm` depois de CADA número), que
    a régua não casa. Sem o motivo, esse caso é indistinguível de 'não tem
    pilar' — e a decisão sobre alargar a régua depende de saber a frequência."""
    assert _deriva([_It("Pilar de betão armado EEP.01 — 20cm × 60cm", "un", 7)], 3.0) == 0
    assert "seção" in _deriva.ultimo_motivo, _deriva.ultimo_motivo


def test_sem_alvo_diz_isso_E_QUANTO_se_perdeu():
    """O motivo mais importante: é o gargalo real (1 de 18 projetos). Ele traz o
    número que TERIA saído — sem isso o log diz que falhou, mas não o tamanho do
    que está sendo deixado na mesa."""
    assert _deriva([_It(_PILAR, "un", 171)], 3.0) == 0
    m = _deriva.ultimo_motivo
    assert "alvo" in m, m
    assert "171" in m, ("o motivo não diz quantos pilares: %s" % m)
    assert "21.55" in m or "21,55" in m, ("o motivo não diz o volume que teria "
                                          "saído: %s" % m)


# ── controle POSITIVO: com alvo, deriva e NÃO inventa motivo ─────────────
def test_CONTROLE_com_alvo_deriva_e_o_motivo_fica_VAZIO():
    itens = [_It(_PILAR, "un", 171), _It("Concreto estrutural de pilar", "m³", 0)]
    assert _deriva(itens, 3.0) == 1
    assert _deriva.ultimo_motivo == "", (
        "derivou e ainda assim registrou motivo de recusa: %r"
        % _deriva.ultimo_motivo)
    assert itens[1].quantity == 21.55, itens[1].quantity


def test_CONTROLE_o_selo_continua_ESTIMADO():
    """🚨 Regra dura nº1: o pé-direito é INFORMADO, não medido. Nada que sai
    daqui pode virar branco."""
    itens = [_It(_PILAR, "un", 171), _It("Concreto estrutural de pilar", "m³", 0)]
    _deriva(itens, 3.0)
    _c = itens[1].confidence
    assert str(getattr(_c, "value", _c)) == "estimado", _c
    assert "NÃO é medição" in itens[1].observations, itens[1].observations[:120]


def test_CONTROLE_alvo_que_JA_tem_numero_nao_e_sobrescrito():
    """Quando a IA já preencheu por índice, a conta só ANOTA a conferência — o
    orçamentista vê os dois números e decide. Sobrescrever seria destruir dado."""
    alvo = _It("Concreto estrutural de pilar", "m³", 18.0)
    _deriva([_It(_PILAR, "un", 171), alvo], 3.0)
    assert alvo.quantity == 18.0, "sobrescreveu a quantidade do alvo"
    assert "Conferência por seção×PD" in alvo.observations


# ── o log tem que CARREGAR o motivo (senão nasce morto de novo) ──────────
def test_o_log_do_pe_direito_REGISTRA_a_estrutura():
    """🪤 A função pode guardar o motivo perfeitamente e ninguém ler — foi o que
    aconteceu com `poly_layers_recusados`, coletado 5 dias sem consumidor."""
    import ast
    import io
    caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "main.py")
    fonte = io.open(caminho, encoding="utf-8").read()
    arv = ast.parse(fonte)

    achou = False
    for n in ast.walk(arv):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "_log_error"):
            continue
        prim = n.args[0] if n.args else None
        if not (isinstance(prim, ast.Constant) and prim.value == "motor:pe-direito"):
            continue
        trecho = ast.get_source_segment(fonte, n) or ""
        if "_derive_estrutura_pe_direito" in trecho and "ultimo_motivo" in trecho:
            achou = True
            break
    assert achou, (
        "o log `motor:pe-direito` não carrega o motivo da ESTRUTURA — a recusa "
        "volta a ser muda, e `motor:pd-estrutura` só grava quando DERIVA "
        "(zero vezes em toda a base até hoje)")
