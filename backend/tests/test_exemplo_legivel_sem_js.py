# -*- coding: utf-8 -*-
"""O exemplo público tem que ser legível SEM JavaScript.

📏 26/09/2026 (auditoria de aquisição, C10): `curl https://ai.arq.br/exemplo.html`
devolvia `<div id="itens" class="mt-4"></div>` VAZIO — os 25 itens só existiam
dentro do `<script>` (`const EX = {...}`). Robô que não roda JS, que é a maioria
dos leitores de IA, via a página do exemplo sem o exemplo. Desde 27/09 o
scripts/gerar_exemplo_publico.py escreve ali uma tabela simples, da mesma fonte
do EX (e o --conferir cobra); o JS continua trocando pela versão visual.
"""
import io
import json
import os
import re

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _pagina():
    return io.open(os.path.join(_RAIZ, "exemplo.html"), encoding="utf-8").read()


def _ex(html):
    m = re.search(r"const EX = (\{.*?\]\});", html, re.S)
    return json.loads(m.group(1))


def _itens_sem_js(html):
    m = re.search(r'<div id="itens" class="mt-4">(.*?)</div>', html, re.S)
    corpo = m.group(1) if m else ""
    return re.findall(r"<tr><td>([0-9.]+)</td><td>(.*?)</td><td>.*?</td><td>.*?</td><td>(Medido|Estimado)</td>", corpo)


def test_os_itens_do_exemplo_estao_no_html_sem_js():
    html = _pagina()
    ex, linhas = _ex(html), _itens_sem_js(html)
    assert len(linhas) == ex["total"] >= 20, "tabela sem JS com %d linhas; o EX tem %d" % (len(linhas), ex["total"])
    assert sum(1 for *_, c in linhas if c == "Medido") == ex["medidos"]
    assert [n for n, *_ in linhas] == [i["num"] for i in ex["itens"]], "a ordem da tabela sem JS saiu da do EX"


def test_CONTROLE_div_vazio_reprova():
    assert _itens_sem_js('<div id="itens" class="mt-4"></div>') == []
