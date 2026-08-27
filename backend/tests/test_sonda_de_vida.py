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
memória às 10:19 e matou os dois jobs da Amanda no meio
([[test_envio_em_dobro]]). Restart não é evento inofensivo neste produto.
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _corpo_da_sonda():
    i = _FONTE.find('@app.get("/health")')
    assert i > 0, "a sonda de vida /health não existe"
    fim = _FONTE.find("@app.", i + 10)
    return _FONTE[i:fim if fim > i else i + 2000]


def test_a_sonda_existe():
    assert '@app.get("/health")' in _FONTE, (
        "sem /health o Render não tem o que sondar — e o 404 volta pro log")


def test_a_sonda_NAO_toca_em_banco_nem_rede():
    """🚨 O guarda que importa. Uma consulta aqui transforma oscilação do
    Supabase em laço de restart."""
    corpo = _corpo_da_sonda()
    # 🪤 A 1ª lista tinha "urlopen" mas não "urllib": sabotei a sonda com um
    # `import urllib.request` e a bateria passou VERDE. Guarda que não reprova
    # não é guarda.
    proibido = ("SUPABASE", "urllib", "urlopen", "requests", "httpx", "psutil",
                "socket", "_supa_rest", "execute_sql", "open(", "subprocess",
                "import ")
    for termo in proibido:
        assert termo not in corpo, (
            "a sonda de vida passou a usar %r — se isso falhar, o Render "
            "reinicia o serviço em laço e derruba job de cliente no meio"
            % termo)


def test_a_sonda_e_TRIVIAL():
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
    perde a leitura de memória que resolveu o caso da Amanda hoje."""
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
