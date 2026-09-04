# -*- coding: utf-8 -*-
"""Limpeza escrita no fim de um laço é promessa que todo `continue` quebra.

🩸 03/09/2026, 2ª rodada da revisão adversarial. O laço de extração de DXF
(`for idx, dxf_path in enumerate(dxf_paths)`) terminava movendo a prancha pro
`_preview` e apagando o `arq_dxf_*` da conversão. Só que ele tem TRÊS saídas
antecipadas:

    1. `dxf:extract-timeout`      (extração passou de 900 s)
    2. extração falhou            (o ramo que monta `dxf_errors`)
    3. **checkpoint da RETOMADA** (`if _dxf_stem in _ckpt_cache: … continue`)

De manhã eu tapei as duas primeiras com `_apaga_dir_de_conversao` e **não vi a
terceira** — que é a pior das três, porque perde DUAS coisas de uma vez:

  • a conversão de DWG **roda de novo** na retomada (nada a pula), então o
    `arq_dxf_*` fica no disco até o fim do job; e
  • a prancha nunca chega no `_preview`, então **o preview morre justo nos jobs
    que caíram e voltaram** — que são os grandes, os que mais precisam dele.

🔑 Por isso este guarda não procura frase nenhuma: ele lê a ÁRVORE do `main.py`,
acha o laço pelo cabeçalho, junta todo `continue` que pertence a ele (sem descer
em laço ou função de dentro) e cobra limpeza antes de cada um. `continue` novo
que alguém escrever amanhã já nasce coberto.

🪤 O `continue` de dentro do `for _r in (_cp.get("items") or [])` é de OUTRO
laço e não entra na conta — se entrasse, o guarda cobraria limpeza no meio da
restauração dos itens e viraria obstáculo.
"""
import ast
import io
import os

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()

# As duas funções que fecham a pasta da conversão. Qualquer uma serve: a de
# falha só apaga, a da retomada guarda pro preview antes de apagar.
_LIMPEZAS = ("_guarda_dxf_pro_preview", "_apaga_dir_de_conversao")


def _acha_laco(arvore):
    """O `for idx, dxf_path in enumerate(dxf_paths):` do process_job."""
    for no in ast.walk(arvore):
        if not isinstance(no, ast.For):
            continue
        alvo = no.target
        if not (isinstance(alvo, ast.Tuple) and len(alvo.elts) == 2):
            continue
        nomes = [e.id for e in alvo.elts if isinstance(e, ast.Name)]
        it = no.iter
        if nomes == ["idx", "dxf_path"] and isinstance(it, ast.Call) \
                and isinstance(it.func, ast.Name) and it.func.id == "enumerate":
            return no
    return None


def _continues_do_laco(laco):
    """(Continue, lista de irmãos) de cada `continue` QUE PERTENCE a este laço.

    Não desce em `for`/`while`/`def`/`class` de dentro: o `continue` de lá é do
    laço de lá.
    """
    achados = []

    def anda(corpo):
        for st in corpo:
            if isinstance(st, ast.Continue):
                achados.append((st, corpo))
            elif isinstance(st, (ast.For, ast.AsyncFor, ast.While,
                                 ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                pass
            else:
                for campo in ("body", "orelse", "finalbody"):
                    anda(getattr(st, campo, None) or [])
                for h in getattr(st, "handlers", None) or []:
                    anda(h.body)

    anda(laco.body)
    return achados


def _tem_limpeza_antes(alvo, corpo):
    """Alguma instrução ANTES do `continue`, no mesmo bloco, limpa a conversão?"""
    for st in corpo:
        if st is alvo:
            return False
        for n in ast.walk(st):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                    and n.func.id in _LIMPEZAS:
                return True
    return False


def _saidas_sem_limpeza(codigo):
    """As linhas dos `continue` do laço que escapam sem limpar. [] = tudo ok."""
    laco = _acha_laco(ast.parse(codigo))
    if laco is None:
        pytest.fail("não achei o laço `for idx, dxf_path in enumerate(...)` — "
                    "se ele foi renomeado, este guarda parou de guardar")
    return [c.lineno for c, corpo in _continues_do_laco(laco)
            if not _tem_limpeza_antes(c, corpo)]


# ══════════════════════════════════════════════════════════════════════════
#  O julgamento sobre o código REAL
# ══════════════════════════════════════════════════════════════════════════
def test_nenhum_continue_do_laco_escapa_sem_limpar():
    fujoes = _saidas_sem_limpeza(_FONTE)
    assert not fujoes, (
        "há `continue` no laço de extração que pula a limpeza da conversão "
        "(linha %s do main.py) — a pasta `arq_dxf_*` fica no disco até o fim do "
        "job e a prancha não chega no _preview"
        % ", ".join(str(n) for n in fujoes))


def test_o_laco_tem_as_tres_saidas_que_a_gente_conhece():
    """Se o número cair, alguém apagou uma saída — ou o guarda parou de achar.

    🪤 Sem isto, um `_acha_laco` que devolvesse um laço ERRADO (sem `continue`
    nenhum) faria o teste de cima passar vazio, e o verde seria falso.
    """
    laco = _acha_laco(ast.parse(_FONTE))
    n = len(_continues_do_laco(laco))
    assert n >= 3, (
        "o laço tinha 3 saídas antecipadas (timeout, extração falhou, "
        "checkpoint) e agora tem %d — ou sumiu uma, ou o guarda está olhando "
        "pro laço errado" % n)


def test_a_saida_da_retomada_guarda_a_prancha_pro_preview():
    """🩸 O furo do dia: só apagar não bastava, o preview precisa do arquivo.

    Na retomada a prancha não é reprocessada, mas ela EXISTE — foi convertida
    de novo neste run. Apagar sem guardar deixaria o cliente sem preview
    exatamente no job que já tinha caído uma vez.
    """
    laco = _acha_laco(ast.parse(_FONTE))
    ckpt = [c for c, corpo in _continues_do_laco(laco)
            if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id == "_guarda_dxf_pro_preview"
                   for st in corpo for n in ast.walk(st))]
    assert len(ckpt) >= 1, (
        "nenhuma saída antecipada guarda a prancha pro preview — a da retomada "
        "tem que guardar, não só apagar")


def test_o_fim_do_laco_continua_guardando_pro_preview():
    """O caminho normal (nada deu errado) é o que alimenta o preview sempre."""
    laco = _acha_laco(ast.parse(_FONTE))
    ultimas = laco.body[-6:]
    assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == "_guarda_dxf_pro_preview"
               for st in ultimas for n in ast.walk(st)), (
        "o fim do corpo do laço parou de guardar a prancha pro preview")


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — o MESMO julgamento sobre um laço furado
# ══════════════════════════════════════════════════════════════════════════
_LACO_FURADO = '''
def process_job():
    for idx, dxf_path in enumerate(dxf_paths):
        if idx in cache:
            for r in cache[idx]:
                if not r:
                    continue          # <- de OUTRO laço, não conta
            continue                  # <- ESTE escapa sem limpar
        try:
            extrair(dxf_path)
        except Timeout:
            _apaga_dir_de_conversao(dxf_path)
            continue                  # <- coberto
        _guarda_dxf_pro_preview(dxf_path, work_dir, job_id)
'''


def test_CONTROLE_o_laco_de_ANTES_do_conserto_REPROVA():
    """O código de hoje de manhã: duas saídas tapadas, a da retomada não."""
    fujoes = _saidas_sem_limpeza(_LACO_FURADO)
    assert fujoes, (
        "o julgamento aprova um laço com `continue` sem limpeza — ele não está "
        "julgando nada, e o teste de cima é verde falso")
    assert len(fujoes) == 1, (
        "esperava exatamente 1 saída furada (a do checkpoint); o `continue` do "
        "laço de dentro não pode entrar na conta — achei %s" % fujoes)
