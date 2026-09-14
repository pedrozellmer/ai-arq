# -*- coding: utf-8 -*-
"""Número lido numa grandeza não pode sair carimbado em outra.

🩸 14/09/2026 — MEDIDO na base, classificando com a régua do próprio motor
(`grandeza_da_unidade`): o motor reescreveu a unidade de **550 linhas mudando a
GRANDEZA FÍSICA**, e **235 delas saíram COM número** — o mesmo valor, agora
medindo outra coisa:

  · 1.200 m de cabo 3×2,5mm²       → "1.200 **un**"   (fornecedor cota rolo)
  · 1.634 m² de rede de sprinkler  → "1.634 **un**"
  · 1.505 m de PERÍMETRO de parede → "1.505 **m²**" de revestimento
  · 1.999 kg de aço CA-50          → "1.999 **un**"

🔑 Isto é PIOR que linha vazia: vazia o cliente preenche, com número ele ORÇA.
O motor já chamava o efeito pelo nome desde 09/08, numa observação do próprio
código: *"~6.971 m² fabricados"*.

🪤 A reescrita da unidade CONTINUA — piso se orça em m², não em ml, e isso está
certo. O que não pode é o número atravessar a troca.

🪤 RECEITA REPETIDA: a normalização acontece em DOIS pontos do `main.py`, e as
duas cópias já tinham divergido (uma escrevia "(revisar quantidade)", a outra
não). Por isso a régua é única e o guarda mira na DIVERGÊNCIA — o teste do fim
reprova se qualquer um dos pontos deixar de chamar.
"""
import ast
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine_rules import quantidade_apos_troca_de_unidade as _troca  # noqa: E402

_MAIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "main.py")


# ── as linhas que saíram ERRADAS em produção ─────────────────────────────
def test_os_quatro_casos_reais_perdem_o_numero():
    for qtd, de, para in ((1200, "ml", "un"), (1634, "m²", "un"),
                          (1505.20, "ml", "m²"), (1999, "kg", "un")):
        nova, nota = _troca(qtd, de, para)
        assert nova == 0, (
            "o número de %s %s atravessou a troca para %s e virou %r"
            % (qtd, de, para, nova))
        assert nota, "zerou sem dizer por quê — o cliente perde o levantamento"


def test_a_nota_preserva_o_numero_lido_e_a_unidade_original():
    """Zerar sem registrar seria perder o levantamento — e a omissão é o que
    mais custa ao cliente hoje (91% do trabalho de revisão dele é preencher
    linha zerada). O número tem que continuar legível na observação."""
    _, nota = _troca(1200, "ml", "un")
    assert "1200" in nota, ("a nota não traz o número lido: %s" % nota)
    assert "ml" in nota, ("a nota não diz a unidade original: %s" % nota)
    assert "un" in nota, ("a nota não diz a unidade nova: %s" % nota)


def test_a_nota_cabe_no_corte_da_tela():
    """🪤 `revisao.html` mostra 110 caracteres e o resto vai num hover que não
    existe no celular. O essencial tem que estar antes do corte."""
    _, nota = _troca(1200, "ml", "un")
    assert "branco" in nota[:110].lower(), (
        "quem lê só o começo não entende por que a célula está vazia: %r"
        % nota[:110])


def test_decimal_nao_vira_dizima():
    _, nota = _troca(1505.201234, "ml", "m²")
    assert "1505.20" in nota, nota
    assert "1505.2012" not in nota, ("número cru na cara do cliente: %s" % nota)


# ── controles: quando o número TEM que passar ────────────────────────────
def test_CONTROLE_troca_so_de_rotulo_preserva_o_numero():
    """138 linhas na base são `cj`→`un`, `m`→`ml`, `kg`→`kg`: mesma grandeza,
    o número continua valendo. Zerar aqui seria destruir medição boa."""
    for qtd, de, para in ((83, "cj", "un"), (8, "ml", "m"), (8, "kg", "kg"),
                          (12, "m", "metro"), (4, "pç", "un")):
        nova, nota = _troca(qtd, de, para)
        assert nova == qtd, (
            "troca de rótulo %s→%s destruiu o número %s" % (de, para, qtd))
        assert nota == ""


def test_CONTROLE_unidade_incomparavel_passa_intacta():
    """`vb`, `%`, `mês` são coringas nossos e mão de obra do SINAPI — não
    descrevem dimensão nenhuma. Na dúvida, cala a boca."""
    for de, para in (("vb", "un"), ("un", "vb"), ("%", "un"), ("mês", "un")):
        nova, nota = _troca(10, de, para)
        assert nova == 10, ("%s→%s mexeu num caso incomparável" % (de, para))
        assert nota == ""


def test_CONTROLE_zero_e_lixo_nao_geram_ruido():
    assert _troca(0, "ml", "un") == (0, "")
    assert _troca(None, "ml", "un")[1] == ""
    assert _troca("abc", "ml", "un")[1] == ""
    assert _troca(-5, "ml", "un")[1] == ""


def test_CONTROLE_mesma_unidade_nao_e_troca():
    nova, nota = _troca(42, "m²", "m²")
    assert (nova, nota) == (42, "")


# ── a DIVERGÊNCIA entre as duas cópias (a doença) ───────────────────────
def _blocos_de_unidade_corrigida():
    arv = ast.parse(io.open(_MAIN, encoding="utf-8").read())
    return [n for n in ast.walk(arv)
            if isinstance(n, ast.If) and isinstance(n.test, ast.Name)
            and n.test.id == "unit_corrected"]


def test_TODO_ponto_que_reescreve_a_unidade_chama_a_regua():
    """🪤 Este é o caso que importa. A normalização é feita em mais de um lugar
    e as cópias JÁ tinham divergido no texto antes de divergirem na regra. Um
    guarda que só testasse a função deixaria passar um segundo ponto sem trava.

    Ancorado no FATO (o bloco `if unit_corrected:` importa a régua), não no
    alias nem na distância em linhas.
    """
    blocos = _blocos_de_unidade_corrigida()
    assert len(blocos) >= 2, (
        "esperava pelo menos os 2 pontos de normalização de unidade; achei %d "
        "— se a normalização mudou de forma, este guarda precisa ser refeito"
        % len(blocos))

    sem_regua = []
    for b in blocos:
        importa = any(
            isinstance(d, ast.ImportFrom) and d.module == "engine_rules"
            and any(a.name == "quantidade_apos_troca_de_unidade" for a in d.names)
            for d in ast.walk(b))
        if not importa:
            sem_regua.append(b.lineno)
    assert not sem_regua, (
        "ponto(s) que reescrevem a unidade SEM passar o número pela régua, na(s) "
        "linha(s) %r — é a cópia divergente que produz o defeito de novo"
        % sem_regua)


def test_cada_ponto_REATRIBUI_a_quantidade():
    """Chamar a régua e jogar o resultado fora deixaria a bancada verde com o
    defeito aberto — foi assim que metade dos guardas desta base ficou cega."""
    sem_atribuir = []
    for b in _blocos_de_unidade_corrigida():
        reatribui = any(
            isinstance(d, ast.Assign)
            and any(isinstance(t, ast.Tuple) and any(
                isinstance(e, ast.Name) and e.id == "qty" for e in t.elts)
                for t in d.targets)
            for d in ast.walk(b))
        if not reatribui:
            sem_atribuir.append(b.lineno)
    assert not sem_atribuir, (
        "a régua é chamada mas a quantidade não é reatribuída na(s) linha(s) %r "
        "— o número errado continua indo pra planilha" % sem_atribuir)
