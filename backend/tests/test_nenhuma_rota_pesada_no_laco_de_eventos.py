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
    # 🩸 03/09, 2ª revisão: ESTA LISTA É A FRONTEIRA DO GUARDA, e ela estava
    # curta. `project_chat` (@app.post) chamava `call_with_retry` — o modelo,
    # com 2 retries de 60 s — DIRETO no laço, e a varredura passou verde porque
    # o nome não estava aqui. Guarda com lista curta certifica o que não olha.
    # Toda chamada ao modelo e todo gerador de arquivo entram, sem exceção.
    "ask", "analyz", "extract", "call_with_retry",
    "generate_spreadsheet", "_carimbar_planilha",
    "render_pdf", "render_png", "exportar_pdf", "exportar_pptx",
    "estrutura_para_pdf", "estrutura_para_docx",
    "gerar_cronograma_xlsx", "montar_estrutura",
    "_memorial_dados_frescos", "_build_cronograma_for_export",
    "processar_revisao_inline", "_merge_montar",
    "storage_download", "storage_upload",
    # 🩸 04/09, varredura adversarial: a lista curta deixou passar de novo.
    # `upload_supplier_quote` (@app.post, aberta ao DONO do projeto, não só
    # admin) parseava o .xlsx do cliente no laço. MEDIDO: 0,80 MB → 3,54 s
    # nesta máquina, e o teto da própria rota é 15 MB. Parsear planilha é da
    # mesma família de "gerar planilha", que já estava aqui — a fronteira era
    # arbitrária, não conceitual.
    "parse_supplier_quote", "parse_strict", "parse_fuzzy",
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
        # 🩸 03/09, 2ª revisão: aqui havia um filtro `if not decorador @app:
        # continue`. Ele deixava a varredura CEGA para helper `async` sem
        # decorador — e era exatamente onde estava o defeito vivo:
        # `_cronograma_preview_png_impl` renderizava PDF e rasterizava PNG no
        # laço, chamada pela rota logo abaixo dela. O guarda passava VERDE
        # dizendo "nenhuma rota pesada no laço".
        # 🔑 O que bloqueia o laço é qualquer `async def` alcançável de rota,
        # com ou sem `@app`. Guarda que não olha uma forma inteira certifica o
        # que não olha — por isso o filtro saiu.
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


def test_CONTROLE_a_varredura_ENXERGA_helper_async_SEM_decorador():
    """🩸 O buraco que deixou a prévia do cronograma congelando o site.

    A 1ª versão desta varredura pulava toda `async def` sem `@app`. O
    `_cronograma_preview_png_impl` é exatamente isso — um helper chamado pela
    rota logo abaixo — e renderizava PDF + rasterizava PNG no laço, com este
    guarda passando verde.

    🔑 Sem este controle, alguém "otimiza" o filtro de volta daqui a um mês e
    ninguém percebe: o teste continua verde, agora certificando menos.
    """
    fonte = (
        "@app.get('/x')" + chr(10) +
        "async def rota(request):" + chr(10) +
        "    return await _impl(request)" + chr(10) +
        "" + chr(10) +
        "async def _impl(request):" + chr(10) +
        "    return render_pdf_bytes(1, 2)" + chr(10))
    tree = ast.parse(fonte)
    helper = [n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "_impl"][0]
    assert not any(ast.unparse(d).startswith("app.") for d in helper.decorator_list), (
        "o controle precisa de um helper SEM decorador pra provar o ponto")
    protegidos = _fora_do_laco(helper)
    cruas = [c for c in ast.walk(helper)
             if isinstance(c, ast.Call) and id(c) not in protegidos
             and getattr(c.func, "id", "") == "render_pdf_bytes"]
    assert cruas, (
        "a varredura voltou a pular `async def` sem @app — é onde o defeito "
        "de 03/09 estava escondido")


def test_a_lista_de_PESADAS_cobre_TODA_chamada_ao_modelo():
    """🩸 A lista é a fronteira do guarda, e ela estava curta.

    `project_chat` e `public_chat` chamavam `call_with_retry` — o modelo, com
    2 retries de 60 s — direto no laço, e a varredura passava verde porque o
    nome não estava aqui. Chamada ao modelo é o item mais caro que existe
    nesta casa; se algum dia houver outro nome pra ela, entra aqui junto.
    """
    assert "call_with_retry" in _PESADAS, (
        "o wrapper de chamada ao modelo saiu da lista — o guarda volta a "
        "certificar rotas que congelam o site por minutos")
    # E os pares gêmeos: se o PDF está na lista, o PPTX/DOCX também têm que
    # estar — foi assim que `exportar_pptx` ficou de fora enquanto o irmão
    # `exportar_pdf` era movido no mesmo commit.
    for a, b in (("exportar_pdf", "exportar_pptx"),
                 ("estrutura_para_pdf", "estrutura_para_docx")):
        assert (a in _PESADAS) == (b in _PESADAS), (
            "%r e %r são irmãos e custam o mesmo; um está na lista e o outro "
            "não — foi exatamente esse descuido que deixou o pptx no laço"
            % (a, b))
