# -*- coding: utf-8 -*-
"""Uma régua só de cliente nos contadores de projeto.

🩸 27/09/2026 — auditoria de telemetria, item 2. A aba Atividade dizia 169
"subiu projeto" em 30 dias quando os de cliente eram 102: 63 avaliações, 3
reprocessos de cliente e 1 projeto da casa entravam como movimento de cliente.

🔑 O projeto vem da view `projetos_de_cliente` (a regra do banco, a mesma do
resto do painel); o reprocesso vira linha à parte. No banco,
`migrations_pendentes/regua_unica_da_casa_nos_contadores.sql` troca a retenção
(17 → 16) e a régua de cobrança (ensaiada num bloco desfeito).

🔑 Nos EVENTOS a régua da equipe continua a de hoje — só o dono sai. Pedro,
27/09, perguntado sobre a outra conta da casa no funil ("+40 eventos"):
"mantém a régua de hoje". Tirá-la também é decisão dele, não deste guarda.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

_CASA2 = "segunda-conta@casa.example"   # a outra conta da casa (fictícia)


def _ev(ev, quem, quando="2026-09-20T10:00:00Z", job=""):
    return {"event": ev, "user_email": quem, "user_id": "u-" + quem[:3], "job_id": job,
            "path": "", "meta": {"cid": "c-" + quem[:3]}, "created_at": quando}


def _proj(job, quem, pai=None, is_eval=False, status="done"):
    return {"job_id": job, "user_email": quem, "user_id": "u-" + (quem or "x")[:3],
            "status": status, "created_at": "2026-09-20T12:00:00Z",
            "completed_at": "2026-09-20T12:10:00Z", "parent_job_id": pai,
            "is_eval": is_eval}


# O banco inteiro (`projects`) e o que a view de cliente devolve dele.
_TODOS = [_proj("raiz", "c@x.com"),
          _proj("repro", "c@x.com", pai="raiz"),
          _proj("aval", "", pai="raiz", is_eval=True),
          _proj("dacasa", _CASA2)]
_DE_CLIENTE = [p for p in _TODOS if p["job_id"] in ("raiz", "repro")]


def _atividade(monkeypatch):
    def _tudo(path, params=None, **k):
        params = params or {}
        if path == "usage_events":
            return 200, [_ev("view_cadastro", _CASA2), _ev("view_dashboard", "c@x.com"),
                         _ev("view_dashboard", main.ADMIN_EMAIL)]
        if path == "projetos_de_cliente":
            return 200, [dict(p) for p in _DE_CLIENTE]
        if path == "projects":
            return 200, ([] if "job_id" in params else [dict(p) for p in _TODOS])
        return 200, []
    # As contas existem no auth, criadas FORA da janela (não viram "criou conta").
    # 🪤 Com a lista vazia este teste só valeria enquanto `usage_events` guarda o
    # e-mail: o trabalho de LGPD de 27/09 passa a buscar o e-mail na CONTA pelo id.
    contas = [{"id": "u-" + e[:3], "email": e, "created_at": "2026-01-01T00:00:00Z"}
              for e in (_CASA2, "c@x.com", main.ADMIN_EMAIL)]
    monkeypatch.setattr(main, "_require_admin", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_rest_tudo", _tudo)
    monkeypatch.setattr(main, "_auth_admin_list_users", lambda *a, **k: [dict(c) for c in contas])
    monkeypatch.setattr(main, "_usage_events_por_nome", lambda dias=365: [])
    return main.admin_activity(object(), days=30, limit=100)


def test_subiu_projeto_conta_so_o_projeto_de_cliente_e_o_reprocesso_fica_a_parte(monkeypatch):
    d = _atividade(monkeypatch)
    ev = d["by_event"]
    assert ev.get("start_project") == 1, (
        "avaliação, reprocesso ou projeto da casa voltaram a contar como "
        "'subiu projeto': %r" % ev)
    assert ev.get("project_done") == 1, ev
    assert ev.get("project_reprocess") == 1, "o reprocesso sumiu em vez de ir pra linha à parte"


def test_nos_eventos_so_o_DONO_sai_e_a_outra_conta_da_casa_continua(monkeypatch):
    """A decisão do Pedro (27/09), presa pra não mudar por acidente — e o
    controle: o dono continua fora."""
    d = _atividade(monkeypatch)
    quem = {u["email"] for u in d["users"]}
    assert main.ADMIN_EMAIL not in quem, "o dono voltou a contar na Atividade"
    assert _CASA2 in quem and d["by_event"].get("view_cadastro") == 1, (
        "a outra conta da casa saiu dos eventos — o Pedro escolheu manter (27/09)")
    assert "c@x.com" in quem


def test_a_tela_tem_nome_pro_reprocesso():
    adm = open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "admin.html"), encoding="utf-8").read()
    rotulos = adm[adm.find("const ACT_LABELS"):]
    rotulos = rotulos[:rotulos.find("};")]
    assert re.search(r"\bproject_reprocess\s*:", rotulos), (
        "o reprocesso aparece como '• project_reprocess' — sem nome na tela")
