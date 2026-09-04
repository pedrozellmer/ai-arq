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
import os

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()

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
def test_nenhum_laco_descarta_prancha_sem_registrar():
    ruins = _perdas_caladas(_FONTE)
    assert not ruins, (
        "laço que baixa do Storage e descarta prancha sem juntar o nome "
        "(linha %s do main.py) — o arquivo some e o cliente recebe `done` numa "
        "leitura incompleta" % ", ".join(str(n) for n in ruins))


def test_toda_funcao_que_baixa_em_laco_avisa_da_perda():
    ausentes = _alertas_ausentes(_FONTE)
    assert not ausentes, (
        "estas funções baixam do Storage num laço e nunca chamam "
        "`_alerta_pranchas_perdidas`: %s" % ", ".join(ausentes))


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
