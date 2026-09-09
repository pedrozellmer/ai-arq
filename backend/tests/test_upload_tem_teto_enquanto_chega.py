# -*- coding: utf-8 -*-
"""O teto do upload tem que agir ENQUANTO os bytes chegam, não depois.

🚨 08/09/2026, auditoria de segurança (44 agentes, com céticos). Três coisas
medidas, e as três corrigem o que eu achava:

1. 🩸 A trava de 450 MB roda TARDE DEMAIS. Ela está no CORPO da rota, e o
   FastAPI faz `body = await request.form()` ANTES (`routing.py:406`). Quando o
   `413` executa, o multipart inteiro já foi lido do socket.

2. 🩸 E FALHA ABERTA sem `Content-Length` (`if _clen and ...`). Não é exótico: o
   Starlette **nunca lê `Content-Length` de request**. 📏 Medido contra a
   produção com corpo minúsculo: chunked sem o header → **200 OK**.

3. 🪤 O estrago barato é RAM, não disco — o oposto do que eu procurava.
   `SpooledTemporaryFile(max_size=1MB)`: arquivo abaixo de 1 MB **nunca vai pro
   disco**. Com `max_files=1000`, 1000 partes de ~1 MB prendem ~1 GB de RAM, e
   cada uma passa folgada pelo teto de 150 MB POR ARQUIVO. 4 GB e `--workers 1`
   → OOM pra todos, o modo de falha de 21/07.

🪤 E EU ERREI DUAS VEZES antes de medir: disse que NENHUMA rota tinha teto por
arquivo (duas têm, 150 MB — tardio, mas real) e que o Cloudflare protegia
(`aiarq-utils.js:41` manda estas três rotas DIRETO pro Render, fora do proxy,
porque o CF Free corta em 100 MB).
"""
import asyncio
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from upload_teto import (  # noqa: E402
    Contador, TetoDeCorpo, vigiado, TETO_PADRAO, CAMINHOS_DE_UPLOAD)


# ══════════════════════════════════════════════════════════════════════════
#  A decisão pura
# ══════════════════════════════════════════════════════════════════════════
def test_o_contador_soma_e_avisa_no_estouro():
    c = Contador(10)
    assert c.somar(4) is False
    assert c.somar(4) is False
    assert c.somar(4) is True          # 12 > 10
    assert c.total == 12


def test_CONTROLE_o_contador_NAO_avisa_abaixo_do_teto():
    """🧪 Sem isto, um contador que devolvesse True sempre passaria no teste
    acima e barraria todo upload legítimo."""
    c = Contador(10)
    for _ in range(10):
        assert c.somar(1) is False     # exatamente 10, nunca passa
    assert c.total == 10


def test_o_teto_e_do_TOTAL_e_nao_de_cada_pedaco():
    """🔑 É isto que fecha o caminho da RAM: mil partes de 1 MB, cada uma
    inocente sozinha, somam o mesmo que um arquivo enorme."""
    c = Contador(100)
    estourou = any(c.somar(1) for _ in range(1000))
    assert estourou, "mil pedaços pequenos passaram batidos — é o caso do OOM"


@pytest.mark.parametrize("metodo,caminho,esperado", [
    ("POST", "/api/process", True),
    ("POST", "/api/estimate-price", True),
    ("POST", "/api/project/abc123/add-file", True),
    ("GET", "/api/process", False),          # só POST carrega corpo
    ("POST", "/api/health", False),
    ("POST", "/api/projects/x/client", False),
    ("POST", "", False),
    ("POST", None, False),
    (None, "/api/process", False),
])
def test_vigia_so_as_rotas_de_upload(metodo, caminho, esperado):
    assert vigiado(metodo, caminho) is esperado


def test_as_TRES_rotas_de_upload_estao_cobertas():
    """🪤 As três são exatamente as que `aiarq-utils.js` manda DIRETO pro
    Render, fora do Cloudflare. Se alguém acrescentar uma quarta lá e esquecer
    aqui, ela nasce sem teto — e sem proxy na frente."""
    for esperada in ("/api/process", "/add-file", "/api/estimate-price"):
        assert esperada in CAMINHOS_DE_UPLOAD


def test_o_teto_padrao_e_o_mesmo_que_o_sistema_ja_promete():
    """🔑 Não é teto novo: é o que as rotas já documentam passando a valer de
    verdade. Se este número divergir dos 450 MB do resto, o cliente lê uma
    promessa e recebe outra."""
    assert TETO_PADRAO == 450 * 1024 * 1024


# ══════════════════════════════════════════════════════════════════════════
#  O middleware, exercitado como ASGI de verdade — sem servidor, sem rede
# ══════════════════════════════════════════════════════════════════════════
def _corpo_em_pedacos(pedacos):
    """Fila de mensagens ASGI como o servidor entregaria."""
    fila = []
    for i, n in enumerate(pedacos):
        fila.append({"type": "http.request", "body": b"x" * n,
                     "more_body": i < len(pedacos) - 1})
    return fila


class _AppQueLe:
    """App de mentira que puxa o corpo inteiro, como o parser faz."""

    def __init__(self):
        self.lidos = 0
        self.chamado = False

    async def __call__(self, scope, receive, send):
        self.chamado = True
        while True:
            msg = await receive()
            if msg.get("type") != "http.request":
                break
            self.lidos += len(msg.get("body") or b"")
            if not msg.get("more_body"):
                break


async def _rodar(mw, scope, fila):
    it = iter(fila)

    async def receive():
        try:
            return next(it)
        except StopIteration:
            return {"type": "http.disconnect"}

    async def send(_msg):
        pass

    await mw(scope, receive, send)


def test_ESTOURO_levanta_413_no_meio_da_chegada():
    """🧪 O controle positivo do middleware: o corte tem que acontecer ANTES de
    o app terminar de ler — é essa antecipação que é o conserto inteiro."""
    from fastapi import HTTPException
    alvo = _AppQueLe()
    mw = TetoDeCorpo(alvo, teto=10)
    scope = {"type": "http", "method": "POST", "path": "/api/estimate-price"}
    with pytest.raises(HTTPException) as e:
        asyncio.run(_rodar(mw, scope, _corpo_em_pedacos([4, 4, 4])))
    assert e.value.status_code == 413
    assert alvo.lidos < 12, (
        "o app leu o corpo inteiro (%d) — o teto agiu tarde, que é exatamente "
        "o defeito que este arquivo conserta" % alvo.lidos)


def test_o_corte_NAO_depende_de_content_length():
    """🔑 O ponto do conserto. O scope não tem header nenhum — é o caso do
    `chunked`, que hoje pula a trava antiga inteira."""
    from fastapi import HTTPException
    mw = TetoDeCorpo(_AppQueLe(), teto=10)
    scope = {"type": "http", "method": "POST", "path": "/api/process",
             "headers": []}          # sem content-length, de propósito
    with pytest.raises(HTTPException):
        asyncio.run(_rodar(mw, scope, _corpo_em_pedacos([6, 6])))


def test_MIL_PEDACOS_pequenos_sao_cortados():
    """🩸 O caminho da RAM: cada parte é inocente, o total é que mata."""
    from fastapi import HTTPException
    mw = TetoDeCorpo(_AppQueLe(), teto=100)
    scope = {"type": "http", "method": "POST", "path": "/api/estimate-price"}
    with pytest.raises(HTTPException):
        asyncio.run(_rodar(mw, scope, _corpo_em_pedacos([1] * 1000)))


def test_upload_LEGITIMO_passa_inteiro():
    """🧪 O outro lado do controle: uma trava que barra todo mundo 'passa' em
    todos os testes de estouro acima. Aqui ela tem que deixar passar."""
    alvo = _AppQueLe()
    mw = TetoDeCorpo(alvo, teto=1000)
    scope = {"type": "http", "method": "POST", "path": "/api/process"}
    asyncio.run(_rodar(mw, scope, _corpo_em_pedacos([100] * 9)))
    assert alvo.lidos == 900
    assert alvo.chamado


def test_rota_que_NAO_e_upload_passa_sem_contar():
    alvo = _AppQueLe()
    mw = TetoDeCorpo(alvo, teto=1)
    scope = {"type": "http", "method": "POST", "path": "/api/health"}
    asyncio.run(_rodar(mw, scope, _corpo_em_pedacos([50, 50])))
    assert alvo.lidos == 100, "contou uma rota que não recebe arquivo"


def test_websocket_e_lifespan_passam_intactos():
    alvo = _AppQueLe()
    mw = TetoDeCorpo(alvo, teto=1)
    asyncio.run(_rodar(mw, {"type": "lifespan"}, _corpo_em_pedacos([50])))
    assert alvo.chamado


def test_defeito_MEU_no_vigia_NAO_barra_o_cliente():
    """🔒 Falha ABERTA em defeito meu, e é decisão, não descuido.

    Esta trava contém abuso; ela não decide se um cliente pode trabalhar.
    Upload de cliente barrado por bug meu é pior que o abuso que ela previne.
    🪤 O estouro do teto, esse sim, fecha — o teste acima prova.
    """
    alvo = _AppQueLe()

    def _vigia_quebrado(_m, _c):
        raise RuntimeError("defeito meu")

    mw = TetoDeCorpo(alvo, teto=1, vigia=_vigia_quebrado)
    scope = {"type": "http", "method": "POST", "path": "/api/process"}
    asyncio.run(_rodar(mw, scope, _corpo_em_pedacos([50, 50])))
    assert alvo.lidos == 100, "um defeito meu barrou o upload do cliente"


# ══════════════════════════════════════════════════════════════════════════
#  A corrente INTEIRA: o 413 chega mesmo no cliente?
# ══════════════════════════════════════════════════════════════════════════
def _app_de_verdade(teto):
    """Um FastAPI real, com o middleware e uma rota que recebe arquivo.

    🔑 Por que este teste existe: todos os de cima exercitam o middleware com um
    app de mentira e provam que ele LEVANTA a exceção. Nenhum deles prova a
    parte que eu não controlo — que essa exceção, levantada lá dentro do
    `receive`, sobe pelo `ExceptionMiddleware` do FastAPI e vira **413**, e não
    um 500 mudo. Era a minha maior suposição não medida.
    """
    from fastapi import FastAPI, File, UploadFile
    app = FastAPI()
    app.add_middleware(TetoDeCorpo, teto=teto)

    @app.post("/api/estimate-price")
    async def _rota(files: list[UploadFile] = File(...)):
        total = 0
        for f in files:
            total += len(await f.read())
        return {"ok": True, "bytes": total}

    return app


def test_o_cliente_recebe_413_e_nao_500():
    from starlette.testclient import TestClient
    c = TestClient(_app_de_verdade(64 * 1024))
    r = c.post("/api/estimate-price",
               files={"files": ("g.bin", b"x" * (256 * 1024), "application/octet-stream")})
    assert r.status_code == 413, (
        "estourar o teto devolveu %s — se for 500, a exceção não está sendo "
        "convertida e o cliente vê erro genérico" % r.status_code)
    assert "MB no total" in r.text


def test_CONTROLE_upload_dentro_do_teto_chega_na_rota():
    """🧪 O par do teste acima. Uma trava que devolvesse 413 pra tudo passaria
    lá e quebraria todo cliente — aqui a rota tem que RODAR e devolver 200."""
    from starlette.testclient import TestClient
    c = TestClient(_app_de_verdade(64 * 1024))
    r = c.post("/api/estimate-price",
               files={"files": ("p.bin", b"x" * 1024, "application/octet-stream")})
    assert r.status_code == 200, r.text
    assert r.json()["bytes"] == 1024


def test_CONTROLE_rota_NAO_vigiada_passa_mesmo_estourando():
    """🧪 Prova que o corte é da lista de rotas, não de tudo."""
    from fastapi import FastAPI
    from starlette.testclient import TestClient
    from starlette.requests import Request
    app = FastAPI()
    app.add_middleware(TetoDeCorpo, teto=1024)

    @app.post("/api/qualquer-outra")
    async def _r(request: Request):
        return {"bytes": len(await request.body())}

    c = TestClient(app)
    r = c.post("/api/qualquer-outra", content=b"x" * (64 * 1024))
    assert r.status_code == 200, r.text
    assert r.json()["bytes"] == 64 * 1024


# ══════════════════════════════════════════════════════════════════════════
#  Estar escrito não é estar LIGADO
# ══════════════════════════════════════════════════════════════════════════
def test_o_middleware_esta_LIGADO_no_app():
    """🪤 Middleware que ninguém registra não protege nada — e hoje eu já
    escrevi guardas que casavam com o próprio comentário que os explicava.

    🔑 Por isso este teste olha a PILHA de middleware do app de verdade, não o
    texto do arquivo: comentário não entra em `user_middleware`.
    """
    import main as M
    nomes = [getattr(m.cls, "__name__", "") for m in M.app.user_middleware]
    assert "TetoDeCorpo" in nomes, (
        "o teto de corpo não está registrado no app — está só escrito. "
        "Pilha atual: %s" % nomes)
