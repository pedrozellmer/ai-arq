# -*- coding: utf-8 -*-
"""Search Console e Bing no tick diário (04/10/2026).

🔎 Pedro: "segue com o Search Console e Bing no tick". O Cloudflare diz de onde chegou a visita; o Search Console e
o Bing dizem por qual busca e em que posição. Credenciais são do Pedro (Render); sem elas o tick diz "sem credencial"
e não grava nada.

Os testes rodam o código de verdade com a rede encenada: o JWT é assinado com uma chave RSA gerada aqui e conferido
com a pública; Google e Bing respondem no formato das documentações (searchAnalytics.query; GetQueryStats e irmãos).
"""
import base64
import io
import json
import os
import sys
import urllib.error
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import busca_organica as bo  # noqa: E402
import main  # noqa: E402
from _jsbancada import funcao_js, motor  # noqa: E402


@pytest.fixture
def sem_credencial(monkeypatch):
    for k in ("GSC_SERVICE_ACCOUNT_JSON", "BING_WEBMASTER_API_KEY", "GSC_SITE"):
        monkeypatch.delenv(k, raising=False)


def _chave_rsa():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                          serialization.NoEncryption()).decode()
    return k, {"client_email": "leitor@projeto-exemplo.iam.gserviceaccount.com", "private_key": pem}


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ─── Google: o JWT da conta de serviço ──────────────────────────────────────────────────────
def test_o_jwt_e_RS256_assinado_pela_chave_da_conta_e_pede_so_leitura():
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    k, cred = _chave_rsa()
    jwt = bo.jwt_da_conta(cred, agora=1000)
    cab, corpo, sig = jwt.split(".")
    assert json.loads(_b64d(cab)) == {"alg": "RS256", "typ": "JWT"}
    c = json.loads(_b64d(corpo))
    assert c == {"iss": cred["client_email"], "scope": "https://www.googleapis.com/auth/webmasters.readonly",
                 "aud": "https://oauth2.googleapis.com/token", "iat": 1000, "exp": 4600}
    # levanta se a assinatura não bater
    k.public_key().verify(_b64d(sig), (cab + "." + corpo).encode(), padding.PKCS1v15(), hashes.SHA256())


def test_credencial_quebrada_diz_o_que_falta_sem_ecoar_o_segredo(monkeypatch):
    monkeypatch.setenv("GSC_SERVICE_ACCOUNT_JSON", '{"private_key": "SEGREDO-PRIVADO" ')
    with pytest.raises(ValueError) as e:
        bo.credencial_google()
    assert "SEGREDO" not in str(e.value) and "JSON" in str(e.value)
    monkeypatch.setenv("GSC_SERVICE_ACCOUNT_JSON", '{"type": "service_account"}')
    with pytest.raises(ValueError) as e:
        bo.credencial_google()
    assert "client_email" in str(e.value)


def test_a_propriedade_e_descoberta_e_o_erro_ensina_o_que_fazer(monkeypatch, sem_credencial):
    monkeypatch.setattr(bo, "_http", lambda *a, **k: {"siteEntry": [
        {"siteUrl": "https://outro-site.exemplo.com/"}, {"siteUrl": "sc-domain:ai.arq.br"}]})
    assert bo.site_google("tok") == "sc-domain:ai.arq.br"
    monkeypatch.setattr(bo, "_http", lambda *a, **k: {"siteEntry": []})
    with pytest.raises(RuntimeError) as e:
        bo.site_google("tok")
    assert "Usuários e permissões" in str(e.value)
    monkeypatch.setenv("GSC_SITE", "https://ai.arq.br/")
    assert bo.site_google("tok") == "https://ai.arq.br/"


def _google_encenado(monkeypatch, total=True):
    pedidos = []

    def _http(metodo, url, corpo=None, cabecalhos=None, **k):
        pedidos.append((metodo, url, corpo, cabecalhos))
        dims = (corpo or {}).get("dimensions") or []
        if not dims:
            return {"rows": [{"clicks": 7, "impressions": 300, "ctr": 0.02, "position": 12.4}]} if total else {}
        if dims == ["query"]:
            return {"rows": [{"keys": ["quantitativo de obra"], "clicks": 4, "impressions": 100, "position": 8.0},
                             {"keys": ["planilha dwg"], "clicks": 3, "impressions": 200, "position": 15.0}]}
        return {"rows": [{"keys": ["https://ai.arq.br/faq.html"], "clicks": 5, "impressions": 150, "position": 9.0},
                         {"keys": ["http://www.ai.arq.br/faq.html"], "clicks": 1, "impressions": 50, "position": 13.0}]}
    monkeypatch.setattr(bo, "_http", _http)
    return pedidos


def test_o_dia_do_google_vem_inteiro_e_a_pagina_vira_caminho(monkeypatch):
    pedidos = _google_encenado(monkeypatch)
    ls = bo.linhas_google("tok", "sc-domain:ai.arq.br", date(2026, 10, 1))
    assert all(p[3] == {"Authorization": "Bearer tok"} for p in pedidos)
    assert pedidos[0][1].endswith("/sites/sc-domain%3Aai.arq.br/searchAnalytics/query")
    assert {p[2]["startDate"] for p in pedidos} == {"2026-10-01"} == {p[2]["endDate"] for p in pedidos}
    tot = [l for l in ls if l["tipo"] == "total"]
    assert tot == [{"fonte": "google", "dia": "2026-10-01", "periodo": "dia", "tipo": "total", "chave": "",
                    "cliques": 7, "impressoes": 300, "posicao": 12.4}]
    pags = bo.juntar([l for l in ls if l["tipo"] == "pagina"])
    assert pags == [{"fonte": "google", "dia": "2026-10-01", "periodo": "dia", "tipo": "pagina",
                     "chave": "/faq.html", "cliques": 6, "impressoes": 200, "posicao": 10.0}]   # (9×150 + 13×50) / 200


def test_dia_que_o_google_ainda_nao_fechou_nao_vira_zero(monkeypatch):
    _google_encenado(monkeypatch, total=False)
    assert bo.linhas_google("tok", "sc-domain:ai.arq.br", date(2026, 10, 3)) == []


# ─── Bing ───────────────────────────────────────────────────────────────────────────────────
def test_a_data_do_bing_e_o_dia_no_fuso_que_ele_mandou():
    assert bo.data_do_bing("/Date(1316156400000-0700)/") == date(2011, 9, 16)      # exemplo da documentação
    # 🪤 no exemplo o fuso não muda o dia; aqui muda: 16/09 01h UTC = 15/09 18h em -07:00
    assert bo.data_do_bing("/Date(1316134800000-0700)/") == date(2011, 9, 15)
    assert bo.data_do_bing("/Date(1759276800000)/") == date(2025, 10, 1)            # sem fuso = UTC
    assert bo.data_do_bing("lixo") is None


def test_o_bing_traz_total_por_dia_e_consultas_e_paginas_por_semana(monkeypatch):
    def _http(metodo, url, **k):
        if "GetRankAndTrafficStats" in url:
            return {"d": [{"Clicks": 2, "Impressions": 90, "Date": "/Date(1759276800000)/"}]}
        if "GetQueryStats" in url:
            return {"d": [{"Query": "levantamento quantitativo", "Clicks": 1, "Impressions": 40,
                           "AvgImpressionPosition": 6.5, "AvgClickPosition": 5, "Date": "/Date(1759276800000)/"}]}
        return {"d": [{"Query": "https://ai.arq.br/blog/posts/exemplo.html", "Clicks": 1, "Impressions": 30,
                       "AvgImpressionPosition": 4.0, "AvgClickPosition": 4, "Date": "/Date(1759276800000)/"}]}
    monkeypatch.setattr(bo, "_http", _http)
    ls = bo.linhas_bing("CHAVE-X")
    assert [(l["tipo"], l["periodo"], l["chave"], l["posicao"]) for l in ls] == [
        ("total", "dia", "", None), ("consulta", "semana", "levantamento quantitativo", 6.5),
        ("pagina", "semana", "/blog/posts/exemplo.html", 4.0)]
    assert {l["dia"] for l in ls} == {"2025-10-01"}


def test_a_chave_do_bing_nunca_aparece_no_erro(monkeypatch):
    """🪤 A API do Bing leva a chave na URL. O erro tem que dizer o que houve sem levar a URL."""
    def _abre(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {},
                                     io.BytesIO(b'{"ErrorCode":3,"Message":"Invalid API key SEGREDO-123"}'))
    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", _abre)
    with pytest.raises(RuntimeError) as e:
        bo.linhas_bing("SEGREDO-123")
    assert "SEGREDO-123" not in str(e.value) and "401" in str(e.value) and "GetRankAndTrafficStats" in str(e.value)


# ─── o resumo do painel ─────────────────────────────────────────────────────────────────────
def test_o_resumo_soma_a_janela_e_pondera_a_posicao_pelas_impressoes():
    L = lambda **k: dict({"fonte": "google", "periodo": "dia", "chave": "", "posicao": None}, **k)  # noqa: E731
    linhas = [L(dia="2026-09-01", tipo="total", cliques=99, impressoes=999, posicao=1.0),   # fora da janela
              L(dia="2026-09-20", tipo="total", cliques=5, impressoes=100, posicao=10.0),
              L(dia="2026-09-21", tipo="total", cliques=3, impressoes=300, posicao=20.0),
              L(dia="2026-09-20", tipo="consulta", chave="b", cliques=1, impressoes=10, posicao=3.0),
              L(dia="2026-09-21", tipo="consulta", chave="a", cliques=4, impressoes=50, posicao=5.0),
              L(dia="2026-09-21", tipo="consulta", chave="b", cliques=1, impressoes=30, posicao=7.0)]
    r = bo.resumo(linhas, date(2026, 9, 7))["google"]
    assert (r["dias_medidos"], r["cliques"], r["impressoes"], r["posicao"]) == (2, 8, 400, 17.5)
    assert [(c["chave"], c["cliques"], c["impressoes"], c["posicao"]) for c in r["consultas"]] == [
        ("a", 4, 50, 5.0), ("b", 2, 40, 6.0)]
    assert bo.resumo(linhas, date(2026, 9, 7))["bing"]["dias_medidos"] == 0


# ─── o tick ─────────────────────────────────────────────────────────────────────────────────
def test_sem_credencial_o_tick_diz_e_nao_grava_nem_alarma(monkeypatch, sem_credencial):
    gravou, alarmes = [], []
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: gravou.append(a) or (201, None))
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: alarmes.append(a))
    assert main._coletar_busca_organica() == {"google": "sem credencial", "bing": "sem credencial"}
    assert gravou == [] and alarmes == []


def test_com_credencial_grava_por_upsert_e_um_buscador_com_erro_nao_derruba_o_outro(monkeypatch, sem_credencial):
    gravou, alarmes = [], []

    def _grava(metodo, path, body=None, params=None, prefer=None, timeout=15):
        gravou.append((metodo, path, body, params, prefer))
        return 201, None
    monkeypatch.setattr(main, "_supa_rest_service", _grava)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: alarmes.append(a))
    monkeypatch.setattr(bo, "credencial_google", lambda: {"client_email": "x", "private_key": "y"})
    monkeypatch.setattr(bo, "token_google", lambda cred: "tok")
    monkeypatch.setattr(bo, "site_google", lambda tok: "sc-domain:ai.arq.br")
    monkeypatch.setattr(bo, "linhas_google", lambda tok, site, dia: [
        bo._linha("google", dia, "dia", "total", "", 1, 10, 5.0)])
    monkeypatch.setattr(bo, "chave_bing", lambda: "CHAVE-X")

    def _bing_caiu(chave):
        raise RuntimeError("GetQueryStats: HTTP 500: fora do ar")
    monkeypatch.setattr(bo, "linhas_bing", _bing_caiu)
    r = main._coletar_busca_organica()
    assert r["google"] == 3 and r["gravados"] == 3 and r["bing"].startswith("erro")
    metodo, path, body, params, prefer = gravou[0]
    assert (metodo, path, params) == ("POST", "busca_organica", {"on_conflict": "fonte,dia,tipo,chave"})
    assert "merge-duplicates" in prefer and len(body) == 3
    assert len(alarmes) == 1 and alarmes[0][0] == "busca:tick" and "CHAVE-X" not in str(alarmes[0])


def test_o_tick_le_os_dias_que_o_google_ja_fechou(monkeypatch, sem_credencial):
    dias = []
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (201, None))
    monkeypatch.setattr(bo, "credencial_google", lambda: {"client_email": "x", "private_key": "y"})
    monkeypatch.setattr(bo, "token_google", lambda cred: "tok")
    monkeypatch.setattr(bo, "site_google", lambda tok: "s")
    monkeypatch.setattr(bo, "linhas_google", lambda tok, site, dia: dias.append(dia) or [])
    monkeypatch.setattr(main, "_hoje_br", lambda: date(2026, 10, 10))
    main._coletar_busca_organica()
    assert dias == [date(2026, 10, 7), date(2026, 10, 6), date(2026, 10, 5)]


def test_a_rota_do_painel_e_so_do_admin():
    from fastapi.testclient import TestClient
    r = TestClient(main.app).get("/api/admin/busca")
    assert r.status_code in (401, 403)


# ─── a caixa do painel (roda no dukpy) ──────────────────────────────────────────────────────
def _caixa(dados):
    js = motor()
    js.evaljs(funcao_js("esc", "admin.html") + "; null;")
    js.evaljs(funcao_js("htmlBuscaOrganica", "admin.html") + "; null;")
    return js.evaljs("htmlBuscaOrganica(%s)" % json.dumps(dados))


def test_a_caixa_tem_tres_estados_e_nenhum_e_zero():
    assert "não consegui ler" in _caixa(None)
    vazio = {"configurado": {"google": False, "bing": True}, "google": {"dias_medidos": 0}, "bing": {"dias_medidos": 0}}
    h = _caixa(vazio)
    assert "aguardando a credencial no Render" in h and "ainda sem dia medido" in h and "0 cliques" not in h


def test_a_caixa_mostra_os_numeros_e_escapa_a_consulta():
    d = {"configurado": {"google": True, "bing": False},
         "google": {"dias_medidos": 3, "cliques": 8, "impressoes": 400, "posicao": 17.5,
                    "consultas": [{"chave": "<img src=x onerror=alert(1)>", "cliques": 2, "impressoes": 40, "posicao": 6}],
                    "paginas": [{"chave": "/faq.html", "cliques": 6, "impressoes": 200, "posicao": 10}]},
         "bing": {"dias_medidos": 0}}
    h = _caixa(d)
    assert "posição média 17,5" in h and "(3 dia(s) medido(s))" in h and "faq" in h
    assert "<img" not in h and "&lt;img" in h
