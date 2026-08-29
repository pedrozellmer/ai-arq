# -*- coding: utf-8 -*-
"""Rota `async` não pode rodar trabalho pesado no laço de eventos.

🚨 27/08/2026, madrugada. **Maria Victoria Suica**, orçamentista, chegou pelo
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


def _chamadas_pesadas_no_laco(src):
    """Devolve [(rota, funcao, linha)] de chamada DIRETA (fora de thread)."""
    achados = []
    for no in ast.walk(ast.parse(src)):
        if not isinstance(no, ast.AsyncFunctionDef):
            continue
        eh_rota = any(
            isinstance(d, ast.Call)
            and getattr(d.func, "attr", "") in _DECORADORES_DE_ROTA
            for d in no.decorator_list)
        if not eh_rota:
            continue
        for sub in ast.walk(no):
            if not isinstance(sub, ast.Call):
                continue
            nome = getattr(sub.func, "id", None) or getattr(sub.func, "attr", None)
            if nome in _PESADAS:
                achados.append((no.name, nome, sub.lineno))
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


def test_a_estimativa_usa_thread():
    src = _fonte()
    i = src.find("async def estimate_price")
    assert i > 0, "a rota de estimativa sumiu"
    # 🪤 29/08: era src[i:i+4000] — mais uma janela fixa a reprovar código
    # certo (docstring maior empurrou o precheck pra fora). Corte estrutural.
    fim = src.find("@app.", i)
    trecho = src[i:fim if fim > i else len(src)]
    assert "run_in_threadpool(estimate_for_files" in trecho
    assert "run_in_threadpool(precheck_warnings" in trecho


def test_o_precheck_tem_TETO_de_espera():
    """🪤 Thread livra o SERVIDOR, não o CLIENTE. 17 s por PDF viraria minutos
    de tela parada — e foi tela parada que espantou a Maria Victoria."""
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
