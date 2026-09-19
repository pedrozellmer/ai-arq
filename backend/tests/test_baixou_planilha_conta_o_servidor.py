# -*- coding: utf-8 -*-
""""Baixou planilha" conta o registro do SERVIDOR — e diz quem baixou.

🩸 18/09/2026 — item 9 da fila. Medido antes de escrever:

  · o registro `entrega:download` (única porta por onde o arquivo passa) existe
    desde 15/09: 89 linhas, **78 do smoke test e 11 de clientes** — e não dizia
    quem baixou;
  · desde que ele existe, em 16 jobs concluídos de cliente o clique do
    navegador (`download_xlsx`, opt-in de cookie) viu **6** e o servidor viu
    **8**: 0 só-navegador, 2 só-servidor. O servidor enxerga tudo que o
    navegador enxerga, e mais;
  · os dois caminhos do navegador (tela do projeto e aba Downloads) passam
    pela MESMA rota `/api/download/{job}` — não há caminho que o servidor não
    veja.

O que se cobra aqui:
  · a rota marca `por=cliente|interno|desconhecido` — um RÓTULO, não o e-mail
    — e "desconhecido" nunca vira "cliente" por padrão;
  · o painel de Atividade troca o clique pelo registro do servidor a partir da
    costura (15/09): antes dela só o clique existe; depois, contar os dois
    seria contar o mesmo download duas vezes. `por=interno` nunca conta;
  · a RPC `admin_filhotes` (SQL, aplicada no banco) passou a valer o MAIOR dos
    dois caminhos — não dá pra rodar SQL aqui; a cópia está em
    `migrations_pendentes/admin_filhotes_conta_download_do_servidor.sql` e foi
    conferida contra o banco no dia (0 filhote baixado desde 15/09, então
    nada mudou de imediato).
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import main  # noqa: E402


# ── a rota, EXECUTADA: quem baixou vira rótulo ─────────────────────────────

def _baixa(monkeypatch, email):
    tmp = os.path.join(tempfile.mkdtemp(prefix="dl_"), "p.xlsx")
    with open(tmp, "wb") as f:
        f.write(b"x" * 10)
    logs = []

    async def _pago(job_id):
        return None
    monkeypatch.setattr(main, "_require_project_owner", lambda *a, **k: None)
    monkeypatch.setattr(main, "_require_entregavel_pago_async", _pago)
    monkeypatch.setattr(main, "get_planilha_path", lambda job_id: tmp)
    monkeypatch.setattr(main, "_get_user_from_request",
                        lambda req, tolerante=False: ({"email": email} if email else None))
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: logs.append(a))
    asyncio.run(main.download_file("job-teste", object()))
    entrega = [l for l in logs if l[0] == "entrega:download"]
    assert len(entrega) == 1, logs
    return entrega[0][1]


def test_o_download_do_cliente_sai_marcado_por_cliente(monkeypatch):
    msg = _baixa(monkeypatch, "cliente-nn@example.com")
    assert msg.endswith(" por=cliente"), msg
    assert "cliente-nn@example.com" not in msg, "o e-mail foi pro error_log — era pra ir só o rótulo"


def test_o_download_da_casa_sai_marcado_por_interno(monkeypatch):
    """🩸 78 dos 89 registros eram o smoke test (alias +smoke do admin)."""
    msg = _baixa(monkeypatch, main.ADMIN_EMAIL.replace("@", "+smoke@"))
    assert msg.endswith(" por=interno"), msg


def test_sem_sessao_confirmada_e_DESCONHECIDO_nunca_cliente(monkeypatch):
    """🪤 'cliente' por padrão inflaria exatamente a métrica que isto corrige."""
    msg = _baixa(monkeypatch, "")
    assert msg.endswith(" por=desconhecido"), msg


def test_o_rotulo_nao_derruba_o_download_se_a_sessao_falhar(monkeypatch):
    def _explode(*a, **k):
        raise RuntimeError("auth fora do ar")
    monkeypatch.setattr(main, "_get_user_from_request", _explode)
    assert main._rotulo_de_quem_baixou(object()) == "desconhecido"


# ── o painel de Atividade: o servidor no lugar do clique, a partir da costura ──

_COSTURA = main._DOWNLOAD_NO_SERVIDOR_DESDE


def _atividade(monkeypatch, eventos, registros, donos):
    def _tudo(path, params=None, **k):
        params = params or {}
        if path == "usage_events":
            return 200, list(eventos)
        if path == "error_log":
            return 200, list(registros)
        if path == "projects":
            if "job_id" in params:
                return 200, list(donos)
            return 200, []
        return 200, []
    monkeypatch.setattr(main, "_require_admin", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_rest_tudo", _tudo)
    monkeypatch.setattr(main, "_auth_admin_list_users", lambda *a, **k: [])
    monkeypatch.setattr(main, "_usage_events_por_nome", lambda dias=365: [])
    return main.admin_activity(object(), days=60, limit=100)


def _ev(ev, quando, quem="c@x.com", job="j1"):
    return {"event": ev, "user_email": quem, "user_id": "u1", "job_id": job,
            "path": "", "meta": {"cid": "abc"}, "created_at": quando}


def _srv(job, quando, rotulo="cliente"):
    return {"job_id": job, "created_at": quando,
            "message": "planilha entregue (10 bytes) por=%s" % rotulo}


_DONOS = [{"job_id": "j1", "user_email": "c@x.com", "user_id": "u1"},
          {"job_id": "j2", "user_email": "c@x.com", "user_id": "u1"}]


def test_depois_da_costura_o_clique_e_trocado_pelo_registro_do_servidor(monkeypatch):
    """O mesmo download aparece nos dois; contar os dois seria contar duas
    vezes. Depois da costura vale o servidor."""
    d = _atividade(monkeypatch,
                   eventos=[_ev("download_xlsx", _COSTURA + "T10:00:00Z")],
                   registros=[_srv("j1", _COSTURA + "T10:00:01Z")],
                   donos=_DONOS)
    assert d["by_event"].get("download_xlsx") == 1, d["by_event"]
    fontes = [(r.get("meta") or {}).get("fonte") for r in d["recent"] if r["event"] == "download_xlsx"]
    assert fontes == ["servidor"], fontes


def test_o_servidor_ve_o_download_que_o_clique_NAO_viu(monkeypatch):
    """🩸 Os 2 só-servidor de 15–18/09: quem não aceitou o cookie."""
    d = _atividade(monkeypatch, eventos=[],
                   registros=[_srv("j2", _COSTURA + "T12:00:00Z")], donos=_DONOS)
    assert d["by_event"].get("download_xlsx") == 1
    assert d["recent"][0]["user_email"] == "c@x.com", "o download ficou sem dono"


def test_ANTES_da_costura_o_clique_continua_valendo(monkeypatch):
    """Antes de 15/09 o servidor não existia — descartar o clique ali apagaria
    a única história que há.

    🪤 A 1ª versão passava sem registro nenhum do servidor — e a função
    devolvia cedo nesse caso, sem nunca rodar o filtro. Sabotagem U06 mostrou:
    a costura movida pra 01/01 não reprovava. Agora há um registro pós-costura
    de OUTRO job, pra o filtro rodar de verdade, e um clique pós-costura sem
    par no servidor, que TEM que cair."""
    d = _atividade(monkeypatch,
                   eventos=[_ev("download_xlsx", "2026-09-01T10:00:00Z", job="j1"),
                            _ev("download_xlsx", _COSTURA + "T09:00:00Z", job="j2")],
                   registros=[_srv("j2", _COSTURA + "T12:00:00Z")], donos=_DONOS)
    # 1 clique de antes da costura (fica) + 1 registro do servidor (entra);
    # o clique pós-costura de j2 é o MESMO download do servidor e cai.
    assert d["by_event"].get("download_xlsx") == 2, d["by_event"]
    quando = sorted(r["created_at"] for r in d["recent"] if r["event"] == "download_xlsx")
    assert quando == ["2026-09-01T10:00:00Z", _COSTURA + "T12:00:00Z"], quando


def test_leitura_VAZIA_do_servidor_ainda_descarta_o_clique_pos_costura(monkeypatch):
    """Leitura 200 com zero linhas é resposta ("ninguém baixou"), não
    ausência de resposta: o clique pós-costura sem par no servidor cai."""
    d = _atividade(monkeypatch,
                   eventos=[_ev("download_xlsx", _COSTURA + "T09:00:00Z")],
                   registros=[], donos=_DONOS)
    assert "download_xlsx" not in d["by_event"], d["by_event"]


def test_o_download_INTERNO_nunca_vira_baixou(monkeypatch):
    d = _atividade(monkeypatch, eventos=[],
                   registros=[_srv("j1", _COSTURA + "T10:00:00Z", "interno"),
                              _srv("j1", _COSTURA + "T10:01:00Z", "desconhecido")],
                   donos=_DONOS)
    assert "download_xlsx" not in d["by_event"], d["by_event"]


def test_registro_SEM_rotulo_so_conta_se_o_dono_nao_e_da_casa(monkeypatch):
    """Os 3 dias entre o registro nascer (15/09) e ganhar rótulo (18/09).

    🪤 Olha a FUNÇÃO, não o painel: o painel tem um filtro de conta interna
    logo depois, que mascarava a mutação (sabotagem U08, equivalente pela
    rota). A checagem precisa valer sozinha, porque a função pode ser
    reusada onde esse filtro não existe."""
    sem = {"job_id": "j1", "created_at": _COSTURA + "T10:00:00Z",
           "message": "planilha entregue (10 bytes)"}

    def _com_dono(dono):
        def _tudo(path, params=None, **k):
            if path == "error_log":
                return 200, [sem]
            if path == "projects":
                return 200, [dono]
            return 200, []
        monkeypatch.setattr(main, "_supa_rest_tudo", _tudo)
        rows, n = main._com_downloads_do_servidor([], "2026-09-01T00:00:00Z", [])
        return [r for r in rows if r["event"] == "download_xlsx"], n

    fora, n = _com_dono({"job_id": "j1", "user_email": "c@x.com", "user_id": "u1"})
    assert n == 1 and fora and fora[0]["user_email"] == "c@x.com"
    casa, n2 = _com_dono({"job_id": "j1", "user_email": main.ADMIN_EMAIL, "user_id": "adm"})
    assert n2 == 0 and casa == [], casa


def test_CONTROLE_se_o_error_log_cair_o_painel_NAO_cai(monkeypatch):
    def _tudo(path, params=None, **k):
        if path == "error_log":
            return 500, []
        if path == "usage_events":
            return 200, [_ev("view_aba", _COSTURA + "T10:00:00Z")]
        return 200, []
    monkeypatch.setattr(main, "_require_admin", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_rest_tudo", _tudo)
    monkeypatch.setattr(main, "_auth_admin_list_users", lambda *a, **k: [])
    monkeypatch.setattr(main, "_usage_events_por_nome", lambda dias=365: [])
    d = main.admin_activity(object(), days=30, limit=10)
    assert d["total_events"] == 1


def test_a_costura_e_uma_data_e_nao_futuro():
    """🪤 Se alguém 'consertar' a costura pra frente, o clique volta a contar
    junto do servidor e o download dobra."""
    import datetime
    dt = datetime.date.fromisoformat(_COSTURA)
    assert dt <= datetime.date(2026, 9, 18), _COSTURA
