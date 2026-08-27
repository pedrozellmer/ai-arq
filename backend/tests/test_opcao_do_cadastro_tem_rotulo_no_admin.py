# -*- coding: utf-8 -*-
"""Toda opção de "Como nos conheceu?" precisa de rótulo no admin.

🚨 26/08/2026, à noite. O Pedro mandou um print do celular: na coluna "Como
conheceu" aparecia **"✏️ ia"** — minúsculo, com ícone de lápis, como se o
cliente tivesse digitado texto livre. Não digitou: `ia` é uma OPÇÃO do
cadastro, criada em 12/08.

O que faltava era uma linha no mapa de rótulos do `admin.html`. Sem ela o código
cai no fallback `'✏️ ' + src`, que existe pra texto livre — e o canal ficou
**duas semanas** parecendo digitação avulsa no único lugar onde a gente olha.

🪤 O que torna isso repetível é a mesma forma do
[[test_botao_bate_com_a_rota]]: os dois lados nascem em commits diferentes. A
opção entra no formulário quando alguém quer medir um canal novo; o rótulo do
admin é outro arquivo, outro dia, e nada conferia que combinavam.

Este guarda cruza os dois lados: para CADA `<option value="...">` do select
`referral_source` em `cadastro.html`, exige entrada no mapa do `admin.html`.

📌 Contexto do desdobramento de 26/08 (pedido do Pedro: *"deixa as IAs
listadas, as principais pelo menos, só pra gente ficar sabendo"*): a opção `ia`
única virou seis (`ia_chatgpt`, `ia_gemini`, `ia_claude`, `ia_copilot`,
`ia_perplexity`, `ia_outra`). Motivo medido: o detalhe era OPCIONAL e o cadastro
de 26/08 veio em branco — sabíamos que veio de IA e não de qual. Dos 5
identificáveis até então, **3 vieram do Gemini** (4 contando o NotebookLM, que
é Google) e 1 do ChatGPT.
"""
import io
import os
import re

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ler(nome):
    return io.open(os.path.join(_RAIZ, nome), encoding="utf-8").read()


def _opcoes_do_cadastro():
    """Os `value=` do select `referral_source` — inclusive dentro de optgroup."""
    html = _ler("cadastro.html")
    i = html.find('id="referral_source"')
    assert i > 0, "não achei o select de origem no cadastro"
    fim = html.find("</select>", i)
    bloco = html[i:fim]
    vals = re.findall(r'<option value="([^"]+)"', bloco)
    return [v for v in vals if v.strip()]


def _mapa_do_admin():
    html = _ler("admin.html")
    i = html.find("function _referralLabel")
    assert i > 0, "não achei o _referralLabel no admin"
    ini = html.find("const map = {", i)
    fim = html.find("};", ini)
    bloco = html[ini:fim]
    return set(re.findall(r"(\w+)\s*:\s*'", bloco))


def test_TODA_opcao_do_cadastro_tem_rotulo_no_admin():
    """🚨 O guarda principal. Foi ele que faltava quando `ia` virou "✏️ ia"."""
    opcoes = set(_opcoes_do_cadastro())
    mapa = _mapa_do_admin()
    faltando = sorted(opcoes - mapa)
    assert not faltando, (
        "opção do cadastro sem rótulo no admin: %s — vai aparecer como texto "
        "livre ('✏️ valor') no único lugar onde a gente olha o canal. "
        "Acrescente no `const map` do `_referralLabel` em admin.html." % faltando)


def test_o_valor_LEGADO_ia_continua_traduzido():
    """🪤 3 perfis reais têm `referral_source='ia'` (12/08 a 26/08). O
    desdobramento não pode deixá-los órfãos de novo."""
    assert "ia" in _mapa_do_admin(), (
        "o valor legado 'ia' saiu do mapa — os 3 perfis que chegaram por IA "
        "antes de 26/08 voltam a aparecer como digitação avulsa")


def test_as_IAs_estao_listadas_uma_a_uma():
    """O pedido do Pedro. Se alguém reunificar em 'ia', a gente volta a não
    saber QUAL IA mandou o cliente."""
    opcoes = set(_opcoes_do_cadastro())
    for v in ("ia_chatgpt", "ia_gemini", "ia_claude", "ia_outra"):
        assert v in opcoes, "sumiu a opção %r do cadastro" % v


def test_o_filtro_de_IA_pega_o_legado_TAMBEM():
    """🪤 Um filtro `=== 'ia'` esconderia as desdobradas; um `startsWith('ia_')`
    esconderia as 3 antigas. Tem que pegar as duas famílias."""
    admin = _ler("admin.html")
    i = admin.find("case 'ia':")
    assert i > 0, "não há filtro de IA na lista de usuários"
    trecho = admin[i:i + 160]
    assert "startsWith('ia')" in trecho, (
        "o filtro de IA não pega as duas famílias (legado 'ia' + 'ia_*'): %r"
        % trecho)


def test_ia_outra_EXIGE_dizer_qual():
    """🚨 O buraco que motivou tudo isto: em 26/08 um cliente marcou IA e deixou
    o detalhe em branco, porque era opcional. 'Outra IA' sem o nome repete o
    problema — a gente sabe que veio de IA e não sabe de qual."""
    cad = _ler("cadastro.html")
    i = cad.find("&& !referralDetailInput.value.trim()")
    assert i > 0, "não achei a validação do detalhe"
    trecho = cad[max(0, i - 320):i + 60]
    assert "ia_outra" in trecho, (
        "'Outra IA' não exige o detalhe — volta a entrar cadastro dizendo "
        "só 'uma IA', que é o que a gente já tinha e não servia")


def test_as_IAs_NOMEADAS_nao_pedem_detalhe():
    """Quem marcou ChatGPT já respondeu qual. Pedir de novo é atrito de graça
    num formulário que já perde 12 cadastros incompletos."""
    cad = _ler("cadastro.html")
    i = cad.find("referralSourceSelect.addEventListener")
    fim = cad.find("});", i)
    trecho = cad[i:fim]
    for v in ("ia_chatgpt", "ia_gemini", "ia_claude", "ia_copilot"):
        assert ("'%s'" % v) not in trecho, (
            "%s abre o campo de detalhe sem precisar" % v)
