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
import os
import re
import sys
import threading
import time as _timeb

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
_AGENT = io.open(os.path.join(_BACKEND, "agent.py"), encoding="utf-8").read()

import main as M  # noqa: E402


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


def test_a_rota_do_chat_NAO_chama_o_agente_no_laco_de_eventos(monkeypatch):
    """🩸 O que derrubou o site às 15:07 de 03/09.

    🪤 05/09/2026: a versão anterior deste guarda lia `run_in_threadpool` no
    TEXTO da rota e ficou verde com um `_NO_THREADPOOL = True` guardando o ramo
    morto e o agente rodando de novo dentro do laço de eventos — o bug inteiro
    de volta, com a string que o assert procurava ainda escrita ali.

    Agora a rota RODA, com um `agent.ask` síncrono que demora, e o guarda mede
    duas coisas: em que thread ele rodou, e se o laço continuou atendendo
    enquanto isso.
    """
    import agent as _agente

    monkeypatch.setattr(M, "_require_project_owner",
                        lambda request, job_id: {"id": "u-cliente-11"})

    visto = {}

    def _ask_lento(job_id, question, max_iterations=8, history=None):
        visto["thread"] = threading.get_ident()
        visto["job_id"] = job_id
        visto["question"] = question
        _timeb.sleep(0.4)          # o agente "pensando" (8 iterações, DXF etc.)
        return {"answer": "o forro sai 26,54 m2", "iterations": 1}
    monkeypatch.setattr(_agente, "ask", _ask_lento)

    async def _cenario():
        visto["laco"] = threading.get_ident()
        tarefa = asyncio.ensure_future(
            M.agent_ask(_RequisicaoFalsa(), job_id="job-11",
                        question="quanto de forro?"))
        batidas = 0
        while not tarefa.done():
            await asyncio.sleep(0.01)
            batidas += 1
        return await tarefa, batidas

    resp, batidas = asyncio.run(_cenario())

    assert resp["status"] == "ok" and resp["answer"], (
        "a rota parou de responder o agente: %r" % (resp,))
    assert visto.get("job_id") == "job-11" and visto.get("question") == "quanto de forro?", (
        "os argumentos do agente voltaram a ir por posição (ou trocados): %r" % (visto,))
    assert visto["thread"] != visto["laco"], (
        "o agente rodou DENTRO do laço de eventos — com --workers 1 isso "
        "congela o site inteiro enquanto ele pensa, e o health check de 5 s do "
        "Render mata a instância (foi o incidente de 03/09)")
    assert batidas >= 3, (
        "o laço de eventos ficou parado enquanto o agente pensava (%d batidas) "
        "— é exatamente o bloqueio que zerou o instance_count" % batidas)


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
