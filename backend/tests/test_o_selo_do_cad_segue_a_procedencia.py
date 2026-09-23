# -*- coding: utf-8 -*-
"""O selo do CAD segue a PROCEDÊNCIA DO INSUMO, não a ausência de conta.

🩸 22/09/2026 — job `64fa324b` (cliente novo, 1 DWG de estrutura, pé-direito
3,20 m informado por ele). O motor mediu: 3.716 m de parede em 20 camadas,
207,84 m² em 3 camadas, 27 itens extraídos. A planilha saiu com 24 linhas COM
número — e **nenhuma marcada como medida**. As contas estavam escritas na
observação de cada linha:

    "16 pilares × perímetro 2×(0,18+0,40) m × 3,20 m = 59,39 m²"
    "Área total hachurada (SOLID) no layer 0 = 194,08 m² (7 hachuras)"

🔑 A CAUSA ESTAVA NO NOSSO PRÓPRIO PROMPT: "Se você multiplicou, somou ou fez
qualquer cálculo além de copiar o valor, NÃO é confirmado." Essa frase proíbe
exatamente o que medir significa — ninguém orça copiando número pronto de
dentro do arquivo; orça multiplicando comprimento por altura, contagem por
seção, área por espessura. E três parágrafos abaixo a "REGRA DE OURO" mandava
"na dúvida, estimado", anulando o "não seja tímido" que vinha depois.

📊 Medido no acervo (60 dias, 69 jobs com CAD): **15 entregaram ZERO linha
medida** e 43 (62%) entregaram menos de 1 em 4. Decisão do Pedro em 21/09:
"se está medido, tem que marcar como medido — independente se é PDF ou CAD".

🚨 Estes guardas MONTAM O PROMPT DE VERDADE (exec do bloco `dxf_prompt` com as
variáveis dubladas) e leem o texto que o modelo recebe — não o fonte em volta.

🧪 Controles positivos: o prompt CONTINUA rebaixando insumo adotado por conta
própria, e CONTINUA proibindo o selo em layer de anotação. Sem eles, apagar o
bloco inteiro passaria verde.
"""
import os
import sys
import textwrap

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)
sys.path.insert(0, os.path.dirname(_AQUI))

from _corpo import fonte  # noqa: E402

_ABRE = 'dxf_prompt = f"""Analise os dados extraídos de um arquivo DXF'


def _prompt_do_cad(proj_kind="estrutura"):
    """O prompt do CAD como o modelo o recebe, montado de verdade.

    🪤 `bloco_desde` corta pela indentação e a f-string tem linhas na coluna
    zero — ele para na primeira. O fim aqui são as aspas triplas que fecham.
    """
    src = fonte("main.py")
    i = src.find(_ABRE)
    assert i >= 0, "não achei a montagem do prompt do CAD em main.py"
    j = src.find('"""', i + len(_ABRE)) + 3
    ns = {"_proj_kind": proj_kind, "_estrutura_directive": "",
          "_pd_directive": "PÉ-DIREITO informado pelo cliente: 3,20 m",
          "structured_text": "COMPRIMENTOS POR LAYER: FO-Vigas 1041,24 m"}
    exec(compile(textwrap.dedent(src[i:j]), "<dxf_prompt>", "exec"), ns)
    return ns["dxf_prompt"]


@pytest.fixture(scope="module")
def prompt():
    return _prompt_do_cad()


# ── o defeito de 22/09 ─────────────────────────────────────────────────────
#: as formas de dizer "houve conta, logo não é medido". Qualquer uma delas
#: devolve o cliente pra planilha 100% laranja do job 64fa324b.
PROIBICOES_DA_CONTA = [
    "além de copiar o valor",
    "fez qualquer cálculo além de copiar",
    "não conseguiu ler DIRETO dos dados extraídos",
]


def test_o_prompt_do_CAD_nao_desqualifica_o_selo_por_haver_CONTA(prompt):
    achadas = [p for p in PROIBICOES_DA_CONTA if p in prompt]
    assert achadas == [], (
        "o prompt voltou a tratar a conta como motivo pra não selar: %r. "
        "Medir É fazer conta — comprimento × pé-direito, contagem × seção, "
        "área × espessura. Foi essa frase que entregou 24 linhas com número e "
        "0 medidas no job 64fa324b." % achadas)


def test_o_prompt_do_CAD_decide_pela_PROCEDENCIA_de_cada_insumo(prompt):
    assert "DE ONDE VEM CADA INSUMO" in prompt, (
        "o prompt precisa dizer que o selo se decide pela procedência do "
        "insumo, não pela presença de multiplicação")
    assert "MEDIR É FAZER CONTA" in prompt


@pytest.mark.parametrize("insumo, porque", [
    ("PREMISSAS", "pé-direito e área construída que o CLIENTE informou são "
                  "dado medido — foi ele quem mediu"),
    ("no nome do bloco", "a seção escrita no desenho é medida; sem ela toda "
                         "fôrma de pilar volta a ser estimada"),
    ("CONTAGEM DE BLOCOS", "contagem literal continua valendo"),
    ("ÁREAS HACHURADAS POR LAYER", "área de hachura continua valendo"),
])
def test_a_lista_de_insumos_MEDIDOS_cobre_o_que_o_caso_real_usou(
        prompt, insumo, porque):
    assert insumo in prompt, porque


# ── controles positivos: o conserto não pode virar carta branca ────────────
def test_CONTROLE_insumo_ADOTADO_pelo_modelo_continua_rebaixando(prompt):
    """A fôrma de viga do mesmo job adotou "seção predominante 14×40" com
    outras quatro seções no desenho — essa TEM que continuar laranja."""
    assert "ADOTADO POR VOCÊ" in prompt, (
        "sem esta metade o conserto vira carta branca: qualquer conta com "
        "espessura de praxe sairia branca")
    assert "espessura de praxe" in prompt


def test_CONTROLE_layer_de_ANOTACAO_continua_sem_direito_a_selo(prompt):
    """A rede de 24/08 (61 itens em 19 projetos selados a partir de texto de
    prancha) mora aqui e não pode ter caído junto."""
    assert "NUNCA marque \"confirmado\"" in prompt
    assert "O LAYER TEM QUE SER DE OBRA" in prompt


def test_CONTROLE_a_regra_de_ouro_ainda_manda_rebaixar_numero_sem_origem(prompt):
    """"Na dúvida, estimado" continua — o que mudou é SOBRE O QUE é a dúvida."""
    assert "A DÚVIDA QUE IMPORTA É SOBRE O INSUMO" in prompt
    assert "não sabe de onde saiu um dos números" in prompt
