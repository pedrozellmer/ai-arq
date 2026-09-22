# -*- coding: utf-8 -*-
"""A frase que conta de onde veio a escala não pode negar a própria fonte.

🩸 08/09/2026, visto ao vivo no job de um cliente. Uma prancha conseguiu escala
1:50 pela VOTAÇÃO das cotas, e o log saiu assim:

    escala 1:50.0 de cotas SEM prova de cota

E não é log: a mesma frase entra no PROMPT como instrução pra IA escrever a
procedência na observação que o CLIENTE lê —

    "a escala veio de cotas e não foi provada por cota"
    "medido do desenho com escala 1:50.0 lida do cotas"

Dois defeitos numa linha: **"lida do cotas"** (o template cravava "do" e a
fonte é um substantivo que varia) e a **contradição** (negar a fonte que acabou
de citar).

🔑 A confusão de origem: são dois mecanismos de nome parecido.
  · DERIVAR — votar cotas × vãos pra DESCOBRIR a escala (`scale_src='cotas'`,
    exige 4 votos E o dobro do 2º colocado);
  · VALIDAR — cruzar uma escala já conhecida com elemento medido na view
    principal (`escala_validada`, exige 2 pares a ±2%).
Passar no primeiro e não no segundo é NORMAL: a validação só olha a view
principal. A frase tem que dizer isso, não desmentir a fonte.

📏 Medido na base: 66 pranchas vieram de carimbo (22 jobs), 14 de viewport
(4 jobs), 5 de cotas (3 jobs), desde 14/08. As 5 de cotas liam a frase quebrada.

🚫 Nada disto muda o NÚMERO: sem confirmação continua estimado (regra nº1).
"""
import io
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

_MAIN = os.path.join(_BACKEND, "main.py")

# O molde real da linha de escala do prompt (main.py, seção de medição do
# `process_job`). É o contrato: `test_a_linha_de_escala_do_prompt_EXECUTADO_e_este_molde`
# executa o trecho de verdade e reprova se o main.py mudar o molde.
# 🪤 22/09 (revisão): aqui morava também um `_MOLDE_REGRA` com o texto ANTIGO da
# regra — ninguém o usava, a regra mudou e nada caiu. A regra agora é
# `_regra_da_medicao_sem_prova`, e quem guarda o molde dela é
# test_a_contagem_nao_diz_medido_do_desenho.py, chamando a função.
_MOLDE_ESCALA = "Escala 1:50 lida {fonte}. {ressalva}."


def _funcao():
    """Executa só o trecho da decisão — importar main.py conecta em Supabase."""
    src = io.open(_MAIN, encoding="utf-8").read()
    ini = "_FONTE_DA_ESCALA = {"
    # 🪤 21/09: o dicionário e a frase subiram pra dentro da fatia dos testes de
    # honestidade de área (a frase do número preservado chama os dois). A borda
    # antiga, `import re as _re_escala`, passou a engolir mil linhas no meio —
    # inclusive `os.getenv`, que aqui não existe. A 1ª linha de CÓDIGO depois
    # dos dois é a constante da frase nova.
    fim = "\n_PREFIXO_CABE_NA_GEOMETRIA = "
    assert src.count(ini) == 1, "a âncora de início mudou"
    i = src.index(ini)
    ns = {"__name__": "escala_fonte_ns"}
    exec(compile(src[i:src.index(fim, i)], "main_fonte_slice", "exec"), ns)
    return ns["_frase_da_escala_sem_prova"], ns["_FONTE_DA_ESCALA"]


_FONTES_REAIS = ["carimbo", "viewport", "cotas"]


# ══════════════════════════════════════════════════════════════════════════
#  O defeito: a frase negava a própria fonte
# ══════════════════════════════════════════════════════════════════════════
def test_quando_a_escala_VEIO_das_cotas_a_frase_nao_diz_que_nao_veio():
    f, _ = _funcao()
    fonte, ressalva = f("cotas")
    frase = _MOLDE_ESCALA.format(fonte=fonte, ressalva=ressalva)

    assert "cota" in fonte.lower(), "a frase tem que dizer que a escala veio das cotas"
    assert "não foi provada por cota" not in frase.lower(), (
        "a frase nega a fonte que acabou de citar:\n  " + frase)
    assert "não foi confirmada por cota" not in frase.lower(), (
        "mesma contradição com outra palavra:\n  " + frase)
    # o que ela PRECISA dizer: a ressalva verdadeira é sobre a view principal
    assert "view principal" in ressalva.lower(), (
        "sem dizer O QUE faltou, a ressalva vira vaga: " + ressalva)


# ══════════════════════════════════════════════════════════════════════════
#  O erro de português — "lida do cotas"
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("src", _FONTES_REAIS + ["", None, "fonte-nova-qualquer"])
def test_a_frase_sai_em_portugues_para_toda_fonte(src):
    f, _ = _funcao()
    fonte, ressalva = f(src)
    frase = _MOLDE_ESCALA.format(fonte=fonte, ressalva=ressalva)

    # o molde já escreve "lida " — a fonte tem que trazer a preposição dela
    assert fonte[:2].lower() in ("do", "da", "de"), (
        "a fonte tem que começar pela preposição, senão o molde 'lida {x}' "
        "quebra: " + repr(fonte))
    assert "lida do cotas" not in frase, "o defeito original voltou: " + frase
    assert not frase.startswith(" ") and ".." not in frase, frase
    assert "  " not in frase, "espaço duplo: " + frase
    for pedaco in (fonte, ressalva):
        assert pedaco and pedaco.strip() == pedaco, repr(pedaco)
        assert not pedaco.endswith("."), (
            "o molde já põe o ponto — dois pontos finais: " + repr(pedaco))


@pytest.mark.parametrize("src", _FONTES_REAIS)
def test_cada_fonte_conta_uma_historia_DIFERENTE(src):
    """CONTROLE POSITIVO: uma frase genérica pra todas passaria em tudo acima
    e não diria nada. Carimbo, viewport e cotas falham por motivos distintos."""
    f, _ = _funcao()
    outras = [f(o) for o in _FONTES_REAIS if o != src]
    minha = f(src)
    for outra in outras:
        assert minha[0] != outra[0], "duas fontes com a mesma frase: " + str(minha)
        assert minha[1] != outra[1], "duas fontes com a mesma ressalva: " + str(minha)


def test_fonte_desconhecida_admite_que_nao_sabe():
    """🪤 Fonte nova (ou vazia) não pode virar frase torta nem mentira
    confiante. O certo é dizer que não sabe."""
    f, _ = _funcao()
    fonte, ressalva = f("algo_que_ainda_nao_existe")
    assert "não identificada" in fonte.lower() or "não" in ressalva.lower()
    frase = _MOLDE_ESCALA.format(fonte=fonte, ressalva=ressalva)
    assert "lida de origem não identificada" in frase, frase


def test_a_ressalva_nunca_promete_medicao():
    """Regra dura nº1: nenhuma ressalva pode soar como confirmação.

    🪤 A 1ª versão deste teste proibia a palavra "medido" e reprovava a
    ressalva CERTA — a de cotas diz "nenhum par cota×elemento **medido** a
    confirmou", onde "medido" qualifica o elemento, não promete nada. Proibir
    palavra é peneira de FORMA; o que importa é a ressalva carregar a marca da
    limitação.
    """
    f, _ = _funcao()
    _LIMITES = ("não", "nenhum", "declara", "sugere", "sem ")
    for src in _FONTES_REAIS + ["desconhecida"]:
        _, ressalva = f(src)
        r = ressalva.lower()
        assert any(m in r for m in _LIMITES), (
            src + " → a ressalva não marca limitação nenhuma: " + ressalva)
        # e não pode afirmar que a escala foi confirmada
        assert "foi confirmada" not in r and "está confirmada" not in r, (
            src + " → ressalva afirma confirmação: " + ressalva)


# ══════════════════════════════════════════════════════════════════════════
#  INTEGRAÇÃO — o process_job tem que USAR a função, não remontar a frase
# ══════════════════════════════════════════════════════════════════════════
def test_o_process_job_chama_a_funcao_em_vez_de_remontar():
    """🪤 Guarda de FONTE, e assumido como tal: ele não prova comportamento,
    prova que a única frase existente é a que os testes acima exercitam. Sem
    ele, alguém remonta `f"lida do {_fonte}"` inline e os testes de cima
    continuam verdes falando de uma função que ninguém chama."""
    src = io.open(_MAIN, encoding="utf-8").read()

    import ast

    assert src.count("_frase_da_escala_sem_prova") >= 3, (
        "esperado: a definição + a chamada no process_job + a docstring")

    # 🪤 A 1ª versão filtrava linhas que começam com "#" e reprovou por causa do
    # DOCSTRING que cita o template antigo pra explicar o defeito. Comentário e
    # texto citado não são código. Pelo AST a diferença é exata: só interessa o
    # que é f-string DE VERDADE (JoinedStr), e docstring é Constant.
    quebrados = []
    for no in ast.walk(ast.parse(src)):
        if isinstance(no, ast.JoinedStr):
            literal = "".join(p.value for p in no.values
                              if isinstance(p, ast.Constant) and isinstance(p.value, str))
            if "lida do " in literal or "SEM prova de cota" in literal:
                quebrados.append((getattr(no, "lineno", "?"), literal[:90]))
    assert not quebrados, (
        "o template quebrado / a frase contraditória voltaram como f-string "
        "viva: " + str(quebrados[:3]))


@pytest.mark.parametrize("src", _FONTES_REAIS + ["vista"])
def test_a_linha_de_escala_do_prompt_EXECUTADO_e_este_molde(src):
    """Executa o trecho REAL da seção de medição (da fonte até `_vet_secao`) e
    compara a linha de escala com `_MOLDE_ESCALA` — o contrato do topo."""
    import textwrap
    from _corpo import corpo_de
    fonte_py = io.open(_MAIN, encoding="utf-8").read()
    ini = "_fonte_txt, _ressalva = _frase_da_escala_sem_prova(_fonte)"
    fim = '_vet_secao = "\\n".join(_l2)'
    assert fonte_py.count(ini) == 1 and fonte_py.count(fim) == 1
    a = fonte_py.rindex("\n", 0, fonte_py.index(ini)) + 1
    b = fonte_py.index("\n", fonte_py.index(fim))
    f, _ = _funcao()
    ns = {"__name__": "secao_ns", "_frase_da_escala_sem_prova": f,
          "_vm": {"scale": 50, "scale_src": src}, "_fonte": src}
    exec(compile(corpo_de("_regra_da_medicao_sem_prova", src=fonte_py), "regra", "exec"), ns)
    exec(compile(textwrap.dedent(fonte_py[a:b + 1]), "secao", "exec"), ns)
    fonte, ressalva = f(src)
    assert ns["_l2"][2] == _MOLDE_ESCALA.format(fonte=fonte, ressalva=ressalva), ns["_l2"]
