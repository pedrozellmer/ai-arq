# -*- coding: utf-8 -*-
"""O mesmo e-mail dizia 5 e 6 medidos, três linhas de distância.

🩸 04/09/2026, job `b5693ca6` — primeiro projeto do cliente `cliente-03`,
8 DWGs de um prédio educacional. O e-mail que ele recebeu dizia:

    "✓ 5 medido(s) direto do CAD (em branco na planilha)"
    ...
    "As medições saíram (6 item(ns) medido(s) do CAD), mas vale conferir..."

Cinco e seis, para o mesmo fato, na mesma mensagem.

🔑 A CAUSA. Existe desde 01/09 uma recontagem que reescreve o aviso do plano B
com o número final de medidos, e o comentário dela dizia:

    "Tudo que rebaixa selo já rodou."

🚨 **Isso nunca foi verdade.** Medido no fonte que estava NO AR, antes de eu
mexer: havia **CINCO** atribuições de `.confidence` depois dessa recontagem
(escala divergente, bloco sem identidade, parede, SINAPI e selo-sem-medida). O
aviso está desatualizado desde o dia em que nasceu.

🩸 Eu primeiro escrevi aqui que "a causa fui eu, de hoje", porque o meu
rebaixamento por GRANDEZA do SINAPI roda ~19 s depois. Fui conferir no
`git show HEAD` e **a minha versão estava errada**: eu acrescentei a SEXTA, não
a primeira. O sintoma apareceu hoje; o defeito é de 01/09. Medido no log:

    13:06:20.237  aviso-planob-recontado : medidos finais=6
    13:06:39.575  sinapi-unidade         : n=2 (base=1 grandeza=1) rebaixei=1

🪤 A lição: **um bloco que afirma "já rodou tudo" vira mentira no dia em que
alguém acrescenta um passo depois dele** — e não quebra nada, não avisa
ninguém, só passa a mentir. Comentário não é garantia; guarda é.

Por isso este arquivo cobra a ORDEM, não a frase: a recontagem tem que ser a
última coisa depois de qualquer atribuição de selo.
"""
import ast
import io
import os

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _process_job(arvore=None):
    arv = arvore or ast.parse(_FONTE)
    for n in ast.walk(arv):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and n.name == "process_job":
            return n
    pytest.fail("não achei `process_job`")


def _linhas_que_mexem_no_selo(fn):
    """Toda atribuição a `.confidence` — é o que muda a contagem de medidos."""
    return sorted(n.lineno for n in ast.walk(fn)
                  if isinstance(n, ast.Assign)
                  for alvo in n.targets
                  if isinstance(alvo, ast.Attribute) and alvo.attr == "confidence")


def _linhas_da_recontagem(fn):
    return sorted(n.lineno for n in ast.walk(fn)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id == "_recontar_aviso_planob")


def _recontagem_cedo_demais(codigo):
    """A última recontagem vem DEPOIS do último rebaixamento? [] = ordem ok."""
    fn = _process_job(ast.parse(codigo))
    selos = _linhas_que_mexem_no_selo(fn)
    recontas = _linhas_da_recontagem(fn)
    if not recontas:
        return ["não há recontagem nenhuma"]
    if not selos:
        return []
    if max(recontas) < max(selos):
        return ["último rebaixamento na linha %d, última recontagem na %d"
                % (max(selos), max(recontas))]
    return []


# ══════════════════════════════════════════════════════════════════════════
#  O julgamento sobre o código REAL
# ══════════════════════════════════════════════════════════════════════════
def test_a_recontagem_vem_DEPOIS_do_ultimo_rebaixamento():
    fora_de_ordem = _recontagem_cedo_demais(_FONTE)
    assert not fora_de_ordem, (
        "a recontagem do aviso do plano B roda ANTES de algo que ainda rebaixa "
        "selo — o cliente lê dois números diferentes no mesmo e-mail: %s"
        % "; ".join(fora_de_ordem))


def test_existem_os_dois_pontos_de_recontagem():
    """Um pros jobs que nem chegam ao SINAPI, outro depois dele.

    🪤 Se sobrar só o primeiro, volta o defeito. Se sobrar só o segundo, job sem
    SINAPI (sem chave da IA, ou que falhou antes) fica sem recontagem nenhuma.
    """
    n = len(_linhas_da_recontagem(_process_job()))
    assert n >= 2, (
        "esperava a recontagem chamada em 2 pontos e achei %d" % n)


def test_a_recontagem_e_idempotente_por_INDICE():
    """Chamar duas vezes só é seguro porque ela reescreve pelo índice guardado,
    não procura a frase antiga por texto."""
    i = _FONTE.index("def _recontar_aviso_planob():")
    corpo = _FONTE[i:i + 2200]
    assert "_av[_aviso_lw_idx] = _novo" in corpo, (
        "a recontagem parou de reescrever por índice — procurar a frase por "
        "texto quebra calado quando alguém muda uma palavra")
    assert "_aviso_lw_idx" in corpo


def test_o_rebaixamento_do_SINAPI_e_mesmo_o_ultimo():
    """🪤 Se alguém acrescentar OUTRO rebaixamento depois da 2ª recontagem, o
    defeito volta — e este teste é quem vai contar."""
    fn = _process_job()
    selos = _linhas_que_mexem_no_selo(fn)
    recontas = _linhas_da_recontagem(fn)
    assert selos, "sumiu todo rebaixamento de selo do process_job"
    assert max(recontas) > max(selos), (
        "há atribuição de selo na linha %d, depois da última recontagem (%d)"
        % (max(selos), max(recontas)))


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — a ordem de ANTES, no MESMO julgamento
# ══════════════════════════════════════════════════════════════════════════
_ANTES = '''
def process_job():
    for _it in all_items:
        _it.confidence = _CfE.ESTIMADO      # escala divergente
    _recontar_aviso_planob()                # <- recontava AQUI
    for _it in lote:
        _it_u.confidence = _CfU.ESTIMADO    # ...e o SINAPI rebaixava DEPOIS
'''


def test_CONTROLE_a_ordem_ANTIGA_e_reprovada():
    fora = _recontagem_cedo_demais(_ANTES)
    assert fora, (
        "o julgamento aprova a ordem que produziu o e-mail com 5 e 6 — ele não "
        "está julgando nada e o teste de cima é verde falso")


_DEPOIS = '''
def process_job():
    for _it in all_items:
        _it.confidence = _CfE.ESTIMADO
    _recontar_aviso_planob()
    for _it in lote:
        _it_u.confidence = _CfU.ESTIMADO
    _recontar_aviso_planob()                # <- e de novo, no fim
'''


def test_CONTROLE_a_ordem_NOVA_passa_no_mesmo_julgamento():
    assert not _recontagem_cedo_demais(_DEPOIS), (
        "o julgamento reprova a ordem correta — está apertado demais")
