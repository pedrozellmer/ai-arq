# -*- coding: utf-8 -*-
"""O anexo que termina SEM mudar a planilha também avisa o cliente.

🩸 21/09/2026 — job 8b7a2b71 (05/09): a pessoa anexou arquivo ao mesmo projeto
TRÊS vezes, as três rodadas terminaram com 0 item, a planilha anterior foi
mantida — e ela nunca recebeu uma linha. Os dois `return` antecipados do
complemento ("CAD falhou, base preservada" e "complemento sem itens") gravavam
`done` + aviso e saíam ANTES do bloco de e-mail, que mora no fim do
`process_job`. E o `except` genérico do `process_job` errava para o outro lado:
não olhava se era anexo, gravava `error` (a planilha que o cliente já tinha
SUMIA da tela) e mandava "deu erro" a quem não tinha perdido nada. Regra do
Pedro no mesmo dia: "tem que receber e-mail em todos".

O QUE ESTE ARQUIVO PROVA, EXECUTANDO O CÓDIGO REAL:
  1. `_email_anexo_sem_mudanca` envia com `log_kind="complemento_sem_resultado"`
     e o `job_id`; o assunto abre com o nome do projeto e cabe na tela; a trava
     é a do PEDIDO de anexo (`<job_id>:<anexo_em_curso>`, 30 min, do tipo
     certo); as duas fichas (`complemento_sem_resultado` e `fim_de_job`) só são
     gravadas se o e-mail SAIU; quando a rodada já avisou, pula e deixa rastro;
     a marca `anexo_em_curso` sai nos três desfechos; e ela nunca levanta.
  2. `_anexo_falhou_mantem_a_base`: com base (200 + linha) volta `done` + aviso
     + e-mail; sem base (200 + []) ou com leitura que falha devolve False e não
     grava NADA.
  3. o `except` do `process_job`: anexo com base mantida NÃO grava `error` nem
     chama `_email_falha_cliente`; os controles (não-anexo, anexo sem base,
     leitura quebrada) seguem o erro de sempre.
  4. os dois `return` antecipados chamam o e-mail — executados de verdade, não
     lidos.

POR QUE CADA PEDAÇO:
  • ficha só se ENVIOU — ficha sem e-mail é a trava calando o próximo aviso
    por 30 minutos, pra um cliente que não recebeu nenhum;
  • a marca sai sempre — pendurada, uma retomada futura (de outro motivo)
    trataria o projeto como anexo: só os CADs, sem apagar os itens velhos;
  • nunca levanta — o return do CAD mora dentro de um `try` cujo `except` grava
    ERRO e relança: um e-mail que estourasse ali transformaria "base mantida"
    em "deu erro", o defeito que o conserto veio tirar;
  • leitura ESTRITA da base — `_complement_base_has_items` diz True quando a
    leitura falha; aqui isso mandaria "sua planilha continua" a quem talvez
    nem tenha planilha;
  • o texto não chuta causa — o e-mail diz o que o código SABE (não abriu, não
    achou item, não chegou ao fim, foi interrompido), nunca "DWG de versão
    recente" ou "PDF escaneado", que ninguém verificou.

🧪 COMO SE TESTA: o banco é um PostgREST de mentira atrás de
`urllib.request.urlopen`. Ele distingue método + tabela + filtro, aplica
`eq`/`gte`/`in`/`is`/`select`/`limit` como o de verdade, responde PATCH com 204
(ou a representação, se pedida), e a RPC `update_project_status` com COALESCE.
Pedido que ele não conhece é ANOTADO e reprova o teste no fim — um dublê que
responde qualquer coisa a qualquer pedido é o verde falso que a casa já pagou.
Com isso rodam de verdade `_supa_rest_service`, `_supa_rows`, `_projeto_patch`,
`_aviso_de_fim_recente`, `_email_auto_registrar`, `_log_error`,
`_supabase_update`, `_avisos_com` e `_complement_base_has_items`. Só o SMTP
(`_send_email_smtp`) é dublado na função, e todo dublê aceita `**k`.
"""
import ast
import functools
import io
import json
import os
import re
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import main as m  # noqa: E402
from _executa import _fonte  # noqa: E402

_JOB = "job-teste-0001"
_PAI = "pai-teste-0001"
_ANEXO = "anx-0001"
_EMAIL = "cliente-01@example.com"
_NOME_18 = "Edifício Horizonte"
_AVISO_ANTIGO = "aviso que JA estava no projeto"
_AVISO_NOVO = ("⚠ O processamento do arquivo anexado não chegou ao fim — a "
               "planilha anterior foi mantida, nada foi apagado.")

#: o que cada motivo TEM que dizer no e-mail — e só ele.
_FRASE_DO_MOTIVO = {
    "cad_nao_abriu": "não conseguimos abrir o desenho",
    # revisão final (21/09): "não encontrou item" era falso quando a leitura
    # FALHOU ou nada entrou — o texto diz só o que o código sabe
    "sem_itens": "não gerou nenhuma linha",
    "falhou": "não chegou ao fim",
    "interrompido": "foi interrompido",
}

#: afirmações de CAUSA que o código não verificou. O e-mail diz o que houve,
#: nunca o porquê que ninguém mediu.
_CAUSA_CHUTADA = [
    r"\bporque\b", r"\bpois\b", r"\bdevido\b", r"por causa",
    r"\bvers[aã]o\b", r"autocad", r"\bmep\b", r"el[eé]trica",
    r"corromp", r"danific", r"defeito", r"escanead", r"sobrecarreg",
    r"inv[aá]lid", r"s[oó] de layout",
]


def _causas_chutadas(texto):
    t = str(texto or "").lower()
    return [rx for rx in _CAUSA_CHUTADA if re.search(rx, t)]


# ── o PostgREST de mentira ──────────────────────────────────────────────────
class _Resp(object):
    def __init__(self, status, corpo=b""):
        self.status = status
        self._corpo = corpo

    def getcode(self):
        return self.status

    def read(self, *a, **k):
        return self._corpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _quando(txt):
    return datetime.fromisoformat(str(txt).rstrip("Z"))


def _ha(minutos):
    return (datetime.utcnow() - timedelta(minutes=minutos)).isoformat() + "Z"


#: a função REAL, guardada antes de o `amb` trocá-la por um gravador
_FALHA_REAL = m._email_falha_cliente


class _Postgrest(object):
    """Responde cada pedido como o PostgREST responderia — e só os que conhece."""

    TABELAS = ("projects", "project_items", "email_auto_log", "error_log")
    _NAO_FILTRO = ("select", "limit", "order", "offset")
    _COLUNAS_DA_RPC = (("p_status", "status"), ("p_items_count", "items_count"),
                       ("p_total_area", "total_area"), ("p_layout_area", "layout_area"),
                       ("p_error_message", "error_message"),
                       ("p_completed_at", "completed_at"), ("p_warnings", "warnings"))

    def __init__(self):
        self.linhas = {t: [] for t in self.TABELAS}
        self.pedidos = []
        self.desconhecidos = []
        #: (método, alvo) -> "conexao" | código HTTP
        self.falhas = {}
        self._seq = 0

    # -- filtros --------------------------------------------------------
    def _casa(self, linha, col, expr):
        op, _, arg = str(expr).partition(".")
        v = linha.get(col)
        if op == "eq":
            return v is not None and str(v) == arg
        if op == "gte":
            if v is None:
                return False
            if col.endswith("_at"):
                return _quando(v) >= _quando(arg)
            return float(v) >= float(arg)
        if op == "in":
            return v is not None and str(v) in arg.strip("()").split(",")
        if op == "is" and arg == "null":
            return v is None
        self.desconhecidos.append("filtro %s=%s" % (col, expr))
        raise urllib.error.URLError("filtro que o dublê não conhece: %s=%s" % (col, expr))

    def _filtra(self, tabela, params):
        filtros = [(c, e) for c, e in params.items() if c not in self._NAO_FILTRO]
        return [r for r in self.linhas[tabela]
                if all(self._casa(r, c, e) for c, e in filtros)]

    @staticmethod
    def _projeta(linha, select):
        if not select or select == "*":
            return dict(linha)
        return {c: linha.get(c) for c in select.split(",")}

    # -- a porta ----------------------------------------------------------
    def urlopen(self, req, *a, **k):
        metodo = req.get_method()
        partes = urllib.parse.urlsplit(req.full_url)
        params = dict(urllib.parse.parse_qsl(partes.query, keep_blank_values=True))
        corpo = json.loads(req.data.decode("utf-8")) if req.data else None
        prefer = req.get_header("Prefer") or ""
        if not partes.path.startswith("/rest/v1/"):
            self.desconhecidos.append("%s %s" % (metodo, req.full_url))
            raise urllib.error.URLError("rota que o dublê não conhece")
        alvo = partes.path[len("/rest/v1/"):]
        self.pedidos.append({"metodo": metodo, "alvo": alvo, "params": params,
                             "corpo": corpo, "prefer": prefer})
        falha = self.falhas.get((metodo, alvo))
        if falha == "conexao":
            raise urllib.error.URLError("conexão recusada (dublê)")
        if isinstance(falha, int):
            raise urllib.error.HTTPError(req.full_url, falha, "erro do dublê", {},
                                         io.BytesIO(b'{"message":"erro do dubl\\u00ea"}'))
        if metodo == "POST" and alvo == "rpc/update_project_status":
            return self._rpc_status(corpo)
        if alvo not in self.linhas:
            self.desconhecidos.append("%s %s" % (metodo, alvo))
            raise urllib.error.URLError("tabela que o dublê não conhece: %s" % alvo)
        if metodo == "GET":
            achou = [self._projeta(r, params.get("select")) for r in self._filtra(alvo, params)]
            if "limit" in params:
                achou = achou[:int(params["limit"])]
            return _Resp(200, json.dumps(achou).encode("utf-8"))
        if metodo == "POST":
            novos = corpo if isinstance(corpo, list) else [corpo]
            for n in novos:
                self._seq += 1
                linha = dict(n)
                linha.setdefault("id", self._seq)
                if alvo == "email_auto_log":
                    linha.setdefault("sent_at", _ha(0))      # default now()
                self.linhas[alvo].append(linha)
            if "return=representation" in prefer:
                return _Resp(201, json.dumps(novos).encode("utf-8"))
            return _Resp(201, b"")
        if metodo == "PATCH":
            mudou = self._filtra(alvo, params)
            for r in mudou:
                r.update(corpo or {})
            if "return=representation" in prefer:
                return _Resp(200, json.dumps(mudou).encode("utf-8"))
            return _Resp(204, b"")
        self.desconhecidos.append("%s %s" % (metodo, alvo))
        raise urllib.error.URLError("método que o dublê não conhece: %s" % metodo)

    def _rpc_status(self, corpo):
        alvo = [r for r in self.linhas["projects"] if r.get("job_id") == corpo.get("p_job_id")]
        for r in alvo:
            for p, col in self._COLUNAS_DA_RPC:
                if corpo.get(p) is not None:             # COALESCE(p_x, x)
                    r[col] = corpo[p]
        return _Resp(200, str(len(alvo)).encode("utf-8"))

    # -- leitura pros testes ---------------------------------------------
    def projeto(self, job_id=_JOB):
        return [r for r in self.linhas["projects"] if r.get("job_id") == job_id][0]

    def fichas(self):
        return [(r["email"], r["kind"], r["ref"]) for r in self.linhas["email_auto_log"]
                if not r.get("_semente")]

    def stages(self):
        return [r.get("stage") for r in self.linhas["error_log"]]

    def escritas(self):
        return [p for p in self.pedidos if p["metodo"] != "GET"]


class _Smtp(object):
    def __init__(self):
        self.enviados = []
        self.resposta = True
        self.levanta = None

    def __call__(self, to_email, subject, html_body, *a, **k):
        extra = dict(zip(("text_body", "log_kind", "job_id"), a))
        extra.update(k)
        self.enviados.append({"para": to_email, "assunto": subject, "html": html_body,
                              "log_kind": extra.get("log_kind"),
                              "job_id": extra.get("job_id")})
        if self.levanta is not None:
            raise self.levanta
        return self.resposta


class _JobsFalso(object):
    def __init__(self, ids=()):
        self.campos = {i: {} for i in ids}
        self.chamadas = []

    def __contains__(self, job_id):
        return job_id in self.campos

    def update_field(self, job_id, **kw):
        self.chamadas.append((job_id, kw))
        if job_id in self.campos:
            self.campos[job_id].update(kw)


def _projeto(**kw):
    linha = {"job_id": _JOB, "status": "processing", "user_email": _EMAIL,
             "user_name": "Pessoa Teste", "project_name": _NOME_18,
             "parent_job_id": None, "anexo_em_curso": _ANEXO,
             "warnings": [_AVISO_ANTIGO], "error_message": None, "completed_at": None}
    linha.update(kw)
    return linha


def _semente_de_ficha(ref, minutos, kind="complemento_sem_resultado", email=_EMAIL):
    return {"email": email, "kind": kind, "ref": ref, "sent_at": _ha(minutos),
            "_semente": True}


@pytest.fixture
def amb(monkeypatch):
    banco = _Postgrest()
    smtp = _Smtp()
    jobs = _JobsFalso([_JOB])
    falha_cliente = []
    monkeypatch.setattr(urllib.request, "urlopen", banco.urlopen)
    # 🪤 host que não existe: se algum caminho escapar do dublê, não chega a
    # lugar nenhum de verdade.
    monkeypatch.setattr(m, "SUPABASE_URL", "https://banco-de-teste.invalid")
    monkeypatch.setattr(m, "_supa_log", lambda *a, **k: None)
    monkeypatch.setattr(m, "_send_email_smtp", smtp)
    monkeypatch.setattr(m, "jobs", jobs)
    monkeypatch.setattr(m, "_email_falha_cliente",
                        lambda *a, **k: falha_cliente.append((a, k)))
    banco.linhas["projects"].append(_projeto())
    yield SimpleNamespace(banco=banco, smtp=smtp, jobs=jobs, falha_cliente=falha_cliente,
                          monkeypatch=monkeypatch)
    assert banco.desconhecidos == [], (
        "o código fez pedidos que o dublê não sabe responder — o resultado do "
        "teste não vale: %r" % (banco.desconhecidos,))


def _paragrafo_do_motivo(html):
    i = html.find("Sobre o projeto")
    j = html.find("O aviso com o detalhe", i)
    assert i >= 0 and j > i, "o corpo do e-mail mudou de forma: %r" % (html[:300],)
    return html[i:j]


# ═══ 1. _email_anexo_sem_mudanca ═══════════════════════════════════════════
def test_o_aviso_SAI_com_o_tipo_e_o_job_certos(amb):
    """🩸 8b7a2b71: três rodadas sem item, nenhum e-mail."""
    r = m._email_anexo_sem_mudanca(_JOB, "sem_itens")
    assert r is True
    assert len(amb.smtp.enviados) == 1, amb.smtp.enviados
    e = amb.smtp.enviados[0]
    assert e["para"] == _EMAIL
    assert e["log_kind"] == "complemento_sem_resultado", (
        "sem a etiqueta o e-mail cai no balde genérico da Central e o "
        "registro não conta o que o cliente recebeu: %r" % (e["log_kind"],))
    assert e["job_id"] == _JOB, "o registro de envio perdeu de qual job veio"


def test_o_assunto_abre_com_o_NOME_do_projeto_e_cabe_na_tela(amb):
    assert len(_NOME_18) == 18
    m._email_anexo_sem_mudanca(_JOB, "sem_itens")
    assunto = amb.smtp.enviados[0]["assunto"]
    assert assunto.startswith(_NOME_18), (
        "o nome do projeto tem que vir NA FRENTE — é o que a pessoa reconhece "
        "na caixa de entrada: %r" % (assunto,))
    assert len(assunto) <= 52, (
        "com nome de 18 caracteres o assunto tem %d (teto 52): %r"
        % (len(assunto), assunto))


def test_sem_nome_de_projeto_o_assunto_nao_sai_vazio_na_frente(amb):
    amb.banco.projeto()["project_name"] = ""
    m._email_anexo_sem_mudanca(_JOB, "sem_itens")
    assunto = amb.smtp.enviados[0]["assunto"]
    assert assunto.startswith("Seu projeto"), assunto


def test_a_janela_e_consultada_com_a_chave_do_PEDIDO_de_anexo(amb):
    """🔑 `<job_id>:<anexo_em_curso>`, tipo `complemento_sem_resultado`, 30 min."""
    m._email_anexo_sem_mudanca(_JOB, "sem_itens")
    consultas = [p for p in amb.banco.pedidos
                 if p["metodo"] == "GET" and p["alvo"] == "email_auto_log"]
    assert len(consultas) == 1, consultas
    q = consultas[0]["params"]
    assert q.get("ref") == "eq.%s:%s" % (_JOB, _ANEXO), q
    assert q.get("kind") == "eq.complemento_sem_resultado", q
    assert q.get("email") == "eq.%s" % _EMAIL, q
    desde = _quando(q["sent_at"].split(".", 1)[1])
    minutos = (datetime.utcnow() - desde).total_seconds() / 60.0
    assert 29 <= minutos <= 31, "a janela virou %.1f min" % minutos


@pytest.mark.parametrize("pai", [None, _PAI])
def test_enviou_registra_SO_a_ficha_do_pedido_e_nao_a_da_familia(amb, pai):
    """A do pedido trava a mesma rodada. 🩸 revisão final (21/09): a da
    FAMÍLIA (`fim_de_job`) NÃO — este aviso não entrega planilha, e com ela na
    janela de 30 min um Reprocessar logo depois terminava sem "planilha pronta"."""
    amb.banco.projeto()["parent_job_id"] = pai
    assert m._email_anexo_sem_mudanca(_JOB, "cad_nao_abriu") is True
    assert amb.banco.fichas() == [
        (_EMAIL, "complemento_sem_resultado", "%s:%s" % (_JOB, _ANEXO)),
    ]


def test_CONTROLE_envio_que_FALHA_nao_registra_ficha(amb):
    """🪤 Ficha sem e-mail = a trava calando o próximo aviso de quem não
    recebeu nenhum."""
    amb.smtp.resposta = False
    assert m._email_anexo_sem_mudanca(_JOB, "sem_itens") is False
    assert len(amb.smtp.enviados) == 1, "nem tentou enviar"
    assert amb.banco.fichas() == [], (
        "o envio falhou e mesmo assim ficou registrado como avisado: %r"
        % (amb.banco.fichas(),))
    assert "email:anexo-sem-mudanca-nao-saiu" in amb.banco.stages(), (
        "o SMTP falhou calado")


def test_a_rodada_ja_avisada_PULA_e_deixa_rastro(amb):
    amb.banco.linhas["email_auto_log"].append(
        _semente_de_ficha("%s:%s" % (_JOB, _ANEXO), minutos=5))
    assert m._email_anexo_sem_mudanca(_JOB, "sem_itens") is False
    assert amb.smtp.enviados == [], "a mesma rodada avisou duas vezes"
    assert amb.banco.fichas() == []
    logs = [r for r in amb.banco.linhas["error_log"]
            if r.get("stage") == "email:anexo-ja-avisado"]
    assert len(logs) == 1, amb.banco.stages()
    assert "%s:%s" % (_JOB, _ANEXO) in logs[0]["message"]
    assert logs[0]["job_id"] == _JOB


@pytest.mark.parametrize("semente", [
    _semente_de_ficha("%s:%s" % (_JOB, _ANEXO), minutos=40),            # fora dos 30 min
    _semente_de_ficha("%s:anx-0000" % _JOB, minutos=5),                 # OUTRO pedido
    _semente_de_ficha("%s:%s" % (_JOB, _ANEXO), minutos=5, kind="fim_de_job"),
    _semente_de_ficha("%s:%s" % (_JOB, _ANEXO), minutos=5,
                      email="cliente-02@example.com"),
], ids=["ha-40-min", "outro-pedido", "outro-tipo", "outro-cliente"])
def test_CONTROLE_a_janela_so_segura_a_MESMA_rodada(amb, semente):
    """🧪 Prova que o dublê distingue a consulta — senão o teste de cima
    passaria com uma trava que segura tudo."""
    amb.banco.linhas["email_auto_log"].append(semente)
    assert m._email_anexo_sem_mudanca(_JOB, "sem_itens") is True
    assert len(amb.smtp.enviados) == 1


def test_sem_email_de_cliente_nao_envia_mas_deixa_rastro(amb):
    amb.banco.projeto()["user_email"] = ""
    assert m._email_anexo_sem_mudanca(_JOB, "sem_itens") is False
    assert amb.smtp.enviados == []
    assert "email:anexo-sem-mudanca-sem-destino" in amb.banco.stages()


@pytest.mark.parametrize("falha", ["conexao", 500])
def test_leitura_do_projeto_que_FALHA_nao_vira_projeto_sem_email(amb, falha):
    """🩸 revisão final (21/09): `_supa_rows` devolvia [] na falha e isso
    virava "projeto sem e-mail" (info) — o aviso sumia calado."""
    amb.banco.falhas[("GET", "projects")] = falha
    assert m._email_anexo_sem_mudanca(_JOB, "sem_itens") is False
    stages = amb.banco.stages()
    assert "email:anexo-sem-mudanca-sem-leitura" in stages, stages
    assert "email:anexo-sem-mudanca-sem-destino" not in stages


def _enviou(amb):
    pass


def _pulou(amb):
    amb.banco.linhas["email_auto_log"].append(
        _semente_de_ficha("%s:%s" % (_JOB, _ANEXO), minutos=5))


def _sem_destino(amb):
    amb.banco.projeto()["user_email"] = None


@pytest.mark.parametrize("prepara", [_enviou, _pulou, _sem_destino],
                         ids=["enviou", "pulou", "sem-email"])
def test_o_email_sozinho_NAO_mexe_na_marca(amb, prepara):
    """🩸 revisão final (21/09): o e-mail limpava a marca no `finally`, SEM
    saber se o `done` tinha gravado — num soluço do banco, a varredura
    seguinte retomava como UPLOAD e apagava a base depois do "nada foi
    apagado". Quem limpa agora é quem CONFIRMOU o `done`."""
    prepara(amb)
    m._email_anexo_sem_mudanca(_JOB, "sem_itens")
    assert amb.banco.projeto()["anexo_em_curso"] == _ANEXO
    assert [p for p in amb.banco.escritas()
            if p["alvo"] == "projects"] == [], amb.banco.escritas()


def test_mantem_a_base_limpa_SO_a_marca_deste_pedido(amb):
    """🩸 revisão final (21/09): a limpeza era incondicional — um anexo NOVO
    que tomasse o projeto enquanto o aviso saía perdia a marca dele."""
    amb.banco.linhas["project_items"].append({"id": 7, "job_id": _JOB})
    _email_real = m._email_anexo_sem_mudanca

    def _outro_anexo_chega(job_id, motivo):
        r = _email_real(job_id, motivo)
        amb.banco.projeto()["anexo_em_curso"] = "outro-pedido"      # tomou o projeto
        return r

    amb.monkeypatch.setattr(m, "_email_anexo_sem_mudanca", _outro_anexo_chega)
    assert m._anexo_falhou_mantem_a_base(_JOB, "falhou", _AVISO_NOVO) is True
    assert amb.banco.projeto()["anexo_em_curso"] == "outro-pedido", (
        "apagou a marca do anexo NOVO")
    limpeza = [p for p in amb.banco.escritas()
               if p["alvo"] == "projects" and p["corpo"] == {"anexo_em_curso": None}]
    assert len(limpeza) == 1 and limpeza[0]["params"]["anexo_em_curso"] == "eq." + _ANEXO


def test_CONTROLE_mantem_a_base_limpa_a_marca_quando_ela_e_a_do_pedido(amb):
    amb.banco.linhas["project_items"].append({"id": 7, "job_id": _JOB})
    assert m._anexo_falhou_mantem_a_base(_JOB, "falhou", _AVISO_NOVO) is True
    assert amb.banco.projeto()["anexo_em_curso"] is None


def test_marca_ilegivel_nao_e_limpa_as_cegas(amb):
    amb.banco.linhas["project_items"].append({"id": 7, "job_id": _JOB})
    lidas = {"n": 0}
    _real = m._ler_marca_do_anexo

    def _le(job_id):
        lidas["n"] += 1
        return (False, "")
    amb.monkeypatch.setattr(m, "_ler_marca_do_anexo", _le)
    assert m._anexo_falhou_mantem_a_base(_JOB, "falhou", _AVISO_NOVO) is True
    assert lidas["n"] == 1 and callable(_real)
    assert amb.banco.projeto()["anexo_em_curso"] == _ANEXO, "limpou sem saber qual marca"


_COLABORADORES = ["_supa_rest_service", "_aviso_de_fim_recente", "_resolve_client_name",
                  "_greeting_line", "_email_wrap", "_send_email_smtp",
                  "_email_auto_registrar"]


@pytest.mark.parametrize("quem", _COLABORADORES)
def test_nunca_levanta_quando_um_colaborador_explode(amb, quem):
    """🪤 O return do CAD mora num `try` cujo `except` grava ERRO e relança:
    um e-mail que estourasse ali desfaria o "base mantida"."""
    explodiu = []

    def _bomba(*a, **k):
        explodiu.append(quem)
        raise RuntimeError("explodiu: %s" % quem)

    amb.monkeypatch.setattr(m, quem, _bomba)
    r = m._email_anexo_sem_mudanca(_JOB, "sem_itens")
    assert explodiu == [quem], (
        "o colaborador %s nem foi chamado — o teste não provou nada" % quem)
    assert isinstance(r, bool)
    assert "email:anexo-sem-mudanca-falhou" in amb.banco.stages(), (
        "explodiu calado — sem rastro no error_log")


def test_nunca_levanta_quando_TUDO_explode_inclusive_o_log(amb):
    chamados = []

    def _bomba_de(nome):
        def _b(*a, **k):
            chamados.append(nome)
            raise RuntimeError("explodiu: %s" % nome)
        return _b

    for nome in _COLABORADORES + ["_log_error"]:
        amb.monkeypatch.setattr(m, nome, _bomba_de(nome))
    assert m._email_anexo_sem_mudanca(_JOB, "sem_itens") is False
    assert "_supa_rest_service" in chamados and "_log_error" in chamados, chamados


def test_nunca_levanta_com_o_banco_fora_do_ar_e_o_smtp_quebrado(amb):
    for alvo in ("projects", "email_auto_log", "error_log"):
        for metodo in ("GET", "POST", "PATCH"):
            amb.banco.falhas[(metodo, alvo)] = "conexao"
    amb.smtp.levanta = OSError("smtp fora")
    assert m._email_anexo_sem_mudanca(_JOB, "sem_itens") is False
    assert amb.banco.pedidos, "o banco nem foi consultado"


@pytest.mark.parametrize("motivo", sorted(_FRASE_DO_MOTIVO))
def test_cada_motivo_diz_o_que_houve_e_NAO_chuta_causa(amb, motivo):
    # a base existe (a promessa "nada foi apagado" só sai conferida — ver o
    # controle logo abaixo)
    amb.banco.linhas["project_items"].append({"id": 7, "job_id": _JOB})
    m._email_anexo_sem_mudanca(_JOB, motivo)
    html = amb.smtp.enviados[0]["html"]
    trecho = _paragrafo_do_motivo(html)
    assert _FRASE_DO_MOTIVO[motivo] in trecho, (motivo, trecho)
    for outro, frase in _FRASE_DO_MOTIVO.items():
        if outro != motivo:
            assert frase not in trecho, (
                "o motivo %r saiu com o texto de %r" % (motivo, outro))
    assert _causas_chutadas(trecho) == [], (
        "o e-mail afirma uma causa que o código não verificou: %r em %r"
        % (_causas_chutadas(trecho), trecho))
    assert "nada foi apagado" in trecho


@pytest.mark.parametrize("falha", [None, 500])
def test_sem_base_CONFERIDA_o_email_nao_promete_a_planilha(amb, falha):
    """🩸 21/09 (revisão): os returns antecipados decidem "tem base" pela leitura
    FROUXA (True quando a leitura falha). O e-mail não pode prometer "a planilha
    que você já tinha continua" sem conferir: sem item (None) ou com a leitura
    caindo (500), sai só o fato."""
    if falha:
        amb.banco.linhas["project_items"].append({"id": 7, "job_id": _JOB})
        amb.banco.falhas[("GET", "project_items")] = falha
    m._email_anexo_sem_mudanca(_JOB, "sem_itens")
    envio = amb.smtp.enviados[0]
    assert "continua exatamente como estava" not in envio["html"], envio["html"]
    assert "nada foi apagado" not in envio["html"], envio["html"]
    assert "continua" not in envio["assunto"], envio["assunto"]


def test_motivo_desconhecido_cai_no_texto_generico_sem_estourar(amb):
    assert m._email_anexo_sem_mudanca(_JOB, "motivo-que-nao-existe") is True
    trecho = _paragrafo_do_motivo(amb.smtp.enviados[0]["html"])
    assert _FRASE_DO_MOTIVO["falhou"] in trecho, trecho


# ═══ 2. _anexo_falhou_mantem_a_base ════════════════════════════════════════
def test_com_base_volta_DONE_com_aviso_e_o_cliente_e_avisado(amb):
    amb.banco.projeto().update(status="error", error_message="erro que ficou")
    amb.banco.linhas["project_items"].append({"id": 7, "job_id": _JOB})
    r = m._anexo_falhou_mantem_a_base(_JOB, "falhou", _AVISO_NOVO)
    assert r is True
    p = amb.banco.projeto()
    assert p["status"] == "done", p
    assert p["error_message"] is None, (
        "a mensagem de erro velha ficou num projeto 'done': %r" % (p["error_message"],))
    assert p["warnings"] == [_AVISO_ANTIGO, _AVISO_NOVO], (
        "o aviso apagou o histórico (clobber de 04/09) ou não entrou: %r" % (p["warnings"],))
    assert p["completed_at"]
    assert p["anexo_em_curso"] is None
    assert amb.jobs.campos[_JOB].get("status") == "done"
    assert "anexo:base-mantida" in amb.banco.stages()
    assert len(amb.smtp.enviados) == 1
    e = amb.smtp.enviados[0]
    assert e["log_kind"] == "complemento_sem_resultado" and e["job_id"] == _JOB
    assert _FRASE_DO_MOTIVO["falhou"] in _paragrafo_do_motivo(e["html"])
    leituras = [q for q in amb.banco.pedidos
                if q["metodo"] == "GET" and q["alvo"] == "project_items"]
    assert leituras and leituras[0]["params"] == {
        "job_id": "eq.%s" % _JOB, "select": "id", "limit": "1"}, leituras


def test_sem_base_devolve_False_e_NAO_grava_nada(amb):
    """🧪 O item de OUTRO projeto prova que o dublê filtra pelo job — um que
    devolvesse a mesma linha pra qualquer pedido faria a base 'existir'
    sempre e este caso nunca rodaria."""
    amb.banco.linhas["project_items"].append({"id": 9, "job_id": "outro-job"})
    antes = dict(amb.banco.projeto())
    assert m._anexo_falhou_mantem_a_base(_JOB, "falhou", _AVISO_NOVO) is False
    assert amb.banco.escritas() == [], amb.banco.escritas()
    assert amb.banco.projeto() == antes
    assert amb.smtp.enviados == []
    assert amb.jobs.chamadas == []


@pytest.mark.parametrize("falha", ["conexao", 500, 503])
def test_leitura_da_base_que_FALHA_devolve_False(amb, falha):
    amb.banco.linhas["project_items"].append({"id": 7, "job_id": _JOB})
    amb.banco.falhas[("GET", "project_items")] = falha
    assert m._anexo_falhou_mantem_a_base(_JOB, "falhou", _AVISO_NOVO) is False
    assert amb.banco.escritas() == [], amb.banco.escritas()
    assert amb.smtp.enviados == []
    assert amb.banco.projeto()["status"] == "processing"


def test_CONTRASTE_a_leitura_frouxa_diria_que_HA_base_no_mesmo_banco_quebrado(amb):
    """🪤 O motivo da leitura estrita: `_complement_base_has_items` assume base
    quando a leitura falha — aqui isso mandaria "sua planilha continua" a quem
    talvez nem tenha planilha."""
    amb.banco.falhas[("GET", "project_items")] = 500
    assert m._complement_base_has_items(_JOB) is True
    assert m._anexo_falhou_mantem_a_base(_JOB, "falhou", _AVISO_NOVO) is False


# ═══ 3. o except do process_job ════════════════════════════════════════════
_ARVORE = ast.parse(_fonte("main.py"))
_LINHAS = _fonte("main.py").splitlines(True)


def _no_da_funcao(nome):
    for no in ast.walk(_ARVORE):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and no.name == nome:
            return no
    raise AssertionError("não achei a função %s no main.py" % nome)


_PROCESS_JOB = _no_da_funcao("process_job")


@functools.lru_cache(maxsize=None)
def _codigo_do_except_do_process_job():
    """O corpo REAL do except genérico do `process_job`.

    🪤 A âncora é a mesma de test_erro_nao_apaga_o_que_o_motor_descobriu
    (`_avisos_ate_aqui` + `_supabase_update`), NÃO o nome do conserto: se a
    âncora fosse `_anexo_falhou_mantem_a_base`, apagar o conserto apagaria a
    âncora e o arquivo quebraria na coleta — reprovando pelo motivo errado,
    em vez de EXECUTAR o except sem o conserto e mostrar o `error` gravado."""
    achados = []
    for t in ast.walk(_PROCESS_JOB):
        if not isinstance(t, ast.Try):
            continue
        for h in t.handlers:
            txt = ast.unparse(ast.Module(body=h.body, type_ignores=[]))
            if "_avisos_ate_aqui" in txt and "_supabase_update" in txt:
                achados.append(txt)
    assert len(achados) == 1, (
        "esperava UM except de process_job que salve avisos e grave no banco; "
        "achei %d" % len(achados))
    return achados[0]


def _roda_o_except(amb, erro=None, **escopo_extra):
    escopo = dict(vars(m))
    escopo.pop("is_complement", None)
    escopo.update({"e": erro or RuntimeError("a leitura do anexo quebrou no meio"),
                   "job_id": _JOB, "jobs": amb.jobs,
                   "_email_falha_cliente": m._email_falha_cliente,
                   "print": lambda *a, **k: None})
    escopo.update(escopo_extra)
    exec(compile(_codigo_do_except_do_process_job(), "<main.py:process_job:except>",
                 "exec"), escopo)
    return escopo


def _gravou_erro(amb):
    return [p for p in amb.banco.pedidos
            if p["alvo"] == "rpc/update_project_status"
            and (p["corpo"] or {}).get("p_status") == "error"]


def test_o_except_de_ANEXO_com_base_NAO_grava_erro_nem_manda_deu_erro(amb):
    amb.banco.linhas["project_items"].append({"id": 7, "job_id": _JOB})
    esc = _roda_o_except(amb, is_complement=True)
    assert esc.get("_base_mantida") is True
    assert _gravou_erro(amb) == [], (
        "o anexo morreu e o projeto virou ERRO — a planilha que o cliente já "
        "tinha sumiu da tela")
    assert amb.banco.projeto()["status"] == "done"
    assert amb.falha_cliente == [], (
        "mandou 'deu erro' a quem não perdeu nada: %r" % (amb.falha_cliente,))
    assert [e["log_kind"] for e in amb.smtp.enviados] == ["complemento_sem_resultado"]
    assert _FRASE_DO_MOTIVO["falhou"] in _paragrafo_do_motivo(amb.smtp.enviados[0]["html"])
    assert "process_job" in amb.banco.stages(), (
        "a causa real sumiu do error_log só porque a base foi mantida")


def test_CONTROLE_sem_ser_anexo_o_erro_e_gravado_como_antes(amb):
    amb.banco.linhas["project_items"].append({"id": 7, "job_id": _JOB})
    esc = _roda_o_except(amb, is_complement=False, erro=RuntimeError("arquivo sem itens"))
    assert not esc.get("_base_mantida")
    p = amb.banco.projeto()
    assert p["status"] == "error" and p["error_message"] == "arquivo sem itens", p
    assert len(amb.falha_cliente) == 1
    assert amb.smtp.enviados == []
    assert not [q for q in amb.banco.pedidos if q["alvo"] == "project_items"], (
        "projeto normal não devia nem consultar a base do anexo")


@pytest.mark.parametrize("como", ["sem-base", "leitura-500", "sem-is_complement"])
def test_CONTROLE_anexo_sem_base_confirmada_segue_o_erro_de_sempre(amb, como):
    extra = {"is_complement": True}
    if como == "leitura-500":
        amb.banco.linhas["project_items"].append({"id": 7, "job_id": _JOB})
        amb.banco.falhas[("GET", "project_items")] = 500
    elif como == "sem-is_complement":
        # 🪤 há guarda que roda este except num escopo sem a variável.
        amb.banco.linhas["project_items"].append({"id": 7, "job_id": _JOB})
        extra = {}
    esc = _roda_o_except(amb, **extra)
    assert not esc.get("_base_mantida")
    assert len(_gravou_erro(amb)) == 1
    assert amb.banco.projeto()["status"] == "error"
    assert len(amb.falha_cliente) == 1
    assert amb.smtp.enviados == []
    # 🩸 revisão final (21/09): anexo que falha SEM base avisa pela chave do
    # PEDIDO (o dedup por job calava quem já tinha levado o 1º "deu erro")
    _a, _k = amb.falha_cliente[0]
    if como == "sem-is_complement":
        assert _k.get("anexo_ref") == "", _k
    else:
        assert _k.get("anexo_ref") == _ANEXO, _k


# ═══ 4. os dois returns antecipados do complemento ═════════════════════════
#: âncora de cada return antecipado: o `current_step` que ele grava. 🪤 NÃO a
#: chamada do e-mail — apagar o e-mail apagaria a âncora, e o arquivo quebraria
#: na coleta em vez de EXECUTAR o return calado e mostrar que ninguém foi avisado.
_ANCORA_DO_RETURN = {
    "cad_nao_abriu": "Complemento não pôde ser lido — planilha anterior mantida",
    "sem_itens": "Complemento sem itens — planilha anterior mantida",
}


@functools.lru_cache(maxsize=None)
def _if_do_return(motivo):
    """O `if` real do return antecipado, recortado pela AST.

    Mesma régua de `_executa.trecho(..., tamanho=1)` (lineno/end_lineno, nunca
    janela de caracteres), numa passada só: o `trecho` refaz o join a cada
    statement de `process_job` e custa ~5 s por chamada."""
    marcador = _ANCORA_DO_RETURN[motivo]
    alvo = [n for n, l in enumerate(_LINHAS, 1) if marcador in l]
    alvo = [n for n in alvo if _PROCESS_JOB.lineno <= n <= _PROCESS_JOB.end_lineno]
    assert len(alvo) == 1, "a âncora %r aparece %d vezes em process_job" % (marcador, len(alvo))
    # revisão final (21/09): o return virou `if is_complement:` + a porta única
    # (`_anexo_falhou_mantem_a_base`) por dentro — o recorte pega o de FORA,
    # onde o aviso nasce.
    ifs = [no for no in ast.walk(_PROCESS_JOB)
           if isinstance(no, ast.If) and no.lineno <= alvo[0] <= no.end_lineno
           and _LINHAS[no.lineno - 1].strip() == "if is_complement:"]
    menor = min(ifs, key=lambda no: no.end_lineno - no.lineno)
    fonte = textwrap.dedent("".join(_LINHAS[menor.lineno - 1:menor.end_lineno]))
    assert "_anexo_falhou_mantem_a_base(" in fonte, (
        "o return antecipado não passa mais pela porta que confere o `done`: %r"
        % (fonte[:160],))
    assert "return" in fonte, "o trecho recortado não tem mais o return antecipado"
    return fonte


def _roda_o_return(amb, motivo, is_complement=True):
    """Executa o `if` real DENTRO de uma função (ele tem `return`). Devolve None
    se o return antecipado aconteceu, "seguiu" se o código passou reto."""
    wrapper = ("def __trecho__():" + chr(10) + textwrap.indent(_if_do_return(motivo), "    ")
               + "    return 'seguiu'" + chr(10))
    escopo = dict(vars(m))
    escopo.update({"is_complement": is_complement, "job_id": _JOB, "jobs": amb.jobs,
                   "arquivos": "planta-baixa.dwg",
                   "file_paths": ["/tmp/planta-baixa.pdf"],
                   "dxf_errors": [], "sheet_errors": [],
                   "print": lambda *a, **k: None})
    exec(compile(wrapper, "<main.py:process_job:return-antecipado>", "exec"), escopo)
    return escopo["__trecho__"]()


_MOTIVOS_DOS_RETURNS = sorted(_ANCORA_DO_RETURN)


@pytest.mark.parametrize("motivo", _MOTIVOS_DOS_RETURNS)
def test_o_return_antecipado_AVISA_o_cliente(amb, motivo):
    amb.banco.linhas["project_items"].append({"id": 7, "job_id": _JOB})
    assert _roda_o_return(amb, motivo) is None, "o return antecipado não aconteceu"
    p = amb.banco.projeto()
    assert p["status"] == "done" and len(p["warnings"]) == 2, p
    assert len(amb.smtp.enviados) == 1, (
        "o anexo terminou sem mudar a planilha e saiu CALADO (8b7a2b71)")
    e = amb.smtp.enviados[0]
    assert e["log_kind"] == "complemento_sem_resultado" and e["job_id"] == _JOB
    assert _FRASE_DO_MOTIVO[motivo] in _paragrafo_do_motivo(e["html"]), (
        "o return de %r mandou o texto de outro motivo" % motivo)
    assert p["anexo_em_curso"] is None


@pytest.mark.parametrize("motivo", _MOTIVOS_DOS_RETURNS)
def test_CONTROLE_sem_anexo_ou_sem_base_o_return_nao_acontece(amb, motivo):
    amb.banco.linhas["project_items"].append({"id": 7, "job_id": _JOB})
    assert _roda_o_return(amb, motivo, is_complement=False) == "seguiu"
    amb.banco.linhas["project_items"][:] = []
    assert _roda_o_return(amb, motivo, is_complement=True) == "seguiu"
    assert amb.smtp.enviados == []
    assert amb.banco.escritas() == []


@pytest.mark.parametrize("motivo", _MOTIVOS_DOS_RETURNS)
def test_o_return_antecipado_sobrevive_ao_email_quebrado(amb, motivo):
    """🪤 O do CAD mora num `try` cujo `except` grava erro e RELANÇA."""
    amb.banco.linhas["project_items"].append({"id": 7, "job_id": _JOB})
    amb.smtp.levanta = OSError("smtp fora")
    assert _roda_o_return(amb, motivo) is None
    assert amb.banco.projeto()["status"] == "done"


def test_CONTROLE_o_detector_de_causa_chutada_SABE_reprovar(amb):
    """🧪 O texto que o aviso do CAD usava até 21/09 CHUTAVA uma causa fixa —
    o detector tem que acusá-lo; senão o 'não chuta causa' é vazio. E o aviso
    novo (revisão final) não chuta nada."""
    antigo = ("O arquivo CAD que você anexou não pôde ser aberto automaticamente "
              "(DWG de versão recente do AutoCAD ou com objetos de MEP/elétrica).")
    assert _causas_chutadas(antigo), antigo
    amb.banco.linhas["project_items"].append({"id": 7, "job_id": _JOB})
    _roda_o_return(amb, "cad_nao_abriu")
    aviso_do_cad = amb.banco.projeto()["warnings"][-1]
    # o "como resolver" cita o AutoCAD como FERRAMENTA — o que não pode é o
    # diagnóstico (antes dele) afirmar causa
    diagnostico = aviso_do_cad.split("Pra medir pelo CAD")[0]
    assert diagnostico != aviso_do_cad, "o aviso perdeu o 'como resolver'"
    assert _causas_chutadas(diagnostico) == [], diagnostico
    assert "que você anexou" not in aviso_do_cad, (
        "com CAD no projeto a rota manda só os CADs: o que não abriu pode não ser o anexo")
    assert _causas_chutadas(_paragrafo_do_motivo(amb.smtp.enviados[0]["html"])) == []


@pytest.mark.parametrize("motivo", _MOTIVOS_DOS_RETURNS)
def test_o_return_com_DONE_que_nao_grava_segue_o_erro_e_guarda_a_marca(amb, motivo):
    """🩸 revisão final (21/09), reproduzido: o return gravava `done` sem
    conferir (a RPC devolve False, não levanta), punha o store local em
    `done` ANTES, e o e-mail limpava a marca — a varredura seguinte retomava
    como UPLOAD e apagava a base depois do "nada foi apagado"."""
    amb.banco.linhas["project_items"].append({"id": 7, "job_id": _JOB})
    amb.monkeypatch.setattr(m, "_supabase_update", lambda *a, **k: False)
    assert _roda_o_return(amb, motivo) == "seguiu", "retornou sem o `done` gravado"
    assert amb.smtp.enviados == [], "prometeu 'nada foi apagado' sem gravar"
    assert amb.banco.projeto()["anexo_em_curso"] == _ANEXO, "limpou a marca"
    assert not any(kw.get("status") == "done" for _j, kw in amb.jobs.chamadas), (
        "o store local foi pra `done` sem o banco — a varredura não pularia")


def test_se_o_DONE_nao_grava_nao_promete_nem_limpa_a_marca(amb):
    """🩸 21/09 (revisão, reproduzido): o retorno do `_supabase_update` era
    ignorado. Com a RPC falhando, a função dizia "mantive", o e-mail prometia a
    planilha e a marca do anexo era LIMPA — o projeto ficava parado sem status
    final e sem marca, e a próxima recuperação o trataria como upload comum,
    APAGANDO a base. Agora: False, sem e-mail, marca intacta (a retomada segue
    sabendo que era anexo)."""
    amb.banco.projeto().update(status="processing", anexo_em_curso="pedido000001")
    amb.banco.linhas["project_items"].append({"id": 7, "job_id": _JOB})
    amb.monkeypatch.setattr(m, "_supabase_update", lambda *a, **k: False)
    r = m._anexo_falhou_mantem_a_base(_JOB, "falhou", _AVISO_NOVO)
    assert r is False, "disse que manteve a planilha sem conseguir gravar"
    assert amb.smtp.enviados == [], "prometeu a planilha por e-mail sem gravar nada"
    assert amb.banco.projeto()["anexo_em_curso"] == "pedido000001", (
        "limpou a marca — a recuperação apagaria a base achando que é upload")
    assert "anexo:base-mantida-nao-gravou" in amb.banco.stages()


# ═══ 5. revisão final (21/09): freio de memória e falha SEM planilha ═══════
def _freio(amb, **kw):
    amb.monkeypatch.setattr(m, "_notify_admin", lambda *a, **k: True)
    amb.monkeypatch.setattr(m, "_container_mem_frac", lambda: 0.9)
    m._abort_job_mem(_JOB, 3, 10, **kw)


def test_freio_de_memoria_num_ANEXO_com_base_mantem_a_planilha(amb):
    """🩸 revisão final: o freio gravava erro, mandava "deu erro" e tirava da
    tela a planilha que o cliente já tinha — o defeito que o except deixou de
    ter. Com base: `done`, aviso, e-mail curto, marca limpa."""
    amb.banco.linhas["project_items"].append({"id": 7, "job_id": _JOB})
    _freio(amb, motivo="projeto", is_complement=True)
    p = amb.banco.projeto()
    assert p["status"] == "done", p
    assert "memória" in p["warnings"][-1] and "mantida" in p["warnings"][-1]
    assert amb.falha_cliente == [], "mandou 'deu erro' a quem não perdeu nada"
    assert [e["log_kind"] for e in amb.smtp.enviados] == ["complemento_sem_resultado"]
    assert p["anexo_em_curso"] is None


@pytest.mark.parametrize("anexo", [True, False], ids=["anexo-sem-base", "upload"])
def test_freio_sem_base_segue_o_erro_e_o_anexo_avisa_pela_chave_do_pedido(amb, anexo):
    _freio(amb, motivo="projeto", is_complement=anexo)
    assert amb.banco.projeto()["status"] == "error"
    assert len(amb.falha_cliente) == 1
    assert amb.falha_cliente[0][1].get("anexo_ref") == (_ANEXO if anexo else "")


def _falha_real(amb, **kw):
    amb.monkeypatch.setattr(m, "_email_falha_cliente", _FALHA_REAL)
    amb.monkeypatch.setattr(m, "_falha_emailed", {_JOB})       # o 1º "deu erro" já saiu
    amb.banco.projeto().update(status="error", error_message="Erro DWG→DXF: x",
                               created_at=_ha(60), reprocess_count=1)
    for col in ("items_count",):
        amb.banco.projeto().setdefault(col, 0)
    return _FALHA_REAL(_JOB, reprocessavel=False, **kw)


def test_anexo_que_falha_SEM_planilha_avisa_mesmo_com_o_job_ja_avisado(amb):
    """🩸 revisão final (21/09), reproduzido: o upload deu erro (1º e-mail), o
    cliente seguiu o conselho e anexou o DXF, o DXF também falhou — e o dedup
    POR JOB calava o 2º aviso. Regra do Pedro: "tem que receber e-mail em
    todos"."""
    assert _falha_real(amb, anexo_ref=_ANEXO) is True
    assert [e["para"] for e in amb.smtp.enviados] == [_EMAIL]
    assert (_EMAIL, "complemento_falhou", "%s:%s" % (_JOB, _ANEXO)) in amb.banco.fichas()


def test_o_mesmo_pedido_de_anexo_nao_avisa_duas_vezes(amb):
    assert _falha_real(amb, anexo_ref=_ANEXO) is True
    assert _FALHA_REAL(_JOB, reprocessavel=False, anexo_ref=_ANEXO) is False
    assert len(amb.smtp.enviados) == 1


def test_CONTROLE_sem_anexo_o_dedup_por_job_segue_valendo(amb):
    assert _falha_real(amb) is False
    assert amb.smtp.enviados == []


# ═══ 6. revisão dos consertos (21/09) ══════════════════════════════════════
def test_freio_num_anexo_com_base_CONTINUA_avisando_o_pedro(amb):
    """🩸 revisão dos consertos: o ramo do anexo tinha tirado o alerta interno
    — o único sinal de que o servidor chegou perto do limite."""
    import threading as _th
    amb.banco.linhas["project_items"].append({"id": 7, "job_id": _JOB})
    avisos, pronto = [], _th.Event()
    amb.monkeypatch.setattr(m, "_notify_admin",
                            lambda assunto, corpo, *a, **k: (avisos.append((assunto, corpo)), pronto.set()))
    amb.monkeypatch.setattr(m, "_container_mem_frac", lambda: 0.9)
    m._abort_job_mem(_JOB, 3, 10, motivo="projeto", is_complement=True)
    assert pronto.wait(5), "o alerta interno do freio sumiu no anexo"
    assert "anexo" in avisos[0][0] and "mantida" in avisos[0][1]
    freio = [r for r in amb.banco.linhas["error_log"] if r.get("stage") == "mem:freio"]
    assert freio and "uso=0.9" in freio[-1]["message"], freio


def test_os_pontos_de_freio_do_motor_dizem_se_e_ANEXO():
    """🩸 revisão dos consertos: tirar `is_complement=` dos dois `_abort_job_mem`
    do motor deixava tudo verde — o anexo voltava a perder a planilha no freio."""
    chamadas = [n for n in ast.walk(_PROCESS_JOB)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "_abort_job_mem"]
    assert len(chamadas) >= 2, len(chamadas)
    for c in chamadas:
        kw = {k.arg: k.value for k in c.keywords}
        assert isinstance(kw.get("is_complement"), ast.Name) and kw["is_complement"].id == "is_complement", (
            "um ponto de freio do motor não passa `is_complement=is_complement` (linha %d)" % c.lineno)


@pytest.mark.parametrize("marca,esperado", [(_ANEXO, _ANEXO), (None, "")],
                         ids=["anexo-sem-base", "CONTROLE-upload"])
def test_teto_de_paginas_avisa_o_anexo_sem_base_pela_chave_do_pedido(amb, marca, esperado):
    """🩸 revisão dos consertos: anexo sem planilha recusado pelo teto de
    páginas calava pelo dedup por job. A âncora é a MARCA (não há a flag)."""
    amb.banco.projeto()["anexo_em_curso"] = marca
    amb.monkeypatch.setattr(m, "_paginas_do_envio",
                            lambda fps: (m.TETO_PAGINAS_DO_ENVIO + 50,
                                         [("licitacao.pdf", m.TETO_PAGINAS_DO_ENVIO + 50,
                                           m.TETO_PAGINAS_DO_ENVIO + 50)]))
    assert m._recusa_por_paginas(_JOB, ["/tmp/licitacao.pdf"]) is True
    assert len(amb.falha_cliente) == 1
    assert amb.falha_cliente[0][1].get("anexo_ref") == esperado, amb.falha_cliente


@pytest.mark.parametrize("trava", ["pai", "15-min"])
def test_as_travas_do_JOB_nao_calam_o_anexo(amb, trava):
    """As travas do dedup por job (filho de reprocesso, freio de 15 min) não
    valem pro aviso de ANEXO — ele tem a chave do pedido."""
    if trava == "pai":
        amb.banco.projeto()["parent_job_id"] = _PAI
    else:
        # 🪤 o freio de 15 min mora num try/except que ENGOLE erro e segue:
        # um dublê que "estoura" não prova nada (a sabotagem mostrou). Aqui
        # ele acha um aviso de falha recente DE VERDADE no banco de mentira —
        # sem a exceção do anexo, calaria.
        amb.banco.linhas["email_auto_log"].append(
            _semente_de_ficha("outro-job", minutos=2, kind="erro_trocar"))
        amb.monkeypatch.setattr(
            m, "_url_de_falha_recente",
            lambda *a, **k: m.SUPABASE_URL + "/rest/v1/email_auto_log?select=id&kind=eq.erro_trocar")
    assert _falha_real(amb, anexo_ref=_ANEXO) is True


def test_CONTROLE_o_freio_de_15_min_CALA_quem_nao_e_anexo(amb):
    """Prova que o dublê do freio de cima dispara de verdade."""
    amb.banco.linhas["email_auto_log"].append(
        _semente_de_ficha("outro-job", minutos=2, kind="erro_trocar"))
    amb.monkeypatch.setattr(
        m, "_url_de_falha_recente",
        lambda *a, **k: m.SUPABASE_URL + "/rest/v1/email_auto_log?select=id&kind=eq.erro_trocar")
    amb.monkeypatch.setattr(m, "_email_falha_cliente", _FALHA_REAL)
    amb.monkeypatch.setattr(m, "_falha_emailed", set())
    amb.banco.projeto().update(status="error", created_at=_ha(60), reprocess_count=0,
                               items_count=0)
    assert _FALHA_REAL(_JOB, reprocessavel=False) is False, "o freio de 15 min não disparou"
    assert amb.smtp.enviados == []
