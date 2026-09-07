# -*- coding: utf-8 -*-
"""Campanha só vai pra quem aceitou; serviço vai pra base toda.

🩸 07/09/2026 — a newsletter mandava para quem tinha marcado **"não quero
receber"** no cadastro. Medido na base: de 102 perfis, **49 marcaram `false`**
em `accept_marketing` — 48% — e recebiam assim mesmo.

A causa: `_newsletter_recipients` descontava só o `newsletter_optout` (o
descadastro de 1 clique) e **nunca lia o `accept_marketing`**. São dois
consentimentos diferentes, e respeitar um enquanto se ignora o outro é
respeitar nenhum. Achado nº52 da auditoria de 06/09, classificado CRÍTICO.

🔑 A SEPARAÇÃO QUE RESOLVE, e por que ela não é rodeio:
  · **serviço**  — fala do que a pessoa JÁ USA (função nova, manutenção,
    mudança de comportamento). Mesma categoria de "sua planilha está pronta",
    que sempre saiu pra todos. Não vende nada.
  · **campanha** — promoção, oferta, newsletter. Depende do aceite.

A diferença é de CONTEÚDO, não de rótulo: serviço fala do que ela tem,
campanha do que ela poderia comprar.

🪤 Pedro perguntou se não valia tirar o aceite do termo. Não vale: apagar o
campo apaga o REGISTRO, não a manifestação — as 49 continuam tendo marcado
"não". E hoje há consentimento documentado de 53; sem o campo, o envio passa a
não ter base nenhuma. Troca cobertura parcial por cobertura zero.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
_RAIZ = os.path.dirname(_BACKEND)
sys.path.insert(0, _BACKEND)

import main  # noqa: E402

REQ = type("R", (), {"headers": {}})()

#: A base de mentira: 2 aceitaram, 2 recusaram, 1 nunca respondeu.
_PERFIS = [
    {"email": "aceitou1@example.com", "accept_marketing": True},
    {"email": "aceitou2@example.com", "accept_marketing": True},
    {"email": "recusou1@example.com", "accept_marketing": False},
    {"email": "recusou2@example.com", "accept_marketing": False},
    {"email": "nunca@example.com", "accept_marketing": None},
]
_PROJETOS = [{"user_email": p["email"], "user_name": "Cliente"} for p in _PERFIS]


@pytest.fixture
def base(monkeypatch):
    """Banco de mentira: `projects`, `newsletter_optout` e `profiles`."""
    import json as _js
    import urllib.request as _ur

    class _Resp:
        def __init__(self, d):
            self._b = _js.dumps(d).encode("utf-8")

        def read(self):
            return self._b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    estado = {"optout": [], "perfis": list(_PERFIS), "erro_perfis": False}

    def _urlopen(req, timeout=None):
        url = getattr(req, "full_url", str(req))
        if "profiles" in url:
            if estado["erro_perfis"]:
                raise RuntimeError("banco fora")
            return _Resp(estado["perfis"])
        if "newsletter_optout" in url:
            return _Resp([{"email": e} for e in estado["optout"]])
        if "projects" in url:
            return _Resp(_PROJETOS)
        return _Resp([])

    monkeypatch.setattr(_ur, "urlopen", _urlopen)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    return estado


def _emails(lista):
    return sorted(e for e, _n in lista)


# ═══════════════════════════════════════════════════════════════════════════
#  Quem recebe o quê
# ═══════════════════════════════════════════════════════════════════════════

def test_CAMPANHA_nao_vai_pra_quem_recusou(base):
    """🚨 O invariante. Quem marcou `false` não recebe promoção — nem quem
    deixou em branco: aceite é ato positivo, ausência não é consentimento."""
    saiu = _emails(main._newsletter_recipients("campanha"))
    assert saiu == ["aceitou1@example.com", "aceitou2@example.com"], saiu


def test_SERVICO_vai_pra_base_toda(base):
    """Comunicação sobre o que a pessoa já usa não depende do aceite de
    marketing — é a mesma categoria de 'sua planilha está pronta'."""
    saiu = _emails(main._newsletter_recipients("servico"))
    assert len(saiu) == 5, saiu
    assert "recusou1@example.com" in saiu


def test_o_descadastro_de_1_CLIQUE_vale_nos_DOIS(base):
    """🔑 São dois consentimentos e os dois mandam. Quem clicou em 'sair da
    lista' sai de tudo — inclusive do comunicado de serviço."""
    base["optout"] = ["aceitou1@example.com", "recusou1@example.com"]
    assert "aceitou1@example.com" not in _emails(main._newsletter_recipients("campanha"))
    assert "aceitou1@example.com" not in _emails(main._newsletter_recipients("servico"))
    assert "recusou1@example.com" not in _emails(main._newsletter_recipients("servico"))


def test_o_DEFAULT_e_o_mais_restrito(base):
    """🪤 Quem escrever código novo e esquecer o argumento tem que mandar pra
    MENOS gente, não pra mais. Erro de omissão não pode virar envio indevido."""
    assert _emails(main._newsletter_recipients()) == \
        _emails(main._newsletter_recipients("campanha"))


def test_se_nao_der_pra_LER_o_aceite_a_campanha_NAO_sai(base):
    """🪤 FALHA FECHADA, ao contrário da lista de supressão (que falha aberta).
    Mandar promoção pra quem recusou é dano que não se desfaz; deixar de mandar
    é adiamento."""
    base["erro_perfis"] = True
    assert main._newsletter_recipients("campanha") == []
    # e o serviço continua saindo: ele não depende desse campo
    assert len(main._newsletter_recipients("servico")) == 5


# ═══════════════════════════════════════════════════════════════════════════
#  A rota
# ═══════════════════════════════════════════════════════════════════════════

def test_a_rota_RECUSA_tipo_desconhecido(base, monkeypatch):
    """Sem isto, um erro de digitação no front cairia num ramo qualquer."""
    import asyncio

    monkeypatch.setattr(main, "_require_admin", lambda r: {"email": main.ADMIN_EMAIL})

    class _Req:
        headers = {}

        async def json(self):
            return {"tipo": "promoçao"}          # errado de propósito

    # 🪤 `asyncio.run`, não `get_event_loop().run_until_complete`: o segundo
    # passou isolado e QUEBROU na bancada inteira — algum teste anterior deixa
    # o laço num estado que ele não sobrevive. Falha por ORDEM é das piores de
    # diagnosticar, porque some quando se roda o arquivo sozinho pra investigar.
    with pytest.raises(main.HTTPException) as ex:
        asyncio.run(main.admin_newsletter_send(_Req()))
    assert ex.value.status_code == 400


def test_a_previa_diz_QUANTOS_antes_de_apertar(base, monkeypatch):
    """🔑 A conferência é o passo do meio. Apertar um botão que manda e-mail
    pra dezenas de pessoas sem ver o número antes é como o produto errava."""
    monkeypatch.setattr(main, "_require_admin", lambda r: {"email": main.ADMIN_EMAIL})
    d = main.admin_newsletter_publico(REQ)
    assert d["servico"] == 5 and d["campanha"] == 2
    assert d["recusaram_marketing"] == 3, d
    assert "servi" in d["explicacao"].lower()


# ═══════════════════════════════════════════════════════════════════════════
#  🧪 Controles
# ═══════════════════════════════════════════════════════════════════════════

def test_CONTROLE_sem_o_filtro_os_dois_seriam_IGUAIS(base, monkeypatch):
    """Prova que o filtro é o que separa os dois — e não outra coisa no
    caminho. Se `_so_quem_aceitou_marketing` virar identidade, campanha volta a
    alcançar quem recusou, e é isso que este controle reproduz."""
    monkeypatch.setattr(main, "_so_quem_aceitou_marketing", lambda d: d)
    assert _emails(main._newsletter_recipients("campanha")) == \
        _emails(main._newsletter_recipients("servico"))


def test_CONTROLE_a_TELA_do_admin_oferece_os_dois_botoes():
    """🪤 Arquivo certo ≠ tela certa. A separação no backend não serve de nada
    se o admin continuar com um botão só de 'enviar pra todos'."""
    import io
    admin = io.open(os.path.join(_RAIZ, "admin.html"), encoding="utf-8").read()
    assert "sendNewsletter(false, 'servico')" in admin, (
        "sumiu o botão de comunicado de serviço")
    assert "sendNewsletter(false, 'campanha')" in admin, (
        "sumiu o botão de campanha")
    assert "sendNewsletter(false)" not in admin.replace("sendNewsletter(false, ", ""), (
        "voltou o botão único 'enviar pra lista (todos)' — era ele que mandava "
        "promoção pra quem recusou")
    assert "newsletter/publico" in admin, (
        "a tela parou de pedir a prévia — o número some da confirmação")
