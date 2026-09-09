# -*- coding: utf-8 -*-
"""A sombra media DENTRO do servidor — o mesmo risco que derrubou o serviço.

🩸 09/09/2026. O caminho de PRODUÇÃO roda a medição vetorial num processo
FILHO com `RLIMIT_AS` de 2 GB. Esse conserto é de 03/09, e o comentário dele
registra por que existe:

    "ESTE FILHO DERRUBOU O SERVIDOR DE TODOS. PDF de 2,63 MB: a memória foi de
     94,6 MB → 3.107,8 MB contra teto de 4 GiB, e o serviço ficou com ZERO
     instância por 2 minutos. Quem estivesse no site levou erro.
     📏 2,63 MB viraram ~2,7 GB de RAM (≈500×). Memória não é proporcional a
     bytes, é proporcional a quantos elementos vetoriais a prancha tem — e o
     teto de 12 MB por arquivo NÃO PROTEGE NADA (este PDF tem 4,6× menos)."

🚨 A SOMBRA NUNCA RECEBEU ESSE CONSERTO. Ela chamava `_measure_page` direto,
numa thread daemon DO SERVIDOR — sem filho, sem RLIMIT — protegida só pelo
teto de 12 MB que a própria casa documentou como inútil. Mesmo risco, aberto,
por seis dias.

🪤 É a SEXTA vez em 09/09 que um conserto foi aplicado num lado só. As outras:
o marcador de página, o `qty = 1`, o conselho de reprocessar, os avisos da IA,
e `workstations`/`departments`.

📏 O teto subiu de 12 pra 80 MB porque 12 excluía 32 páginas em 6 jobs — 16%
das páginas da sombra. Como a sombra é o INSTRUMENTO com que eu meço cobertura
de escala, toda medição minha estava enviesada pro subconjunto de arquivos
pequenos, e eu não sabia.
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

import pdf_vector  # noqa: E402


def _ast_pdf_vector():
    return ast.parse(io.open(os.path.join(_BACKEND, "pdf_vector.py"),
                             encoding="utf-8").read())


# ══════════════════════════════════════════════════════════════════════════
#  🔑 O invariante: a sombra NÃO mede dentro do servidor
# ══════════════════════════════════════════════════════════════════════════
def test_o_laco_da_sombra_NAO_chama_a_medicao_direto():
    """🩸 O defeito em pessoa. `_run` roda numa thread DO SERVIDOR; chamar
    `_measure_page` ali aloca no processo que atende todos os clientes."""
    arvore = _ast_pdf_vector()
    run = next((n for n in arvore.body
                if isinstance(n, ast.FunctionDef) and n.name == "_run"), None)
    assert run is not None, "o `_run` da sombra sumiu"
    diretas = [n.lineno for n in ast.walk(run)
               if isinstance(n, ast.Call)
               and (getattr(n.func, "id", None) or getattr(n.func, "attr", None))
               == "_measure_page"]
    assert not diretas, (
        "a sombra voltou a chamar `_measure_page` DENTRO do servidor (linhas "
        "%s). Um cronômetro não limita memória; só o kernel limita — foi a "
        "lição da queda de 03/09. Use `medir_pagina_em_filho`." % diretas)


def test_o_laco_da_sombra_USA_o_filho_protegido():
    arvore = _ast_pdf_vector()
    run = next(n for n in arvore.body
               if isinstance(n, ast.FunctionDef) and n.name == "_run")
    usa = [n for n in ast.walk(run)
           if isinstance(n, ast.Call)
           and (getattr(n.func, "id", None) or getattr(n.func, "attr", None))
           == "medir_pagina_em_filho"]
    assert usa, "a sombra não chama `medir_pagina_em_filho`"


def test_CONTROLE_a_leitura_por_AST_nao_casa_com_comentario(tmp_path):
    """🧪 O docstring deste arquivo CITA `_measure_page` de propósito, pra
    explicar o defeito. Se o guarda lesse texto, documentar seria proibido."""
    p = tmp_path / "so_texto.py"
    p.write_text('def _run():\n    """chama _measure_page e é errado."""\n'
                 "    # _measure_page(a, b, c)\n    return 1\n", encoding="utf-8")
    arv = ast.parse(p.read_text(encoding="utf-8"))
    chamadas = [n for n in ast.walk(arv) if isinstance(n, ast.Call)]
    assert not chamadas, "a leitura por AST casou com comentário/docstring"


# ══════════════════════════════════════════════════════════════════════════
#  O filho: teto do KERNEL, e nunca derruba quem chamou
# ══════════════════════════════════════════════════════════════════════════
def _comando_do_filho(monkeypatch, pdf="x.pdf", pagina=0):
    """Captura o `-c` que o runner monta, sem rodar processo nenhum."""
    capturado = {}

    class _Falso:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def _run_falso(cmd, **kw):
        capturado["cmd"] = cmd
        capturado["env"] = kw.get("env") or {}
        capturado["timeout"] = kw.get("timeout")
        return _Falso()

    import subprocess
    monkeypatch.setattr(subprocess, "run", _run_falso)
    pdf_vector.medir_pagina_em_filho(pdf, pagina)
    return capturado


def test_o_filho_poe_TETO_DE_MEMORIA_do_kernel(monkeypatch):
    """🔑 O coração: sem `setrlimit` no filho, o teto é decorativo."""
    cap = _comando_do_filho(monkeypatch)
    codigo = cap["cmd"][2]
    assert "setrlimit" in codigo, codigo[:200]
    assert "RLIMIT_AS" in codigo
    assert str(pdf_vector.SHADOW_RLIMIT_BYTES) in codigo, (
        "o teto passado ao filho não é o SHADOW_RLIMIT_BYTES")


def test_o_teto_do_filho_e_o_MESMO_da_producao():
    """🪤 Dois tetos diferentes divergem — foi a doença do dia inteiro. A
    produção usa 2 GB (main.py); a sombra tem que usar o mesmo."""
    assert pdf_vector.SHADOW_RLIMIT_BYTES == 2_000_000_000
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    assert "2_000_000_000" in fonte, (
        "a produção mudou o teto e a sombra ficou pra trás")


def test_o_filho_corta_a_reserva_virtual_do_OpenBLAS(monkeypatch):
    """🪤 O RLIMIT_AS cobra ENDEREÇO. O OpenBLAS que o numpy do shapely importa
    reserva >1 GB virtual que nem vira RAM — sem isto o teto mata medição
    legítima. Mesma receita do filho da produção."""
    cap = _comando_do_filho(monkeypatch)
    assert cap["env"].get("OPENBLAS_NUM_THREADS") == "1"
    assert cap["env"].get("MALLOC_ARENA_MAX") == "2"
    assert cap["env"].get("PYTHONFAULTHANDLER") == "1", (
        "sem faulthandler, morte por OOM em código C sai com stderr VAZIO")


def test_o_caminho_do_PDF_vai_por_ARGV_e_nao_embutido_no_fonte(monkeypatch):
    """🪤 A 1ª versão colava `r'{0}'.format(pdf_path)` DENTRO do código do
    filho. Um caminho com aspa simples (`pé d'água`, nome de pasta comum em
    projeto) fecharia a string: o filho morreria de `SyntaxError` e este runner
    arquivaria como "filho da sombra morreu" — **indistinguível do estouro de
    memória que a função existe pra conter**. Defeito disfarçado do defeito.

    🔑 Por argv não existe aspa pra escapar. O teste prova as duas metades:
    o caminho NÃO aparece no fonte, e o fonte COMPILA com ele em cena."""
    caminho = "/tmp/pe d'agua/planta 1:50.pdf"
    cap = _comando_do_filho(monkeypatch, pdf=caminho, pagina=7)
    codigo = cap["cmd"][2]
    assert "pe d'agua" not in codigo, (
        "o caminho voltou a ser embutido no fonte do filho:\n%s" % codigo)
    compile(codigo, "<filho da sombra>", "exec")   # 🧪 sintaxe válida
    assert cap["cmd"][-2] == caminho, cap["cmd"]
    assert cap["cmd"][-1] == "7", cap["cmd"]


def test_o_filho_tem_CRONOMETRO(monkeypatch):
    cap = _comando_do_filho(monkeypatch)
    assert cap["timeout"] == pdf_vector.SHADOW_TIMEOUT_S
    assert 0 < pdf_vector.SHADOW_TIMEOUT_S <= 180


@pytest.mark.parametrize("como_morre,marca", [
    ("rc", "morreu"), ("timeout", "tempo"),
    ("json_quebrado", "JSON"), ("explode", "nao rodou")])
def test_filho_que_morre_NAO_derruba_quem_chamou(monkeypatch, como_morre, marca):
    """🔒 A sombra é telemetria: ela nunca pode matar o job nem o servidor.
    Toda morte vira dict com `skip` — recusa registrada não é silêncio.

    🔑 E o `skip` tem que DIZER QUAL morte. A mutação pegou isto: trocando o
    `except TimeoutExpired` por outro tipo, o estouro de tempo caía no
    `except Exception` genérico e era arquivado como "não rodou". O servidor
    sobrevivia igual — mas o log mentia, e é esse log que eu leio depois pra
    decidir se o teto está apertado ou se o fork está falhando. Guarda que só
    exige `skip` verdadeiro deixa passar telemetria trocada."""
    import subprocess

    class _Falso:
        def __init__(s, rc, out, err):
            s.returncode, s.stdout, s.stderr = rc, out, err

    def _run_falso(cmd, **kw):
        if como_morre == "rc":
            return _Falso(-9, "", "Killed")
        if como_morre == "timeout":
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout") or 1)
        if como_morre == "json_quebrado":
            return _Falso(0, "{isso nao e json", "")
        raise OSError("fork falhou")

    monkeypatch.setattr(subprocess, "run", _run_falso)
    r = pdf_vector.medir_pagina_em_filho("x.pdf", 0)
    assert isinstance(r, dict), r
    assert r.get("skip"), "morte do filho tem que virar `skip` registrado: %r" % r
    assert marca in r["skip"], (
        "o filho morreu de '%s' e o log diz %r — motivo trocado manda a "
        "investigação pro lado errado" % (como_morre, r["skip"]))


def test_CONTROLE_filho_que_DA_CERTO_devolve_a_medicao(monkeypatch):
    """🧪 Sem isto, um runner que devolvesse `skip` sempre passaria em todos os
    testes de morte acima e a sombra nunca mediria nada."""
    import subprocess

    class _Ok:
        returncode = 0
        stdout = '{"scale": 50, "n_rooms": 7, "scale_src": "carimbo"}'
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Ok())
    r = pdf_vector.medir_pagina_em_filho("x.pdf", 3)
    assert r.get("scale") == 50 and r.get("n_rooms") == 7
    assert not r.get("skip")


# ══════════════════════════════════════════════════════════════════════════
#  O teto de tamanho: freio de custo, NÃO proteção de memória
# ══════════════════════════════════════════════════════════════════════════
def test_o_teto_de_tamanho_nao_e_mais_a_unica_protecao():
    """📏 12 MB excluía 32 páginas em 6 jobs (16% das páginas da sombra) e não
    protegia nada — a queda de 03/09 veio de um PDF de 2,63 MB, 4,6× MENOR que
    o teto. Quem protege memória agora é o RLIMIT."""
    assert pdf_vector.MAX_FILE_MB >= 40, (
        "o teto voltou a ser apertado a ponto de enviesar a medição: %s MB"
        % pdf_vector.MAX_FILE_MB)


def test_o_motivo_do_teto_esta_ESCRITO():
    """🪤 Constante nua envelhece e vira lei. Esta já era: `MAX_FILE_MB = 12`
    com um comentário de uma linha, sem data nem medição — a mesma forma do
    piso de envoltória de 400 m² que hoje se provou arbitrário."""
    fonte = io.open(os.path.join(_BACKEND, "pdf_vector.py"), encoding="utf-8").read()
    i = fonte.index("MAX_FILE_MB")
    antes = fonte[max(0, i - 1400):i]
    assert "RLIMIT" in antes, (
        "o comentário do teto não diz mais quem protege memória de verdade")
    assert "03/09" in antes or "2,63 MB" in antes, (
        "sumiu a medição que justifica o número — sem ela a próxima pessoa "
        "aperta o teto de novo achando que protege")
