# -*- coding: utf-8 -*-
"""Selo zero NÃO prova que o número veio de texto — eram dois fatos, cinco vozes.

🩸 03/09/2026, job `b5ce23ff` do EDVALDO (maior lead B2B, avaliando o produto).
Ele leu, na tela e na planilha:

    "nenhuma quantidade foi medida da geometria — o que saiu na planilha veio
     de texto lido das pranchas"

A planilha dele tinha 90,86 m² de laje vindos de **hachura do layer LAJE** e
169,83 m de viga vindos do **comprimento das linhas do layer VIGA**. Ou seja:
dissemos a um coordenador de estrutura que a planilha dele era transcrição de
legenda, e ele descarta o número certo achando que é texto copiado.

🔑 A DOENÇA: o motor contava `confidence == 'confirmado'`, achava zero, e daí
afirmava ORIGEM. São dois fatos diferentes:
  • SELO zero = ninguém passou na conferência que libera o branco;
  • ORIGEM    = de onde a quantidade saiu.
Afirmar procedência sem olhar a procedência é a regra dura nº1 pelo avesso: lá
é "não diga MEDIDO sem medir"; aqui é "não diga que NÃO mediu sem olhar".

🪤 Eram CINCO lugares dizendo isso, achados por revisão adversarial: o aviso do
plano B (escrito DUAS vezes), a linha da escala, o e-mail do complemento, o
diagnóstico de leitura de todo e-mail de planilha pronta, e o e-mail "não
consegui medir esse arquivo". Consertar quatro deixaria o cliente lendo o
quinto — por isso a frase mora num lugar só.
"""
import io
import os

import main
from engine_rules import quantidades_da_geometria
from _corpo import corpo_de

_FONTE = io.open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()


class _It:
    def __init__(self, quantity=0, observations="", confidence="estimado"):
        self.quantity = quantity
        self.observations = observations
        self.confidence = confidence


# As 9 observações REAIS do job b5ce23ff, copiadas do banco.
_EDVALDO = [
    _It(0, "Especificação lida diretamente do texto 'CONCRETO Fck=30MPa' no layer"),
    _It(90.86, "Fonte: área hachurada do layer 'LAJE' = 90.86 m² (10 hachuras)"),
    _It(0, "Área de projeção horizontal = 90.86 m² (layer 'LAJE'). Espessuras lidas"),
    _It(169.83, "Fonte: comprimento total de linhas do layer 'VIGA' = 339.66 m"),
    _It(0, "Área de fôrma de viga não calculada: altura de viga não medida no CAD"),
    _It(0, "Área de fôrma de pilar não calculada: altura de pavimento não lida"),
    _It(0, "Escada identificada no layer S-STRS: comprimento total de linhas = 61."),
    _It(1.57, "Área de fôrma de escada não calculada a partir dos dados disponíveis."),
    _It(0, "NÃO há quadro/resumo de aço com pesos por bitola"),
]


def test_o_caso_do_edvaldo_conta_DUAS_quantidades_da_geometria():
    """As duas que existem: a hachura da laje e o comprimento do layer da viga."""
    assert quantidades_da_geometria(_EDVALDO) == 2


def test_CONTROLE_procedencia_de_TEXTO_nao_conta():
    """Sem isto a função poderia contar tudo e o teste acima passaria igual."""
    so_texto = [
        _It(264.54, "Fonte: texto layer 'ARQ-TEXTO 1': 'AREA TOTAL = 264,54 m2'"),
        _It(12, "Conforme legenda da prancha, quadro de esquadrias"),
        _It(8, "Lido do carimbo da prancha"),
    ]
    assert quantidades_da_geometria(so_texto) == 0


def test_CONTROLE_linha_ZERADA_que_cita_hachura_nao_conta():
    """Observação que CITA geometria numa linha sem quantidade não é medição.

    É o item "Escada — Fôrma" do próprio Edvaldo: a observação fala em área
    hachurada e, na frase seguinte, diz "NÃO calculada". Contar isso seria
    inventar procedência na direção oposta — o mesmo vício, de costas.
    """
    assert quantidades_da_geometria([
        _It(0, "Fonte: área hachurada do layer 'LAJE' = 90.86 m²")]) == 0


def test_CONTROLE_lista_vazia_e_lixo_nao_estouram():
    assert quantidades_da_geometria([]) == 0
    assert quantidades_da_geometria(None) == 0
    assert quantidades_da_geometria([object()]) in (0, -1)


def test_a_frase_da_origem_muda_conforme_a_origem():
    n_geo, frase = main._origem_das_quantidades(_EDVALDO)
    assert n_geo == 2
    assert "tirada da geometria do desenho" in frase
    # 🩸 03/09, revisão adversarial: este assert exigia que a frase também
    # dissesse "o resto veio de texto lido das pranchas" — e a função NÃO OLHA
    # o resto. Ela conta só quem veio da geometria. "O resto" inclui linha
    # zerada (31% dos itens), chute do modelo, item de catálogo e a linha
    # "informado por você". O teste estava CODIFICANDO o exagero: a função
    # criada pra parar de afirmar procedência sem olhar afirmava procedência
    # sem olhar, e o guarda cobrava que continuasse.
    # 🔑 Calar sobre o que não foi medido é o conserto — e é o que se cobra.
    assert "o resto veio de texto" not in frase, (
        "a frase voltou a afirmar a procedência do RESTO da planilha, que esta "
        "função nunca olhou")


def test_CONTROLE_a_frase_do_caso_SEM_geometria_continua_afirmando_texto():
    """Quando a contagem é ZERO, aí sim a afirmação é sustentada.

    Sem este controle, "não afirmar procedência" viraria "nunca dizer nada" — e
    o cliente perde a informação que o impede de tratar legenda como
    levantamento.
    """
    so_texto = [_It(264.54, "Fonte: texto layer 'X': 'AREA = 264,54 m2'")]
    n_geo, frase = main._origem_das_quantidades(so_texto)
    assert n_geo == 0
    assert "veio de texto lido das pranchas" in frase


def test_CONTROLE_quando_a_origem_E_texto_a_frase_diz_isso():
    """Sem este controle, o conserto poderia ser 'apagar a frase' — e aí o
    cliente perde a informação que evita tratar legenda como levantamento."""
    so_texto = [_It(264.54, "Fonte: texto layer 'X': 'AREA = 264,54 m2'")]
    n_geo, frase = main._origem_das_quantidades(so_texto)
    assert n_geo == 0
    assert frase == "O que saiu na planilha veio de texto lido das pranchas."


def test_a_frase_mora_num_lugar_so():
    """Cinco cópias divergindo foi como isso durou.

    A frase de procedência só pode ser escrita dentro de
    `_origem_das_quantidades`. Qualquer outro ponto do main.py que a escreva é
    uma sexta voz esperando pra divergir.
    """
    # 🪤 O guarda tem que ignorar a DOCUMENTAÇÃO: o comentário e a docstring da
    # própria função CITAM a frase pra explicar por que ela mora ali. A 1ª
    # versão deste teste acusou a docstring de `_origem_das_quantidades` — a
    # armadilha de [[feedback_guarda_que_le_fonte]] acontecendo DENTRO do teste
    # escrito pra impedir esse mesmo tipo de erro.
    dentro = corpo_de("_origem_das_quantidades")
    fora = _FONTE.replace(dentro, "")
    linhas = [l for l in fora.splitlines()
              if "texto lido das pranchas" in l
              and not l.strip().startswith("#")]
    assert not linhas, (
        "a frase de procedência é escrita FORA de `_origem_das_quantidades` — "
        "é uma sexta voz esperando pra divergir:" + chr(10) + "  "
        + (chr(10) + "  ").join(l.strip()[:90] for l in linhas))
    assert dentro.count("texto lido das pranchas") >= 1, (
        "a frase sumiu de dentro da função que deveria ser dona dela")


def test_nenhum_site_decide_procedencia_so_pelo_selo():
    """O padrão que causou tudo: contar 'confirmado' e afirmar origem.

    Cada um dos cinco sites agora consulta `_origem_das_quantidades`. Este
    teste trava a contagem: se alguém acrescentar um site novo sem consultar,
    a frase volta a ter dono errado.
    """
    assert _FONTE.count("_origem_das_quantidades(") >= 6, (
        "algum dos cinco lugares parou de consultar a origem real "
        "(1 definição + 5 usos, no mínimo)")


def test_o_email_nao_inventa_mais_a_CAUSA_de_nao_ter_medido():
    """🪤 Além da origem falsa, o e-mail dava um MOTIVO que ninguém mediu.

    Dizia "(comum quando os elementos foram desenhados como linhas soltas, não
    como blocos)". O motor nunca olhou se os elementos são blocos ou linhas —
    e o cliente ia mexer no desenho por causa disso.
    """
    # Sem comentário: o comentário que ficou no lugar CITA a frase proibida
    # pra explicar por que ela saiu. Acusar isso é acusar a própria lápide.
    codigo = chr(10).join(l for l in _FONTE.splitlines()
                          if not l.strip().startswith("#"))
    assert "desenhados como linhas soltas" not in codigo, (
        "voltou a explicar ao cliente uma causa que o motor não mediu")
