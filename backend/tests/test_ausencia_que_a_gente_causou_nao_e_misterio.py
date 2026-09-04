# -*- coding: utf-8 -*-
"""A prancha que NÓS apagamos não pode entrar no balde de "sumiu, não sei por quê".

🩸 03/09/2026, 2ª rodada da revisão adversarial. A thread de preview de CAD
itera `dxf_paths` e, quando o arquivo não existe, soma `sem_dxf`. Só que o laço
de extração apaga de propósito a pasta da conversão de toda prancha que falhou
(`_apaga_dir_de_conversao`) — e deixa o caminho morto dentro de `dxf_paths`.
Resultado: **a nossa própria limpeza virava `sem_dxf`.**

🔑 Por que isso importa mais do que parece: `sem_dxf` não é enfeite, é o balde
de diagnóstico. Foi olhando ele que a causa do preview do cliente franweldon
apareceu, em 10/08 — eu tinha apostado em timeout e estava errado. Balde de
diagnóstico envenenado pela própria limpeza faz a próxima investigação começar
por uma pista falsa. Agora são dois fatos separados: `descartada` (fomos nós) e
`sem_dxf` (ninguém explica).

🪤 E a docstring do `_apaga_dir_de_conversao` afirmava que era seguro apagar
"porque depois do laço `dxf_paths` só é usado em bool() e len() — ninguém lê o
arquivo de uma prancha pulada". Era **falso**: a thread do preview lê. Invariante
escrita errada é pior que invariante nenhuma — é o que a próxima pessoa cita pra
não conferir. O que torna seguro de verdade é a thread só disparar bem depois do
laço, e tratar arquivo ausente.
"""
import ast
import io
import os

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _blocos_com(codigo, nome_chamada):
    """Todo bloco de instruções que contém uma chamada a `nome_chamada`."""
    achados = []

    def anda(corpo):
        if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == nome_chamada
               for st in corpo for n in ast.walk(st)):
            achados.append(corpo)
        for st in corpo:
            for campo in ("body", "orelse", "finalbody"):
                anda(getattr(st, campo, None) or [])
            for h in getattr(st, "handlers", None) or []:
                anda(h.body)

    anda(ast.parse(codigo).body)
    # o bloco mais interno é o que interessa (o corpo do except, não a função)
    return [b for b in achados
            if not any(o is not b and _contem(b, o) for o in achados)]


def _contem(externo, interno):
    for st in externo:
        for n in ast.walk(st):
            if n is interno:
                return True
    return False


def _descartes_nao_registrados(codigo):
    """Blocos que apagam a conversão SEM anotar que a ausência foi nossa.

    🩸 03/09, varredura adversarial: a 1ª versão só olhava
    `_apaga_dir_de_conversao`. Mas `_guarda_dxf_pro_preview` TAMBÉM apaga — nos
    dois casos em que não consegue guardar (acima do teto de 50 MB do render, e
    quando o `shutil.move` falha) — e não anotava nada. Ou seja: o guarda que eu
    escrevi pra impedir exatamente isto não enxergava a outra metade do próprio
    conserto, porque eu o escrevi olhando UMA função em vez do COMPORTAMENTO
    (apagar).

    🔑 Lá dentro o registro é feito pelo parâmetro `descartadas`, então o
    julgamento aceita as duas formas: `_descartadas.add(...)` no bloco, ou o
    conjunto passado como argumento pra função que apaga.
    """
    ruins = []
    for nome in ("_apaga_dir_de_conversao", "_guarda_dxf_pro_preview"):
        for bloco in _blocos_com(codigo, nome):
            anota = any(
                isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "add"
                and isinstance(n.func.value, ast.Name)
                and n.func.value.id == "_descartadas"
                for st in bloco for n in ast.walk(st))
            # ou o registro viaja como argumento pra quem apaga
            passa = any(
                isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == nome
                and any(isinstance(a, ast.Name) and a.id == "_descartadas"
                        for a in n.args)
                for st in bloco for n in ast.walk(st))
            if not (anota or passa):
                ruins.append(min(st.lineno for st in bloco))
    return ruins


# ══════════════════════════════════════════════════════════════════════════
#  O julgamento sobre o código REAL
# ══════════════════════════════════════════════════════════════════════════
def test_todo_descarte_nosso_fica_anotado():
    ruins = sorted(_descartes_nao_registrados(_FONTE))
    assert not ruins, (
        "há lugar que apaga a conversão sem anotar em `_descartadas` (linha %s "
        "do main.py) — a thread de preview vai contar essa prancha como "
        "`sem_dxf`, que é o balde de causa desconhecida"
        % ", ".join(str(n) for n in ruins))


def test_existem_os_dois_sitios_de_descarte():
    """Se cair pra menos de 2, ou sumiu um ramo de falha, ou o guarda cegou."""
    n = len(_blocos_com(_FONTE, "_apaga_dir_de_conversao"))
    assert n >= 2, (
        "o laço tinha 2 descartes (timeout e extração falhou) e o guarda achou "
        "%d — verde vazio é verde falso" % n)


def test_quem_recebe_o_registro_de_fato_ANOTA():
    """🪤 O julgamento aceita "passou `_descartadas` como argumento" — e isso
    seria fácil de enganar: bastava a função receber o conjunto e ignorar.

    Então aqui a cobrança é dentro de `_guarda_dxf_pro_preview`: ela tem que
    chamar `descartadas.add(...)` quando não conseguiu guardar a prancha.
    """
    fn = [n for n in ast.walk(ast.parse(_FONTE))
          if isinstance(n, ast.FunctionDef)
          and n.name == "_guarda_dxf_pro_preview"]
    assert fn, "sumiu `_guarda_dxf_pro_preview`"
    assert "descartadas" in [a.arg for a in fn[0].args.args], (
        "a função parou de receber o registro dos descartes")
    anota = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "add"
                and isinstance(n.func.value, ast.Name)
                and n.func.value.id == "descartadas"
                for n in ast.walk(fn[0]))
    assert anota, (
        "`_guarda_dxf_pro_preview` recebe o registro e não anota nada — a "
        "prancha que ELA apaga (acima do teto de preview, ou move falhado) "
        "volta pro balde `sem_dxf`, que é o de causa desconhecida")


def test_o_preview_separa_o_que_a_gente_apagou():
    assert '_prev["descartada"] += 1' in _FONTE, (
        "a thread de preview voltou a jogar tudo em `sem_dxf` — a ausência que "
        "a gente causou some dentro da que ninguém explica")
    assert 'if _dxf_path in _descartadas:' in _FONTE, (
        "sumiu a consulta ao registro dos descartes")


def test_o_resumo_do_preview_mostra_o_balde_novo():
    """Contador que não aparece no log não conserta investigação nenhuma."""
    assert "descartada={_prev['descartada']}" in _FONTE, (
        "o balde `descartada` existe mas não sai no resumo — ninguém vai ver")


def test_a_lista_nasce_junto_com_dxf_paths():
    """🪤 A thread de preview lê `_descartadas` por closure.

    Se a inicialização for parar dentro de um `if`, um job sem CAD deixa o nome
    sem valor e a thread quebra. Nascer no MESMO bloco de `dxf_paths` é o que
    garante que os dois existem juntos ou não existem.
    """
    def _nomes(bloco):
        return {a.id for st in bloco if isinstance(st, ast.Assign)
                for a in st.targets if isinstance(a, ast.Name)}

    achou = []

    def anda(corpo):
        n = _nomes(corpo)
        if "dxf_paths" in n:
            achou.append("_descartadas" in n)
        for st in corpo:
            for campo in ("body", "orelse", "finalbody"):
                anda(getattr(st, campo, None) or [])
            for h in getattr(st, "handlers", None) or []:
                anda(h.body)

    anda(ast.parse(_FONTE).body)
    assert achou, "não achei onde `dxf_paths` é criada"
    assert all(achou), (
        "`_descartadas` não é criada no mesmo bloco que `dxf_paths` — separadas, "
        "uma pode existir sem a outra e a thread de preview quebra")


def test_a_docstring_nao_afirma_mais_a_invariante_falsa():
    """🩸 Ela dizia que ninguém lê o arquivo de uma prancha pulada. Lê."""
    i = _FONTE.index("def _apaga_dir_de_conversao")
    doc = _FONTE[i:_FONTE.index('"""', _FONTE.index('"""', i) + 3)]
    assert "Era falso" in doc or "Era **falso**" in doc, (
        "a docstring voltou a afirmar a invariante sem marcar que ela é falsa")
    assert "_render_cad_previews_bg" in doc, (
        "sumiu quem é que lê o arquivo — sem o nome, a correção não ajuda "
        "ninguém a conferir")


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — o MESMO julgamento sobre o código de antes
# ══════════════════════════════════════════════════════════════════════════
_ANTES = '''
def process_job():
    try:
        extrair(dxf_path)
    except Timeout:
        dxf_errors.append("demorou demais")
        _apaga_dir_de_conversao(dxf_path)
        continue
    except Exception:
        dxf_errors.append("nao consegui ler")
        _apaga_dir_de_conversao(dxf_path)
        _descartadas.add(dxf_path)
        continue
'''


def test_CONTROLE_o_codigo_de_ANTES_REPROVA_na_mesma_funcao():
    ruins = _descartes_nao_registrados(_ANTES)
    assert ruins, (
        "o julgamento aprova um descarte sem registro — ele não julga nada e o "
        "teste de cima é verde falso")
    assert len(ruins) == 1, (
        "esperava exatamente 1 descarte sem registro (o do timeout); o segundo "
        "está anotado e não pode entrar na conta — achei %s" % ruins)

# 🪤 Aqui eu tinha escrito um segundo "controle" que afirmava que uma string
# escrita DUAS LINHAS ACIMA não continha `_prev["descartada"]`. É a tautologia
# que eu tinha acabado de tirar de outros quatro testes, no commit anterior,
# reaparecendo na primeira oportunidade. Apagado. O controle real deste arquivo
# é o de cima: mesmo julgamento, dois insumos.

