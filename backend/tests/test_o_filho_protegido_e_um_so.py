# -*- coding: utf-8 -*-
"""Trabalho que aloca sem limite roda em FILHO — e a receita é UMA só.

🩸 09/09/2026. Em 03/09 um PDF de 2,63 MB fez a medição vetorial ir de 94,6 MB
a 3.107,8 MB e o serviço ficou com **ZERO instância por 2 minutos**. A memória é
proporcional a quantos elementos vetoriais a prancha tem (~500× medido), não ao
tamanho do arquivo — teto de MB não protege nada.

A produção foi consertada naquele dia. Nos seis dias seguintes descobriu-se que
a MESMA decisão existia em mais dois lugares sem o conserto:

  1. a SOMBRA (`pdf_vector._run`) — medindo em thread do servidor, sem teto;
  2. `POST /api/estimate-price` — **rota PÚBLICA, sem login**, mandando
     `precheck_warnings` (que abre PDF com pdfplumber) pro threadpool do
     servidor, protegida só por um `asyncio.wait_for` que **não protege nada**:
     ele para de ESPERAR, a thread segue viva alocando, porque não dá pra matar
     thread em Python.

🪤 E ao consertar a sombra eu escrevi uma SEGUNDA CÓPIA da receita. Três cópias
da mesma decisão é exatamente a doença: conserta-se um lado e o cliente recebe o
outro. Este arquivo guarda o lado único (`filho_protegido`) e, sobretudo, a
NÃO-DIVERGÊNCIA entre ele e o filho da produção, que ainda não migrou.
"""
import ast
import io
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import filho_protegido as fp  # noqa: E402
import pricing  # noqa: E402


def _fonte(nome):
    return io.open(os.path.join(_BACKEND, nome), encoding="utf-8").read()


# ══════════════════════════════════════════════════════════════════════════
#  🔑 A porta PÚBLICA não mede dentro do servidor
# ══════════════════════════════════════════════════════════════════════════
def test_a_rota_publica_de_preco_NAO_chama_o_precheck_direto():
    """🩸 O defeito em pessoa, e o pior dos três: sem login, qualquer pessoa
    de fora podia mandar a prancha que derruba o site.

    🔑 Ancorado na AST do `main.py`: comentário citando `precheck_warnings`
    (e este arquivo cita de propósito) não pode fazer isto passar.
    """
    # 🪤 Procuro o NOME, não a CHAMADA. O defeito original era exatamente
    # `run_in_threadpool(precheck_warnings, saved_paths)` — a função PASSADA
    # como argumento, que não é um `ast.Call` dela. Um guarda que só olhasse
    # chamada passaria verde com o defeito na cara.
    arvore = ast.parse(_fonte("main.py"))
    diretas = sorted(n.lineno for n in ast.walk(arvore)
                     if (isinstance(n, ast.Name) and n.id == "precheck_warnings")
                     or (isinstance(n, ast.Attribute) and n.attr == "precheck_warnings")
                     or (isinstance(n, ast.alias) and n.name == "precheck_warnings"))
    assert not diretas, (
        "`precheck_warnings` aparece no processo do servidor (linhas %s). "
        "Ele abre PDF com pdfplumber e aloca proporcional aos elementos "
        "vetoriais da prancha. Use `precheck_em_filho`." % diretas)


def test_a_rota_publica_USA_o_filho():
    """🪤 Procurar CHAMADA aqui não funciona, e eu caí nessa: a função é
    PASSADA como argumento (`run_in_threadpool(precheck_em_filho, ...)`), então
    ela é um `Name`, não um `Call`. É a mesma armadilha que já me pegou em
    `feedback_guarda_que_procura_chamada_nao_ve_argumento`: cobertura por NOME,
    não por forma de uso."""
    arvore = ast.parse(_fonte("main.py"))
    usa = [n.lineno for n in ast.walk(arvore)
           if isinstance(n, ast.Name) and n.id == "precheck_em_filho"]
    assert usa, "a rota de preço não usa `precheck_em_filho` em lugar nenhum"


# ══════════════════════════════════════════════════════════════════════════
#  🔑 A receita é UMA — e a produção não pode divergir dela
# ══════════════════════════════════════════════════════════════════════════
def test_so_o_filho_protegido_MONTA_a_receita_do_teto():
    """🪤 Guarda contra a doença, não contra o sintoma. Quem escrever uma
    QUARTA cópia do `setrlimit` num módulo novo reprova aqui.

    ⚠️ `main.py` é a exceção NOMEADA e datada: o filho da medição vetorial de
    produção está entrelaçado com `_pdfvec_falhas`, seis diagnósticos de saída
    muda e telemetria por etapa, tudo provado em produção. Migrar junto seria
    trocar risco conhecido por risco novo. O que não pode é DIVERGIR — os dois
    testes abaixo cuidam disso.
    """
    import glob
    culpados = []
    for caminho in glob.glob(os.path.join(_BACKEND, "*.py")):
        nome = os.path.basename(caminho)
        if nome in ("filho_protegido.py", "main.py"):
            continue
        arv = ast.parse(io.open(caminho, encoding="utf-8").read())
        for n in ast.walk(arv):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) \
                    and "setrlimit" in n.value:
                culpados.append("%s:%d" % (nome, n.lineno))
    assert not culpados, (
        "cópia nova da receita do teto em %s — a receita mora em "
        "`filho_protegido`. Três cópias já custaram seis dias de risco aberto."
        % culpados)


def test_o_teto_da_producao_e_o_MESMO_do_filho_protegido():
    """🚨 O risco real não é a duplicação, é a DIVERGÊNCIA: alguém sobe o teto
    num lado e o outro continua matando medição legítima (ou deixando passar)."""
    fonte = _fonte("main.py")
    assert "2_000_000_000" in fonte, (
        "o filho da produção mudou o teto e o `filho_protegido` ficou pra trás")
    assert fp.RLIMIT_BYTES == 2_000_000_000, fp.RLIMIT_BYTES


def _envs_de_subprocesso(fonte):
    """Chaves de cada `env={...}` passado a um subprocess.run no fonte.

    🪤 Ancorado na AST porque a 1ª versão procurava a PALAVRA no texto — e a
    mutação passou batida: os comentários que EXPLICAM por que
    `PYTHONFAULTHANDLER` existe contêm a palavra. Tirar a chave do dicionário
    de verdade não mudava nada pro guarda. É a quinta vez que prosa citando
    código engana um guarda meu.
    """
    fora = []
    for n in ast.walk(ast.parse(fonte)):
        if not isinstance(n, ast.Call):
            continue
        if (getattr(n.func, "attr", None) or getattr(n.func, "id", None)) != "run":
            continue
        for kw in n.keywords:
            if kw.arg != "env" or not isinstance(kw.value, ast.Dict):
                continue
            fora.append({k.value for k in kw.value.keys
                         if isinstance(k, ast.Constant) and isinstance(k.value, str)})
    return fora


@pytest.mark.parametrize("chave", ["PYTHONFAULTHANDLER", "OPENBLAS_NUM_THREADS",
                                   "MALLOC_ARENA_MAX"])
def test_o_env_da_producao_e_o_MESMO(chave):
    """🪤 Cada uma dessas tem um motivo MEDIDO: sem faulthandler a morte em
    código C sai com stderr vazio; sem os outros dois o OpenBLAS reserva >1 GB
    de endereço virtual que nunca vira RAM e o RLIMIT_AS mata medição boa."""
    assert chave in fp.ENV_DO_FILHO, chave
    envs = _envs_de_subprocesso(_fonte("main.py"))
    completos = [e for e in envs if set(fp.ENV_DO_FILHO) <= e]
    assert completos, (
        "nenhum subprocess.run do main.py passa a receita completa %s — o "
        "filho da produção perdeu %r e os dois lados divergiram"
        % (sorted(fp.ENV_DO_FILHO), chave))


def test_CONTROLE_o_leitor_de_env_ACHA_a_chave_removida():
    """🧪 Prova que o predicado reprova: o mesmo fonte sem uma chave."""
    com = 'subprocess.run(c, env={**os.environ, "PYTHONFAULTHANDLER": "1", "OPENBLAS_NUM_THREADS": "1", "MALLOC_ARENA_MAX": "2"})'
    sem = 'subprocess.run(c, env={**os.environ, "OPENBLAS_NUM_THREADS": "1", "MALLOC_ARENA_MAX": "2"})'
    assert [e for e in _envs_de_subprocesso(com) if set(fp.ENV_DO_FILHO) <= e]
    assert not [e for e in _envs_de_subprocesso(sem) if set(fp.ENV_DO_FILHO) <= e]


def test_o_teto_vem_ANTES_de_qualquer_import_no_corpo():
    """🩸 Ordem é tudo: teto depois do import que aloca é decorativo."""
    linhas = fp.prefixo_do_teto()
    assert "setrlimit" in linhas[1] and "RLIMIT_AS" in linhas[1], linhas
    assert linhas[2].startswith("except"), (
        "sumiu o `except` — no Windows não existe `resource` e o filho morreria "
        "antes de trabalhar: %r" % linhas)
    montado = chr(10).join(fp.prefixo_do_teto() + ["import numpy"])
    assert montado.index("setrlimit") < montado.index("import numpy")


# ══════════════════════════════════════════════════════════════════════════
#  O contrato: morte vira recusa registrada, nunca queda de quem chamou
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("como_morre", ["rc", "timeout", "json_quebrado", "explode"])
def test_filho_que_morre_devolve_SKIP_e_nao_levanta(monkeypatch, como_morre):
    import subprocess

    class _F:
        def __init__(s, rc, out, err):
            s.returncode, s.stdout, s.stderr = rc, out, err

    def _run(cmd, **kw):
        if como_morre == "rc":
            return _F(-9, "", "Killed")
        if como_morre == "timeout":
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout") or 1)
        if como_morre == "json_quebrado":
            return _F(0, "{isso nao e json", "")
        raise OSError("fork falhou")

    monkeypatch.setattr(subprocess, "run", _run)
    r = fp.rodar(["pass"], [], 5, rotulo="filho de teste")
    assert isinstance(r, dict) and r.get("skip"), r
    assert "filho de teste" in r["skip"], (
        "o rótulo sumiu do skip — sem ele o log não diz QUAL filho morreu: %r" % r)


def test_o_precheck_no_filho_devolve_LISTA_VAZIA_quando_o_filho_morre(monkeypatch):
    """🔑 Best-effort: o preço sai igual, como sempre saiu quando o precheck
    falhava. Aviso é acessório; derrubar a tela do cliente não é."""
    monkeypatch.setattr(fp, "rodar",
                        lambda **k: {"skip": "filho do precheck morreu"})
    assert pricing.precheck_em_filho(["a.pdf"]) == []


def test_CONTROLE_o_precheck_no_filho_ENTREGA_os_avisos(monkeypatch):
    """🧪 Sem isto, um `precheck_em_filho` que devolvesse [] sempre passaria em
    todos os testes acima e o cliente nunca receberia aviso nenhum."""
    monkeypatch.setattr(fp, "rodar", lambda **k: ["⚠ x.pdf: parece escaneado"])
    assert pricing.precheck_em_filho(["x.pdf"]) == ["⚠ x.pdf: parece escaneado"]


def test_CONTROLE_o_filho_que_DA_CERTO_devolve_o_JSON(monkeypatch):
    import subprocess

    class _Ok:
        returncode = 0
        stdout = '[llm_cache] ruido antes\n{"ok": 1}'
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Ok())
    assert fp.rodar(["pass"], [], 5) == {"ok": 1}, (
        "ruído antes do JSON matou a leitura — tem que ler a ÚLTIMA linha")


def test_os_argumentos_vao_por_ARGV_e_nao_embutidos(monkeypatch):
    """🪤 Caminho com aspa simples fecharia a string do fonte e o filho morreria
    de SyntaxError — que este runner arquivaria como "morreu", indistinguível
    de estouro de memória. Defeito disfarçado do defeito."""
    import subprocess
    cap = {}

    class _Ok:
        returncode = 0
        stdout = "{}"
        stderr = ""

    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: (cap.update(cmd=cmd, env=kw.get("env")), _Ok())[1])
    caminho = "/tmp/pe d'agua/planta 1:50.pdf"
    fp.rodar(["import sys"], [caminho, 7], 5)
    codigo = cap["cmd"][2]
    assert "pe d'agua" not in codigo, codigo
    compile(codigo, "<filho>", "exec")
    assert cap["cmd"][-2] == caminho and cap["cmd"][-1] == "7", cap["cmd"]
    for k, v in fp.ENV_DO_FILHO.items():
        assert cap["env"].get(k) == v, (k, cap["env"].get(k))
