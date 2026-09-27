# -*- coding: utf-8 -*-
"""O tema escuro dos e-mails (27/09/2026).

O Pedro abriu os e-mails no iPhone no modo escuro e achou estranho. Resultado
depois dos testes PELO SMTP DE VERDADE:
- Gmail: ignora o tema do e-mail e inverte do jeito dele. O truque de
  "blindar" o botão piorou o contraste — descartado por decisão do Pedro.
- Mail do iPhone / Outlook: aceitam o tema escuro. `_email_wrap` agora é um
  documento completo com `@media (prefers-color-scheme: dark)` que troca cada
  COR da paleta pela sua versão escura (`_ESCURO_TEXTO/_FUNDO/_BORDA`).

O que este arquivo segura:
1. O molde declara que suporta escuro e traz o bloco `@media`.
2. O truque do Gmail NÃO volta sem teste (ele piorou o botão).
3. Toda cor de texto/fundo usada num `style="..."` do main.py tem par escuro
   — ou está na lista curta das que funcionam nos dois temas. Cor nova sem
   par = texto escuro em fundo escuro, ilegível, e ninguém percebe.
"""
import io
import os
import re
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import main  # noqa: E402

# Cores que ficam boas nos DOIS temas (não precisam de par):
_TEXTO_OK_NOS_DOIS = {"#ffffff", "#fff", "#94a3b8", "#aab4c0", "#8b93f6"}
_FUNDO_OK_NOS_DOIS = {"#4f46e5"}   # botões roxos: letra branca nos dois


def _cores_do_main():
    src = io.open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8").read()
    texto, fundo = set(), set()
    for m in re.finditer(r'style="([^"]{0,800})"', src):
        st = m.group(1).lower()
        texto.update(re.findall(r'(?<![-\w])color:\s*(#[0-9a-f]{3,6})\b', st))
        fundo.update(re.findall(r'background(?:-color)?:\s*(#[0-9a-f]{3,6})\b', st))
    return texto, fundo


def _sem_par(texto, fundo):
    return (sorted(c for c in texto if c not in main._ESCURO_TEXTO and c not in _TEXTO_OK_NOS_DOIS),
            sorted(c for c in fundo if c not in main._ESCURO_FUNDO and c not in _FUNDO_OK_NOS_DOIS))


def test_o_molde_declara_o_tema_escuro():
    html = main._email_wrap("Título", "Corpo", "Botão", "https://ai.arq.br/")
    assert html.startswith("<!DOCTYPE html>") and html.rstrip().endswith("</html>")
    assert 'name="color-scheme" content="light dark"' in html
    assert "@media (prefers-color-scheme: dark)" in html
    # o par escuro do texto corrido está lá de verdade
    assert '[style*="color:#475569" i]{color:#cbd5e1 !important;}' in html


def test_o_truque_do_gmail_nao_volta_sem_teste():
    """Testado pelo SMTP de verdade em 27/09: fundo roxo + letra escura no
    Gmail do iPhone — pior que o lilás de antes. Se for religar, testar de
    novo no Gmail iOS escuro (NUNCA pelo conector do Gmail, que apaga
    background e <style> antes de mandar)."""
    html = main._email_wrap("Título", "Corpo", "Botão", "https://ai.arq.br/")
    assert "gmail-blend" not in html
    assert "linear-gradient(#4F46E5,#4F46E5)" not in html


def test_toda_cor_dos_emails_tem_par_escuro():
    texto, fundo = _cores_do_main()
    t, f = _sem_par(texto, fundo)
    assert not t and not f, (
        "cor usada em e-mail sem versão escura (fica ilegível no Mail do "
        "iPhone/Outlook no escuro) — acrescente em _ESCURO_TEXTO/_ESCURO_FUNDO "
        "do main.py: texto=%s fundo=%s" % (t, f))


def test_controle_positivo_cor_nova_sem_par_seria_pega():
    t, f = _sem_par({"#475569", "#123456"}, {"#ffffff", "#abcdef"})
    assert t == ["#123456"] and f == ["#abcdef"]
