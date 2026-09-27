# -*- coding: utf-8 -*-
"""Post com modelo pra baixar diz, AO LADO do download, se o AI.arq gera aquele documento.

📏 27/09/2026 (auditoria de aquisição, pauta): dos 8 posts com download, nenhum
dizia colado no botão o que o produto faz com aquilo (o do memorial dizia dois
parágrafos abaixo, e só no 1º dos seus dois blocos de download). Quem baixa o
modelo de boletim, quadro de áreas ou checklist da Caixa saía sem saber se o
AI.arq gera aquele documento — e a IA que lê o post também.

Regra: todo post com `downloads` tem `download_nota` no posts.json, que o
gerador põe DENTRO da caixa de download, logo abaixo dos botões (em todos os
blocos <DOWNLOAD_BUTTONS> do post).
"""
import io
import json
import os
import re

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _posts():
    d = json.loads(io.open(os.path.join(_RAIZ, "blog", "posts.json"), encoding="utf-8").read())
    return d if isinstance(d, list) else d["posts"]


def _sem_nota(posts):
    return [p["slug"] for p in posts
            if p.get("downloads") and "AI.arq" not in (p.get("download_nota") or "")]


def test_todo_post_com_download_diz_o_que_o_produto_faz_com_aquilo():
    ruins = _sem_nota(_posts())
    assert not ruins, (
        "post com download sem `download_nota` dizendo se o AI.arq gera o documento: %s" % ruins)


def _notas_dentro_da_caixa(html, nota):
    """Quantas vezes a nota aparece logo depois da grade de botões e logo antes
    de a caixa fechar — ou seja, dentro dela."""
    return len(re.findall(r'</a>\s*</div>\s*<p class="aiarq-dl-nota[^"]*">' + re.escape(nota) + r'</p>\s*</div>', html))


def test_a_nota_sai_dentro_de_cada_caixa_de_download():
    for p in _posts():
        if not p.get("download_nota"):
            continue
        html = io.open(os.path.join(_RAIZ, "blog", "posts", p["slug"] + ".html"), encoding="utf-8").read()
        caixas = html.count('class="aiarq-downloads')
        assert caixas >= 1, p["slug"]
        assert _notas_dentro_da_caixa(html, p["download_nota"]) == caixas, (
            "%s: %d caixa(s) de download, nota dentro de %d — rode blog/generate.py"
            % (p["slug"], caixas, _notas_dentro_da_caixa(html, p["download_nota"])))


def test_CONTROLE_download_sem_nota_e_pego():
    falso = {"slug": "x", "downloads": [{"file": "a.pdf"}]}
    assert _sem_nota([falso]) == ["x"]
    falso["download_nota"] = "Este modelo é pra preencher à mão."
    assert _sem_nota([falso]) == ["x"], "nota que não fala do AI.arq não cumpre a regra"
    falso["download_nota"] = "O AI.arq não gera este documento."
    assert _sem_nota([falso]) == []


def test_CONTROLE_nota_fora_da_caixa_nao_conta():
    fora = '<div class="aiarq-downloads"><div class="grid"><a>b</a>\n  </div>\n</div>\n<p class="aiarq-dl-nota">N</p>'
    dentro = '<div class="aiarq-downloads"><div class="grid"><a>b</a>\n  </div>\n  <p class="aiarq-dl-nota mt-3">N</p>\n</div>'
    assert _notas_dentro_da_caixa(fora, "N") == 0
    assert _notas_dentro_da_caixa(dentro, "N") == 1
