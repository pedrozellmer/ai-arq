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


def chamadas_diretas(arvore, alvo="_measure_page"):
    """Linhas onde `alvo` é CHAMADO — em QUALQUER função do módulo.

    🔑 09/09, 2ª volta. A 1ª versão varria só o corpo do `_run`, e a revisão
    adversarial mostrou o furo: um ajudante de uma linha no nível do módulo
    (`def _medir_aqui(p, i): return _measure_page(p, i, "")`) devolvia a
    medição pro processo do servidor com os DOIS guardas VERDES — o `_run`
    chamava o filho (2º guarda feliz) e `_measure_page` não aparecia dentro
    dele (1º guarda feliz). Ancorar na FUNÇÃO era ancorar na forma; o fato é
    "ninguém mede dentro deste processo", e isso é do MÓDULO.

    🪤 A chamada legítima do filho mora dentro de uma STRING (o código do
    `-c`), então ela não é um `ast.Call` e não polui esta conta.
    """
    return sorted(n.lineno for n in ast.walk(arvore)
                  if isinstance(n, ast.Call)
                  and (getattr(n.func, "id", None)
                       or getattr(n.func, "attr", None)) == alvo)


# ══════════════════════════════════════════════════════════════════════════
#  🔑 O invariante: a sombra NÃO mede dentro do servidor
# ══════════════════════════════════════════════════════════════════════════
def test_o_laco_da_sombra_NAO_chama_a_medicao_direto():
    """🩸 O defeito em pessoa. `_run` roda numa thread DO SERVIDOR; chamar
    `_measure_page` ali aloca no processo que atende todos os clientes."""
    arvore = _ast_pdf_vector()
    assert any(isinstance(n, ast.FunctionDef) and n.name == "_run"
               for n in arvore.body), "o `_run` da sombra sumiu"
    diretas = chamadas_diretas(arvore)
    assert not diretas, (
        "`_measure_page` é CHAMADO no processo do servidor (linhas %s). Não "
        "basta o `_run` não chamar: um ajudante no módulo faz o mesmo estrago. "
        "Um cronômetro não limita memória; só o kernel limita — foi a lição da "
        "queda de 03/09. Use `medir_pagina_em_filho`." % diretas)


def test_o_laco_da_sombra_USA_o_filho_protegido():
    arvore = _ast_pdf_vector()
    run = next(n for n in arvore.body
               if isinstance(n, ast.FunctionDef) and n.name == "_run")
    usa = [n for n in ast.walk(run)
           if isinstance(n, ast.Call)
           and (getattr(n.func, "id", None) or getattr(n.func, "attr", None))
           == "medir_pagina_em_filho"]
    assert usa, "a sombra não chama `medir_pagina_em_filho`"


def test_CONTROLE_a_leitura_por_AST_nao_casa_com_comentario():
    """🧪 O docstring deste arquivo CITA `_measure_page` de propósito, pra
    explicar o defeito. Se o guarda lesse texto, documentar seria proibido."""
    fonte = ('def _run():\n    """cita _measure_page e é errado."""\n'
             "    # _measure_page(a, b, c)\n    return 1\n")
    assert chamadas_diretas(ast.parse(fonte)) == [], (
        "a leitura por AST casou com comentário/docstring")


@pytest.mark.parametrize("fonte,onde", [
    ("def _run():\n    return _measure_page(a, b, c)\n", "chamada nua"),
    ("def _run():\n    return pv._measure_page(a, b, c)\n", "chamada com ponto"),
    ("def _medir_aqui(p, i):\n    return _measure_page(p, i, '')\n"
     "def _run():\n    return _medir_aqui(1, 2)\n", "ajudante no módulo"),
])
def test_CONTROLE_o_predicado_ACHA_o_defeito_plantado(fonte, onde):
    """🧪 O controle que faltava — e a falta dele quase custou o guarda inteiro.

    🩸 A 1ª versão provava uma propriedade do módulo `ast`, não do MEU
    predicado: nunca chamava `chamadas_diretas`. Trocar o `or` por `and` (o que
    zera o casamento em `pv._measure_page`, porque `Attribute` não tem `.id`)
    ou errar o nome deixaria o guarda PERMANENTEMENTE verde com o defeito
    aberto. O 3º caso é exatamente o furo que a revisão adversarial achou.
    """
    assert chamadas_diretas(ast.parse(fonte)), "o predicado não achou: " + onde


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


def test_o_setrlimit_vem_ANTES_do_import_que_aloca(monkeypatch):
    """🩸 Ordem é tudo. Mover o bloco do `setrlimit` pra depois do
    `from pdf_vector import _measure_page` deixa as três asserções de texto
    acima VERDES — e o filho importa shapely/numpy e mede a prancha inteira
    SEM teto. É a queda de 03/09 de novo, agora na sombra, com a bancada
    dizendo que está tudo bem.

    🔑 O repo já tinha o guarda certo do lado da PRODUÇÃO e eu não espelhei:
    oitava vez hoje que uma decisão existe em dois lugares e só um tem guarda.
    """
    codigo = _comando_do_filho(monkeypatch)["cmd"][2]
    i_lim = codigo.index("setrlimit")
    i_imp = codigo.index("from pdf_vector import")
    assert i_lim < i_imp, (
        "o teto do kernel foi posto DEPOIS do import que aloca — decorativo:\n"
        + codigo)
    assert codigo.index("except Exception") < i_imp, (
        "o `except` que tolera a ausência de `resource` (Windows) saiu do "
        "prefixo — no Linux o filho passa a morrer antes de medir")


def test_o_filho_EXECUTA_e_o_kernel_RECEBE_o_teto(tmp_path, monkeypatch):
    """🧪 O controle que faltava: procurar a palavra `setrlimit` no texto não
    prova que o kernel recebeu nada. Aqui o código do filho RODA.

    🔑 O truque é o próprio filho: ele faz `sys.path.insert(0, sys.argv[1])`,
    e o argv[1] é meu. Ponho nesse diretório um `pdf_vector.py` falso que, ao
    ser importado, imprime o teto que o kernel está cobrando naquele instante
    — ou seja, DEPOIS do prefixo do `setrlimit` ter rodado, no processo real.
    """
    import json as _j
    import subprocess as _sp
    import sys as _sy

    sonda = tmp_path / "pdf_vector.py"
    sonda.write_text(
        "import json, sys\n"
        "try:\n"
        "    import resource\n"
        "    _lim = resource.getrlimit(resource.RLIMIT_AS)[0]\n"
        "except Exception:\n"
        "    _lim = None\n"
        "def _measure_page(p, i, k):\n"
        "    return {'rlimit_as': _lim, 'pdf': p, 'pagina': i}\n",
        encoding="utf-8")

    codigo = _comando_do_filho(monkeypatch)["cmd"][2]   # o `-c` DE VERDADE
    # 🪤 `_comando_do_filho` dubla `subprocess.run` pra capturar o comando —
    # sem desfazer, o `run` abaixo cairia no DUBLÊ e o teste passaria lendo o
    # `stdout` falso, sem nunca rodar processo nenhum. Auto-sabotagem: era
    # exatamente a forma de guarda vácuo que este arquivo veio consertar.
    monkeypatch.undo()
    pr = _sp.run([_sy.executable, "-c", codigo, str(tmp_path), "x.pdf", "0"],
                 capture_output=True, text=True, timeout=60)
    assert pr.returncode == 0, pr.stderr[-500:]
    saida = _j.loads(pr.stdout.strip().splitlines()[-1])
    assert saida["pagina"] == 0 and saida["pdf"] == "x.pdf", saida

    if saida["rlimit_as"] is None:
        pytest.skip("sem módulo `resource` (Windows) — o teto é do Linux")
    assert saida["rlimit_as"] == pdf_vector.SHADOW_RLIMIT_BYTES, (
        "o kernel cobrou %r, não os %d bytes que o código diz pedir"
        % (saida["rlimit_as"], pdf_vector.SHADOW_RLIMIT_BYTES))


def test_o_cronometro_da_sombra_e_MAIOR_que_o_da_promocao():
    """🩸 Regressão que a revisão adversarial pegou no meu próprio conserto.

    `SHADOW_TIMEOUT_S` era 75 — EXATAMENTE o do filho da promoção. Com isso a
    sombra vira uma cópia mais lenta dela (paga startup de interpretador que a
    thread não pagava) e a página perdida por TEMPO deixa de ser medida em
    qualquer lugar. E é a única coisa que a sombra media a mais: o contrato
    está vivo em `_pular_sombra` (main.py só barra 'processo'/'memoria', deixa
    'tempo' vir pra cá) e na bancada.

    📏 Medido depois do parse único (05/09): CPQ11 112 s, FORRO 83 s, LAYOUT
    74 s. Em produção a sombra já mediu em 108 s uma página que a promoção
    tinha perdido no cronômetro. Com 75 aqui, essa medição some.
    """
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    assert "timeout=75" in fonte, (
        "a promoção mudou o cronômetro dela — reconferir a folga da sombra")
    assert pdf_vector.SHADOW_TIMEOUT_S > 75, (
        "a sombra voltou a ter o mesmo teto de tempo da promoção (%s s): a "
        "página perdida por tempo não é medida em lugar nenhum"
        % pdf_vector.SHADOW_TIMEOUT_S)


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


def test_RUIDO_no_stdout_antes_do_JSON_nao_mata_a_medicao(monkeypatch):
    """🩸 Regressão que a revisão pegou. A produção lê a ÚLTIMA LINHA do
    stdout do filho (`main.py`, `.splitlines()[-1]`); meu runner lia o buffer
    INTEIRO. E o filho imprime antes do JSON: página sem viewport cai no
    carimbo, que chama a IA, e o registro de cache do `llm_retry` vai pro
    stdout. Resultado: `json.loads` estoura e a medição boa vira "JSON
    quebrado" — perda silenciosa, no instrumento que mede cobertura.

    🪤 A mesma decisão em dois lugares, consertada num lado só: exatamente o
    vício que este arquivo existe pra fechar, cometido dentro dele.
    """
    import subprocess

    class _ComRuido:
        returncode = 0
        stdout = ("[llm_cache] hit etapa=pdfvec-carimbo\n"
                  "aviso qualquer de biblioteca\n"
                  '{"scale": 50, "n_rooms": 7}')
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _ComRuido())
    r = pdf_vector.medir_pagina_em_filho("x.pdf", 0)
    assert r.get("scale") == 50 and r.get("n_rooms") == 7, (
        "ruído antes do JSON matou a medição: %r" % r)
    assert not r.get("skip")


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
#  O RESUMO: skip não é medição, e evidência não pode se autodestruir
# ══════════════════════════════════════════════════════════════════════════
def _roda_a_sombra(monkeypatch, tmp_path, n_paginas, resposta):
    """Roda `_run` de verdade com o filho dublado; devolve o payload gravado."""
    import json as _j
    monkeypatch.setattr(pdf_vector.time, "sleep", lambda *_: None)
    monkeypatch.setattr(pdf_vector, "medir_pagina_em_filho",
                        lambda pdf, pag, **_k: dict(resposta(pdf, pag)))
    unidades = []
    for i in range(n_paginas):
        f = tmp_path / ("p%d.pdf" % i)
        f.write_bytes(b"%PDF-1.4 x")
        unidades.append((str(f), "p%d.pdf" % i, "arq", 0))
    gravados = []
    pdf_vector._run(unidades, "job-teste", "chave",
                    lambda *a, **k: gravados.append(a))
    bruto = next((a[1] for a in gravados if a[0] == "pdfvec:shadow"), None)
    assert bruto is not None, "a sombra não gravou nada"
    return bruto, _j.loads(bruto)


def test_o_filho_recebe_o_RESTO_do_orcamento_nao_o_teto_cheio(monkeypatch, tmp_path):
    """🪤 O filho não conhece o `deadline` do laço. Passando sempre o teto
    cheio, a thread da sombra vive `BUDGET_S + SHADOW_TIMEOUT_S` — 180 + 170 =
    350 s — porque o deadline é lido ANTES de lançar o filho e o filho segue
    contando por conta própria. O orçamento vira sugestão.

    🔑 Este guarda nasceu de um mutante SOBREVIVENTE: eu tinha consertado o
    código e não tinha guarda nenhum olhando pra isso.
    """
    recebidos = []
    relogio = {"t": 1000.0}
    monkeypatch.setattr(pdf_vector.time, "sleep", lambda *_: None)
    monkeypatch.setattr(pdf_vector.time, "time", lambda: relogio["t"])

    def _falso(pdf, pag, timeout_s=None, **_k):
        recebidos.append(timeout_s)
        relogio["t"] += 70.0          # cada página queima 70 s do orçamento
        return {"scale": 50}

    monkeypatch.setattr(pdf_vector, "medir_pagina_em_filho", _falso)
    unidades = []
    for i in range(3):
        f = tmp_path / ("q%d.pdf" % i)
        f.write_bytes(b"%PDF-1.4 x")
        unidades.append((str(f), "q%d.pdf" % i, "arq", 0))
    pdf_vector._run(unidades, "job-teste", "chave", lambda *a, **k: None)

    assert recebidos, "a sombra não mediu nada"
    assert recebidos[0] <= pdf_vector.SHADOW_TIMEOUT_S
    # 3ª página: já se passaram 140 s dos 180 — sobram 40, não 170.
    if len(recebidos) >= 3:
        assert recebidos[2] < pdf_vector.SHADOW_TIMEOUT_S, (
            "o filho recebeu o teto cheio (%s s) com o orçamento quase no fim "
            "— a thread pode viver BUDGET_S + SHADOW_TIMEOUT_S" % recebidos[2])
        assert recebidos[2] >= 30, (
            "o piso de 30 s sumiu: filho com cronômetro perto de zero morre "
            "sem nem abrir o arquivo, e a recusa vira ruído")


def test_skip_NAO_conta_como_pagina_medida(monkeypatch, tmp_path):
    """🩸 `n` era `len(results)`, e skip vira linha em `results`. Oito filhos
    mortos viravam "8 de 8 página(s) medida(s)": ZERO medição registrada como
    cobertura de 100%, no número com que eu decido se o leitor vetorial sai da
    sombra. Métrica que conta a própria falha como sucesso é pior que métrica
    nenhuma — a ausência pelo menos se vê."""
    _b, pl = _roda_a_sombra(monkeypatch, tmp_path, 5,
                            lambda p, i: {"skip": "filho da sombra morreu"})
    assert pl["n"] == 0, "skip contado como medição: %r" % pl
    assert pl.get("tentadas") == 5, pl


def test_CONTROLE_pagina_que_MEDE_continua_contando(monkeypatch, tmp_path):
    """🧪 Sem isto, um `n` fixo em zero passaria no teste acima."""
    _b, pl = _roda_a_sombra(monkeypatch, tmp_path, 3,
                            lambda p, i: {"scale": 50, "n_rooms": 2,
                                          "rooms_m2": 10.0})
    assert pl["n"] == 3, pl
    assert pl["rooms_m2_total"] == 30.0, pl


def test_o_orcamento_de_paginas_NAO_e_gasto_por_recusa(monkeypatch, tmp_path):
    """🪤 `MAX_PAGES` contava linha GRAVADA, e recusa é linha. Um job em que os
    filhos da promoção morreram nas 8 primeiras páginas fechava com 8 recusas e
    ZERO medição, sem nunca olhar as páginas 9 em diante — que podiam medir
    perfeitamente. O orçamento é de MEDIÇÃO."""
    monkeypatch.setattr(pdf_vector, "MAX_PAGES", 2)
    vistas = []

    def _resp(pdf, pag):
        vistas.append(os.path.basename(pdf))
        return {"scale": 50} if len(vistas) > 3 else {"skip": "arquivo grande"}

    _b, pl = _roda_a_sombra(monkeypatch, tmp_path, 6, _resp)
    assert pl["n"] == 2, "as recusas comeram a cota de medição: %r" % pl
    assert len(vistas) >= 5, (
        "a sombra parou nas recusas em vez de seguir pras páginas boas: %r"
        % vistas)


def test_o_stderr_do_filho_morto_NAO_estoura_o_log(monkeypatch, tmp_path):
    """🩸 O `err` do filho traz até 400 chars de stderr e ia inteiro pro
    payload. Com 8 páginas mortas passa dos 2.000 da coluna, o corte parte a
    string no meio e a linha vira JSON INVÁLIDO — some a evidência do job
    inteiro, inclusive das páginas que mediram bem. É a reabertura literal do
    incidente de 30/07 que o comentário do `_resumo` registra: o caso em que eu
    MAIS preciso do log é justamente o que o apaga."""
    import json as _j
    bruto, _pl = _roda_a_sombra(
        monkeypatch, tmp_path, 8,
        lambda p, i: {"skip": "filho da sombra morreu", "rc": -9,
                      "err": "Traceback " + "x" * 400})
    assert len(bruto) <= 2000, "o payload passou do corte da coluna: %d" % len(bruto)
    _j.loads(bruto)   # 🧪 tem que continuar sendo JSON válido


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
