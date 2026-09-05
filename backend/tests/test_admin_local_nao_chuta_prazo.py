# -*- coding: utf-8 -*-
"""O motor chutava o PRAZO DA OBRA em "Administração local".

🩸 04/09/2026. O prompt mandava: "Administração local de obra (un: mês —
quantidade conforme prazo)". A IA obedecia e inventava a duração.

📏 MEDIDO em 156 projetos de cliente concluídos:

    79 itens · unidade "mês" em 76 · quantidade de 0 a 18 · média 3,8
    29 dos 79 (37%) saíram ZERO — "Administração local de obra — 0 meses"

Os outros quatro Serviços Preliminares saem como verba (260 de 346) e têm 7,5%
de zero. Só este chuta tempo. E é o mais EDITADO do grupo: 5 edições para 9
aprovações — o cliente conserta o palpite.

🔑 Prazo de obra não sai de planta, sai de cronograma. Regra dura nº5: publicar
"3 meses" é virar orçamentista por um instante.

🪤 O PROJETO JÁ NÃO CONFIAVA NESSE NÚMERO em outro lugar: o cronograma se recusa
a consumi-lo, e o comentário de lá (caso Eloídes, 03/08) diz por quê — "usar
esse chute aqui seria o cronograma aprendendo com o palpite dele mesmo e
chamando de informação". Só o quantitativo ainda o publicava.

🚫 O QUE ESTE CONSERTO **NÃO** FAZ: remover os Serviços Preliminares. Medido nas
revisões, eles são APROVADOS — 58 aprovações de 9 pessoas contra 11 rejeições de
3, taxa de rejeição de 13,8% contra 11,1% do resto da planilha, e nenhum dos
cinco itens concentra rejeição. Tirá-los iria contra o que o cliente faz com
eles. Sai o número inventado, não a linha.

🪤 Por que uma regra determinística e não só o prompt: o motor NÃO é
determinístico (o mesmo DWG já deu "17,18 ml" e "44,67 m²" em duas rodadas). O
prompt pede; a regra garante.
"""
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from engine_rules import (administracao_local_com_prazo_chutado as _chutou,
                          normalizar_administracao_local as _normaliza)


# ══════════════════════════════════════════════════════════════════════════
#  1. A REGRA — o que ela pega e o que ela deixa em paz
# ══════════════════════════════════════════════════════════════════════════
def test_pega_administracao_local_em_unidade_de_tempo():
    for unidade in ("mês", "mes", "meses", "dia", "dias", "semana", "ano"):
        assert _chutou("Administração local de obra", unidade), (
            "não pegou a unidade de tempo %r — o prazo continua sendo chutado"
            % unidade)


def test_pega_sem_acento_e_com_outra_redacao():
    """A IA não escreve a mesma frase duas vezes — o motor não é determinístico."""
    assert _chutou("Administracao local da obra", "meses")
    assert _chutou("ADMINISTRAÇÃO LOCAL — equipe de obra", "mês")
    assert _chutou("Custos com administração local no canteiro", "mes")


def test_NAO_mexe_em_quem_ja_esta_certo():
    """🪤 Alarme que dispara em item são é ruído, e ruído é desligado."""
    assert not _chutou("Administração local de obra", "vb"), (
        "mexeria num item que já está como verba — trabalho à toa e risco")
    assert _normaliza("Administração local de obra", "vb", "") is None


def test_NAO_mexe_nos_OUTROS_preliminares():
    """Os outros quatro são verba e o cliente aprova. Não é com eles."""
    for desc, un in (("Mobilização e desmobilização de obra", "vb"),
                     ("Limpeza permanente e final de obra", "vb"),
                     ("Proteção de áreas sem intervenção", "vb"),
                     ("Projeto executivo complementar", "vb")):
        assert not _chutou(desc, un)
        assert _normaliza(desc, un, "") is None


def test_NAO_confunde_com_item_de_tempo_legitimo():
    """🪤 Há itens que são cotados em dia de propósito (serventia, caçamba).
    A regra é sobre administração local, não sobre a unidade sozinha."""
    assert not _chutou("Serventia — ajudante geral de obra (seg-sex)", "dia")
    assert not _chutou("Locação de container de obra", "mês")


# ══════════════════════════════════════════════════════════════════════════
#  2. O QUE SAI NO LUGAR
# ══════════════════════════════════════════════════════════════════════════
def test_vira_verba_com_quantidade_UM():
    """🪤 Nunca 0: zero era 37% do defeito. Verba com quantidade 0 não é
    honestidade, é linha quebrada."""
    un, qtd, _ = _normaliza("Administração local de obra", "mês", "")
    assert un == "vb"
    assert qtd == 1.0, "quantidade %r — verba com 0 é o defeito de novo" % qtd


def test_a_observacao_DIZ_que_o_prazo_nao_foi_medido():
    _, _, obs = _normaliza("Administração local de obra", "mês", "")
    assert "não foi medida" in obs or "NÃO foi medida" in obs
    assert "cronograma" in obs, (
        "a observação não diz de ONDE vem o prazo — é a parte acionável")


def test_preserva_a_observacao_que_ja_existia():
    """A observação da IA pode ter informação boa. Acrescenta, não substitui."""
    _, _, obs = _normaliza("Administração local de obra", "mês",
                           "Fonte: carimbo da prancha — prazo contratual citado.")
    assert "carimbo da prancha" in obs


def test_aplicar_DUAS_VEZES_nao_duplica_o_aviso():
    """🪤 O motor refaz a planilha (regra nº7) e pode passar aqui de novo."""
    _, _, obs1 = _normaliza("Administração local de obra", "mês", "")
    assert obs1.count("não sai da planta") == 1
    # Depois da 1ª passada o item já é verba — a regra não se aplica mais, e é
    # ISSO que garante a idempotência: não há segunda escrita pra duplicar.
    assert _normaliza("Administração local de obra", "vb", obs1) is None
    # E mesmo que alguém force a regra com a unidade de tempo de volta, a frase
    # não entra duas vezes.
    _, _, obs2 = _normaliza("Administração local de obra", "mês", obs1)
    assert obs2.count("não sai da planta") == 1, (
        "a frase foi acrescentada de novo — a planilha refeita (regra nº7) "
        "passaria aqui outra vez e o cliente veria o aviso repetido")


# ══════════════════════════════════════════════════════════════════════════
#  3. O MOTOR APLICA MESMO? (guarda de ponto de chamada, executável)
# ══════════════════════════════════════════════════════════════════════════
class _Item(object):
    def __init__(self, description, unit, quantity, observations=""):
        self.description = description
        self.unit = unit
        self.quantity = quantity
        self.observations = observations
        self.discipline = "Serviços Preliminares"


def test_o_motor_normaliza_os_itens():
    import main as _m
    itens = [
        _Item("Administração local de obra", "mês", 3.0),
        _Item("Administração local de obra", "mês", 0.0),
        _Item("Mobilização e desmobilização de obra", "vb", 1.0),
        _Item("Piso cerâmico 60x60", "m²", 48.5),
    ]
    n = _m._aplicar_admin_local(itens)
    assert n == 2, "normalizou %r itens, esperava os 2 de administração local" % n
    assert itens[0].unit == "vb" and itens[0].quantity == 1.0
    assert itens[1].unit == "vb" and itens[1].quantity == 1.0, (
        "o item que saiu ZERO continuou zerado — era 37% do defeito")
    assert "cronograma" in itens[0].observations
    # os que não são o alvo ficam intactos
    assert itens[2].unit == "vb" and itens[2].quantity == 1.0
    assert itens[3].unit == "m²" and itens[3].quantity == 48.5


def test_o_motor_NAO_mexe_em_planilha_sem_o_item():
    import main as _m
    itens = [_Item("Piso cerâmico 60x60", "m²", 48.5)]
    assert _m._aplicar_admin_local(itens) == 0
    assert itens[0].unit == "m²" and itens[0].quantity == 48.5


def test_a_funcao_e_CHAMADA_no_fluxo_do_job():
    """🪤 Função que ninguém chama é código morto que passa em teste.

    Cobertura por AST: procura a chamada dentro do fluxo, não a palavra no
    arquivo. Um guarda meu de 04/09 procurava `ast.Call` por nome e ficava cego
    quando a função era ARGUMENTO — aqui a pergunta é só "alguém chama?".
    """
    import ast
    import io
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    arvore = ast.parse(fonte)
    chamadas = [n for n in ast.walk(arvore)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "_aplicar_admin_local"]
    assert chamadas, (
        "`_aplicar_admin_local` existe mas NINGUÉM a chama — o conserto não "
        "roda em job nenhum")


# ══════════════════════════════════════════════════════════════════════════
#  4. O PROMPT PAROU DE PEDIR O CHUTE
# ══════════════════════════════════════════════════════════════════════════
def test_o_prompt_nao_pede_mais_quantidade_por_prazo():
    """A regra determinística conserta a saída; o prompt evita o trabalho.

    🪤 Guarda de texto — fraco por natureza. Ele existe só pra impedir que a
    instrução volte; quem GARANTE é a regra testada acima.
    """
    import io
    src = io.open(os.path.join(_BACKEND, "analyzer.py"), encoding="utf-8").read()
    i = src.index("Administração local de obra")
    linha = src[i:src.index("\n", i)]
    assert "conforme prazo" not in linha, (
        "o prompt voltou a mandar a IA cotar administração local por prazo: %r"
        % linha)
    assert "vb" in linha, (
        "o prompt não diz mais qual unidade usar: %r" % linha)


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — a instrução de ANTES, no MESMO julgamento
# ══════════════════════════════════════════════════════════════════════════
_LINHA_ANTES = "- Administração local de obra (un: mês — quantidade conforme prazo)"


def test_CONTROLE_a_instrucao_de_ANTES_e_reprovada():
    assert "conforme prazo" in _LINHA_ANTES and "vb" not in _LINHA_ANTES, (
        "o critério aprova a instrução que causou o defeito — não julga nada")


def test_CONTROLE_o_item_de_ANTES_seria_pego_pela_regra():
    """O item como saía antes: mês + 3. A regra tem que ver isso."""
    assert _chutou("Administração local de obra", "mês")
    un, qtd, _ = _normaliza("Administração local de obra", "mês", "")
    assert (un, qtd) != ("mês", 3.0), "o controle está mal montado"
