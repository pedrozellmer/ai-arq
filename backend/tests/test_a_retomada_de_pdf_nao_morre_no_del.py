# -*- coding: utf-8 -*-
"""A retomada morria na primeira prancha de PDF que tinha checkpoint.

🩸 03/09/2026, achado pela varredura adversarial dos 32 commits do dia. O laço
de pranchas de PDF termina com:

    del text, crop_paths, sheet, result

e os TRÊS primeiros nascem **só no `else`** — o caminho normal, que extrai
texto, recorta a prancha e chama a IA. O ramo do checkpoint (retomada depois de
queda) cria só `result`, cai no mesmo `del` e levanta:

    UnboundLocalError: cannot access local variable 'text'

🔑 O que torna isso grave é ONDE acontece: o checkpoint existe justamente pra
salvar o job pesado que já caiu uma vez (caso perplan/Rafael, 43 pranchas,
21/07). O mecanismo de recuperação morria na hora de recuperar. Medido no banco
em 03/09: **31 projetos já auto-retomaram**, 20 deles com o cache ligado.

🪤 Por que ninguém viu: o `del` é IRMÃO do `if/else` no corpo do laço, seis
instruções depois — longe o bastante pra ninguém ligar um ao outro lendo. E o
laço de DXF, que é o irmão desta lógica, tem `continue` no ramo do checkpoint,
então NÃO tem o problema. Um caminho tem a saída antecipada, o outro não.

🪤 Conferido antes de consertar: as 5 instruções entre o if/else e o `del` leem
só `result` — nenhuma toca em `text`, `crop_paths` ou `sheet`. Por isso o
conserto pode ser criar os nomes no ramo do checkpoint, sem inventar valor que
alguém fosse consumir.
"""
import ast
import io
import os

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _atribuidos(nos):
    """Nomes que este trecho de código cria."""
    return {x.id for st in nos for x in ast.walk(st)
            if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store)}


def _lidos(nos):
    return {x.id for st in nos for x in ast.walk(st)
            if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load)}


def _del_orfaos(codigo):
    """Nomes que o `del` do laço de prancha apaga sem que todo ramo os crie.

    Devolve {nome_do_ramo: [nomes órfãos]}. Vazio = todo caminho cria tudo.
    """
    arv = ast.parse(codigo)
    for laco in [n for n in ast.walk(arv) if isinstance(n, ast.For)]:
        corpo = laco.body
        dels = [k for k, s in enumerate(corpo) if isinstance(s, ast.Delete)]
        ifs = [k for k, s in enumerate(corpo)
               if isinstance(s, ast.If) and s.orelse
               and "_ckpt_cache" in ast.dump(s.test)]
        if not dels or not ifs:
            continue
        i_if, i_del = ifs[0], dels[0]
        if i_if > i_del:
            continue
        apagados = {t.id for t in corpo[i_del].targets if isinstance(t, ast.Name)}
        antes = _atribuidos(corpo[:i_if])
        ramo = corpo[i_if]
        return {
            "checkpoint": sorted(apagados - _atribuidos(ramo.body) - antes),
            "normal": sorted(apagados - _atribuidos(ramo.orelse) - antes),
        }
    pytest.fail("não achei o laço de prancha com checkpoint e `del` — se ele "
                "foi reescrito, este guarda parou de guardar")


# ══════════════════════════════════════════════════════════════════════════
#  O julgamento sobre o código REAL
# ══════════════════════════════════════════════════════════════════════════
def test_todo_ramo_cria_o_que_o_del_apaga():
    orfaos = _del_orfaos(_FONTE)
    ruins = {k: v for k, v in orfaos.items() if v}
    assert not ruins, (
        "o `del` do fim do laço apaga nome que algum ramo não cria — "
        "UnboundLocalError na retomada: %s" % ruins)


def test_o_ramo_do_checkpoint_cria_os_tres_nomes():
    """Explícito, pra a falha dizer QUAL nome sumiu."""
    arv = ast.parse(_FONTE)
    ck = [n for n in ast.walk(arv)
          if isinstance(n, ast.If) and isinstance(n.test, ast.Compare)
          and getattr(n.test.left, "id", "") == "_ck_key"][0]
    criados = _atribuidos(ck.body)
    for nome in ("text", "crop_paths", "sheet", "result"):
        assert nome in criados, (
            "o ramo do checkpoint parou de criar %r — a retomada volta a morrer "
            "com UnboundLocalError no `del` do fim do laço" % nome)


def test_ninguem_consome_os_tres_entre_o_if_e_o_del():
    """🪤 A premissa do conserto. Se alguém passar a LER `text`/`sheet` aí, os
    `None` que o checkpoint cria viram medição vazia calada — e aí o conserto
    certo deixa de ser este."""
    arv = ast.parse(_FONTE)
    laco = [n for n in ast.walk(arv) if isinstance(n, ast.For)
            and any(isinstance(s, ast.Delete) for s in n.body)
            and any(isinstance(s, ast.If) and "_ckpt_cache" in ast.dump(s.test)
                    for s in n.body)][0]
    corpo = laco.body
    i_if = [k for k, s in enumerate(corpo)
            if isinstance(s, ast.If) and "_ckpt_cache" in ast.dump(s.test)][0]
    i_del = [k for k, s in enumerate(corpo) if isinstance(s, ast.Delete)][0]
    lidos = _lidos(corpo[i_if + 1:i_del])
    intrusos = sorted({"text", "crop_paths", "sheet"} & lidos)
    assert not intrusos, (
        "agora alguém lê %s entre o if/else e o `del` — no caminho do "
        "checkpoint esses nomes são None de propósito, então esta leitura vai "
        "medir vazio calada. Reveja o conserto." % intrusos)


def test_o_laco_de_DXF_continua_saindo_antes():
    """O irmão desta lógica escapa por `continue` — é por isso que ele nunca
    teve o problema. Se alguém tirar o `continue` de lá, ele herda o defeito."""
    arv = ast.parse(_FONTE)
    dxf = [n for n in ast.walk(arv)
           if isinstance(n, ast.If) and isinstance(n.test, ast.Compare)
           and getattr(n.test.left, "id", "") == "_dxf_stem"][0]
    assert any(isinstance(s, ast.Continue) for s in dxf.body), (
        "o ramo do checkpoint de DXF perdeu o `continue` — confira se ele não "
        "passou a cair num `del` como o do PDF")


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — o MESMO julgamento sobre o código de ANTES
# ══════════════════════════════════════════════════════════════════════════
_ANTES = '''
def process_job():
    for i, (pdf_path, page_index) in enumerate(page_units):
        _ck_key = _sanitize_filename_for_storage(_stem)
        if _ck_key in _ckpt_cache:
            result = _ckpt_cache[_ck_key]
            print("retomando")
        else:
            text = extrair_texto(pdf_path)
            crop_paths = recortar(pdf_path)
            sheet = montar(text)
            result = analyze_sheet(sheet)
        if result.get("error"):
            sheet_errors.append(result["error"])
        del text, crop_paths, sheet, result
'''


def test_CONTROLE_o_codigo_de_ANTES_REPROVA_na_mesma_funcao():
    orfaos = _del_orfaos(_ANTES)
    assert orfaos["checkpoint"] == ["crop_paths", "sheet", "text"], (
        "o julgamento não vê os três nomes órfãos no código de antes — ele não "
        "está julgando nada e o teste de cima é verde falso; achei %r"
        % orfaos["checkpoint"])
    assert not orfaos["normal"], (
        "o caminho normal nunca teve o problema; se o julgamento acusa ele "
        "também, está acusando errado")
