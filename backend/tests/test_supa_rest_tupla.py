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


def _fonte():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def test_ninguem_atribui_a_tupla_a_uma_variavel_sozinha():
    src = _fonte()
    ruins = []
    for n, linha in enumerate(src.split("\n"), 1):
        if "_supa_rest_service(" not in linha:
            continue
        if linha.lstrip().startswith(("#", "def ", '"""')):
            continue
        antes_do_igual = linha.split("=")[0] if "=" in linha else ""
        m = re.search(r"([A-Za-z_]\w*)\s*=\s*\(?_supa_rest_service\(", linha)
        if m and "," not in antes_do_igual:
            ruins.append(f"linha {n}: {linha.strip()[:90]}")
    assert not ruins, (
        "Retorno de _supa_rest_service é (status, dados) e foi atribuído a uma "
        "variável só — use _supa_rows(...) ou desempacote:\n  " + "\n  ".join(ruins))


def test_supa_rows_existe_e_devolve_lista():
    src = _fonte()
    assert "def _supa_rows(" in src
    i = src.index("def _supa_rows(")
    corpo = src[i:i + 1200]
    assert "return _rows or []" in corpo
    assert "return []" in corpo   # falha de rede não derruba quem chamou
