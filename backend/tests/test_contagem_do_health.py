# -*- coding: utf-8 -*-
"""As contagens do /api/health têm que ser lidas do banco, não de um except.

🚨 25/08/2026. Enquanto conferia o deploy, o `/api/health` respondeu
`"total_users": 0` — com **77 perfis** no banco. A contagem pedia
`profiles?select=id` e a tabela **não tem coluna `id`** (a chave é `user_id`).
Provado com curl na anon key, no dia:

    GET /rest/v1/profiles?select=id      → HTTP 400
       {"code":"42703","message":"column profiles.id does not exist"}
    GET /rest/v1/profiles?select=user_id → HTTP 200

O 400 caía num `except Exception: pass` e o zero ia pro ar como se fosse
medição. `total_projects` funcionava (projects TEM `id`), então o payload
parecia saudável — um número certo ao lado de um número morto.

🪤 O detalhe que faz este caso valer um guarda: três linhas acima existe um
comentário `FIX 2026-05-14` que descreve exatamente o sintoma
"total_users=0 sempre". Consertaram OUTRA causa (write-back de `locals()`),
não conferiram a SAÍDA, e o número seguiu zero por 3 meses com um comentário
dizendo que estava resolvido. Conserto que não é conferido na saída não é
conserto — é um comentário.

🚨 Por isso falha agora vira `null` e não `0`: zero é um número e se lê como
medição; `null` diz "não consegui contar".
"""
import os
import sys
import types
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _corpo import corpo_de, so_o_que_roda  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main  # noqa: E402

# Coluna que existe de verdade em cada tabela (conferido no
# information_schema em 25/08/2026).
CHAVE = {"projects": "id", "profiles": "user_id"}

# 🚨 O FATO de 25/08/2026, provado com curl na anon key no dia:
#     GET /rest/v1/profiles?select=id      -> HTTP 400
#        {"code":"42703","message":"column profiles.id does not exist"}
#     GET /rest/v1/profiles?select=user_id -> HTTP 200
# A bancada abaixo e um PostgREST que se comporta assim. A rota roda contra ele.
NAO_EXISTE = {"profiles": {"id"}, "projects": set()}
QUANTOS = {"projects": 229, "profiles": 77}


class _RespostaFalsa:
    def __init__(self, total):
        self.headers = {"content-range": "0-0/%d" % total}

    def read(self):
        return b"[]"

    def getcode(self):
        return 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _postgrest_de_verdade(pedidos):
    """Devolve 400 quando a consulta pede uma coluna que a tabela nao tem."""
    def _urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        pedidos.append(url)
        caminho = url.split("/rest/v1/", 1)[-1]
        tabela = caminho.split("?", 1)[0]
        colunas = []
        for parte in caminho.split("?", 1)[-1].split("&"):
            if parte.startswith("select="):
                colunas = parte[len("select="):].split(",")
        faltando = NAO_EXISTE.get(tabela, set()) & set(colunas)
        if faltando:
            raise urllib.error.HTTPError(
                url, 400,
                "column %s.%s does not exist" % (tabela, sorted(faltando)[0]),
                {}, None)
        return _RespostaFalsa(QUANTOS.get(tabela, 0))
    return _urlopen


# ── a bancada que o guarda convertido pede ────────────────────────────────
NO_BANCO = {"projects": 229, "profiles": 77}


class _FakeReq:
    headers = {}
    client = None


def _postgrest(monkeypatch, quebradas=(), pedidos=None):
    """PostgREST do dia 25/08: 400 na coluna que a tabela nao tem."""
    pedidos = [] if pedidos is None else pedidos

    def _urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        pedidos.append(url)
        caminho = url.split("/rest/v1/", 1)[-1]
        tabela = caminho.split("?", 1)[0]
        colunas = []
        for parte in caminho.split("?", 1)[-1].split("&"):
            if parte.startswith("select="):
                colunas = [c for c in parte[len("select="):].split(",") if c]
        if tabela in quebradas:
            raise urllib.error.HTTPError(url, 500, "boom", {}, None)
        for c in colunas:
            if c != CHAVE.get(tabela):
                raise urllib.error.HTTPError(
                    url, 400, "column %s.%s does not exist" % (tabela, c), {}, None)
        return _RespostaFalsa(NO_BANCO.get(tabela, 0))

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    monkeypatch.setattr(main, "_get_user_from_request",
                        lambda request, tolerante=False: {
                            "id": "uid-admin", "email": main.ADMIN_EMAIL})
    return _FakeReq()


def _chamar(fn, *a):
    """Roda a rota aceitando `def` OU `async def`."""
    import asyncio
    import inspect
    r = fn(*a)
    if inspect.isawaitable(r):
        return asyncio.run(r)
    return r


def _health_de_admin(monkeypatch):
    """Chama `/api/health` DE VERDADE como admin. Devolve (saida, urls pedidas)."""
    pedidos = []
    monkeypatch.setattr(urllib.request, "urlopen", _postgrest_de_verdade(pedidos))
    monkeypatch.setattr(main, "_get_user_from_request",
                        lambda request, tolerante=False: {
                            "id": "uid-admin", "email": main.ADMIN_EMAIL})
    pedido = types.SimpleNamespace(headers={"Authorization": "Bearer jwt-admin"})
    return main.health(pedido), pedidos



def test_cada_tabela_e_contada_pela_coluna_que_ELA_tem(monkeypatch):
    """🚨 O bug, medido na SAÍDA: `profiles?select=id` devolve 400 e o painel
    dizia "0 usuários" com 77 perfis no banco."""
    req = _postgrest(monkeypatch)
    stats = _chamar(main.health, req)["stats"]
    assert stats["total_users"] == 77, (
        "a contagem de profiles voltou a pedir uma coluna que a tabela não tem "
        "— o PostgREST devolve 400 e o número morre (veio %r)"
        % stats["total_users"])
    assert stats["total_projects"] == 229, stats

def test_CONTROLE_a_bancada_REPROVA_a_coluna_errada(monkeypatch):
    """🧪 Se o PostgREST falso aceitasse qualquer coluna, o teste de cima seria
    verde vazio. Aqui ele tem que dar 400 no `profiles?select=id` — e 200 no
    `projects?select=id`, que existe."""
    pedidos = []
    urlopen = _postgrest_de_verdade(pedidos)

    class _Req:
        def __init__(self, url):
            self.full_url = url

    base = main.SUPABASE_URL + "/rest/v1/"
    with pytest.raises(urllib.error.HTTPError) as e:
        urlopen(_Req(base + "profiles?select=id&limit=1"))
    assert e.value.code == 400
    assert "profiles.id does not exist" in str(e.value.reason)
    assert urlopen(_Req(base + "profiles?select=user_id&limit=1")).headers[
        "content-range"].endswith("/77")
    assert urlopen(_Req(base + "projects?select=id&limit=1")).headers[
        "content-range"].endswith("/229")


def test_falha_de_contagem_nao_vira_zero():
    """Zero é um número e se lê como medição. Não consegui contar é `null`."""
    corpo = so_o_que_roda("health")
    assert "total_users = None" in corpo, (
        "a contagem voltou a nascer em 0 — falha silenciosa vira 'nenhum "
        "usuário' na cara de quem lê o painel")
    assert "total_projects = None" in corpo


def test_a_falha_da_contagem_deixa_rastro():
    """🪤 `except Exception: pass` foi o que escondeu isto por 3 meses."""
    corpo = corpo_de("health")
    i = corpo.index("def _count_table")
    trecho = corpo[i:]
    assert "except Exception: pass" not in trecho, (
        "voltou o except mudo — foi ele que engoliu o HTTP 400 do profiles")
    assert trecho.count("[health] contagem de") >= 2, (
        "as duas contagens precisam gritar quando falham")


@pytest.mark.parametrize("tabela,coluna", sorted(CHAVE.items()))
def test_controle_a_coluna_declarada_bate_com_o_codigo(tabela, coluna):
    """🧪 Se alguém trocar a coluna no código sem trocar aqui, os dois lados
    divergem em silêncio — e este arquivo vira decoração."""
    assert "_count_table('%s', '%s')" % (tabela, coluna) in so_o_que_roda("health")


def test_controle_positivo_o_guarda_PEGA_o_codigo_antigo():
    """🧪 O código exato que estava no ar até hoje de manhã."""
    antigo = """    total_projects = 0
    total_users = 0
    try:
        def _count_table(table):
            url = f"{SUPABASE_URL}/rest/v1/{table}?select=id"
        try: total_users = _count_table('profiles')
        except Exception: pass
"""
    assert "total_users = None" not in antigo
    assert "_count_table('profiles', 'user_id')" not in antigo
    assert "except Exception: pass" in antigo
