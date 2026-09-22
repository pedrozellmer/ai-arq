# -*- coding: utf-8 -*-
"""UM MOTOR POR PROJETO — a trava que impede dois processamentos no mesmo job_id.

🩸 21/09/2026. Dois caminhos relançavam o mesmo projeto SEM CONDIÇÃO:

  • a rota de anexo (`/add-file`) LIA o status (409 se queued/processing),
    passava MINUTOS subindo e baixando arquivo do Storage, e só então gravava
    "queued" — pela RPC `update_project_status`, que grava sem olhar o status
    anterior;
  • a varredura/retomada (`_retomar_job_do_storage`) lia "error" e relançava,
    também sem condição.

Se a varredura caísse na janela do upload, eram dois motores no mesmo job_id:
IA paga duas vezes, duas planilhas diferentes e dois e-mails contando
histórias diferentes. E a retomada ainda APAGAVA `project_items` antes de
relançar — por cima da planilha que o anexo estava preservando.

🔑 O conserto é UMA gravação condicional, `_tomar_o_projeto`: PATCH em
`projects` com o filtro de status na própria URL e `Prefer:
return=representation`, contando a linha que volta. 1 linha = "ganhou";
lista vazia = "perdeu" (outro já pegou); resposta perdida/estranha =
"incerto". A rota grava `anexo_em_curso` (o id DESTE pedido) no MESMO PATCH
do status, e quando a resposta se perde relê a marca pra saber se foi ela.

🪤 Por que os dublês daqui distinguem cada pedido (regra da casa): um dublê de
`urlopen` que devolve a mesma linha pra qualquer PATCH faz a trava SEMPRE
ganhar — o teste do perdedor nunca roda de verdade e fica verde por
construção. Por isso o banco daqui é um PostgREST de mentira que APLICA o
filtro de status (eq., in., not.in.), respeita o `Prefer` (sem
`return=representation` o PostgREST responde 204 sem corpo) e só devolve as
linhas que casaram. A corrida é encenada onde ela acontece: o projeto muda
DURANTE o upload (a janela de minutos da rota) ou logo DEPOIS da leitura da
retomada.

🧪 Tudo aqui EXECUTA o código real — `_tomar_o_projeto`,
`add_file_and_reprocess` e `_retomar_job_do_storage` — com rede, banco,
Storage e o motor (`_process_job_throttled`) substituídos. Todo dublê aceita
`**k` (dublê de assinatura exata desarma calado quando nasce parâmetro).
Cada recusa tem o seu CONTROLE: o caso em que o código TEM que agir.
"""
import asyncio
import io
import json
import os
import socket
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main  # noqa: E402
from models import ProcessingStatus  # noqa: E402

JOB = "f1c7c10e2109"                     # job_id fictício
EMAIL = "cliente-nn@example.com"          # repositório público: nada de cliente real
LIVRE = "not.in.(queued,processing)"      # o filtro que a rota do anexo usa

DXF = b"0\r\nSECTION\r\n2\r\nHEADER\r\n0\r\nENDSEC\r\n0\r\nEOF\r\n"
PDF = b"%PDF-1.4\n% prancha de mentira\n" + b"0" * 64 + b"\n%%EOF\n"


# ══════════════════════════════════════════════════════════════════════════
#  O PostgREST de mentira
# ══════════════════════════════════════════════════════════════════════════
class _FiltroDesconhecido(Exception):
    pass


def _casa(valor, filtro):
    """Um filtro do PostgREST aplicado a UM valor de coluna.

    🪤 Como no Postgres: NULL não casa com `eq.`, `in.` nem `not.in.` — só com
    `is.null`. Filtro que este dublê não conhece levanta, pra não virar um
    "casa tudo" calado.
    """
    if filtro == "is.null":
        return valor is None
    if filtro.startswith("not.in.(") and filtro.endswith(")"):
        opcoes = filtro[len("not.in.("):-1].split(",")
        return valor is not None and str(valor) not in opcoes
    if filtro.startswith("in.(") and filtro.endswith(")"):
        opcoes = filtro[len("in.("):-1].split(",")
        return valor is not None and str(valor) in opcoes
    if filtro.startswith("eq."):
        return valor is not None and str(valor) == filtro[3:]
    if filtro.startswith("neq."):
        return valor is not None and str(valor) != filtro[4:]
    raise _FiltroDesconhecido(filtro)


class _Resposta(object):
    def __init__(self, codigo, corpo=b""):
        self._codigo = codigo
        self._corpo = corpo
        self.status = codigo

    def getcode(self):
        return self._codigo

    def read(self, *a, **k):
        return self._corpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _json(dados, codigo=200):
    return _Resposta(codigo, json.dumps(dados, default=str).encode("utf-8"))


class _Banco(object):
    """`projects` + `project_items` + Storage, em memória, respondendo como o
    PostgREST responderia a cada pedido (método + tabela + filtros + Prefer).

    `pedidos` guarda tudo o que chegou, na ordem. `estranhos` guarda o que
    este dublê não sabe atender — tem que terminar vazio, senão algum caminho
    do código foi pra rede sem o teste saber.
    """

    _RESERVADOS = {"select", "limit", "order", "offset"}

    def __init__(self, projeto, itens=(), storage=None):
        self.tabelas = {"projects": [dict(projeto)],
                        "project_items": [dict(i) for i in itens]}
        self.storage = dict(storage or {})
        self.pedidos = []
        self.estranhos = []
        self._falhas = []       # [predicado, modo] — uma vez cada
        self._depois = []       # [predicado, ação] — a corrida, uma vez cada
        self.ao_subir = None    # ação durante o upload da rota (a janela de minutos)

    @property
    def projeto(self):
        return self.tabelas["projects"][0]

    @property
    def itens(self):
        return self.tabelas["project_items"]

    def falhar(self, predicado, modo):
        self._falhas.append([predicado, modo])

    def depois_de(self, predicado, acao):
        self._depois.append([predicado, acao])

    # ── o urlopen ─────────────────────────────────────────────────────────
    def urlopen(self, req, timeout=None, *a, **k):
        if isinstance(req, str):
            url, metodo, prefer, bruto = req, "GET", "", None
        else:
            url = req.full_url
            metodo = req.get_method()
            prefer = req.get_header("Prefer") or ""
            bruto = req.data
        partes = urllib.parse.urlsplit(url)
        pedido = {
            "metodo": metodo,
            "caminho": partes.path,
            "params": dict(urllib.parse.parse_qsl(partes.query, keep_blank_values=True)),
            "prefer": prefer,
            "corpo": json.loads(bruto.decode("utf-8")) if bruto else None,
        }
        self.pedidos.append(pedido)
        for regra in list(self._falhas):
            if regra[0](pedido):
                self._falhas.remove(regra)
                modo = regra[1]
                if modo == "grava_e_some":      # gravou, e a resposta se perdeu
                    self._atender(pedido)
                    raise socket.timeout("timed out")
                if modo == "timeout":           # nem chegou ao banco
                    raise socket.timeout("timed out")
                if modo == "sem_corpo":         # 204: o que vem sem return=representation
                    return _Resposta(204, b"")
                if modo == "objeto":            # 200 com corpo que não é lista
                    return _json({"job_id": JOB, "status": "queued"})
                if isinstance(modo, int):
                    raise urllib.error.HTTPError(
                        url, modo, "erro de mentira", {},
                        io.BytesIO(b'{"message":"indisponivel"}'))
                raise AssertionError("modo de falha desconhecido: %r" % (modo,))
        resposta = self._atender(pedido)
        for regra in list(self._depois):
            if regra[0](pedido):
                self._depois.remove(regra)
                regra[1](self)
        return resposta

    def _estranho(self, pedido):
        self.estranhos.append(pedido)
        raise urllib.error.HTTPError(
            pedido["caminho"], 404, "dublê não conhece este pedido", {},
            io.BytesIO(b'{"message":"desconhecido"}'))

    def _atender(self, p):
        c = p["caminho"]
        if c.startswith("/storage/v1/object/list/"):
            if p["metodo"] != "POST":
                return self._estranho(p)
            return _json([{"name": n, "metadata": {"size": len(b)}}
                          for n, b in sorted(self.storage.items())])
        if c == "/rest/v1/rpc/increment_auto_resume_count":
            self.projeto["auto_resume_count"] = int(self.projeto.get("auto_resume_count") or 0) + 1
            return _Resposta(204, b"")
        if not c.startswith("/rest/v1/"):
            return self._estranho(p)
        tabela = c[len("/rest/v1/"):]
        if tabela not in self.tabelas:
            return self._estranho(p)
        filtros = {k: v for k, v in p["params"].items() if k not in self._RESERVADOS}
        try:
            linhas = [l for l in self.tabelas[tabela]
                      if all(_casa(l.get(col), f) for col, f in filtros.items())]
        except _FiltroDesconhecido:
            return self._estranho(p)
        representa = "return=representation" in p["prefer"]
        if p["metodo"] == "GET":
            sel = p["params"].get("select") or "*"
            lim = int(p["params"].get("limit") or 0)
            if lim:
                linhas = linhas[:lim]
            if sel.strip() == "*":
                return _json([dict(l) for l in linhas])
            cols = [s.strip() for s in sel.split(",") if s.strip()]
            return _json([{col: l.get(col) for col in cols} for l in linhas])
        if p["metodo"] == "PATCH":
            for l in linhas:
                l.update(p["corpo"] or {})
            if representa:
                return _json([dict(l) for l in linhas])
            return _Resposta(204, b"")
        if p["metodo"] == "DELETE":
            self.tabelas[tabela] = [l for l in self.tabelas[tabela]
                                    if not any(l is x for x in linhas)]
            if representa:
                return _json([dict(l) for l in linhas])
            return _Resposta(204, b"")
        return self._estranho(p)

    # ── consultas pro julgamento ──────────────────────────────────────────
    def tomadas(self):
        """Os PATCH condicionais em `projects` — os que levam filtro de status."""
        return [p for p in self.pedidos
                if p["metodo"] == "PATCH" and p["caminho"] == "/rest/v1/projects"
                and "status" in p["params"]]

    def deletes_de_itens(self):
        return [p for p in self.pedidos
                if p["metodo"] == "DELETE" and p["caminho"] == "/rest/v1/project_items"]


def _e_tomada(p):
    return (p["metodo"] == "PATCH" and p["caminho"] == "/rest/v1/projects"
            and "status" in p["params"])


def _e_releitura_da_marca(p):
    return (p["metodo"] == "GET" and p["caminho"] == "/rest/v1/projects"
            and p["params"].get("select") == "anexo_em_curso")


def _e_leitura_da_retomada(p):
    return (p["metodo"] == "GET" and p["caminho"] == "/rest/v1/projects"
            and "anexo_em_curso" in (p["params"].get("select") or "")
            and "user_pe_direito" in (p["params"].get("select") or ""))


# ══════════════════════════════════════════════════════════════════════════
#  O motor de mentira e a thread que dispara na hora
# ══════════════════════════════════════════════════════════════════════════
class _Motor(object):
    """Faz as vezes de `_process_job_throttled`. Guarda o que viu NO INSTANTE
    do disparo: o store local (`jobs`) e a linha do projeto no banco."""

    def __init__(self, banco):
        self.banco = banco
        self.disparos = []

    def __call__(self, job_id, file_paths, work_dir, *a, **k):
        try:
            local = main.jobs[job_id].status if job_id in main.jobs else None
        except Exception as e:           # pragma: no cover — só pra não mascarar
            local = "ilegível: %r" % (e,)
        self.disparos.append({
            "job_id": job_id,
            "arquivos": sorted(os.path.basename(p) for p in file_paths),
            "kw": dict(k),
            "store_local": local,
            "linha": dict(self.banco.projeto),
        })


def _thread_sincrona_para(monkeypatch, alvos):
    """`threading.Thread(...).start()` roda NA HORA quando o alvo é o motor.

    🔑 Assim "semeia o store ANTES do disparo" vira determinístico: se alguém
    mover a semeadura pra depois do `.start()`, o motor olha o store vazio —
    toda vez, não só quando a thread perde a corrida. Qualquer outra thread
    (executor do asyncio, alerta pro Pedro) segue real.
    """
    _Real = threading.Thread

    class _Thread(_Real):
        def start(self, *a, **k):
            if any(getattr(self, "_target", None) is alvo for alvo in alvos):
                self._target(*self._args, **self._kwargs)
                return None
            return _Real.start(self, *a, **k)

    monkeypatch.setattr(threading, "Thread", _Thread)


# ══════════════════════════════════════════════════════════════════════════
#  O ambiente
# ══════════════════════════════════════════════════════════════════════════
def _projeto(**muda):
    linha = {
        "job_id": JOB, "status": "done", "error_message": None,
        "anexo_em_curso": None, "typology": "office",
        "project_type": "arquitetura", "user_total_area": 0,
        "user_pe_direito": 0, "user_email": EMAIL, "user_name": "cliente-nn",
        "project_name": "obra de teste", "parent_job_id": None,
        "auto_resume_count": 0, "warnings": [],
    }
    linha.update(muda)
    return linha


def _itens(n=3):
    return [{"id": i, "job_id": JOB, "confidence": "estimado",
             "description": "piso cerâmico %d" % i} for i in range(1, n + 1)]


@pytest.fixture
def ambiente(monkeypatch, tmp_path):
    """Monta o banco de mentira e troca rede, Storage, e-mail e motor."""
    def _montar(projeto=None, itens=None, storage=None):
        banco = _Banco(projeto or _projeto(),
                       _itens() if itens is None else itens,
                       storage)
        monkeypatch.setattr(urllib.request, "urlopen", banco.urlopen)
        monkeypatch.setattr(main, "WORK_DIR", str(tmp_path / "work"))
        monkeypatch.setattr(main, "JOBS_FILE", str(tmp_path / "_jobs.json"))
        monkeypatch.setattr(main, "_supa_log", lambda *a, **k: None)

        banco.logs = []
        monkeypatch.setattr(main, "_log_error",
                            lambda *a, **k: banco.logs.append(a))
        monkeypatch.setattr(main, "_notify_admin", lambda *a, **k: True)
        monkeypatch.setattr(main, "_require_project_owner", lambda *a, **k: None)
        monkeypatch.setattr(main, "_rate_limit_ok", lambda *a, **k: True)

        # A RPC de status: gravada à parte, pra provar que o status da trava
        # NÃO vai por ela (ela grava sem olhar o status anterior).
        banco.updates = []

        def _update(tabela, col, val, dados, *a, **k):
            banco.updates.append((tabela, col, val, dict(dados)))
            if tabela == "projects":
                banco.projeto.update(dados)
            return True
        monkeypatch.setattr(main, "_supabase_update", _update)
        monkeypatch.setattr(main, "_avisos_com",
                            lambda job_id, novos, *a, **k: list(novos) if isinstance(novos, list) else [novos])

        def _sobe(caminho, job_id, nome, *a, **k):
            with open(caminho, "rb") as f:
                banco.storage[nome] = f.read()
            if banco.ao_subir:
                acao, banco.ao_subir = banco.ao_subir, None
                acao(banco)
            return True
        monkeypatch.setattr(main, "_supabase_storage_upload_prancha", _sobe)
        banco.baixados = []

        def _baixa(job_id, nome, *a, **k):
            banco.baixados.append(nome)
            return banco.storage.get(nome)
        monkeypatch.setattr(main, "_supabase_storage_download_prancha", _baixa)

        motor = _Motor(banco)
        monkeypatch.setattr(main, "_process_job_throttled", motor)
        _thread_sincrona_para(monkeypatch, [motor])
        banco.motor = motor
        return banco
    return _montar


class _Upload(object):
    """O mínimo que `_stream_upload_to_disk` usa: filename, seek, read(n)."""

    def __init__(self, filename, conteudo):
        self.filename = filename
        self._b = conteudo
        self._i = 0

    async def seek(self, n, *a, **k):
        self._i = n

    async def read(self, n=-1, *a, **k):
        if n is None or n < 0:
            n = len(self._b) - self._i
        pedaco = self._b[self._i:self._i + n]
        self._i += len(pedaco)
        return pedaco


class _Request(object):
    headers = {}
    client = None
    query_params = {}


def _anexar(arquivos=(("planta-nova.dxf", DXF),)):
    ups = [_Upload(n, c) for n, c in arquivos]
    return asyncio.run(main.add_file_and_reprocess(JOB, _Request(), files=ups))


def _banco_do_anexo(ambiente):
    """Projeto pronto (done), com planilha estimada e o PDF original guardado."""
    return ambiente(projeto=_projeto(status="done"),
                    storage={"planta-original.pdf": PDF})


# ══════════════════════════════════════════════════════════════════════════
#  0. O dublê não pode ser um "sempre ganha"
# ══════════════════════════════════════════════════════════════════════════
def test_PRECONDICAO_o_banco_de_mentira_aplica_o_filtro_e_o_prefer(ambiente):
    """Se este teste cair, todos os de baixo passam por construção: um PATCH
    que "ganha" sem casar o status é exatamente o dublê que desarma a trava."""
    import main as _m
    banco = ambiente(projeto=_projeto(status="processing"))
    st, js = _m._supa_rest_service(
        "PATCH", "projects", body={"status": "queued"},
        params={"job_id": "eq." + JOB, "status": LIVRE},
        prefer="return=representation")
    assert (st, js) == (200, []), "o dublê casou um status que o filtro exclui"
    assert banco.projeto["status"] == "processing"

    banco.projeto["status"] = "done"
    st, js = _m._supa_rest_service(
        "PATCH", "projects", body={"status": "queued"},
        params={"job_id": "eq." + JOB, "status": LIVRE},
        prefer="return=representation")
    assert st == 200 and isinstance(js, list) and len(js) == 1, (st, js)
    assert banco.projeto["status"] == "queued"

    st, js = _m._supa_rest_service(
        "PATCH", "projects", body={"status": "done"},
        params={"job_id": "eq." + JOB}, prefer="return=minimal")
    assert (st, js) == (204, None), "sem return=representation o PostgREST não devolve corpo"
    assert banco.estranhos == []


# ══════════════════════════════════════════════════════════════════════════
#  1. _tomar_o_projeto — os três resultados
# ══════════════════════════════════════════════════════════════════════════
_CAMPOS = {"status": "queued", "error_message": None, "anexo_em_curso": "pedido0meu"}


@pytest.mark.parametrize("filtro,status_no_banco,esperado", [
    (LIVRE, "done", "ganhou"),
    (LIVRE, "error", "ganhou"),
    (LIVRE, "queued", "perdeu"),
    (LIVRE, "processing", "perdeu"),
    ("eq.error", "error", "ganhou"),        # o filtro da retomada: o status que ela VIU
    ("eq.error", "queued", "perdeu"),       # a rota gravou antes: a retomada não passa
])
def test_tomar_o_projeto_ganha_so_quando_o_status_casa(
        ambiente, filtro, status_no_banco, esperado):
    banco = ambiente(projeto=_projeto(status=status_no_banco))
    antes = dict(banco.projeto)

    r = main._tomar_o_projeto(JOB, filtro, dict(_CAMPOS))

    assert r == esperado, (
        "status %r com filtro %r deu %r — %s" % (
            status_no_banco, filtro, r,
            "dois motores no mesmo projeto" if r == "ganhou" else
            "a trava recusou um projeto livre"))
    if esperado == "ganhou":
        assert banco.projeto["status"] == "queued"
        assert banco.projeto["anexo_em_curso"] == "pedido0meu"
    else:
        assert banco.projeto == antes, "quem perdeu a trava gravou por cima do vencedor"
    assert banco.estranhos == []


def test_tomar_o_projeto_manda_o_filtro_de_status_o_prefer_e_os_campos(ambiente):
    banco = ambiente(projeto=_projeto(status="done"))
    main._tomar_o_projeto(JOB, LIVRE, dict(_CAMPOS))

    tomadas = banco.tomadas()
    assert len(tomadas) == 1, banco.pedidos
    t = tomadas[0]
    assert t["params"] == {"job_id": "eq." + JOB, "status": LIVRE}, (
        "o PATCH saiu sem o filtro de status na URL: %r — gravação sem "
        "condição é o defeito de 21/09" % (t["params"],))
    assert "return=representation" in t["prefer"], (
        "sem return=representation o PostgREST devolve 204 vazio e não dá "
        "pra contar se a linha mudou: %r" % (t["prefer"],))
    assert t["corpo"] == _CAMPOS


@pytest.mark.parametrize("modo,gravou", [
    (503, False),               # banco respondeu erro
    ("timeout", False),         # nem chegou
    ("grava_e_some", True),     # gravou e a resposta se perdeu
    ("sem_corpo", False),       # 204 — não dá pra contar linha
    ("objeto", False),          # 200 com corpo que não é lista
])
def test_tomar_o_projeto_na_duvida_diz_incerto(ambiente, modo, gravou):
    """🪤 "incerto" não é "perdeu": pode ter gravado (a resposta sumiu DEPOIS).
    Quem chama decide relendo a marca — nunca assume que ganhou."""
    banco = ambiente(projeto=_projeto(status="done"))
    banco.falhar(_e_tomada, modo)

    r = main._tomar_o_projeto(JOB, LIVRE, dict(_CAMPOS))

    assert r == "incerto", "resposta %r virou %r" % (modo, r)
    assert (banco.projeto["anexo_em_curso"] == "pedido0meu") is gravou


# ══════════════════════════════════════════════════════════════════════════
#  2. A ROTA /add-file de verdade
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_rota_ganha_a_trava_e_dispara_como_complemento(ambiente):
    banco = _banco_do_anexo(ambiente)

    r = _anexar()

    assert r["status"] == "ok", r
    assert len(banco.motor.disparos) == 1, "a rota ganhou a trava e não disparou o motor"
    d = banco.motor.disparos[0]
    assert d["job_id"] == JOB
    assert d["kw"].get("is_complement") is True, (
        "o anexo rodou como upload normal: %r — sem is_complement a planilha "
        "que o cliente já tinha deixa de ser preservada" % (d["kw"],))
    assert d["arquivos"] == ["planta-nova.dxf"]
    # revisão final (21/09): o motor sabe o que foi anexado AGORA — é o que
    # impede o e-mail de chamar o CAD do projeto de "o que você anexou"
    assert d["kw"].get("anexados") == ["planta-nova.dxf"], d["kw"]

    # a marca vai no MESMO PATCH do status — não numa gravação separada
    tomadas = banco.tomadas()
    assert len(tomadas) == 1, tomadas
    t = tomadas[0]
    assert t["params"].get("status") == LIVRE, t["params"]
    assert "return=representation" in t["prefer"]
    assert t["corpo"].get("status") == "queued"
    assert "error_message" in t["corpo"] and t["corpo"]["error_message"] is None
    anexo_id = t["corpo"].get("anexo_em_curso")
    assert isinstance(anexo_id, str) and anexo_id, (
        "o PATCH do status não levou a marca do anexo: %r" % (t["corpo"],))
    outras = [p for p in banco.pedidos
              if p["metodo"] == "PATCH" and p is not t
              and "anexo_em_curso" in (p["corpo"] or {})]
    assert not outras, "a marca foi gravada separada do status: %r" % outras
    assert not [u for u in banco.updates if "status" in u[3]], (
        "o status foi (também) pela RPC, que grava sem olhar o status "
        "anterior: %r" % banco.updates)

    # no instante do disparo: banco tomado e store local semeado
    assert d["linha"]["status"] == "queued"
    assert d["linha"]["anexo_em_curso"] == anexo_id
    assert d["store_local"] == "queued", (
        "o motor foi disparado com o store local em %r — a semeadura tem que "
        "vir ANTES do disparo (a varredura pula quem está vivo aqui)"
        % (d["store_local"],))
    assert banco.estranhos == []


def test_rota_PERDE_a_trava_409_sem_disparar_nem_semear(ambiente):
    """🩸 O caso de 21/09: a rota leu "done", e enquanto o arquivo subia a
    varredura relançou o projeto. A gravação condicional não casa → 409."""
    banco = _banco_do_anexo(ambiente)

    def _a_varredura_relancou(b):
        b.projeto.update(status="queued", error_message=None)
    banco.ao_subir = _a_varredura_relancou

    with pytest.raises(main.HTTPException) as e:
        _anexar()

    assert e.value.status_code == 409, e.value.detail
    assert "começou a processar" in str(e.value.detail), (
        "o 409 não é o da trava (é outro 409 da rota): %r" % (e.value.detail,))
    assert len(banco.tomadas()) == 1, "a rota nem tentou tomar o projeto"
    assert banco.motor.disparos == [], "segundo motor no mesmo projeto"
    assert JOB not in main.jobs, "quem perdeu a trava semeou o store local"
    assert banco.projeto["anexo_em_curso"] is None, (
        "quem perdeu carimbou a marca por cima do motor que ganhou")
    assert banco.projeto["status"] == "queued"
    assert "planta-nova.dxf" in banco.storage, (
        "o 409 diz que os arquivos ficaram guardados — e não ficaram")
    assert banco.estranhos == []


def test_rota_INCERTA_que_relê_o_proprio_id_segue_e_dispara(ambiente):
    """A gravação aconteceu e a resposta se perdeu: a releitura da marca mostra
    o id DESTE pedido — o projeto é dele, segue."""
    banco = _banco_do_anexo(ambiente)
    banco.falhar(_e_tomada, "grava_e_some")

    r = _anexar()

    assert r["status"] == "ok", r
    i_tomada = next(i for i, p in enumerate(banco.pedidos) if _e_tomada(p))
    releituras = [i for i, p in enumerate(banco.pedidos) if _e_releitura_da_marca(p)]
    assert releituras and releituras[0] > i_tomada, (
        "a resposta se perdeu e a rota não releu a marca")
    assert len(banco.motor.disparos) == 1, (
        "a gravação valeu e a rota desistiu: projeto preso em 'queued' sem motor")
    d = banco.motor.disparos[0]
    assert d["kw"].get("is_complement") is True
    assert d["store_local"] == "queued"
    assert d["linha"]["anexo_em_curso"] == banco.tomadas()[0]["corpo"]["anexo_em_curso"]
    assert banco.estranhos == []


def test_rota_INCERTA_que_relê_OUTRO_id_devolve_503_sem_disparar(ambiente):
    """Outro pedido de anexo (clique duplo) ganhou no meio do upload, e a
    resposta do nosso PATCH se perdeu. A marca relida é a DELE → 503."""
    banco = _banco_do_anexo(ambiente)

    def _outro_pedido_ganhou(b):
        b.projeto.update(status="queued", anexo_em_curso="outro0pedido")
    banco.ao_subir = _outro_pedido_ganhou
    banco.falhar(_e_tomada, "timeout")

    with pytest.raises(main.HTTPException) as e:
        _anexar()

    assert e.value.status_code == 503, e.value.detail
    assert any(_e_releitura_da_marca(p) for p in banco.pedidos), (
        "a rota recusou sem reler — nem tentou saber se tinha gravado")
    assert banco.motor.disparos == [], "disparou em cima do motor do outro pedido"
    assert JOB not in main.jobs
    assert banco.projeto["anexo_em_curso"] == "outro0pedido"
    assert banco.estranhos == []


def test_rota_INCERTA_com_releitura_que_falha_devolve_503(ambiente):
    """🪤 Na dúvida dupla (PATCH e releitura sem resposta) não dispara: um
    segundo motor custa mais que o cliente tentar de novo."""
    banco = _banco_do_anexo(ambiente)
    banco.falhar(_e_tomada, "timeout")
    banco.falhar(_e_releitura_da_marca, 500)

    with pytest.raises(main.HTTPException) as e:
        _anexar()

    assert e.value.status_code == 503, e.value.detail
    assert banco.motor.disparos == []
    assert JOB not in main.jobs
    # 🩸 revisão final (21/09): "tente de novo" levava a um 409 FALSO — o
    # arquivo já subiu e o reenvio caía no "esse arquivo já está no projeto"
    assert "Reprocessar" in e.value.detail and "tente de novo" not in e.value.detail


# ══════════════════════════════════════════════════════════════════════════
#  3. A RETOMADA de verdade
# ══════════════════════════════════════════════════════════════════════════
def _banco_da_retomada(ambiente, **muda):
    return ambiente(
        projeto=_projeto(status="error",
                         error_message="⚠ O processamento foi interrompido por um reinício do servidor.",
                         **muda),
        storage={"planta.pdf": PDF})


def _retomar():
    return main._retomar_job_do_storage(JOB, "office", "arquitetura")


def test_CONTROLE_retomada_ganha_a_trava_limpa_e_dispara(ambiente):
    """Upload normal interrompido: a retomada toma o projeto (filtro = o status
    que ela viu), limpa os itens parciais e relança."""
    banco = _banco_da_retomada(ambiente)

    r = _retomar()

    assert r is True, r
    assert len(banco.motor.disparos) == 1, "a retomada ganhou a trava e não relançou"
    d = banco.motor.disparos[0]
    assert d["arquivos"] == ["planta.pdf"]
    assert not d["kw"].get("is_complement"), d["kw"]
    tomadas = banco.tomadas()
    assert len(tomadas) == 1
    assert tomadas[0]["params"].get("status") == "eq.error", (
        "a retomada tem que tomar com o status que VIU: %r" % (tomadas[0]["params"],))
    assert tomadas[0]["corpo"].get("status") == "queued"
    assert "return=representation" in tomadas[0]["prefer"]
    assert len(banco.deletes_de_itens()) == 1 and banco.itens == [], (
        "upload normal retomado tem que limpar os itens parciais")
    assert d["store_local"] == "queued"
    assert banco.estranhos == []


def test_retomada_PERDE_a_trava_ocupado_sem_apagar_nem_disparar(ambiente):
    """🩸 A corrida inversa: a retomada leu "error", e logo depois a rota do
    anexo tomou o projeto. A trava da retomada não casa → "ocupado"; e a
    planilha que o anexo está preservando NÃO é apagada."""
    banco = _banco_da_retomada(ambiente)

    def _a_rota_do_anexo_tomou(b):
        b.projeto.update(status="queued", error_message=None,
                         anexo_em_curso="pedido0rota")
    banco.depois_de(_e_leitura_da_retomada, _a_rota_do_anexo_tomou)

    r = _retomar()

    assert r == "ocupado", (
        "a retomada perdeu a trava e devolveu %r — False faria o chamador "
        "marcar erro e mandar e-mail de falha por cima de um motor vivo" % (r,))
    assert len(banco.tomadas()) == 1, "a retomada nem tentou a trava"
    assert banco.tomadas()[0]["params"].get("status") == "eq.error"
    assert banco.deletes_de_itens() == [], (
        "a retomada que PERDEU apagou project_items — a planilha do cliente")
    assert len(banco.itens) == 3
    assert banco.motor.disparos == [], "segundo motor no mesmo projeto"
    assert banco.projeto["status"] == "queued"
    assert banco.projeto["anexo_em_curso"] == "pedido0rota"
    assert banco.projeto["auto_resume_count"] == 0, (
        "quem não retomou gastou uma tentativa do orçamento de retomada")
    assert banco.estranhos == []


def test_retomada_INCERTA_tambem_fica_ocupada(ambiente):
    """A resposta da trava sumiu: não dá pra saber se o projeto é dela. Não
    apaga, não relança — a próxima volta da varredura (5 min) decide."""
    banco = _banco_da_retomada(ambiente)
    banco.falhar(_e_tomada, "timeout")

    r = _retomar()

    assert r == "ocupado", r
    assert banco.deletes_de_itens() == [] and len(banco.itens) == 3
    assert banco.motor.disparos == []


def test_retomada_com_motor_vivo_aqui_nem_baixa(ambiente):
    """Motor vivo NESTE processo: baixar de novo truncaria (`open(..., "wb")`)
    os arquivos que ele está lendo. Sai antes de tocar no Storage."""
    banco = _banco_da_retomada(ambiente)
    main.jobs[JOB] = ProcessingStatus(job_id=JOB, status="processing", progress=40,
                                      current_step="lendo", total_steps=3)

    r = _retomar()

    assert r == "ocupado", r
    assert banco.baixados == [], "baixou por cima dos arquivos do motor vivo"
    assert not [p for p in banco.pedidos if "/storage/" in p["caminho"]]
    assert banco.tomadas() == [] and banco.deletes_de_itens() == []
    assert banco.motor.disparos == []


def test_CONTROLE_entrada_local_MORTA_nao_segura_a_retomada(ambiente):
    """Controle do de cima: a entrada local que sobrou de um job que morreu
    ("error") não é motor vivo — a retomada tem que seguir."""
    banco = _banco_da_retomada(ambiente)
    main.jobs[JOB] = ProcessingStatus(job_id=JOB, status="error", progress=40,
                                      current_step="caiu", total_steps=3)

    r = _retomar()

    assert r is True, r
    assert banco.baixados == ["planta.pdf"]
    assert len(banco.motor.disparos) == 1


def test_rota_com_contagem_de_medidos_ILEGIVEL_nao_roda_so_PDF(ambiente, monkeypatch):
    """🩸 21/09 (revisão, reproduzido): a trava anti-perda da rota (30/07) era
    `_medidos_antes > 0`, e `_job_medidos_count` devolve -1 quando a leitura
    cai — o -1 passava e o anexo só com PDF rodava sobre uma base que talvez
    fosse medida (regra dura nº1). Sem saber, não roda: 503, sem trava, sem
    motor."""
    banco = _banco_do_anexo(ambiente)
    monkeypatch.setattr(main, "_job_medidos_count", lambda *a, **k: -1)
    with pytest.raises(main.HTTPException) as e:
        _anexar(arquivos=(("detalhe-novo.pdf", PDF + b"% outra prancha"),))
    assert e.value.status_code == 503, e.value.detail
    assert "Reprocessar" in e.value.detail and "tente de novo" not in e.value.detail
    assert banco.tomadas() == [], "tomou o projeto sem saber se havia medição a perder"
    assert banco.motor.disparos == []


def test_CONTROLE_rota_com_ZERO_medidos_segue_so_com_PDF(ambiente, monkeypatch):
    banco = _banco_do_anexo(ambiente)
    monkeypatch.setattr(main, "_job_medidos_count", lambda *a, **k: 0)
    _anexar(arquivos=(("detalhe-novo.pdf", PDF + b"% outra prancha"),))
    assert len(banco.motor.disparos) == 1, "sem medição a perder, o anexo de PDF tem que rodar"
