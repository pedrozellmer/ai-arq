# -*- coding: utf-8 -*-
"""O e-mail da versão COMBINADA tem que SAIR, não só existir com o nome certo.

🪤 06/09/2026 — o guarda antigo (`test_existe_um_email_proprio_pro_merge`, em
test_merge_email_cliente.py) media a string `def _email_leitura_combinada` no
fonte do main.py. Um `return False` na 1ª linha do corpo deixava a string
intacta e o cliente sem e-mail nenhum. Aqui o SMTP é de mentira e o guarda
conta o que chegou nele.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import main  # noqa: E402

PAI = {"job_id": "aa11bb22", "user_id": "u-cliente-01",
       "user_email": "cliente-01@example.com", "user_name": "Cliente Um",
       "project_name": "Obra do cliente-01"}
FILHO_AVISOS = ["Prancha 4366-EL-E veio da leitura ORIGINAL",
                "Prancha 3073-AQ-E veio da RELEITURA"]
ANTES = {"itens": 120, "medidos": 49, "pranchas": 7}
DEPOIS = {"itens": 138, "medidos": 77, "pranchas": 9}


class _Bancada(object):
    """O que sairia pelo SMTP e o que seria GRAVADO no `email_auto_log`."""

    def __init__(self):
        self.saiu = []          # e-mails entregues ao SMTP
        self.registrou = []     # (email, kind, ref) gravados no teto semanal
        self.smtp_responde = True

    def __len__(self):
        return len(self.saiu)

    def __getitem__(self, i):
        return self.saiu[i]


@pytest.fixture
def smtp(monkeypatch):
    """Captura tudo que sairia pelo SMTP **e o registro do teto semanal**.

    🪤 07/09/2026 — a versão anterior desta fixture desligava o
    `_email_auto_registrar` com um `lambda: None` e NUNCA conferia que ele foi
    chamado. O e-mail do merge podia sair sem alimentar o `email_auto_log`, que
    é a tabela de onde o teto de "1 automático por pessoa por semana" é lido —
    e o `emails_auto_tick` da hora seguinte mandaria outro automático pra mesma
    pessoa. É o defeito que main.py:25058 diz já ter acontecido ("o conserto de
    29/08 fechou só metade da porta", caso cliente-20 com 3 e-mails num dia).
    """
    b = _Bancada()

    def _envia(to_email, subject, html_body, text_body="", log_kind="email"):
        b.saiu.append({"para": to_email, "assunto": subject, "html": html_body,
                       "kind": log_kind})
        return b.smtp_responde

    def _registra(email, kind, ref=""):
        b.registrou.append((email, kind, ref))

    monkeypatch.setattr(main, "_send_email_smtp", _envia)
    monkeypatch.setattr(main, "_email_auto_registrar", _registra)
    return b


def test_existe_um_email_proprio_pro_merge(smtp):
    """Não basta a função existir com o nome certo: ela tem que MANDAR.

    🧪 Controle negativo junto: pai sem e-mail não dispara nada."""
    ok = main._email_leitura_combinada(PAI, {"warnings": FILHO_AVISOS},
                                       "mg634d18", ANTES, DEPOIS)
    assert ok is True, "o e-mail da versão combinada não foi enviado"
    assert len(smtp.saiu) == 1, "esperava 1 e-mail, saíram %d" % len(smtp.saiu)
    assert smtp[0]["para"] == PAI["user_email"]
    assert smtp[0]["kind"] == "leitura_combinada", (
        "o log do envio não distingue o e-mail do merge: %r" % smtp[0]["kind"])

    sem_email = dict(PAI, user_email="")
    assert main._email_leitura_combinada(sem_email, {}, "mg1", ANTES, DEPOIS) is False
    assert len(smtp.saiu) == 1, "mandou e-mail pra um projeto sem dono"
    assert smtp.registrou == [(PAI["user_email"], "leitura_combinada", "mg634d18")], (
        "o envio não alimentou o `email_auto_log` (registrado: %r) — o teto de "
        "'1 automático por pessoa por semana' é LIDO dessa tabela, então o "
        "`emails_auto_tick` da hora seguinte manda outro automático pra mesma "
        "pessoa. É o caso cliente-20 (3 e-mails num dia) de volta."
        % (smtp.registrou,))


def test_o_email_do_merge_TEM_CONTEUDO_e_nao_so_existe(smtp):
    """🪤 07/09/2026 — o guarda antigo contava o e-mail e olhava o destinatário.
    Um builder que devolvesse `("", "")` mandaria um e-mail EM BRANCO e passava.

    Aqui o assunto e o corpo são cobrados por CONTEÚDO: o nome do projeto, o
    ganho real de medição, o rodapé de LGPD e o link que leva à versão nova."""
    main._email_leitura_combinada(PAI, {"warnings": FILHO_AVISOS},
                                  "mg634d18", ANTES, DEPOIS)
    assunto, html = smtp[0]["assunto"], smtp[0]["html"]

    assert PAI["project_name"] in assunto, (
        "o assunto não diz de qual projeto se trata: %r" % assunto)
    assert "&" not in assunto, (
        "entidade HTML no assunto — o cliente lê o código na caixa de "
        "entrada: %r" % assunto)
    assert len(html) > 1500, (
        "o corpo do e-mail veio com %d caracteres — e-mail em branco sai como "
        "sucesso" % len(html))
    # o ganho REAL, em medição do CAD (49 → 77), é a razão de o e-mail existir
    assert str(ANTES["medidos"]) in html and str(DEPOIS["medidos"]) in html, (
        "o e-mail não mostra o ganho de medição %d → %d"
        % (ANTES["medidos"], DEPOIS["medidos"]))
    assert "Nenhuma prancha entrou duas vezes" in html, (
        "sumiu a resposta pra pergunta que todo orçamentista faz ao ouvir "
        "'juntamos duas planilhas'")
    # 🚨 regra dura nº6: o rodapé de LGPD tem que ir junto (o e-mail cru, sem
    # `_email_wrap`, saiu uma vez sem ele)
    assert "privacidade" in html and "remover seus dados" in html, (
        "o e-mail saiu FORA da moldura da marca — sem o rodapé de LGPD")
    assert "job_id=mg634d18" in html, (
        "o botão não leva à versão combinada que o e-mail está anunciando")


def test_SMTP_que_falha_NAO_gasta_o_teto_semanal_do_cliente(smtp):
    """O outro ramo do `if _ok:`. Se o e-mail não saiu, gravar no
    `email_auto_log` queimaria a cota semanal da pessoa por um e-mail que ela
    nunca recebeu — e o aviso da versão combinada morreria calado."""
    smtp.smtp_responde = False
    ok = main._email_leitura_combinada(PAI, {"warnings": FILHO_AVISOS},
                                       "mg634d18", ANTES, DEPOIS)
    assert ok is False, "envio falhou e a função disse que deu certo"
    assert smtp.registrou == [], (
        "o SMTP falhou e mesmo assim o teto semanal foi consumido: %r"
        % (smtp.registrou,))
