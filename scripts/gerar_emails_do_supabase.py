# -*- coding: utf-8 -*-
"""Gera os e-mails que o SUPABASE manda (login) no molde dos e-mails do AI.arq.

Por que existe (27/09/2026): o link de acesso sem senha chegou com o modelo
padrão do Supabase, em inglês ("Your Magic Link — Follow this link to login").
Os e-mails de confirmar cadastro e de redefinir senha estavam iguais. Estes
três NÃO saem pelo backend — saem pelo Supabase Auth —, então o molde
`_email_wrap` do main.py não chegava neles.

Como usar:
    python -X utf8 scripts/gerar_emails_do_supabase.py
Grava `supabase/emails/*.html` (+ o assunto de cada um em `assuntos.txt`).
O conteúdo vai pro painel do Supabase: Authentication → Emails → Templates →
(Magic link / Confirm sign up / Reset password) → Subject + Body.

🔑 `{{ .ConfirmationURL }}` é a variável do Supabase com o link do login. Sem
ela o e-mail chega bonito e NÃO ENTRA — o guarda
`test_emails_do_supabase.py` confere que cada arquivo tem.
"""
import io
import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RAIZ, "backend"))

import main  # noqa: E402  (só pra usar o MESMO molde dos outros e-mails)

LINK = "{{ .ConfirmationURL }}"

_SE_NAO_FOI_VOCE = ("Se não foi você, pode ignorar este e-mail — "
                    "nada muda na sua conta.")

EMAILS = {
    "link-de-acesso": {
        "painel": "Magic link",
        "assunto": "Seu link de acesso ao AI.arq",
        "html": main._email_wrap(
            title="Seu link de acesso",
            body_html=("Clique no botão abaixo para entrar no AI.arq — "
                       "sem senha.<br><br>"
                       "<span style=\"font-size:13px;color:#94a3b8;\">O link expira "
                       "em pouco tempo e só funciona uma vez. Se ele não abrir, "
                       "peça um novo na tela de login.</span>"),
            cta_text="Entrar no AI.arq",
            cta_url=LINK,
            reason=("Você recebeu este e-mail porque alguém pediu um link de "
                    "acesso ao AI.arq com este endereço. " + _SE_NAO_FOI_VOCE),
            signoff=False,
            preheader="Clique para entrar no AI.arq — sem senha.",
        ),
    },
    "confirmar-cadastro": {
        "painel": "Confirm sign up",
        "assunto": "Confirme seu e-mail no AI.arq",
        "html": main._email_wrap(
            title="Falta só confirmar seu e-mail",
            body_html=("Que bom ter você no AI.arq! Clique no botão abaixo para "
                       "confirmar este endereço e entrar na sua conta.<br><br>"
                       "Depois é só enviar a primeira prancha (PDF, DWG ou DXF) "
                       "pra gerar a planilha de quantitativos."),
            cta_text="Confirmar e entrar",
            cta_url=LINK,
            reason=("Você recebeu este e-mail porque este endereço foi usado "
                    "para criar uma conta no AI.arq. " + _SE_NAO_FOI_VOCE),
            signoff=True,
            preheader="Um clique para confirmar e entrar no AI.arq.",
        ),
    },
    "redefinir-senha": {
        "painel": "Reset password",
        "assunto": "Redefinir sua senha do AI.arq",
        "html": main._email_wrap(
            title="Redefinir sua senha",
            body_html=("Recebemos um pedido para trocar a senha da sua conta no "
                       "AI.arq. Clique no botão abaixo para escolher uma nova."
                       "<br><br><span style=\"font-size:13px;color:#94a3b8;\">O "
                       "link expira em pouco tempo e só funciona uma vez.</span>"),
            cta_text="Escolher nova senha",
            cta_url=LINK,
            reason=("Se não foi você que pediu, pode ignorar este e-mail — "
                    "sua senha atual continua valendo."),
            signoff=False,
            preheader="Clique para escolher uma nova senha.",
        ),
    },
}


def main_():
    # 1º argumento opcional = pasta de saída (o teste gera numa pasta temporária
    # e compara com a do repositório, sem escrever no repositório)
    saida = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_RAIZ, "supabase", "emails")
    os.makedirs(saida, exist_ok=True)
    assuntos = []
    for nome, e in EMAILS.items():
        caminho = os.path.join(saida, nome + ".html")
        # 🪤 Acento vira entidade HTML (&#227;): o 1º preview saiu "botÃ£o"
        # porque o arquivo não declara charset. Em e-mail, quem manda o charset
        # é o Supabase — entidade funciona com ou sem ele, em qualquer leitor.
        html = e["html"].encode("ascii", "xmlcharrefreplace").decode("ascii")
        io.open(caminho, "w", encoding="utf-8", newline="\n").write(html + "\n")
        assuntos.append("%s (%s): %s" % (nome, e["painel"], e["assunto"]))
        print("gravado:", os.path.relpath(caminho, _RAIZ))
    io.open(os.path.join(saida, "assuntos.txt"), "w", encoding="utf-8",
            newline="\n").write("\n".join(assuntos) + "\n")


if __name__ == "__main__":
    main_()
