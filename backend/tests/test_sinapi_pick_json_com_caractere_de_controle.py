# -*- coding: utf-8 -*-
"""Um caractere de controle na resposta da IA não pode derrubar o LOTE inteiro.

🩸 27/09/2026 — na medição local do conserto 976b567, 1 de 32 respostas da
Haiku trouxe um caractere de controle cru dentro de uma string do JSON. O
`json.loads` estrito levantou "Invalid control character", o `except` do lote
imprimiu "[sinapi-pick] lote falhou (segue sem IA)" e os 12 itens do lote
ficaram sem a escolha da IA — caíram no corte por nota de similaridade, que é
justamente o que a IA existe pra corrigir.

Alcance medido em produção antes do conserto (logs do Render, que guardam 7
dias: 20/09 11h50 → 27/09): 1 lote perdido em 693 chamadas `sinapi_pick` de 53
projetos, e por OUTRO motivo ("Extra data"). Caractere de controle: 0. O
conserto é de prevenção — o formato já apareceu com a IA de verdade.

Roda a FUNÇÃO REAL (`pick_best_batch` + `call_with_retry`); só a API é dublada.
"""
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import llm_retry  # noqa: E402
import sinapi_matcher  # noqa: E402


class _Bloco:
    def __init__(self, texto):
        self.text = texto
        self.type = "text"


class _Resposta:
    def __init__(self, texto):
        self.content = [_Bloco(texto)]
        self.stop_reason = "end_turn"
        self.usage = None
        self.model = "claude-haiku-4-5-20251001"


class _ClienteFalso:
    def __init__(self, texto):
        self.messages = self
        self._texto = texto

    # 🪤 `**k` de propósito: parâmetro novo no call site não pode desarmar o
    # guarda em silêncio (feedback_duble_com_assinatura_exata_desarma_calado).
    def create(self, **k):
        return _Resposta(self._texto)


def _escolhas(monkeypatch, resposta_da_ia):
    monkeypatch.setenv("LLM_CACHE_TELEMETRIA", "0")
    monkeypatch.setattr(llm_retry, "_gravar_uso", lambda **k: None)
    monkeypatch.setattr(sinapi_matcher, "_client", lambda: _ClienteFalso(resposta_da_ia))
    itens = [{"description": "Porta de madeira 80x210 com fechadura", "unit": "un",
              "candidates": [{"codigo": "91314", "descricao": "KIT DE PORTA", "unidade": "UN"},
                             {"codigo": "91320", "descricao": "KIT DE PORTA", "unidade": "UN"}]},
             {"description": "Porta corta-fogo 80x210", "unit": "un",
              "candidates": [{"codigo": "106139", "descricao": "PORTA CORTA-FOGO", "unidade": "UN"}]}]
    return sinapi_matcher.pick_best_batch(itens, job_id="teste")


@pytest.mark.parametrize("controle", ["\t", "\n", "\r"], ids=["tab", "quebra-de-linha", "retorno"])
def test_caractere_de_controle_dentro_da_string_nao_derruba_o_lote(monkeypatch, controle):
    resposta = ('[{"i": 0, "codigo": "91314", "nota": "kit%scom fechadura"},\n'
                ' {"i": 1, "codigo": null}]' % controle)
    assert controle in resposta, "o teste perdeu o caractere de controle"
    assert _escolhas(monkeypatch, resposta) == {0: "91314", 1: None}, (
        "a resposta tem um caractere de controle cru dentro de uma string e o "
        "lote inteiro caiu — os itens ficam sem a escolha da IA")


def test_CONTROLE_codigo_fora_da_mesa_continua_barrado(monkeypatch):
    """Aceitar caractere de controle não pode afrouxar a blindagem: código que
    não estava entre os candidatos DAQUELE item continua virando None."""
    resposta = '[{"i": 0, "codigo": "99999", "nota": "inventado\tpela IA"}]'
    assert _escolhas(monkeypatch, resposta) == {0: None}
