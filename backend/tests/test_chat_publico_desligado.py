# -*- coding: utf-8 -*-
"""O chat público do site está DESLIGADO — e não volta sem querer.

🩸 27/09/2026 — O chat público (widget de dúvidas, sem login) saiu das páginas em 21/07 (0 lead) e só
tinha sobrado no blog, trocado pelo botão de WhatsApp em 27/09 (9badc0e). O Pedro: "pode apagar o chat
velho". Sem página nenhuma chamando, as duas rotas do servidor eram só porta aberta: /api/public/chat
chamava o modelo a cada mensagem (custo de IA pra qualquer robô que achasse o endereço) e
/api/public/chat/lead gravava nome e e-mail com service_role.

Agora o arquivo do widget não existe e as duas rotas respondem 410 sem chamar modelo nem banco.
O guarda pergunta ao APP (TestClient), não ao fonte: dublês que EXPLODEM se alguém tentar falar com
o modelo ou com o Supabase — a resposta tem que ser 410 sem nenhum deles disparar.
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _cliente(monkeypatch):
    import llm_retry
    import main as _m
    chamadas = []

    def _proibido(*a, **k):
        chamadas.append("chamou")
        raise AssertionError("o chat desligado chamou o modelo ou o banco")
    falso = types.ModuleType("anthropic")
    falso.Anthropic = _proibido
    monkeypatch.setitem(sys.modules, "anthropic", falso)
    for nome in ("call_with_retry", "call_with_retry_stream"):
        if hasattr(llm_retry, nome):
            monkeypatch.setattr(llm_retry, nome, _proibido)
    monkeypatch.setattr(_m.urllib.request, "urlopen", _proibido)
    from fastapi.testclient import TestClient
    return TestClient(_m.app, raise_server_exceptions=False), chamadas


def test_o_chat_publico_responde_410_sem_chamar_o_modelo(monkeypatch):
    cli, chamadas = _cliente(monkeypatch)
    r = cli.post("/api/public/chat", json={"message": "quanto custa?", "history": []})
    assert r.status_code == 410, (r.status_code, r.text[:200])
    assert r.json().get("error") == "chat_desligado", r.text[:200]
    assert not chamadas, "o chat desligado chamou o modelo ou o banco"


def test_a_captura_de_lead_responde_410_sem_gravar(monkeypatch):
    cli, chamadas = _cliente(monkeypatch)
    r = cli.post("/api/public/chat/lead", json={"name": "Visitante", "email": "visitante@exemplo.local"})
    assert r.status_code == 410, (r.status_code, r.text[:200])
    assert not chamadas, "a rota de lead desligada tentou gravar"


def test_o_arquivo_do_chat_saiu_do_site():
    assert not os.path.exists(os.path.join(RAIZ, "chat-widget.js")), "o chat-widget.js voltou pro site"


def test_CONTROLE_os_dubles_mordem(monkeypatch):
    """🧪 Se os dublês não disparassem, o 410 passaria verde mesmo com o modelo sendo chamado."""
    import llm_retry
    import main as _m
    _cli, chamadas = _cliente(monkeypatch)
    for chamar in (lambda: _m.urllib.request.urlopen("https://exemplo.local"),
                   lambda: sys.modules["anthropic"].Anthropic(),
                   lambda: llm_retry.call_with_retry()):
        try:
            chamar()
        except AssertionError:
            pass
    assert chamadas == ["chamou"] * 3, chamadas
