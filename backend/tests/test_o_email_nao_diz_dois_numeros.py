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
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()

_CAB_PLANOB = ("O motor precisou do leitor alternativo em 1 prancha "
               "(plano B): PRANCHA-01. ")

_ESCRITAS_DE_SELO = []


def _itens(medidos, total, espioes=False):
    """Itens de um job qualquer — `medidos` com selo branco, o resto laranja."""
    from models import BudgetItem, Confidence
    base = _ItemEspiao if espioes else BudgetItem
    itens = [base(item_num="1.%d" % k, description="Serviço %d" % k, unit="m²",
                  quantity=10.0 + k,
                  confidence=(Confidence.CONFIRMADO if k < medidos
                              else Confidence.ESTIMADO),
                  origem="dxf_geom")
             for k in range(total)]
    del _ESCRITAS_DE_SELO[:]          # o construtor não conta
    return itens


def _monta_espiao():
    """Item que ANOTA toda escrita em `.confidence`, seja qual for a forma."""
    from models import BudgetItem

    class _Espiao(BudgetItem):
        def __setattr__(self, nome, valor):
            if nome == "confidence":
                _ESCRITAS_DE_SELO.append(
                    (getattr(self, "description", "?"), str(valor)))
            return super().__setattr__(nome, valor)
    return _Espiao


_ItemEspiao = _monta_espiao()


def _diagnostico_com(avisos, medidos, total):
    """O bloco 'Como lemos o seu projeto' — o REAL, o mesmo do e-mail."""
    import main
    from _fim_do_job import ProjetoFake
    return main._build_reading_diagnostic(
        _itens(medidos=medidos, total=total), 0, 1, "", ProjetoFake(warnings=avisos))


def _process_job(arvore=None):
    arv = arvore or ast.parse(_FONTE)
    for n in ast.walk(arv):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and n.name == "process_job":
            return n
    pytest.fail("não achei `process_job`")


def _linhas_da_recontagem(fn):
    return sorted(n.lineno for n in ast.walk(fn)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id == "_recontar_aviso_planob")


# ══════════════════════════════════════════════════════════════════════════
#  O julgamento sobre o código REAL
# ══════════════════════════════════════════════════════════════════════════
# 🪤 06/09 — os dois guardas de baixo rodavam UM cenário só: `project_type=''`,
# `partial_failure=False`, `is_complement=False`, `n_pdf=0`, `n_cad=1`,
# `dwg_failed=[]`. Rebaixamento de selo que dependesse de qualquer uma dessas
# condições — e é justamente onde vivem os de unidade, escala e parede —
# acontecia depois da recontagem sem que nenhum dos dois enxergasse. Cada linha
# aqui é um job que o produto processa de verdade.
_JOBS = [
    ("so_cad", {}),
    ("cad_e_pdf", {"n_pdf": 2, "n_cad": 1}),
    ("so_pdf", {"n_pdf": 2, "n_cad": 0}),
    ("estrutural", {"project_type": "estrutural"}),
    ("complemento", {"is_complement": True}),
    ("falha_parcial", {"partial_failure": True,
                       "partial_errors": ["a prancha 3 não abriu"]}),
    ("dwg_que_nao_abriu", {"dwg_failed": ["planta.dwg"]}),
]
_IDS = [j[0] for j in _JOBS]


@pytest.mark.parametrize("rotulo,cenario", _JOBS, ids=_IDS)
def test_a_recontagem_vem_DEPOIS_do_ultimo_rebaixamento(rotulo, cenario):
    """O MESMO e-mail não pode dizer dois números de medidos.

    Reproduz o job `b5693ca6`: o aviso do plano B nasce com a contagem da hora
    em que o plano B rodou (aqui, 8), e a recontagem final é quem o corrige pros
    6 que sobraram. Se alguém rebaixar selo DEPOIS dela — ou se a recontagem
    deixar de acontecer — o cabeçalho diz um número e o parágrafo diz outro.
    Foi exatamente o que o cliente `cliente-03` leu.

    🔑 E em TODO tipo de job: com PDF, estrutural, complemento, falha parcial.
    O e-mail de complemento é outro e-mail, montado por outro ramo — e carrega
    o mesmo diagnóstico e o mesmo aviso.
    """
    from _fim_do_job import roda_ate_o_email, medidos_no_placar, medidos_no_aviso
    d = roda_ate_o_email(_itens(medidos=6, total=20), cab_planob=_CAB_PLANOB,
                         medidos_antes=8, **cenario)
    html = d["emails"][-1]["html"]
    no_placar = medidos_no_placar(html)
    no_aviso = medidos_no_aviso(html)
    assert no_placar is not None, "sumiu o placar de medidos do e-mail (%s)" % rotulo
    assert no_aviso is not None, (
        "o aviso do plano B não chegou ao e-mail (%s) — sem ele este guarda "
        "não mede nada" % rotulo)
    assert no_placar == no_aviso, (
        "%s: o mesmo e-mail diz %d medido(s) no cabeçalho e %d no aviso do "
        "plano B — alguém rebaixa selo DEPOIS da recontagem final"
        % (rotulo, no_placar, no_aviso))


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


@pytest.mark.parametrize("rotulo,cenario", _JOBS, ids=_IDS)
def test_o_rebaixamento_do_SINAPI_e_mesmo_o_ultimo(rotulo, cenario):
    """Depois da recontagem final, NADA mexe mais no selo — nem na contagem.

    🪤 O outro lado do mesmo fato, e o que pega a forma que enganou o juiz
    antigo: os itens são espiões, então `setattr` e atribuição direta contam
    igual.

    🪤 06/09 — e o espião tem um ponto cego próprio: quem quisesse mudar o
    número do e-mail não precisa tocar em `.confidence`. Basta FILTRAR
    `all_items` depois da recontagem — nenhum `__setattr__` acontece e o
    espião fica mudo. Por isso a contagem também é cobrada aqui."""
    from _fim_do_job import roda_ate_o_email, medidos_no_placar, medidos_no_aviso
    itens = _itens(medidos=6, total=20, espioes=True)
    d = roda_ate_o_email(itens, cab_planob=_CAB_PLANOB, **cenario)
    assert not _ESCRITAS_DE_SELO, (
        "%s: %d item(ns) tiveram o selo mexido DEPOIS da última recontagem: "
        "%r — o e-mail volta a dizer dois números"
        % (rotulo, len(_ESCRITAS_DE_SELO), _ESCRITAS_DE_SELO[:4]))

    # 🔑 O segundo caminho: mexer na CONTAGEM em vez do selo.
    assert len(d["ns"]["all_items"]) == 20, (
        "%s: a lista de itens mudou de tamanho depois da recontagem (%d de 20) "
        "— o e-mail passa a contar em cima de outra lista"
        % (rotulo, len(d["ns"]["all_items"])))
    html = d["emails"][-1]["html"]
    assert medidos_no_placar(html) == medidos_no_aviso(html) == 6, (
        "%s: o e-mail saiu com placar=%r e aviso=%r, e os itens entregues "
        "tinham 6 medidos — alguém mexeu na contagem depois da recontagem"
        % (rotulo, medidos_no_placar(html), medidos_no_aviso(html)))


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — a conferência sabe REPROVAR
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_o_email_de_ANTES_seria_reprovado():
    """A aritmética exata do job b5693ca6: o aviso ficou com 6, os itens com 5.

    Se esta conferência aprovar isto, o guarda de cima é verde falso."""
    from _fim_do_job import medidos_no_placar, medidos_no_aviso
    velho = (_CAB_PLANOB + "As medições saíram (6 item(ns) medido(s) do CAD), "
             "mas vale conferir 2-3 medidas-chave contra o projeto antes de "
             "fechar orçamento.")
    html = _diagnostico_com([velho], medidos=5, total=20)
    assert medidos_no_placar(html) == 5 and medidos_no_aviso(html) == 6, (
        "não reproduzi o e-mail de 04/09 — placar=%r aviso=%r"
        % (medidos_no_placar(html), medidos_no_aviso(html)))
    assert medidos_no_placar(html) != medidos_no_aviso(html), (
        "a conferência aprova o e-mail que disse 5 e 6 — ela não está "
        "conferindo nada")


def test_CONTROLE_o_email_RECONTADO_passa_na_mesma_conferencia():
    """O outro lado: com o aviso recontado, os dois números batem."""
    from _fim_do_job import medidos_no_placar, medidos_no_aviso
    novo = (_CAB_PLANOB + "As medições saíram (5 item(ns) medido(s) do CAD), "
            "mas vale conferir 2-3 medidas-chave contra o projeto antes de "
            "fechar orçamento.")
    html = _diagnostico_com([novo], medidos=5, total=20)
    assert medidos_no_placar(html) == medidos_no_aviso(html) == 5, (
        "a conferência reprova o e-mail certo — está apertada demais")
