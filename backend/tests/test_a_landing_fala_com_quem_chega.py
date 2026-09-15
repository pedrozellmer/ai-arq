# -*- coding: utf-8 -*-
"""A landing tem que nomear o público que realmente chega — e sem virar lista.

📏 MEDIDO em 14/09/2026, nos 118 perfis da base:

  Engenharia Civil     51 (43,2%)   ← e 27 deles nos últimos 30 dias
  Orçamento e Custos   23 (19,5%)
  Outro                15 (12,7%)
  Arquitetura          14 (11,9%)
  Construção           14 (11,9%)

**88% de quem se cadastra não é arquiteto**, e a landing falava "pra arquiteto
e projetista". A virada foi em julho: arquitetura era 33,3% dos cadastros até
junho e caiu para 0% em julho, 5% em agosto. O Google traz 63,6% da base e
**80% desses são engenharia/orçamento/construção**.

🔑 E o produto serve MELHOR esse público (60 dias):
  Orçamento    19,6% das linhas medidas · 56,0% cobráveis
  Engenharia   14,9% · 59,6%
  Arquitetura   3,4% · 16,7%   ← o pior
A causa é direta: quanto mais a linha depende de ÁREA, pior a gente mede (m²
sai 3,1% medido contra 42% de peça), e área é o trabalho do arquiteto.

🪤 MAS NÃO PODE VIRAR LISTA. Em 31/08 a IA do Capterra leu o site e publicou
que a AI.arq é "for contractors" — a causa foi uma **lista plana de 6 públicos**
na FAQ, e a máquina escolheu dela o item mais "empresa de obra". Lista de
profissão é perder o controle de como a IA nos descreve, e 26% das nossas
impressões passam por IA generativa.

🪤 E o `og:description` entra JUNTO. Também em 31/08: corrigi title, description
e og:title e **esqueci o og:description** — que era exatamente de onde o
Capterra tirou a frase que publicou.

🚫 Arquitetura NÃO sai: são 11,9% da base, mas a maior média de projetos por
pessoa (2,3 contra 1,7). O conserto é incluir, não trocar.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _corpo import fonte  # noqa: E402

_PUBLICOS = ("arquitet", "engenh", "orçament", "orcament", "projetista",
             "construtor", "incorporador", "empreiteir", "mestre de obra")


def _index():
    return fonte("index.html")


def _tag(nome):
    """O conteúdo de uma tag de metadado da home."""
    src = _index()
    if nome == "title":
        m = re.search(r"<title>(.*?)</title>", src, re.S)
    else:
        m = re.search(r'<meta[^>]*(?:name|property)="%s"[^>]*content="(.*?)"'
                      % re.escape(nome), src, re.S)
    assert m, "não achei a tag %r na home" % nome
    return m.group(1)


# ── as quatro portas por onde o Google e a IA leem a home ────────────────
def test_as_QUATRO_tags_nomeiam_engenharia():
    """🪤 São quatro, e em 31/08 eu corrigi três. A que faltou foi justamente a
    que a IA do Capterra citou."""
    faltando = [n for n in ("title", "description", "og:title", "og:description")
                if "engenh" not in _tag(n).lower()]
    assert not faltando, (
        "tag(s) que ainda não falam com 43%% da base: %r" % faltando)


def test_o_schema_org_nao_diz_mais_so_arquitetos():
    """🪤 A 1ª versão deste guarda usava regex e pegava a `description` de
    DENTRO de `offers` (a de preço), reprovando o conserto certo. JSON-LD é
    JSON: parsear é mais curto e não erra de campo."""
    import json
    src = _index()
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', src, re.S)
    assert m, "não achei o bloco JSON-LD na home"
    dados = json.loads(m.group(1))
    if isinstance(dados, list):
        dados = next(d for d in dados
                     if d.get("@type") == "SoftwareApplication")
    assert dados.get("@type") == "SoftwareApplication", dados.get("@type")
    d = (dados.get("description") or "")
    assert "engenh" in d.lower(), (
        "o JSON-LD — que é o que a máquina lê primeiro — continua dizendo que o "
        "produto é só pra arquitetos: %r" % d[:130])
    assert "arquitet" in d.lower(), (
        "arquitetura saiu do JSON-LD: %r" % d[:130])


def test_CONTROLE_arquitetura_NAO_sumiu():
    """São 11,9% da base mas a MAIOR média de projetos por pessoa (2,3 × 1,7).
    O conserto é incluir, não trocar de público."""
    for n in ("title", "description", "og:title", "og:description"):
        assert "arquitet" in _tag(n).lower(), (
            "arquitetura saiu da tag %r — era pra incluir engenharia, não "
            "trocar um público pelo outro" % n)


# ── a lição de 31/08: lista de profissão entrega a descrição pra máquina ──
def test_NAO_virou_lista_de_profissoes():
    """🚨 Em 31/08 a IA do Capterra publicou que somos "for contractors" porque
    havia uma lista plana de 6 públicos. Quanto mais nomes, menos controle sobre
    qual deles a máquina usa pra nos definir. Teto de 3 por tag."""
    for n in ("title", "description", "og:title", "og:description"):
        txt = _tag(n).lower()
        quantos = sum(1 for p in _PUBLICOS if p in txt)
        assert quantos <= 3, (
            "a tag %r cita %d públicos — vira lista, e a máquina escolhe um "
            "deles pra nos descrever (caso Capterra, 31/08): %r"
            % (n, quantos, _tag(n)[:140]))


def test_o_title_cabe_no_google():
    """Title cortado no meio perde justamente o fim, que é onde o público está."""
    t = _tag("title")
    assert len(t) <= 70, ("title com %d caracteres — o Google corta perto de 60 "
                          "e o público fica de fora: %r" % (len(t), t))


# ── a seção de recursos não pode dizer ao engenheiro que não é pra ele ────
def test_a_secao_de_recursos_nao_exclui_instalacoes():
    """A frase dizia "pranchas de ARQUITETURA brasileiras" — e as disciplinas de
    instalação são as que a gente MEDE MELHOR: incêndio 51%, hidráulica 41%,
    ar-condicionado 35%, elétrica 30%, contra pisos 2,9%."""
    src = _index()
    assert "pranchas de arquitetura brasileiras" not in src.lower(), (
        "a home voltou a dizer que a IA lê 'pranchas de arquitetura', que é "
        "mandar embora 43% de quem chega")
    m = re.search(r"O que a IA enxerga em cada prancha.*?</p>", src, re.S)
    assert m and "instala" in m.group(0).lower(), (
        "a chamada da seção de recursos não menciona instalações")


def test_a_lista_de_pranchas_cita_as_disciplinas_que_medem_melhor():
    src = _index().lower()
    m = re.search(r"10\+ tipos de pranchas.*?</p>", src, re.S)
    assert m, "não achei o card dos tipos de prancha"
    bloco = m.group(0)
    faltando = [d for d in ("elétrica", "hidráulica", "incêndio")
                if d not in bloco]
    assert not faltando, (
        "o card de tipos de prancha ainda só cita arquitetura/interiores e "
        "deixa de fora %r — que são as disciplinas de maior %% medido" % faltando)
