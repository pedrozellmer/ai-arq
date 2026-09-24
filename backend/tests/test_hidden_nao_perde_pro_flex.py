# -*- coding: utf-8 -*-
"""`hidden` NÃO esconde quem tem classe de display nesta folha do Tailwind.

24/09/2026 — o cartão do Escritório (piloto) no painel nasceu `<a hidden class="flex ...">`.
No tailwind.min.css o `[hidden]{display:none}` mora na camada base e o `.flex{display:flex}`
vem depois, com a mesma especificidade: o `.flex` vence. Resultado: o cartão do piloto
apareceu pra TODO cliente. Medido no navegador: `hidden`+`flex` → display "flex";
controles: só `hidden` → "none", só `flex` → "flex". Lição já anotada em 17/09 (a miniatura).

O guarda: em toda página que carrega o Tailwind e NÃO força `[hidden]{display:none !important}`,
elemento com o atributo `hidden` e classe de display tem que nascer com `style="display:none"`.
🧪 Controle positivo: o cartão antigo reprova no mesmo detector.
"""
import os
import re
import subprocess

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TAG = re.compile(r'<([a-zA-Z][a-zA-Z0-9-]*)\s((?:[^<>"\']|"[^"]*"|\'[^\']*\')*)>', re.S)
_HIDDEN = re.compile(r'(?:^|\s)hidden(?=\s|=|$)')
_CLASSE = re.compile(r'\bclass\s*=\s*"([^"]*)"')
_STYLE_NONE = re.compile(r'\bstyle\s*=\s*"[^"]*display\s*:\s*none', re.I)
_DISPLAY = {"flex", "inline-flex", "grid", "inline-grid", "block", "inline-block", "inline", "table", "contents", "flow-root"}
_FORCA = re.compile(r'\[hidden\][^{]*\{[^}]*display\s*:\s*none\s*!important', re.S)


def _ofensores(fonte):
    if "tailwind" not in fonte or _FORCA.search(fonte):
        return []
    achados = []
    for mt in _TAG.finditer(fonte):
        attrs = mt.group(2)
        if not _HIDDEN.search(re.sub(r'"[^"]*"|\'[^\']*\'', '""', attrs)):
            continue
        c = _CLASSE.search(attrs)
        ruins = (set(c.group(1).split()) if c else set()) & _DISPLAY
        if ruins and not _STYLE_NONE.search(attrs):
            achados.append((fonte[:mt.start()].count("\n") + 1, sorted(ruins)))
    return achados


def test_nenhuma_pagina_esconde_so_com_hidden_o_que_tem_classe_de_display():
    arquivos = subprocess.run(["git", "-C", _RAIZ, "ls-files", "*.html"], capture_output=True, text=True).stdout.split()
    assert len(arquivos) > 20, "não achei as páginas — o guarda estaria olhando o vazio"
    ruins = []
    for arq in arquivos:
        fonte = open(os.path.join(_RAIZ, arq), encoding="utf-8", errors="replace").read()
        ruins += [f"{arq}:{linha} {classes}" for linha, classes in _ofensores(fonte)]
    assert not ruins, "hidden perde pra classe de display (use style=display:none):\n" + "\n".join(ruins)


def test_controle_o_cartao_antigo_reprova():
    antigo = '<link href="/tailwind.min.css"><a id="escritorio-entrada" href="escritorio.html" hidden\n   class="flex items-center">x</a>'
    assert _ofensores(antigo), "o detector não pega o defeito que o criou"
    assert not _ofensores(antigo.replace(" hidden", ' hidden style="display:none"'))    # o conserto passa
    assert not _ofensores("<style>[hidden] { display:none !important; }</style>" + antigo)  # página que força passa


def test_o_painel_revela_pelo_style():
    fonte = open(os.path.join(_RAIZ, "dashboard.html"), encoding="utf-8").read()
    assert "if (porta && (noPiloto || temProjeto)) { porta.hidden = false; porta.style.display = ''; }" in fonte
