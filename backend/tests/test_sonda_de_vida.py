# -*- coding: utf-8 -*-
"""A sonda de vida do Render não pode depender de terceiro.

🔎 26/08/2026, primeira leitura do Render pelo conector. O serviço está com
`healthCheckPath` **VAZIO**: a plataforma não tem como saber se o processo
travou, e o deploy troca a instância sem esperar o app subir. E o log já
mostrava `GET /health → 404 Not Found` repetido — alguma coisa sonda esse
caminho e leva 404 desde sempre.

🚨 A armadilha que este guarda protege: usar o `/api/health` como sonda. Ele
consulta o Supabase (`projects?select=id&created_at=gte...`) pra contar
projetos do dia. Se o Supabase oscilar e essa rota falhar, o Render entra em
**laço de restart** — e um problema de terceiro vira queda nossa, derrubando
todo job em andamento.

🔑 Sonda de vida responde UMA pergunta: "o processo está de pé?". Quem quiser
diagnóstico usa `/api/health`.

📌 Contexto de por que restart importa aqui: em 26/08 a instância reiniciou por
memória às 10:19 e matou os dois jobs da cliente-16 no meio
([[test_envio_em_dobro]]). Restart não é evento inofensivo neste produto.
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()

import main as M  # noqa: E402


def _corpo_da_sonda():
    i = _FONTE.find('@app.get("/health")')
    assert i > 0, "a sonda de vida /health não existe"
    fim = _FONTE.find("@app.", i + 10)
    return _FONTE[i:fim if fim > i else i + 2000]


def _cliente():
    """Fala com o app pelo MESMO caminho do Render: uma requisicao HTTP.

    SEM `with`: o context manager dispara os eventos de startup, que tocam
    banco. Quem sonda o Render nao roda startup nenhum.
    """
    from fastapi.testclient import TestClient
    return TestClient(M.app, raise_server_exceptions=False)


def test_a_sonda_existe():
    """EXECUTA a sonda pelo caminho do Render: um GET /health."""
    r = _cliente().get("/health")
    assert r.status_code == 200, (
        "GET /health respondeu %s — e este 404 que enche o log do Render e "
        "deixa a plataforma sem saber se o processo travou" % r.status_code)
    assert r.json() == {"ok": True}, r.text


def _minar_todas_as_saidas(monkeypatch):
    """Mina TODA porta que sai do processo — e devolve a lista de pisadas.

    🪤 07/09/2026 — a versão anterior deste campo minado era uma LISTA FIXA de
    11 portas (urlopen, socket.create_connection, subprocess.Popen,
    psutil.virtual_memory e 7 helpers `_supa_*` escritos à mão). `requests` e
    `httpx` estão instalados no projeto e passavam batido; um helper `_supa_*`
    novo nasceria fora da lista. Agora:

      · a rede é minada EMBAIXO de todas as bibliotecas (`socket.socket.connect`
        e o DNS), além de cada biblioteca por cima;
      · os helpers de banco são varridos por PREFIXO no módulo, não listados;
      · disco (`open`), relógio (`sleep`) e leitura de processo (`psutil`)
        entram, porque custo também derruba sonda.
    """
    import builtins
    import http.client
    import io as _io
    import socket
    import subprocess
    import time
    import urllib.request

    pisadas = []

    def _mina(nome):
        def _explode(*a, **k):
            pisadas.append(nome)
            raise AssertionError("a sonda de vida tocou em %s" % nome)
        return _explode

    def _armar(obj, attr, nome):
        if obj is not None and hasattr(obj, attr):
            monkeypatch.setattr(obj, attr, _mina(nome), raising=False)

    # ── rede: a camada de baixo (pega requests, httpx, urllib, supabase-py…)
    #    🪤 `socket.socket.connect` NÃO pode explodir sem olhar o destino: no
    #    Windows o próprio laço de eventos do asyncio abre um par de sockets em
    #    127.0.0.1 pra acordar a si mesmo. A mina deixa a volta local passar e
    #    só denuncia quem sai da máquina — que é o caso perigoso.
    _LOCAIS = ("127.0.0.1", "::1", "localhost", "0.0.0.0", "")

    def _mina_de_saida(orig, nome):
        def _talvez(self, endereco, *a, **k):
            destino = endereco[0] if isinstance(endereco, tuple) else endereco
            if str(destino) not in _LOCAIS:
                pisadas.append("%s -> %s" % (nome, destino))
                raise AssertionError("a sonda de vida abriu socket pra %s"
                                     % (destino,))
            return orig(self, endereco, *a, **k)
        return _talvez

    for _met in ("connect", "connect_ex"):
        monkeypatch.setattr(
            socket.socket, _met,
            _mina_de_saida(getattr(socket.socket, _met),
                           "socket.socket.%s" % _met))
    _armar(socket, "create_connection", "socket.create_connection")
    _armar(socket, "getaddrinfo", "DNS (socket.getaddrinfo)")
    _armar(socket, "gethostbyname", "DNS (socket.gethostbyname)")
    # ── rede: e cada biblioteca por cima, pra a mensagem dizer QUEM tentou
    _armar(urllib.request, "urlopen", "urllib.request.urlopen")
    _armar(http.client.HTTPConnection, "request", "http.client.HTTPConnection")
    # 🪤 `httpx.Client.send` NÃO pode ser minado: o TestClient do Starlette É um
    #    `httpx.Client` (com transporte ASGI em memória) — minar ali explode o
    #    próprio guarda, não a sonda. A porta certa é o transporte de REDE do
    #    httpx, que o TestClient nunca usa.
    for _mod, _cls, _met in (("requests", "Session", "request"),
                             ("requests", "api", "request"),
                             ("httpx", "HTTPTransport", "handle_request"),
                             ("httpx", "AsyncHTTPTransport", "handle_async_request")):
        try:
            _lib = __import__(_mod)
            _armar(getattr(_lib, _cls, None), _met, "%s.%s.%s" % (_mod, _cls, _met))
        except ImportError:
            pass
    # ── banco: TODO helper do main que fala com o Supabase, por prefixo
    for _nome in dir(M):
        if _nome.startswith("_supa"):
            _armar(M, _nome, "main.%s()" % _nome)
    # ── subprocesso, disco, relógio e leitura de processo: CUSTO
    _armar(subprocess, "Popen", "subprocess.Popen")
    _armar(subprocess, "run", "subprocess.run")
    _armar(os, "system", "os.system")
    _armar(builtins, "open", "open() em disco")
    _armar(_io, "open", "io.open() em disco")
    _armar(time, "sleep", "time.sleep")
    _armar(os, "statvfs", "os.statvfs")
    try:
        import psutil
        for _at in ("virtual_memory", "Process", "cpu_percent", "disk_usage"):
            _armar(psutil, _at, "psutil.%s" % _at)
    except ImportError:
        pass
    return pisadas


def test_a_sonda_NAO_toca_em_banco_nem_rede(monkeypatch):
    """🚨 O guarda que importa. Uma consulta aqui transforma oscilação do
    Supabase em laço de restart.

    🪤 A 1ª versão lia o FONTE e proibia substrings ("urllib", "requests"…).
    Um helper com outro nome, ou uma chamada indireta, passava verde. Agora a
    sonda roda com o campo minado ARMADO — se ela sair do processo por
    qualquer caminho, a mina registra QUEM foi.
    """
    cliente = _cliente()          # constrói ANTES de armar as minas
    pisadas = _minar_todas_as_saidas(monkeypatch)
    r = cliente.get("/health")
    assert pisadas == [], (
        "a sonda de vida saiu do processo por %s — se isso falhar, o Render "
        "reinicia o serviço em laço e derruba job de cliente no meio"
        % ", ".join(pisadas))
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}, r.text


def test_a_sonda_e_TRIVIAL(monkeypatch):
    """A sonda tem que ser BARATA, não só limpa: ela responde a cada 30 s e é
    ela que decide se o Render mata a instância.

    🪤 07/09/2026 — a versão anterior dizia medir CUSTO e media uma lista de
    nomes proibidos. Custo por qualquer outra porta (`psutil.Process`, `open()`,
    `time.sleep`, DNS) passava batido contanto que a resposta continuasse
    `{"ok": True}` — e sonda que se auto-derruba sob pressão é a doença
    inteira de volta (o restart de 26/08 10:19 matou os dois jobs da
    cliente-16). Agora o guarda cobra TEMPO, medido.
    """
    import time as _t
    cliente = _cliente()
    cliente.get("/health")        # aquece import/rota, fora da medição
    pisadas = _minar_todas_as_saidas(monkeypatch)

    tempos = []
    for _ in range(10):
        _t0 = _t.perf_counter()
        r = cliente.get("/health")
        tempos.append((_t.perf_counter() - _t0) * 1000.0)
        assert r.status_code == 200 and r.json() == {"ok": True}, r.text
    assert pisadas == [], "a sonda pagou por %s" % ", ".join(pisadas)

    melhor = min(tempos)
    # 🪤 Teto FROUXO de propósito: máquina de bancada tem ruído, e o guarda não
    # pode ficar vermelho por isso. Qualquer coisa que consulte banco, leia
    # /proc ou durma passa MUITO disso — é esse o defeito que ele pega.
    assert melhor < 50.0, (
        "a sonda mais rápida de 10 levou %.1f ms — ela responde a cada 30 s e "
        "decide se o Render mata a instância; alguém pôs trabalho dentro dela"
        % melhor)


def test_a_sonda_e_UMA_INSTRUCAO():
    """Poucas INSTRUÇÕES de verdade. Se crescer, alguém pôs lógica nela.

    🪤 A 1ª versão deste teste contava LINHAS de texto e reprovava por causa da
    própria docstring — comentário não é código. Contar com o parser do Python
    mede o que importa.
    """
    import ast
    arvore = ast.parse(_FONTE)
    alvo = None
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and no.name == "liveness":
            alvo = no
            break
    assert alvo is not None, "não achei a função da sonda"
    corpo = [n for n in alvo.body
             if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                     and isinstance(n.value.value, str))]   # tira a docstring
    # 🪤 Era `<= 2`, o que deixava passar um `import` antes do return — e foi
    # exatamente assim que a sabotagem escapou. Sonda de vida é UMA instrução.
    assert len(corpo) == 1, (
        "a sonda tem %d instruções — sonda de vida é UM return, mais nada"
        % len(corpo))
    assert isinstance(corpo[-1], ast.Return), "a sonda não devolve nada"


def test_o_api_health_CONTINUA_rico():
    """A sonda não substitui o diagnóstico — os dois têm papéis diferentes.
    Se alguém 'simplificar' o /api/health achando que virou redundante, a gente
    perde a leitura de memória que resolveu o caso da cliente-16 hoje."""
    i = _FONTE.find('@app.get("/api/health")')
    assert i > 0, "o /api/health sumiu"
    trecho = _FONTE[i:i + 2500]
    assert "psutil" in trecho, (
        "o /api/health perdeu a métrica de memória — foi ela que explicou o "
        "restart de 10:19")


def test_as_DUAS_rotas_sao_distintas():
    """🪤 Nome parecido, papel oposto. Se virarem a mesma coisa, ou a sonda
    fica pesada ou o diagnóstico fica pobre."""
    assert _FONTE.count('@app.get("/health")') == 1
    assert _FONTE.count('@app.get("/api/health")') == 1
    i_sonda = _FONTE.find('@app.get("/health")')
    i_diag = _FONTE.find('@app.get("/api/health")')
    assert i_sonda != i_diag


def test_a_sonda_responde_de_verdade():
    """Controle positivo: chama a função e confere a resposta."""
    import asyncio
    import main as M
    r = asyncio.get_event_loop().run_until_complete(M.liveness()) \
        if not asyncio.iscoroutinefunction(M.liveness) else \
        asyncio.new_event_loop().run_until_complete(M.liveness())
    assert isinstance(r, dict) and r.get("ok") is True, r
