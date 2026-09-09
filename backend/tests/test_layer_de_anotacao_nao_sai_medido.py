# -*- coding: utf-8 -*-
"""Layer de anotação não é obra — e não pode sair com selo de MEDIDO.

🩸 09/09/2026, projeto de pórtico (job 43c52488). Das 14 linhas com selo BRANCO
("✓ MEDIDO do CAD"), **dez** eram assim:

    "Acabamento/textura — linear layer ARQ_TEX-3"   109,40 ml   ✓ MEDIDO
    "Contorno/representação de cobertura — layer ARQ_COB"  13,43 ml  ✓ MEDIDO

Ninguém precifica isso — e quem lê a planilha é um **orçamentista humano**
(regra dura nº5). O número é honesto (o comprimento foi somado do desenho), mas
o item não tem identidade.

📏 E o número que alimenta isso vem sujo: no arquivo A, `ARQ_TEX-4` respondia
por **3.782 m dos 4.258 m** somados como "layer de parede" (88,8%) — a alvenaria
de verdade (`ARQ_ALV`) somava 119 m. No arquivo B o topo era `ARQ_TXT-2`.
O próprio job tem itens cuja fonte declarada é *"texto no layer ARQ_TXT-1"*.

🔑 O CONSERTO NÃO É APAGAR A LINHA. Citar o layer no item é comportamento
DELIBERADO em outro caminho (infra linear, `main.py` ~10063: *"marcando estimado
e citando o layer e o valor na observação"*, porque *"deixar quantity=0 com um
layer de condutos MEDIDO na lista é jogar medição fora"*). O que não pode
existir é o **par**: nome de layer na descrição COM selo confirmado.

💰 Isto encosta no dinheiro: a régua de cobrança conta selos confirmados. O job
saiu carimbado como cobrável apoiado em 10 nomes de layer.

📏 Medido ANTES de ligar, no acervo inteiro e com o vocabulário FINAL:
**60 de 2.121 itens confirmados (2,8%)**, em 29 de 118 projetos — e **ZERO
projeto perde a cobrabilidade**, porque todos têm outra linha medida de
verdade. 🪤 A 1ª medição dizia 41 em 21; depois eu alarguei o vocabulário
(prefixo TEXT) e **remedi**. Número medido antes de mexer na régua não vale
pra régua depois — é estimativa com cara de medição, regra dura nº1.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from engine_rules import layer_is_anotacao, layer_is_carimbo  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
#  🔑 A régua: o que É anotação
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("layer", [
    "ARQ_TEX-4", "ARQ_TXT-2", "ARQ_TXT", "ARQ_TEX-1",   # os do caso real
    "A-ANNO-DIMS", "ARQ-COTA", "LEGENDA", "ARQ_TITULO",
    "ARQ-HACHURA", "TEXTO", "arq_txt", "ARQ_DETL-2", "ARQ-CHAMADA",
])
def test_layer_de_ANOTACAO_e_reconhecido(layer):
    assert layer_is_anotacao(layer) is True, layer


@pytest.mark.parametrize("layer", [
    "ARQ_ALV", "ARQ_ALV-4", "ARQ_COB-3", "A-ROOF", "ARQ_PIS-1",
    "ARQ_EST-1", "ARQ_FOR-2", "PAREDE", "ALVENARIA",
])
def test_CONTROLE_layer_de_OBRA_nao_e_confundido(layer):
    """🧪 O outro lado. Uma régua que dissesse "sim" pra tudo passaria em todos
    os testes acima e rebaixaria a planilha inteira."""
    assert layer_is_anotacao(layer) is False, layer


@pytest.mark.parametrize("layer", [
    "JARDIM", "JARDINEIRA",          # contêm "dim" no MEIO
    "CONTEXTO", "PORTEXO",           # contêm "tex" no MEIO
    "ESTRUTURA", "TESOURAS", "ARMARIO",   # nomes reais do acervo
])
def test_CONTROLE_a_regua_compara_TOKEN_nao_pedaco_de_palavra(layer):
    """🪤 A trava que `layer_is_carimbo` já tinha e que eu precisei repetir:
    comparar por SUBSTRING transformaria 'JARDIM' em cota e 'CONTEXTO' em
    texto. Guarda que rebaixa demais acaba desligado."""
    assert layer_is_anotacao(layer) is False, layer


def test_TEXTURA_e_pego_de_proposito_e_esta_documentado():
    """🪤 O prefixo `TEXT` pega `TEXTURA` junto, e isso é ESCOLHA, não descuido.

    🩸 Meu primeiro conjunto era de tokens EXATOS e ficou mais estreito que a
    régua de substring que já existia num guarda vizinho — `TEXTOS`,
    `TEXTO_TABELAS` e `ELE-TEXTOS` (nomes REAIS do nosso banco) escapavam. A
    bancada completa pegou; a mutação isolada não pegaria, porque o defeito era
    "meu conserto é mais estreito que o que já havia", não "meu conserto está
    errado".

    📏 Conferido no acervo: NENHUM layer com "TEXTURA" tem item confirmado
    hoje. E se aparecer, textura é decoração de desenho — o COMPRIMENTO dela
    também não é serviço. O custo do falso positivo é um selo branco a menos; o
    do falso negativo é quantidade inventada com cara de medição.
    """
    assert layer_is_anotacao("ARQ-TEXTURA-PISO-CERAMICO") is True
    assert layer_is_anotacao("TEXTOS") is True
    assert layer_is_anotacao("TEXTO_TABELAS") is True
    assert layer_is_anotacao("ELE-TEXTOS") is True


def test_a_regua_nova_NAO_atropela_a_do_carimbo():
    """🔑 São duas perguntas diferentes: 'é mobília da prancha' (selo, moldura,
    logotipo) e 'é anotação' (texto, cota, legenda). Um layer de carimbo pode
    ser as duas; um de texto não é carimbo."""
    assert layer_is_carimbo("CARIMBO") and layer_is_anotacao("CARIMBO")
    assert layer_is_anotacao("ARQ_TXT") and not layer_is_carimbo("ARQ_TXT")
    assert layer_is_carimbo("LOGO") and not layer_is_anotacao("LOGO")


@pytest.mark.parametrize("vazio", [None, "", "   "])
def test_vazio_nao_e_anotacao(vazio):
    """🔒 Isto roda no caminho do cliente: dizer "sim" pra vazio rebaixaria
    todo item sem layer citado."""
    assert layer_is_anotacao(vazio) is False


# ══════════════════════════════════════════════════════════════════════════
#  🔑 O CALL SITE: o motor tem que CHAMAR a régua onde o selo é decidido
# ══════════════════════════════════════════════════════════════════════════
def test_o_motor_CHAMA_a_regua_onde_decide_o_selo():
    """🪤 Ancorado na AST. A régua existir e não ser chamada foi exatamente o
    estado anterior: o vocabulário de anotação vivia numa tupla local do
    `main.py` e servia só pra evitar um alarme falso de sobreposição de m² —
    conhecimento parado enquanto anotação virava quantidade com selo branco no
    caminho ao lado."""
    import ast
    import io
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    chamadas = [n.lineno for n in ast.walk(ast.parse(fonte))
                if isinstance(n, ast.Call)
                and (getattr(n.func, "id", None) or getattr(n.func, "attr", None))
                in ("_layer_is_anotacao", "layer_is_anotacao")]
    assert len(chamadas) >= 2, (
        "o motor chama a régua de anotação em %d lugar(es). São dois: o "
        "rebaixamento do selo e o dedup de m². Menos que isso significa que "
        "alguém desligou um deles." % len(chamadas))


def test_o_rebaixamento_NAO_apaga_o_item_nem_a_quantidade():
    """🔑 A linha continua na planilha, com o número e com o motivo. Apagar
    seria jogar fora medição real e deixar o cliente sem saber que existia.

    🪤 Ancorado no texto do aviso porque é ELE que o cliente lê — e ele tem que
    dizer as duas coisas: que foi medido, e que foi medido do desenho da
    anotação."""
    import ast
    import io
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()

    # 🪤 O ramo é achado pela CHAMADA da régua, e o que se exige dele são
    # ATRIBUIÇÕES de verdade. A 1ª versão deste teste procurava a palavra
    # "obs_raw" num trecho de texto — e a mutação passou batida, porque o nome
    # continua aparecendo no `+ obs_raw` do fim da concatenação. Sexta vez no
    # dia que prosa citando código engana um guarda meu.
    ramos = []
    for n in ast.walk(ast.parse(fonte)):
        if not isinstance(n, ast.If):
            continue
        chama = [c for c in ast.walk(n.test) if isinstance(c, ast.Call)
                 and (getattr(c.func, "id", None) or getattr(c.func, "attr", None))
                 in ("_layer_is_anotacao", "layer_is_anotacao")]
        if chama:
            ramos.append(n)
    assert ramos, "não achei o ramo que decide o selo pela régua de anotação"

    # 🪤 São DOIS call sites com propósitos diferentes: um decide o SELO, o
    # outro (dedup de m²) só pula o item. Exigir selo dos dois reprovava o
    # inocente — e guarda que acusa inocente acaba desligado. Exijo que EXISTA
    # o ramo do selo, não que todos sejam ele.
    def _atribuidos(ramo):
        return {getattr(t, "id", None)
                for x in ast.walk(ast.Module(body=ramo.body, type_ignores=[]))
                if isinstance(x, ast.Assign) for t in x.targets}

    def _rebaixa_de_verdade(ramo):
        """🪤 Não basta ATRIBUIR `conf` — tem que atribuir "estimado".
        A mutação `conf = conf` sobreviveu ao guarda que só olhava o alvo:
        alvo certo, valor inócuo, defeito aberto e bancada verde."""
        for x in ast.walk(ast.Module(body=ramo.body, type_ignores=[])):
            if not isinstance(x, ast.Assign):
                continue
            if not any(getattr(t, "id", None) == "conf" for t in x.targets):
                continue
            if isinstance(x.value, ast.Constant) and x.value.value == "estimado":
                return True
        return False

    do_selo = [r for r in ramos if _rebaixa_de_verdade(r)]
    assert do_selo, (
        "nenhum ramo que consulta a régua de anotação rebaixa o selo — a régua "
        "voltou a ser conhecimento parado (linhas: %s)"
        % [r.lineno for r in ramos])

    for ramo in do_selo:
        assert "obs_raw" in _atribuidos(ramo), (
            "o ramo de anotação (linha %d) rebaixa mas não escreve o motivo na "
            "observação — rebaixar em silêncio deixa o cliente sem saber o que "
            "conferir" % ramo.lineno)
        texto = " ".join(
            x.value for x in ast.walk(ast.Module(body=ramo.body, type_ignores=[]))
            if isinstance(x, ast.Constant) and isinstance(x.value, str))
        for palavra in ("medido", "Confirme", "ANOTAÇÃO"):
            assert palavra in texto, (
                "o aviso não diz %r — o cliente precisa saber que o número "
                "existe e que ele tem que conferir o serviço" % palavra)
