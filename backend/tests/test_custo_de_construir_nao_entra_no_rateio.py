# -*- coding: utf-8 -*-
"""O que custa CONSTRUIR o produto não pode virar custo DE UM PROJETO.

Decisão do Pedro, 06/09/2026: o Claude Code aparece na tela do Financeiro (ele
quer ver o gasto), mas fica FORA do rateio por projeto. O motivo é que o
"custo por projeto" existe pra uma coisa só — decidir preço — e pra isso ele
precisa ser o custo MARGINAL: o que cada projeto novo realmente consome.
Construir o produto é custo fixo do negócio; se entrar na divisão, o número
sobe entre US$20 e US$200/mês e ainda encolhe sozinho quando o volume crescer,
que é exatamente quando ele mais vai ser usado pra decidir.

🪤 `renderCostTotals` somava TODAS as linhas sem olhar categoria
(`COSTS.reduce(...)`), então bastava cadastrar a linha pra ela entrar na
divisão em silêncio. Este guarda existe pra essa porta não reabrir.
"""
import io
import os
import re

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ADMIN = os.path.join(_RAIZ, "projeto_arq", "admin.html")
if not os.path.isfile(_ADMIN):                      # rodando de dentro do repo
    _ADMIN = os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "admin.html")


def _fonte():
    return io.open(_ADMIN, encoding="utf-8").read()


def _linha_do_fixo(src):
    """A linha que calcula o fixo mensal — a mesma que alimenta o custo/projeto."""
    m = re.search(r"^\s*const fixoMensal\s*=.*$", src, re.M)
    assert m, "não achei o cálculo de `fixoMensal` em admin.html"
    return m.group(0)


def test_o_fixo_rateado_por_projeto_EXCLUI_o_custo_de_construir():
    linha = _linha_do_fixo(_fonte())
    assert "costEntraNoRateio" in linha, (
        "o `fixoMensal` voltou a somar TODAS as linhas: %s\n"
        "Com isso o Claude Code (categoria 'desenvolvimento') entra na divisão "
        "por projeto e o custo marginal deixa de servir pra decidir preço."
        % linha.strip())


def test_o_custo_por_projeto_sai_do_fixo_ja_filtrado():
    """O elo seguinte: não adianta filtrar o fixo se a divisão usar outra soma."""
    src = _fonte()
    m = re.search(r"^\s*const custoProj\s*=.*$", src, re.M)
    assert m, "não achei o cálculo de `custoProj` em admin.html"
    assert "fixoMensal" in m.group(0), (
        "o custo por projeto deixou de derivar do fixo filtrado: %s" % m.group(0).strip())


def test_a_categoria_existe_no_seletor_da_tela():
    """Categoria que o backend aceita mas a tela não oferece vira linha órfã:
    ninguém consegue classificar o gasto, e ele volta pro rateio."""
    src = _fonte()
    m = re.search(r"const COST_CATS\s*=\s*\[([^\]]+)\]", src)
    assert m, "não achei COST_CATS"
    assert "'desenvolvimento'" in m.group(1), (
        "a categoria 'desenvolvimento' sumiu do seletor — sem ela o gasto de "
        "construir o produto não tem onde ser classificado")

    m2 = re.search(r"const COST_CATS_FORA_DO_RATEIO\s*=\s*\[([^\]]+)\]", src)
    assert m2 and "'desenvolvimento'" in m2.group(1), (
        "a lista de categorias fora do rateio sumiu ou esvaziou")


def test_CONTROLE_a_versao_ANTIGA_reprovaria():
    """🔑 Este guarda só vale se souber acusar. Aqui rodo a mesma peneira contra
    a linha que existia até 06/09 — ela TEM que reprovar."""
    antiga = "  const fixoMensal = COSTS.reduce((s,c)=> s + costMonthlyBRL(c), 0);"
    assert "costEntraNoRateio" not in antiga, (
        "a peneira parou de distinguir a versão antiga da nova — o teste de "
        "cima virou decoração")


def test_CONTROLE_o_recorte_encontra_a_linha_certa():
    """Prova que o regex pega o cálculo, e não outra linha qualquer."""
    falso = "x\n  const fixoMensal = COSTS.filter(costEntraNoRateio).reduce(f, 0);\ny"
    assert "costEntraNoRateio" in _linha_do_fixo(falso)
    vazio = "const outraCoisa = 1;"
    try:
        _linha_do_fixo(vazio)
    except AssertionError:
        return
    raise AssertionError("o recorte aceitou um fonte sem `fixoMensal`")
