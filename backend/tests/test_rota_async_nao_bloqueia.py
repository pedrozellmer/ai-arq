# -*- coding: utf-8 -*-
"""Rota `async` não pode rodar trabalho pesado no laço de eventos.

🚨 27/08/2026, madrugada. **cliente-18**, orçamentista, chegou pelo
ChatGPT e cadastrou às 02:02 — do primeiro clique ao cadastro em 2 segundos.
Às 02:03 selecionou 17 arquivos. E foi embora às 02:04:47 sem enviar nada.

Ela não desistiu por capricho: **a página congelou na mão dela.**

    02:03  POST /api/estimate-price   (17 arquivos)
    02:04  CPU a 100% de um núcleo, travada
    02:04  ela some
    02:05  "Shutting down" + 31 s esperando conexões
    02:06  instância reiniciada  (e de novo às 02:09)

Memória no pico: 348 MB de 4,29 GB. **Não era memória — era CPU.**

🔑 A causa: rota `async def` executa NO LAÇO DE EVENTOS. Trabalho pesado
síncrono ali não deixa o servidor "lento", deixa **bloqueado** — nenhuma outra
requisição é atendida enquanto roda. Medido nesta máquina:

    estimate_for_files   6 DWG  ->  0,00 s
    precheck_warnings    6 DWG  ->  3,81 s
    precheck_warnings    4 PDF  -> 68,25 s     (~17 s POR PDF)

O comentário original chamava o precheck de *"barato"*. Não é.

🪤 **A sonda de vida do Render não causou isso — ela REVELOU.** O uvicorn
registra a requisição quando ela TERMINA: uma resposta de 8 s aparece como
"200 OK" no log enquanto o Render já desistiu nos 5 s. O log parecia saudável.
Sem a sonda (ligada na véspera), isso seguiria acontecendo em silêncio — e
provavelmente já acontecia havia tempo.

📌 O caminho de PROCESSAMENTO já estava certo: `process_job` é `def` comum e
roda em thread daemon com semáforo. O buraco era só a estimativa.
"""
import ast
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import asyncio                                                     # noqa: E402
import threading                                                   # noqa: E402
import time                                                        # noqa: E402
import types                                                       # noqa: E402

import main                                                        # noqa: E402
import pricing                                                     # noqa: E402
import pytest                                                     # noqa: E402


class _RequestFake:
    def __init__(self):
        self.headers = {}
        self.client = types.SimpleNamespace(host="127.0.0.1")


class _UploadFake:
    """UploadFile o suficiente pro caminho do estimate: nome e nada mais.

    A gravação em disco é encenada (`_grava_encenado`), então o conteúdo não
    importa — o que importa é QUANTOS arquivos chegam na função pesada.
    """

    def __init__(self, filename):
        self.filename = filename
        self.size = 4096


def _rodar_estimativa(monkeypatch, tmp_path, estimativa=None, precheck=None,
                      teto_s=None, n_arquivos=0):
    """Chama a rota /api/estimate-price DE VERDADE. Devolve (resposta, diário).

    🪤 06/09: esta bancada só sabia chamar a rota com ZERO arquivo — justo o
    caso em que não há trabalho pesado nenhum. Qualquer regressão presa à
    QUANTIDADE de arquivos (a forma do incidente real: a cliente-18 selecionou
    17) ficava invisível. Agora o número de arquivos é um parâmetro, e o
    diário anota quantos caminhos chegaram em cada função pesada.
    """
    diario = {"threads": {}, "logs": [], "caminhos": {}}

    def _est(caminhos, known=0):
        diario["threads"]["estimate_for_files"] = threading.current_thread()
        diario["caminhos"]["estimate_for_files"] = list(caminhos or [])
        return (estimativa or (lambda: {"pranchas": 1, "preco": 97}))()

    def _pre(caminhos):
        # 🔑 09/09/2026: o dublê passou a ser `precheck_em_filho`, não
        # `precheck_warnings`. O FATO que este guarda mede não mudou — a rota
        # não pode bloquear o laço de eventos —, mas a rota deixou de chamar o
        # precheck em thread do servidor: ele agora roda num PROCESSO FILHO com
        # teto de memória do kernel, porque `pdfplumber` aloca proporcional aos
        # elementos vetoriais da prancha (~500× medido) e esta rota é PÚBLICA,
        # sem login. Ver `test_o_filho_protegido_e_um_so.py`.
        # 🪤 Dublar o nome antigo deixaria este guarda medindo um telefone
        # desligado: verde, e sem exercitar o caminho real.
        diario["threads"]["precheck"] = threading.current_thread()
        diario["caminhos"]["precheck"] = list(caminhos or [])
        return (precheck or (lambda: ["aviso de precheck"]))()

    async def _grava_encenado(upload_file, path):
        io.open(path, "w", encoding="utf-8").write("cad de mentira")
        return 14, b""

    monkeypatch.setattr(pricing, "estimate_for_files", _est)
    monkeypatch.setattr(pricing, "precheck_em_filho", _pre)
    monkeypatch.setattr(main, "_rate_limit_ok", lambda *a, **k: True)
    monkeypatch.setattr(main, "WORK_DIR", str(tmp_path))
    monkeypatch.setattr(main, "_stream_upload_to_disk", _grava_encenado)
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, job=None, **k: diario["logs"].append(
                            (stage, str(msg))))
    if teto_s is not None:
        monkeypatch.setattr(main, "_PRECHECK_ORCAMENTO_S", teto_s)

    arquivos = [_UploadFake("PRANCHA_%02d.dwg" % i) for i in range(n_arquivos)]
    t0 = time.monotonic()
    resp = asyncio.run(main.estimate_price(request=_RequestFake(),
                                           files=arquivos, known_pranchas=1))
    diario["segundos"] = time.monotonic() - t0
    diario["thread_do_laco"] = threading.current_thread()
    return resp, diario


# Funções que ABREM ou PROCESSAM arquivo — caras por natureza.
_PESADAS = {
    "estimate_for_files", "precheck_warnings", "extract_dxf", "analyze_sheet",
    "extract_from_file", "_convert_dwg_to_dxf", "_dwg_tem_objetos_aec",
    "gerar_planilha", "criar_planilha", "contar_pranchas",
}

_DECORADORES_DE_ROTA = ("get", "post", "put", "delete", "patch")


def _fonte(caminho=None):
    return io.open(caminho or os.path.join(_BACKEND, "main.py"),
                   encoding="utf-8").read()


def _nomes_chamados(no):
    """[(nome, linha)] de tudo que é CHAMADO dentro de `no`.

    🔑 Só nós `Call`. `run_in_threadpool(pesada, x)` passa `pesada` como NOME,
    não como chamada — é assim que a forma certa deixa de ser acusada.
    """
    fora = []
    for sub in ast.walk(no):
        if isinstance(sub, ast.Call):
            nome = getattr(sub.func, "id", None) or getattr(sub.func, "attr", None)
            if nome:
                fora.append((nome, sub.lineno))
    return fora


def _chamadas_pesadas_no_laco(src):
    """[(rota, funcao, linha)] de trabalho pesado rodando NO LAÇO.

    Pega dois formatos:
      1. a rota chama a pesada direto (o formato do incidente de 27/08);
      2. a rota chama um HELPER de módulo, e o helper chama a pesada.

    🪤 06/09: o detector só sabia o formato 1 — era por NOME e por ESCOPO DE
    ROTA. Mover a chamada uma linha pra dentro de `def _monta_orcamento(...)`
    devolvia o bloqueio inteiro ao laço de eventos com o guarda verde. O laço
    não sabe em que função o trabalho está: ele só sabe que ninguém mais é
    atendido enquanto roda.
    """
    arvore = ast.parse(src)
    # helpers SÍNCRONOS de módulo: são eles que "escondem" a chamada pesada.
    helpers = {n.name: n for n in arvore.body if isinstance(n, ast.FunctionDef)}
    achados = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.AsyncFunctionDef):
            continue
        eh_rota = any(
            isinstance(d, ast.Call)
            and getattr(d.func, "attr", "") in _DECORADORES_DE_ROTA
            for d in no.decorator_list)
        if not eh_rota:
            continue
        for nome, linha in _nomes_chamados(no):
            if nome in _PESADAS:
                achados.append((no.name, nome, linha))
            elif nome in helpers:
                for n2, _l2 in _nomes_chamados(helpers[nome]):
                    if n2 in _PESADAS:
                        achados.append((no.name, "%s -> %s" % (nome, n2), linha))
    return achados


def test_nenhuma_rota_async_chama_funcao_pesada_direto():
    """🚨 O guarda. Uma chamada dessas trava o site inteiro pra todo mundo."""
    achados = _chamadas_pesadas_no_laco(_fonte())
    assert not achados, (
        "rota async chamando função pesada DENTRO do laço de eventos: %s — "
        "isso não deixa o site lento, deixa BLOQUEADO. Use "
        "`await run_in_threadpool(funcao, ...)`." % achados)


def test_CONTROLE_POSITIVO_o_detector_pega_de_verdade():
    """🧪 Sem isto, o teste acima passaria verde num detector quebrado — e eu
    não saberia. Monta o padrão exato que existia antes do conserto."""
    ruim = (
        "@app.post('/api/x')\n"
        "async def rota_ruim(request):\n"
        "    result = estimate_for_files(caminhos)\n"
        "    return result\n"
    )
    achados = _chamadas_pesadas_no_laco(ruim)
    assert achados, "o detector não pega o padrão que causou o incidente"
    assert achados[0][0] == "rota_ruim" and achados[0][1] == "estimate_for_files"

    # e o padrão CERTO não pode ser acusado
    bom = (
        "@app.post('/api/x')\n"
        "async def rota_boa(request):\n"
        "    result = await run_in_threadpool(estimate_for_files, caminhos)\n"
        "    return result\n"
    )
    assert not _chamadas_pesadas_no_laco(bom), (
        "falso positivo: a versão em thread foi acusada")


def test_CONTROLE_POSITIVO_o_detector_atravessa_o_helper_de_modulo():
    """🧪 O disfarce mais barato: mover a chamada pesada uma linha pra dentro de
    um helper de módulo. O laço de eventos continua bloqueado igual."""
    disfarcado = (
        "def _monta_orcamento(caminhos):\n"
        "    return estimate_for_files(caminhos)\n"
        "\n"
        "@app.post('/api/x')\n"
        "async def rota_disfarcada(request):\n"
        "    return _monta_orcamento(caminhos)\n"
    )
    achados = _chamadas_pesadas_no_laco(disfarcado)
    assert achados, (
        "o detector é cego a helper de módulo — basta mover a chamada uma "
        "linha pra dentro pra o bloqueio voltar com o guarda verde")
    assert achados[0][0] == "rota_disfarcada"
    assert achados[0][1] == "_monta_orcamento -> estimate_for_files", achados

    # …e o helper MANDADO PRA THREAD não pode ser acusado.
    correto = (
        "def _monta_orcamento(caminhos):\n"
        "    return estimate_for_files(caminhos)\n"
        "\n"
        "@app.post('/api/x')\n"
        "async def rota_correta(request):\n"
        "    return await run_in_threadpool(_monta_orcamento, caminhos)\n"
    )
    assert not _chamadas_pesadas_no_laco(correto), (
        "falso positivo: o helper mandado pra thread foi acusado")


@pytest.mark.parametrize("n_arquivos", [0, 1, 6, 17],
                         ids=["sem_arquivo", "um", "seis", "dezessete"])
def test_a_estimativa_usa_thread(monkeypatch, tmp_path, n_arquivos):
    """🚨 O incidente da cliente-18: `estimate_for_files` e `precheck_warnings`
    rodando NO LAÇO DE EVENTOS travam o site inteiro pra todo mundo.

    Guarda por EXECUÇÃO: as duas têm que rodar numa thread que não é a do laço,
    **em qualquer quantidade de arquivos**.

    🪤 06/09: o cenário único era ZERO arquivo — o caso em que não há trabalho
    pesado nenhum. Um "atalho pra seleção pequena/grande" (`if len(saved_paths)
    > N: roda aqui mesmo`) passava verde, e é exatamente a forma do incidente:
    a cliente-18 selecionou **17** arquivos, a CPU foi a 100%% e o site parou de
    responder na mão dela. 6 é a medição de 3,81 s dos DWG; 17 é o caso real.
    """
    resp, d = _rodar_estimativa(monkeypatch, tmp_path, n_arquivos=n_arquivos)
    assert resp["status"] == "ok"
    assert set(d["threads"]) == {"estimate_for_files", "precheck"}, (
        "alguma das duas funções pesadas não chegou a rodar: %r" % (d["threads"],))
    for nome, th in d["threads"].items():
        assert th is not d["thread_do_laco"], (
            "%s rodou NA THREAD DO LAÇO DE EVENTOS com %d arquivo(s) — isso "
            "não deixa o site lento, deixa BLOQUEADO: nenhuma outra requisição "
            "é atendida enquanto roda. É o congelamento que espantou a "
            "cliente-18." % (nome, n_arquivos))
    for nome, caminhos in d["caminhos"].items():
        assert len(caminhos) == n_arquivos, (
            "%s recebeu %d caminho(s) de %d — a rota está descartando arquivo "
            "no meio do caminho, e a estimativa sai medindo menos do que o "
            "cliente mandou" % (nome, len(caminhos), n_arquivos))


def test_o_precheck_tem_TETO_de_espera():
    """🪤 Thread livra o SERVIDOR, não o CLIENTE. 17 s por PDF viraria minutos
    de tela parada — e foi tela parada que espantou a cliente-18."""
    src = _fonte()
    assert "_PRECHECK_ORCAMENTO_S" in src, "o precheck ficou sem teto de tempo"
    i = src.find("_PRECHECK_ORCAMENTO_S = ")
    valor = int(src[i:i + 40].split("=")[1].split()[0])
    assert 5 <= valor <= 60, (
        "teto de %ss fora do razoável: curto demais mata o aviso sempre, "
        "longo demais devolve o problema" % valor)
    j = src.find("async def estimate_price")
    fim = src.find("@app.", j)
    assert "wait_for" in src[j:fim if fim > j else len(src)], (
        "o teto existe mas não é aplicado na estimativa")


def test_o_estouro_do_precheck_VIRA_LOG():
    """Se o teto começar a cortar sempre, a gente precisa saber — senão o aviso
    de PDF sem texto some em silêncio e ninguém liga os pontos."""
    src = _fonte()
    assert "motor:precheck-estourou" in src, (
        "estouro do precheck não deixa rastro — vira conserto invisível")


def test_o_PROCESSAMENTO_continua_fora_do_laco():
    """📌 Esse caminho já estava certo; o guarda existe pra não regredir.
    `process_job` tem que ser `def` comum (thread), nunca `async def`."""
    src = _fonte()
    assert "\ndef process_job(" in src, (
        "process_job virou async — agora TODO processamento de cliente trava "
        "o site inteiro enquanto roda")
    assert "\nasync def process_job(" not in src
