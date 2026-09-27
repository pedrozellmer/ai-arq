# -*- coding: utf-8 -*-
"""O site servido não expõe métrica de negócio em comentário (30/08).

🔒 A auditoria achou taxas de funil, nº de clientes e contagens em comentários
HTML (removidos no build por scripts/strip_html_comments.py) e alguns em
comentário JS (neutralizados no fonte). Este guarda cobre os dois:
  1. o stripper de comentário HTML funciona e é seguro (não toca <script>);
  2. nenhum comentário JS servido carrega número cru de cliente/funil.
"""
import glob
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "scripts"))

import strip_html_comments as sh  # noqa: E402


def _servidos():
    """TUDO que o deploy põe no ar: .html e .js da raiz e o blog.

    🩸 26/09/2026: a lista era feita à mão (9 páginas) e o `aiarq-utils.js`,
    carregado em TODA página, servia "39 de 39 clientes" num comentário; o
    admin.html servia contagens de clientes e endereços. Página ou script novo
    nascia fora do guarda."""
    arqs = (sorted(glob.glob(os.path.join(RAIZ, "*.html")))
            + sorted(glob.glob(os.path.join(RAIZ, "*.js")))
            + sorted(glob.glob(os.path.join(RAIZ, "blog", "**", "*.html"), recursive=True)))
    return [os.path.relpath(a, RAIZ) for a in arqs]

# padrões de métrica de negócio que não podem chegar ao público
_METRICA = re.compile(
    # 🩸 26/09/2026: "(18 dos / 32 cadastros da semana de 21/09)" chegou ao ar no
    # cadastro.html — o regex só conhecia "de" (não "dos/das/do/da") e cada linha
    # `//` era olhada sozinha, então a frase quebrada em duas passava. Agora o
    # conector aceita as contrações, contagem solta de cadastros também conta, e
    # os `//` de linhas seguidas são lidos juntos (ver _comentarios_js).
    r"\b\d+\s+d[eoa]s?\s+\d+\s+(cadastros?|projetos?|clientes?)\b"
    r"|\b\d+\s+cadastros?\b"
    # a revisão cética de 26/09 achou o que ainda escapava: "68 pessoas
    # COMPLETARAM", "16 projetos de 12 clientes", tabela "60 projetos — 0,0%",
    # "19 entregas", "74 clientes"
    r"|\b\d+\s+(pessoas|clientes|projetos|entregas)\s+d[eoa]s?\s+\d+"
    r"|\b\d+\s+pessoas\s+complet"
    r"|\b\d+\s+projetos?\s*[:—]"
    r"|\b\d+\s+(entregas|clientes)\b"
    r"|\b\d+\s+correções\b"
    r"|\b\d+\s+clientes?\s+reais\b"
    r"|\bpágina mais vist"
    r"|\b\d+\s+endereços\b",
    re.IGNORECASE)


def _servido(nome):
    """O arquivo como o público recebe: HTML com os comentários HTML já
    removidos pelo build; .js cru (o build não toca em JS)."""
    texto = open(os.path.join(RAIZ, nome), encoding="utf-8").read()
    return sh.limpa_html(texto) if nome.endswith(".html") else texto


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


def _comentarios_js(texto):
    """Os comentários JS do texto, com os `//` de linhas SEGUIDAS juntados num
    bloco só: frase quebrada em duas linhas ('(18 dos' / '// 32 cadastros')
    passava quando cada linha era olhada sozinha."""
    blocos = [m.group(0) for m in re.finditer(r"/\*.*?\*/", texto, re.DOTALL)]
    seguidas = []
    for linha in texto.split("\n"):
        m = re.search(r"//(.*)$", linha)
        if m and linha.lstrip().startswith("//"):
            seguidas.append(m.group(1).strip())
            continue
        if seguidas:
            blocos.append(" ".join(seguidas))
            seguidas = []
        if m:  # comentário no fim de uma linha de código
            blocos.append(m.group(1))
    if seguidas:
        blocos.append(" ".join(seguidas))
    return blocos


def test_nenhuma_pagina_servida_vaza_metrica():
    ruins = []
    servidos = _servidos()
    assert len(servidos) >= 30, "o guarda quase não achou arquivo servido: %d" % len(servidos)
    for nome in servidos:
        # olha só o que sobra em comentário JS (// ou /* */) — HTML já foi limpo
        for bloco in _comentarios_js(_servido(nome)):
            if _METRICA.search(bloco):
                ruins.append((nome, _METRICA.search(bloco).group(0), bloco.strip()[:90]))
    assert not ruins, "métrica de negócio vazando em comentário JS servido: %r" % ruins


def test_CONTROLE_a_frase_quebrada_em_duas_linhas_e_pega():
    """🧪 Frase partida entre dois `//` (o caso de 26/09): só a leitura JUNTADA
    pega — linha a linha, nem o regex novo casa (a revisão cética mostrou que o
    controle de antes passava mesmo sem a junção, porque "32 cadastros" sozinho
    já casava)."""
    js = "<script>\n  // medido: 18 dos\n  // 32 projetos concluídos\n  var a = 1;\n</script>"
    assert any(_METRICA.search(b) for b in _comentarios_js(js))
    assert not any(_METRICA.search(m.group(0)) for m in re.finditer(r"//[^\n]*", js))


def test_CONTROLE_o_js_servido_tambem_e_lido():
    """O .js não passa pelo stripper de HTML, mas é servido — e é lido."""
    assert "aiarq-utils.js" in _servidos()
    assert any(n.startswith("blog") for n in _servidos())


def test_CONTROLE_o_detector_de_metrica_reprova():
    """🧪 Prova que o regex pega mesmo — senão o teste acima passaria por
    qualquer coisa."""
    assert _METRICA.search("// 11 de 50 cadastros pelo Google")
    assert _METRICA.search("// 96 correções de 6 clientes reais")
    assert _METRICA.search("// 18 dos 32 cadastros")
    assert _METRICA.search("// 11 das 50 projetos")
    assert not _METRICA.search("// isto é um comentário normal sem número de funil")
