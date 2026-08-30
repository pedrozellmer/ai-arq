# -*- coding: utf-8 -*-
"""O rate-limit tem que pegar o IP REAL do cliente, não o egress do proxy (30/08).

🔒 A auditoria floodou o /api/contact: 20 POSTs anônimos passaram porque
_client_ip usava x-forwarded-for[-1] — atrás de Cloudflare→Render esse é o IP
de egress ROTATIVO do proxy, diferente a cada requisição, então o bucket por IP
nunca fechava. CF-Connecting-IP carrega o IP real (é o mesmo header que o
/api/admin/marcar-meu-ip já usa). Cada lead cria linha no banco + dispara e-mail
ao Pedro: flood barato de inbox/DB.
"""
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import main  # noqa: E402


class _Req:
    def __init__(self, headers):
        self.headers = headers
        self.client = None


def test_cf_connecting_ip_vence_o_xff_rotativo():
    # mesmo cliente (CF diz 200.1.1.1), mas o egress do proxy muda toda vez
    a = _Req({"cf-connecting-ip": "200.1.1.1", "x-forwarded-for": "200.1.1.1, 10.0.0.5"})
    b = _Req({"cf-connecting-ip": "200.1.1.1", "x-forwarded-for": "200.1.1.1, 10.0.0.9"})
    assert main._client_ip(a) == "200.1.1.1"
    assert main._client_ip(b) == "200.1.1.1", "egress rotativo do proxy furou o IP real"


def test_o_flood_do_mesmo_cliente_FECHA(monkeypatch):
    """O caso da auditoria: mesmo atacante, XFF mudando, tem que bater no teto."""
    monkeypatch.setattr(main, "_RATE_BUCKETS", {})
    ok = 0
    for i in range(20):
        r = _Req({"cf-connecting-ip": "203.0.113.7",
                  "x-forwarded-for": f"203.0.113.7, 10.0.0.{i}"})  # egress muda
        if main._rate_limit_ok("contact", r, limit=8, window_s=600):
            ok += 1
    assert ok == 8, f"deixou passar {ok} (era pra fechar em 8) — flood ainda aberto"


def test_CONTROLE_clientes_diferentes_nao_se_atrapalham(monkeypatch):
    """🧪 Sem isto, um _client_ip que devolvesse constante 'x' também passaria
    no teste acima — e barraria clientes legítimos entre si."""
    monkeypatch.setattr(main, "_RATE_BUCKETS", {})
    passou = 0
    for i in range(12):  # 12 clientes distintos, 1 request cada
        r = _Req({"cf-connecting-ip": f"198.51.100.{i}"})
        if main._rate_limit_ok("contact", r, limit=8, window_s=600):
            passou += 1
    assert passou == 12, "clientes distintos estão colidindo no mesmo bucket"


def test_sem_cloudflare_cai_pro_xff_primeiro(monkeypatch):
    """Fora do CF (dev/local), usa o 1º da cadeia XFF (cliente), não o último."""
    r = _Req({"x-forwarded-for": "203.0.113.9, 10.0.0.1, 10.0.0.2"})
    assert main._client_ip(r) == "203.0.113.9"
