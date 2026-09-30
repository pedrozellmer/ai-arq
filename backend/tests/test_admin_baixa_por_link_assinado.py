# -*- coding: utf-8 -*-
"""A rota de admin que baixa o arquivo original entrega LINK ASSINADO com `link=1`.

🩸 30/09/2026. Setembro passou dos 5 GB de banda do plano do Render. Numa manhã
de estudo do acervo saíram 208 MB por `/api/admin/baixar-arquivo` (7 DWG de
~30 MB e alguns PDFs) — tudo o que a rota entrega sai da conta do Render. E o
caminho dos bytes carrega o arquivo INTEIRO na memória do servidor antes de
mandar: um DXF de 200 MB do acervo são 200 MB a mais ao lado do job de um
cliente, num servidor que já caiu por memória.

Com `link=1` a rota devolve um link assinado do Storage e o arquivo vai do
Supabase direto pro navegador.

O que estes testes seguram:
- com `link=1`, a rota NÃO baixa o arquivo — nenhum byte passa pelo servidor;
- o link é ASSINADO (`/object/sign/`), vale 10 min e é pedido com a chave de
  serviço, no balde das pranchas, na pasta do job;
- nome com espaço e acento vai codificado no caminho;
- assinatura que falha (ou vem vazia) vira ERRO 502 — nunca cai pro caminho
  dos bytes, nunca vira link público;
- o link (a credencial) não vai pro log;
- sem `link`, os bytes seguem como antes;
- só admin, e só arquivo do próprio job.
"""
import asyncio
import json
import os
import sys
from urllib.parse import quote

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main as m                                    # noqa: E402
from fastapi import HTTPException                   # noqa: E402

_JOB = "ab12cd34"
_NOME = "PLANTA TÉRREO.dwg"
_TOKEN = "TOKEN-SECRETO-123"


class _Resp:
    def __init__(self, corpo: bytes):
        self._b = corpo

    def read(self):
        return self._b


def _prepara(monkeypatch, nomes=(_NOME,), assinatura=None, falha=False,
             bytes_do_storage=None):
    """Admin passa; o Storage lista `nomes`; o `urlopen` responde à assinatura.

    O download de bytes EXPLODE se for chamado — a não ser que o teste diga
    quais bytes ele devolve (`bytes_do_storage`), que é o caso sem `link`."""
    pedidos, logs, baixou = [], [], []
    # 🪤 chaves DIFERENTES de propósito: com as duas vazias no ambiente de
    # teste, "assinou com a chave pública" passaria calado.
    monkeypatch.setattr(m, "SUPABASE_URL", "https://exemplo.supabase.co")
    monkeypatch.setattr(m, "SUPABASE_KEY", "chave-publica-falsa")
    monkeypatch.setattr(m, "SUPABASE_SERVICE_ROLE_KEY", "chave-de-servico-falsa")
    monkeypatch.setattr(m, "_require_admin", lambda *a, **k: None)
    monkeypatch.setattr(m, "_supabase_storage_list", lambda bucket, prefix: list(nomes))

    def _download(job_id, filename, *a, **k):
        baixou.append(filename)
        if bytes_do_storage is None:
            raise AssertionError("o caminho dos BYTES foi chamado com link=1")
        return bytes_do_storage
    monkeypatch.setattr(m, "_supabase_storage_download_prancha", _download)
    monkeypatch.setattr(m, "_log_error", lambda *a, **k: logs.append(" ".join(map(str, a))))

    import urllib.request as _ur

    def _urlopen(req, timeout=None):
        pedidos.append(req)
        if falha:
            raise OSError("storage fora do ar")
        corpo = assinatura if assinatura is not None else {
            "signedURL": f"/object/sign/{m.PRANCHAS_BUCKET}/{_JOB}/x?token={_TOKEN}"}
        return _Resp(json.dumps(corpo).encode("utf-8"))
    monkeypatch.setattr(_ur, "urlopen", _urlopen)
    return pedidos, logs, baixou


def _roda(**kw):
    return asyncio.run(m.admin_baixar_arquivo(_JOB, None, **kw))


def test_com_link_devolve_link_assinado_e_NAO_baixa_os_bytes(monkeypatch):
    pedidos, _logs, baixou = _prepara(monkeypatch)
    r = _roda(nome=_NOME, link=1)
    assert baixou == [], "com link=1 o arquivo passou pelo servidor"
    assert isinstance(r, dict), f"esperava JSON com o link, veio {type(r).__name__}"
    assert r["nome"] == _NOME
    assert r["expira_em_s"] == 600
    assert r["url"].startswith(f"{m.SUPABASE_URL}/storage/v1/object/sign/")
    assert f"token={_TOKEN}" in r["url"]
    # sem `download=` o link abre como página em vez de salvar o arquivo
    assert "&download=" in r["url"] and quote(_NOME) in r["url"].split("&download=")[1]
    assert len(pedidos) == 1


def test_o_pedido_de_assinatura_vai_pro_balde_e_pasta_certos_com_a_chave_de_servico(monkeypatch):
    pedidos, _logs, _b = _prepara(monkeypatch)
    _roda(nome=_NOME, link=1)
    req = pedidos[0]
    assert req.get_method() == "POST"
    assert req.full_url == (f"{m.SUPABASE_URL}/storage/v1/object/sign/"
                            f"{m.PRANCHAS_BUCKET}/{_JOB}/{quote(_NOME)}")
    assert " " not in req.full_url and "É" not in req.full_url, "nome sem codificar no caminho"
    assert json.loads(req.data.decode("utf-8")) == {"expiresIn": 600}
    assert req.get_header("Authorization") == "Bearer chave-de-servico-falsa"


def test_assinatura_que_FALHA_e_erro_502_nunca_bytes(monkeypatch):
    _p, logs, baixou = _prepara(monkeypatch, falha=True)
    with pytest.raises(HTTPException) as e:
        _roda(nome=_NOME, link=1)
    assert e.value.status_code == 502
    assert baixou == [], "a falha da assinatura caiu pro caminho dos bytes"
    assert any("storage:assinar-link" in l for l in logs), "a falha não deixou rastro"


def test_assinatura_VAZIA_e_erro_502_nunca_link_publico(monkeypatch):
    _p, _l, baixou = _prepara(monkeypatch, assinatura={})
    with pytest.raises(HTTPException) as e:
        _roda(nome=_NOME, link=1)
    assert e.value.status_code == 502
    assert baixou == []


def test_o_link_NAO_vai_pro_log(monkeypatch):
    _p, logs, _b = _prepara(monkeypatch)
    _roda(nome=_NOME, link=1)
    assert not any(_TOKEN in l for l in logs), "o link assinado (credencial) foi pro log"


def test_sem_link_os_bytes_seguem_como_antes(monkeypatch):
    pedidos, _l, baixou = _prepara(monkeypatch, bytes_do_storage=b"AC1032...")
    r = _roda(nome=_NOME)
    assert baixou == [_NOME]
    assert r.body == b"AC1032..."
    assert pedidos == [], "sem link=1 a rota pediu assinatura mesmo assim"


def test_so_admin(monkeypatch):
    pedidos, _l, baixou = _prepara(monkeypatch)

    def _barra(*a, **k):
        raise HTTPException(403, "admin only")
    monkeypatch.setattr(m, "_require_admin", _barra)
    with pytest.raises(HTTPException) as e:
        _roda(nome=_NOME, link=1)
    assert e.value.status_code == 403
    assert pedidos == [] and baixou == []


def test_arquivo_que_nao_e_do_job_da_404_e_nao_assina(monkeypatch):
    pedidos, _l, _b = _prepara(monkeypatch, nomes=("outro.dwg",))
    with pytest.raises(HTTPException) as e:
        _roda(nome="../ff00ee11/segredo.dwg", link=1)
    assert e.value.status_code == 404
    assert pedidos == [], "assinou link de arquivo que não está na pasta do job"
