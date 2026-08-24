"""_supa_rest_service devolve (status, dados) — ninguém pode tratar como lista.

🚨 23/08/2026: 11 pontos do main.py faziam `rows = _supa_rest_service(...) or []`
e depois `rows[0].get(...)`. Como o retorno é uma TUPLA, `rows[0]` virava o
inteiro 200 e o `.get` estourava AttributeError. Efeitos reais:
  - botão "Liberar pro cliente" respondia "Load failed" no Safari (o 500 sai
    sem cabeçalho CORS, e o navegador reporta como erro de rede);
  - a fusão das revisões do cliente (regra dura nº7) nunca rodou — o except
    engolia o erro.
Quem quer só as linhas usa `_supa_rows(...)`.
"""
import io
import os
import re

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Formas legítimas: desempacotar em dois nomes, ou chamar sem guardar o retorno
# (PATCH/POST fire-and-forget).
_OK_UNPACK = re.compile(r"^\s*[A-Za-z_]\w*\s*,\s*[A-Za-z_]\w*\s*=\s*_supa_rest_service\(")
_OK_SOLTA = re.compile(r"^\s*_supa_rest_service\(")


def _fonte():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def test_ninguem_usa_a_tupla_como_se_fosse_a_lista():
    """🚨 2ª rodada (23/08): a 1ª versão deste teste só olhava
    `nome = _supa_rest_service(...)` e passou batido por
    `_n_rev_log = len(_supa_rest_service(...) or [])` — `len` de uma tupla é
    SEMPRE 2, e esse log vinha dizendo "itens tocados=2" em toda revisão
    concluída desde que nasceu. Um guarda que só pega a forma que eu já
    consertei não guarda nada.
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


def test_supa_rows_existe_e_devolve_lista():
    src = _fonte()
    assert "def _supa_rows(" in src
    i = src.index("def _supa_rows(")
    corpo = src[i:i + 1200]
    assert "return _rows or []" in corpo
    assert "return []" in corpo   # falha de rede não derruba quem chamou
