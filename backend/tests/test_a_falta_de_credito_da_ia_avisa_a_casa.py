# -*- coding: utf-8 -*-
"""Crédito da IA acabou: a CASA recebe um aviso urgente; o cliente nunca lê "crédito".

🩸 Junho/2026: a Anthropic respondeu "Your credit balance is too low" e o cliente
leu na tela "provável sobrecarga temporária… Detalhe técnico: Error code: 400 …
credit balance is too low" — em inglês, e errado. Até 25/09 o mesmo erro virava
"problema técnico do nosso lado, reprocesse" na tela, "troque o arquivo, é PDF
escaneado" no e-mail, e um "Projeto com erro terminal" POR PROJETO pro Pedro —
sem nada dizendo que era uma causa só e que parava tudo.
Pedro, 25/09: "crédito de IA esgotado é algo interno nosso, não faz sentido
nenhum a gente avisar isso para o cliente".
"""
import ast
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import llm_retry  # noqa: E402

MSG_REAL = ("Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
            "'message': 'Your credit balance is too low to access the Anthropic API. Please "
            "go to Plans & Billing to upgrade or purchase credits.'}}")


@pytest.mark.parametrize("texto", [MSG_REAL, "BadRequestError: " + MSG_REAL,
                                   "credit balance is too low"])
def test_reconhece_a_falta_de_credito(texto):
    assert llm_retry.e_falta_de_credito(texto)


@pytest.mark.parametrize("texto", [
    "Error code: 529 - overloaded_error",
    "RateLimitError: rate_limit_error",
    "Error code: 400 - invalid_request_error: invalid high surrogate",
    "httpx.RemoteProtocolError: peer closed connection",
    "",
])
def test_CONTROLE_outros_erros_nao_sao_falta_de_credito(texto):
    assert not llm_retry.e_falta_de_credito(texto)


class _Cliente:
    def __init__(self, erro):
        self._erro = erro

        class _M:
            def create(_s, **k):
                raise self._erro
        self.messages = _M()


def test_a_chamada_recusada_aciona_o_gancho_e_o_erro_continua_subindo(monkeypatch):
    vistos = []
    monkeypatch.setattr(llm_retry, "ao_faltar_credito",
                        lambda d, t, j: vistos.append((d, t, j)))
    monkeypatch.setattr(llm_retry, "_gravar_uso", lambda **k: None)
    with pytest.raises(Exception) as e:
        llm_retry.call_with_retry(_Cliente(Exception(MSG_REAL)), max_retries=0,
                                  tag="prancha", job_id="abc12345", model="m",
                                  messages=[], max_tokens=1)
    assert "credit balance" in str(e.value), "o erro original tem que continuar subindo"
    assert len(vistos) == 1 and vistos[0][1] == "prancha" and vistos[0][2] == "abc12345"


def test_CONTROLE_outro_400_nao_aciona_o_gancho(monkeypatch):
    vistos = []
    monkeypatch.setattr(llm_retry, "ao_faltar_credito",
                        lambda d, t, j: vistos.append((d, t, j)))
    monkeypatch.setattr(llm_retry, "_gravar_uso", lambda **k: None)
    with pytest.raises(Exception):
        llm_retry.call_with_retry(_Cliente(Exception("Error code: 400 - invalid_request_error: bad")),
                                  max_retries=0, tag="prancha", model="m", messages=[], max_tokens=1)
    assert vistos == []


def test_gancho_que_quebra_nao_troca_o_erro(monkeypatch):
    def _quebra(*a):
        raise RuntimeError("smtp fora")
    monkeypatch.setattr(llm_retry, "ao_faltar_credito", _quebra)
    monkeypatch.setattr(llm_retry, "_gravar_uso", lambda **k: None)
    with pytest.raises(Exception) as e:
        llm_retry.call_with_retry(_Cliente(Exception(MSG_REAL)), max_retries=0, tag="x",
                                  model="m", messages=[], max_tokens=1)
    assert "credit balance" in str(e.value)


# ── o aviso da casa ───────────────────────────────────────────────────────────
@pytest.fixture
def m(monkeypatch):
    import main
    enviados, registrados, logs = [], [], []
    monkeypatch.setattr(main, "_SEM_CREDITO_ULTIMO", [None])
    monkeypatch.setattr(main, "_email_auto_ja_enviado", lambda *a, **k: False)
    monkeypatch.setattr(main, "_notify_admin",
                        lambda assunto, corpo: enviados.append((assunto, corpo)) or True)
    monkeypatch.setattr(main, "_email_auto_registrar", lambda *a, **k: registrados.append((a, k)))
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: logs.append((a, k)))
    monkeypatch.setattr(main, "_supa_rest_service",
                        lambda *a, **k: (200, [{"job_id": "aaa11111"}, {"job_id": "bbb22222"}]))
    main._t_env = (enviados, registrados, logs)
    return main


def test_o_gancho_do_llm_retry_e_o_aviso_da_casa(m):
    assert llm_retry.ao_faltar_credito is m._alerta_sem_credito_ia


def test_o_aviso_diz_o_que_fazer_e_quais_projetos_pararam(m):
    enviados, registrados, logs = m._t_env
    assert m._alerta_sem_credito_ia(MSG_REAL, "prancha", "ccc33333") is True
    assunto, corpo = enviados[0]
    assert "crédito" in assunto.lower() and "urgente" in assunto.lower()
    assert "Recarregar" in corpo and "Reprocessar" in corpo
    for j in ("aaa11111", "bbb22222", "ccc33333"):
        assert j in corpo, j
    assert registrados and registrados[0][0][1] == "alerta_sem_credito_ia"
    assert any(a[0] == "ia:sem-credito" and k.get("severity") == "critical" for a, k in logs)


def test_um_aviso_por_incidente_nao_um_por_projeto(m):
    enviados, _, _ = m._t_env
    assert m._alerta_sem_credito_ia(MSG_REAL, "prancha", "a1") is True
    assert m._alerta_sem_credito_ia(MSG_REAL, "prancha", "a2") is False
    assert m._alerta_sem_credito_ia(MSG_REAL, "dxf", "a3") is False
    assert len(enviados) == 1


def test_CONTROLE_ja_avisado_nesta_hora_por_outro_processo_nao_repete(m, monkeypatch):
    enviados, _, _ = m._t_env
    monkeypatch.setattr(m, "_email_auto_ja_enviado", lambda *a, **k: True)
    assert m._alerta_sem_credito_ia(MSG_REAL, "prancha", "a1") is False
    assert enviados == []


def test_o_fim_do_job_tambem_avisa():
    """A chamada à IA pode ter rodado fora deste processo (sem gancho): o ramo
    que monta a falha do projeto chama o aviso ele mesmo."""
    fonte = open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8").read()
    fn = next(n for n in ast.walk(ast.parse(fonte))
              if isinstance(n, ast.FunctionDef) and n.name == "process_job")
    chamadas = [c for c in ast.walk(fn) if isinstance(c, ast.Call)
                and getattr(c.func, "id", "") == "_alerta_sem_credito_ia"]
    assert chamadas, "o fim do job não chama o aviso de crédito"
    assert any(isinstance(a, ast.Constant) and a.value == "fim-do-job" for c in chamadas for a in c.args)


class _ClienteStream:
    """A leitura de prancha usa `messages.stream` — o outro caminho do llm_retry."""
    def __init__(self, erro):
        self._erro = erro

        class _M:
            def stream(_s, **k):
                raise self._erro
        self.messages = _M()


def test_o_caminho_em_streaming_tambem_aciona_o_gancho(monkeypatch):
    vistos = []
    monkeypatch.setattr(llm_retry, "ao_faltar_credito",
                        lambda d, t, j: vistos.append((d, t, j)))
    monkeypatch.setattr(llm_retry, "_gravar_uso", lambda **k: None)
    with pytest.raises(Exception):
        llm_retry.call_with_retry_stream(_ClienteStream(Exception(MSG_REAL)), max_retries=0,
                                         tag="analyzer:p.pdf", job_id="abc12345", model="m",
                                         messages=[], max_tokens=1)
    assert len(vistos) == 1 and vistos[0][2] == "abc12345"
