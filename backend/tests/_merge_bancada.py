# -*- coding: utf-8 -*-
"""O merge EXECUTADO — `/merge-criar`, `_merge_montar` e o Liberar rodando.

🚨 07/09/2026. Três guardas do merge afirmavam sobre o TEXTO de `main.py`:
que existe um `startswith("mg")`, que existe um `zip(_disputadas, _vs)`, que
existe um `_ssg_m(...)`. Nenhum deles vê:

  • o **gerador** do `mg` (`novo_id = "mg" + uuid…`): trocar duas letras ali
    faz todo merge de verdade descer a rota da releitura — nome errado no
    painel, e-mail "refizemos a leitura" (mentira num merge), sufixo errado no
    revogar, selo roxo e aviso do admin.html (que também são `startsWith('mg')`);
  • um `break`/`[:1]` na rede do selo, que deixa passar toda linha MEDIDA com
    procedência só de texto menos a primeira (regra dura nº1);
  • a ordem em que o veredito da juíza volta pras pranchas.

🔑 Um lugar só. Três arquivos de teste com a mesma bancada divergem sozinhos —
é a lição de `_corpo.py`, e vale igual quando o que se compartilha é banco de
mentira em vez de recorte de fonte.

⏭️ `test_merge_criar_executa.py` tem uma bancada IRMÃ (a fixture `criar`), que
substitui o `_merge_montar` inteiro por um dublê. Ela não foi absorvida aqui
porque os guardas deste módulo precisam do `_merge_montar` RODANDO (é lá que
mora a ordem das juízas) — mas são duas bancadas do mesmo endpoint, e duas
bancadas do mesmo endpoint divergem. Vale unificar quando alguém mexer nas duas.
"""
import os
import sys
import threading

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import main as _m  # noqa: E402


class Req(object):
    """O pedaço de `Request` que estas rotas realmente leem."""

    def __init__(self, **qp):
        self.query_params = {k: str(v) for k, v in qp.items()}
        self.headers = {"user-agent": "bancada"}


_ThreadReal = threading.Thread


class _NaHora(object):
    """Roda o alvo dentro do `start()`, sem thread nenhuma."""

    def __init__(self, target, args, kwargs):
        self._t, self._a, self._k = target, args, kwargs

    def start(self):
        if self._t:
            self._t(*self._a, **self._k)

    def join(self, *a, **k):
        pass

    def is_alive(self):
        return False


def thread_do_email(target=None, args=(), kwargs=None, daemon=None, **extra):
    """`threading.Thread` de bancada — e SÓ pro e-mail.

    O e-mail sai em thread desde 23/08; se ele rodar de verdade, o guarda mede
    antes de a coisa acontecer e fica verde por corrida. Então essa thread roda
    na hora.

    🪤 07/09: a 1ª versão disto substituía TODA thread. O `ThreadPoolExecutor`
    das juízas (`_merge_montar`) monta seus operários com `threading.Thread` e
    o operário é um laço que espera na fila — rodar ele "na hora" pendura o
    merge inteiro pra sempre. O merge ficou travado até o faulthandler contar.
    Por isso só o alvo definido em `main` roda inline; o resto é thread real.
    """
    if getattr(target, "__module__", "") == "main":
        return _NaHora(target, args, kwargs or {})
    return _ThreadReal(target=target, args=args, kwargs=kwargs or {},
                       daemon=daemon, **extra)


def item(ref_sheet, descricao="Porta interna 0,80 x 2,10", confidence="estimado",
         quantity=1, unit="un", observations="", origem="", **extra):
    """Uma linha de `project_items` como o banco devolve."""
    linha = {"item_num": "1", "description": descricao, "unit": unit,
             "quantity": quantity, "observations": observations,
             "ref_sheet": ref_sheet, "confidence": confidence,
             "discipline": "arquitetura", "section": "esquadrias",
             "sort_order": 1, "origem": origem}
    linha.update(extra)
    return linha


def itens(ref_sheet, n_itens, n_medidos, rotulo="", **kw):
    """`n_itens` linhas da mesma prancha, `n_medidos` delas com selo MEDIDO.

    `rotulo` marca de qual LEITURA a linha veio. Serve pra o teste distinguir
    as duas listas quando elas são passadas adiante — sem isso, mandar a lista
    do pai duas vezes pra juíza é indistinguível de mandar as duas certas."""
    fora = []
    for i in range(n_itens):
        medido = i < n_medidos
        fora.append(item(
            ref_sheet,
            descricao="%s%s — item %d" % (rotulo + " " if rotulo else "",
                                          ref_sheet, i),
            confidence="confirmado" if medido else "estimado",
            # medição de geometria de verdade: a rede do selo ABSOLVE
            observations="Fonte: contagem de blocos no layer" if medido else "",
            origem="dxf_geom" if medido else "",
            **kw))
    return fora


class Banco(object):
    """Supabase de mentira. Guarda o que foi GRAVADO — é isso que os testes leem."""

    def __init__(self, projetos, itens_por_job, revisoes=0):
        self.projetos = {k: dict(v) for k, v in projetos.items()}
        self.itens = {k: [dict(x) for x in v] for k, v in itens_por_job.items()}
        self.revisoes = revisoes
        self.patches = []
        self.inseridos = []
        self.logs = []
        self.emails = []

    # ── leitura sem status ────────────────────────────────────────────────
    def rows(self, method, path, **kw):
        params = kw.get("params") or {}
        if path != "projects":
            return []
        if "job_id" in params:
            jid = str(params["job_id"]).replace("eq.", "")
            p = self.projetos.get(jid)
            return [dict(p)] if p else []
        if "parent_job_id" in params:
            pai = str(params["parent_job_id"]).replace("eq.", "")
            return [dict(p) for p in self.projetos.values()
                    if p.get("parent_job_id") == pai and p.get("is_eval")]
        return []

    # ── leitura paginada (o `_merge_carregar` usa esta) ───────────────────
    def tudo(self, path, params=None, **kw):
        params = params or {}
        jid = str(params.get("job_id", "")).replace("eq.", "")
        if str(path).strip("/").startswith("project_items"):
            return 200, [dict(x) for x in self.itens.get(jid, [])]
        return 200, []

    # ── leitura/escrita com status ────────────────────────────────────────
    def service(self, method, path, body=None, params=None, **kw):
        params = params or {}
        jid = str(params.get("job_id", "")).replace("eq.", "")
        alvo = str(path).strip("/").split("?")[0]
        if method == "GET" and alvo == "project_items":
            return 200, [dict(x) for x in self.itens.get(jid, [])]
        if method == "GET" and alvo == "item_reviews":
            if self.revisoes < 0:
                return 500, None
            return 200, [{"id": i} for i in range(self.revisoes)]
        if method == "POST" and alvo == "projects":
            novo = dict(body or {})
            self.projetos[novo.get("job_id")] = novo
            self.inseridos.append(novo)
            return 201, None
        if method == "POST" and alvo == "project_items":
            for linha in (body or []):
                self.itens.setdefault(linha.get("job_id"), []).append(dict(linha))
            return 201, None
        if method == "PATCH" and alvo == "projects":
            self.patches.append({"job_id": jid, "body": dict(body or {})})
            self.projetos.setdefault(jid, {}).update(body or {})
            return 204, None
        return 200, []

    # ── o que foi gravado, do jeito que os testes perguntam ───────────────
    def itens_do(self, job_id):
        return list(self.itens.get(job_id) or [])


def instalar(monkeypatch, banco, juiza=None):
    """Prende tudo que toca rede. `juiza` recebe (prancha, itens_pai, itens_filho)
    e devolve o veredito; o padrão é "não consegui ler" (a contagem decide).

    Devolve a lista de chamadas da juíza — cada uma com a prancha E as duas
    listas que ela recebeu, porque "veio o veredito certo" e "veio o veredito
    da prancha certa" são coisas diferentes."""
    chamadas = []

    def _log(stage, msg, *a, **k):
        banco.logs.append((stage, str(msg)))
    monkeypatch.setattr(_m, "_require_admin", lambda *a, **k: True)
    monkeypatch.setattr(_m, "_log_error", _log)
    monkeypatch.setattr(_m, "_supa_rows", banco.rows)
    monkeypatch.setattr(_m, "_supa_rest_tudo", banco.tudo)
    monkeypatch.setattr(_m, "_supa_rest_service", banco.service)
    monkeypatch.setattr(_m, "_supabase_insert", lambda *a, **k: None)
    monkeypatch.setattr(_m, "_notify_admin", lambda *a, **k: True)
    monkeypatch.setattr(_m, "_email_auto_recente", lambda *a, **k: False)
    monkeypatch.setattr(_m, "_email_auto_registrar", lambda *a, **k: None)

    def _smtp(to_email, subject, html_body, text_body="", log_kind="email"):
        banco.emails.append({"para": to_email, "assunto": subject,
                             "html": html_body, "tipo": log_kind})
        return True
    monkeypatch.setattr(_m, "_send_email_smtp", _smtp)

    def _juiza(prancha, ip, if_):
        chamadas.append({"prancha": prancha, "pai": list(ip), "filho": list(if_)})
        return (juiza(prancha, ip, if_) if juiza
                else {"lado": None, "motivo": "não consegui ler"})
    monkeypatch.setattr(_m, "_merge_juiza_prancha", _juiza)
    monkeypatch.setattr(threading, "Thread", thread_do_email)
    return chamadas
