# -*- coding: utf-8 -*-
"""Um PDF de 2,63 MB derrubou o servidor de TODOS os clientes.

🩸 03/09/2026, caso EDVALDO (job `7ddbccc1`), o maior lead B2B, avaliando o
produto no mesmo dia. Medido no Render (memory_usage, resolução 30 s):

    12:30:30 UTC ...... 94,6 MB
    12:31:00 .......... 350,7 MB
    12:31:30 ......... 1.366,7 MB
    12:32:00 ......... 3.107,8 MB   (72% do teto de 4 GiB — última amostra viva)
    12:33 e 12:34 .... instance_count = 0   ← o site ficou FORA por 2 minutos

Quem estivesse no site nesses dois minutos levou erro. Não foi só o job dele.

🔑 A CAUSA: o processo filho que mede a geometria do PDF rodava **sem teto de
memória**. O único freio era um cronômetro de 75 s — e cronômetro não limita
memória. Nessa rodada ele perdeu a corrida pro estouro por ~20 segundos; na
tentativa seguinte, ganhou por acaso (o filho morreu de timeout às 12:39:11 e a
memória caiu 2,25 GB de uma vez, SEM reinício de contêiner — que é a prova de
que os GB moravam no filho, não no servidor).

📏 A amplificação é o que assusta: **2,63 MB de arquivo viraram ~2,7 GB de RAM
(≈500×)**. Memória aqui não é proporcional a bytes, é proporcional a quantos
elementos vetoriais a prancha tem. Por isso o teto de 12 MB por arquivo que
existia não protege nada — este PDF tem 4,6× MENOS que ele.

🪤 TETO DE 2 GB, NÃO 1,5. A auditoria propôs 1,5 GB. Não medimos ainda o pico
das 109 medições que DÃO certo, e teto apertado mata trabalho legítimo. 2 GB já
teria impedido as duas quedas de hoje e deixa 2 GB de folga. Apertar depois,
com dado — nunca no chute.

🪤 `resource` é módulo só de Unix: em produção (Linux) o teto vale, no Windows o
try/except deixa passar. Sem isso, TODA medição de PDF morreria de ImportError
em desenvolvimento. Por isso o teste de comportamento abaixo só roda em Linux —
no CI, que é ubuntu.
"""
import ast
import io
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
_MAIN = os.path.join(_BACKEND, "main.py")


# ══════════════════════════════════════════════════════════════════════════
#  🧪 O comando REAL que o filho recebe — não o texto que o monta
# ══════════════════════════════════════════════════════════════════════════
# 🪤 06/09/2026: o guarda do teto conferia se o literal `RLIMIT_AS, (2_000_...`
# aparecia no fonte, perto do `_cmd = [...]`. Envolver as três linhas do prefixo
# num `("" if 1 else "...") +` deixa o literal exatamente onde ele procurava E
# tira o teto do `-c` que o filho executa — o guarda passava e o filho voltava a
# rodar sem teto, que é o caminho que derrubou o site por 2 minutos.
#
# 🔑 A pergunta certa não é "o texto existe?", é "o teto CHEGA ao filho?".
# `process_job` tem ~3.900 linhas e não dá pra chamar num teste; então a
# atribuição `_cmd = [...]` é levantada do PRÓPRIO fonte (AST, sem janela de
# tamanho fixo) e EXECUTADA — o que sai é o argv de verdade.
def _no_unico(pred, oque):
    tree = ast.parse(io.open(_MAIN, encoding="utf-8").read())
    achados = [n for n in ast.walk(tree) if pred(n)]
    assert len(achados) == 1, (
        "esperava 1 %s em main.py, achei %d — o guarda perdeu o alvo"
        % (oque, len(achados)))
    return achados[0]


def _argv_real_do_filho():
    """Executa a atribuição `_cmd = [...]` de main.py e devolve o argv."""
    no = _no_unico(
        lambda n: isinstance(n, ast.Assign) and len(n.targets) == 1
        and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "_cmd",
        "atribuição de _cmd")

    class _Sysv:                       # o `sys` que main.py importa como _sysv
        executable = sys.executable

    ns = {"os": os, "_sysv": _Sysv, "__file__": _MAIN,
          "pdf_path": "/tmp/prancha.pdf", "page_index": 0}
    exec(compile(ast.unparse(no), "<_cmd de main.py>", "exec"), ns)
    return ns["_cmd"]


def _prefixo_real():
    """Só o pedaço do `-c` que vem ANTES da medição: é ele que põe o teto."""
    codigo = _argv_real_do_filho()[2]
    marco = "import sys, json"
    assert marco in codigo, (
        "o comando do filho mudou de forma — não achei onde a medição começa")
    return codigo[:codigo.index(marco)]


# o prefixo que o filho executa — LEVANTADO DO CÓDIGO DE PRODUÇÃO, não copiado.
# 🪤 A versão anterior era uma cópia colada aqui: os testes de comportamento
# provavam que UM texto limita memória, nunca que era ESSE que o filho recebia.
_PREFIXO = _prefixo_real()


# ── O comportamento, no sistema que importa ────────────────────────────────
@pytest.mark.skipif(not sys.platform.startswith("linux"),
                    reason="RLIMIT_AS só existe no Unix; produção é Linux")
def test_o_filho_MORRE_em_vez_de_derrubar_o_servidor():
    """🩸 O teste que vale. Alocar acima do teto tem que matar o FILHO."""
    r = subprocess.run(
        [sys.executable, "-c", _PREFIXO + "x = bytearray(3_000_000_000)"],
        capture_output=True, text=True, timeout=120)
    assert r.returncode != 0, (
        "o filho alocou 3 GB sem morrer — o teto não está valendo, e o próximo "
        "PDF denso derruba o servidor de todos os clientes de novo")
    assert "MemoryError" in (r.stderr or ""), r.stderr[-300:]


@pytest.mark.skipif(not sys.platform.startswith("linux"),
                    reason="RLIMIT_AS só existe no Unix")
def test_CONTROLE_o_teto_NAO_atrapalha_medicao_normal():
    """🧪 Teto que mata trabalho legítimo é pior que teto nenhum. 50 MB é a
    ordem de grandeza de uma prancha comum e tem que passar."""
    r = subprocess.run(
        [sys.executable, "-c", _PREFIXO + "x = bytearray(50_000_000); print(len(x))"],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-300:]
    assert "50000000" in r.stdout


def test_CONTROLE_o_prefixo_NAO_estoura_em_sistema_sem_resource():
    """🪤 No Windows `import resource` levanta ImportError. Se o try/except
    sumir, toda medição de PDF morre em desenvolvimento."""
    r = subprocess.run([sys.executable, "-c", _PREFIXO + "print('vivo')"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "vivo" in r.stdout, r.stderr[-200:]


# ── O código de produção ───────────────────────────────────────────────────
def test_a_chamada_de_medicao_LEVA_o_teto(tmp_path):
    """🩸 O teto tem que CHEGAR ao filho — não basta existir no arquivo.

    O filho de verdade é rodado aqui, com um `resource` de brinquedo na frente
    do da máquina (PYTHONPATH), que só conta o que recebeu. Assim o teste vale
    igual no Windows (onde `resource` não existe) e no Linux do CI, e mede o
    que importa: o valor que o kernel receberia."""
    prefixo = _prefixo_real()
    espiao = tmp_path / "resource.py"
    espiao.write_text(
        "RLIMIT_AS = 9\n"
        "def setrlimit(qual, limites):\n"
        "    import sys\n"
        "    sys.stderr.write('SETRLIMIT %r %r\\n' % (qual, tuple(limites)))\n",
        encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-c", prefixo + "print('o filho rodou')"],
        capture_output=True, text=True, timeout=60,
        env={**os.environ, "PYTHONPATH": str(tmp_path)})
    assert "o filho rodou" in r.stdout, (
        "o prefixo do teto quebrou o filho: %s" % (r.stderr or "")[-400:])
    assert "SETRLIMIT 9 (2000000000, 2000000000)" in r.stderr, (
        "o filho da medição de PDF NÃO recebeu o teto de 2 GB — é o caminho "
        "que derrubou o site por 2 minutos em 03/09. stderr: %r"
        % (r.stderr or "")[-400:])


def test_o_teto_e_TOLERANTE_a_plataforma():
    i = _SRC.find("_cmd = [_sysv.executable")
    trecho = _SRC[i:i + 600]
    assert "try:" in trecho and "except Exception" in trecho, (
        "o import de `resource` ficou sem proteção — quebra em Windows")


def test_o_ramo_que_AVISA_o_cliente_continua_de_pe():
    """🔑 O conserto não precisou de tratamento novo justamente porque este
    ramo já existia: filho com rc≠0 vira log + aviso ao cliente.

    🪤 06/09: o guarda antigo procurava três strings no fonte INTEIRO — e as
    três existem em OUTROS ramos do mesmo arquivo ('pdfvec:filho-morreu'
    aparece 3×, `_pdfvec_falhas.append(` 4×). Esvaziar este ramo (`pass` e o
    corpo debaixo de `if False:`) deixava o guarda verde e a prancha morta
    voltava a sumir em silêncio. Agora o ramo é EXECUTADO: filho com rc=-6
    entra, e o que se confere é o que ele DEIXOU — a falha na lista que vira
    aviso do cliente e a linha de log."""
    ramo = _no_unico(
        lambda n: isinstance(n, ast.If) and _teste_do_if(n) == "_pr.returncode != 0",
        "ramo `if _pr.returncode != 0:`")

    def _rodar(rc):
        falhas, logs = [], []

        class _PR:
            returncode = rc
            stderr = "Fatal Python error: Cannot allocate memory\n"
            stdout = ""

        ns = {"_pr": _PR, "_pdfvec_falhas": falhas, "_stem": "prancha_p0",
              "filename": "planta.pdf", "pdf_path": "/tmp/planta.pdf",
              "page_index": 0, "job_id": "job-de-teste",
              "_log_error": lambda *a, **k: logs.append((a, k))}
        exec(compile(ast.Module(body=[ramo], type_ignores=[]), "<ramo>", "exec"), ns)
        return falhas, logs

    falhas, logs = _rodar(-6)
    assert falhas, (
        "o filho morreu (rc=-6) e NADA entrou em `_pdfvec_falhas` — a prancha "
        "some da medição sem o cliente ficar sabendo")
    assert falhas[0]["motivo"] == "processo" and falhas[0]["rc"] == -6, falhas[0]
    assert falhas[0]["arquivo"] == "planta.pdf", (
        "o aviso não diz QUAL prancha morreu")
    assert logs and logs[0][0][0] == "pdfvec:filho-morreu", (
        "o filho morreu e não sobrou linha de log — o traceback foi pro lixo")
    assert "Cannot allocate memory" in logs[0][0][1], (
        "o log não carrega o stderr do filho: sem ele não dá pra saber se "
        "morreu de memória ou de outra coisa")

    # 🧪 controle negativo: filho SÃO não pode gerar aviso nenhum
    falhas_ok, logs_ok = _rodar(0)
    assert not falhas_ok and not logs_ok, (
        "prancha medida com sucesso virou aviso de falha pro cliente")


def _teste_do_if(no):
    try:
        return ast.unparse(no.test)
    except Exception:
        return ""


def test_o_cronometro_NAO_foi_subido_junto():
    """🚨 A ordem importa e a auditoria foi explícita: subir o timeout ANTES
    do teto de memória PIORA — foram os 75 s que impediram a segunda queda,
    às 12:39. Só depois deste teto estar rodando em produção é que dá pra
    discutir tempo maior."""
    assert "timeout=75" in _SRC, (
        "o cronômetro da medição mudou no mesmo commit do teto de memória — "
        "as duas coisas juntas não dá pra atribuir efeito a nenhuma")


def test_CONTROLE_a_checagem_do_teto_sabe_REPROVAR():
    falso = '_cmd = [_sysv.executable, "-c", ("import sys, json; ...")]'
    assert "RLIMIT_AS" not in falso
