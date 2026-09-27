# -*- coding: utf-8 -*-
"""Os e-mails de login que o SUPABASE manda (27/09/2026).

Link de acesso, confirmar cadastro e redefinir senha saem pelo Supabase Auth,
não pelo backend — então o molde `_email_wrap` não chegava neles e o cliente
recebia "Your Magic Link — Follow this link to login", em inglês. Os modelos
agora moram em `supabase/emails/*.html`, gerados por
`scripts/gerar_emails_do_supabase.py`, e são COLADOS no painel do Supabase
(Authentication → Emails → Templates).

O que este arquivo segura:
1. Todo modelo tem `{{ .ConfirmationURL }}` — sem ela o e-mail chega bonito e
   o botão não leva a lugar nenhum: ninguém entra, ninguém confirma.
2. Nenhum caractere fora do ASCII: os acentos vão como entidade HTML (&#227;).
   O 1º preview saiu "botÃ£o" porque o arquivo não declara charset.
3. O arquivo gravado é o que o gerador produz HOJE — se alguém mexer no texto
   à mão (ou no molde) sem regerar, o repositório e o painel se separam calados.
"""
import glob
import io
import os
import subprocess
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(os.path.dirname(_AQUI))
_PASTA = os.path.join(_RAIZ, "supabase", "emails")
_ESPERADOS = ("link-de-acesso", "confirmar-cadastro", "redefinir-senha")


def _modelos():
    return {os.path.splitext(os.path.basename(p))[0]: io.open(p, encoding="utf-8").read()
            for p in glob.glob(os.path.join(_PASTA, "*.html"))}


def _tem_o_link(html):
    return "{{ .ConfirmationURL }}" in html


def _so_ascii(html):
    return all(ord(c) < 128 for c in html)


def test_os_tres_modelos_existem():
    faltando = [n for n in _ESPERADOS if n not in _modelos()]
    assert not faltando, "faltam modelos em supabase/emails: %s" % faltando


def test_todo_modelo_tem_o_link_do_login():
    sem = [n for n, h in _modelos().items() if not _tem_o_link(h)]
    assert not sem, ("estes modelos não têm {{ .ConfirmationURL }} — o botão "
                     "do e-mail não leva a lugar nenhum: %s" % sem)


def test_acentos_viram_entidade_html():
    fora = [n for n, h in _modelos().items() if not _so_ascii(h)]
    assert not fora, "estes modelos têm acento cru (vira 'botÃ£o' sem charset): %s" % fora


def test_controle_positivo_os_detectores_reprovam():
    assert not _tem_o_link('<a href="{{ .SiteURL }}">Entrar</a>')
    assert _tem_o_link('<a href="{{ .ConfirmationURL }}">Entrar</a>')
    assert not _so_ascii("Clique no botão")
    assert _so_ascii("Clique no bot&#227;o")


def test_o_arquivo_gravado_e_o_que_o_gerador_produz(tmp_path):
    """Regera numa cópia e compara: modelo editado à mão (ou molde mudado sem
    regerar) reprova aqui — e é o aviso de que o painel do Supabase também
    precisa receber a versão nova."""
    gravados = _modelos()
    r = subprocess.run([sys.executable, "-X", "utf8",
                        os.path.join(_RAIZ, "scripts", "gerar_emails_do_supabase.py"),
                        str(tmp_path)],
                       cwd=_RAIZ, capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr[-2000:]
    gerados = {n: io.open(os.path.join(str(tmp_path), n + ".html"), encoding="utf-8").read()
               for n in _ESPERADOS}
    diferentes = [n for n in _ESPERADOS if gravados.get(n) != gerados.get(n)]
    assert not diferentes, (
        "supabase/emails/%s não é o que o gerador produz hoje — regere com "
        "scripts/gerar_emails_do_supabase.py e cole a versão nova no painel "
        "do Supabase" % diferentes)
