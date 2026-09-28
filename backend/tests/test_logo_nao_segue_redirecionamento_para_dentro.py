# -*- coding: utf-8 -*-
"""A logo do perfil só vem de host público — no pedido E em cada redirecionamento (auditoria SI, 27/09/2026).

A guarda `_url_is_safe_public` (22/07) conferia só o primeiro endereço; o `urlopen` seguia redirecionamento às cegas,
e uma logo num host público podia mandar o servidor pra um endereço interno. Tudo aqui roda sem rede.
"""
import email.message
import io
import os
import sys
import urllib.error
import urllib.request

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def _redirecionar(main, destino):
    h = main._RedirecionamentoConferido()
    req = urllib.request.Request("https://cdn.exemplo.com/logo.png")
    return h.redirect_request(req, io.BytesIO(b""), 302, "Found", email.message.Message(), destino)


@pytest.mark.parametrize("destino", ["http://169.254.169.254/latest/meta-data/", "http://127.0.0.1:8000/api/health",
                                     "http://10.0.0.5/x", "file:///etc/passwd"])
def test_redirecionamento_para_endereco_interno_e_recusado(destino):
    import main
    with pytest.raises(urllib.error.HTTPError):
        _redirecionar(main, destino)


def test_CONTROLE_redirecionamento_para_host_publico_segue(monkeypatch):
    import main
    monkeypatch.setattr(main, "_url_is_safe_public", lambda u: True)
    novo = _redirecionar(main, "https://outra-cdn.exemplo.com/logo.png")
    assert novo is not None and novo.full_url == "https://outra-cdn.exemplo.com/logo.png"


def test_endereco_interno_nem_comeca():
    import main
    with pytest.raises(ValueError):
        main._baixar_de_host_publico("http://127.0.0.1/logo.png")


def test_os_dois_lugares_que_baixam_a_logo_usam_o_caminho_conferido():
    src = open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    assert src.count("_baixar_de_host_publico(logo_url)") == 1, "o PPTX do comparativo voltou a baixar a logo por fora"
    assert src.count("_baixar_de_host_publico(ctx['logo_url']") == 1, "o PDF do cronograma voltou a baixar a logo por fora"
