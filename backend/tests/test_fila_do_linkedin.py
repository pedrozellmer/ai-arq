# -*- coding: utf-8 -*-
"""A fila do LinkedIn no admin: o Pedro aprova ANTES, e o painel não finge que publica.

27/09/2026 — Pedro: "vamos colocar no nosso site no admin pra eu aprovar antes… tipo o instagram".
Diferente do IG, não há robô: a API de páginas do LinkedIn exige app de desenvolvedor ligado à conta
dele, e ele pediu pra não vincular nada ao perfil. Então o painel só aprova, devolve, cancela e edita;
"agendado"/"publicado" são marcados por quem agenda na página.

O guarda chama as rotas DE VERDADE, com o Supabase de mentira gravando cada PATCH:
- aprovar sem imagem ou sem texto é barrado ANTES de gravar;
- post que já está no LinkedIn (agendado/publicado) não muda nem é editado pelo painel;
- o painel não consegue marcar "agendado" (isso diria que está no LinkedIn sem estar);
- texto acima de 3.000 caracteres (limite do LinkedIn) não é salvo.
"""
import asyncio
import io
import json
import os
import sys
import urllib.request

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)
_RAIZ = os.path.dirname(_BACKEND)

import main as _m  # noqa: E402
from fastapi import HTTPException  # noqa: E402

_ID = "0f8fad5b-d9cb-469f-a165-70867728950e"


class _Resp:
    def __init__(self, dados):
        self._b = json.dumps(dados).encode("utf-8")

    def read(self):
        return self._b


class _Req:
    """Request mínimo: as rotas só leem o corpo JSON (o admin é dublado)."""
    def __init__(self, corpo):
        self._c = corpo

    async def json(self):
        return self._c


@pytest.fixture
def banco(monkeypatch):
    ctl = {"linha": None, "patches": []}
    monkeypatch.setattr(_m, "_require_admin", lambda r: {"email": "admin@example.com"})

    def _fake(req, timeout=None):
        url = getattr(req, "full_url", str(req))
        assert "linkedin_posts" in url, url
        if req.get_method() == "PATCH":
            ctl["patches"].append(json.loads(req.data.decode("utf-8")))
            return _Resp([])
        return _Resp([ctl["linha"]] if ctl["linha"] else [])

    monkeypatch.setattr(urllib.request, "urlopen", _fake)
    return ctl


def _status(corpo):
    return asyncio.run(_m.admin_linkedin_post_status(_Req(corpo)))


def _editar(corpo):
    return asyncio.run(_m.admin_linkedin_post_update(_Req(corpo)))


def test_aprovar_com_imagem_e_texto_grava_approved(banco):
    """🧪 CONTROLE do dublê: o caminho feliz GRAVA — sem isto, os 'não gravou' abaixo passariam à toa."""
    banco["linha"] = {"id": _ID, "status": "pending_approval", "texto": "Post.", "image_url": "https://x/a.png"}
    assert _status({"id": _ID, "status": "approved"})["new_status"] == "approved"
    assert len(banco["patches"]) == 1, banco["patches"]
    assert banco["patches"][0]["status"] == "approved"
    assert banco["patches"][0]["approved_at"], "aprovou sem registrar QUANDO"


@pytest.mark.parametrize("linha", [
    {"status": "pending_approval", "texto": "Post.", "image_url": ""},
    {"status": "pending_approval", "texto": "   ", "image_url": "https://x/a.png"},
])
def test_aprovar_sem_imagem_ou_sem_texto_e_barrado_antes_de_gravar(banco, linha):
    banco["linha"] = dict(linha, id=_ID)
    with pytest.raises(HTTPException) as e:
        _status({"id": _ID, "status": "approved"})
    assert e.value.status_code == 400
    assert not banco["patches"], "gravou a aprovação de um post sem imagem/texto"


@pytest.mark.parametrize("ja_no_linkedin", ["scheduled", "published"])
def test_post_que_ja_esta_no_linkedin_nao_muda_nem_e_editado(banco, ja_no_linkedin):
    banco["linha"] = {"id": _ID, "status": ja_no_linkedin, "texto": "Post.", "image_url": "https://x/a.png"}
    for chamar in (lambda: _status({"id": _ID, "status": "canceled"}),
                   lambda: _editar({"id": _ID, "texto": "outro texto"})):
        with pytest.raises(HTTPException) as e:
            chamar()
        assert e.value.status_code == 409
    assert not banco["patches"], "o painel mexeu num post que já está no LinkedIn (lá não muda)"


@pytest.mark.parametrize("fingido", ["scheduled", "published"])
def test_o_painel_nao_marca_agendado_nem_publicado(banco, fingido):
    """Marcar 'agendado' pelo painel diria que o post está no LinkedIn sem estar."""
    banco["linha"] = {"id": _ID, "status": "approved", "texto": "Post.", "image_url": "https://x/a.png"}
    with pytest.raises(HTTPException) as e:
        _status({"id": _ID, "status": fingido})
    assert e.value.status_code == 400
    assert not banco["patches"]


def test_texto_acima_do_limite_do_linkedin_nao_e_salvo(banco):
    banco["linha"] = {"id": _ID, "status": "pending_approval", "texto": "Post.", "image_url": "https://x/a.png"}
    with pytest.raises(HTTPException) as e:
        _editar({"id": _ID, "texto": "a" * 3001})
    assert e.value.status_code == 400
    assert not banco["patches"]
    _editar({"id": _ID, "texto": "a" * 3000})
    assert banco["patches"] and banco["patches"][-1]["texto"] == "a" * 3000


def test_a_aba_existe_e_fala_com_as_rotas():
    html = io.open(os.path.join(_RAIZ, "admin.html"), encoding="utf-8").read()
    assert 'id="tab-linkedin"' in html and 'data-tab="linkedin"' in html
    assert "if (tabName === 'linkedin') loadLinkedinPosts();" in html
    for rota in ("/api/admin/linkedin/posts?", "/api/admin/linkedin/posts/status", "/api/admin/linkedin/posts/update"):
        assert rota in html, "a aba não chama %s" % rota
    # o calendário é UMA linha do tempo: LinkedIn entra nela
    assert "canal: '💼 LinkedIn'" in html
