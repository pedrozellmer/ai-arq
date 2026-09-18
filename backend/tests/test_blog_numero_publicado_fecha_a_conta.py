# -*- coding: utf-8 -*-
"""Número que o blog publica tem que fechar a conta — e fechar nos DOIS lugares.

🩸 18/09/2026. O post `ia-conta-melhor-do-que-mede-planta` publica os mesmos
seis números DUAS vezes: no corpo ("32,4% seladas como medidas: 901 de 2.779
linhas") e na ficha de fonte do rodapé ("Contagem (un/pç): 901 de 2.779 seladas
como medidas (32,4%)"). Quando a medição envelhece e alguém atualiza à mão, o
erro provável não é errar a conta — é atualizar UM dos dois lugares e não o
outro. O post sobe, o site fica verde, e o rodapé desmente o texto.

🔑 Nenhum guarda do blog olhava a ARITMÉTICA do que a gente afirma em público,
e a regra dura da casa é "fonte em toda afirmação". Fonte que não bate com a
afirmação é pior que fonte nenhuma.

O que estes guardas provam:
  1. todo percentual grudado num par "N de M" bate com N/M;
  2. todo par citado numa ficha de fonte interna também aparece no corpo — o que
     reprova nos DOIS sentidos do esquecimento (mexeu no corpo e não na ficha: o
     par velho da ficha some do corpo; mexeu na ficha e não no corpo: idem);
  3. os números sobrevivem à GERAÇÃO — o HTML publicado carrega os mesmos pares.

🪤 "Grudado" é a parte delicada. Uma janela larga de caracteres reprova texto
inocente: `dwg-ou-pdf-...` diz "falha em 6 de 10 envios; o PDF mede 4,7%", que
são dois fatos diferentes na mesma frase. Por isso o percentual só conta como
ligado ao par quando o que separa os dois não tem outro dígito, nem ';', nem
fim de frase. Medido no acervo antes de escrever: janela larga dava 1
falso-positivo em 9 pares; a regra apertada dá 0 em 8.

🚨 O QUE ESTE GUARDA **NÃO** ALCANÇA — dito aqui pra ninguém confundir verde
com cobertura:

  · **Múltiplo escrito por extenso.** "A IA sela vinte vezes mais contagem do
    que área" é uma afirmação aritmética sobre dois percentuais, e nada aqui a
    confere. A revisão adversarial de 18/09 achou exatamente isso: a versão
    anterior do post dizia "dezesseis vezes" com números que davam 22,8×, e os
    guardas passaram verdes. Conferir exigiria adivinhar QUAIS dois percentuais
    o múltiplo compara — guarda que adivinha vira ruído, então este não tenta.
    **Ao mexer num percentual, releia o múltiplo à mão.**
  · **Se o número é VERDADEIRO.** Aqui só se prova coerência interna: a conta
    fecha e os dois lugares concordam. Se o número bate com o banco, só medindo
    — e a bancada não tem banco. Isso é trabalho de quem escreve, não do CI.
  · **Se a definição é a mesma nas duas pontas.** Comparar 54,8% de agosto com
    69,2% de setembro pode ser maçã com laranja se uma correção retroativa
    mudou a régua no meio — foi o que aconteceu em 14/09, e nenhum teste pega.
"""
import io
import json
import os
import re

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLOG = os.path.join(RAIZ, "blog")

RE_PAR = re.compile(r"(\d[\d.]*)\s+de\s+(\d[\d.]*)")
RE_PCT = re.compile(r"(\d+(?:,\d+)?)\s*%")

MAX_ENTRE = 40          # caracteres entre o par e o percentual
TOLERANCIA_PP = 0.15    # arredondamento de uma casa decimal


def _posts():
    return json.load(io.open(os.path.join(BLOG, "posts.json"), encoding="utf-8"))["posts"]


def _n(s):
    """1.283 em pt-BR é mil duzentos e oitenta e três, não 1,283."""
    return int(s.replace(".", ""))


def _pct(s):
    return float(s.replace(",", "."))


def _separador_limpo(entre):
    """O que separa o par do percentual não pode conter outro número nem quebra
    de frase — senão são duas estatísticas vizinhas, e não uma afirmação só."""
    if len(entre) > MAX_ENTRE:
        return False
    return not (re.search(r"\d", entre) or ";" in entre or "." in entre or "\n" in entre)


def percentuais_ligados(texto, casamento):
    """Percentuais estruturalmente amarrados a este par — antes ou depois."""
    ligados = []
    for mp in RE_PCT.finditer(texto):
        if mp.end() <= casamento.start():
            if _separador_limpo(texto[mp.end():casamento.start()]):
                ligados.append(_pct(mp.group(1)))
        elif mp.start() >= casamento.end():
            if _separador_limpo(texto[casamento.end():mp.start()]):
                ligados.append(_pct(mp.group(1)))
    return ligados


def contas_do_texto(texto):
    """Devolve (trecho, esperado, percentuais_ligados) de cada par com percentual."""
    saida = []
    for m in RE_PAR.finditer(texto):
        parte, todo = _n(m.group(1)), _n(m.group(2))
        if todo == 0:
            continue
        ligados = percentuais_ligados(texto, m)
        if ligados:
            saida.append((m.group(0), round(parte * 100.0 / todo, 1), ligados))
    return saida


def corpo_do_post(p):
    partes = [p.get("title", ""), p.get("description", ""), p.get("intro", "")]
    for s in p.get("sections", []):
        for chave, valor in s.items():
            if isinstance(valor, str):
                partes.append(valor)
            elif isinstance(valor, list):
                partes.append(" ".join(str(x) for x in valor))
    return "\n".join(partes)


def fichas_internas(p):
    return [(s.get("title", "") + " " + s.get("description", ""))
            for s in p.get("sources", []) if s.get("type") == "internal"]


def pares_de(texto):
    return {(_n(a), _n(b)) for a, b in RE_PAR.findall(texto)}


# ----------------------------------------------------------------- os guardas

def test_o_percentual_publicado_fecha_com_o_proprio_par():
    """901 de 2.779 é 32,4%. Se o texto disser outro número, o post mente com
    a prova do lado."""
    quebrados = []
    for p in _posts():
        for texto in [corpo_do_post(p)] + fichas_internas(p):
            for trecho, esperado, ligados in contas_do_texto(texto):
                if not any(abs(c - esperado) <= TOLERANCIA_PP for c in ligados):
                    quebrados.append((p["slug"], trecho, esperado, ligados))
    assert not quebrados, (
        "percentual publicado que NÃO fecha com o par ao lado "
        "(slug, par, o que a conta dá, o que o texto diz): %r" % quebrados)


def test_a_ficha_de_fonte_nao_desmente_o_corpo():
    """Ficha interna é a prova do que o corpo afirma. Todo par citado nela tem
    que existir no corpo — é isto que pega o 'atualizei um lugar só'."""
    orfaos = []
    for p in _posts():
        no_corpo = pares_de(corpo_do_post(p))
        for ficha in fichas_internas(p):
            for par in pares_de(ficha):
                if par not in no_corpo:
                    orfaos.append((p["slug"], "%d de %d" % par))
    assert not orfaos, (
        "ficha de fonte cita par que o corpo do post não afirma — um dos dois "
        "ficou pra trás numa atualização: %r" % orfaos)


def test_os_numeros_sobrevivem_a_geracao():
    """🪤 O artefato é que vai pro ar. Par que existe no JSON e some do HTML
    gerado é número que ninguém lê — a lição de test_blog_fontes, aplicada aqui."""
    sumidos = []
    for p in _posts():
        caminho = os.path.join(BLOG, "posts", p["slug"] + ".html")
        if not os.path.isfile(caminho):
            continue
        gerado = io.open(caminho, encoding="utf-8").read()
        for ficha in fichas_internas(p):
            for a, b in RE_PAR.findall(ficha):
                if ("%s de %s" % (a, b)) not in gerado:
                    sumidos.append((p["slug"], "%s de %s" % (a, b)))
    assert not sumidos, (
        "par de número que está no posts.json e NÃO está no HTML gerado — "
        "rode `python blog/generate.py`: %r" % sumidos)


# ------------------------------------------------- controles: provar que REPROVA

def test_CONTROLE_conta_errada_e_pega():
    """🧪 Guarda que nunca reprova não é guarda."""
    mentira = "Contagem: 901 de 2.779 seladas como medidas (50,0%)."
    contas = contas_do_texto(mentira)
    assert contas, "o controle não achou par nenhum — o casador quebrou"
    trecho, esperado, ligados = contas[0]
    assert abs(esperado - 32.4) <= TOLERANCIA_PP
    assert not any(abs(c - esperado) <= TOLERANCIA_PP for c in ligados), (
        "a conta errada passou pelo guarda")


def test_CONTROLE_conta_certa_passa():
    """🧪 E o controle pelo avesso: o texto verdadeiro não pode reprovar."""
    verdade = "Contagem: 901 de 2.779 seladas como medidas (32,4%)."
    trecho, esperado, ligados = contas_do_texto(verdade)[0]
    assert any(abs(c - esperado) <= TOLERANCIA_PP for c in ligados)


def test_CONTROLE_duas_estatisticas_na_mesma_frase_NAO_sao_amarradas():
    """🪤 O falso-positivo que existe de verdade no acervo: 'falha em 6 de 10
    envios; o PDF mede 4,7%' são dois fatos. Se o guarda amarrar os dois, ele
    reprova post correto e vira ruído — e guarda que vira ruído é desligado."""
    frase = "o DWG falha em 6 de 10 envios; o PDF mede 4,7%"
    assert contas_do_texto(frase) == [], (
        "o guarda amarrou percentual de um fato ao par de outro")


def test_CONTROLE_o_par_orfao_e_pego():
    """🧪 O caso de 18/09: a ficha ficou com o número velho."""
    corpo = "Contagem: 1.184 de 2.771 linhas."
    ficha = "Contagem (un/pç): 901 de 2.779 seladas como medidas."
    assert pares_de(ficha) - pares_de(corpo), (
        "par velho na ficha não foi detectado como órfão do corpo")


def test_CONTROLE_milhar_em_pt_br_nao_vira_decimal():
    """🪤 '1.283' vale mil duzentos e oitenta e três. Ler como 1,283 erra por
    mil — é o mesmo erro de 1000× que o cronograma financeiro quase cometeu."""
    assert _n("1.283") == 1283
    assert _n("2.779") == 2779
    assert _pct("54,8") == pytest.approx(54.8)
