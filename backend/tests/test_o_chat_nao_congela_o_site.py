# -*- coding: utf-8 -*-
"""Uma pergunta no chat derrubava o site pra todos os clientes.

🩸 03/09/2026, 15:07 BRT. O cliente `cliente-11@` (job `eebe543a`) mandou uma
pergunta no chat do projeto. Medido no Render:

    15:07:30 → 15:09:00   instance_count = 0     ← o site FORA do ar
    e-mail do Render: "HTTP health check failed (timed out after 5 seconds)"

**NÃO foi memória.** O pico do container no episódio inteiro foi 906 MB — 22%
dos 4 GiB. Foi BLOQUEIO.

🔑 `agent.ask` é SÍNCRONA: até 8 iterações seguidas de chamada ao modelo, cada
uma executando tools que leem DXF. Ela estava sendo chamada direto de dentro de
um `async def`, ou seja, **no laço de eventos**. Com `--workers 1` (obrigatório
aqui, ver [[project_oom_multidxf_20260722]]) isso congela o processo inteiro
enquanto o agente pensa: o health check de 5 s morre e o Render mata a
instância. Qualquer cliente perguntando no chat derrubava o site para todos.

🪤 Mesma doença de 28/08 (o relógio congelando o site), que foi consertada em 61
rotas — esta ficou de fora. Provavelmente porque a varredura procurou I/O óbvio
(`urllib`, `requests`) e aqui o bloqueio está escondido atrás de um
`from agent import ask`. Bloqueio não se acha procurando o NOME da biblioteca;
se acha procurando função síncrona chamada de rota assíncrona.
"""
import asyncio
import io
import json as _json
import os
import re
import sys
import threading
import time as _timeb

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
_AGENT = io.open(os.path.join(_BACKEND, "agent.py"), encoding="utf-8").read()

import agent  # noqa: E402
import main  # noqa: E402
import main as M  # noqa: E402
import time  # noqa: E402


class _Req:
    def __init__(self, corpo=b""):
        self._corpo = corpo
        self.state = type("_S", (), {})()

    async def body(self):
        return self._corpo


def _rodar_a_rota(monkeypatch, falso_ask, corpo=b"",
                  pergunta="  quantos m2 de piso?  ", job_id="job-cliente-11"):
    monkeypatch.setattr(main, "_require_project_owner", lambda *a, **k: "dono")
    monkeypatch.setattr(agent, "ask", falso_ask)
    medido = {"thread_do_laco": None, "tiques": 0, "tiques_durante": 0,
              "resposta": None}

    async def _cenario():
        medido["thread_do_laco"] = threading.get_ident()
        parar = threading.Event()

        async def _relogio():
            while not parar.is_set():
                medido["tiques"] += 1
                await asyncio.sleep(0.01)
        t = asyncio.create_task(_relogio())
        await asyncio.sleep(0.05)
        antes = medido["tiques"]
        medido["resposta"] = await main.agent_ask(_Req(corpo), job_id=job_id,
                                                  question=pergunta)
        medido["tiques_durante"] = medido["tiques"] - antes
        parar.set()
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
    asyncio.run(_cenario())
    return medido


class _RequisicaoFalsa:
    headers = {"user-agent": "bancada"}
    query_params = {}

    async def body(self):
        return b""


def _corpo_da_rota_do_chat():
    """O corpo da rota /api/agent/ask, do decorador até a próxima rota."""
    i = _FONTE.index('@app.post("/api/agent/ask")')
    j = _FONTE.index("@app.", i + 10)
    return _FONTE[i:j]


# 🪤 06/09/2026 — O FIXTURE SÓ MANDAVA CORPO VAZIO, E ESSE CORPO A PRODUÇÃO
# NUNCA MANDA. `dashboard.html` envia SEMPRE
# `body: JSON.stringify({ history: agentConversation })`. Na 1ª pergunta
# `agentConversation` é `[]` (falsy, `history` fica `[]`); da 2ª em diante tem
# 2+ turnos e `history` fica CHEIO — que é a maioria do tráfego do chat. Com o
# guarda testando só o corpo vazio, dava pra devolver o agente ao laço de
# eventos justamente no ramo que a produção mais usa (um `if history: ask(...)`)
# e ficar verde. Os três corpos abaixo cobrem os três estados reais.
_CORPO_SEM_BODY = b""
_CORPO_1A_PERGUNTA = _json.dumps({"history": []}).encode("utf-8")
_CORPO_CONVERSA = _json.dumps({"history": [
    {"role": "user", "content": "quantos m2 de piso?"},
    {"role": "assistant", "content": "120 m2 no layer PISO"},
    {"role": "user", "content": "e de rodape?"},
    {"role": "assistant", "content": "48 m"},
]}).encode("utf-8")


@pytest.mark.parametrize("rotulo,corpo,history_esperado", [
    ("sem corpo nenhum", _CORPO_SEM_BODY, None),
    ("1a pergunta (history=[])", _CORPO_1A_PERGUNTA, []),
    ("conversa em andamento (history com 4 turnos)", _CORPO_CONVERSA,
     _json.loads(_CORPO_CONVERSA.decode("utf-8"))["history"]),
])
def test_a_rota_do_chat_NAO_chama_o_agente_no_laco_de_eventos(
        monkeypatch, rotulo, corpo, history_esperado):
    """O agente tem que rodar em OUTRA thread, e o laco tem que continuar vivo.

    O agente falso aqui bloqueia 0,3 s - 6% do health check de 5 s do Render.
    Se ele rodar no laco, o relogio paralelo para de bater durante esse tempo,
    que e exatamente o que matou a instancia.

    Roda com os TRES corpos que a producao realmente manda - inclusive o de
    conversa em andamento, que e a maioria do trafego do chat.
    """
    visto = {}

    def _falso_ask(job_id, question, max_iterations=8, history=None):
        visto["thread"] = threading.get_ident()
        visto["history"] = history
        time.sleep(0.30)                    # o agente "pensando"
        return {"answer": "resposta do agente", "tool_calls": [], "iterations": 1}

    m = _rodar_a_rota(monkeypatch, _falso_ask, corpo=corpo)

    assert visto.get("thread") is not None, "o agente nem foi chamado (%s)" % rotulo
    assert visto["thread"] != m["thread_do_laco"], (
        "com o corpo '%s' o agente rodou NA THREAD DO LACO DE EVENTOS - com "
        "--workers 1 isso congela o site inteiro enquanto ele pensa, e o health "
        "check de 5 s do Render mata a instancia (episodio de 03/09, "
        "instance_count=0 por 90 s)" % rotulo)
    assert m["tiques_durante"] >= 5, (
        "com o corpo '%s' o laco de eventos bateu so %d vez(es) durante os "
        "0,30 s do agente - ele estava CONGELADO; com o threadpool batem ~30 "
        "tiques de 10 ms" % (rotulo, m["tiques_durante"]))
    assert visto["history"] == history_esperado, (
        "o historico que chegou ao agente com o corpo '%s' foi %r, esperado %r "
        "- tirar do laco nao pode custar o contexto da conversa"
        % (rotulo, visto["history"], history_esperado))
    assert m["resposta"]["answer"] == "resposta do agente", (
        "a rota nao devolveu a resposta do agente com o corpo '%s': %r"
        % (rotulo, m["resposta"]))


def test_o_corpo_que_a_producao_MANDA_e_o_que_a_bancada_testa():
    """🪤 Ancora o fixture na tela real: se `dashboard.html` parar de mandar
    `{history: ...}`, o parametrize acima vira ficcao e ninguem percebe."""
    _RAIZ = os.path.dirname(_BACKEND)
    dash = io.open(os.path.join(_RAIZ, "dashboard.html"), encoding="utf-8").read()
    i = dash.index("/api/agent/ask")
    trecho = dash[i:i + 900]
    assert "JSON.stringify({ history: agentConversation })" in trecho, (
        "a tela mudou o corpo que manda pro chat - o parametrize desta bancada "
        "precisa acompanhar, senao volta a testar um formato que nao existe")


def test_CONTROLE_o_agente_continua_SENDO_chamado():
    """Tirar do laço não pode virar 'não chama mais'."""
    corpo = _corpo_da_rota_do_chat()
    assert "from agent import ask" in corpo
    assert "ask," in corpo or "ask ," in corpo, (
        "o agente não é mais passado pro threadpool — a rota parou de responder")


def test_ask_continua_SINCRONA_que_e_o_motivo_do_threadpool():
    """Se `ask` virar `async def`, o threadpool passa a ser o errado.

    🪤 Este teste existe pra que a mudança lá do outro lado não deixe aqui um
    `run_in_threadpool` recebendo corrotina — que devolve a corrotina sem
    executar, e a rota passa a responder um objeto em vez da resposta.
    """
    assert re.search(r"^def ask\(", _AGENT, re.M), (
        "`agent.ask` virou assíncrona: o `run_in_threadpool` da rota do chat "
        "precisa virar `await ask(...)` no mesmo commit")
    assert not re.search(r"^async def ask\(", _AGENT, re.M)


def test_os_argumentos_vao_por_NOME():
    """`ask` tem `max_iterations` no meio da assinatura.

    Passar posicional fixaria o default na rota, e mexer na assinatura do
    agente quebraria isto de um jeito silencioso — o pior tipo.
    """
    corpo = _corpo_da_rota_do_chat()
    assert "job_id=job_id" in corpo and "question=question.strip()" in corpo, (
        "os argumentos do agente voltaram a ir por posição")


def test_a_assinatura_do_agente_e_a_que_a_rota_supoe():
    """Guarda de contrato: a rota passa job_id, question e history por nome."""
    import inspect

    import agent
    params = list(inspect.signature(agent.ask).parameters)
    for nome in ("job_id", "question", "history"):
        assert nome in params, (
            "a rota do chat passa `%s=` e `agent.ask` não tem mais esse "
            "parâmetro" % nome)
