# -*- coding: utf-8 -*-
"""A telemetria do prompt caching não pode derrubar uma extração.

🚨 24/08/2026: a Anthropic avisou de novo que o cache hit rate está baixo. O
caching foi ligado em 23/07 e conferido com DUAS chamadas manuais naquele dia —
e nunca mais foi medido. Não havia nada no backend lendo `response.usage`, então
não dava pra confirmar nem refutar o aviso pelo nosso lado.

Este arquivo guarda duas coisas: que a medição acontece, e que ela é INÓCUA —
telemetria que quebra o caminho da planilha é pior que telemetria nenhuma.
"""
import io
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from llm_retry import _registrar_uso  # noqa: E402


class _Uso:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class _Resp:
    def __init__(self, usage):
        self.usage = usage


def test_mede_e_nao_levanta(capsys):
    _registrar_uso("dxf:teste", _Resp(_Uso(
        cache_read_input_tokens=4800, cache_creation_input_tokens=0,
        input_tokens=95000, output_tokens=3000)), True)
    saida = capsys.readouterr().out
    assert "cache_read=4800" in saida
    assert "total_in=99800" in saida
    assert "4.8%" in saida, (
        "a porcentagem é o número que interessa — é ela que responde ao e-mail "
        "da Anthropic. Saiu: " + saida)


def test_resposta_sem_usage_nao_quebra():
    """Alguns caminhos devolvem objeto sem `usage`. Não pode explodir."""
    _registrar_uso("x", _Resp(None), True)
    _registrar_uso("x", object(), True)
    _registrar_uso("x", None, False)


def test_campos_ausentes_ou_lixo_nao_quebram():
    _registrar_uso("x", _Resp(_Uso()), True)
    _registrar_uso("x", _Resp(_Uso(cache_read_input_tokens=None,
                                   input_tokens="abc")), True)


def test_tudo_zero_nao_loga_divisao_por_zero(capsys):
    _registrar_uso("x", _Resp(_Uso(cache_read_input_tokens=0,
                                   cache_creation_input_tokens=0,
                                   input_tokens=0)), True)
    assert "llm_cache" not in capsys.readouterr().out


def test_kill_switch(capsys, monkeypatch):
    """Telemetria tem que ter como ser desligada sem deploy."""
    monkeypatch.setenv("LLM_CACHE_TELEMETRIA", "0")
    _registrar_uso("x", _Resp(_Uso(cache_read_input_tokens=10,
                                   input_tokens=10)), True)
    assert capsys.readouterr().out == ""


def test_os_dois_wrappers_medem():
    src = io.open(os.path.join(_BACKEND, "llm_retry.py"), encoding="utf-8").read()
    assert src.count("_registrar_uso(tag, _resp, cache_system)") == 2, (
        "os DOIS wrappers (create e stream) precisam medir — a extração de "
        "prancha usa o stream, e é ela que domina o gasto")


def test_o_log_nao_entope_o_painel_de_erros():
    """🪤 Uma linha por chamada de IA. Ontem o painel 'Erros do motor' tinha 20
    das 40 linhas ocupadas por bookkeeping; isto aqui repetiria o problema."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("_STAGES_DIAGNOSTICO = frozenset({")
    bloco = src[i:src.index("})", i)]
    assert '"llm:cache"' in bloco, (
        "o stage llm:cache não está na lista de diagnóstico — vai empurrar erro "
        "de verdade pra fora do painel")
