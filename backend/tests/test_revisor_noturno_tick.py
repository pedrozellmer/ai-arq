# -*- coding: utf-8 -*-
"""As rotas do revisor noturno (19/10/2026): o tick da noite e o painel do admin.

O banco é encenado (dublê de `_supa_rest_service` e `_supa_rest_tudo`) — a bancada não alcança a
produção (conftest). O que se prova aqui é o que a conta pura não prova:
- leitura que falha NÃO vira ficha (falha fechada) e a noite diz qual leitura caiu;
- o carimbo da rodada sai COM fuso (o relógio de Brasília da casa sai sem);
- texto do cliente não vai pro banco do revisor;
- sem a tabela (migração não aplicada) o tick para antes de ler qualquer coisa.
"""
import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

RECADO = "recado único do cliente 91be"


class _Req:
    def __init__(self, segredo=""):
        self.headers = {"X-Tick-Secret": segredo} if segredo else {}


class _Banco:
    """Responde por tabela; guarda tudo que foi escrito."""

    def __init__(self, falha_em=None, noites_status=200, anterior=None):
        self.falha_em = falha_em or set()
        self.noites_status = noites_status
        self.anterior = anterior
        self.escritas = []
        self.lidas = []
        self.tabelas = {
            "projetos_de_cliente": [
                {"job_id": "j1", "created_at": "2026-10-15T12:00:00+00:00", "status": "done",
                 "file_types": {"dwg": 1, "dxf": 0, "pdf": 0}, "reprocess_count": 0, "revisao_aberturas": 2},
                {"job_id": "j2", "created_at": "2026-10-16T12:00:00+00:00", "status": "done",
                 "file_types": {"dwg": 0, "dxf": 0, "pdf": 1}, "reprocess_count": 0, "revisao_aberturas": 0},
                {"job_id": "j3", "created_at": "2026-10-18T12:00:00+00:00", "status": "processing",
                 "file_types": {}, "reprocess_count": 0, "revisao_aberturas": 0},
            ],
            "projects": [{"job_id": "j1", "linhas_medidas": 4, "linhas_total": 10, "project_name": "Obra A"},
                         {"job_id": "j2", "linhas_medidas": 0, "linhas_total": 8, "project_name": "Obra B"}],
            "item_reviews": [
                {"job_id": "j1", "item_id": None, "action": "faltou", "comment": RECADO,
                 "reviewed_at": "2026-10-18T20:00:00+00:00", "conf": None},
                {"job_id": "j1", "item_id": None, "action": "reject", "comment": "",
                 "reviewed_at": "2026-10-18T20:01:00+00:00", "conf": "confirmado"},
            ],
            "revision_feedback": [], "agent_conversations": [], "nps_responses": [],
            "error_log": [{"job_id": "j1", "stage": "motor:spline"}, {"job_id": "j1", "stage": "nps:x"}],
            "email_sent_log": [], "project_memorial": [], "cronogramas": [],
            "financeiro_lancamentos": [], "project_supplier_quotes": [],
        }

    def _tabela(self, path):
        return path.split("?")[0].strip("/").split("/")[-1]

    def tudo(self, path, params=None, **kw):
        t = self._tabela(path)
        self.lidas.append(t)
        if t in self.falha_em:
            return 500, []
        filtro = (params or {}).get("job_id", "")
        linhas = self.tabelas.get(t, [])
        if filtro.startswith("in.("):
            jobs = {j.strip('"') for j in filtro[4:-1].split(",")}
            linhas = [r for r in linhas if r.get("job_id") in jobs]
        return 200, [dict(r) for r in linhas]

    def service(self, method, path, body=None, params=None, prefer=None, timeout=15):
        t = self._tabela(path)
        if method == "GET" and t == "revisor_noturno_noites":
            if self.noites_status != 200:
                return self.noites_status, None
            return 200, ([{"noite": "2026-10-18", "rodou_em": self.anterior}] if self.anterior else [])
        self.escritas.append((method, t, body, params))
        return (201 if method == "POST" else 204), None


@pytest.fixture
def banco(monkeypatch):
    def _faz(**kw):
        b = _Banco(**kw)
        monkeypatch.setattr(main, "_supa_rest_tudo", b.tudo)
        monkeypatch.setattr(main, "_supa_rest_service", b.service)
        monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
        monkeypatch.setattr(main, "TICK_SECRET", "s3gr3d0")
        return b
    return _faz


def test_sem_o_segredo_o_tick_nao_roda(banco):
    banco()
    with pytest.raises(HTTPException) as e:
        main.revisor_tick(_Req("errado"))
    assert e.value.status_code == 401


def test_sem_a_tabela_para_antes_de_ler_projeto(banco):
    b = banco(noites_status=404)
    r = main.revisor_tick(_Req("s3gr3d0"))
    assert r["status"] == "sem_tabela"
    assert b.lidas == [] and b.escritas == []


def test_leitura_que_falha_nao_vira_ficha(banco):
    b = banco(falha_em={"item_reviews"})
    r = main.revisor_tick(_Req("s3gr3d0"))
    assert r["status"] == "falhou" and any("item_reviews" in f for f in r["falhas"])
    assert not [w for w in b.escritas if w[0] == "POST" and w[1] == "revisor_noturno_fichas"]
    noite = [w for w in b.escritas if w[1] == "revisor_noturno_noites" and w[0] == "POST"][0][2]
    assert noite["n_projetos"] == 0 and any("item_reviews" in f for f in noite["falhas"])


def test_rodada_grava_as_fichas_com_fuso_e_sem_texto_do_cliente(banco):
    b = banco(anterior="2026-10-18T06:12:00+00:00")
    r = main.revisor_tick(_Req("s3gr3d0"))
    assert r["status"] == "ok" and r["projetos"] == 2          # j3 ainda processando: fora
    noite = [w for w in b.escritas if w[1] == "revisor_noturno_noites" and w[0] == "POST"][0][2]
    # 🪤 COM fuso: `_agora_br_fn()` sairia sem, e o timestamptz leria como UTC (3 h errado)
    assert noite["rodou_em"].endswith("+00:00")
    fichas = [w for w in b.escritas if w[1] == "revisor_noturno_fichas" and w[0] == "POST"][0][2]
    por_job = {f["job_id"]: f for f in fichas}
    j1 = por_job["j1"]
    assert {m["codigo"] for m in j1["motivos"]} >= {"faltou", "recado", "medido_mexido"}
    assert j1["novidade"] is True                               # revisão 18/10 20:00 > rodada 06:12
    assert j1["sinais"]["motor"]["etapas"] == ["motor:spline"]  # nps:x não é motor
    assert por_job["j2"]["novidade"] is False
    assert RECADO not in repr(b.escritas)
    # rodar de novo na mesma noite troca as fichas (apaga antes) e a retenção roda no fim
    metodos = [(m, t) for m, t, _, _ in b.escritas]
    assert metodos.index(("DELETE", "revisor_noturno_fichas")) < metodos.index(("POST", "revisor_noturno_fichas"))
    assert metodos[-1] == ("DELETE", "revisor_noturno_noites")


def test_a_janela_tem_teto(banco):
    b = banco()
    r = main.revisor_tick(_Req("s3gr3d0"), dias=999)
    assert r["janela_dias"] == main._REVISOR_JANELA_TETO
    assert b.lidas[0] == "projetos_de_cliente"


# ── painel ────────────────────────────────────────────────────────────────────────────────────
class _BancoPainel:
    def __init__(self, falha_fichas=False):
        self.falha_fichas = falha_fichas

    def service(self, method, path, body=None, params=None, prefer=None, timeout=15):
        assert method == "GET"
        if params.get("noite", "").startswith("eq."):
            return 200, [{"noite": params["noite"][3:], "padroes": [{"etapa": "motor:x"}], "falhas": []}]
        return 200, [{"noite": "2026-10-19"}, {"noite": "2026-10-18"}]

    def tudo(self, path, params=None, **kw):
        t = path.split("?")[0]
        if t == "revisor_noturno_fichas":
            if self.falha_fichas:
                return 500, []
            return 200, [{"job_id": "j1", "nota": 6, "noite": params["noite"][3:]}]
        if t == "projects":
            return 200, [{"job_id": "j1", "project_name": "Obra A"}]
        return 200, []


def test_painel_mostra_a_ultima_noite_com_o_nome_lido_na_hora(monkeypatch):
    p = _BancoPainel()
    monkeypatch.setattr(main, "_require_admin", lambda r: {"email": "x"})
    monkeypatch.setattr(main, "_supa_rest_service", p.service)
    monkeypatch.setattr(main, "_supa_rest_tudo", p.tudo)
    d = main.admin_revisor_noturno(_Req())
    assert d["erro"] is False and d["noite"]["noite"] == "2026-10-19"
    assert d["fichas"][0]["projeto"] == "Obra A"
    d = main.admin_revisor_noturno(_Req(), noite="2026-10-18")
    assert d["noite"]["noite"] == "2026-10-18"
    # noite que não está na lista cai na última, não em consulta livre
    assert main.admin_revisor_noturno(_Req(), noite="'; drop")["noite"]["noite"] == "2026-10-19"


def test_painel_que_nao_leu_as_fichas_diz_erro_e_nao_fila_vazia(monkeypatch):
    p = _BancoPainel(falha_fichas=True)
    monkeypatch.setattr(main, "_require_admin", lambda r: {"email": "x"})
    monkeypatch.setattr(main, "_supa_rest_service", p.service)
    monkeypatch.setattr(main, "_supa_rest_tudo", p.tudo)
    assert main.admin_revisor_noturno(_Req())["erro"] is True
