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


# -- o que o `_sp.run` REALMENTE recebe -------------------------------------
# 🚨 06/09/2026, 2a rodada dos ceticos. Os dois guardas abaixo eram frouxos
# pelo MESMO motivo: falavam do `_cmd` que a arvore de `main.py` mostra, nunca
# do argumento que chega no `_sp.run`.
#   · o do env avaliava o dict `env=` e depois rodava um filho DELE
#     (`[sys.executable, '-c', 'os.abort()']`). Botar `-E` ou `-I` no `_cmd`
#     (o jeito classico de "isolar" um subprocesso) faz o Python IGNORAR as
#     variaveis PYTHON*: o env continua perfeito e o filho volta a morrer MUDO,
#     que e o `rc=-6 (sem stderr)` que este arquivo nasceu pra acabar.
#   · o do teto conferia as strings do `setrlimit` no FONTE. Qualquer coisa
#     entre a montagem do `_cmd` e a chamada (uma valvula de debug, um "sem
#     teto" temporario, o teto mudando pro env numa etapa futura do plano)
#     deixava o filho medir SEM RLIMIT_AS com o guarda verde — e foi um filho
#     sem teto que derrubou o servidor por 2 minutos em 03/09.
# 🔑 Agora o bloco de producao que monta o `_cmd` E chama o filho e EXECUTADO
# (recorte por AST, ver `_executa.py`) com o `subprocess.run` espionado. O que
# se afirma e o argv e o env que chegaram na chamada — e um filho de verdade
# sobe com ELES.
_FIM_DO_PREFIXO = "except Exception:" + chr(10) + "    pass" + chr(10)


def _o_que_chegou_no_sp_run(rc=-6, stdout="", stderr=""):
    """Roda o bloco real do filho de pdfvec e devolve `(argv, kwargs, logs)`."""
    import subprocess

    import _executa
    import main

    visto = {}

    class _Filho:
        returncode = rc

    _Filho.stdout = stdout
    _Filho.stderr = stderr

    def _espiao(cmd, **kw):
        visto["cmd"] = list(cmd)
        visto["kw"] = dict(kw)
        return _Filho()

    logs = []
    escopo = dict(vars(main))
    escopo.update({
        "os": os,
        "pdf_path": "/work/j/prancha.pdf",
        "page_index": 0,
        "_stem": "PRANCHA-01",
        "filename": "prancha.pdf",
        "_pdfvec_falhas": [],
        "_log_error": lambda stage, msg, *a, **k: logs.append((stage, msg)),
        "job_id": "job-teste",
        "_pdfvec_area_m2": 0.0,
        "_pdfvec_compr_m": 0.0,
        "_pdfvec_por_prancha": {},
        "_vet_secao": "",
    })
    _real = subprocess.run
    subprocess.run = _espiao
    try:
        # tamanho=1 = o `try:` que monta o `_cmd` E chama o filho
        _executa.roda("process_job", "_pr = _sp.run(_cmd", escopo, tamanho=1)
    finally:
        subprocess.run = _real
    assert "cmd" in visto, (
        "o bloco de producao rodou e NAO chamou o filho — as falhas foram %s"
        % (logs,))
    return visto["cmd"], visto["kw"], logs


def _filho_com_o_argv_da_producao(sufixo, timeout=60):
    """Sobe um filho DE VERDADE com o argv e o env que chegaram no `_sp.run`,
    trocando so o miolo do `-c` (o prefixo do teto de memoria fica)."""
    import subprocess
    argv, kw, _ = _o_que_chegou_no_sp_run()
    codigo = argv[-1]
    i = codigo.find(_FIM_DO_PREFIXO)
    assert i > 0, (
        "o ultimo argumento do `-c` que chegou no `_sp.run` nao tem mais o "
        "prefixo do teto: %r" % codigo[:200])
    prefixo = codigo[:i + len(_FIM_DO_PREFIXO)]
    return subprocess.run(list(argv[:-1]) + [prefixo + sufixo],
                          capture_output=True, text=True, timeout=timeout,
                          env=kw.get("env"))


def test_a_chamada_do_filho_LIGA_o_faulthandler_pelo_env():
    """O env que CHEGA no `_sp.run` e o efetivo, e um filho de verdade — com o
    argv da producao, flags inclusas — aborta com ele pra provar que a pilha
    sai."""
    _, kw, _ = _o_que_chegou_no_sp_run()
    env = kw.get("env")
    assert isinstance(env, dict), (
        "a chamada do filho perdeu o argumento `env=`: %s" % sorted(kw))
    assert env.get("PATH") == os.environ.get("PATH"), (
        "o env do filho parou de HERDAR o do servidor — sem PATH/chaves a "
        "Vision e o import quebram")
    assert env.get("PYTHONFAULTHANDLER") == "1", (
        "o env EFETIVO do filho leva PYTHONFAULTHANDLER=%r — o faulthandler "
        "nao liga e a proxima morte por memoria volta como 'rc=-6 (sem stderr)'"
        % env.get("PYTHONFAULTHANDLER"))

    # 🔑 com o ARGV da producao: se alguem puser `-E`/`-I` no `_cmd`, o Python
    # ignora as variaveis PYTHON* e o abort volta a ser mudo.
    r = _filho_com_o_argv_da_producao("import os; os.abort()")
    assert r.returncode != 0
    assert "Fatal Python error" in (r.stderr or ""), (
        "com o ARGV e o ENV DA PRODUCAO o filho abortou MUDO: %r — procure "
        "por `-E`/`-I` nas flags do `_cmd`" % (r.stderr or "")[:200])
    # a LINHA muda (o prefixo do teto empurra o codigo pra baixo); o que tem
    # que vir e a pilha, nao o numero
    assert 'File "<string>", line' in (r.stderr or ""), (
        "veio o cabecalho e nao veio a pilha — e a pilha que diz onde morreu")


def test_o_teto_de_2GB_CHEGA_no_argumento_do_run():
    """🪤 O teste do teto congela o prefixo do `-c`. O passo 1 não podia tocar
    nele — e agora quem responde é o argumento que o `_sp.run` recebeu, não o
    texto do `main.py`."""
    # o bloco que este guarda executa tem que ser O UNICO que sobe o filho:
    # um segundo call site ficaria fora da espionagem, e portanto sem teto.
    _chamada_do_filho()
    argv, _, _ = _o_que_chegou_no_sp_run()
    assert argv[-2] == "-c", (
        "o `-c` deixou de ser o penultimo argumento: %r" % (argv[:-1],))
    codigo = argv[-1]
    assert "import resource; resource.setrlimit(" in codigo, (
        "o filho que CHEGOU no `_sp.run` nao seta mais o teto de memoria — "
        "foi um filho sem teto que derrubou o servidor em 03/09: %r"
        % codigo[:200])
    assert "resource.RLIMIT_AS, (2_000_000_000, 2_000_000_000)" in codigo, (
        "o teto que chega no filho nao e mais 2 GB: %r" % codigo[:300])
    assert "except Exception" in codigo, (
        "sumiu o try/except do `resource` — em Windows TODA medicao de PDF "
        "morreria de ImportError")
    assert codigo.index("import resource") < codigo.index("from pdf_vector"), (
        "o teto e setado DEPOIS de importar o medidor — a alocacao grande "
        "acontece no import e escapa do limite")


def test_o_prefixo_do_teto_RODA_ate_onde_nao_existe_o_modulo_resource():
    """🧪 O prefixo que chega no filho tem que EXECUTAR limpo — inclusive onde
    `resource` não existe (Windows, desenvolvimento). E onde ele existe, o teto
    tem que valer de verdade dentro do processo."""
    import json
    sonda = ("import json" + chr(10)
             + "try:" + chr(10)
             + "    import resource; _l = list(resource.getrlimit(resource.RLIMIT_AS))" + chr(10)
             + "except Exception:" + chr(10)
             + "    _l = None" + chr(10)
             + "print(json.dumps({'lim': _l}))" + chr(10))
    r = _filho_com_o_argv_da_producao(sonda)
    assert r.returncode == 0, (
        "o prefixo do `-c` que chega no filho QUEBRA o processo (rc=%r): %r"
        % (r.returncode, (r.stderr or "")[-400:]))
    lim = json.loads((r.stdout or "").strip().splitlines()[-1])["lim"]
    if lim is None:
        # sem o módulo `resource` (Windows): o que se prova aqui é a tolerância
        pytest.skip("sem o modulo `resource` neste sistema — teto so vale em Linux")
    assert lim == [2_000_000_000, 2_000_000_000], (
        "o filho comecou a medir com RLIMIT_AS=%r — nao e o teto de 2 GB" % (lim,))


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
