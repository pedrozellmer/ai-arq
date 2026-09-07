# -*- coding: utf-8 -*-
"""O botão Liberar e o vigia automático, EXECUTADOS — não lidos.

🩸 06/09/2026. Os guardas que este arquivo substitui liam `main.py` procurando
frase (`'_e_merge = str(eval_job_id).startswith("mg")' in corpo`,
`"_email_auto_recente" in bloco`). Mutação provou que não viam:

  • a linha `_e_merge = str(eval_job_id).startswith("mg")` MANTIDA, com
    `_e_merge = False` na linha seguinte — o merge vira "nova leitura (motor
    atualizado)" no painel do cliente e dispara o e-mail da releitura;
  • `dias=7` virando `dias=0` nas duas portas: a janela do cooldown some e a
    trava que nasceu do caso "3 e-mails num dia" nunca mais pega;
  • `email_motivo = (...)` virando `_motivo_perdido = (...)`: o endpoint segura
    o e-mail e devolve motivo NENHUM pra quem clicou;
  • `_log_error(...)` do caminho automático trocado por um lambda mudo;
  • no PATCH da liberação automática, sumir com o `user_id`: o job é renomeado
    mas NUNCA chega ao painel do cliente.

Aqui a rota é CHAMADA. O que vale é a linha que foi gravada no banco, o e-mail
que saiu (ou não) e o motivo que volta pra quem clicou.
"""
import datetime as _dt
import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main  # noqa: E402
import _merge_bancada as _mb  # noqa: E402


# ═════════════════════════════════════════════════════════════════════════════
#  Bancada
# ═════════════════════════════════════════════════════════════════════════════
PAI_ID = "p1df33ea"
PAI = {"job_id": PAI_ID, "user_id": "u-cliente-19", "user_email": "cliente-19@exemplo",
       "user_name": "Fulano de Tal", "project_name": "Residência Alto da Serra",
       "created_at": "2026-08-20T19:37:48+00"}


class _Req(object):
    """O mínimo de Request que a rota lê."""

    def __init__(self, revogar=False):
        self.query_params = {"revogar": "1"} if revogar else {}
        self.headers = {"user-agent": "bancada"}


def _itens(n_itens, n_medidos, prancha="4366-EL-E"):
    fora = []
    for i in range(n_itens):
        fora.append({"confidence": "confirmado" if i < n_medidos else "estimado",
                     "ref_sheet": prancha,
                     "description": "Item %d" % i, "unit": "un", "quantity": 1})
    return fora


class Banco(object):
    """Supabase de mentira. Guarda o que foi GRAVADO — é isso que os testes leem."""

    def __init__(self, filho, itens_pai, itens_filho, revisoes=0, revisoes_status=200):
        self.projects = {PAI_ID: dict(PAI), filho["job_id"]: filho}
        self.itens = {PAI_ID: itens_pai, filho["job_id"]: itens_filho}
        self.revisoes = revisoes
        self.revisoes_status = revisoes_status
        self.patches = []
        self.logs = []

    # ── leitura sem status (o que a rota usa pros projetos) ──────────────
    def supa_rows(self, method, path, **kw):
        params = kw.get("params") or {}
        jid = str(params.get("job_id", "")).replace("eq.", "")
        if path == "projects":
            row = self.projects.get(jid)
            return [dict(row)] if row else []
        if path == "project_items":
            return list(self.itens.get(jid) or [])
        return []

    # ── leitura/escrita com status ───────────────────────────────────────
    def supa_service(self, method, path, body=None, params=None, prefer=None,
                     timeout=15):
        params = params or {}
        jid = str(params.get("job_id", "")).replace("eq.", "")
        if method == "GET" and path.strip("/").startswith("project_items"):
            return 200, list(self.itens.get(jid) or [])
        if method == "GET" and path.strip("/").startswith("item_reviews"):
            if self.revisoes_status != 200:
                return self.revisoes_status, None
            return 200, [{"id": i} for i in range(self.revisoes)]
        if method == "PATCH" and path.strip("/").startswith("projects"):
            self.patches.append({"job_id": jid, "body": dict(body or {})})
            self.projects.setdefault(jid, {}).update(body or {})
            return 204, None
        return 200, []


@pytest.fixture
def bancada(monkeypatch):
    """Tudo que toca rede fica preso. Devolve um montador de cenário."""
    estado = {"emails": [], "banco": None, "auto_log": []}

    monkeypatch.setattr(main, "_require_admin", lambda *a, **k: True)
    monkeypatch.setattr(main, "_supabase_insert", lambda *a, **k: None)
    monkeypatch.setattr(main, "_notify_admin", lambda *a, **k: True)

    def _log(stage, msg, *a, **k):
        estado.setdefault("logs", []).append((stage, str(msg)))
    monkeypatch.setattr(main, "_log_error", _log)

    # o SMTP e o registro do cooldown
    def _smtp(to_email, subject, html_body, text_body="", log_kind="email"):
        estado["emails"].append({"para": to_email, "assunto": subject,
                                 "html": html_body, "kind": log_kind})
        return True
    monkeypatch.setattr(main, "_send_email_smtp", _smtp)

    # `_email_auto_recente` roda DE VERDADE: o urlopen é que é de mentira, e
    # ele HONRA o corte `sent_at=gte.` — sem isso a janela de 7 dias não é
    # medida por teste nenhum.
    class _Resp(object):
        def __init__(self, dados):
            self._d = json.dumps(dados).encode("utf-8")

        def read(self):
            return self._d

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _urlopen(req, timeout=10):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "email_auto_log" not in url:
            return _Resp([])
        corte = ""
        for parte in url.split("&"):
            if "sent_at=gte." in parte:
                corte = urllib.parse.unquote(parte.split("sent_at=gte.", 1)[1])
        vivos = [x for x in estado["auto_log"]
                 if not corte or x.isoformat() >= corte]
        return _Resp([{"id": 1} for _ in vivos])
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)

    # o e-mail sai numa thread — aqui ela é síncrona, senão o teste mede antes
    class _ThreadJa(object):
        def __init__(self, target=None, daemon=None, **k):
            self._t = target

        def start(self):
            if self._t:
                self._t()
    monkeypatch.setattr(threading, "Thread", _ThreadJa)
    monkeypatch.setattr(time, "sleep", lambda *_a: None)

    def _monta(job_id, itens_filho=None, itens_pai=None, revisoes=0,
               revisoes_status=200, nome_filho=None, recebeu_ha_dias=None):
        filho = {"job_id": job_id, "parent_job_id": PAI_ID, "is_eval": True,
                 "user_id": "eval", "status": "done",
                 "project_name": nome_filho if nome_filho is not None
                 else "[TESTE] Residência Alto da Serra — combinada",
                 "warnings": [], "created_at": "2026-08-24T19:37:48+00"}
        b = Banco(filho, itens_pai if itens_pai is not None else _itens(147, 92),
                  itens_filho if itens_filho is not None else _itens(307, 179),
                  revisoes, revisoes_status)
        estado["banco"] = b
        monkeypatch.setattr(main, "_supa_rows", b.supa_rows)
        monkeypatch.setattr(main, "_supa_rest_service", b.supa_service)
        if recebeu_ha_dias is not None:
            estado["auto_log"].append(
                _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=recebeu_ha_dias))
        return b

    estado["monta"] = _monta
    return estado


# ═════════════════════════════════════════════════════════════════════════════
#  O Liberar tem que distinguir merge de releitura
# ═════════════════════════════════════════════════════════════════════════════
def test_o_liberar_reconhece_o_merge_pelo_prefixo(bancada):
    """O prefixo 'mg' é a ÚNICA coisa que separa os dois caminhos. Se ele deixa
    de ser lido, o merge segue por toda a rota do filhote — nome, e-mail e
    sufixo de revogação.

    🪤 07/09 (cético): este guarda FABRICA os job_id, então prova que o prefixo
    é LIDO e nunca que ele é ESCRITO. Quem fecha a outra metade é o irmão
    `test_o_prefixo_mg_vem_do_GERADOR_do_merge_criar`, logo abaixo."""
    bancada["monta"]("mg634d18")
    main.admin_liberar_filhote("mg634d18", _Req())
    nome_merge = bancada["banco"].patches[-1]["body"]["project_name"]

    bancada["emails"].clear()
    bancada["monta"]("ev597afa", nome_filho="[TESTE] Residência Alto da Serra — avaliação")
    main.admin_liberar_filhote("ev597afa", _Req())
    nome_releitura = bancada["banco"].patches[-1]["body"]["project_name"]

    assert nome_merge != nome_releitura, (
        "merge e releitura foram renomeados IGUAL — o prefixo 'mg' deixou de "
        "ser lido (os dois saíram como %r)" % nome_merge)
    assert "combinada" in nome_merge and "nova leitura" in nome_releitura


def test_o_merge_ganha_nome_proprio_no_painel_do_cliente(bancada):
    """Chamar merge de 'nova leitura (motor atualizado)' seria mentir no título
    da linha que o cliente vê no painel dele."""
    b = bancada["monta"]("mg634d18")
    main.admin_liberar_filhote("mg634d18", _Req())
    nome = b.patches[-1]["body"]["project_name"]
    assert nome.endswith(" — versão combinada (o melhor das duas leituras)"), (
        "o merge chegou ao painel do cliente com o nome %r" % nome)
    assert b.patches[-1]["body"]["user_id"] == PAI["user_id"], (
        "o filhote foi renomeado mas não apontou pro dono — não aparece pra ele")


def test_o_liberar_escolhe_o_email_certo(bancada):
    """O e-mail do filhote diz 'refizemos a leitura'. Num merge isso é falso."""
    bancada["monta"]("mg634d18")
    main.admin_liberar_filhote("mg634d18", _Req())
    assert len(bancada["emails"]) == 1, "o merge não avisou o cliente"
    html = bancada["emails"][0]["html"].lower()
    assert "refizemos a leitura" not in html, (
        "o cliente do MERGE recebeu o e-mail da releitura")
    assert bancada["emails"][0]["kind"] == "leitura_combinada"

    bancada["emails"].clear()
    bancada["monta"]("ev597afa")
    main.admin_liberar_filhote("ev597afa", _Req())
    assert bancada["emails"][0]["kind"] == "leitura_nova", (
        "a releitura passou a mandar o e-mail da combinada — o espelho do bug")


def _banco_do_merge():
    """Um par original+releitura pronto pro `/merge-criar`, com prancha ganha
    de cada lado (senão o merge não mede mais que a melhor leitura sozinha e a
    rota recusa criar, com razão)."""
    projetos = {
        PAI_ID: dict(PAI, status="done", typology="office",
                     project_type="arquitetura", warnings=[]),
        "ev597afa": {"job_id": "ev597afa", "parent_job_id": PAI_ID, "is_eval": True,
                     "status": "done", "user_id": "eval", "warnings": [],
                     "project_name": "[TESTE] Residência Alto da Serra — avaliação",
                     "created_at": "2026-08-24T19:37:48+00"},
    }
    itens_por_job = {
        PAI_ID: _mb.itens("ARQ-01", 10, 6) + _mb.itens("EL-02", 8, 2),
        "ev597afa": _mb.itens("ARQ-01", 10, 3) + _mb.itens("EL-02", 8, 5),
    }
    return _mb.Banco(projetos, itens_por_job)


def test_o_prefixo_mg_vem_do_GERADOR_do_merge_criar(monkeypatch):
    """🩸 07/09 — a metade que faltava: o 'mg' é ESCRITO por `/merge-criar`.

    Toda a bancada do merge fabricava os job_id ('mg634d18'), então provava
    só que `startswith('mg')` é lido. Trocando duas letras no gerador
    (`novo_id = "mg" + uuid…`), TODO merge de verdade deixa de casar com o
    prefixo e desce a rota da releitura inteira: nome "nova leitura (motor
    atualizado)" no painel do cliente, e-mail "refizemos a leitura" (que num
    merge é mentira), sufixo errado no revogar — e no admin.html o selo roxo e
    o aviso "libere a combinada", que também são `startsWith('mg')`.

    Aqui o merge é CRIADO de verdade e o id que ELE gerou é o que vai pro
    Liberar. Não há string de merge escrita à mão neste teste."""
    b = _banco_do_merge()
    _mb.instalar(monkeypatch, b)

    criado = main.admin_merge_criar("ev597afa", _mb.Req())
    novo = criado["job_id"]
    assert novo.startswith("mg"), (
        "o gerador do merge parou de escrever o prefixo 'mg' (saiu %r) — a "
        "rota do Liberar, o e-mail e o admin.html todos reconhecem o merge "
        "por ele" % novo)

    b.emails.clear()
    main.admin_liberar_filhote(novo, _mb.Req())
    nome = b.patches[-1]["body"]["project_name"]
    assert nome.endswith(" — versão combinada (o melhor das duas leituras)"), (
        "o merge que o /merge-criar acabou de gerar (%s) chegou ao painel do "
        "cliente como %r" % (novo, nome))
    assert len(b.emails) == 1 and b.emails[0]["tipo"] == "leitura_combinada", (
        "o merge gerado pelo /merge-criar recebeu o e-mail %r"
        % [e["tipo"] for e in b.emails])


def test_revogar_devolve_o_nome_de_teste_certo(bancada):
    """🪤 Em 23/08 o revogar gravava de volta o nome JÁ renomeado e o job ficava
    marcado como liberado depois de recolhido. Tem que funcionar pros DOIS
    sufixos."""
    b = bancada["monta"](
        "mg634d18",
        nome_filho="Residência Alto da Serra — versão combinada (o melhor das duas leituras)")
    main.admin_liberar_filhote("mg634d18", _Req(revogar=True))
    corpo = b.patches[-1]["body"]
    assert corpo["user_id"] == "eval", "revogar não tirou o job do painel do cliente"
    assert corpo["project_name"] == "[TESTE] Residência Alto da Serra — combinada", (
        "revogar gravou %r — o job continua com cara de liberado"
        % corpo["project_name"])
    assert not bancada["emails"], "revogar mandou e-mail pro cliente"

    b2 = bancada["monta"](
        "ev597afa",
        nome_filho="Residência Alto da Serra — nova leitura (motor atualizado)")
    main.admin_liberar_filhote("ev597afa", _Req(revogar=True))
    assert b2.patches[-1]["body"]["project_name"] == \
        "[TESTE] Residência Alto da Serra — avaliação"


# ═════════════════════════════════════════════════════════════════════════════
#  O teto de 1 automático por semana vale nas DUAS portas
# ═════════════════════════════════════════════════════════════════════════════
def test_o_botao_MANUAL_consulta_o_teto_antes_de_mandar(bancada):
    """🚨 O caso da cliente-20: 3 e-mails num dia. A liberação chamava o e-mail
    POR FORA do cooldown, então essa porta nunca passou pela regra."""
    bancada["monta"]("ev597afa", recebeu_ha_dias=3)
    r = main.admin_liberar_filhote("ev597afa", _Req())
    assert not bancada["emails"], (
        "mandou automático pra quem já tinha recebido um há 3 dias — a regra "
        "do Pedro é no máximo 1 por semana")
    assert r["email_enviado"] is False

    # 🧪 Controle positivo: quem recebeu há 30 dias RECEBE.
    bancada["auto_log"].clear()
    bancada["monta"]("ev597afa", recebeu_ha_dias=30)
    main.admin_liberar_filhote("ev597afa", _Req())
    assert len(bancada["emails"]) == 1, (
        "a trava passou a segurar sempre — pior que não ter trava")


def test_o_motivo_VOLTA_pra_quem_libera_em_vez_de_sumir(bancada):
    """🪤 Bloquear calado seria pior que mandar: o cliente deixaria de saber que
    a leitura melhorou, e ninguém saberia que ele não soube."""
    bancada["monta"]("ev597afa", recebeu_ha_dias=2)
    r = main.admin_liberar_filhote("ev597afa", _Req())
    motivo = r.get("email_motivo") or ""
    assert motivo, "o endpoint segurou o e-mail e devolveu motivo NENHUM"
    assert "NÃO enviado" in motivo, motivo
    assert "painel" in motivo, (
        "o motivo não diz que a leitura JÁ está no painel — quem lê vai achar "
        "que a liberação falhou: %r" % motivo)
    assert "à mão" in motivo or "a mão" in motivo, (
        "não aponta a saída (falar à mão), que é o que a regra manda quando a "
        "máquina se cala: %r" % motivo)


def test_CONTROLE_o_teto_existe_e_e_de_7_dias(bancada):
    """🧪 A janela medida na função de verdade, com o log honrando o corte.

    Sem isto, os testes acima poderiam passar com um cooldown de zero dia."""
    bancada["monta"]("ev597afa")
    bancada["auto_log"].append(
        _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=3))
    assert main._email_auto_recente("cliente-19@exemplo") is True, (
        "quem recebeu há 3 dias não foi visto pela janela de 7 — a janela "
        "encolheu")
    bancada["auto_log"].clear()
    bancada["auto_log"].append(
        _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=9))
    assert main._email_auto_recente("cliente-19@exemplo") is False, (
        "quem recebeu há 9 dias continua segurado — a janela cresceu e a "
        "esteira inteira cala")


# ═════════════════════════════════════════════════════════════════════════════
#  O caminho AUTOMÁTICO (a juíza libera sozinha)
# ═════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def juiza(monkeypatch):
    """A IA que decide a liberação automática, respondendo o que o teste manda."""
    veredito = {"liberar": True, "motivo": "preencheu pintura e forro que estavam em branco"}

    class _Bloco(object):
        def __init__(self, t):
            self.text = t

    class _R(object):
        def __init__(self, t):
            self.content = [_Bloco(t)]

    import anthropic
    import llm_retry
    monkeypatch.setattr(anthropic, "Anthropic", lambda **k: object())
    monkeypatch.setattr(llm_retry, "call_with_retry",
                        lambda *a, **k: _R(json.dumps(veredito)))
    return veredito


def test_e_o_caminho_AUTOMATICO_tambem(bancada, juiza):
    """A liberação automática usa a mesma porta e tem o mesmo risco — com o
    agravante de não ter ninguém pra ler o aviso."""
    bancada["monta"]("ev597afa", recebeu_ha_dias=2)
    main._auto_liberar_filhote_quando_pronto("ev597afa", PAI_ID, timeout_min=1)
    assert not bancada["emails"], (
        "o caminho automático mandou e-mail pra quem já recebeu um há 2 dias")

    # 🧪 Controle positivo: fora da janela, o aviso SAI.
    bancada["auto_log"].clear()
    bancada["monta"]("ev597afa", recebeu_ha_dias=40)
    main._auto_liberar_filhote_quando_pronto("ev597afa", PAI_ID, timeout_min=1)
    assert len(bancada["emails"]) == 1, (
        "o automático parou de avisar até quem está fora da janela")


def test_o_automatico_deixa_RASTRO_quando_segura(bancada, juiza):
    """Sem log, "não mandei" e "falhou o SMTP" viram a mesma coisa no escuro."""
    bancada["monta"]("ev597afa", recebeu_ha_dias=2)
    main._auto_liberar_filhote_quando_pronto("ev597afa", PAI_ID, timeout_min=1)
    rastro = [m for _s, m in bancada.get("logs", []) if "SEGURADO" in m]
    assert rastro, (
        "segurou o e-mail sem registrar por quê — o que ficou no log foi: %s"
        % [m[:60] for _s, m in bancada.get("logs", [])])


def test_a_liberacao_acontece_mesmo_quando_o_email_e_segurado(bancada, juiza):
    """🔒 O que NÃO pode: o teto de e-mail impedir a leitura nova de CHEGAR ao
    painel. São duas coisas diferentes — uma é avisar, a outra é entregar."""
    b = bancada["monta"]("ev597afa", recebeu_ha_dias=2)
    main._auto_liberar_filhote_quando_pronto("ev597afa", PAI_ID, timeout_min=1)
    assert not bancada["emails"], "controle: o e-mail tinha que ser segurado aqui"
    assert b.patches, "o filhote não foi liberado — nada foi gravado"
    corpo = b.patches[-1]["body"]
    assert corpo.get("user_id") == PAI["user_id"], (
        "o job foi renomeado mas NÃO apontou pro dono: %r — o cliente nunca "
        "vê a leitura nova, e o log diz 'LIBERADO'" % corpo)
    assert "nova leitura (motor atualizado)" in corpo.get("project_name", "")
