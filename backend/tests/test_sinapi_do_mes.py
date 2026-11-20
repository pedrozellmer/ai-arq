# -*- coding: utf-8 -*-
"""Carga do SINAPI do mês direto da Caixa, pra uma tabela À PARTE.

📅 20/11/2026 — a tabela do motor parou em 03/2026; 2% das escolhas do último
mês já apontavam código desativado (180 de 209 eram o concreto fck 25/30).
Isto aqui só ENCHE `sinapi_composicao_novo`; a tabela do motor não muda.
"""
import io
import os
import sys
import zipfile

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import sinapi_do_mes as sm  # noqa: E402


def _zip(nomes):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n in nomes:
            z.writestr(n, b"conteudo-de-" + n.encode("utf-8"))
    return buf.getvalue()


def _linhas(n):
    return [{"codigo": str(90000 + i), "descricao": "X", "unidade": "M2",
             "sync_month": "2026-10-01"} for i in range(n)]


# ── endereço ───────────────────────────────────────────────────────────────
def test_endereco_do_mes():
    assert sm.url_do_mes("2026-10").endswith("/SINAPI-2026-10-formato-xlsx.zip")


@pytest.mark.parametrize("ruim", ["", "2026-13", "2026-1", "10/2026", "2026-10-01",
                                  "1999-10", "2026-10;rm"])
def test_mes_em_formato_errado_e_recusado(ruim):
    with pytest.raises(ValueError):
        sm.url_do_mes(ruim)


def test_pagina_de_erro_no_lugar_do_zip_e_recusada(monkeypatch):
    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(sm.urllib.request, "urlopen",
                        lambda *a, **k: _Resp(b"<html>nao achou</html>"))
    with pytest.raises(ValueError):
        sm.baixar("2026-10")


# ── a planilha certa de dentro do pacote ───────────────────────────────────
def test_pega_a_planilha_de_referencia_mesmo_com_acento_torto(tmp_path):
    # o pacote real traz 4 planilhas; o nome da Referência vem com o "ê"
    # em codificação diferente conforme o mês
    pacote = _zip(["SINAPI_familias_e_coeficientes_2026_10.xlsx",
                   "SINAPI_Manutenções_2026_10.xlsx",
                   "SINAPI_ReferÃªncia_2026_10.xlsx",
                   "SINAPI_mao_de_obra_2026_10.xlsx"])
    caminho = sm.extrair_referencia(pacote, str(tmp_path))
    assert open(caminho, "rb").read().startswith(b"conteudo-de-SINAPI_Refer")


def test_pacote_sem_referencia_e_recusado(tmp_path):
    with pytest.raises(ValueError):
        sm.extrair_referencia(_zip(["SINAPI_mao_de_obra_2026_10.xlsx"]), str(tmp_path))


# ── planilha que chega pela metade não grava ───────────────────────────────
def test_poucas_composicoes_nao_passam(monkeypatch):
    import sinapi_loader
    monkeypatch.setattr(sinapi_loader, "parse_composicoes", lambda *a, **k: _linhas(500))
    with pytest.raises(ValueError, match="nada foi gravado"):
        sm.ler_composicoes("2026-10", _zip(["SINAPI_Referencia_2026_10.xlsx"]))


def test_planilha_cheia_passa_com_o_mes_certo(monkeypatch):
    import sinapi_loader
    visto = {}

    def _parse(caminho, sync_month=""):
        visto["mes"] = sync_month
        return _linhas(sm.MINIMO_DE_COMPOSICOES)
    monkeypatch.setattr(sinapi_loader, "parse_composicoes", _parse)
    assert len(sm.ler_composicoes("2026-10", _zip(["SINAPI_Referencia.xlsx"]))) == sm.MINIMO_DE_COMPOSICOES
    assert visto["mes"] == "2026-10-01"


# ── gravar ─────────────────────────────────────────────────────────────────
def test_falha_ao_ler_NAO_esvazia_a_tabela(monkeypatch):
    monkeypatch.setattr(sm, "baixar", lambda mes: b"PK")
    monkeypatch.setattr(sm, "ler_composicoes",
                        lambda mes, z: (_ for _ in ()).throw(ValueError("formato mudou")))
    apagou = []
    with pytest.raises(ValueError):
        sm.carregar("2026-10", lambda: apagou.append(1), lambda l: True)
    assert apagou == []


def test_grava_em_lotes_e_conta_lote_que_falhou(monkeypatch):
    monkeypatch.setattr(sm, "baixar", lambda mes: b"PK")
    monkeypatch.setattr(sm, "ler_composicoes", lambda mes, z: _linhas(1200))
    ordem, lotes = [], []

    def _inserir(l):
        ordem.append("inserir")
        lotes.append(len(l))
        return len(lotes) != 2          # o 2º lote falha
    r = sm.carregar("2026-10", lambda: ordem.append("apagar"), _inserir, lote=500)
    assert ordem[0] == "apagar"
    assert lotes == [500, 500, 200]
    assert r == {"mes": "2026-10", "lidas": 1200, "gravadas": 700, "lotes_com_erro": 1}


# ── a rota ─────────────────────────────────────────────────────────────────
@pytest.fixture
def rota(monkeypatch):
    import main
    monkeypatch.setattr(main, "_require_admin", lambda *a, **k: {"email": "x"})
    monkeypatch.setattr(main.jobs, "em_curso", lambda: 0)
    monkeypatch.setattr(main.jobs, "uploads_em_curso", lambda: 0)
    disparos = []
    monkeypatch.setattr(main.threading, "Thread",
                        lambda target, args, **k: type("T", (), {
                            "start": lambda self: disparos.append(args)})())
    yield main, disparos
    if main._sinapi_do_mes_rodando.locked():
        main._sinapi_do_mes_rodando.release()


def test_rota_dispara_a_carga_e_nao_toca_a_tabela_do_motor(rota):
    main, disparos = rota
    r = main.admin_sinapi_do_mes(request=None, mes="2026-10")
    assert disparos == [("2026-10",)]
    assert r["tabela"] == "sinapi_composicao_novo" != "sinapi_composicao"


def test_rota_recusa_mes_errado(rota):
    main, disparos = rota
    with pytest.raises(main.HTTPException) as e:
        main.admin_sinapi_do_mes(request=None, mes="outubro")
    assert e.value.status_code == 400 and disparos == []


def test_rota_recusa_com_projeto_rodando(rota, monkeypatch):
    main, disparos = rota
    monkeypatch.setattr(main.jobs, "em_curso", lambda: 1)
    with pytest.raises(main.HTTPException) as e:
        main.admin_sinapi_do_mes(request=None, mes="2026-10")
    assert e.value.status_code == 409 and disparos == []


def test_rota_nao_roda_duas_cargas_ao_mesmo_tempo(rota):
    main, disparos = rota
    main.admin_sinapi_do_mes(request=None, mes="2026-10")
    with pytest.raises(main.HTTPException) as e:
        main.admin_sinapi_do_mes(request=None, mes="2026-10")
    assert e.value.status_code == 409 and len(disparos) == 1


def test_a_thread_solta_a_trava_mesmo_quando_falha(monkeypatch):
    import main
    import sinapi_do_mes
    monkeypatch.setattr(sinapi_do_mes, "carregar",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("caiu")))
    logs = []
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: logs.append((a, k)))
    main._sinapi_do_mes_rodando.acquire()
    main._rodar_sinapi_do_mes("2026-10")
    assert not main._sinapi_do_mes_rodando.locked()
    assert logs and "FALHOU" in logs[0][0][1]


def test_a_rota_exige_admin():
    import inspect
    import main
    fonte = inspect.getsource(main.admin_sinapi_do_mes)
    assert fonte.index("_require_admin(request)") < fonte.index("threading.Thread")
