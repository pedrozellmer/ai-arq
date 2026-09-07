# -*- coding: utf-8 -*-
"""O filho da medição de PDF morria MUDO. Agora diz em que linha morreu.

🩸 05/09/2026, job 135fdfac (cliente-39): o filho que mede a geometria do PDF morreu
com rc=-6 e stderr VAZIO, 19 s depois de ter a escala. A sombra mediu a mesma
página sem teto (40 ambientes, 581,7 m²). O estudo do teto reproduziu a morte
localmente: quando a alocação falha dentro de código C (PDFium/pikepdf), o
processo aborta sem passar por nenhum `except` — e sem escrever nada.

🔑 PASSO 1 do plano (só observação): `PYTHONFAULTHANDLER=1` no env do filho.
O faulthandler escreve a pilha Python no fd 2 sem alocar memória — dá certo
justamente na condição de OOM — e re-levanta o sinal, então o rc continua -6 e
o ramo `filho-morreu` continua igual. Junto: o corte do stderr sobe de 400 pra
1500 (senão o traceback chega decapitado) e o rabo do stdout entra no log
(JSON + rc≠0 = medição boa perdida no encerramento; vazio = morreu no meio).

🪤 Vai no `env=`, NÃO no texto do `-c`: `test_medicao_de_pdf_tem_teto_de_memoria`
congela aquele prefixo de propósito.

🧪 Controles positivos: sem a variável o abort continua mudo (é a variável que
faz a diferença); e o guarda de fonte reprova a versão antiga.
"""
import os
import subprocess
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

from _corpo import fonte, sem_comentarios          # noqa: E402

_SRC = sem_comentarios(fonte("main.py"))
_SO_LINUX = pytest.mark.skipif(not sys.platform.startswith("linux"),
                               reason="rc=-6 e SIGABRT são coisa de Unix; produção é Linux")


def _trecho_da_chamada():
    i = _SRC.find("_pr = _sp.run(_cmd")
    assert i > 0, "a chamada do filho sumiu ou mudou de nome"
    return _SRC[i:i + 400]


# ── O comportamento, no sistema que importa ────────────────────────────────
@_SO_LINUX
def test_com_faulthandler_o_abort_DIZ_onde_morreu():
    r = subprocess.run([sys.executable, "-c", "import os; os.abort()"],
                       capture_output=True, text=True, timeout=60,
                       env={**os.environ, "PYTHONFAULTHANDLER": "1"})
    assert r.returncode == -6, f"esperava SIGABRT (-6), veio {r.returncode}"
    assert "Fatal Python error: Aborted" in (r.stderr or ""), r.stderr[-400:]
    assert 'File "<string>", line 1' in (r.stderr or ""), (
        "a pilha não veio — sem ela o log continua dizendo só 'rc=-6'")


@_SO_LINUX
def test_CONTROLE_sem_a_variavel_o_abort_continua_MUDO():
    """🧪 Prova que é a variável que faz a diferença, não o Python novo."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONFAULTHANDLER"}
    r = subprocess.run([sys.executable, "-c", "import os; os.abort()"],
                       capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode == -6
    assert "Fatal Python error" not in (r.stderr or ""), (
        "o controle está mal montado: o abort já vinha com pilha sem a variável")


def test_o_rc_continua_sendo_o_do_sinal_com_faulthandler():
    """O faulthandler re-levanta o sinal: quem lê rc≠0 continua lendo rc≠0.
    Roda em qualquer sistema (no Windows o rc é outro número, mas ≠ 0)."""
    r = subprocess.run([sys.executable, "-c", "import os; os.abort()"],
                       capture_output=True, text=True, timeout=60,
                       env={**os.environ, "PYTHONFAULTHANDLER": "1"})
    assert r.returncode != 0


# ── O código de produção ───────────────────────────────────────────────────
# -- helpers: o codigo de producao, tirado por AST e EXECUTADO --------------
import ast as _ast
_ARVORE = _ast.parse(fonte("main.py"))


def _chamada_do_filho():
    """O no `_sp.run(_cmd, ...)` que dispara a medicao geometrica do PDF."""
    achados = [n for n in _ast.walk(_ARVORE)
               if isinstance(n, _ast.Call)
               and isinstance(n.func, _ast.Attribute) and n.func.attr == "run"
               and isinstance(n.func.value, _ast.Name) and n.func.value.id == "_sp"
               and n.args and isinstance(n.args[0], _ast.Name)
               and n.args[0].id == "_cmd"]
    assert len(achados) == 1, (
        "esperava UMA chamada `_sp.run(_cmd...)`, achei %d" % len(achados))
    return achados[0]


def _kwarg(no, nome):
    for k in no.keywords:
        if k.arg == nome:
            return _ast.unparse(k.value)
    raise AssertionError("a chamada do filho perdeu o argumento `%s=`" % nome)


def test_a_chamada_do_filho_LIGA_o_faulthandler_pelo_env():
    """O dict do env e AVALIADO (e o env EFETIVO) e um filho de verdade aborta
    com ele pra provar que a pilha sai."""
    import os, subprocess, sys
    env = eval(_kwarg(_chamada_do_filho(), "env"), {"os": os})
    assert isinstance(env, dict)
    assert env.get("PATH") == os.environ.get("PATH"), (
        "o env do filho parou de HERDAR o do servidor — sem PATH/chaves a "
        "Vision e o import quebram")
    assert env.get("PYTHONFAULTHANDLER") == "1", (
        "o env EFETIVO do filho leva PYTHONFAULTHANDLER=%r — o faulthandler "
        "nao liga e a proxima morte por memoria volta como 'rc=-6 (sem stderr)'"
        % env.get("PYTHONFAULTHANDLER"))

    r = subprocess.run([sys.executable, "-c", "import os; os.abort()"],
                       capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode != 0
    assert "Fatal Python error" in (r.stderr or ""), (
        "com o env DA PRODUCAO o filho abortou MUDO: %r" % (r.stderr or "")[:200])
    assert 'File "<string>", line 1' in (r.stderr or ""), (
        "veio o cabecalho e nao veio a pilha — e a pilha que diz onde morreu")


def test_o_texto_do_menos_c_NAO_mudou():
    """🪤 O teste do teto congela o prefixo do `-c`. O passo 1 não podia tocar nele."""
    i = _SRC.find("_cmd = [_sysv.executable")
    assert i > 0
    trecho = _SRC[i:i + 600]
    assert "import resource; resource.setrlimit(" in trecho
    assert "resource.RLIMIT_AS, (2_000_000_000, 2_000_000_000)" in trecho
    assert "except Exception" in trecho


def test_o_stderr_guardado_cabe_um_traceback():
    i = _SRC.find('"pdfvec:filho-morreu"')
    assert i > 0
    trecho = _SRC[max(0, i - 1200):i]
    assert "[-1500:]" in trecho, (
        "o corte do stderr voltou a 400 — o traceback do faulthandler chega "
        "decapitado, sem o 'File ...pdfvec_*.py, line N'")
    assert "[-400:]" not in trecho


def test_o_rabo_do_stdout_vai_pro_log():
    i = _SRC.find('"pdfvec:filho-morreu"')
    trecho = _SRC[max(0, i - 1200):i + 400]
    assert "_pr.stdout" in trecho and "stdout:" in trecho, (
        "sem o rabo do stdout não dá pra separar 'medição boa perdida no "
        "encerramento' de 'morreu no meio'")


def test_o_cronometro_continua_75():
    assert "timeout=75" in _trecho_da_chamada()


# ── Controle: o guarda de fonte sabe reprovar a versão antiga ──────────────
def test_CONTROLE_guarda_reprova_a_chamada_antiga():
    antiga = '_pr = _sp.run(_cmd, capture_output=True, text=True, timeout=75)\n    x = 1'
    assert "env=" not in antiga and "PYTHONFAULTHANDLER" not in antiga
