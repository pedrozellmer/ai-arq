# -*- coding: utf-8 -*-
"""Lista de supressão de e-mail: quem devolve tudo não recebe NADA — e a trava mora num lugar só.

05/09/2026, Pedro: *"tem vários e-mails de usuário que ficam voltando
recorrentemente, vamos identificar isso e tirar eles de qq envio?"* Medido no
Gmail dele (60 dias): 2 endereços, todas as mensagens devolvidas por "caixa de
entrada cheia" (7 e 3). Cada devolução pesa na reputação do remetente.

O desenho:
  • tabela `email_suprimidos` (bastidor, só service_role); `liberado_em` NULL = suprimido;
  • a trava é `_send_email_smtp` — a ÚNICA porta de saída de e-mail da casa (transacional,
    esteira automática, newsletter, teste do admin: tudo passa por ela);
  • falha ABERTA: se a lista não puder ser lida, o e-mail sai (mandar pra caixa cheia é
    mal menor que calar todo e-mail da casa) e fica o rastro no error_log;
  • cache de 5 min (um e-mail não pode custar uma leitura no banco) e UM log por
    (dia, endereço, tipo) — a esteira horária tentaria 24× por dia;
  • contas internas (Pedro/aliases) nunca são suprimidas, nem se alguém puser na lista.
🧪 Controles: endereço fora da lista segue o caminho normal; lista ilegível não bloqueia;
o guarda de forma cobra a trava ANTES de olhar o SMTP.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main  # noqa: E402
from _corpo import corpo_de  # noqa: E402

REQ = type("R", (), {"headers": {}})()


class _Servico:
    def __init__(self, resp):
        self.resp = resp
        self.chamadas = []

    def __call__(self, method, path, body=None, params=None, prefer=None, timeout=15):
        self.chamadas.append({"m": method, "path": path, "body": body, "prefer": prefer})
        return self.resp


@pytest.fixture
def limpo(monkeypatch):
    """Cache zerado e logs capturados."""
    monkeypatch.setattr(main, "_SUPRIMIDOS_CACHE", {"em": 0.0, "mapa": None})
    monkeypatch.setattr(main, "_SUPRIMIDO_AVISADO", set())
    logs = []
    monkeypatch.setattr(main, "_log_error", lambda stage, msg, *a, **k: logs.append((stage, msg, k.get("severity"))))
    return logs


LISTA = [{"email": "cliente2@example.com", "motivo": "7 devoluções caixa cheia", "liberado_em": None},
         {"email": "cliente5@example.com", "motivo": "3 devoluções caixa cheia", "liberado_em": None}]


# ── a consulta e o cache ───────────────────────────────────────────────────
def test_suprimido_devolve_o_motivo_sem_ligar_pra_caixa(monkeypatch, limpo):
    svc = _Servico((200, LISTA))
    monkeypatch.setattr(main, "_supa_rest_service", svc)
    assert main._email_suprimido("cliente2@example.com") == "7 devoluções caixa cheia"
    assert main._email_suprimido("  cliente5@example.com ") == "3 devoluções caixa cheia"
    assert main._email_suprimido("william@exemplo.com") is None
    assert main._email_suprimido("") is None and main._email_suprimido(None) is None
    assert len(svc.chamadas) == 1, "3 consultas, 1 leitura — o cache segura"
    assert "liberado_em=is.null" in svc.chamadas[0]["path"], "quem foi liberado volta a receber"


def test_cache_vence_em_5_min_e_force_reconsulta(monkeypatch, limpo):
    svc = _Servico((200, LISTA))
    monkeypatch.setattr(main, "_supa_rest_service", svc)
    main._email_suprimido("a@b.com")
    main._SUPRIMIDOS_CACHE["em"] -= main._SUPRIMIDOS_TTL_S + 1
    main._email_suprimido("a@b.com")
    assert len(svc.chamadas) == 2
    main._suprimidos(force=True)
    assert len(svc.chamadas) == 3


def test_lista_ilegivel_FALHA_ABERTA_com_rastro_e_sem_martelar_o_banco(monkeypatch, limpo):
    svc = _Servico((500, None))
    monkeypatch.setattr(main, "_supa_rest_service", svc)
    assert main._email_suprimido("cliente2@example.com") is None, "sem lista legível, o e-mail SAI (mal menor)"
    main._email_suprimido("cliente2@example.com")
    assert len(svc.chamadas) == 1, "falha também respeita o cache — senão cada e-mail bate no banco caído"
    assert any(s == "email:supressao-ilegivel" for s, _m, _sev in limpo)


def test_lista_ilegivel_mantem_o_ultimo_mapa_bom(monkeypatch, limpo):
    svc = _Servico((200, LISTA))
    monkeypatch.setattr(main, "_supa_rest_service", svc)
    main._email_suprimido("x@y.com")
    main._SUPRIMIDOS_CACHE["em"] = 0.0
    svc.resp = (0, None)
    assert main._email_suprimido("cliente2@example.com") == "7 devoluções caixa cheia", "a lista antiga vale mais que nada"


# ── a trava em _send_email_smtp ────────────────────────────────────────────
def _sem_smtp(monkeypatch):
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.delenv(k, raising=False)


def test_endereco_suprimido_NAO_sai_e_fica_o_rastro(monkeypatch, limpo):
    monkeypatch.setattr(main, "_email_suprimido", lambda e: "7 devoluções caixa cheia")
    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: (_ for _ in ()).throw(AssertionError("tentou falar com o SMTP")))
    monkeypatch.setenv("SMTP_HOST", "smtp.x"); monkeypatch.setenv("SMTP_USER", "u"); monkeypatch.setenv("SMTP_PASSWORD", "p")
    ok = main._send_email_smtp("cliente2@example.com", "Assunto", "<b>x</b>", log_kind="proximo_projeto")
    assert ok is False
    sup = [l for l in limpo if l[0] == "email:suprimido"]
    assert len(sup) == 1 and "proximo_projeto" in sup[0][1] and "cliente2@example.com" in sup[0][1] and "caixa cheia" in sup[0][1]


def test_um_log_por_dia_por_endereco_e_tipo(monkeypatch, limpo):
    monkeypatch.setattr(main, "_email_suprimido", lambda e: "caixa cheia")
    for _ in range(5):
        main._send_email_smtp("cliente2@example.com", "A", "b", log_kind="proximo_projeto")
    main._send_email_smtp("cliente2@example.com", "A", "b", log_kind="newsletter")
    assert len([l for l in limpo if l[0] == "email:suprimido"]) == 2, "24 tentativas/dia da esteira não podem virar 24 logs"


def test_CONTROLE_endereco_fora_da_lista_segue_o_caminho_normal(monkeypatch, limpo):
    monkeypatch.setattr(main, "_email_suprimido", lambda e: None)
    _sem_smtp(monkeypatch)
    ok = main._send_email_smtp("william@exemplo.com", "A", "b", log_kind="planilha_pronta")
    assert ok is False, "sem SMTP configurado ele não sai — mas pelo motivo de sempre"
    assert not [l for l in limpo if l[0] == "email:suprimido"]


def test_conta_interna_nunca_e_suprimida(monkeypatch, limpo):
    chamou = []
    monkeypatch.setattr(main, "_email_suprimido", lambda e: chamou.append(e) or "na lista por engano")
    _sem_smtp(monkeypatch)
    main._send_email_smtp(main.ADMIN_EMAIL, "A", "b", log_kind="email")
    assert not chamou, "interno não consulta a lista — alerta pro Pedro não pode ser calado por engano"
    assert not [l for l in limpo if l[0] == "email:suprimido"]


def test_a_trava_vem_ANTES_de_olhar_o_smtp():
    c = corpo_de("_send_email_smtp")
    i = c.find("_email_suprimido(")
    j = c.find('os.getenv("SMTP_HOST"')
    assert 0 < i < j, "a supressão tem que ser a 1ª coisa — antes do SMTP e de qualquer envio"


# ── as rotas do admin ─────────────────────────────────────────────────────
@pytest.fixture
def admin(monkeypatch, limpo):
    monkeypatch.setattr(main, "_require_admin", lambda request: {"email": main.ADMIN_EMAIL})


def test_suprimir_normaliza_valida_e_grava_com_upsert(monkeypatch, admin):
    svc = _Servico((201, None))
    monkeypatch.setattr(main, "_supa_rest_service", svc)
    r = main.admin_email_suprimir(main.SuprimirPayload(email="  Fulano@Exemplo.com ", motivo="devolve tudo", tipo="caixa_cheia", n_devolucoes=2), REQ)
    assert r["status"] == "ok" and r["email"] == "fulano@exemplo.com"
    post = [c for c in svc.chamadas if c["m"] == "POST"][0]
    assert "on_conflict=email" in post["path"] and "merge-duplicates" in (post["prefer"] or "")
    assert post["body"]["email"] == "fulano@exemplo.com" and post["body"]["liberado_em"] is None, "suprimir de novo quem foi liberado volta a bloquear"
    assert post["body"]["n_devolucoes"] == 2 and post["body"]["tipo"] == "caixa_cheia"
    assert any(c["m"] == "GET" for c in svc.chamadas), "o cache é renovado na hora — a próxima tentativa já bloqueia"


@pytest.mark.parametrize("ruim", [{"email": "semarroba"}, {"email": "@x.com"}, {"email": "a@b.com", "tipo": "chato"}])
def test_suprimir_recusa_entrada_torta(monkeypatch, admin, ruim):
    monkeypatch.setattr(main, "_supa_rest_service", _Servico((201, None)))
    with pytest.raises(main.HTTPException) as ex:
        main.admin_email_suprimir(main.SuprimirPayload(**ruim), REQ)
    assert ex.value.status_code == 400


def test_liberar_preenche_liberado_em_e_nao_apaga(monkeypatch, admin):
    svc = _Servico((204, None))
    monkeypatch.setattr(main, "_supa_rest_service", svc)
    r = main.admin_email_liberar(main.SuprimirPayload(email="cliente2@example.com"), REQ)
    assert r["status"] == "ok"
    patch = [c for c in svc.chamadas if c["m"] == "PATCH"][0]
    assert "email=eq.cliente2%40example.com" in patch["path"] and patch["body"]["liberado_em"] and patch["body"]["liberado_por"]
    assert not [c for c in svc.chamadas if c["m"] == "DELETE"], "liberar guarda o histórico; nada é apagado"


def test_listar_devolve_ativos_e_falha_e_502_nao_lista_vazia(monkeypatch, admin):
    monkeypatch.setattr(main, "_supa_rest_service", _Servico((200, LISTA + [{"email": "x@y.com", "motivo": "m", "liberado_em": "2026-09-01T00:00:00Z"}])))
    r = main.admin_email_suprimidos(REQ)
    assert r["ativos"] == 2 and len(r["itens"]) == 3
    monkeypatch.setattr(main, "_supa_rest_service", _Servico((500, None)))
    with pytest.raises(main.HTTPException) as ex:
        main.admin_email_suprimidos(REQ)
    assert ex.value.status_code == 502
