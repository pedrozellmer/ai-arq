# -*- coding: utf-8 -*-
"""Instrumento do selo: contar antes de mexer.

🩸 04/09/2026, medido em 156 projetos de cliente concluídos:

    · 83 de 156 (53%) não têm UMA ÚNICA linha branca
    · o selo VARIA entre rodadas do MESMO commit — duas rodadas com 3 segundos
      de diferença deram 30 × 34 itens e **9 × 6 medidos**

Enquanto isso for verdade, nenhum conserto de selo pode ser PROVADO. Foi
exatamente assim que o conserto de 26/08 passou 9 dias parecendo ter funcionado:
não havia contador que dissesse o contrário.

🔑 O que faltava é o OUTRO LADO de um guarda que já existe. `selos_sem_medida`
olha branco SEM prova e rebaixa. Ninguém olhava laranja COM prova — o teto do
que poderia virar branco. Medido no acervo: 109 linhas em 31 projetos (não as
559 que a primeira conta sugeria; 92 do "recuperável" foram rebaixadas DE
PROPÓSITO por guardas existentes).

🚫 O QUE ESTE INSTRUMENTO NÃO FAZ, E NÃO PODE PASSAR A FAZER: promover item.
`laranja_com_prova` é um NÚMERO, não uma lista de promoção. Promover a partir
daqui ressuscitaria o cross-check aposentado e o "área lida vira medida" — os
dois já refutados com medição neste projeto. Regra dura nº1.

🪤 Usa AS MESMAS constantes do guarda que rebaixa. Uma segunda definição de
"prova de geometria" divergiria da primeira em semanas, e aí os dois lados
contariam coisas diferentes com o mesmo nome.
"""
import ast
import io
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from engine_rules import retrato_do_selo as _retrato


def _item(selo, qtd, obs=""):
    return {"confidence": selo, "quantity": qtd, "observations": obs}


_OBS_GEOMETRIA = "Fonte: comprimento total do layer 'PAREDES' = 17,18 m"
_OBS_HACHURA = "Fonte: área hachurada do layer PISO-CERAMICO"
_OBS_TEXTO = "Fonte: texto da prancha — quadro de áreas"
_OBS_CARIMBO = "Fonte: carimbo da prancha"


# ══════════════════════════════════════════════════════════════════════════
#  1. A CONTA BÁSICA
# ══════════════════════════════════════════════════════════════════════════
def test_conta_a_composicao_do_job():
    r = _retrato([
        _item("confirmado", 10, _OBS_GEOMETRIA),
        _item("estimado", 48.5, _OBS_HACHURA),
        _item("estimado", 0, _OBS_TEXTO),
        _item("estimado", 3, _OBS_TEXTO),
    ])
    assert r["itens"] == 4
    assert r["brancos"] == 1
    assert r["laranjas"] == 3
    assert r["zerados"] == 1


def test_planilha_vazia_nao_explode():
    for vazio in ([], None):
        r = _retrato(vazio)
        assert r["itens"] == 0 and r["laranja_com_prova"] == 0


# ══════════════════════════════════════════════════════════════════════════
#  2. LARANJA COM PROVA — o teto que ninguém media
# ══════════════════════════════════════════════════════════════════════════
def test_laranja_com_numero_e_prova_de_geometria_e_contado():
    r = _retrato([_item("estimado", 48.5, _OBS_HACHURA)])
    assert r["laranja_com_prova"] == 1, (
        "laranja com número e prova escrita de geometria não foi contado — é "
        "justamente o número que faltava pra dimensionar o conserto do selo")


def test_laranja_ZERADO_nao_conta_mesmo_com_prova():
    """🪤 Linha sem número não é candidata a nada: não há o que selar."""
    r = _retrato([_item("estimado", 0, _OBS_HACHURA)])
    assert r["laranja_com_prova"] == 0


def test_laranja_com_procedencia_de_TEXTO_nao_conta():
    """Regra nº1: texto da prancha é leitura, não medição. Nunca seria branco."""
    for obs in (_OBS_TEXTO, _OBS_CARIMBO, "Fonte: legenda", ""):
        r = _retrato([_item("estimado", 12, obs)])
        assert r["laranja_com_prova"] == 0, (
            "contou %r como candidato a branco — isso infla o teto e faria a "
            "gente dimensionar o conserto errado" % obs)


def test_o_branco_nunca_entra_no_teto():
    """O teto é do que PODERIA virar branco. Quem já é, não é candidato."""
    r = _retrato([_item("confirmado", 10, _OBS_GEOMETRIA)])
    assert r["laranja_com_prova"] == 0 and r["brancos"] == 1


# ══════════════════════════════════════════════════════════════════════════
#  3. BRANCO SEM PROVA — sentinela do guarda vizinho
# ══════════════════════════════════════════════════════════════════════════
def test_branco_sem_prova_e_contado():
    """Depois do `selos_sem_medida` isto deve ser 0. Se subir, é regressão dele."""
    r = _retrato([_item("confirmado", 3, _OBS_CARIMBO)])
    assert r["branco_sem_prova"] == 1


def test_o_QUADRO_DE_ACO_nao_e_acusado():
    """🩸 Erro que eu quase subi, pego relendo o próprio diff.

    A 1ª versão reimplementava aqui a pergunta "este branco tem prova?" com as
    mesmas constantes do `selos_sem_geometria`. Parecia idêntico e não era:
    aquele guarda ABSOLVE o quadro de aço (tabela com colunas rotuladas), de
    propósito, e eu não copiei a absolvição. Pelo comentário do próprio guarda,
    **38 dos 46** confirmados com procedência de texto são aço — ou seja, o
    alarme crítico dispararia falso em todo projeto com ferragem.

    🔑 O conserto foi não reimplementar: `branco_sem_prova` agora É
    `len(selos_sem_geometria(items))`. Não há divergência possível.
    🪤 Este teste é o controle daquele alarme: sem ele, o instrumento voltaria a
    gritar em item são, e alarme sem controle a gente desliga em duas semanas.
    """
    aco = ("Fonte: QUADRO DE AÇO da prancha — coluna COMPR. da tabela de "
           "ferragem, bitola 10.0mm, 24 barras")
    r = _retrato([_item("confirmado", 120, aco)])
    assert r["branco_sem_prova"] == 0, (
        "acusou o quadro de aço, que o `selos_sem_geometria` absolve de "
        "propósito — o alarme crítico vira falso positivo")


def test_branco_sem_prova_usa_o_MESMO_guarda_que_rebaixa():
    """Duas definições de "prova" divergem em semanas. Aqui só existe uma."""
    from engine_rules import selos_sem_geometria as _ssg
    itens = [
        _item("confirmado", 3, _OBS_CARIMBO),
        _item("confirmado", 10, _OBS_GEOMETRIA),
        _item("estimado", 5, _OBS_TEXTO),
    ]
    assert _retrato(itens)["branco_sem_prova"] == len(_ssg(itens)), (
        "o retrato conta uma coisa e o guarda que rebaixa conta outra — com o "
        "mesmo nome. É assim que as duas réguas divergem sem ninguém ver")


def test_branco_COM_prova_nao_e_acusado():
    """🪤 Sentinela que acusa medição de verdade vira ruído, e ruído é desligado."""
    for obs in (_OBS_GEOMETRIA, _OBS_HACHURA,
                "Fonte: CONTAGEM DE BLOCOS — bloco 'PORTA' = 12 un"):
        r = _retrato([_item("confirmado", 12, obs)])
        assert r["branco_sem_prova"] == 0, (
            "acusou %r, que é geometria pura" % obs)


# ══════════════════════════════════════════════════════════════════════════
#  4. O INSTRUMENTO NÃO PODE MEXER EM NADA
# ══════════════════════════════════════════════════════════════════════════
def test_NAO_altera_os_itens():
    """🚫 A linha que separa instrumento de conserto. Se um dia isto falhar,
    alguém transformou o contador em promotor — e a regra nº1 caiu junto."""
    itens = [
        _item("estimado", 48.5, _OBS_HACHURA),
        _item("confirmado", 3, _OBS_CARIMBO),
    ]
    antes = [dict(i) for i in itens]
    _retrato(itens)
    assert itens == antes, (
        "o retrato ALTEROU os itens — ele é instrumento, não conserto. "
        "Promover a partir daqui é o cross-check aposentado voltando")


def _escreve_selo(fonte, nome_func="retrato_do_selo"):
    """A função ATRIBUI selo em algum lugar? Por AST, não por substring.

    🩸 A primeira versão deste julgamento procurava os textos "confidence =",
    "confidence=" e "CONFIRMADO". O controle positivo logo abaixo passou um
    promotor escrito como `it["confidence"] = "confirmado"` e o guarda **não
    viu** — nenhum dos três padrões casa com isso. Substring de novo.
    Ver [[feedback_procurei_a_palavra_nao_o_comportamento]].
    """
    alvo = next((n for n in ast.walk(ast.parse(fonte))
                 if isinstance(n, ast.FunctionDef) and n.name == nome_func), None)
    assert alvo is not None, "não achei %s — o guarda cegou" % nome_func

    def _toca_selo(no):
        # it.confidence = ...
        if isinstance(no, ast.Attribute) and no.attr == "confidence":
            return True
        # it["confidence"] = ...
        if (isinstance(no, ast.Subscript) and isinstance(no.slice, ast.Constant)
                and str(no.slice.value).lower() == "confidence"):
            return True
        return False

    for no in ast.walk(alvo):
        alvos = []
        if isinstance(no, ast.Assign):
            alvos = list(no.targets)
        elif isinstance(no, (ast.AugAssign, ast.AnnAssign)):
            alvos = [no.target]
        for a in alvos:
            for sub in ast.walk(a):
                if _toca_selo(sub):
                    return True
    return False


def test_a_funcao_nao_escreve_confidence_em_lugar_nenhum():
    """🚫 A linha entre instrumento e conserto, conferida na estrutura."""
    src = io.open(os.path.join(_BACKEND, "engine_rules.py"), encoding="utf-8").read()
    assert not _escreve_selo(src), (
        "o instrumento passou a ESCREVER selo — virou conserto, e conserto de "
        "selo precisa ser revisado como tal (regra dura nº1)")


# ══════════════════════════════════════════════════════════════════════════
#  5. O MOTOR CHAMA MESMO?
# ══════════════════════════════════════════════════════════════════════════
def test_o_retrato_e_tirado_no_fluxo_do_job():
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    arvore = ast.parse(src)
    chamadas = [n for n in ast.walk(arvore)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "_retrato"]
    assert chamadas, (
        "ninguém tira o retrato — o instrumento existe e não mede job nenhum")


def test_o_retrato_e_tirado_DEPOIS_do_ultimo_rebaixamento():
    """🪤 A ordem é o que dá sentido ao número.

    `selos_sem_medida` (linha ~12045) é o fim da fila de quem rebaixa selo. Um
    retrato tirado antes dele fotografa um estado que ainda vai mudar — e o
    `branco_sem_prova` viria alto sempre, virando alarme de mentira.
    """
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i_rebaixa = src.index("_sem_medida = _selos_sem_medida(all_items)")
    i_retrato = src.index("_rs = _retrato(all_items)")
    assert i_rebaixa < i_retrato, (
        "o retrato é tirado ANTES do último rebaixamento — ele mediria um "
        "estado que ainda muda, e o alarme de branco-sem-prova seria falso")


def test_o_retrato_e_tirado_ANTES_da_planilha():
    """Tem que retratar o que o cliente vai receber, não outra coisa."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i_retrato = src.index("_rs = _retrato(all_items)")
    i_planilha = src.index("output_path = os.path.join(work_dir, f\"orcamento_")
    assert i_retrato < i_planilha


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLES POSITIVOS
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_a_ordem_invertida_e_reprovada():
    falso = "_rs = _retrato(all_items)\n_sem_medida = _selos_sem_medida(all_items)\n"
    assert falso.index("_sem_medida = _selos_sem_medida(all_items)") > \
           falso.index("_rs = _retrato(all_items)"), "o controle está mal montado"


def test_CONTROLE_um_instrumento_que_PROMOVE_e_reprovado():
    """Três formas de promover, todas pelo MESMO julgamento do teste real.

    🩸 Foi este controle que derrubou a primeira versão do guarda: ele procurava
    substrings e não via `it["confidence"] = "confirmado"`.
    """
    por_chave = '''
def retrato_do_selo(items):
    for it in items:
        it["confidence"] = "confirmado"
    return {}
'''
    por_atributo = '''
def retrato_do_selo(items):
    for it in items:
        it.confidence = "confirmado"
    return {}
'''
    disfarcado = '''
def retrato_do_selo(items):
    for it in items:
        if it.get("quantity"):
            it["confidence"] = _CONF
    return {}
'''
    for nome, corpo in (("por chave", por_chave),
                        ("por atributo", por_atributo),
                        ("disfarçado", disfarcado)):
        assert _escreve_selo(corpo), (
            "o julgamento aprova um promotor escrito %s — não guarda nada" % nome)


def test_CONTROLE_um_instrumento_que_so_LE_e_aprovado():
    """🪤 O outro lado: se o julgamento acusasse leitura, ele reprovaria o
    instrumento correto e eu desligaria o guarda achando que era falso positivo."""
    so_le = '''
def retrato_do_selo(items):
    n = 0
    for it in items:
        selo = it.get("confidence")
        if selo == "confirmado":
            n += 1
    return {"brancos": n}
'''
    assert not _escreve_selo(so_le), (
        "acusou um instrumento que apenas LÊ o selo — alarme sem controle")
