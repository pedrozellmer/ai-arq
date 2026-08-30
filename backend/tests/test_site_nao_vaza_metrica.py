# -*- coding: utf-8 -*-
"""O site servido não expõe métrica de negócio em comentário (30/08).

🔒 A auditoria achou taxas de funil, nº de clientes e contagens em comentários
HTML (removidos no build por scripts/strip_html_comments.py) e alguns em
comentário JS (neutralizados no fonte). Este guarda cobre os dois:
  1. o stripper de comentário HTML funciona e é seguro (não toca <script>);
  2. nenhum comentário JS servido carrega número cru de cliente/funil.
"""
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "scripts"))

import strip_html_comments as sh  # noqa: E402

# páginas do app onde as notas de dev vivem
_PAGINAS = ["cadastro.html", "dashboard.html", "revisao.html", "projeto.html",
            "faq.html", "index.html", "login.html", "cronograma.html"]

# padrões de métrica de negócio que não podem chegar ao público
_METRICA = re.compile(
    r"\b\d+\s+de\s+\d+\s+(cadastros?|projetos?|clientes?)\b"
    r"|\b\d+\s+correções\b"
    r"|\b\d+\s+clientes?\s+reais\b"
    r"|\bpágina mais vist"
    r"|\b\d+\s+endereços\b",
    re.IGNORECASE)


def _servido(nome):
    """O HTML como o público recebe: com os comentários HTML já removidos."""
    return sh.limpa_html(io._read(nome)) if False else sh.limpa_html(
        open(os.path.join(RAIZ, nome), encoding="utf-8").read())


def test_stripper_remove_comentario_HTML():
    html = '<p>oi</p><!-- 53 de 89 projetos secretos --><p>tchau</p>'
    assert "53 de 89" not in sh.limpa_html(html)
    assert "<p>oi</p>" in sh.limpa_html(html) and "<p>tchau</p>" in sh.limpa_html(html)


def test_CONTROLE_stripper_NAO_toca_script():
    """🧪 O '<!--' dentro de <script> não é comentário HTML — e um '-->' pode
    estar numa string JS. Se o stripper mexesse aqui, quebraria o site."""
    js = '<script>var a = "x <!-- y --> z"; foo();</script>'
    assert sh.limpa_html(js) == js, "stripper tocou conteúdo de <script>"
    style = '<style>/* <!-- nada --> */ .a{color:red}</style>'
    assert sh.limpa_html(style) == style


def test_nenhuma_pagina_servida_vaza_metrica():
    ruins = []
    for nome in _PAGINAS:
        servido = _servido(nome)
        # olha só o que sobra em comentário JS (// ou /* */) — HTML já foi limpo
        for m in re.finditer(r"//[^\n]*|/\*.*?\*/", servido, re.DOTALL):
            if _METRICA.search(m.group(0)):
                ruins.append((nome, m.group(0).strip()[:70]))
    assert not ruins, "métrica de negócio vazando em comentário JS servido: %r" % ruins


def test_CONTROLE_o_detector_de_metrica_reprova():
    """🧪 Prova que o regex pega mesmo — senão o teste acima passaria por
    qualquer coisa."""
    assert _METRICA.search("// 11 de 50 cadastros pelo Google")
    assert _METRICA.search("// 96 correções de 6 clientes reais")
    assert not _METRICA.search("// isto é um comentário normal sem número de funil")
