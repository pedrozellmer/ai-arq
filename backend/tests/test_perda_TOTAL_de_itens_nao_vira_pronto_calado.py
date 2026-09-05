# -*- coding: utf-8 -*-
"""Perder TODOS os itens na gravação virava "pronto" com contagem mentirosa.

🩸 04/09/2026. O guarda de 01/09 (`test_persist_confere_o_que_gravou`) pegou a
perda PARCIAL e deixou a TOTAL passar por uma condição só.

`_persist_items_to_supabase` devolve **0** nos dois caminhos de exceção — HTTP
4xx/5xx do PostgREST e qualquer outra falha. E quem chama fazia:

    _itens_no_banco = _n_gravados if isinstance(_n_gravados, int) and _n_gravados > 0 \\
        else len(all_items)

Zero não passa no `> 0`. Então o chamador adotava `len(all_items)` — o número
que a gente QUIS gravar — e a comparação logo abaixo (`_itens_no_banco !=
len(all_items)`) dava False. Resultado, com o banco vazio:

  · `items_count` do projeto anuncia 50;
  · o cliente NÃO recebe o aviso de que a tela de revisão está vazia;
  · a planilha em anexo tem os 50 itens, e a tela mostra zero;
  · nada disso chega ao `error_log`: os dois `except` chamam `_supa_log`, que
    escreve num ARQUIVO LOCAL do Render — some no redeploy.

Ou seja: o único caso em que o cliente perde TUDO era também o único que não
avisava ninguém. Perder metade gritava; perder tudo, silêncio.

🪤 Este guarda EXECUTA o trecho real do `main.py` em vez de procurar texto. Os
dois guardas do ponto de chamada que já existiam eram de texto e continuaram
verdes com o defeito de pé — eles conferem que o retorno é USADO, não COMO ele
é usado. Ver [[feedback_procurei_a_palavra_nao_o_comportamento]].

📉 Contexto medido no mesmo dia: 53% dos projetos concluídos não têm nenhuma
linha medida e 29,6% das linhas saem zeradas — este defeito não explica esses
números, é outra doença. Aqui o assunto é só o silêncio.
"""
import io
import os
import sys
import textwrap

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

_INI = "        _itens_no_banco = _n_gravados"
_FIM = "        _supa_ok = _supabase_update("


def _fonte():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _trecho_real():
    """O bloco do main.py que decide a contagem e o aviso.

    🪤 Ancorado nos DOIS extremos. Janela de tamanho fixo já me fez reprovar
    teste correto só porque um comentário cresceu acima do trecho.
    """
    src = _fonte()
    assert src.count(_INI) == 1, (
        "a âncora do início mudou (%d ocorrências) — o guarda cegou"
        % src.count(_INI))
    i = src.index(_INI)
    j = src.index(_FIM, i)
    return textwrap.dedent(src[i:j])


def _rodar(n_gravados, n_montados=50):
    """Executa o trecho REAL e devolve (contagem_adotada, avisos)."""

    class _PD(object):
        warnings = None

    ns = {
        "_n_gravados": n_gravados,
        "all_items": list(range(n_montados)),
        "project_data": _PD(),
    }
    exec(compile(_trecho_real(), "<trecho-main>", "exec"), ns, ns)
    return ns["_itens_no_banco"], (ns["project_data"].warnings or [])


# ══════════════════════════════════════════════════════════════════════════
#  O DEFEITO
# ══════════════════════════════════════════════════════════════════════════
def test_perda_TOTAL_nao_vira_contagem_cheia():
    """Banco ficou vazio: o projeto não pode anunciar os 50 que não entraram."""
    contagem, _ = _rodar(n_gravados=0, n_montados=50)
    assert contagem == 0, (
        "a gravação falhou inteira (0 no banco) e o projeto adotou %r — é o "
        "número que a gente MANDOU, não o que existe. A tela de revisão fica "
        "vazia anunciando %r itens" % (contagem, contagem))


def test_perda_TOTAL_avisa_o_cliente():
    """O pior caso era o único mudo."""
    _, avisos = _rodar(n_gravados=0, n_montados=50)
    assert avisos, (
        "perdemos TODOS os itens e o cliente não é avisado de nada — ele abre "
        "a tela de revisão vazia sem explicação")
    texto = " ".join(avisos)
    assert "não chegaram na tela de revisão do site" in texto
    assert "ESTÃO na planilha em anexo" in texto, (
        "o aviso não diz onde os itens ainda existem — é a parte acionável")
    assert "50" in texto, "o aviso não diz quantos itens sumiram"


# ══════════════════════════════════════════════════════════════════════════
#  O QUE NÃO PODE QUEBRAR
# ══════════════════════════════════════════════════════════════════════════
def test_perda_PARCIAL_continua_pegando():
    """O comportamento de 01/09 tem que sobreviver ao conserto de hoje."""
    contagem, avisos = _rodar(n_gravados=33, n_montados=50)
    assert contagem == 33
    assert avisos and "17" in " ".join(avisos), (
        "o aviso de perda parcial parou de dizer quantos faltaram")


def test_gravacao_COMPLETA_nao_alarma_ninguem():
    """🪤 O alarme que dispara sempre é ruído, e ruído é desligado."""
    contagem, avisos = _rodar(n_gravados=50, n_montados=50)
    assert contagem == 50
    assert not avisos, (
        "gravação perfeita gerou aviso de perda — falso positivo em 100%% dos "
        "jobs sãos: %r" % (avisos,))


def test_retorno_NAO_numerico_cai_no_que_montamos():
    """Se um dia a função devolver None/str, não dá pra adotar isso como
    contagem. O comportamento antigo (usar o que montamos) é o certo AQUI —
    o problema nunca foi o fallback, foi o zero cair nele."""
    contagem, avisos = _rodar(n_gravados=None, n_montados=50)
    assert contagem == 50
    assert not avisos


# ══════════════════════════════════════════════════════════════════════════
#  TODO CAMINHO QUE DEVOLVE 0 TEM QUE GRITAR
# ══════════════════════════════════════════════════════════════════════════
import ast

_GRITO = "_gritar_perda_total"


def _handlers_que_devolvem_zero(fonte, nome_func="_persist_items_to_supabase"):
    """Todo `except` do persist cujo corpo devolve 0, e se ele grita.

    🪤 Cobertura por LUGAR, não por contagem. Um guarda meu de 04/09 de manhã
    conferia `>= 5` chamadas e passava verde contando laços de DEBUG enquanto
    3 dos 5 lugares reais estavam descobertos. Aqui a pergunta é feita a CADA
    handler: "você devolve zero? então você grita?".
    """
    arvore = ast.parse(fonte)
    alvo = next((n for n in ast.walk(arvore)
                 if isinstance(n, ast.FunctionDef) and n.name == nome_func), None)
    assert alvo is not None, "não achei %s — o guarda cegou" % nome_func
    achados = []
    for h in ast.walk(alvo):
        if not isinstance(h, ast.ExceptHandler):
            continue
        devolve_zero = any(
            isinstance(n, ast.Return) and isinstance(n.value, ast.Constant)
            and n.value.value == 0
            for n in ast.walk(h))
        if not devolve_zero:
            continue
        grita = any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == _GRITO
            for n in ast.walk(h))
        achados.append((getattr(h, "lineno", -1), grita))
    return achados


def test_TODO_caminho_que_devolve_zero_grita():
    achados = _handlers_que_devolvem_zero(_fonte())
    assert len(achados) >= 2, (
        "esperava ao menos os 2 caminhos de exceção que devolvem 0, achei %d — "
        "ou o código mudou de forma, ou o guarda cegou" % len(achados))
    mudos = [ln for ln, grita in achados if not grita]
    assert not mudos, (
        "há caminho(s) que devolvem 0 SEM gritar, na(s) linha(s) %r — a perda "
        "total volta a morrer no arquivo local do Render" % (mudos,))


def test_CONTROLE_um_handler_MUDO_e_reprovado():
    """🧪 Se eu consertasse só um dos dois `except`, este teste tem que ver."""
    meio_conserto = textwrap.dedent('''
        def _persist_items_to_supabase(job_id, items):
            rows = []
            try:
                pass
            except ValueError as e:
                _supa_log("x")
                _gritar_perda_total(job_id, len(rows), "a")
                return 0
            except Exception as e:
                _supa_log("y")
                return 0
        ''')
    achados = _handlers_que_devolvem_zero(meio_conserto)
    assert len(achados) == 2, "o controle está mal montado"
    assert [g for _, g in achados].count(False) == 1, (
        "o julgamento não distingue o handler mudo do que grita")


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — o código de ANTES, no MESMO julgamento
# ══════════════════════════════════════════════════════════════════════════
_ANTES = '''
_itens_no_banco = _n_gravados if isinstance(_n_gravados, int) and _n_gravados > 0 \\
    else len(all_items)
if _itens_no_banco != len(all_items):
    project_data.warnings = (getattr(project_data, "warnings", None) or []) + [
        "avisou"]
'''


def _rodar_antes(n_gravados, n_montados=50):
    class _PD(object):
        warnings = None
    ns = {"_n_gravados": n_gravados, "all_items": list(range(n_montados)),
          "project_data": _PD()}
    exec(compile(_ANTES, "<antes>", "exec"), ns, ns)
    return ns["_itens_no_banco"], (ns["project_data"].warnings or [])


def test_CONTROLE_o_codigo_de_ANTES_engolia_a_perda_total():
    """Sem isto, os dois testes de cima poderiam estar aprovando qualquer coisa."""
    contagem, avisos = _rodar_antes(n_gravados=0, n_montados=50)
    assert contagem == 50, "o controle está mal montado"
    assert not avisos, (
        "o controle deveria mostrar o silêncio de antes — se ele avisa, o "
        "defeito que estou consertando não era esse")


def test_CONTROLE_o_codigo_de_ANTES_JA_pegava_a_perda_parcial():
    """Delimita o defeito: o de antes não era cego, era cego SÓ no zero."""
    contagem, avisos = _rodar_antes(n_gravados=33, n_montados=50)
    assert contagem == 33 and avisos, "o controle está mal montado"
