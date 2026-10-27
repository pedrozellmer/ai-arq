# -*- coding: utf-8 -*-
"""O chat responde com o que juntou, em vez de "não consegui formular".

🩸 27/10/2026 — cliente aceitou a oferta do próprio agente ("quer que eu
busque o código SINAPI de cada item?" → "sim"). O agente chamou 27 ferramentas
(um `get_item_details` por item) e as 8 rodadas acabaram antes do texto: a
resposta foi "Não consegui formular uma resposta após várias iterações."
📏 120 d: 1 de 31 conversas — esta.

🔑 Na ÚLTIMA rodada a ferramenta é proibida (`tool_choice: none`), e a API
obriga o modelo a responder em texto com o que já coletou.
Roda o `agent.ask` REAL com um modelo falso (o molde de
`test_o_chat_acha_o_item_pelas_palavras._rodar_ask`).
"""
import os
import sys
import types

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))


def _rodar(monkeypatch, responde_na_rodada=None):
    """Modelo falso: pede ferramenta sempre, a menos que a ferramenta esteja
    proibida (aí responde texto) ou seja a rodada `responde_na_rodada`."""
    import agent
    import llm_retry
    monkeypatch.setattr(agent, "_log_conversation", lambda *a, **k: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "teste-sem-rede")
    monkeypatch.setitem(sys.modules, "anthropic",
                        types.SimpleNamespace(Anthropic=lambda **kw: object()))
    monkeypatch.setattr(agent, "_dispatch_tool", lambda nome, job, inp: {"ok": True})
    chamadas = []

    def _falso(client, **kw):
        chamadas.append(kw)
        n = len(chamadas)
        proibida = kw.get("tool_choice") == {"type": "none"}
        if proibida or n == responde_na_rodada:
            txt = types.SimpleNamespace(type="text", text="Aqui estão os códigos que achei.")
            return types.SimpleNamespace(content=[txt], stop_reason="end_turn")
        uso = types.SimpleNamespace(type="tool_use", id="t%d" % n, name="get_item_details",
                                    input={"item_num": n})
        return types.SimpleNamespace(content=[uso], stop_reason="tool_use")

    monkeypatch.setattr(llm_retry, "call_with_retry", _falso)
    r = agent.ask("job01", "sim")
    return r, chamadas


def test_o_caso_na_ultima_rodada_ele_responde(monkeypatch):
    r, chamadas = _rodar(monkeypatch)
    assert "Não consegui formular" not in r["answer"], r["answer"]
    assert r["answer"] == "Aqui estão os códigos que achei.", r["answer"]
    assert len(chamadas) == 8, len(chamadas)
    # só a ÚLTIMA proíbe a ferramenta
    assert [("tool_choice" in c) for c in chamadas] == [False] * 7 + [True], chamadas


def test_CONTROLE_quem_responde_cedo_nunca_tem_a_ferramenta_proibida(monkeypatch):
    r, chamadas = _rodar(monkeypatch, responde_na_rodada=2)
    assert r["answer"] == "Aqui estão os códigos que achei."
    assert len(chamadas) == 2 and not any("tool_choice" in c for c in chamadas), chamadas
