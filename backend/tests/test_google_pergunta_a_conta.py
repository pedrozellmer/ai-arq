# -*- coding: utf-8 -*-
"""O login com Google tem que PERGUNTAR qual conta.

🚨 25/08/2026. O Pedro: *"não to conseguindo logar no admin agora"*. O backend
estava de pé, o Supabase Auth respondendo em 0,6s, a página carregando sem erro
de JS. Nada quebrado — e mesmo assim ele não entrava.

A causa: minutos antes ele tinha logado no Gmail como **pedro@ai.arq.br**. O
botão "Entrar com Google" do AI.arq chamava `signInWithOAuth` **sem**
`prompt: 'select_account'`, então o Google reaproveitou essa sessão em
silêncio. Só que o admin é **zarelalopes@gmail.com** (`ADMIN_EMAIL`, e a conta
dele é provider `google`). Ele não escolheu a conta errada: **nunca foi
perguntado**.

🔑 E isto não é problema de admin. QUALQUER cliente com duas contas Google — a
pessoal e a do escritório — entra na conta errada do AI.arq sem perceber. Do
lado dele a leitura é **"meus projetos sumiram"**, e não há erro nenhum na tela
pra explicar: do ponto de vista do sistema, o login deu certo.

🪤 É a família de defeito mais cara que existe aqui: nada falha, nada loga,
ninguém vê. Só o cliente, do lado de lá, achando que perdeu o trabalho dele.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _corpo import fonte  # noqa: E402


def _login():
    return fonte("login.html")


def test_o_google_e_obrigado_a_mostrar_o_seletor():
    """🚨 O caso real: sem isto o Google entrega a conta que já está aberta."""
    src = _login()
    i = src.index("signInWithOAuth")
    corpo = src[i:src.index("});", i)]
    assert "prompt" in corpo and "select_account" in corpo, (
        "o login com Google voltou a aceitar a conta que o navegador já tem "
        "aberta — quem tem duas contas entra na errada e conclui que os "
        "projetos sumiram")


def test_o_prompt_esta_em_queryParams():
    """🪤 `prompt` fora de `queryParams` é ignorado pelo supabase-js: vira uma
    opção que ninguém lê, e o defeito volta parecendo consertado."""
    src = _login()
    i = src.index("signInWithOAuth")
    corpo = src[i:src.index("});", i)]
    assert re.search(r"queryParams\s*:\s*\{[^}]*prompt", corpo), (
        "o `prompt` precisa estar dentro de `queryParams` pra chegar no Google")


def test_o_redirect_do_google_continua_no_cadastro():
    """🧪 Controle: o conserto não pode ter mexido no destino da volta, que foi
    medido em 09/08 (50% dos cadastros por Google se perdiam indo pro painel)."""
    src = _login()
    i = src.index("signInWithOAuth")
    corpo = src[i:src.index("});", i)]
    assert "cadastro.html" in corpo


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO: o guarda tem que REPROVAR o login de antes
# ══════════════════════════════════════════════════════════════════════════
_LOGIN_ANTIGO = """
    const { error } = await sbClient.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: 'https://ai.arq.br/cadastro.html'
      }
    });
"""


def test_controle_positivo_o_login_de_antes_nao_passaria():
    i = _LOGIN_ANTIGO.index("signInWithOAuth")
    corpo = _LOGIN_ANTIGO[i:_LOGIN_ANTIGO.index("});", i)]
    assert "select_account" not in corpo
    assert not re.search(r"queryParams\s*:\s*\{[^}]*prompt", corpo)


def test_todo_botao_de_google_do_site_passa_pela_mesma_regra():
    """🪤 Um segundo botão de Google em outra página, sem o `prompt`, traria o
    defeito de volta por uma porta que este guarda não olha."""
    import glob
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    faltando = []
    for f in glob.glob(os.path.join(raiz, "*.html")):
        txt = open(f, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r"signInWithOAuth", txt):
            # 🪤 Aqui eu tinha escrito `txt[m.start():m.start()+1400]` e o teste
            # reprovou o login JÁ CONSERTADO: o comentário que explica o
            # conserto empurrou o `select_account` pra fora da janela. Quinta
            # vez no mesmo dia que uma janela de N caracteres mede errado.
            # A janela certa termina onde a CHAMADA termina.
            fim = txt.find("});", m.start())
            trecho = txt[m.start():fim if fim > 0 else m.start() + 2000]
            if "'google'" not in trecho and '"google"' not in trecho:
                continue
            if "select_account" not in trecho:
                faltando.append(os.path.basename(f))
    assert not faltando, (
        "estas páginas entram com Google sem perguntar a conta: %s" % faltando)
