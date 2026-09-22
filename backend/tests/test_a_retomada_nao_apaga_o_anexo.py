# -*- coding: utf-8 -*-
"""A retomada automática não pode apagar a planilha de quem estava ANEXANDO.

21/09/2026 — conserto "um motor por projeto". A retomada depois de queda
(`_retomar_job_do_storage`) fazia sempre a mesma coisa: baixava TUDO do
Storage, dava DELETE em todos os `project_items` do job e relançava como
upload normal, sem `is_complement`. Para um projeto novo isso é o certo. Para
um ANEXO interrompido por reinício era destruir a planilha que o cliente já
tinha:

  * o DELETE apagava a planilha-base sem arquivar (e as revisões do cliente
    iam junto pelo CASCADE);
  * sem `is_complement`, as guardas "base preservada" (CAD que não abre,
    0 item, teto de páginas) paravam de valer — elas dependem de a base
    existir;
  * PDF e CAD iam juntos pro motor, que é o que duplica quantidade (a rota
    do anexo manda só os CADs).

E a varredura corria contra a rota do anexo: lia "error", o cliente anexava,
a rota gravava "queued", e a varredura relançava por cima — dois motores no
mesmo job_id, IA paga duas vezes, dois e-mails.

Por que estes testes EXECUTAM a função em vez de ler o fonte: a decisão
"é anexo?" depende do que o banco responde, a trava depende de o PATCH casar
o filtro, e a retomada devolve um terceiro valor ("ocupado") que é truthy de
propósito. Nada disso aparece lendo texto.

Armadilha que este arquivo evita: um dublê de `urlopen` que devolve a mesma
linha pra qualquer pedido faz a trava SEMPRE ganhar, e o caso do perdedor
nunca roda. Por isso o banco de mentira abaixo avalia os filtros do PostgREST
(`eq.`, `in.`, `not.`, `is.`, `gte.`), respeita `Prefer: return=representation`
e só devolve a linha que casou. Há um teste de controle do PRÓPRIO dublê
provando que ele faz a trava perder.

O que é real aqui: `_retomar_job_do_storage` inteira, `_supa_rest_service`,
`_tomar_o_projeto`, `_job_medidos_count`, `_escolher_cads_do_anexo` (lendo o
conteúdo do arquivo no disco), o `JobsStore` (num arquivo temporário),
`_auto_retry_erros_transitorios` e `_recover_stuck_jobs_on_startup`.
Substituídos: a rede (`urllib.request.urlopen`), o download do Storage, o
disparo do motor, `_log_error` e, nos chamadores, os e-mails.
"""
import io
import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main  # noqa: E402

#: job_id e e-mail fictícios — o repositório é público.
JOB = "0000feed-2109-4000-8000-000000000021"
EMAIL = "cliente-nn@example.com"
ANEXO = "anexo-0000-teste"

_PDF = b"%PDF-1.4\n% prancha de mentira\n"
_DXF = b"0\r\nSECTION\r\n2\r\nHEADER\r\n0\r\nENDSEC\r\n0\r\nEOF\r\n"
_DWG = b"AC1027" + b"\x00" * 58
_CONTEUDO = {".pdf": _PDF, ".dxf": _DXF, ".dwg": _DWG}

_ERRO_PASSAGEIRO = "Processamento interrompido por reinício do servidor."


# ══════════════════════════════════════════════════════════════════════════
#  O banco de mentira — um PostgREST mínimo que AVALIA os filtros
# ══════════════════════════════════════════════════════════════════════════
class _FiltroDesconhecido(Exception):
    pass


def _casa(valor, expr):
    """Um filtro do PostgREST aplicado a um valor de coluna.

    Só os operadores que o código percorrido usa. Operador desconhecido é
    defeito DO DUBLÊ, e vira `inesperados` (o teste reprova) em vez de casar
    por acaso.
    """
    if expr.startswith("not."):
        return not _casa(valor, expr[4:])
    op, _, arg = expr.partition(".")
    if op == "eq":
        return valor is not None and str(valor) == arg
    if op == "in":
        return valor is not None and str(valor) in arg.strip("()").split(",")
    if op == "is":
        if arg == "null":
            return valor is None
        if arg == "true":
            return valor is True
        if arg == "false":
            return valor is False
    if op == "gte":
        return valor is not None and str(valor) >= arg
    raise _FiltroDesconhecido(expr)


def _projeta(linha, select):
    if not select or select == "*":
        return dict(linha)
    return {c: linha.get(c) for c in select.split(",")}


class _Resp(object):
    def __init__(self, codigo, corpo=b""):
        self.status = codigo
        self._corpo = corpo

    def getcode(self):
        return self.status

    def read(self, *a, **k):
        return self._corpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _json(dados, codigo=200):
    return _Resp(codigo, json.dumps(dados).encode("utf-8"))


class _Banco(object):
    """Projects + project_items + a listagem do Storage, em memória."""

    _OPCOES = ("select", "limit", "order", "offset")

    def __init__(self, projeto, itens=(), storage=()):
        self.projetos = [dict(projeto)] if projeto else []
        self.itens = [dict(i) for i in itens]
        self.storage = {JOB: list(storage)}
        self.diario = []          # (metodo, tabela, filtros, corpo)
        self.inesperados = []
        self.falha = {}           # (metodo, tabela) -> código HTTP ou "rede"
        #: o que OUTRO ator grava entre a leitura da retomada e a trava dela
        self.antes_do_patch = None

    def chamadas(self, metodo, tabela):
        return [c for c in self.diario if c[0] == metodo and c[1] == tabela]

    def indice(self, metodo, tabela):
        for n, c in enumerate(self.diario):
            if c[0] == metodo and c[1] == tabela:
                return n
        return None

    def urlopen(self, req, *a, **k):
        if isinstance(req, str):
            req = urllib.request.Request(req)
        partes = urllib.parse.urlsplit(req.full_url)
        metodo = req.get_method()
        caminho = urllib.parse.unquote(partes.path)
        if caminho.startswith("/rest/v1/"):
            tabela = caminho[len("/rest/v1/"):]
        elif caminho.startswith("/storage/v1/object/list/"):
            tabela = "storage:list"
        else:
            tabela = caminho
        pares = urllib.parse.parse_qsl(partes.query, keep_blank_values=True)
        filtros = {c: v for c, v in pares if c not in self._OPCOES}
        opcoes = {c: v for c, v in pares if c in self._OPCOES}
        corpo = json.loads(req.data.decode("utf-8")) if req.data else None
        self.diario.append((metodo, tabela, filtros, corpo))

        falha = self.falha.get((metodo, tabela))
        if falha == "rede":
            raise urllib.error.URLError("conexão recusada (dublê)")
        if falha:
            raise urllib.error.HTTPError(req.full_url, falha, "erro do dublê", {},
                                         io.BytesIO(b'{"message":"dubl\xc3\xaa"}'))
        try:
            resp = self._responde(metodo, tabela, filtros, opcoes, corpo, req)
        except _FiltroDesconhecido as e:
            resp = None
            self.inesperados.append("filtro desconhecido %r em %s %s" % (str(e), metodo, tabela))
        if resp is None:
            if not self.inesperados or tabela not in self.inesperados[-1]:
                self.inesperados.append("%s %s %r" % (metodo, tabela, filtros))
            raise urllib.error.HTTPError(req.full_url, 404, "dublê não conhece", {},
                                         io.BytesIO(b"{}"))
        return resp

    def _filtra(self, linhas, filtros):
        return [l for l in linhas
                if all(_casa(l.get(c), v) for c, v in filtros.items())]

    def _responde(self, metodo, tabela, filtros, opcoes, corpo, req):
        if tabela == "storage:list" and metodo == "POST":
            prefixo = ((corpo or {}).get("prefix") or "").rstrip("/")
            return _json([{"name": n} for n in self.storage.get(prefixo, [])])

        if tabela == "rpc/increment_auto_resume_count" and metodo == "POST":
            for l in self.projetos:
                if l.get("job_id") == (corpo or {}).get("p_job_id"):
                    l["auto_resume_count"] = int(l.get("auto_resume_count") or 0) + 1
            return _Resp(204, b"")

        if tabela == "rpc/list_stuck_jobs" and metodo == "POST":
            return _json([{"job_id": l["job_id"], "status": l["status"],
                           "created_at": l["created_at"]}
                          for l in self.projetos
                          if l.get("status") in ("queued", "processing")])

        if tabela not in ("projects", "project_items"):
            return None
        linhas = self.projetos if tabela == "projects" else self.itens

        if metodo == "GET":
            alvo = self._filtra(linhas, filtros)
            if "limit" in opcoes:
                alvo = alvo[:int(opcoes["limit"])]
            return _json([_projeta(l, opcoes.get("select")) for l in alvo])

        if metodo == "PATCH":
            if tabela == "projects" and self.antes_do_patch:
                gancho, self.antes_do_patch = self.antes_do_patch, None
                gancho(self)
            alvo = self._filtra(linhas, filtros)
            for l in alvo:
                l.update(corpo or {})
            if "return=representation" in (req.get_header("Prefer") or ""):
                return _json([dict(l) for l in alvo])
            return _Resp(204, b"")

        if metodo == "DELETE":
            for l in self._filtra(linhas, filtros):
                linhas.remove(l)
            return _Resp(204, b"")
        return None


def _projeto(**mudar):
    linha = {
        "job_id": JOB, "parent_job_id": None, "status": "error",
        "error_message": _ERRO_PASSAGEIRO, "anexo_em_curso": None,
        "user_total_area": 0, "user_pe_direito": 0,
        "typology": "residential", "project_type": "arquitetura",
        "auto_resume_count": 0, "archived": False, "is_eval": False,
        "user_email": EMAIL, "project_name": "Projeto de teste nn",
        "created_at": (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z",
    }
    linha.update(mudar)
    return linha


def _itens(confirmados=2, estimados=1):
    """A planilha-base: o que o cliente JÁ tem e não pode perder."""
    return ([{"id": 1 + n, "job_id": JOB, "confidence": "confirmado"}
             for n in range(confirmados)]
            + [{"id": 100 + n, "job_id": JOB, "confidence": "estimado"}
               for n in range(estimados)])


# ══════════════════════════════════════════════════════════════════════════
#  A bancada que roda a retomada de verdade
# ══════════════════════════════════════════════════════════════════════════
class _Cena(object):
    def __init__(self, banco):
        self.banco = banco
        self.baixados = []
        self.disparos = []
        self.disparou = threading.Event()
        self.logs = []
        self.mantidas = []
        self.alertas = []
        self.ret = None

    def esperar_disparo(self):
        return self.disparou.wait(5.0)

    def nao_disparou(self):
        # o disparo é numa thread: dá um fôlego pra ela aparecer, se existir
        return (not self.disparou.wait(0.3)) and not self.disparos


def _armar(monkeypatch, tmp_path, banco, local=None):
    cena = _Cena(banco)
    monkeypatch.setattr(urllib.request, "urlopen", banco.urlopen)
    monkeypatch.setattr(main, "WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setattr(main, "JOBS_FILE", str(tmp_path / "_jobs.json"))
    monkeypatch.setattr(main, "_supa_log", lambda *a, **k: None)

    def _baixa(job_id, nome, *a, **k):
        cena.baixados.append(nome)
        return _CONTEUDO[os.path.splitext(nome)[1].lower()]
    monkeypatch.setattr(main, "_supabase_storage_download_prancha", _baixa)

    def _dispara(*a, **k):
        cena.disparos.append({
            "job_id": a[0] if a else k.get("job_id"),
            "arquivos": sorted(os.path.basename(p) for p in (a[1] if len(a) > 1 else [])),
            "kw": dict(k)})
        cena.disparou.set()
    monkeypatch.setattr(main, "_process_job_throttled", _dispara)

    def _log(stage, *a, **k):
        cena.logs.append(stage)
    monkeypatch.setattr(main, "_log_error", _log)

    def _mantem(*a, **k):
        cena.mantidas.append(a)
        return True
    monkeypatch.setattr(main, "_anexo_falhou_mantem_a_base", _mantem)

    if local:
        main.jobs[JOB] = main.ProcessingStatus(
            job_id=JOB, status=local, progress=40, current_step="lendo pranchas")
    return cena


def _retomar(monkeypatch, tmp_path, *, projeto=None, itens=None,
             storage=("arquitetura.pdf", "forro.dxf"), local=None,
             antes_do_patch=None, falha=None):
    banco = _Banco(_projeto(**(projeto or {})) if projeto is not False else None,
                   _itens() if itens is None else itens, storage)
    banco.antes_do_patch = antes_do_patch
    banco.falha.update(falha or {})
    cena = _armar(monkeypatch, tmp_path, banco, local=local)
    cena.ret = main._retomar_job_do_storage(JOB, "residential", "arquitetura")
    return cena


def _a_rota_do_anexo_tomou_o_projeto(banco):
    """O que a rota /add-file grava quando vence a trava dela."""
    banco.projetos[0].update({"status": "queued", "error_message": None,
                              "anexo_em_curso": "anexo-da-rota"})


# ══════════════════════════════════════════════════════════════════════════
#  0. Controle do PRÓPRIO dublê: a trava tem que poder perder
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_o_banco_de_mentira_faz_a_trava_PERDER(monkeypatch):
    """Sem isto, todo teste de "a trava perdeu" abaixo poderia ser verde por
    um dublê que devolve linha pra qualquer PATCH — a trava sempre ganharia e
    o ramo do perdedor nunca rodaria."""
    banco = _Banco(_projeto(status="queued"))
    monkeypatch.setattr(urllib.request, "urlopen", banco.urlopen)
    monkeypatch.setattr(main, "_supa_log", lambda *a, **k: None)

    assert main._tomar_o_projeto(JOB, "not.in.(queued,processing)",
                                 {"status": "queued"}) == "perdeu"
    assert main._tomar_o_projeto(JOB, "eq.error", {"status": "queued"}) == "perdeu"
    banco.projetos[0]["status"] = "error"
    assert main._tomar_o_projeto(JOB, "eq.error", {"status": "queued"}) == "ganhou"
    assert banco.projetos[0]["status"] == "queued"
    banco.falha[("PATCH", "projects")] = 500
    assert main._tomar_o_projeto(JOB, "eq.queued", {"status": "queued"}) == "incerto"
    assert banco.inesperados == []


# ══════════════════════════════════════════════════════════════════════════
#  1. Anexo interrompido volta como ANEXO — e a planilha fica
# ══════════════════════════════════════════════════════════════════════════
def test_anexo_interrompido_retoma_como_ANEXO_sem_apagar_a_planilha(monkeypatch, tmp_path):
    """O caso do conserto: projeto com planilha, cliente anexou, o servidor
    reiniciou no meio. A retomada tem que relançar como complemento, só com
    o CAD, e sem tocar nos itens que o cliente já tem."""
    cena = _retomar(monkeypatch, tmp_path,
                    projeto={"anexo_em_curso": ANEXO, "user_total_area": 250.5,
                             "user_pe_direito": 2.9})
    banco = cena.banco

    assert cena.ret is True, "a retomada do anexo não relançou (devolveu %r)" % (cena.ret,)
    assert cena.esperar_disparo(), "o motor não foi disparado"
    assert banco.chamadas("DELETE", "project_items") == [], (
        "a retomada de um ANEXO apagou os project_items — é a planilha que o "
        "cliente já tinha, e as revisões dele iam junto pelo CASCADE")
    assert len(banco.itens) == 3, "a planilha-base encolheu: %r" % banco.itens

    (d,) = cena.disparos
    assert d["kw"].get("is_complement") is True, (
        "relançou como upload normal — as guardas de 'base preservada' deixam "
        "de valer: %r" % d["kw"])
    assert d["arquivos"] == ["forro.dxf"], (
        "o anexo tem CAD e o motor recebeu %r — PDF junto com CAD duplica a "
        "quantidade (a rota manda só os CADs)" % d["arquivos"])
    assert d["kw"].get("user_total_area") == 250.5
    assert d["kw"].get("user_pe_direito") == 2.9

    (patch,) = banco.chamadas("PATCH", "projects")
    assert patch[2] == {"job_id": "eq." + JOB, "status": "eq.error"}, (
        "a trava não condicionou ao status visto: %r" % (patch[2],))
    assert patch[3] == {"status": "queued", "error_message": None}
    assert banco.projetos[0]["anexo_em_curso"] == ANEXO, (
        "a trava da retomada apagou a marca do anexo — o fim do complemento "
        "não saberia mais que era anexo")
    assert banco.inesperados == []


def test_CONTROLE_sem_anexo_apaga_os_parciais_e_retoma_como_upload(monkeypatch, tmp_path):
    """O outro lado: job comum interrompido. Os itens são PARCIAIS da rodada
    que caiu — apagar é a idempotência que sempre existiu, e o motor recebe
    todos os arquivos."""
    cena = _retomar(monkeypatch, tmp_path,
                    projeto={"user_total_area": 180.0, "user_pe_direito": 3.1})
    banco = cena.banco

    assert cena.ret is True
    assert cena.esperar_disparo()
    deletes = banco.chamadas("DELETE", "project_items")
    assert len(deletes) == 1 and deletes[0][2] == {"job_id": "eq." + JOB}, deletes
    assert banco.itens == [], "os parciais da rodada que caiu não foram limpos"
    assert banco.indice("PATCH", "projects") < banco.indice("DELETE", "project_items"), (
        "apagou os itens ANTES de vencer a trava — se a trava perdesse, o "
        "estrago já estaria feito")

    (d,) = cena.disparos
    assert not d["kw"].get("is_complement"), d["kw"]
    assert d["arquivos"] == ["arquitetura.pdf", "forro.dxf"]
    assert d["kw"].get("user_total_area") == 180.0
    assert d["kw"].get("user_pe_direito") == 3.1
    assert d["kw"].get("typology") == "residential"
    assert banco.projetos[0]["auto_resume_count"] == 1, "o anti-loop não contou a retomada"
    assert banco.inesperados == []


@pytest.mark.parametrize("anexo", [ANEXO, None], ids=["anexo", "upload"])
@pytest.mark.parametrize("area,pe,esperado", [
    (312.75, 3.05, (312.75, 3.05)),
    (None, None, (0.0, 0.0)),
], ids=["informados", "nao-informados"])
def test_area_e_pe_direito_informados_chegam_ao_disparo(
        monkeypatch, tmp_path, anexo, area, pe, esperado):
    """A leitura que decide "é anexo?" é a mesma que traz a metragem que o
    cliente digitou (03/08: a retomada perdia calada). Os dois caminhos
    precisam levar os dois números; e o que não foi informado não vira
    número inventado."""
    cena = _retomar(monkeypatch, tmp_path,
                    projeto={"anexo_em_curso": anexo, "user_total_area": area,
                             "user_pe_direito": pe})
    assert cena.ret is True and cena.esperar_disparo()
    kw = cena.disparos[0]["kw"]
    assert (kw.get("user_total_area"), kw.get("user_pe_direito")) == esperado, kw
    assert cena.banco.inesperados == []


# ══════════════════════════════════════════════════════════════════════════
#  2. Na dúvida, NÃO retomar — e devolver "ocupado", não False
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("falha,sem_linha", [
    ({("GET", "projects"): 500}, False),
    ({("GET", "projects"): 503}, False),
    ({("GET", "projects"): "rede"}, False),
    ({}, True),
], ids=["http-500", "http-503", "rede", "projeto-sem-linha"])
def test_leitura_do_projeto_que_falha_NAO_retoma_as_cegas(
        monkeypatch, tmp_path, falha, sem_linha):
    """Sem a leitura não dá pra saber se é anexo. Seguir "no escuro" é tratar
    como upload e apagar a base justamente no soluço do banco. E a resposta
    é "ocupado" — False faria o chamador marcar erro e mandar e-mail."""
    cena = _retomar(monkeypatch, tmp_path,
                    projeto=False if sem_linha else {"anexo_em_curso": ANEXO},
                    falha=falha)
    banco = cena.banco

    assert cena.ret == "ocupado", (
        "leitura do projeto falhou e a retomada devolveu %r" % (cena.ret,))
    assert banco.chamadas("GET", "projects"), "a leitura nem foi tentada"
    assert banco.chamadas("PATCH", "projects") == [], "tomou o projeto sem saber o que ele é"
    assert banco.chamadas("DELETE", "project_items") == []
    assert len(banco.itens) == 3
    assert cena.nao_disparou(), "disparou o motor sem conseguir ler o projeto"
    assert "recovery:retomada-sem-leitura" in cena.logs, cena.logs
    assert banco.inesperados == []


@pytest.mark.parametrize("status", ["done"])
def test_status_que_nao_e_de_retomada_nao_retoma(monkeypatch, tmp_path, status):
    """Entre a varredura ler "error" e a retomada ler de novo, o projeto pode
    ter fechado. Aí não há o que retomar — e nem erro a marcar."""
    cena = _retomar(monkeypatch, tmp_path, projeto={"status": status})
    assert cena.ret == "ocupado"
    assert cena.banco.chamadas("PATCH", "projects") == []
    assert cena.banco.chamadas("DELETE", "project_items") == []
    assert cena.nao_disparou()
    assert cena.banco.inesperados == []


@pytest.mark.parametrize("como", ["perdeu", "incerto"])
def test_a_trava_que_nao_ganha_nao_retoma_nem_apaga(monkeypatch, tmp_path, como):
    """A corrida de 21/09: a retomada leu "error" (sem anexo), e ANTES da trava
    dela a rota do anexo gravou "queued" + a marca. Se a retomada seguisse,
    apagaria os itens — que agora são a base do anexo — e subiria um segundo
    motor. "incerto" (a resposta do PATCH se perdeu) é tratado igual."""
    if como == "perdeu":
        cena = _retomar(monkeypatch, tmp_path,
                        antes_do_patch=_a_rota_do_anexo_tomou_o_projeto)
    else:
        cena = _retomar(monkeypatch, tmp_path, falha={("PATCH", "projects"): 500})
    banco = cena.banco

    assert cena.ret == "ocupado", "a trava deu %s e a retomada devolveu %r" % (como, cena.ret)
    assert banco.chamadas("PATCH", "projects"), "a trava nem foi tentada"
    assert banco.chamadas("DELETE", "project_items") == [], (
        "apagou os itens sem ter vencido a trava")
    assert len(banco.itens) == 3
    assert cena.nao_disparou(), "subiu um segundo motor no mesmo projeto"
    assert banco.chamadas("POST", "rpc/increment_auto_resume_count") == []
    assert "recovery:retomada-ocupada" in cena.logs, cena.logs
    if como == "perdeu":
        assert banco.projetos[0]["anexo_em_curso"] == "anexo-da-rota"
        assert banco.projetos[0]["status"] == "queued", "a retomada gravou por cima da rota"
    assert banco.inesperados == []


# ══════════════════════════════════════════════════════════════════════════
#  3. Motor vivo aqui: "ocupado" ANTES de baixar qualquer coisa
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("status_local", ["queued", "processing"])
def test_motor_vivo_no_JobsStore_devolve_ocupado_ANTES_de_baixar(
        monkeypatch, tmp_path, status_local):
    """`open(lp, "wb")` trunca o arquivo que o motor vivo está lendo. A
    checagem tem que vir antes da listagem do Storage — e antes de ler o
    banco, porque não há decisão a tomar."""
    cena = _retomar(monkeypatch, tmp_path, local=status_local)
    assert cena.ret == "ocupado"
    assert cena.baixados == [], "baixou por cima de um motor vivo: %r" % cena.baixados
    assert cena.banco.diario == [], (
        "falou com o banco/Storage antes de desistir: %r" % cena.banco.diario)
    assert cena.nao_disparou()
    assert main.jobs[JOB].status == status_local, "a retomada re-semeou por cima do motor vivo"


@pytest.mark.parametrize("status_local", ["error", "done"])
def test_CONTROLE_entrada_local_MORTA_nao_segura_a_retomada(
        monkeypatch, tmp_path, status_local):
    """Só motor VIVO segura. Uma entrada local de job que já morreu não pode
    impedir a retomada — senão o projeto fica em erro pra sempre."""
    cena = _retomar(monkeypatch, tmp_path, local=status_local)
    assert cena.ret is True, "entrada local %r segurou a retomada" % status_local
    assert sorted(cena.baixados) == ["arquitetura.pdf", "forro.dxf"]
    assert cena.esperar_disparo()
    assert main.jobs[JOB].status == "queued", "o status local não foi re-semeado"
    assert cena.banco.inesperados == []


# ══════════════════════════════════════════════════════════════════════════
#  4. Anexo sem CAD no Storage: a trava anti-perda da rota vale aqui também
# ══════════════════════════════════════════════════════════════════════════
def test_anexo_sem_CAD_com_itens_MEDIDOS_mantem_a_base_e_nao_dispara(monkeypatch, tmp_path):
    """Regra dura nº1: rodar só com PDF trocaria medição por estimativa. A
    retomada devolve a planilha anterior (`_anexo_falhou_mantem_a_base`) e
    não sobe motor nenhum."""
    cena = _retomar(monkeypatch, tmp_path, projeto={"anexo_em_curso": ANEXO},
                    storage=("arquitetura.pdf",), itens=_itens(confirmados=2))
    banco = cena.banco

    assert cena.ret == "ocupado", cena.ret
    contagem = [c for c in banco.chamadas("GET", "project_items")
                if c[2].get("confidence") == "eq.confirmado"]
    assert contagem, "não contou os itens medidos antes de decidir"
    assert len(cena.mantidas) == 1, "a base não foi mantida: %r" % cena.mantidas
    job, motivo = cena.mantidas[0][0], cena.mantidas[0][1]
    assert (job, motivo) == (JOB, "interrompido"), cena.mantidas[0]
    assert "planilha anterior foi mantida" in cena.mantidas[0][2]
    # 21/09: a trava vem ANTES da decisão (quem perde a trava não pode gravar
    # "done" por cima de um motor vivo) — então a ÚNICA gravação no projeto é
    # a própria trava. Rodar, apagar ou disparar continua proibido abaixo.
    patches = banco.chamadas("PATCH", "projects")
    assert len(patches) == 1 and patches[0][3] == {"status": "queued", "error_message": None}, (
        "gravou no projeto algo além da trava: %r" % patches)
    assert banco.chamadas("DELETE", "project_items") == []
    assert len(banco.itens) == 3
    assert cena.nao_disparou(), "subiu o motor só com PDF num projeto que tinha medição"
    assert banco.inesperados == []


def test_CONTROLE_anexo_sem_CAD_e_SEM_medicao_segue_como_anexo(monkeypatch, tmp_path):
    """Sem item medido não há medição a perder: o anexo de PDF segue — como
    complemento, e sem apagar a base."""
    cena = _retomar(monkeypatch, tmp_path, projeto={"anexo_em_curso": ANEXO},
                    storage=("arquitetura.pdf",), itens=_itens(confirmados=0, estimados=4))
    assert cena.ret is True
    assert cena.mantidas == [], "manteve a base sem haver medição a proteger"
    assert cena.esperar_disparo()
    d = cena.disparos[0]
    assert d["arquivos"] == ["arquitetura.pdf"]
    assert d["kw"].get("is_complement") is True
    assert cena.banco.chamadas("DELETE", "project_items") == []
    assert len(cena.banco.itens) == 4
    assert cena.banco.inesperados == []


# ══════════════════════════════════════════════════════════════════════════
#  5. Os CHAMADORES: "ocupado" é silêncio, não re-tentativa nem erro
# ══════════════════════════════════════════════════════════════════════════
def _armar_varredura(monkeypatch, cena):
    monkeypatch.setattr(main, "_email_auto_ja_enviado", lambda *a, **k: False)
    monkeypatch.setattr(main, "_email_auto_registrar", lambda *a, **k: None)
    monkeypatch.setattr(main, "_notify_admin",
                        lambda assunto, corpo=" ", *a, **k: cena.alertas.append(corpo) or True)
    monkeypatch.setattr(main, "_error_log_causa_real", lambda *a, **k: "")
    monkeypatch.setattr(main, "_linha_do_email_ao_cliente", lambda *a, **k: "")


@pytest.mark.parametrize("retorno,retenta,alerta", [
    ("ocupado", False, False),
    (True, True, False),
    (False, False, True),
], ids=["ocupado", "CONTROLE-retomou", "CONTROLE-sem-arquivo"])
def test_a_varredura_trata_OCUPADO_como_silencio(
        monkeypatch, tmp_path, retorno, retenta, alerta):
    """Molde de test_dois_motores: varredura REAL, retomada substituída.

    "ocupado" é truthy de propósito. Sem o ramo próprio, ele cairia no
    `if _ret:` e o log diria "re-tentativa automática 1/2" de uma re-tentativa
    que não aconteceu; tratado como False, viraria alerta de erro terminal
    por cima de um motor vivo. Os dois controles provam que o mesmo teste
    enxerga cada um desses caminhos."""
    banco = _Banco(_projeto(), _itens(), ())
    cena = _armar(monkeypatch, tmp_path, banco)
    _armar_varredura(monkeypatch, cena)
    retomadas = []
    monkeypatch.setattr(main, "_retomar_job_do_storage",
                        lambda j, *a, **k: retomadas.append(j) or retorno)

    main._auto_retry_erros_transitorios()

    assert retomadas == [JOB], "a varredura nem chamou a retomada: %r" % retomadas
    assert ("auto-retry" in cena.logs) is retenta, cena.logs
    assert bool(cena.alertas) is alerta, cena.alertas
    assert banco.inesperados == []


@pytest.mark.parametrize("corrida", [True, False], ids=["rota-venceu", "CONTROLE-sem-corrida"])
def test_varredura_e_retomada_REAIS_quando_a_rota_do_anexo_vence(
        monkeypatch, tmp_path, corrida):
    """O caso de 21/09 de ponta a ponta, sem dublê no meio: a varredura lê o
    projeto em erro, chama a retomada de verdade, e o cliente anexa entre a
    leitura e a trava. Nada de DELETE, nada de segundo motor, nada de alerta.
    Controle: sem a corrida, a mesma bancada retoma e loga a re-tentativa."""
    banco = _Banco(_projeto(), _itens(), ("arquitetura.pdf", "forro.dxf"))
    if corrida:
        banco.antes_do_patch = _a_rota_do_anexo_tomou_o_projeto
    cena = _armar(monkeypatch, tmp_path, banco)
    _armar_varredura(monkeypatch, cena)

    main._auto_retry_erros_transitorios()

    assert cena.alertas == [], "alerta terminal: %r" % cena.alertas
    assert banco.chamadas("PATCH", "projects"), "a retomada real nem chegou à trava"
    if corrida:
        assert "auto-retry" not in cena.logs, "logou re-tentativa que não aconteceu"
        assert "recovery:retomada-ocupada" in cena.logs, cena.logs
        assert banco.chamadas("DELETE", "project_items") == []
        assert len(banco.itens) == 3, "a base do anexo foi apagada"
        assert banco.projetos[0]["anexo_em_curso"] == "anexo-da-rota"
        assert cena.nao_disparou(), "dois motores no mesmo projeto"
    else:
        assert "auto-retry" in cena.logs, cena.logs
        assert cena.esperar_disparo()
        assert banco.itens == []
    assert banco.inesperados == []


@pytest.mark.parametrize("retorno,anexo,erro,mantem", [
    ("ocupado", ANEXO, False, False),
    ("ocupado", None, False, False),
    (False, ANEXO, False, True),
    (False, None, True, False),
], ids=["ocupado-anexo", "ocupado-upload", "CONTROLE-falhou-anexo", "CONTROLE-falhou-upload"])
def test_a_recuperacao_de_startup_nao_marca_erro_por_cima_de_OCUPADO(
        monkeypatch, tmp_path, retorno, anexo, erro, mantem):
    """O outro chamador. "ocupado" não pode virar erro + e-mail de falha, nem
    `_anexo_falhou_mantem_a_base` (que gravaria `done` por cima do motor que
    pegou o projeto). Controles: False com anexo devolve a base; False sem
    anexo marca o erro de sempre."""
    banco = _Banco(_projeto(status="processing", anexo_em_curso=anexo), _itens(), ())
    cena = _armar(monkeypatch, tmp_path, banco)
    updates, emails, resumo = [], [], []
    retomadas = []
    monkeypatch.setattr(main, "_retomar_job_do_storage",
                        lambda j, *a, **k: retomadas.append(j) or retorno)
    monkeypatch.setattr(main, "_supabase_update",
                        lambda *a, **k: updates.append(a) or True)
    monkeypatch.setattr(main, "_email_falha_cliente",
                        lambda *a, **k: emails.append((a, k)))
    monkeypatch.setattr(main, "_notify_admin", lambda *a, **k: True)
    monkeypatch.setattr(main, "_supa_log", lambda linha, *a, **k: resumo.append(linha))

    main._recover_stuck_jobs_on_startup()

    assert retomadas == [JOB], "a recuperação nem chamou a retomada: %r" % retomadas
    marcou_erro = any(len(u) > 3 and (u[3] or {}).get("status") == "error" for u in updates)
    assert marcou_erro is erro, updates
    assert bool(emails) is erro, emails
    assert bool(cena.mantidas) is mantem, cena.mantidas
    # O resumo da varredura diz "N jobs marcados como erro". "ocupado" não é
    # nem retomada nem erro — contá-lo ali é o log mentindo sobre o que fez.
    contou = [l for l in resumo if l.startswith("RECOVERY startup")]
    assert contou and ("recovered=%d" % (0 if retorno == "ocupado" else 1)) in contou[-1], contou
    assert banco.inesperados == []


# ══════════════════════════════════════════════════════════════════════════
#  🩸 21/09 (revisão dos guardas, reproduzido): a rota toma o projeto
#  DURANTE o download da retomada
# ══════════════════════════════════════════════════════════════════════════
def _rota_toma_no_meio_do_download(monkeypatch, cena, semeia_local):
    """Na 1ª prancha baixada pela retomada, a rota do anexo vence a trava
    dela (queued + marca) e, se `semeia_local`, semeia o store local — o que a
    rota faz logo depois de ganhar."""
    original = main._supabase_storage_download_prancha
    feito = []

    def _baixa_e_a_rota_entra(job_id, nome, *a, **k):
        if not feito:
            feito.append(nome)
            _a_rota_do_anexo_tomou_o_projeto(cena.banco)
            if semeia_local:
                main.jobs[JOB] = main.ProcessingStatus(
                    job_id=JOB, status="queued", progress=0,
                    current_step="Refazendo com o novo arquivo")
        return original(job_id, nome, *a, **k)
    monkeypatch.setattr(main, "_supabase_storage_download_prancha", _baixa_e_a_rota_entra)
    return feito


def test_VARREDURA_nao_sobe_segundo_motor_quando_a_rota_entra_no_download(
        monkeypatch, tmp_path):
    """A re-tentativa listou o projeto em ERRO; enquanto a retomada baixa, a
    rota do anexo grava queued + marca. Antes a retomada lia "queued", travava
    com `eq.queued` — que casava com a gravação da própria rota — e subia um
    SEGUNDO motor. Agora a re-tentativa diz de que status partiu (`error`) e
    a retomada recua. O store local fica de fora de propósito: é a trava por
    status, sozinha, que tem que segurar."""
    banco = _Banco(_projeto(), _itens(), ("arquitetura.pdf", "forro.dxf"))
    cena = _armar(monkeypatch, tmp_path, banco)
    _armar_varredura(monkeypatch, cena)
    feito = _rota_toma_no_meio_do_download(monkeypatch, cena, semeia_local=False)

    main._auto_retry_erros_transitorios()

    assert feito, "a rota nem entrou — o teste não provou nada"
    assert cena.nao_disparou(), "dois motores no mesmo projeto"
    assert [c for c in banco.chamadas("PATCH", "projects")
            if (c[3] or {}).get("status") == "queued"] == [], (
        "a retomada tentou travar um projeto que a rota já tinha tomado")
    assert banco.chamadas("DELETE", "project_items") == []
    assert len(banco.itens) == 3
    assert banco.projetos[0]["anexo_em_curso"] == "anexo-da-rota"
    assert cena.alertas == [] and "auto-retry" not in cena.logs, (cena.alertas, cena.logs)


def test_RECUPERACAO_recua_se_o_motor_da_rota_aparece_no_store_durante_o_download(
        monkeypatch, tmp_path):
    """A recuperação procura projeto TRAVADO e aceita "queued" (não passa
    status esperado). Aí quem segura é o store local conferido DE NOVO logo
    antes da trava — a rota o semeia assim que ganha."""
    banco = _Banco(_projeto(status="processing"), _itens(), ("arquitetura.pdf", "forro.dxf"))
    cena = _armar(monkeypatch, tmp_path, banco)
    feito = _rota_toma_no_meio_do_download(monkeypatch, cena, semeia_local=True)

    ret = main._retomar_job_do_storage(JOB, "residential", "arquitetura")

    assert feito, "a rota nem entrou — o teste não provou nada"
    assert ret == "ocupado", ret
    assert cena.nao_disparou(), "dois motores no mesmo projeto"
    assert banco.chamadas("DELETE", "project_items") == []
    assert [c for c in banco.chamadas("PATCH", "projects")
            if (c[3] or {}).get("status") == "queued"] == [], (
        "travou por cima do motor vivo da rota")


def test_CONTROLE_a_varredura_manda_o_status_de_onde_partiu(monkeypatch, tmp_path):
    """Sem este controle, a re-tentativa poderia parar de passar `error` e o
    teste da corrida acima só seria salvo por acaso."""
    banco = _Banco(_projeto(), _itens(), ())
    cena = _armar(monkeypatch, tmp_path, banco)
    _armar_varredura(monkeypatch, cena)
    vistos = []
    monkeypatch.setattr(main, "_retomar_job_do_storage",
                        lambda j, *a, **k: vistos.append(k.get("status_esperado")) or True)
    main._auto_retry_erros_transitorios()
    assert vistos == ["error"], vistos


def test_anexo_sem_CAD_com_contagem_de_medidos_ILEGIVEL_nao_roda_so_PDF(monkeypatch, tmp_path):
    """🩸 21/09 (revisão, reproduzido): `_job_medidos_count` devolve -1 quando a
    leitura cai; "> 0" deixava o -1 seguir e o anexo rodava só com PDF sobre
    uma base medida. Aqui, só "0" segue.
    🩸 revisão final (21/09): e o -1 também não pode ABANDONAR o anexo (ele
    encerrava com "o CAD não pôde ser relido" onde nunca houve CAD): é "não
    sei" — devolve o status e a próxima volta confere de novo."""
    banco = _Banco(_projeto(anexo_em_curso=ANEXO), _itens(confirmados=2), ("arquitetura.pdf",))
    cena = _armar(monkeypatch, tmp_path / "ilegivel", banco)
    monkeypatch.setattr(main, "_job_medidos_count", lambda *a, **k: -1)
    ret = main._retomar_job_do_storage(JOB, "residential", "arquitetura")
    assert ret == "ocupado", ret
    assert cena.nao_disparou(), "rodou só com PDF sem saber se havia medição"
    assert cena.mantidas == [], "abandonou o anexo por um soluço de leitura"
    assert banco.chamadas("DELETE", "project_items") == []
    assert banco.projetos[0]["status"] == "error", "não devolveu o status que a trava tomou"
    assert banco.projetos[0]["anexo_em_curso"] == ANEXO
    assert "recovery:anexo-medidos-ilegivel" in cena.logs, cena.logs


def test_anexo_sem_CAD_com_medidos_mantem_a_base_com_aviso_que_nao_inventa_CAD(monkeypatch, tmp_path):
    banco = _Banco(_projeto(anexo_em_curso=ANEXO), _itens(confirmados=2), ("arquitetura.pdf",))
    cena = _armar(monkeypatch, tmp_path / "medidos", banco)
    monkeypatch.setattr(main, "_job_medidos_count", lambda *a, **k: 2)
    assert main._retomar_job_do_storage(JOB, "residential", "arquitetura") == "ocupado"
    assert cena.nao_disparou() and len(cena.mantidas) == 1, cena.mantidas
    assert "não pôde ser relido" not in str(cena.mantidas[0]), cena.mantidas


def test_varredura_com_medidos_ILEGIVEL_tenta_de_novo_na_volta_seguinte(monkeypatch, tmp_path):
    """🩸 revisão dos consertos (21/09), reproduzido: o recuo do -1 devolvia só o
    status — a trava tinha zerado `error_message` — e a 2ª volta lia "não é
    passageiro", desistia do anexo e mandava alerta terminal. O que se toma,
    se devolve inteiro."""
    msg = "Processamento interrompido por reinício do servidor."
    banco = _Banco(_projeto(anexo_em_curso=ANEXO, error_message=msg), _itens(confirmados=0),
                   ("arquitetura.pdf",))
    cena = _armar(monkeypatch, tmp_path, banco)
    _armar_varredura(monkeypatch, cena)
    contagens = iter([-1, 0, 0, 0])
    monkeypatch.setattr(main, "_job_medidos_count", lambda *a, **k: next(contagens))
    monkeypatch.setattr(main, "_filhote_do_projeto", lambda *a, **k: "", raising=False)
    main._auto_retry_erros_transitorios()
    assert cena.nao_disparou(), "rodou só com PDF sem saber se havia medição"
    assert banco.projetos[0]["error_message"] == msg, "a mensagem sumiu no recuo"
    main._auto_retry_erros_transitorios()
    assert not cena.nao_disparou(), "a 2ª volta desistiu do anexo"
    assert cena.alertas == [], "alerta terminal por cima de um anexo que ia rodar"
