# -*- coding: utf-8 -*-
"""Resposta cortada no teto de tokens não pode sair como se estivesse inteira.

🩸 03/09/2026, cliente `cliente-11@` (job `eebe543a`). Ele pediu uma análise
longa no chat do projeto. A resposta bateu no teto de 2.000 tokens e terminou
assim, no meio da palavra:

    "PROBLEMA 1 — SOBREPOSIÇÃO ENTRE PTO(1) E RJ45(1) … O projeto usa dois sím"

O `stop_reason` que a API devolve dizia `max_tokens`. **Ele não era lido em
lugar nenhum do `agent.py`** — o pedaço era entregue como se fosse a resposta.

🔑 Duas defesas, porque teto maior sozinho só empurra o problema:
  1. se cortou, PEDE PRA CONTINUAR de onde parou (até 2 vezes) e emenda;
  2. se ainda assim cortar, DIZ ao cliente.

Resposta incompleta **avisada** é utilizável — o cliente pede a continuação do
tópico. Resposta incompleta **calada** vira decisão errada com a nossa
assinatura embaixo. É a mesma família do dia inteiro: o sistema sabe que parou
no meio e o cliente não.
"""
import io
import os

import agent

_FONTE = io.open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "agent.py"), encoding="utf-8").read()


class _Bloco:
    def __init__(self, texto):
        self.type = "text"
        self.text = texto


class _Resp:
    def __init__(self, texto, stop_reason="end_turn"):
        self.content = [_Bloco(texto)]
        self.stop_reason = stop_reason


def _fila_de_respostas(monkeypatch, respostas):
    """Troca a chamada ao modelo por uma fila, e desliga o log."""
    fila = list(respostas)
    vistas = {"n": 0}

    def _fake(client, **kw):
        vistas["n"] += 1
        if not fila:
            raise AssertionError("o agente chamou o modelo mais vezes que o previsto")
        return fila.pop(0)

    import llm_retry
    monkeypatch.setattr(llm_retry, "call_with_retry", _fake)
    monkeypatch.setattr(agent, "_log_conversation", lambda *a, **k: None)
    monkeypatch.setattr(agent, "_alerta_lacuna", lambda *a, **k: None)
    # 🪤 `ask` DESISTE logo no começo se não houver ANTHROPIC_API_KEY, e devolve
    # "API key não configurada" sem nunca chamar o modelo. Sem isto o teste
    # passaria a medir o ramo errado — e os asserts de continuação leriam zero
    # chamadas como se o agente tivesse se comportado.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chave-de-teste")
    return vistas


def test_resposta_cortada_e_CONTINUADA_e_emendada(monkeypatch):
    """🩸 O caso do cliente: cortou, pede pra continuar, entrega inteira."""
    vistas = _fila_de_respostas(monkeypatch, [
        _Resp("O projeto usa dois sím", stop_reason="max_tokens"),
        _Resp("bolos diferentes para o mesmo ponto.", stop_reason="end_turn"),
    ])
    r = agent.ask("job1", "analise o projeto")
    assert vistas["n"] == 2, "não pediu a continuação"
    assert r["answer"].startswith("O projeto usa dois sím"), r["answer"]
    assert "bolos diferentes" in r["answer"], (
        "a continuação não foi emendada na resposta")
    assert "cortada no limite" not in r["answer"], (
        "avisou de corte numa resposta que ficou completa")


def test_se_continuar_cortando_o_cliente_e_AVISADO(monkeypatch):
    """Depois das tentativas, o corte tem que aparecer — nunca sair calado."""
    vistas = _fila_de_respostas(monkeypatch, [
        _Resp("parte 1", stop_reason="max_tokens"),
        _Resp(" parte 2", stop_reason="max_tokens"),
        _Resp(" parte 3", stop_reason="max_tokens"),
    ])
    r = agent.ask("job1", "analise o projeto")
    assert vistas["n"] == 3, "o teto de continuações mudou sem o teste saber"
    assert "cortada no limite" in r["answer"], (
        "a resposta saiu incompleta e CALADA — é o defeito original de volta")
    for p in ("parte 1", "parte 2", "parte 3"):
        assert p in r["answer"], "perdeu %r ao emendar" % p


def test_CONTROLE_resposta_completa_nao_ganha_aviso_nem_chamada_extra(monkeypatch):
    """Sem isto, o conserto poderia ser 'avisar sempre' ou 'chamar de novo sempre'."""
    vistas = _fila_de_respostas(monkeypatch, [
        _Resp("resposta inteira, terminou sozinha.", stop_reason="end_turn"),
    ])
    r = agent.ask("job1", "quantos itens?")
    assert vistas["n"] == 1, "chamou o modelo de novo sem precisar (custa dinheiro)"
    assert r["answer"] == "resposta inteira, terminou sozinha."
    assert "cortada" not in r["answer"]


def test_o_stop_reason_e_LIDO():
    """Guarda de forma: o defeito era não olhar esse campo.

    Se alguém tirar a leitura, os testes de cima ainda poderiam passar por
    acaso num refactor — este trava a causa, não só o sintoma.
    """
    assert 'stop_reason' in _FONTE and 'max_tokens"' in _FONTE, (
        "o agente voltou a não olhar por que o modelo parou")


def test_o_teto_de_tokens_nao_voltou_pro_valor_que_cortou():
    """2.000 tokens foi o teto que cortou a resposta do cliente."""
    assert "max_tokens=2000" not in _FONTE, (
        "o teto voltou pra 2.000, que é o valor que cortou a resposta real")
    assert "max_tokens=4000" in _FONTE
