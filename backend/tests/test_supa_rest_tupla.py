"""_supa_rest_service devolve (status, dados) — ninguém pode tratar como lista.

🚨 23/08/2026: 11 pontos do main.py faziam `rows = _supa_rest_service(...) or []`
e depois `rows[0].get(...)`. Como o retorno é uma TUPLA, `rows[0]` virava o
inteiro 200 e o `.get` estourava AttributeError. Efeitos reais:
  - botão "Liberar pro cliente" respondia "Load failed" no Safari (o 500 sai
    sem cabeçalho CORS, e o navegador reporta como erro de rede);
  - a fusão das revisões do cliente (regra dura nº7) nunca rodou — o except
    engolia o erro.
Quem quer só as linhas usa `_supa_rows(...)`.

🪤 06/09/2026 — OS DOIS GUARDAS PRINCIPAIS DESTE ARQUIVO LIAM O FONTE E FORAM
PROVADOS CEGOS. A mutação que passou por eles não acrescentou nenhuma das
formas proibidas: só INVERTEU o desempacotamento (`_rows, _st = ...` no
`_supa_rows`; `_revs, _st_r = ...` na fusão das revisões). A forma continuava
"dois nomes = chamada" e o regex continuava satisfeito — enquanto `_supa_rows`
passava a devolver o inteiro 200 no lugar das linhas e a fusão da regra nº7
voltava a nunca rodar. É a MESMA doença que este arquivo existe pra impedir,
escrita de um jeito que o texto aprova.

Agora os guardas EXECUTAM os dois consumidores com um `_supa_rest_service`
envenenado: o status sabe gritar quando é usado como lista, e as linhas sabem
gritar quando são comparadas com um código HTTP.
"""
import io
import os
import re
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

# Formas legítimas: desempacotar em dois nomes, ou chamar sem guardar o retorno
# (PATCH/POST fire-and-forget).
_OK_UNPACK = re.compile(r"^\s*[A-Za-z_]\w*\s*,\s*[A-Za-z_]\w*\s*=\s*_supa_rest_service\(")
_OK_SOLTA = re.compile(r"^\s*_supa_rest_service\(")


def _fonte():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


# ══════════════════════════════════════════════════════════════════════════
#  O VENENO — troca (status, linhas) por dois objetos que sabem gritar
# ══════════════════════════════════════════════════════════════════════════
class _Status(int):
    """O código HTTP. Comparar com 200 funciona; usar como lista explode."""

    def __iter__(self):
        raise AssertionError("o STATUS foi percorrido como se fosse a lista de linhas")

    def __getitem__(self, i):
        raise AssertionError("o STATUS foi indexado como se fosse a lista de linhas")

    def __len__(self):
        raise AssertionError("mediram o STATUS com len() — `len` de tupla é sempre 2")

    def get(self, *a, **k):
        raise AssertionError("chamaram .get() no STATUS — ele é um inteiro, não uma linha")


class _Linhas(list):
    """As linhas. Comparar com um código HTTP explode."""

    def __eq__(self, outro):
        if isinstance(outro, int) and not isinstance(outro, bool):
            raise AssertionError(
                "as LINHAS foram comparadas com um código HTTP (%r) — o "
                "desempacotamento está invertido" % outro)
        return list.__eq__(self, outro)

    def __ne__(self, outro):
        if isinstance(outro, int) and not isinstance(outro, bool):
            raise AssertionError(
                "as LINHAS foram comparadas com um código HTTP (%r) — o "
                "desempacotamento está invertido" % outro)
        return list.__ne__(self, outro)

    __hash__ = None


def _rest_falso(por_tabela, chamadas=None):
    """Um `_supa_rest_service` que devolve (status, linhas) envenenados."""
    def _f(method, path, **kw):
        if chamadas is not None:
            chamadas.append((method, path))
        tabela = str(path).split("?")[0]
        st, linhas = por_tabela.get(tabela, (200, []))
        return _Status(st), _Linhas(linhas or [])
    return _f


# ══════════════════════════════════════════════════════════════════════════
#  Consumidor 1 — `_supa_rows`, o helper que existe por causa do bug
# ══════════════════════════════════════════════════════════════════════════
def test_supa_rows_existe_e_devolve_lista(monkeypatch):
    """CHAMA `_supa_rows` de verdade e olha o que sai."""
    import main

    linhas_do_banco = [{"id": "i-1", "description": "Piso porcelanato"},
                       {"id": "i-2", "description": "Laje maciça"}]
    monkeypatch.setattr(main, "_supa_rest_service",
                        _rest_falso({"project_items": (200, linhas_do_banco)}))

    r = main._supa_rows("GET", "project_items", params={"job_id": "eq.x"})

    assert isinstance(r, list), (
        "`_supa_rows` devolveu %r (%s) no lugar das linhas — é o STATUS "
        "vazando pelo desempacotamento invertido" % (r, type(r).__name__))
    assert [d["id"] for d in r] == ["i-1", "i-2"], r


def test_supa_rows_devolve_LISTA_VAZIA_quando_a_rede_falha(monkeypatch):
    """Falha de rede não pode derrubar quem chamou — e não pode virar status."""
    import main

    monkeypatch.setattr(main, "_supa_rest_service",
                        _rest_falso({"project_items": (500, None)}))
    assert main._supa_rows("GET", "project_items") == []

    def _explode(*a, **k):
        raise RuntimeError("rede caiu")

    monkeypatch.setattr(main, "_supa_rest_service", _explode)
    assert main._supa_rows("GET", "project_items") == []


def test_CONTROLE_o_veneno_REPROVA_o_desempacotamento_invertido():
    """O veneno só vale se souber gritar. Aqui ele leva a inversão na mão."""
    _st, _linhas = _Status(200), _Linhas([{"id": "i-1"}])
    # o jeito certo: comparar status com 200 e percorrer as linhas
    assert _st == 200
    assert [d["id"] for d in _linhas] == ["i-1"]
    # o jeito invertido: as duas formas do bug têm que explodir
    invertido_status, invertido_linhas = _linhas, _st
    try:
        if invertido_status != 200:
            pass
    except AssertionError:
        pass
    else:
        raise AssertionError("o veneno não viu as LINHAS comparadas com 200")
    try:
        list(invertido_linhas)
    except AssertionError:
        pass
    else:
        raise AssertionError("o veneno não viu o STATUS percorrido como lista")


# ══════════════════════════════════════════════════════════════════════════
#  Consumidor 2 — a fusão das revisões (regra dura nº7), que NUNCA rodou
# ══════════════════════════════════════════════════════════════════════════
def test_a_fusao_da_regra7_LE_as_revisoes_de_verdade(monkeypatch):
    """🩸 O efeito real do bug de 23/08: a fusão morria na leitura da tupla,
    dentro de um try/except que engolia tudo. O cliente corrigia à mão e a
    releitura devolvia o número do motor por cima, calada."""
    import main
    from models import BudgetItem, Confidence

    revs = [{"item_id": "id-1", "reviewed_at": "2026-08-23T10:00:00Z",
             "edits": {"description": "Piso porcelanato", "unit": "m²",
                       "quantity": 100.0}}]
    pai = [{"id": "id-1", "description": "Piso porcelanato", "unit": "m²",
            "quantity": 250.0, "confidence": "estimado", "observations": ""}]
    monkeypatch.setattr(main, "_supa_rest_service", _rest_falso({
        "item_reviews": (200, revs), "project_items": (200, pai)}))
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)

    novo = BudgetItem(item_num="2.1", description="Piso porcelanato", unit="m²",
                      quantity=118.5, confidence=Confidence.CONFIRMADO,
                      origem="dxf_geom")
    itens, resumo = main._fundir_revisoes_do_cliente([novo], "pai123")

    assert not resumo.get("erro_leitura"), (
        "a fusão desistiu na leitura das revisões (%r) — o status e as linhas "
        "trocaram de lugar" % resumo.get("erro_leitura"))
    assert resumo["revisoes"] == 1 and resumo["casadas"] == 1, resumo
    assert novo.quantity == 250.0, (
        "a correção do cliente não entrou (ficou %r) — regra dura nº7"
        % novo.quantity)


def test_falha_de_verdade_na_leitura_das_revisoes_DEIXA_rastro(monkeypatch):
    """Controle do outro lado: um 500 de verdade tem que virar erro_leitura.

    Sem isto, um `_fundir_revisoes_do_cliente` que ignorasse o status passaria
    pelo teste acima.
    """
    import main

    monkeypatch.setattr(main, "_supa_rest_service",
                        _rest_falso({"item_reviews": (500, None)}))
    gritos = []
    monkeypatch.setattr(main, "_log_error",
                        lambda *a, **k: gritos.append((a, k)))

    _, resumo = main._fundir_revisoes_do_cliente([], "pai123")
    assert resumo.get("erro_leitura") == "HTTP 500", resumo
    assert gritos and gritos[0][1].get("severity") == "critical", gritos


# ══════════════════════════════════════════════════════════════════════════
#  E a varredura de FORMA, que cobre os outros ~9 pontos do arquivo
# ══════════════════════════════════════════════════════════════════════════
def test_nenhuma_FORMA_proibida_voltou_ao_arquivo():
    """🚨 2ª rodada (23/08): a 1ª versão disto só olhava
    `nome = _supa_rest_service(...)` e passou batido por
    `_n_rev_log = len(_supa_rest_service(...) or [])` — `len` de uma tupla é
    SEMPRE 2, e esse log vinha dizendo "itens tocados=2" em toda revisão
    concluída desde que nasceu.

    🪤 Este guarda é COMPLEMENTAR, não principal: ele pega forma nova em ponto
    que nenhum teste executa, e não pega inversão de nomes. Quem prova o
    comportamento são os dois consumidores acima.
    """
    src = _fonte()
    ruins = []
    dentro_do_helper = False
    for n, linha in enumerate(src.split("\n"), 1):
        if linha.startswith("def "):
            dentro_do_helper = linha.startswith("def _supa_rows(")
        if "_supa_rest_service(" not in linha:
            continue
        nu = linha.lstrip()
        if nu.startswith("#") or nu.startswith('"""') or nu.startswith("- ") or nu.startswith("* "):
            continue
        if "def _supa_rest_service(" in linha or dentro_do_helper:
            continue
        if _OK_UNPACK.match(linha) or _OK_SOLTA.match(linha):
            continue
        ruins.append("linha %d: %s" % (n, nu[:100]))
    assert not ruins, (
        "_supa_rest_service devolve (status, dados). Use _supa_rows(...) para as "
        "linhas, ou desempacote em dois nomes:\n  " + "\n  ".join(ruins))


def test_o_guarda_pegaria_a_forma_que_escapou():
    """Controle positivo — sem isto, um guarda que não pega nada passa por
    guarda que aprova tudo. Foi exatamente o que aconteceu na 1ª versão."""
    venenos = [
        '    _n = len(_supa_rest_service("GET", "x") or [])',
        '    rows = _supa_rest_service("GET", "x") or []',
        '    primeiro = (_supa_rest_service("GET", "x") or [{}])[0]',
        '    for r in _supa_rest_service("GET", "x"):',
        '    return _supa_rest_service("GET", "x")[0]',
    ]
    for v in venenos:
        assert not (_OK_UNPACK.match(v) or _OK_SOLTA.match(v)), "o guarda deixaria passar: " + v
    saudaveis = [
        '    _st, _rows = _supa_rest_service("GET", "x")',
        '        _supa_rest_service("PATCH", "projects", body=p)',
    ]
    for h in saudaveis:
        assert _OK_UNPACK.match(h) or _OK_SOLTA.match(h), "o guarda reprovaria código são: " + h
