# -*- coding: utf-8 -*-
"""O "Leia também" tem que espalhar, não concentrar — e o download tem que medir.

🚨 29/08/2026, do estudo do blog. O gerador escolhia posts relacionados POR
DATA: "os 3 mais recentes de qualquer categoria". Medido no HTML gerado:

    57 dos 78 links iam pra SÓ 3 posts (23 + 20 + 14)
    8 posts publicados não recebiam UM ÚNICO link interno
      — entre eles o único com ranking orgânico provado (ia-arquitetura)
      e o campeão de visitas (memorial, que recebia 2)

Link interno é o jeito mais barato de dizer ao Google que uma página importa,
e a gente dizia isso só pros 3 últimos publicados. Depois do conserto (afinidade
por palavra-chave/categoria, com desconto por link já recebido): 0 órfãos,
teto 6, piso 1 — os mesmos 78 links, redistribuídos.

E o download — a hipótese que sustenta a pauta inteira ("arquivo pra baixar é o
formato que converte") — NUNCA tinha sido medido: o botão não disparava evento.
"""
import io
import os
import re
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BLOG = os.path.join(_RAIZ, "blog")
sys.path.insert(0, _BLOG)

import generate as G  # noqa: E402


def _grafo_simulado():
    """Roda a escolha de relacionados pros publicados, como o build faz.

    🪤 Simula em memória em vez de ler o HTML commitado: o HTML envelhece
    (posts futuros cruzam a data de publicação sem regeneração) e um teste
    sobre ele quebraria com o passar do calendário, não com regressão de código.
    """
    from datetime import date
    hoje = date.today().isoformat()
    pub = [p for p in G.POSTS if p["publish_date"] <= hoje]
    contador = {}
    recebidos = {p["slug"]: 0 for p in pub}
    # 🪤 O build gera TODOS os posts — os futuros também escolhem relacionados
    # (eles só não RECEBEM link, por causa do redirect). A 1ª versão deste
    # simulado iterava só os publicados e acusou 2 órfãos que no site real têm
    # link vindo das páginas futuras. Simulação que não espelha o build acusa
    # errado — e guarda que acusa errado é ignorado.
    for p in G.POSTS:
        for alvo in G.pick_related_posts(p, _contador=contador):
            recebidos[alvo["slug"]] = recebidos.get(alvo["slug"], 0) + 1
    return pub, recebidos


def test_nenhum_post_publicado_fica_ORFAO():
    """🚨 O defeito principal. Órfão = página que o Google só acha pelo sitemap,
    sem nenhum voto interno. Eram 8, incluindo o campeão de visitas."""
    pub, recebidos = _grafo_simulado()
    orfaos = [s for s, n in recebidos.items() if n == 0]
    assert not orfaos, (
        "%d post(s) publicados sem nenhum link interno: %s — a escolha por "
        "relacionados voltou a concentrar" % (len(orfaos), orfaos))


def test_nenhum_post_vira_BURACO_NEGRO():
    """🪤 O outro lado do mesmo defeito: um post com 23 links recebidos rouba o
    voto de todos os outros. Teto folgado (9) pra não quebrar com flutuação —
    o valor medido depois do conserto é 6."""
    _, recebidos = _grafo_simulado()
    pior = max(recebidos.items(), key=lambda kv: kv[1])
    assert pior[1] <= 9, (
        "%s recebe %d links — a distribuição voltou a concentrar (antes do "
        "conserto o pior tinha 23)" % pior)


def test_relacionado_nunca_aponta_pra_post_FUTURO():
    """🔒 Regra antiga que não pode regredir: post futuro tem redirect no guard
    JS — link pra ele é link morto pro SEO."""
    from datetime import date
    hoje = date.today().isoformat()
    pub = [p for p in G.POSTS if p["publish_date"] <= hoje]
    contador = {}
    for p in pub:
        for alvo in G.pick_related_posts(p, _contador=contador):
            assert alvo["publish_date"] <= hoje, (
                "%s linka pro futuro %s" % (p["slug"], alvo["slug"]))


def test_o_botao_de_download_dispara_evento():
    """🔑 A pauta aposta que download converte; sem instrumento é palpite.
    Todo botão gerado tem que carregar data-track com slug válido."""
    html = G.download_buttons_html(
        [{"file": "memorial-descritivo-obra-modelo.docx", "label": "x", "kind": "DOCX"}])
    m = re.search(r'data-track="(baixar-[a-z0-9-]{1,39})"', html)
    assert m, "o botão de download perdeu o data-track — a hipótese do formato "\
              "volta a ser imensurável"
    assert re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", m.group(1)), (
        "slug %r fora da regra do /api/track — o evento morreria calado"
        % m.group(1))


def test_CONTROLE_slug_de_arquivo_esquisito_ainda_passa_na_regra():
    """🧪 Nome de arquivo com maiúscula, acento ou espaço não pode gerar slug
    que o backend descarta."""
    for arquivo in ("Planilha Модель (V2).xlsx", "ÁREAS__2026 final.pdf",
                    "a" * 80 + ".docx"):
        s = G._slug_download(arquivo)
        assert re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", s), (arquivo, s)
