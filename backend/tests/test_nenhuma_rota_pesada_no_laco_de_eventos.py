# -*- coding: utf-8 -*-
"""Varredura: rota `async` não pode chamar função pesada SÍNCRONA direto.

🩸 03/09/2026, 15:07 BRT. Uma pergunta no chat derrubou o site por 1,5 minuto
(`instance_count = 0`, "HTTP health check failed after 5 seconds"). Não foi
memória — o pico foi 906 MB de 4 GiB. Foi BLOQUEIO: `agent.ask` é síncrona e
estava sendo chamada de dentro de um `async def`. Com `--workers 1` isso
congela o processo inteiro.

🪤 A varredura de 28/08 consertou 61 rotas e DEIXOU ESTA PASSAR. Ela procurou
o nome da biblioteca de I/O (`urllib`, `requests`); aqui o bloqueio estava
atrás de `from agent import ask`. Bloqueio não se acha pelo NOME do módulo —
se acha pela FORMA: função síncrona chamada de rota assíncrona.

Este teste é essa forma, virada guarda. Ele não olha nome de biblioteca: ele
lê o AST, descobre quais funções desta casa são `def` (não `async def`), e
reprova quando uma delas — das pesadas — é chamada direto no corpo de uma rota
`async` sem `run_in_threadpool`.

🔑 Por que só as PESADAS: quase toda rota chama alguma função síncrona nossa
(329 ocorrências medidas). O que trava o health check de 5 s é o que demora
segundos: chamada ao modelo, render de PDF/PNG, geração de planilha, download
de MB do Storage. A lista `_PESADAS` é essa fronteira, e cresce quando a gente
descobrir outra.

🪤 DOIS falsos positivos que este guarda precisa saber evitar, os dois reais:
  • helper aninhado despachado com `run_in_threadpool(_trabalho)` — o corpo
    dele já está fora do laço;
  • helper aninhado rodado em `threading.Thread(target=...)` — idem
    (`finalize_review` faz isso com a esteira de revisão).
"""
import ast
import io
import os

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Funções cujo custo é medido em SEGUNDOS, não milissegundos.
_PESADAS = (
    "ask", "analyz", "extract",
    "generate_spreadsheet", "_carimbar_planilha",
    "render_pdf", "render_png", "exportar_pdf", "estrutura_para_pdf",
    "gerar_cronograma_xlsx", "montar_estrutura",
    "_memorial_dados_frescos", "_build_cronograma_for_export",
    "processar_revisao_inline", "_merge_montar",
    "storage_download", "storage_upload",
)


def _sincronas_da_casa():
    nomes = {}
    for arq in sorted(os.listdir(_BACKEND)):
        if not arq.endswith(".py"):
            continue
        try:
            t = ast.parse(io.open(os.path.join(_BACKEND, arq),
                                  encoding="utf-8").read())
        except Exception:
            continue
        for n in ast.walk(t):
            if isinstance(n, ast.FunctionDef):      # def, NÃO async def
                nomes.setdefault(n.name, arq)
    return nomes


def _fora_do_laco(rota):
    """ids dos nós que já rodam fora do laço (threadpool ou Thread)."""
    despachadas = set()
    for c in ast.walk(rota):
        if not isinstance(c, ast.Call):
            continue
        alvo = getattr(c.func, "id", "") or getattr(c.func, "attr", "")
        if alvo == "run_in_threadpool" and c.args and isinstance(c.args[0], ast.Name):
            despachadas.add(c.args[0].id)
        if alvo == "Thread":
            for kw in c.keywords:
                if kw.arg == "target" and isinstance(kw.value, ast.Name):
                    despachadas.add(kw.value.id)
    aninhadas = {n.name: n for n in ast.walk(rota)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n is not rota}
    protegidos = set()
    for nome in despachadas:
        if nome in aninhadas:
            for c in ast.walk(aninhadas[nome]):
                protegidos.add(id(c))
    return protegidos


def _rotas_que_bloqueiam():
    sincronas = _sincronas_da_casa()
    tree = ast.parse(io.open(os.path.join(_BACKEND, "main.py"),
                             encoding="utf-8").read())
    achados = []
    for rota in ast.walk(tree):
        if not isinstance(rota, ast.AsyncFunctionDef):
            continue
        if not any(ast.unparse(d).startswith("app.") for d in rota.decorator_list):
            continue
        protegidos = _fora_do_laco(rota)
        for c in ast.walk(rota):
            if not isinstance(c, ast.Call) or id(c) in protegidos:
                continue
            nome = getattr(c.func, "id", None) or getattr(c.func, "attr", None)
            if not nome or nome not in sincronas:
                continue
            if not any(p in nome for p in _PESADAS):
                continue
            achados.append((rota.name, nome, c.lineno))
    return achados


def test_nenhuma_rota_async_chama_funcao_pesada_no_laco():
    """🩸 O que derrubou o site às 15:07 de 03/09, virado varredura."""
    achados = _rotas_que_bloqueiam()
    assert not achados, (
        "rota(s) `async` chamando função síncrona PESADA direto no laço de "
        "eventos — com --workers 1 isso congela o site inteiro e o health "
        "check de 5 s do Render mata a instância:" + chr(10)
        + chr(10).join("  %s -> %s()  [main.py:%d]" % a for a in achados))


def test_CONTROLE_a_varredura_SABE_achar_o_defeito():
    """Sem isto, o teste acima passaria por a varredura estar quebrada.

    Monta uma rota com o defeito EXATO do caso de hoje e confirma que a
    varredura a acusa.
    """
    fonte = (
        "@app.post('/x')" + chr(10) +
        "async def rota_ruim(request):" + chr(10) +
        "    result = ask(job_id='j', question='q')" + chr(10) +
        "    return result" + chr(10))
    tree = ast.parse(fonte)
    rota = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)][0]
    protegidos = _fora_do_laco(rota)
    chamadas = [c for c in ast.walk(rota)
                if isinstance(c, ast.Call) and id(c) not in protegidos
                and getattr(c.func, "id", "") == "ask"]
    assert chamadas, "a varredura não enxerga a chamada crua — está cega"


def test_CONTROLE_a_varredura_ABSOLVE_quem_ja_esta_no_threadpool():
    """E precisa saber absolver, senão vira ruído e para de ser lida."""
    fonte = (
        "@app.post('/x')" + chr(10) +
        "async def rota_boa(request):" + chr(10) +
        "    def _trabalho():" + chr(10) +
        "        return generate_spreadsheet(1, 2)" + chr(10) +
        "    return await run_in_threadpool(_trabalho)" + chr(10))
    tree = ast.parse(fonte)
    rota = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)][0]
    protegidos = _fora_do_laco(rota)
    cruas = [c for c in ast.walk(rota)
             if isinstance(c, ast.Call) and id(c) not in protegidos
             and getattr(c.func, "id", "") == "generate_spreadsheet"]
    assert not cruas, (
        "a varredura acusa código que JÁ está no threadpool — falso positivo "
        "assim faz o guarda ser ignorado")


def test_CONTROLE_a_varredura_ABSOLVE_quem_roda_em_Thread():
    """`finalize_review` roda a esteira de revisão numa Thread — é legítimo."""
    fonte = (
        "@app.post('/x')" + chr(10) +
        "async def rota_thread(request):" + chr(10) +
        "    def _esteira():" + chr(10) +
        "        return processar_revisao_inline('j')" + chr(10) +
        "    _th.Thread(target=_esteira, daemon=True).start()" + chr(10) +
        "    return {'ok': True}" + chr(10))
    tree = ast.parse(fonte)
    rota = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)][0]
    protegidos = _fora_do_laco(rota)
    cruas = [c for c in ast.walk(rota)
             if isinstance(c, ast.Call) and id(c) not in protegidos
             and getattr(c.func, "id", "") == "processar_revisao_inline"]
    assert not cruas, "acusou trabalho que roda em Thread própria"
