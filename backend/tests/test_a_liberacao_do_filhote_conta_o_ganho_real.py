# -*- coding: utf-8 -*-
"""Liberar o filhote: melhora é LINHA COM NÚMERO, o e-mail conta o ganho que
houve, e o filhote liberado fica com o contato do dono.

🩸 22/09/2026 — jobs ee801b82 (ontem, estrutura, 63 itens, 16 com número, 0
medidos, NPS 2) e f8d8e6d8 (hoje, os mesmos 7 PDFs, 91 itens, 61 zerados). O
Pedro quer entregar um filhote decente. A auditoria achou três defeitos na
porta de saída dele (A10 e A11):

  1. A porta 3 do e-mail chamava de melhora QUALQUER aumento de itens. Em PDF
     "medidos" é 0 por regra, então sobrava a contagem de itens — e o f8d8
     tinha 28 itens a mais e 61 linhas zeradas. Medido nas 21 liberações:
     ev572486 passou com 0/19 → 0/83 (medidos/itens), evbdbe1e com 6/28 → 5/47.
  2. O e-mail dizia "Melhoramos o motor" (no caso, era o MESMO commit), abria
     com "N prancha(s) que não tinham entrado agora entraram (30 → 38)" —
     contando variações do hint da IA — e o preheader diria "0 → 0 itens
     medidos do CAD".
  3. O filhote liberado continuava com `user_email` vazio: se a cliente
     anexasse ou refizesse a partir dele, o fim do job não mandava e-mail
     nenhum. 21 de 21 liberados estavam assim.

Os testes CHAMAM a rota, o vigia automático, o montador do e-mail e a esteira;
o banco, o SMTP e a IA são dublados.
"""
import datetime as _dt
import json
import os
import sys
import threading
import time
import urllib.request

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import main  # noqa: E402

PAI_ID = "ee801b82"
FILHO_ID = "ev0f8d8e"
EMAIL = "cliente-nn@example.com"
PAI = {"job_id": PAI_ID, "user_id": "u-cliente-nn", "user_email": EMAIL,
       "user_name": "Cliente NN", "project_name": "Projeto cliente-nn"}


def _itens(n, com_numero, medidos, arquivos, hints, verbas=0):
    """`n` linhas espalhadas por `arquivos` PDFs de 1 página, com `hints`
    variações de hint da IA no `ref_sheet` — como a leitura grava. As
    `verbas` primeiras linhas com número são "1 vb"."""
    fora = []
    for i in range(n):
        arq = "prancha-%s.pdf" % "ABCDEFG"[i % arquivos]
        verba = i < verbas
        fora.append({"confidence": "confirmado" if i < medidos else "estimado",
                     "ref_sheet": "%s (VISTA %d – PLANTA / CORTE)" % (arq, i % hints),
                     "quantity": (1 if verba else 1.5) if i < com_numero else 0,
                     "description": "Item %d" % i, "unit": "vb" if verba else "m³"})
    return fora


#: o ee801b82 como está no banco: 63 itens, 16 com número, 0 medidos, 5 dos 7
#: PDFs (2 perdidos no parse), 30 variações de ref_sheet.
_PAI_ITENS = _itens(63, 16, 0, 5, 30)


def _filho_bom():
    """Um filhote BOM de verdade: as 7 pranchas, 16 → 40 linhas com quantidade
    e MENOS linha zerada (47 → 30).
    🩸 22/09 (revisão): até aqui o "filhote bom" era 91/30/7 — as contagens da
    releitura REAL do f8d8, que foi de tipo errado. Ver o teste do caso."""
    return _itens(70, 40, 0, 7, 38)


class _Banco(object):
    """Supabase de mentira. Guarda o que foi GRAVADO."""

    def __init__(self, itens_filho, itens_pai=None):
        self.projects = {
            PAI_ID: dict(PAI),
            FILHO_ID: {"job_id": FILHO_ID, "parent_job_id": PAI_ID, "is_eval": True,
                       "user_id": "eval", "user_email": "", "user_name": "",
                       "status": "done", "warnings": [],
                       "project_name": "[TESTE] Projeto cliente-nn — avaliação"}}
        self.itens = {PAI_ID: itens_pai if itens_pai is not None else _PAI_ITENS,
                      FILHO_ID: itens_filho}
        self.patches = []

    def rows(self, method, path, **kw):
        jid = str((kw.get("params") or {}).get("job_id", "")).replace("eq.", "")
        if path == "projects":
            row = self.projects.get(jid)
            return [dict(row)] if row else []
        if path == "project_items":
            return [dict(x) for x in self.itens.get(jid) or []]
        return []

    def service(self, method, path, body=None, params=None, **kw):
        jid = str((params or {}).get("job_id", "")).replace("eq.", "")
        if method == "GET" and path.strip("/").startswith("project_items"):
            return 200, [dict(x) for x in self.itens.get(jid) or []]
        if method == "GET" and path.strip("/").startswith("item_reviews"):
            return 200, []
        if method == "PATCH" and path.strip("/").startswith("projects"):
            self.patches.append(dict(body or {}))
            self.projects[jid].update(body or {})
            return 204, None
        return 200, []


class _ThreadJa(object):
    """O e-mail sai numa thread — aqui ela roda na hora."""

    def __init__(self, target=None, daemon=None, **k):
        self._t = target

    def start(self):
        if self._t:
            self._t()


class _Req(object):
    def __init__(self, revogar=False, sem_email=False):
        self.query_params = {}
        if revogar:
            self.query_params["revogar"] = "1"
        if sem_email:
            self.query_params["sem_email"] = "1"
        self.headers = {"user-agent": "bancada"}


@pytest.fixture
def bancada(monkeypatch):
    estado = {"emails": [], "logs": []}
    monkeypatch.setattr(main, "_require_admin", lambda *a, **k: True)
    monkeypatch.setattr(main, "_notify_admin", lambda *a, **k: True)
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, *a, **k: estado["logs"].append((stage, str(msg))))
    monkeypatch.setattr(main, "_email_auto_recente", lambda *a, **k: False)
    monkeypatch.setattr(main, "_email_auto_registrar", lambda *a, **k: None)

    def _smtp(to_email, subject, html_body, *a, **k):
        estado["emails"].append({"para": to_email, "assunto": subject, "html": html_body})
        return True
    monkeypatch.setattr(main, "_send_email_smtp", _smtp)
    monkeypatch.setattr(threading, "Thread", _ThreadJa)
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)

    def _monta(itens_filho, itens_pai=None):
        b = _Banco(itens_filho, itens_pai)
        monkeypatch.setattr(main, "_supa_rows", b.rows)
        monkeypatch.setattr(main, "_supa_rest_service", b.service)
        estado["banco"] = b
        return b
    estado["monta"] = _monta
    return estado


# ── a régua ─────────────────────────────────────────────────────────────────
def test_item_a_mais_NAO_e_melhora():
    """🩸 As duas liberações que passaram sem ganho, e o caso de hoje."""
    f = main._releitura_melhorou
    # evbdbe1e: 6/28 → 5/47 medidos/itens, 17 → 16 com número
    assert not f({"itens": 28, "medidos": 6, "com_numero": 17},
                 {"itens": 47, "medidos": 5, "com_numero": 16})
    # ee801b82 → um filhote que só ganha item zerado
    assert not f({"itens": 63, "medidos": 0, "com_numero": 16},
                 {"itens": 91, "medidos": 0, "com_numero": 16})


def test_CONTROLE_linha_com_numero_ou_medido_a_mais_e_melhora():
    f = main._releitura_melhorou
    # ev572486: 0/19 → 0/83 e 0 → 58 com número — ganho de verdade
    assert f({"itens": 19, "medidos": 0, "com_numero": 0},
             {"itens": 83, "medidos": 0, "com_numero": 58})
    assert f({"itens": 9, "medidos": 1, "com_numero": 4},
             {"itens": 8, "medidos": 4, "com_numero": 4})


def test_a_contagem_conta_arquivo_e_linha_com_numero(bancada):
    """🩸 "pranchas" era o número de STRINGS de `ref_sheet` (30 no ee801b82)."""
    bancada["monta"](_itens(91, 30, 0, 7, 38))
    c = main._contagem_para_liberar(PAI_ID)
    assert c["itens"] == 63 and c["com_numero"] == 16 and c["medidos"] == 0, c
    assert c["zerados"] == 47, c
    assert c["pranchas"] == 5, "contou variação de hint como prancha: %r" % c["pranchas"]


def test_verba_NAO_e_linha_com_quantidade(bancada):
    """🩸 22/09/2026 (revisão): "1 vb" contava como linha com número. No
    ev572486 ("0 → 58"), 20 das 58 eram verba ou prazo."""
    f = main._linha_tem_quantidade
    for un in ("vb", "VB", "verba", "%", "mês", "meses", "dia", "h"):
        assert not f({"quantity": 1, "unit": un}), un
    # 🧪 controle: quantidade de obra conta, zero não conta
    for un in ("m²", "m³", "m", "kg", "un", "cj"):
        assert f({"quantity": 2.5, "unit": un}), un
    assert not f({"quantity": 0, "unit": "m²"}) and not f({"quantity": None, "unit": "m²"})
    bancada["monta"](_itens(91, 30, 0, 7, 38), itens_pai=_itens(63, 16, 0, 5, 30, verbas=4))
    c = main._contagem_para_liberar(PAI_ID)
    assert c["com_numero"] == 12 and c["zerados"] == 47, (
        "a verba entrou na conta de linha com quantidade: %r" % c)


def test_mais_linha_zerada_que_linha_com_numero_NAO_e_melhora():
    """🩸 A releitura do f8d8 (tipo errado): 12 → 24 com quantidade, mas 47 →
    61 zeradas. Linha com número a mais não compensa ainda mais linha vazia."""
    f = main._releitura_melhorou
    assert not f({"medidos": 0, "com_numero": 12, "zerados": 47},
                 {"medidos": 0, "com_numero": 24, "zerados": 61})
    # 🧪 controles: ganho que não traz mais zerada (ou traz menos) é melhora
    assert f({"medidos": 0, "com_numero": 12, "zerados": 47},
             {"medidos": 0, "com_numero": 24, "zerados": 59})
    assert f({"medidos": 0, "com_numero": 16, "zerados": 47},
             {"medidos": 0, "com_numero": 40, "zerados": 30})
    # e medido a mais continua sendo melhora, com zerada ou sem
    assert f({"medidos": 1, "com_numero": 5, "zerados": 2},
             {"medidos": 3, "com_numero": 5, "zerados": 9})


# ── a rota: o e-mail só sai com ganho, e diz o ganho que houve ──────────────
def test_o_caso_filhote_com_mais_itens_e_o_mesmo_numero_NAO_manda_email(bancada):
    """🩸 O filhote do caso, se ele só trouxer item zerado a mais: a cliente
    não recebe "refizemos a leitura", e quem clicou lê o porquê.
    🩸 22/09 (revisão): e o porquê não pode dizer "não ficou melhor… nada" de
    um filhote que recuperou as 2 pranchas perdidas (5 → 7)."""
    bancada["monta"](_itens(91, 16, 0, 7, 38))
    r = main.admin_liberar_filhote(FILHO_ID, _Req())
    assert bancada["emails"] == [], "mandou 'refizemos a leitura' sem ganho nenhum"
    assert r["melhorou"] is False, r
    assert r["melhorou_em"] == "5 → 7 pranchas lidas", r["melhorou_em"]
    m = r["email_motivo"]
    assert "NÃO enviado" in m and "16 → 16" in m, m
    assert "5 → 7" in m and "não ficou melhor" not in m, m
    assert "painel" in m and "à mão" in m, m


def test_o_caso_REAL_do_f8d8_como_filhote_NAO_manda_email(bancada):
    """🩸 A releitura f8d8e6d8 (os mesmos 7 PDFs lidos como arquitetura) com as
    contagens do banco: 63 → 91 itens, 16 → 30 com número (4 → 6 verbas), 47
    → 61 zeradas, 5 → 7 arquivos. A 1ª régua a chamaria de melhora e o e-mail
    diria "16 → 30 linhas com quantidade"."""
    bancada["monta"](_itens(91, 30, 0, 7, 38, verbas=6),
                     itens_pai=_itens(63, 16, 0, 5, 30, verbas=4))
    r = main.admin_liberar_filhote(FILHO_ID, _Req())
    assert bancada["emails"] == [], "a releitura de tipo errado virou 'refizemos a leitura'"
    assert r["melhorou"] is False, r
    m = r["email_motivo"]
    assert "12 → 24" in m and "47 → 61" in m and "5 → 7" in m, m
    assert "linhas com quantidade" in r["melhorou_em"], r["melhorou_em"]


def test_com_ganho_o_email_conta_o_ganho_REAL(bancada):
    """O filhote bom: 7 de 7 pranchas e 16 → 40 linhas com número. O e-mail
    diz isso — e não diz "melhoramos o motor" nem "0 → 0 medidos"."""
    bancada["monta"](_filho_bom())
    r = main.admin_liberar_filhote(FILHO_ID, _Req())
    assert r["melhorou"] is True, r
    assert r["melhorou_em"] == "16 → 40 linhas com quantidade, 5 → 7 pranchas lidas", r
    assert len(bancada["emails"]) == 1 and bancada["emails"][0]["para"] == EMAIL
    html = bancada["emails"][0]["html"]
    assert "16 &rarr; 40 linhas com quantidade</b> (sem contar verba)" in html, html
    assert "2 prancha(s) que n&atilde;o tinham entrado agora entraram" in html, (
        "a conta de prancha não é por arquivo")
    assert "(5 &rarr; 7 pranchas lidas)" in html, html
    assert "medidos do CAD" not in html, (
        "o e-mail fala de medido com 0 dos dois lados: 0 → 0 não diz nada")
    assert "Melhoramos o motor" not in html and "melhoramos o motor" not in html


def test_zero_contra_zero_nao_sai_em_linha_nenhuma():
    """O "0 → 0" que o commit anterior tirou dos medidos também não pode sair
    nas linhas com quantidade (um DXF que só ganhou medido)."""
    _a = {"itens": 9, "medidos": 1, "com_numero": 0, "pranchas": 1}
    _d = {"itens": 9, "medidos": 3, "com_numero": 0, "pranchas": 1}
    _s, html = main._build_leitura_nova_email("cliente-nn", "Projeto", FILHO_ID, _a, _d)
    assert "1 &rarr; 3 medidos do CAD" in html, html
    assert "0 &rarr; 0" not in html and "0 → 0" not in html, html


def test_a_combinada_conta_linha_com_quantidade_e_nao_0_contra_0():
    """🩸 22/09/2026 (revisão, R5): o portão novo vale também pro MERGE, e deixa
    passar combinada cujo ganho é só linha com quantidade. O e-mail dela não
    sabia falar disso: "O que você ganha: uma leitura mais completa" e, no
    preheader, "0 itens medidos do CAD, contra 0 na leitura anterior"."""
    antes = {"itens": 40, "medidos": 0, "com_numero": 10, "zerados": 30,
             "pranchas": 3, "por_prancha": {}}
    depois = {"itens": 40, "medidos": 0, "com_numero": 25, "zerados": 15,
              "pranchas": 3, "por_prancha": {}}
    assert main._releitura_melhorou(antes, depois), "controle: o portão deixa passar"
    _s, html = main._build_leitura_combinada_email(
        "cliente-nn", "Projeto cliente-nn", "mg000001", antes, depois, [])
    assert "10 &rarr; 25 linhas com quantidade" in html, html
    assert "25 linhas com quantidade, contra 10 na leitura anterior" in html, html
    assert "uma leitura mais completa" not in html
    assert "0 itens medidos do CAD" not in html and "contra 0 na leitura" not in html, html
    # 🧪 controle: com medido de verdade, o medido aparece — como sempre
    _s, h2 = main._build_leitura_combinada_email(
        "cliente-nn", "Projeto cliente-nn", "mg000001",
        dict(antes, medidos=49), dict(depois, medidos=77), [])
    assert "49 &rarr; 77 itens medidos direto do CAD" in h2, h2
    assert "77 itens medidos do CAD, contra 49 na leitura anterior" in h2, h2


def test_medido_aparece_quando_algum_lado_tem(bancada):
    """Com medido de um dos lados, ele entra — inclusive se caiu."""
    _a = {"itens": 28, "medidos": 6, "com_numero": 17, "pranchas": 2}
    _d = {"itens": 47, "medidos": 5, "com_numero": 25, "pranchas": 2}
    _s, html = main._build_leitura_nova_email("cliente-nn", "Projeto", FILHO_ID, _a, _d)
    assert "6 &rarr; 5 medidos do CAD" in html, html
    assert "17 &rarr; 25 linhas com quantidade" in html


# ── A11: o filhote liberado fica com o contato do dono ──────────────────────
def test_o_filhote_liberado_fica_com_o_email_do_dono(bancada):
    """🩸 Com `user_email` vazio, o anexo ou o reprocesso que a cliente fizer
    em cima do filhote termina sem e-mail nenhum."""
    b = bancada["monta"](_itens(91, 30, 0, 7, 38))
    main.admin_liberar_filhote(FILHO_ID, _Req())
    corpo = b.patches[-1]
    assert corpo["user_id"] == PAI["user_id"]
    assert corpo.get("user_email") == EMAIL, (
        "o filhote foi liberado sem o e-mail do dono: %r" % corpo)
    assert corpo.get("user_name") == PAI["user_name"]


def test_revogar_devolve_o_filhote_mudo(bancada):
    """🔒 Projeto que o cliente não vê não pode mandar e-mail pra ele."""
    b = bancada["monta"](_itens(91, 30, 0, 7, 38))
    main.admin_liberar_filhote(FILHO_ID, _Req())
    bancada["emails"].clear()
    main.admin_liberar_filhote(FILHO_ID, _Req(revogar=True))
    corpo = b.patches[-1]
    assert corpo["user_id"] == "eval" and corpo.get("user_email") == "", corpo
    assert bancada["emails"] == []


def test_o_vigia_automatico_tambem_grava_o_contato_e_segura_sem_ganho(
        bancada, monkeypatch):
    """O caminho automático faz o mesmo movimento — e sem linha com número a
    mais não manda o e-mail (a juíza pode liberar por conteúdo; a contagem que
    o e-mail sabe contar não tem o que dizer)."""
    import anthropic
    import llm_retry

    class _Bloco(object):
        text = json.dumps({"liberar": True, "motivo": "organizou por estrutura"})

    class _R(object):
        content = [_Bloco()]
    monkeypatch.setattr(anthropic, "Anthropic", lambda **k: object())
    monkeypatch.setattr(llm_retry, "call_with_retry", lambda *a, **k: _R())
    b = bancada["monta"](_itens(91, 16, 0, 7, 38))
    b.projects[FILHO_ID]["user_id"] = "eval"
    main._auto_liberar_filhote_quando_pronto(FILHO_ID, PAI_ID, timeout_min=1)
    assert b.patches and b.patches[-1].get("user_email") == EMAIL, b.patches
    assert bancada["emails"] == [], "o automático mandou e-mail sem ganho"
    assert any("SEGURADO" in m and "16 → 16" in m for _s, m in bancada["logs"]), (
        bancada["logs"])


# ── a esteira não conta a nossa releitura como visita do cliente ────────────
def _esteira(monkeypatch, projetos):
    """Roda o `emails_auto_tick` em ensaio, com `projects` que HONRA o filtro
    `is_eval` da consulta — como o PostgREST."""
    monkeypatch.setattr(main, "TICK_SECRET", "")
    monkeypatch.setenv("EMAILS_AUTO", "1")
    monkeypatch.setattr(main, "_auth_admin_list_users", lambda *a, **k: [])
    monkeypatch.setattr(main, "_email_auto_ja_enviado", lambda *a, **k: False)
    monkeypatch.setattr(main, "_email_auto_recente", lambda *a, **k: False)
    monkeypatch.setattr(main, "_alertas_de_cadastro_ao_pedro",
                        lambda *a, **k: {"status": "dry"})
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)

    def _tudo(path, params=None, **k):
        if path == "projects":
            linhas = [dict(p) for p in projetos]
            if str((params or {}).get("is_eval", "")) == "not.is.true":
                linhas = [p for p in linhas if not p.get("is_eval")]
            return 200, linhas
        return 200, []
    monkeypatch.setattr(main, "_supa_rest_tudo", _tudo)
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (200, []))

    class _Vazio(object):
        def read(self):
            return b"[]"
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Vazio())

    class _R(object):
        headers = {}
    return main.emails_auto_tick(_R(), dry=1)


def _projeto(job_id, dias, is_eval=False):
    quando = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=dias)).isoformat()
    return {"job_id": job_id, "user_email": EMAIL, "user_name": "Cliente NN",
            "status": "done", "project_name": "Projeto cliente-nn",
            "created_at": quando, "is_eval": is_eval}


def test_a_esteira_ignora_o_filhote_liberado(monkeypatch):
    """🩸 Com o e-mail do dono no filhote, a releitura de 40 dias atrás
    viraria "último movimento" dela e dispararia o retorno_30d — que a conta
    de 70 dias atrás já não dispara."""
    r = _esteira(monkeypatch, [_projeto(PAI_ID, 70), _projeto(FILHO_ID, 40, is_eval=True)])
    assert r["status"] == "dry", r
    assert "retorno_30d" not in r["por_tipo"], (
        "a esteira contou a nossa releitura como visita da cliente: %r" % r)


def test_CONTROLE_a_esteira_ve_projeto_de_verdade_de_40_dias(monkeypatch):
    """🧪 Sem isto, o teste de cima passaria com uma esteira que nunca manda
    retorno_30d."""
    r = _esteira(monkeypatch, [_projeto(PAI_ID, 70), _projeto("f8d8e6d8", 40)])
    assert r["por_tipo"].get("retorno_30d") == 1, r


# ══════════════════════════════════════════════════════════════════════════
#  Liberar EM SILÊNCIO — quando o automático contaria metade da história
#  💡 23/09/2026, pedido do Pedro: "ou a gente bloqueia esse e-mail automático
#     e manda explicando tudo".
#  🩸 O caso: job que FALHOU por defeito nosso. O cliente leu "problema
#     técnico do nosso lado — reprocessar não resolve" e ficou com zero item.
#     Consertado o motor, a releitura entrega a planilha; mas o automático diz
#     "refizemos a leitura do seu projeto" e não menciona o erro. E mandar os
#     dois é a doença de 29/08 — dois e-mails em minutos dizendo o mesmo.
# ══════════════════════════════════════════════════════════════════════════
def test_sem_email_LIBERA_e_nao_manda_nada(bancada):
    bancada["monta"](_filho_bom())
    r = main.admin_liberar_filhote(FILHO_ID, _Req(sem_email=True))
    assert bancada["emails"] == [], "mandou o automático mesmo com sem_email=1"
    assert r["melhorou"] is True, "a liberação em si tem que acontecer: %r" % r


def test_sem_email_DIZ_por_que_nao_mandou(bancada):
    """🔑 Igual às outras três travas: o motivo volta na resposta, pra quem
    liberou saber que o silêncio foi de propósito — e não um e-mail perdido."""
    bancada["monta"](_filho_bom())
    m = main.admin_liberar_filhote(FILHO_ID, _Req(sem_email=True))["email_motivo"]
    assert "NÃO enviado" in m, m
    assert "sem_email" in m and "à mão" in m, m


def test_CONTROLE_sem_a_opcao_o_automatico_CONTINUA_saindo(bancada):
    """🧪 O padrão não mudou: liberar sem pedir silêncio avisa o cliente, que
    é o ponto do mecanismo desde 08/08 (1 de 44 voltava ao site sozinho)."""
    bancada["monta"](_filho_bom())
    main.admin_liberar_filhote(FILHO_ID, _Req())
    assert len(bancada["emails"]) == 1, "a opção nova calou o caminho normal"


def test_CONTROLE_sem_email_nao_atropela_a_trava_de_quem_REVISOU(bancada,
                                                                 monkeypatch):
    """A trava do cliente que revisou à mão é regra dura nº7 e NÃO depende
    desta opção: com ou sem ela, o automático não sai. E o motivo devolvido
    tem que ser o DA REVISÃO — quem liberou precisa saber que existe trabalho
    humano em risco, não só que ele pediu silêncio."""
    bancada["monta"](_filho_bom())
    _real = main._supa_rest_service

    def _com_revisoes(method, path, *a, **k):
        if method == "GET" and str(path).strip("/").startswith("item_reviews"):
            return 200, [{"id": 1}, {"id": 2}, {"id": 3}]
        return _real(method, path, *a, **k)

    monkeypatch.setattr(main, "_supa_rest_service", _com_revisoes)
    for req in (_Req(), _Req(sem_email=True)):
        bancada["emails"].clear()
        r = main.admin_liberar_filhote(FILHO_ID, req)
        assert bancada["emails"] == [], "empurrou a versão nova por cima da revisão dele"
        assert "revisou" in r["email_motivo"], r["email_motivo"]
