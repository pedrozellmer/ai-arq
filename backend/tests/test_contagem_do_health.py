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
#
# 🪤 06/09/2026 — A BANCADA SÓ SABIA UM JEITO DE RECUSAR. Ela devolvia o total
# no `content-range` acontecesse o que acontecesse e ignorava CABEÇALHO por
# completo. Com isso o guarda provava que a palavra `user_id` chega na URL, não
# que a contagem funciona: tirar o `Prefer: count=exact` da produção — que é o
# que faz o PostgREST contar — passava VERDE, e o painel voltava a dizer
# "0 usuários" (o PostgREST de verdade responde `content-range: 0-0/*`, o
# `int('*')` estoura e o número morre). Agora o falso sabe recusar de TRÊS
# jeitos: coluna que a tabela não tem (400), servidor fora do ar (500) e
# pedido sem `count=exact` (não conta, devolve `*`).
NO_BANCO = {"projects": 229, "profiles": 77}


class _RespostaFalsa:
    def __init__(self, content_range, corpo=b"[{}]"):
        self.headers = {"content-range": content_range}
        self._corpo = corpo

    def read(self):
        return self._corpo

    def getcode(self):
        return 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _postgrest_falso(pedidos, quebradas=()):
    """O PostgREST do dia 25/08, com as três recusas que ele sabe dar.

    `pedidos` recebe (url, cabeçalhos) de cada consulta — é por ele que os
    guardas conferem QUAL consulta saiu, não só qual número voltou.
    """
    def _urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        cabecalhos = dict(getattr(req, "headers", None) or {})
        pedidos.append((url, cabecalhos))
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
        # 🔑 Sem `Prefer: count=exact` o PostgREST NÃO conta: devolve `*` no
        # lugar do total e a página pedida (limit=1) no corpo.
        prefer = ""
        for k, v in cabecalhos.items():
            if str(k).lower() == "prefer":
                prefer = str(v).lower()
        if "count=exact" not in prefer:
            return _RespostaFalsa("0-0/*")
        return _RespostaFalsa("0-0/%d" % NO_BANCO.get(tabela, 0))

    return _urlopen


class _FakeReq:
    headers = {}
    client = None


def _postgrest(monkeypatch, quebradas=(), pedidos=None):
    """Planta o PostgREST falso e o porteiro de admin. Devolve o Request."""
    pedidos = [] if pedidos is None else pedidos
    monkeypatch.setattr(urllib.request, "urlopen",
                        _postgrest_falso(pedidos, quebradas))
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


def _url_da_contagem(tabela, coluna):
    return "%s?select=%s&limit=1" % (tabela, coluna)


def test_cada_tabela_e_contada_pela_coluna_que_ELA_tem(monkeypatch):
    """🚨 O bug, medido na SAÍDA: `profiles?select=id` devolve 400 e o painel
    dizia "0 usuários" com 77 perfis no banco.

    🪤 E medido também na CONSULTA que saiu: a versão anterior deste guarda
    tinha largado as assertivas de URL por tabela, ficando mais fraca do que a
    que ela substituiu. As duas coisas cabem no mesmo teste.
    """
    pedidos = []
    req = _postgrest(monkeypatch, pedidos=pedidos)
    stats = _chamar(main.health, req)["stats"]
    assert stats["total_users"] == 77, (
        "a contagem de profiles voltou a pedir uma coluna que a tabela não tem "
        "— o PostgREST devolve 400 e o número morre (veio %r)"
        % stats["total_users"])
    assert stats["total_projects"] == 229, stats
    urls = [u for u, _c in pedidos]
    for tabela, coluna in sorted(CHAVE.items()):
        assert any(_url_da_contagem(tabela, coluna) in u for u in urls), (
            "a consulta de %s não saiu como `%s` — saíram: %r"
            % (tabela, _url_da_contagem(tabela, coluna), urls))


@pytest.mark.parametrize("tabela,coluna", sorted(CHAVE.items()))
def test_a_consulta_PEDE_a_contagem_ao_servidor(tabela, coluna, monkeypatch):
    """🚨 `Prefer: count=exact` é o que faz o PostgREST contar. Sem ele o
    `content-range` volta `0-0/*`, o `int('*')` estoura e a contagem morre —
    exatamente o mesmo estrago do 400 de 25/08, por outra porta."""
    pedidos = []
    _chamar(main.health, _postgrest(monkeypatch, pedidos=pedidos))
    minhas = [c for u, c in pedidos if _url_da_contagem(tabela, coluna) in u]
    assert minhas, "a consulta de %s nem saiu" % tabela
    prefer = " ".join(str(v) for k, v in minhas[0].items()
                      if str(k).lower() == "prefer").lower()
    assert "count=exact" in prefer, (
        "a contagem de %s saiu sem `Prefer: count=exact` (cabeçalhos: %r) — o "
        "servidor devolve `*` no lugar do total e o número vira nulo"
        % (tabela, minhas[0]))


@pytest.mark.parametrize("quebrada,morto,vivo", [
    ("profiles", "total_users", "total_projects"),
    ("projects", "total_projects", "total_users"),
])
def test_servidor_fora_do_ar_vira_NULO_e_nao_derruba_a_outra(
        quebrada, morto, vivo, monkeypatch):
    """🚨 Zero é um número e se lê como medição. E a falha de UMA tabela não
    pode apagar a outra — foi um número certo ao lado de um número morto que
    fez o payload parecer saudável por 3 meses."""
    req = _postgrest(monkeypatch, quebradas=(quebrada,))
    stats = _chamar(main.health, req)["stats"]
    assert stats[morto] is None, (
        "a contagem de %s falhou e virou %r — zero se lê como 'nenhum'"
        % (quebrada, stats[morto]))
    outra = "projects" if quebrada == "profiles" else "profiles"
    assert stats[vivo] == NO_BANCO[outra], (
        "a falha de %s derrubou junto a contagem de %s (veio %r)"
        % (quebrada, outra, stats[vivo]))


def test_CONTROLE_a_bancada_REPROVA_a_coluna_errada():
    """🧪 Se o PostgREST falso aceitasse qualquer coisa, os testes de cima
    seriam verde vazio. Ele tem que dar 400 no `profiles?select=id`, 200 no
    `projects?select=id`, 500 quando o servidor cai — e `*` (não contei) para
    quem não pediu `Prefer: count=exact`."""
    pedidos = []
    urlopen = _postgrest_falso(pedidos)
    base = main.SUPABASE_URL + "/rest/v1/"

    def _req(caminho, contar=True):
        r = urllib.request.Request(base + caminho)
        if contar:
            r.add_header("Prefer", "count=exact")
        return r

    with pytest.raises(urllib.error.HTTPError) as e:
        urlopen(_req("profiles?select=id&limit=1"))
    assert e.value.code == 400
    assert "profiles.id does not exist" in str(e.value.reason)
    assert urlopen(_req("profiles?select=user_id&limit=1")).headers[
        "content-range"].endswith("/77")
    assert urlopen(_req("projects?select=id&limit=1")).headers[
        "content-range"].endswith("/229")
    assert urlopen(_req("profiles?select=user_id&limit=1", contar=False)
                   ).headers["content-range"] == "0-0/*", (
        "a bancada conta mesmo sem `Prefer: count=exact` — ela absolveria a "
        "produção que parou de pedir a contagem")
    with pytest.raises(urllib.error.HTTPError) as e500:
        _postgrest_falso([], quebradas=("profiles",))(
            _req("profiles?select=user_id&limit=1"))
    assert e500.value.code == 500


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
