# -*- coding: utf-8 -*-
"""Quem travou no cadastro recebe UM e-mail, no mesmo dia — não dois, com uma
semana de intervalo.

🚨 25/08/2026. Um amigo do Pedro testou o cadastro pelo Google e não conseguiu
seguir sem completar o perfil. Fui olhar o banco e achei, **7 minutos antes do
teste**, uma pessoa real no mesmo estado — e mais 11 nos últimos 30 dias:

    81 contas Google · 13 sem perfil (16%) · 11 nos últimos 30 dias

A esteira já resgatava essa gente, mas com um atraso que ninguém tinha medido:

    boas_vindas    +3h
    nudge_cadastro +7 DIAS   ← o teto de "1 automático por semana" segurava

Prova do teto, no acervo:

    orcamento.eletroenge  boas_vindas 17/08 15:00 · nudge 24/08 15:00
                          (exatamente 7 dias depois, na mesma hora)

🔑 O teto semanal existe pra marketing. Este lembrete **não é marketing**: sem
ele a conta não funciona. A pessoa passa uma semana com um login que não leva
a lugar nenhum.

Decisão do Pedro: juntar os dois. Quem não tem perfil recebe UM e-mail em 3h —
boas-vindas + o passo que falta + link de 1 clique.

🪤 E aí some o e-mail antigo? Não: o `nudge_cadastro` continua existindo pra
quem recebeu o welcome ANTES desta mudança. O que ele não pode é chegar
depois do combinado, repetindo o mesmo recado uma semana atrasado.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _corpo import corpo_de, fonte  # noqa: E402

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)


def _monta(**kw):
    """Executa `_build_welcome_email` de verdade."""
    import html as _html_real
    ns = {"_email_img": lambda *a, **k: "",
          "_greeting_line": lambda n: "Oi",
          "_email_wrap": lambda titulo, body, cta, url, **k: {
              "titulo": titulo, "body": body, "cta": cta, "url": url, **k},
          "_hw": _html_real}
    corpo = corpo_de("_build_welcome_email")
    corpo = corpo.replace("import html as _hw", "pass")
    exec(compile(corpo, "welcome", "exec"), ns)
    return ns["_build_welcome_email"](**kw)


# ══════════════════════════════════════════════════════════════════════════
#  O e-mail combinado
# ══════════════════════════════════════════════════════════════════════════
def test_quem_travou_ve_o_passo_que_falta_ANTES_de_tudo():
    """🔑 O bloco vem primeiro: é a única coisa que ela precisa fazer agora."""
    subject, html = _monta(name="Victor", falta_cadastro=True,
                           link_cadastro="https://magic")
    corpo = html["body"]
    assert corpo.index("Falta um passo") < corpo.index("Oi"), (
        "o aviso do cadastro ficou depois da saudação — a pessoa que abre no "
        "celular vê 'bem-vindo' e fecha")


def test_o_assunto_diz_que_falta_algo():
    """🪤 Assunto e preheader são o que ela lê antes de abrir. 'Bem-vindo'
    faz o e-mail que destrava a conta parecer cartão de visita."""
    subject, html = _monta(name="", falta_cadastro=True, link_cadastro="x")
    assert "Falta um passo" in subject
    assert "menos de um minuto" in html["preheader"]


def test_o_link_de_um_clique_vai_no_botao_E_no_bloco():
    subject, html = _monta(name="", falta_cadastro=True,
                           link_cadastro="https://magic-link")
    assert "https://magic-link" in html["body"]
    assert html["url"] == "https://magic-link"


def test_sem_link_o_email_ainda_serve():
    """🪤 `_generate_magic_link` pode falhar. O e-mail não pode virar um
    botão quebrado — cai no cadastro.html, que resolve com um login a mais."""
    subject, html = _monta(name="", falta_cadastro=True, link_cadastro="")
    assert html["url"] == "https://ai.arq.br/cadastro.html"
    assert "Falta um passo" in html["body"]


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE: o welcome normal não pode ter mudado
# ══════════════════════════════════════════════════════════════════════════
def test_quem_completou_o_cadastro_recebe_o_welcome_de_sempre():
    subject, html = _monta(name="Ana")
    assert subject == "Bem-vindo — seu projeto vira planilha medida"
    assert html["titulo"] == "Bem-vindo ao AI.arq"
    assert html["url"] == "https://ai.arq.br/dashboard.html"
    assert "Falta um passo" not in html["body"]


def test_o_conteudo_do_produto_continua_nos_dois():
    """O combinado não pode virar só um lembrete seco: quem travou também
    nunca viu o que o produto faz."""
    _, com = _monta(name="", falta_cadastro=True, link_cadastro="x")
    _, sem = _monta(name="")
    for marca in ("Como funciona", "Nosso compromisso", "beta"):
        assert marca in com["body"], "sumiu %r da versão combinada" % marca
        assert marca in sem["body"]


# ══════════════════════════════════════════════════════════════════════════
#  A esteira: um e-mail só, e o antigo não chega atrasado por cima
# ══════════════════════════════════════════════════════════════════════════
def test_sem_perfil_dispara_o_combinado():
    corpo = corpo_de("emails_automaticos_tick") if False else fonte("main.py")
    assert '"boas_vindas_cadastro" if not tem_perfil else "boas_vindas"' in corpo, (
        "a esteira voltou a mandar o welcome puro pra quem não tem perfil")


def test_o_nudge_nao_repete_o_recado_do_combinado():
    """🪤 Sem esta trava, quem recebeu o combinado leva o MESMO recado de novo
    7 dias depois — e o 2º chega com cara de cobrança.

    🪤 A 1ª versão deste teste passou com a trava REMOVIDA: eu escrevi um
    comentário acima do `elif` citando a própria condição, e o teste leu o
    comentário. Terceira variação do mesmo tropeço hoje — guarda que lê a
    explicação em vez do código."""
    corpo = fonte("main.py")
    so_codigo = chr(10).join(l for l in corpo.splitlines()
                             if not l.strip().startswith("#"))
    assert "email not in emails_com_welcome_cadastro" in so_codigo, (
        "o nudge voltou a poder chegar depois do combinado, repetindo o "
        "mesmo recado uma semana atrasado")


def test_a_dedupe_do_welcome_conhece_os_dois_tipos():
    """🚨 Se a lista de 'já recebeu boas-vindas' não incluir o combinado, a
    pessoa leva um welcome DE NOVO — o bug de 24/08 voltando por outra porta."""
    corpo = fonte("main.py")
    assert '"kind": "in.(boas_vindas,boas_vindas_cadastro)"' in corpo


@pytest.mark.parametrize("kind", ["boas_vindas", "boas_vindas_cadastro"])
def test_cada_tipo_e_registrado_com_o_proprio_nome(kind):
    """Registrar os dois como 'boas_vindas' apagaria a diferença no log — e
    sem ela não dá pra medir se o combinado converte melhor."""
    corpo = corpo_de("_send_welcome_email")
    assert kind in corpo
