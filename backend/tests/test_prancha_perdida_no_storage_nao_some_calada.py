# -*- coding: utf-8 -*-
"""Perder ALGUMAS pranchas do Storage era silêncio; só perder TODAS reclamava.

🩸 04/09/2026, varredura adversarial. Em 03/09 a gente ensinou
`_supabase_storage_download_prancha` a DESCARTAR download truncado (quando o
`Content-Length` não bate) — conserto certo, metade feito. Os cinco laços que
baixam do Storage tratam o `None` com um `continue` e só reclamam do caso ZERO:

    if not file_paths:
        raise HTTPException(500, "Falha ao baixar arquivos do Storage")

Perder **1 de 9** passava direto: o job rodava com menos pranchas e o cliente
recebia `done` numa leitura incompleta.

🔑 É o caso de **18/08** — um cliente perdeu 8 pranchas e recebeu `done` —
voltando pela porta que a gente mesmo abriu. Detectar sem consequência não é
conserto: é o defeito com um log a mais.

🪤 Os dois piores dos cinco:
  • `_retomar_job_do_storage` — a retomada automática depois de queda, ou seja,
    quando o job já está fragilizado; e
  • `add_file_and_reprocess` — o caminho em que o cliente manda o CAD que A
    GENTE PEDIU. Ele fez exatamente o que pedimos e receberia menos.

🪤 E escrever o aviso não bastava: DOIS pontos gravavam `warnings` com o array
de MEMÓRIA do motor por cima do banco (o fim do job e o ramo de erro), o que
apagaria o aviso de perda logo depois de ele ser gravado. Achado lendo, antes
de rodar. Por isso `_avisos_com` passou a aceitar lista, e os dois usam.
"""
import ast
import io
import json
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()

import main  # noqa: E402

_BAIXA = "_supabase_storage_download_prancha"


def _lacos_que_baixam(codigo):
    """Todo laço cujo corpo baixa do Storage.

    🩸 04/09, teste de mutação DESTE guarda: a 1ª versão procurava só
    `ast.Call` com `func.id == _BAIXA` — chamada DIRETA. Mas três dos cinco
    laços chamam por `await run_in_threadpool(_supabase_storage_download_
    prancha, ...)`, onde a função é um ARGUMENTO, não o alvo da chamada. O
    guarda achava 6 laços e três deles eram de debug; os três reais faltavam.

    🚨 Provado por mutação: devolvi um laço ao estado de "descarta calado" e o
    guarda passou VERDE. Ou seja, o meu guarda anti-verde-falso estava
    falsamente verde — e o `>= 5` de controle passava contando os laços de
    debug, que nem são caminho de cliente.

    🔑 Casar `ast.Name` cobre as duas formas de uma vez, e continua cobrindo
    qualquer jeito novo de despachar a mesma função.
    """
    arv = ast.parse(codigo)
    return [n for n in ast.walk(arv)
            if isinstance(n, (ast.For, ast.AsyncFor))
            and any(isinstance(x, ast.Name) and x.id == _BAIXA
                    for st in n.body for x in ast.walk(st))]


def _perdas_caladas(codigo):
    """Laços que descartam prancha sem juntar o nome pra contar depois.

    O julgamento: se o laço tem um `continue` no ramo em que o download voltou
    vazio, alguma coisa nesse mesmo ramo tem que REGISTRAR a perda (um
    `.append(...)` numa lista). Sem isso, o arquivo some sem deixar rastro.
    """
    ruins = []
    for laco in _lacos_que_baixam(codigo):
        for st in laco.body:
            if not isinstance(st, ast.If):
                continue
            tem_continue = any(isinstance(x, ast.Continue) for x in st.body)
            if not tem_continue:
                continue
            registra = any(
                isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)
                and x.func.attr == "append"
                for s in st.body for x in ast.walk(s))
            if not registra:
                ruins.append(laco.lineno)
    return sorted(set(ruins))


def _descarta_a_prancha(laco):
    """Este laço JOGA FORA a prancha que não baixou (em vez de reportar)?

    🪤 A 1ª versão deste guarda cobrava o alerta de TODA função que baixa em
    laço, e acusou três que estão certas — `_rodar`, `_rodar_qualidade` e
    `debug_libredwg_batch` gravam `item["resultado"] = "não consegui baixar"`
    pra cada item, ou seja, elas já contam. Guarda que exige o remédio de quem
    não tem a doença vira obstáculo; o que importa é DESCARTAR calado.
    """
    for st in laco.body:
        if isinstance(st, ast.If) and any(isinstance(x, ast.Continue)
                                          for x in st.body):
            return True
    return False


def _lista_entregue_ao_alerta(fn):
    """Os NOMES de lista que esta função entrega ao alerta."""
    nomes = set()
    for c in ast.walk(fn):
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) \
                and c.func.id == "_alerta_pranchas_perdidas":
            for a in list(c.args) + [k.value for k in c.keywords]:
                if isinstance(a, ast.Name):
                    nomes.add(a.id)
    return nomes


def _nomes_appendados(no):
    """`x.append(...)` em qualquer lugar deste nó → {'x'}."""
    nomes = set()
    for c in ast.walk(no):
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) \
                and c.func.attr == "append" \
                and isinstance(c.func.value, ast.Name):
            nomes.add(c.func.value.id)
    return nomes


def _perdas_na_lista_errada(codigo):
    """Laços que anotam a perda numa lista que o alerta NUNCA vê.

    🩸 06/09/2026 — O BURACO QUE SOBROU DO CENSO. Ele se contentava com a
    EXISTÊNCIA de um `.append` qualquer no ramo do `continue`. Trocar
    `_perdidas.append(fname)` por `_ignorados.append(fname)` — com o
    `_alerta_pranchas_perdidas(job_id, _perdidas, ...)` intacto logo abaixo —
    satisfazia o censo, entregava lista VAZIA ao alerta e não acusava nada: a
    prancha some e o cliente recebe `done` numa leitura incompleta.

    🔑 Aqui a pergunta é outra: a lista que recebe o nome é a MESMA que chega
    ao alerta?
    """
    arv = ast.parse(codigo)
    ruins = []
    for fn in ast.walk(arv):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if fn.name in ("_alerta_pranchas_perdidas", _BAIXA):
            continue
        entregues = _lista_entregue_ao_alerta(fn)
        if not entregues:
            continue        # função que não avisa é assunto de `_alertas_ausentes`
        for laco in ast.walk(fn):
            if not isinstance(laco, (ast.For, ast.AsyncFor)):
                continue
            if not any(isinstance(x, ast.Name) and x.id == _BAIXA
                       for st in laco.body for x in ast.walk(st)):
                continue
            for st in laco.body:
                if not isinstance(st, ast.If):
                    continue
                if not any(isinstance(x, ast.Continue) for x in st.body):
                    continue
                registrados = _nomes_appendados(st)
                if registrados and not (registrados & entregues):
                    ruins.append(
                        "%s (linha %d) anota a perda em %s e entrega %s ao alerta"
                        % (fn.name, laco.lineno, sorted(registrados),
                           sorted(entregues)))
    return sorted(set(ruins))


def _alertas_ausentes(codigo):
    """Funções que DESCARTAM prancha num laço e nunca chamam o alerta."""
    arv = ast.parse(codigo)
    ruins = []
    for fn in ast.walk(arv):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if fn.name in ("_alerta_pranchas_perdidas", _BAIXA):
            continue
        descarta = any(
            _descarta_a_prancha(n)
            for n in ast.walk(fn) if isinstance(n, (ast.For, ast.AsyncFor))
            and any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                    and c.func.id == _BAIXA
                    for st in n.body for c in ast.walk(st)))
        if not descarta:
            continue
        alerta = any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                     and c.func.id == "_alerta_pranchas_perdidas"
                     for c in ast.walk(fn))
        if not alerta:
            ruins.append(fn.name)
    return sorted(set(ruins))


# ══════════════════════════════════════════════════════════════════════════
#  O julgamento sobre o código REAL
# ══════════════════════════════════════════════════════════════════════════
class _Parou(BaseException):
    """Sentinela: para o caminho logo depois do ponto que a gente mede.

    🪤 06/09/2026 — HERDA DE BaseException DE PROPÓSITO. `_retomar_job_do_storage`
    embrulha tudo num `except Exception`, então o freio comum era ENGOLIDO: o
    teste via "não parou" e, pior, um freio engolido daria a mesma cara de um
    caminho que nunca chamou o alerta. Mesma régua do guarda do resgate por PDF.
    """


def _storage_de_mentira(monkeypatch, presentes, sumidas, respostas=None):
    """Storage que LISTA todas as pranchas e só ENTREGA algumas.

    É o caso de 18/08 encenado: o arquivo existe na listagem e o download volta
    vazio (truncado, e por isso descartado desde 03/09).
    """
    import urllib.request as _ur

    nomes = list(presentes) + list(sumidas)
    respostas = respostas or {}
    diario = []

    class _Resp:
        def __init__(self, dados):
            self._d = dados

        def read(self):
            return self._d

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _urlopen(req, timeout=None):
        url, metodo = req.full_url, req.get_method()
        diario.append((metodo, url))
        for chave, dados in respostas.items():
            if chave in url:
                return _Resp(dados)
        if "storage/v1/object/list" in url:
            return _Resp(json.dumps([{"name": n} for n in nomes]).encode())
        return _Resp(b"[]")

    monkeypatch.setattr(_ur, "urlopen", _urlopen)
    monkeypatch.setattr(main, _BAIXA,
                        lambda job_id, fname: (b"PDF-de-mentira"
                                               if fname in presentes else None))
    return diario


_PRESENTES = ["planta-a.pdf", "planta-c.pdf"]
_SUMIDA = "planta-b.pdf"


class _ReqFalso(object):
    """O mínimo que as rotas leem de um Request."""
    headers = {}
    client = None


class _ArquivoFalso(object):
    """O mínimo que `add_file_and_reprocess` lê de um UploadFile."""

    def __init__(self, filename):
        self.filename = filename


def _linha_do_projeto():
    return json.dumps([{
        "job_id": "job-orig", "is_eval": False, "typology": "office",
        "project_type": "arquitetura", "status": "done",
        "reprocess_count": 0, "auto_resume_count": 0,
        "user_total_area": 0, "user_pe_direito": 0,
        "user_email": "cliente-NN@example.com", "project_name": "Obra cliente-NN",
    }]).encode()


def _rodar(saida):
    """Aceita `def` e `async def` — o mesmo julgamento vale pros dois."""
    import asyncio
    import inspect
    if inspect.isawaitable(saida):
        return asyncio.run(saida)
    return saida


# ── os CINCO caminhos de cliente, cada um armado do seu jeito ──────────────
def _driver_filhote(monkeypatch):
    monkeypatch.setattr(main, "_require_admin", lambda *a, **k: {"email": "x"})
    return lambda: main.admin_eval_reprocess("job-orig", request=None)


def _driver_retomada(monkeypatch):
    return lambda: main._retomar_job_do_storage("job-orig")


def _driver_reprocesso(monkeypatch):
    monkeypatch.setattr(main, "_require_project_owner",
                        lambda *a, **k: {"email": "dono@example.com"})
    monkeypatch.setattr(main, "_get_user_from_request",
                        lambda *a, **k: {"email": "dono@example.com"})
    return lambda: _rodar(main.reprocess_project("job-orig", request=_ReqFalso()))


def _driver_add_file(monkeypatch):
    """🚨 O PIOR DOS CINCO: é o caminho em que o cliente manda o CAD que A
    GENTE PEDIU. Ele fez exatamente o que pedimos e receberia menos."""
    async def _grava(arquivo, destino):
        io.open(destino, "wb").write(b"CAD-de-mentira")
        return len(b"CAD-de-mentira"), None

    monkeypatch.setattr(main, "_require_project_owner",
                        lambda *a, **k: {"email": "dono@example.com"})
    monkeypatch.setattr(main, "_rate_limit_ok", lambda *a, **k: True)
    monkeypatch.setattr(main, "_stream_upload_to_disk", _grava)
    monkeypatch.setattr(main, "_supabase_storage_upload_prancha",
                        lambda *a, **k: True)
    return lambda: _rodar(main.add_file_and_reprocess(
        "job-orig", request=_ReqFalso(), files=[_ArquivoFalso("planta-a.pdf")]))


def _driver_combinar(monkeypatch):
    monkeypatch.setattr(main, "_require_admin", lambda *a, **k: {"email": "x"})
    return lambda: _rodar(main.admin_eval_combine("job-orig", request=None))


#: 🪤 06/09/2026 — A CONVERSÃO SÓ RODAVA UM DOS CINCO. Os outros quatro —
#: inclusive a retomada automática depois de queda e o add-file — ficavam só
#: com o censo AST, que se contentava com a EXISTÊNCIA de um `.append` no ramo
#: do `continue`. Appendar na lista ERRADA satisfazia o censo e escapava do
#: guarda executado: a prancha some e o cliente recebe `done` numa leitura
#: incompleta, que é literalmente o caso de 18/08.
_CAMINHOS = [
    ("admin_eval_reprocess", _driver_filhote),
    ("_retomar_job_do_storage", _driver_retomada),
    ("reprocess_project", _driver_reprocesso),
    ("add_file_and_reprocess", _driver_add_file),
    ("admin_eval_combine", _driver_combinar),
]


@pytest.mark.parametrize("nome,armar", _CAMINHOS, ids=[n for n, _ in _CAMINHOS])
def test_nenhum_laco_descarta_prancha_sem_registrar(
        nome, armar, monkeypatch, tmp_path):
    """Cada caminho perde 1 de 3 pranchas — e o alerta recebe o NOME dela.

    Não basta a lista existir: ela tem que chegar CHEIA no alerta. Appendar num
    `_ignorados` que ninguém entrega passa no censo e some aqui.
    """
    avisos = []

    def _alerta(job_id, perdidos, total, onde):
        avisos.append({"job_id": job_id, "perdidos": list(perdidos),
                       "total": total, "onde": onde})
        raise _Parou()          # o que vem depois é o job inteiro; já medimos

    _storage_de_mentira(
        monkeypatch, presentes=_PRESENTES, sumidas=[_SUMIDA],
        respostas={"rest/v1/projects": _linha_do_projeto()})
    monkeypatch.setattr(main, "WORK_DIR", str(tmp_path))
    monkeypatch.setattr(main, "_alerta_pranchas_perdidas", _alerta)
    chamar = armar(monkeypatch)

    with pytest.raises(_Parou):
        chamar()

    assert avisos, (
        "%s baixou 2 de 3 pranchas e o alerta nunca foi chamado — o arquivo "
        "some e o cliente recebe `done` numa leitura incompleta" % nome)
    assert avisos[0]["perdidos"] == [_SUMIDA], (
        "%s descartou a prancha e a lista de perdas chegou %r — ou o laço "
        "appenda numa lista que ninguém entrega, ou o nome se perde no caminho"
        % (nome, avisos[0]["perdidos"]))
    assert avisos[0]["total"] == 3, (
        "%s não diz de QUANTAS: %r — '1 perdida' num envio de 2 e num de 40 "
        "são coisas muito diferentes" % (nome, avisos[0]["total"]))

def test_toda_funcao_que_baixa_em_laco_avisa_da_perda():
    ausentes = _alertas_ausentes(_FONTE)
    assert not ausentes, (
        "estas funções baixam do Storage num laço e nunca chamam "
        "`_alerta_pranchas_perdidas`: %s" % ", ".join(ausentes))


def test_a_perda_e_anotada_na_MESMA_lista_que_chega_ao_alerta():
    """🪤 O censo aceitava um `.append` qualquer. Appendar na lista ERRADA
    passava por ele, entregava lista vazia ao alerta e a prancha sumia."""
    erradas = _perdas_na_lista_errada(_FONTE)
    assert not erradas, (
        "a perda é anotada numa lista que o alerta nunca vê: %s"
        % "; ".join(erradas))


def _funcoes_que_descartam(codigo):
    """Os NOMES das funções que jogam fora prancha que não baixou."""
    arv = ast.parse(codigo)
    nomes = set()
    for fn in ast.walk(arv):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for laco in ast.walk(fn):
            if isinstance(laco, (ast.For, ast.AsyncFor)) \
                    and any(isinstance(x, ast.Name) and x.id == _BAIXA
                            for st in laco.body for x in ast.walk(st)) \
                    and _descarta_a_prancha(laco):
                nomes.add(fn.name)
    return nomes


def test_os_cinco_caminhos_de_cliente_estao_cobertos():
    """🪤 Verde vazio é verde falso — e ESTE teste já foi verde falso uma vez.

    🩸 04/09: aqui estava `len(_lacos_que_baixam(...)) >= 5`. Passava contando
    os QUATRO laços de debug (`_rodar`, `debug_libredwg_batch`), enquanto três
    dos cinco caminhos de cliente estavam invisíveis pro guarda. Contagem crua
    aceita qualquer coisa que chegue ao número; nome exige que sejam ESTES.
    """
    esperadas = {"_retomar_job_do_storage", "reprocess_project",
                 "admin_eval_reprocess", "admin_eval_combine",
                 "add_file_and_reprocess"}
    achadas = _funcoes_que_descartam(_FONTE)
    faltando = esperadas - achadas
    assert not faltando, (
        "o guarda não enxerga mais estes caminhos de cliente: %s — os testes "
        "acima passam sem olhar pra eles" % ", ".join(sorted(faltando)))
    # 🪤 06/09/2026 — E CENSO NÃO É EXECUÇÃO. Enquanto só um dos cinco rodava,
    # os outros quatro estavam cobertos por uma pergunta sobre a FORMA do
    # código. Caminho novo entra aqui e no `_CAMINHOS`, ou este teste reclama.
    rodados = {n for n, _ in _CAMINHOS}
    assert esperadas == rodados, (
        "estes caminhos de cliente são julgados só pelo censo AST, ninguém os "
        "EXECUTA: %s" % ", ".join(sorted(esperadas - rodados)))


def test_o_alerta_e_CRITICO_e_diz_quantas_de_quantas():
    corpo = _FONTE[_FONTE.index("def _alerta_pranchas_perdidas"):]
    corpo = corpo[:corpo.index("\ndef ", 10)]
    assert 'severity="critical"' in corpo, (
        "a perda parcial voltou a ser gravada como erro comum — ela some no "
        "meio do bookkeeping do painel")
    assert "%d de %d" in corpo, (
        "o alerta parou de dizer QUANTAS de QUANTAS — '1 arquivo perdido' num "
        "envio de 2 e num de 40 são coisas muito diferentes")


# ══════════════════════════════════════════════════════════════════════════
#  O aviso tem que SOBREVIVER — dois pontos gravavam por cima
# ══════════════════════════════════════════════════════════════════════════
def _updates_que_trocam_o_array(codigo):
    """`warnings` gravado num UPDATE sem ler o que já existe.

    🔑 INSERT é isento de propósito: linha nova não tem histórico pra apagar.
    O guarda de ontem não fazia essa distinção e reprovou o `_supabase_insert`
    legítimo do reprocesso — guarda que acusa código certo vira obstáculo.

    🔑 Formas aceitas num UPDATE: chamada a `_avisos_com` (o helper) ou uma
    concatenação (`_existing + _novos`), que por construção lê o que havia.
    Recusadas: lista literal e nome solto — foi por um nome solto que o
    defeito passaria despercebido pelo guarda anterior.
    """
    arv = ast.parse(codigo)
    isentos, suspeitos = set(), set()
    for n in ast.walk(arv):
        if not isinstance(n, ast.Call):
            continue
        nome = getattr(n.func, "id", "") or getattr(n.func, "attr", "")
        primeiro = (n.args[0].value
                    if n.args and isinstance(n.args[0], ast.Constant) else None)
        alvo = isentos if (nome == "_supabase_insert" or primeiro == "POST") else (
            suspeitos if (nome == "_supabase_update" or primeiro == "PATCH") else None)
        if alvo is None:
            continue
        for d in ast.walk(n):
            if isinstance(d, ast.Dict):
                alvo.add(id(d))
    ruins = []
    for n in ast.walk(arv):
        if not isinstance(n, ast.Dict) or id(n) not in suspeitos:
            continue
        if id(n) in isentos:
            continue
        for c, v in zip(n.keys, n.values):
            if not (isinstance(c, ast.Constant) and c.value == "warnings"):
                continue
            ok = (isinstance(v, ast.Call)
                  and getattr(v.func, "id", "") == "_avisos_com") \
                or isinstance(v, ast.BinOp)
            if not ok:
                ruins.append(n.lineno)
    return sorted(set(ruins))


def test_nenhum_update_troca_o_array_de_avisos():
    ruins = _updates_que_trocam_o_array(_FONTE)
    assert not ruins, (
        "UPDATE gravando `warnings` sem ler o que já existe (linha %s) — apaga "
        "o aviso de prancha perdida e tudo o mais que o projeto tinha"
        % ", ".join(str(n) for n in ruins))


def test_o_helper_aceita_LISTA_e_nao_so_um_aviso():
    """Sem isto os dois pontos que gravam a lista do motor não teriam como
    usar o helper — e foi por isso que eles ficaram de fora ontem."""
    fn = [n for n in ast.walk(ast.parse(_FONTE))
          if isinstance(n, ast.FunctionDef) and n.name == "_avisos_com"][0]
    fonte_fn = ast.get_source_segment(_FONTE, fn) or ""
    assert "isinstance(novo_aviso, (list, tuple))" in fonte_fn, (
        "`_avisos_com` voltou a aceitar só um aviso — os dois pontos que "
        "gravam a lista inteira do motor ficam sem caminho e voltam a "
        "sobrescrever")


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLES POSITIVOS — o código de ANTES, nas MESMAS funções
# ══════════════════════════════════════════════════════════════════════════
_LACO_ANTIGO = '''
async def reprocess_project():
    file_paths = []
    for fname in original_filenames:
        data = _supabase_storage_download_prancha(job_id, fname)
        if not data:
            continue
        file_paths.append(fname)
    if not file_paths:
        raise HTTPException(500, "Falha ao baixar arquivos do Storage")
'''


def test_CONTROLE_o_laco_de_ANTES_REPROVA_no_mesmo_julgamento():
    assert _perdas_caladas(_LACO_ANTIGO), (
        "o julgamento aprova um laço que descarta prancha calado — ele não "
        "está julgando nada e o teste de cima é verde falso")
    assert _alertas_ausentes(_LACO_ANTIGO) == ["reprocess_project"], (
        "o julgamento não vê a função sem alerta: %s"
        % _alertas_ausentes(_LACO_ANTIGO))


#: O laço que o censo ANTIGO aprovava: tem `.append` no ramo do `continue`, tem
#: alerta chamado — só que a lista anotada não é a lista entregue.
_LACO_LISTA_ERRADA = '''
async def reprocess_project():
    file_paths = []
    _perdidas = []
    _ignorados = []
    for fname in original_filenames:
        data = _supabase_storage_download_prancha(job_id, fname)
        if not data:
            _ignorados.append(fname)
            continue
        file_paths.append(fname)
    _alerta_pranchas_perdidas(job_id, _perdidas, len(original_filenames), "x")
'''

_LACO_CERTO = _LACO_LISTA_ERRADA.replace("_ignorados.append", "_perdidas.append")


def test_CONTROLE_o_julgamento_da_LISTA_separa_o_certo_do_errado():
    """🧪 Sem os dois lados, um julgamento que devolvesse sempre vazio (ou
    sempre cheio) passaria pelo teste do código real."""
    assert not _perdas_caladas(_LACO_LISTA_ERRADA), (
        "o censo ANTIGO já pegava este caso — então ele não prova nada de novo")
    erradas = _perdas_na_lista_errada(_LACO_LISTA_ERRADA)
    assert len(erradas) == 1 and "_ignorados" in erradas[0], (
        "o julgamento aprovou um laço que anota a perda em `_ignorados` e "
        "entrega `_perdidas` (vazia) ao alerta: %s" % erradas)
    assert not _perdas_na_lista_errada(_LACO_CERTO), (
        "o julgamento acusa o laço CERTO — guarda que reprova código bom vira "
        "obstáculo: %s" % _perdas_na_lista_errada(_LACO_CERTO))


_UPDATES_ANTIGOS = '''
def a():
    _supabase_update("projects", "job_id", job_id, {"warnings": [_warn_zero]})
def b():
    _lst = [_warn_zero]
    _supabase_update("projects", "job_id", job_id, {"warnings": _lst})
def c():
    _supabase_insert("projects", {"job_id": novo, "warnings": [_av]})
def d():
    _supabase_update("projects", "job_id", job_id,
                     {"warnings": _avisos_com(job_id, _av)})
def e():
    _supabase_update("projects", "job_id", job_id,
                     {"warnings": _existing + _novos})
'''


def test_CONTROLE_o_julgamento_dos_UPDATES_separa_os_cinco_casos():
    """Duas reprovações (lista literal e nome solto) e três aprovações.

    🩸 O caso `b` é o que o guarda de ontem NÃO pegava: ele só enxergava lista
    LITERAL, então bastava passar por uma variável pra escapar. Foi assim que a
    varredura provou que ele mentia.
    🩸 E o caso `c` é o que ele acusava ERRADO: INSERT de linha nova.
    """
    ruins = _updates_que_trocam_o_array(_UPDATES_ANTIGOS)
    linhas = ast.parse(_UPDATES_ANTIGOS)
    nomes = {f.name: f.lineno for f in linhas.body}
    assert len(ruins) == 2, (
        "esperava exatamente 2 reprovações (lista literal e nome solto), "
        "achei %s" % ruins)
    assert all(r > nomes["a"] for r in ruins)
    assert all(r < nomes["d"] for r in ruins), (
        "o julgamento reprovou o helper ou a concatenação, que são corretos")
