# -*- coding: utf-8 -*-
"""Todo formulário com arquivo tem teto enquanto chega — não só as três rotas grandes (auditoria SI, 27/09/2026).

🩸 O `TetoDeCorpo` (08/09) contava o corpo só de /api/process, add-file e estimate-price. Outras 8 rotas recebem
arquivo (cotações, planilha revisada, cliente, cashback, calibração, 2 do lote do financeiro, fotos do Escritório), e
o FastAPI lê o formulário INTEIRO antes de a rota conferir o login. Sem conta nenhuma, dava pra prender memória nelas
pela origem direta do Render — o mesmo modo de falha do incidente de 21/07.

🔑 A régua agora é o TIPO do corpo (`multipart/form-data`), com teto de 60 MB; as três grandes seguem com 450 MB.
Rota nova que receba arquivo já nasce coberta, sem ninguém lembrar de pôr numa lista.
"""
import asyncio
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from upload_teto import TETO_FORMULARIO, TETO_PADRAO, TetoDeCorpo, formulario_com_arquivo  # noqa: E402

MULTIPART = b"multipart/form-data; boundary=xyz"


# ══════════════════════════════════════════════════════════════════════════
#  A decisão pura
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("metodo,tipo,esperado", [
    ("POST", "multipart/form-data; boundary=a", True),
    ("PUT", "multipart/form-data; boundary=a", True),
    ("PATCH", "Multipart/Form-Data; boundary=a", True),
    ("POST", "application/json", False),
    ("POST", "", False),
    ("POST", None, False),
    ("GET", "multipart/form-data; boundary=a", False),
    (None, "multipart/form-data", False),
])
def test_reconhece_formulario_com_arquivo(metodo, tipo, esperado):
    assert formulario_com_arquivo(metodo, tipo) is esperado


def test_o_teto_do_formulario_cabe_as_rotas_legitimas_e_e_menor_que_o_grande():
    """O maior envio legítimo fora das três grandes é o de fotos do Escritório, que a rota limita a 40 MB."""
    import escritorio_drive
    assert escritorio_drive._FOTOS_TOTAL < TETO_FORMULARIO, "o teto novo barraria um envio de fotos que a rota aceita"
    assert TETO_FORMULARIO < TETO_PADRAO


# ══════════════════════════════════════════════════════════════════════════
#  O middleware como ASGI de verdade
# ══════════════════════════════════════════════════════════════════════════
class _AppQueLe:
    def __init__(self):
        self.lidos = 0

    async def __call__(self, scope, receive, send):
        while True:
            msg = await receive()
            if msg.get("type") != "http.request":
                break
            self.lidos += len(msg.get("body") or b"")
            if not msg.get("more_body"):
                break


def _rodar(mw, scope, pedacos):
    fila = iter([{"type": "http.request", "body": b"x" * n, "more_body": i < len(pedacos) - 1}
                 for i, n in enumerate(pedacos)])

    async def receive():
        try:
            return next(fila)
        except StopIteration:
            return {"type": "http.disconnect"}

    async def send(_m):
        pass

    asyncio.run(mw(scope, receive, send))


def _scope(caminho, tipo):
    return {"type": "http", "method": "POST", "path": caminho,
            "headers": [(b"content-type", tipo)] if tipo else []}


def test_formulario_fora_das_tres_rotas_e_cortado_no_teto_proprio():
    from fastapi import HTTPException
    mw = TetoDeCorpo(_AppQueLe(), teto=10_000, teto_formulario=100)
    with pytest.raises(HTTPException) as e:
        _rodar(mw, _scope("/api/cashback/upload", MULTIPART), [60, 60])
    assert e.value.status_code == 413


def test_CONTROLE_formulario_pequeno_passa_inteiro():
    alvo = _AppQueLe()
    mw = TetoDeCorpo(alvo, teto=10_000, teto_formulario=100)
    _rodar(mw, _scope("/api/cashback/upload", MULTIPART), [40, 40])
    assert alvo.lidos == 80


def test_CONTROLE_corpo_que_nao_e_formulario_nao_e_contado():
    """JSON das telas segue como antes: o corte é do formulário com arquivo, não de todo corpo."""
    alvo = _AppQueLe()
    mw = TetoDeCorpo(alvo, teto=10_000, teto_formulario=1)
    _rodar(mw, _scope("/api/escritorio/convite/ver", b"application/json"), [50, 50])
    assert alvo.lidos == 100


def test_as_tres_rotas_grandes_continuam_no_teto_grande():
    """Upload de projeto de 200 MB não pode passar a esbarrar no teto de 60."""
    alvo = _AppQueLe()
    mw = TetoDeCorpo(alvo, teto=10_000, teto_formulario=100)
    _rodar(mw, _scope("/api/process", MULTIPART), [3000, 3000])
    assert alvo.lidos == 6000


# ══════════════════════════════════════════════════════════════════════════
#  A corrente inteira: a rota confere o login DEPOIS de o formulário ser lido
# ══════════════════════════════════════════════════════════════════════════
def _app_com_login_depois(teto_formulario):
    """Igual às nossas rotas: parâmetro de arquivo (o FastAPI lê o formulário antes) e o login conferido no corpo."""
    from fastapi import FastAPI, File, HTTPException, UploadFile
    app = FastAPI()
    app.add_middleware(TetoDeCorpo, teto_formulario=teto_formulario)
    app.state.rodou = 0

    @app.post("/api/projects/{job_id}/revised-sheet/upload")
    async def _rota(job_id: str, file: UploadFile = File(...)):
        app.state.rodou += 1
        raise HTTPException(401, "Autenticação requerida")

    return app


def test_sem_login_e_acima_do_teto_o_corte_vem_antes_da_rota():
    from starlette.testclient import TestClient
    app = _app_com_login_depois(64 * 1024)
    r = TestClient(app).post("/api/projects/x/revised-sheet/upload",
                             files={"file": ("p.xlsx", b"x" * (256 * 1024), "application/octet-stream")})
    assert r.status_code == 413, r.status_code
    assert app.state.rodou == 0, "a rota rodou: o formulário inteiro foi lido antes do corte"


def test_CONTROLE_dentro_do_teto_a_rota_roda_e_responde_401():
    from starlette.testclient import TestClient
    app = _app_com_login_depois(64 * 1024)
    r = TestClient(app).post("/api/projects/x/revised-sheet/upload",
                             files={"file": ("p.xlsx", b"x" * 1024, "application/octet-stream")})
    assert r.status_code == 401
    assert app.state.rodou == 1


# ══════════════════════════════════════════════════════════════════════════
#  A premissa: as 8 rotas de hoje recebem formulário (senão este guarda descreve outra realidade)
# ══════════════════════════════════════════════════════════════════════════
def test_as_rotas_com_arquivo_do_app_de_verdade_existem_e_nenhuma_mudou_o_teto():
    import main as M
    com_arquivo = set()
    for r in M.app.routes:
        dep = getattr(r, "dependant", None)
        if not dep:
            continue
        if any(type(p.field_info).__name__ in ("File", "Form") for p in dep.body_params):
            com_arquivo.add(r.path)
    for esperada in ("/api/projects/{job_id}/quotes/upload", "/api/projects/{job_id}/revised-sheet/upload",
                     "/api/cashback/upload", "/api/financeiro/{job_id}/lote/conferir",
                     "/api/escritorio/projetos/{projeto_id}/fotos"):
        assert esperada in com_arquivo, "a rota %s deixou de receber formulário — reveja este guarda" % esperada
    mw = [m for m in M.app.user_middleware if getattr(m.cls, "__name__", "") == "TetoDeCorpo"]
    assert mw, "o teto de corpo saiu do app"
    assert "teto_formulario" not in (getattr(mw[0], "kwargs", None) or {}), "alguém afrouxou o teto do formulário no app"
