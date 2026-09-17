# -*- coding: utf-8 -*-
"""No beta, reprocessar é ilimitado — e a porta não pode estar trancada.

🩸 17/09/2026, Pedro: *"a gente está em beta, é grátis sempre, então não faz
nenhum sentido"*. O site promete beta ilimitado — a própria confirmação do botão
mandava "criar um projeto novo (grátis e ilimitado no beta)" — e a rota, três
linhas depois, devolvia **402 Payment Required** na segunda tentativa.

📏 O que a trava custou, medido em 17/09: **16 projetos de 12 clientes** viam
"você já usou seu reprocesso grátis" **sem nunca terem reprocessado** — o
contador sobe por caminhos que NÃO são o botão (retomada automática depois de
queda, filhote de avaliação). E **6 desses 16 não tinham recebido nada**: 4
fecharam com zero linha medida e 2 deram erro. A porta de conserto estava
trancada exatamente para quem mais precisava dela.

🔑 Cota e anti-abuso são coisas DIFERENTES. A cota contradizia o beta e saiu; o
freio contra laço/robô (6 por 10 min, por projeto) fica — e estes guardas
provam que ele ficou.

🚨 Os guardas da rota a CHAMAM de verdade (TestClient).
"""
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import main  # noqa: E402

_JOB = "job-reproc-01"
_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _Resp(object):
    def __init__(self, payload):
        self._p = payload

    def read(self):
        import json
        return json.dumps(self._p).encode("utf-8")

    def getcode(self):
        return 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture()
def rota(monkeypatch):
    """A rota real, com dono, banco, storage e disparo de motor encenados."""
    from fastapi.testclient import TestClient

    estado = {"disparos": [], "rate_ok": True, "reprocess_count": 3}

    monkeypatch.setattr(main, "_require_project_owner", lambda *a, **k: "dono-1")
    monkeypatch.setattr(main, "_get_user_from_request", lambda *a, **k: None)
    monkeypatch.setattr(main, "_rate_limit_ok", lambda *a, **k: estado["rate_ok"])
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supabase_storage_download_prancha",
                        lambda job, nome, **k: b"%PDF-1.4 fake")
    monkeypatch.setattr(main, "_supabase_insert", lambda *a, **k: True)
    monkeypatch.setattr(main, "_supabase_update", lambda *a, **k: True)
    monkeypatch.setattr(main, "_process_job_throttled",
                        lambda *a, **k: estado["disparos"].append(a))

    def _urlopen(req, *a, **k):
        url = getattr(req, "full_url", "") or str(req)
        if "/storage/v1/object/list/" in url:
            return _Resp([{"name": "prancha.pdf", "metadata": {"size": 12}}])
        return _Resp([{"job_id": _JOB, "user_id": "dono-1", "user_email": "c@e.com",
                       "project_name": "p", "typology": "office",
                       "project_type": "arquitetura", "status": "done",
                       "file_types": {"pdf": 1}, "user_total_area": 0,
                       "user_pe_direito": 0, "user_prazo_meses": 0,
                       "reprocess_count": estado["reprocess_count"]}])

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    return TestClient(main.app, raise_server_exceptions=False), estado


def _post(cliente, tipo=None):
    corpo = {"project_type": tipo} if tipo else {}
    return cliente.post("/api/project/%s/reprocess" % _JOB, json=corpo)


# ── a cota ─────────────────────────────────────────────────────────────────
def test_quem_ja_reprocessou_TRES_vezes_continua_podendo(rota):
    """O caso dos 12 clientes: contador alto, e a porta tem que abrir."""
    cliente, estado = rota
    r = _post(cliente)
    assert r.status_code != 402, (
        "a trava de cota voltou — o beta promete ilimitado: %s" % r.text[:200])
    assert r.status_code == 200, (r.status_code, r.text[:300])


def test_a_constante_diz_ILIMITADO():
    assert main.REPROCESS_FREE_LIMIT is None, (
        "REPROCESS_FREE_LIMIT deixou de ser None — se a cobrança ligou, o texto "
        "público e a tela precisam mudar JUNTO (regra dura nº7)")


def test_CONTROLE_o_mecanismo_da_cota_continua_funcionando(rota, monkeypatch):
    """🪤 Tirar a cota não pode ser arrancar o mecanismo: quando a cobrança
    ligar, basta pôr um número. Este guarda prova que o 402 volta sozinho."""
    cliente, estado = rota
    monkeypatch.setattr(main, "REPROCESS_FREE_LIMIT", 1)
    r = _post(cliente)
    assert r.status_code == 402, (
        "com limite=1 e contador=3 a rota tinha que recusar: %s" % r.text[:200])
    assert "limite" in r.json().get("detail", "").lower()


# ── o freio que FICA ───────────────────────────────────────────────────────
def test_CONTROLE_o_freio_ANTI_ABUSO_continua_de_pe(rota):
    """Cota saiu; laço/robô não. São coisas diferentes e só uma contradiz o beta."""
    cliente, estado = rota
    estado["rate_ok"] = False
    r = _post(cliente)
    assert r.status_code == 429, (r.status_code, r.text[:200])
    assert estado["disparos"] == [], "gastou IA num pedido que o freio barrou"


def test_o_motor_roda_quando_a_porta_abre(rota):
    cliente, estado = rota
    _post(cliente, tipo="arquitetura")
    assert estado["disparos"], "a porta abriu e o motor não rodou"


# ── o que o cliente lê ─────────────────────────────────────────────────────
def _pagina():
    import io
    return io.open(os.path.join(_RAIZ, "projeto.html"), encoding="utf-8").read()


def test_a_tela_NAO_promete_mais_uma_vez_por_projeto():
    """🚨 Copy pública: a promessa do beta é ilimitada. Texto que diga o
    contrário é promessa quebrada na cara do cliente."""
    src = _pagina()
    for frase in ("1× por projeto", "1 reprocessamento por projeto",
                  "Já reprocessado"):
        assert frase not in src, (
            "a tela ainda promete cota que não existe: %r" % frase)


def test_a_tela_NAO_decide_cota_sozinha():
    """🩸 Era aqui que os 12 clientes ficavam presos: a tela desabilitava o
    botão por `reprocess_count`, um contador que sobe por caminhos que não são
    o botão. Quem decide política é o servidor; a tela mostra a resposta dele."""
    src = _pagina()
    assert "reprocessCount >= 1" not in src, "a tela voltou a decidir a cota"
    assert "res.status === 402" in src, (
        "sumiu o tratamento do 402 — se a cobrança ligar, o cliente fica sem "
        "explicação nenhuma na tela")
