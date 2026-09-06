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
import io
import os
import re

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
_AGENT = io.open(os.path.join(_BACKEND, "agent.py"), encoding="utf-8").read()


def _corpo_da_rota_do_chat():
    """O corpo da rota /api/agent/ask, do decorador até a próxima rota."""
    i = _FONTE.index('@app.post("/api/agent/ask")')
    j = _FONTE.index("@app.", i + 10)
    return _FONTE[i:j]


def test_a_rota_do_chat_NAO_chama_o_agente_no_laco_de_eventos():
    """🩸 O que derrubou o site às 15:07 de 03/09."""
    corpo = _corpo_da_rota_do_chat()
    assert "run_in_threadpool" in corpo, (
        "a rota do chat voltou a rodar o agente no laço de eventos — com "
        "--workers 1 isso congela o site inteiro enquanto o agente pensa, e o "
        "health check de 5 s do Render mata a instância")
    # e a chamada crua não pode voltar
    assert not re.search(r"^\s*result = ask\(", corpo, re.M), (
        "voltou a chamada síncrona direta `result = ask(...)`")


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
