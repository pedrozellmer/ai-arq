# -*- coding: utf-8 -*-
"""Monta os e-mails DE VERDADE e devolve o que o cliente lê.

🔁 Não reimplemente a régua: quem monta é `main._build_falha_email` /
`main._render_email_by_type`. Aqui só se corta o HTML em pedaços legíveis.
"""
import html as _html
import os
import re
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
for _p in (_BACKEND, _AQUI):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# (rótulo, error_hint) — os TRÊS ramos do `_build_falha_email` com
# reprocessavel=False. O hint é o que o próprio código usa pra escolher o ramo.
RAMOS_DE_FALHA = [
    ("dwg_nao_abre", "não consegui abrir/converter o DWG"),
    ("arquivo_grande", "arquivo grande demais: passa do limite de 150 MB"),
    ("sem_cotas", "não achei quantidades na prancha"),
]


def falha_do_ramo(hint):
    """(subject, html) do e-mail de falha NÃO reprocessável para este hint."""
    import main as _m
    return _m._build_falha_email("Cliente", "Residencial Exemplo", False, hint)


def preheader_de(html):
    """A linha que aparece na CAIXA DE ENTRADA, antes de abrir o e-mail."""
    m = re.search(r'mso-hide:all;">(.*?)</div>', html, re.S)
    if not m:
        return ""
    txt = m.group(1).replace("&zwnj;", "").replace("&nbsp;", " ")
    return _html.unescape(re.sub(r"<[^>]+>", " ", txt)).strip()


def imagens_de(html):
    """[(arquivo, alt)] — o alt é o que o Gmail mostra com imagem bloqueada."""
    fora = []
    for m in re.finditer(r"<img\b[^>]*>", html, re.I):
        tag = m.group(0)
        src = re.search(r'src="([^"]*)"', tag)
        alt = re.search(r'alt="([^"]*)"', tag)
        fora.append((os.path.basename(src.group(1)) if src else "",
                     _html.unescape(alt.group(1)) if alt else ""))
    return fora


#: corta em fim de frase, quebra de linha visual e imagem — NÃO em ';'
_CORTE = re.compile(r"(?:<br\s*/?>|</?p\b[^>]*>|</?div\b[^>]*>|<img\b[^>]*>"
                    r"|</?li\b[^>]*>|</?tr\b[^>]*>|</?td\b[^>]*>)", re.I)


def frases(html):
    """As frases que o cliente lê no corpo do e-mail, na ordem."""
    pedacos = _CORTE.split(html)
    fora = []
    for p in pedacos:
        texto = _html.unescape(re.sub(r"<[^>]+>", "", p))
        texto = re.sub(r"\s+", " ", texto).strip()
        if not texto:
            continue
        for f in re.split(r"(?<=[.!?])\s+", texto):
            f = f.strip()
            if f:
                fora.append(f)
    return fora
