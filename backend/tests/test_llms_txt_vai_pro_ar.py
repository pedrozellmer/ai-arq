# -*- coding: utf-8 -*-
"""O /llms.txt existe e É PUBLICADO (31/08/2026).

Pedro, 31/08: *"A gente precisa cada vez mais alavancar as IA's"*. O llms.txt e
a convencao pela qual a gente diz aos modelos o que o site e — inclusive o que
a AI.arq NAO faz, que e o que impede uma IA de nos descrever errado.

🪤 A ARMADILHA QUE ESTE GUARDA FECHA: o workflow de deploy copia a raiz com um
`find -maxdepth 1` que lista extensao por extensao — e **.txt nao esta la**.
Arquivo de texto na raiz so vai pro ar se estiver na lista explicita, que ate
hoje tinha so sitemap.xml e robots.txt. Sem esta linha, o llms.txt existiria no
repo e daria 404 no site PARA SEMPRE, sem ninguem perceber. E a mesma familia
do "pasta nova precisa entrar na include-list".
"""
import io
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARQ = os.path.join(RAIZ, "llms.txt")
YML = os.path.join(RAIZ, ".github", "workflows", "deploy-pages.yml")


def test_o_arquivo_existe():
    assert os.path.isfile(ARQ), "llms.txt sumiu da raiz"


def test_o_deploy_COPIA_o_arquivo():
    """Sem isto o arquivo existe no git e nao existe no site."""
    y = io.open(YML, encoding="utf-8").read()
    # 🪤 31/08 (auditoria): sem a ancora de inicio de linha, o guarda passava
    # com a copia COMENTADA no YAML ("# for f in ... llms.txt"). Guarda que
    # aceita a propria linha desligada nao guarda nada.
    y = chr(10).join(l for l in y.splitlines() if not l.lstrip().startswith("#"))
    assert re.search(r"for f in [^;]*llms\.txt", y), (
        "llms.txt saiu da lista de copia do deploy — ele daria 404 no site, "
        "calado, porque o `find` da raiz nao pega *.txt")


def test_diz_o_que_NAO_fazemos():
    """A parte que mais importa: e o bloco que impede a IA de inventar que a
    gente da preco de obra ou substitui o profissional."""
    t = io.open(ARQ, encoding="utf-8").read().lower()
    for frase in ("não damos preço", "não substituímos", "não somos bim"):
        assert frase in t, "faltou no llms.txt: " + frase


def test_a_promessa_do_beta_esta_certa():
    """🚨 Regra dura: a promessa e gratis e ILIMITADO no beta, sem cartao."""
    t = io.open(ARQ, encoding="utf-8").read().lower()
    assert "ilimitado" in t and "sem cartão" in t
    assert not re.search(r"(primeiro|1[ºo°]?)\s+projeto\s+(grátis|gratis)", t), (
        "o llms.txt promete '1º projeto grátis' — a promessa e ilimitada")


def test_nao_cita_post_que_ainda_nao_publicou():
    """🪤 Os HTMLs dos posts futuros JA existem no site (respondem 200), mas o
    indice do blog filtra por data. Citar um deles aqui furaria o calendario
    editorial — e foi o que a 1a versao deste arquivo fazia, com 8 posts."""
    import json
    posts = json.load(io.open(os.path.join(RAIZ, "blog", "posts.json"),
                              encoding="utf-8"))["posts"]
    t = io.open(ARQ, encoding="utf-8").read()
    import datetime
    hoje = datetime.date.today().isoformat()
    furados = [p["slug"] for p in posts
               if p.get("publish_date", "") > hoje and p["slug"] in t]
    assert not furados, "llms.txt cita post ainda nao publicado: " + str(furados)


def test_CONTROLE_o_guarda_do_deploy_REPROVA_a_linha_COMENTADA():
    """🧪 31/08: era exatamente por aqui que ele passava verde de mentira."""
    linhas = ["jobs:", "  build:", "    steps:",
              "      # for f in index.html llms.txt; do"]
    limpo = chr(10).join(l for l in linhas if not l.lstrip().startswith("#"))
    assert not re.search(r"for f in [^;]*llms" + chr(92) + r".txt", limpo), (
        "o guarda aceita a copia comentada — llms.txt daria 404 calado")
