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

import pytest

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
    """Um `_supa_rest_service` que devolve (status, linhas) envenenados.

    🪤 06/09: o espião guardava só `(method, path)` e cegava o repasse dos
    `**kw` — que é onde mora o `params={"job_id": "eq...."}` de 15 das 18
    chamadas reais de `_supa_rows`. Agora guarda os kwargs também.
    """
    def _f(method, path, **kw):
        if chamadas is not None:
            chamadas.append((method, str(path), dict(kw)))
        tabela = str(path).split("?")[0].lstrip("/")
        st, linhas = por_tabela.get(tabela, (200, []))
        return _Status(st), _Linhas(linhas or [])
    return _f


# ══════════════════════════════════════════════════════════════════════════
#  Consumidor 1 — `_supa_rows`, o helper que existe por causa do bug
# ══════════════════════════════════════════════════════════════════════════
def test_supa_rows_existe_e_devolve_lista(monkeypatch):
    """CHAMA `_supa_rows` de verdade e olha o que sai — e o que ENTRA.

    🚨 06/09: o filtro do projeto viaja nos `**kw`. Se `_supa_rows` parar de
    repassá-los, 15 das 18 chamadas reais do main.py passam a ler a TABELA
    INTEIRA sem `job_id`, e o `[0]` que vem depois é de um projeto qualquer —
    isolamento entre projetos (regra dura nº2) caindo em silêncio, ainda por
    cima com o teto de 1000 linhas do PostgREST cortando o resto. O guarda
    antigo só olhava a lista de saída e ficava verde nessa mutação.
    """
    import main

    linhas_do_banco = [{"id": "i-1", "description": "Piso porcelanato"},
                       {"id": "i-2", "description": "Laje maciça"}]
    vistos = []
    monkeypatch.setattr(main, "_supa_rest_service",
                        _rest_falso({"project_items": (200, linhas_do_banco)},
                                    vistos))

    filtro = {"job_id": "eq.job-01", "select": "id,description",
              "limit": "500"}
    r = main._supa_rows("GET", "project_items", params=filtro, timeout=7)

    assert isinstance(r, list), (
        "`_supa_rows` devolveu %r (%s) no lugar das linhas — é o STATUS "
        "vazando pelo desempacotamento invertido" % (r, type(r).__name__))
    assert [d["id"] for d in r] == ["i-1", "i-2"], r
    assert vistos == [("GET", "project_items",
                       {"params": filtro, "timeout": 7})], (
        "o que chegou ao banco foi %r — o filtro do projeto (e o select, e o "
        "limit) ficou pelo caminho: a consulta vira 'a tabela inteira'"
        % (vistos,))


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
#  Consumidores 3 a 7 — a inversão de nomes em QUALQUER um deles tem que doer
# ══════════════════════════════════════════════════════════════════════════
#  🪤 06/09: os dois guardas de execução acima cobriam UM consumidor cada.
#  Inverter o desempacotamento em qualquer um dos ~60 outros
#  `x, y = _supa_rest_service(...)` do main.py passava neste arquivo inteiro —
#  a mesma doença de 23/08, no ponto vizinho. Cada linha abaixo é um consumidor
#  REAL rodando com o serviço envenenado: o status sabe gritar quando é
#  percorrido/indexado e as linhas sabem gritar quando são comparadas com um
#  código HTTP. O que se cobra é o RESULTADO, porque três destes engolem
#  exceção e devolvem o valor de "falhou" caladinhos.
def _c_avisos_com(main):
    return main._avisos_com("job-01", "o complemento não deu certo")


def _c_entregavel_liberado(main):
    return main._entregavel_liberado("job-01")


def _c_memorial_salvo(main):
    return main._memorial_carregar_salvo("job-01")


def _c_revisoes_depois_de(main):
    return main._revisoes_depois_de("job-01", "2026-09-01T00:00:00Z")


def _c_paginador(main):
    return main._supa_rest_tudo("project_items", params={"job_id": "eq.job-01"})


_CONSUMIDORES = [
    # (apelido, banco por tabela, o que chamar, o que TEM que sair)
    ("_avisos_com",
     {"projects": (200, [{"warnings": ["área estimada por escala"]}])},
     _c_avisos_com,
     ["área estimada por escala", "o complemento não deu certo"]),
    ("_entregavel_liberado",
     {"projects": (200, [{"pagamento": "", "cobravel": True}])},
     _c_entregavel_liberado,
     (False, "aguardando_pagamento")),
    ("_memorial_carregar_salvo",
     {"project_memorial": (200, [{"conteudo": {"blocos": 3}}])},
     _c_memorial_salvo,
     {"blocos": 3}),
    ("_revisoes_depois_de",
     {"item_reviews": (200, [{"action": "edit", "item_id": "a"},
                             {"action": "edit", "item_id": "a"},
                             {"action": "reject", "item_id": "b"}])},
     _c_revisoes_depois_de,
     {"editados": 1, "excluidos": 1}),
    ("_supa_rest_tudo",
     {"project_items": (200, [{"id": "i-1"}, {"id": "i-2"}])},
     _c_paginador,
     (200, [{"id": "i-1"}, {"id": "i-2"}])),
]


@pytest.mark.parametrize("apelido,banco,chamar,esperado", _CONSUMIDORES,
                         ids=[c[0] for c in _CONSUMIDORES])
def test_outros_consumidores_leem_a_tupla_na_ORDEM_certa(
        monkeypatch, apelido, banco, chamar, esperado):
    """Inverter `st, rows` em qualquer um destes tem que REPROVAR aqui."""
    import main

    monkeypatch.setenv("COBRANCA_LIGADA", "1")
    monkeypatch.setattr(main, "_supa_rest_service", _rest_falso(banco))
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)

    saida = chamar(main)
    assert saida == esperado, (
        "%s devolveu %r em vez de %r — o status e as linhas trocaram de lugar "
        "(ou o erro foi engolido e virou o valor de 'falhou')"
        % (apelido, saida, esperado))


def test_a_varredura_de_consumidores_nao_encolheu():
    """Controle: alguém 'consertando' um teste chato apagando a linha dele do
    parametrize deixaria o buraco de volta sem deixar rastro."""
    assert len(_CONSUMIDORES) >= 5, (
        "a varredura de consumidores tem só %d — ela existe justamente porque "
        "UM consumidor não cobre os outros" % len(_CONSUMIDORES))


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
