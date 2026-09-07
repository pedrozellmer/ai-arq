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


@pytest.fixture
def smtp(monkeypatch):
    """Captura tudo que sairia pelo SMTP; nada vai pra rede nem pro banco."""
    saiu = []

    def _envia(to_email, subject, html_body, text_body="", log_kind="email"):
        saiu.append({"para": to_email, "assunto": subject, "html": html_body,
                     "kind": log_kind})
        return True
    monkeypatch.setattr(main, "_send_email_smtp", _envia)
    monkeypatch.setattr(main, "_email_auto_registrar", lambda *a, **k: None)
    return saiu


def test_existe_um_email_proprio_pro_merge(smtp):
    """Não basta a função existir com o nome certo: ela tem que MANDAR.

    🧪 Controle negativo junto: pai sem e-mail não dispara nada."""
    ok = main._email_leitura_combinada(PAI, {"warnings": FILHO_AVISOS},
                                       "mg634d18", ANTES, DEPOIS)
    assert ok is True, "o e-mail da versão combinada não foi enviado"
    assert len(smtp) == 1, "esperava 1 e-mail, saíram %d" % len(smtp)
    assert smtp[0]["para"] == PAI["user_email"]
    assert smtp[0]["kind"] == "leitura_combinada", (
        "o log do envio não distingue o e-mail do merge: %r" % smtp[0]["kind"])

    sem_email = dict(PAI, user_email="")
    assert main._email_leitura_combinada(sem_email, {}, "mg1", ANTES, DEPOIS) is False
    assert len(smtp) == 1, "mandou e-mail pra um projeto sem dono"
