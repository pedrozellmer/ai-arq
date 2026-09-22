# -*- coding: utf-8 -*-
"""A sugestão de "projeto irmão" tem que dizer o TIPO do irmão.

🩸 22/09/2026 — jobs ee801b82 → f8d8e6d8. O anexo ao projeto de ontem (tipo
ESTRUTURA) foi recusado por arquivo repetido, e a tela criou um projeto novo
sozinha no tipo padrão do formulário — arquitetura. O conserto do dashboard
(ver test_o_anexo_recusado_nao_vira_projeto_sozinho) só cria projeto com o
clique da pessoa e oferece o tipo do irmão; pra isso, as duas rotas que acham
o irmão (`/api/projetos/candidatos-anexo`, pelo nome, e
`/api/projetos/comparar-desenho`, pelo conteúdo do DXF) precisam devolver o
`project_type` dele. Sem isso a tela volta a oferecer o padrão, calada.

O banco de mentira aqui responde como o PostgREST: só as colunas que o
`select=` pediu. Um dublê que devolvesse a linha inteira deixaria o guarda
verde com a coluna fora da consulta — o CONTROLE no fim prova que não deixa.

E o evento novo `anexo_recusado` (a falha do anexo, que não deixava rastro) tem
que passar na lista do `/api/track` — rota CHAMADA, não lida.
"""
import asyncio
import os
import sys
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

_LINHA = {"job_id": "ee801b82", "project_name": "Projeto 21/09/2026",
          "project_type": "estrutura", "status": "done",
          "created_at": "2026-09-21T20:07:00Z", "items_count": 63,
          "desenho_assinatura": {"fingerprint": "f" * 36, "n_layers": 12}}


def _postgrest(linhas, pedidos):
    """`_supa_rest_service` de mentira que devolve SÓ as colunas do `select=`."""
    def _chamada(method, path, *a, **k):
        pedidos.append(path)
        qs = parse_qs(urlsplit("/" + path).query)
        cols = [c.strip() for c in (qs.get("select") or [""])[0].split(",") if c.strip()]
        return 200, [{c: l[c] for c in cols if c in l} for l in linhas]
    return _chamada


class _Req(object):
    headers = {}
    client = None


def _candidatos(monkeypatch, linhas):
    pedidos = []
    monkeypatch.setattr(main, "_get_user_from_request", lambda *a, **k: {"id": "u-teste"})
    monkeypatch.setattr(main, "_supa_rest_service", _postgrest(linhas, pedidos))
    monkeypatch.setattr(main, "_supabase_storage_list",
                        lambda *a, **k: ["prancha-A.pdf", "prancha-B.pdf"])
    return main.projetos_candidatos_anexo(_Req(), horas=72), pedidos


def test_candidatos_anexo_devolve_o_tipo_do_irmao(monkeypatch):
    fora, pedidos = _candidatos(monkeypatch, [_LINHA])
    assert pedidos, "a rota nem consultou o banco"
    p = fora["projetos"]
    assert len(p) == 1 and p[0]["job_id"] == "ee801b82", fora
    assert p[0]["project_type"] == "estrutura", (
        "o candidato saiu sem o tipo: a tela oferece o padrão do formulário "
        "de novo (o caso f8d8e6d8): %r" % p[0])
    assert p[0]["bases"] == ["prancha a", "prancha b"], p[0]["bases"]


def test_candidato_sem_tipo_no_banco_sai_vazio_nunca_inventado(monkeypatch):
    linha = dict(_LINHA, project_type=None)
    fora, _ = _candidatos(monkeypatch, [linha])
    assert fora["projetos"][0]["project_type"] == "", fora


def test_comparar_desenho_devolve_o_tipo_do_irmao(monkeypatch):
    import dxf_assinatura
    pedidos = []
    monkeypatch.setattr(main, "_get_user_from_request", lambda *a, **k: {"id": "u-teste"})
    monkeypatch.setattr(main, "_supa_rest_service", _postgrest([_LINHA], pedidos))
    monkeypatch.setattr(dxf_assinatura, "semelhanca",
                        lambda *a, **k: {"mesmo_desenho": True, "jaccard": 1.0,
                                         "motivo": "mesmo identificador"})
    fora = main.comparar_desenho(main.AssinaturaPayload(fingerprint="f" * 36),
                                 _Req(), horas=72)
    assert pedidos, "a rota nem consultou o banco"
    assert fora["achou"] and fora["achou"]["job_id"] == "ee801b82", fora
    assert fora["achou"]["project_type"] == "estrutura", fora["achou"]


def test_CONTROLE_o_banco_de_mentira_corta_a_coluna_que_nao_foi_pedida():
    """Sem este, os guardas acima passariam com a coluna fora do `select=`."""
    pedidos = []
    st, linhas = _postgrest([_LINHA], pedidos)(
        "GET", "projects?user_id=eq.u&select=job_id,project_name")
    assert st == 200 and linhas == [{"job_id": "ee801b82",
                                     "project_name": "Projeto 21/09/2026"}], linhas


def test_o_evento_anexo_recusado_passa_no_track_com_o_codigo(monkeypatch):
    linhas = []
    monkeypatch.setattr(main, "_supabase_insert", lambda tabela, row, *a, **k: linhas.append(row))
    corpo = main.TrackPayload(event="anexo_recusado", job_id="ee801b82",
                              meta={"type": "409"})
    fora = asyncio.run(main.track_event(corpo, _Req()))
    assert fora.get("status") != "ignored", (
        "o /api/track descarta o evento — a falha do anexo seguiria sem rastro")
    assert len(linhas) == 1 and linhas[0]["event"] == "anexo_recusado", linhas
    assert linhas[0]["meta"].get("type") == "409", linhas[0]


def test_CONTROLE_evento_fora_da_lista_e_descartado(monkeypatch):
    linhas = []
    monkeypatch.setattr(main, "_supabase_insert", lambda tabela, row, *a, **k: linhas.append(row))
    corpo = main.TrackPayload(event="anexo_recusado_x", meta={"type": "409"})
    fora = asyncio.run(main.track_event(corpo, _Req()))
    assert fora.get("status") == "ignored" and linhas == [], (fora, linhas)
