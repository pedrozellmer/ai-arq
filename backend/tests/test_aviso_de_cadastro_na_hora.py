# -*- coding: utf-8 -*-
"""O aviso de cadastro INCOMPLETO chega na hora — e o de "completou" também.

🩸 21/09/2026 — Pedro: "quando um cliente faz um cadastro incompleto, eu estou
recebendo esse e-mail muito tempo depois, uma hora e meia, duas horas [...] O
ideal é que eu recebesse no mesmo tempo [...] E aí, quando e caso esse
cliente complete o cadastro, aí sim eu receber mais um e-mail".

Medido nas 121 contas dos 60 dias anteriores:
  · quem COMPLETA é avisado em ~1 min (o aviso sai quando abre o painel);
  · quem PARA dependia do tick de e-mails — de hora em hora, SÓ das 8h às 20h
    de Brasília — que ainda esperava 30 min de conta. Mediana: 71 min; à noite,
    só às 8h do dia seguinte (até 10 h);
  · 2 contas pararam e completaram dias depois: nenhum 2º aviso existia.

Estes guardas EXECUTAM `_alertas_de_cadastro_ao_pedro` de verdade contra um
banco de mentira que avalia os filtros (e-mail do destinatário, lista de
kinds, e-mail/uid do perfil). Um dublê que devolvesse "sempre vazio" faria
todo mundo parecer nunca avisado — e o teste passaria mandando aviso repetido.
"""
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import main  # noqa: E402
from fastapi import HTTPException  # noqa: E402

AVISO = "aviso@exemplo.test"
KINDS = ("alerta_novo_cadastro", "alerta_cadastro_parou", "alerta_cadastro_completou")


def _ts(minutos_atras):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutos_atras)).isoformat()


class _Mundo:
    def __init__(self):
        self.contas = []          # o que a API de Auth devolve
        self.perfis = []          # o RETRATO de `profiles` do início da rodada
        self.perfis_agora = None  # a leitura AO VIVO (None = igual ao retrato)
        self.marcas = []          # email_auto_log (de todo mundo, não só do Pedro)
        self.enviados = []        # (assunto, corpo)
        self.smtp_ok = True
        self.st_perfis = 200
        self.st_marcas = 200
        self.st_grava = 201
        self.falha_uma_vez = set()   # kinds cuja PRÓXIMA gravação falha
        self.st_perfil_agora = 200
        self.logs = []

    # ── montagem ──
    def conta(self, email, minutos, uid=None, nome=""):
        uid = uid or "uid-%d" % (len(self.contas) + 1)
        self.contas.append({"id": uid, "email": email, "created_at": _ts(minutos),
                            "user_metadata": {"full_name": nome} if nome else {}})
        return uid

    def perfil(self, uid, email, minutos, nome=""):
        self.perfis.append({"user_id": uid, "email": email, "full_name": nome,
                            "created_at": _ts(minutos)})

    def marca(self, kind, ref, email=AVISO):
        self.marcas.append({"email": email, "kind": kind, "ref": ref})

    def marcas_de(self, kind):
        return sorted(m["ref"] for m in self.marcas if m["email"] == AVISO and m["kind"] == kind)

    def assuntos(self):
        return [a for a, _ in self.enviados]

    # ── dublês ──
    def tudo(self, path, params=None, **k):
        params = params or {}
        if path == "profiles":
            return (self.st_perfis, list(self.perfis) if self.st_perfis == 200 else [])
        if path == "email_auto_log":
            if self.st_marcas != 200:
                return (self.st_marcas, [])
            # avalia os filtros como o PostgREST: sem filtro, não filtra
            quem = params.get("email")
            kinds = re.fullmatch(r"in\.\((.*)\)", params.get("kind", ""))
            ks = kinds.group(1).split(",") if kinds else None
            return (200, [{"kind": m["kind"], "ref": m["ref"]} for m in self.marcas
                          if (quem is None or m["email"] == quem[3:])
                          and (ks is None or m["kind"] in ks)])
        raise AssertionError("tabela inesperada: %s" % path)

    def rest(self, metodo, path, body=None, params=None, prefer=None, **k):
        params = params or {}
        if metodo == "POST" and path.startswith("/email_auto_log"):
            assert "on_conflict=email,kind,ref" in path and "ignore-duplicates" in (prefer or "")
            if body.get("kind") in self.falha_uma_vez:
                self.falha_uma_vez.discard(body["kind"])
                return (503, None)
            if self.st_grava not in (200, 201, 204):
                return (self.st_grava, None)
            if not any(m == body for m in self.marcas):
                self.marcas.append(dict(body))
            return (self.st_grava, None)
        if metodo == "GET" and path.strip("/") == "profiles":
            if self.st_perfil_agora != 200:
                return (self.st_perfil_agora, None)
            base = self.perfis if self.perfis_agora is None else self.perfis_agora
            if "email" in params:
                alvo = params["email"][3:]
                return (200, [p for p in base if p["email"] == alvo][:1])
            if "user_id" in params:
                alvo = params["user_id"][3:]
                return (200, [p for p in base if p["user_id"] == alvo][:1])
        raise AssertionError("chamada inesperada: %s %s %s" % (metodo, path, params))

    def notify(self, assunto, corpo):
        if self.smtp_ok:
            self.enviados.append((assunto, corpo))
        return self.smtp_ok


@pytest.fixture
def mundo(monkeypatch):
    m = _Mundo()
    monkeypatch.setattr(main, "NOTIFY_EMAIL", AVISO)
    monkeypatch.setattr(main, "_auth_admin_list_users", lambda *a, **k: list(m.contas))
    monkeypatch.setattr(main, "_supa_rest_tudo", m.tudo)
    monkeypatch.setattr(main, "_supa_rest_service", m.rest)
    monkeypatch.setattr(main, "_notify_admin", m.notify)
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, *a, **k: m.logs.append((stage, str(msg))))
    monkeypatch.setattr(main, "_ALERTA_CADASTRO_SAIU_AQUI", set(), raising=False)
    monkeypatch.setattr(main, "_ALERTA_CADASTRO_FALHA_REGISTRADA", {"detalhe": None}, raising=False)
    # nada de rede de verdade: se algum caminho escapar dos dublês, estoura aqui
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("sem rede no teste")))
    return m


def _rodar(**k):
    return main._alertas_de_cadastro_ao_pedro(**k)


# ══════════════════════════════════════════════════════════════════════════
#  1 · o incompleto é avisado em minutos, não em horas
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_incompleto_de_6_min_e_avisado_e_marcado(mundo):
    mundo.conta("fulano@exemplo.test", minutos=6)
    r = _rodar()
    assert r["status"] == "ok" and r["cadastro_incompleto"] == 1, r
    assert mundo.assuntos() == ["Cadastro incompleto — fulano@exemplo.test"]
    assert "ainda não completou o cadastro" in mundo.enviados[0][1]
    assert "conta criada há 6 min" in mundo.enviados[0][1]
    assert "parou" not in mundo.enviados[0][1], "o código não sabe que a pessoa desistiu"
    assert "chega outro aviso" in mundo.enviados[0][1]
    assert mundo.marcas_de("alerta_novo_cadastro") == ["fulano@exemplo.test"]
    assert mundo.marcas_de("alerta_cadastro_parou") == ["fulano@exemplo.test"], (
        "sem a marca 'parou' o 2º aviso (completou) nunca sai")


def test_incompleto_de_menos_de_5_min_ainda_pode_estar_preenchendo(mundo):
    """90% dos que completam levam até 2,5 min (medido, 21/09)."""
    mundo.conta("fulano@exemplo.test", minutos=3)
    _rodar()
    assert mundo.enviados == [] and mundo.marcas == []


def test_o_limiar_e_5_min_e_nao_os_30_de_antes(mundo):
    """🩸 O tick horário esperava 30 min — e só rodava de hora em hora."""
    assert main._CADASTRO_MIN_ANTES_DE_PAROU == 5
    mundo.conta("fulano@exemplo.test", minutos=12)
    _rodar()
    assert len(mundo.enviados) == 1, "conta de 12 min sem perfil tem que ser avisada"


def test_conta_velha_nao_e_ressuscitada(mundo):
    mundo.conta("fulano@exemplo.test", minutos=37 * 60)
    _rodar()
    assert mundo.enviados == []


def test_conta_interna_nao_avisa(mundo, monkeypatch):
    monkeypatch.setattr(main, "ADMIN_EMAIL", "dono@exemplo.test")
    mundo.conta("dono+smoke@exemplo.test", minutos=10)
    _rodar()
    assert mundo.enviados == []


# ══════════════════════════════════════════════════════════════════════════
#  2 · o 2º aviso: completou DEPOIS de ter parado
# ══════════════════════════════════════════════════════════════════════════
def test_parou_e_depois_completou_manda_o_2o_aviso_uma_vez(mundo):
    uid = mundo.conta("fulano@exemplo.test", minutos=10, nome="Fulano")
    _rodar()
    assert mundo.assuntos() == ["Cadastro incompleto — fulano@exemplo.test"]

    mundo.perfil(uid, "fulano@exemplo.test", minutos=0.2, nome="Fulano de Tal")
    r = _rodar()
    assert r["completou_depois"] == 1, r
    assert mundo.assuntos()[-1] == "Completou o cadastro — fulano@exemplo.test"
    assert "Fulano de Tal" in mundo.enviados[-1][1], "o nome vem do perfil que acabou de nascer"
    assert mundo.marcas_de("alerta_cadastro_completou") == ["fulano@exemplo.test"]

    _rodar()
    _rodar()
    assert len(mundo.enviados) == 2, "o 'completou' repetiu"
    main._ALERTA_CADASTRO_SAIU_AQUI.clear()     # o servidor reiniciou
    _rodar()
    assert len(mundo.enviados) == 2, "depois de reiniciar, só o banco segura — e não segurou"


def test_o_2o_aviso_NAO_espera_a_carencia_do_perfil(mundo):
    """O aviso do painel não sai para quem já foi avisado (a marca
    `alerta_novo_cadastro` cala ele) — então não há corrida a evitar aqui."""
    uid = mundo.conta("fulano@exemplo.test", minutos=60)
    mundo.marca("alerta_novo_cadastro", "fulano@exemplo.test")
    mundo.marca("alerta_cadastro_parou", "fulano@exemplo.test")
    mundo.perfil(uid, "fulano@exemplo.test", minutos=0.1)
    _rodar()
    assert mundo.assuntos() == ["Completou o cadastro — fulano@exemplo.test"]


def test_parou_e_continua_parado_nao_manda_nada(mundo):
    mundo.conta("fulano@exemplo.test", minutos=300)
    mundo.marca("alerta_novo_cadastro", "fulano@exemplo.test")
    mundo.marca("alerta_cadastro_parou", "fulano@exemplo.test")
    _rodar()
    assert mundo.enviados == []


def test_conta_ANTIGA_marcada_pelo_backfill_tambem_ganha_o_2o_aviso(mundo):
    """As contas que pararam antes do conserto ganham a marca `parou` por SQL
    no deploy. A janela de 36 h é do 1º aviso — o 2º não tem prazo: há quem
    tenha completado 3,7 dias depois."""
    uid = mundo.conta("fulano@exemplo.test", minutos=40 * 24 * 60)
    mundo.marca("alerta_novo_cadastro", "fulano@exemplo.test")
    mundo.marca("alerta_cadastro_parou", "fulano@exemplo.test")
    mundo.perfil(uid, "fulano@exemplo.test", minutos=1)
    _rodar()
    assert mundo.assuntos() == ["Completou o cadastro — fulano@exemplo.test"]


def test_quem_completou_de_primeira_NAO_recebe_2o_aviso(mundo):
    """Sem a marca `parou`, completar não é notícia — senão os 99 que
    completaram de primeira ganhariam um 'completou' cada."""
    uid = mundo.conta("fulano@exemplo.test", minutos=60)
    mundo.perfil(uid, "fulano@exemplo.test", minutos=59)
    mundo.marca("alerta_novo_cadastro", "fulano@exemplo.test")
    _rodar()
    assert mundo.enviados == []


# ══════════════════════════════════════════════════════════════════════════
#  3 · o completo: o aviso do painel vem primeiro, sem duplicar
# ══════════════════════════════════════════════════════════════════════════
def test_completo_com_perfil_recente_deixa_o_aviso_do_painel_sair(mundo):
    uid = mundo.conta("fulano@exemplo.test", minutos=2)
    mundo.perfil(uid, "fulano@exemplo.test", minutos=1)
    _rodar()
    assert mundo.enviados == [], "disputou com o aviso do painel — sairiam dois"


def test_completo_que_nao_abriu_o_painel_e_avisado_sem_marca_parou(mundo):
    uid = mundo.conta("fulano@exemplo.test", minutos=10)
    mundo.perfil(uid, "fulano@exemplo.test", minutos=8)
    r = _rodar()
    assert r["cadastro_novo"] == 1, r
    assert mundo.assuntos() == ["Cadastro novo — fulano@exemplo.test"]
    assert "completou o cadastro" in mundo.enviados[0][1]
    assert mundo.marcas_de("alerta_cadastro_parou") == []


def test_ja_avisado_pelo_painel_nao_repete(mundo):
    uid = mundo.conta("fulano@exemplo.test", minutos=10)
    mundo.perfil(uid, "fulano@exemplo.test", minutos=8)
    mundo.marca("alerta_novo_cadastro", "fulano@exemplo.test")
    _rodar()
    assert mundo.enviados == []


def test_completou_DURANTE_a_rodada_nao_vira_parou(mundo):
    """🚨 O retrato de perfis é do início da rodada. Se a leitura ao vivo acha
    o perfil, a pessoa acabou de completar: o aviso do painel está saindo."""
    uid = mundo.conta("fulano@exemplo.test", minutos=9)
    mundo.perfis_agora = [{"user_id": uid, "email": "fulano@exemplo.test",
                           "full_name": "", "created_at": _ts(0)}]
    _rodar()
    assert mundo.enviados == [] and mundo.marcas == []


def test_perfil_achado_pelo_UID_quando_o_email_do_perfil_difere(mundo):
    uid = mundo.conta("fulano@exemplo.test", minutos=10)
    mundo.perfil(uid, "outro-endereco@exemplo.test", minutos=8)
    _rodar()
    assert mundo.assuntos() == ["Cadastro novo — fulano@exemplo.test"]


# ══════════════════════════════════════════════════════════════════════════
#  4 · na dúvida, cala — e o que falha deixa rastro
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("campo", ["st_perfis", "st_marcas"])
def test_leitura_que_falha_nao_manda_nada(mundo, campo):
    mundo.conta("fulano@exemplo.test", minutos=10)
    uid = mundo.conta("beltrano@exemplo.test", minutos=10)
    mundo.perfil(uid, "beltrano@exemplo.test", minutos=8)
    setattr(mundo, campo, 503)
    r = _rodar()
    assert r["status"] == "erro", r
    assert mundo.enviados == [], "sem saber quem tem perfil ou quem já foi avisado, chutou"


def test_rodada_que_nao_le_deixa_UMA_linha_de_rastro_por_queda(mundo):
    """Sem rastro, a falta de aviso se lê como "ninguém se cadastrou". Com uma
    linha a cada 5 min, uma queda de um dia vira 288 linhas."""
    mundo.conta("fulano@exemplo.test", minutos=10)
    mundo.st_perfis = 503
    for _ in range(3):
        _rodar()
    rastro = [m for s, m in mundo.logs if s == "alerta-cadastro:rodada-sem-leitura"]
    assert len(rastro) == 1, rastro
    mundo.st_perfis = 200
    _rodar()                                  # voltou: avisa e zera
    assert len(mundo.enviados) == 1
    mundo.st_perfis = 503
    _rodar()                                  # caiu de novo: nova linha
    rastro = [m for s, m in mundo.logs if s == "alerta-cadastro:rodada-sem-leitura"]
    assert len(rastro) == 2, rastro


def test_lista_de_contas_vazia_e_erro_nao_silencio(mundo):
    r = _rodar()
    assert r["status"] == "erro" and mundo.enviados == []


def test_perfil_ao_vivo_ilegivel_pula_sem_marcar(mundo):
    mundo.conta("fulano@exemplo.test", minutos=10)
    mundo.st_perfil_agora = 503
    _rodar()
    assert mundo.enviados == [] and mundo.marcas == []
    assert any(s == "alerta-cadastro:perfil-agora" for s, _ in mundo.logs)


def test_envio_que_falha_nao_marca_e_tenta_de_novo(mundo):
    mundo.conta("fulano@exemplo.test", minutos=10)
    mundo.smtp_ok = False
    _rodar()
    assert mundo.marcas == [], "marcou um aviso que não saiu — perdido pra sempre"
    mundo.smtp_ok = True
    _rodar()
    assert mundo.assuntos() == ["Cadastro incompleto — fulano@exemplo.test"]


def test_marca_que_nao_grava_deixa_rastro_e_nao_repete_de_5_em_5_min(mundo):
    mundo.conta("fulano@exemplo.test", minutos=10)
    mundo.st_grava = 500
    _rodar()
    assert len(mundo.enviados) == 1
    assert any(s == "alerta-cadastro:marca-nao-gravou" for s, _ in mundo.logs)
    assert not any("fulano@exemplo.test" in m for _, m in mundo.logs), "e-mail de cliente no error_log"
    _rodar()
    _rodar()
    assert len(mundo.enviados) == 1, "sem a memória do processo, repetiria a cada rodada"


def test_marca_que_nao_grava_ainda_permite_o_2o_aviso_no_mesmo_processo(mundo):
    uid = mundo.conta("fulano@exemplo.test", minutos=10)
    mundo.st_grava = 500
    _rodar()
    mundo.perfil(uid, "fulano@exemplo.test", minutos=0.1)
    _rodar()
    assert mundo.assuntos()[-1] == "Completou o cadastro — fulano@exemplo.test"


def test_marca_de_OUTRO_destinatario_nao_cala_o_aviso(mundo):
    """O filtro é por e-mail do destinatário: um lembrete ao CLIENTE com o
    mesmo kind/ref não pode ser lido como 'o Pedro já sabe'."""
    mundo.conta("fulano@exemplo.test", minutos=10)
    mundo.marca("alerta_novo_cadastro", "fulano@exemplo.test", email="fulano@exemplo.test")
    _rodar()
    assert len(mundo.enviados) == 1


def test_uma_rodada_por_vez(mundo):
    mundo.conta("fulano@exemplo.test", minutos=10)
    assert main._ALERTA_CADASTRO_TRAVA.acquire(blocking=False)
    try:
        assert _rodar() == {"status": "ocupado"}
        assert mundo.enviados == []
    finally:
        main._ALERTA_CADASTRO_TRAVA.release()
    _rodar()
    assert len(mundo.enviados) == 1, "a trava não foi devolvida"


def test_nome_vai_escapado(mundo):
    mundo.conta("fulano@exemplo.test", minutos=10, nome="<img src=x onerror=alert(1)>")
    _rodar()
    assert "<img" not in mundo.enviados[0][1] and "&lt;img" in mundo.enviados[0][1]


def test_dry_nao_manda_nao_grava_e_nao_devolve_email(mundo):
    uid = mundo.conta("fulano@exemplo.test", minutos=10)
    mundo.conta("beltrano@exemplo.test", minutos=10)
    mundo.marca("alerta_novo_cadastro", "fulano@exemplo.test")
    mundo.marca("alerta_cadastro_parou", "fulano@exemplo.test")
    mundo.perfil(uid, "fulano@exemplo.test", minutos=1)
    antes = list(mundo.marcas)
    r = _rodar(dry=True)
    assert r == {"status": "dry", "completaram_depois": 1, "contas_novas_sem_aviso": 1}, r
    assert mundo.enviados == [] and mundo.marcas == antes
    assert "@" not in repr(r)


# ══════════════════════════════════════════════════════════════════════════
#  5 · a rota e o dono único
# ══════════════════════════════════════════════════════════════════════════
class _Req:
    def __init__(self, headers=None):
        self.headers = headers or {}


def test_a_rota_exige_o_segredo_do_cron(mundo, monkeypatch):
    monkeypatch.setattr(main, "TICK_SECRET", "s3gredo")
    mundo.conta("fulano@exemplo.test", minutos=10)
    with pytest.raises(HTTPException) as e:
        main.cadastro_alerta_tick(_Req())
    assert e.value.status_code == 401
    assert mundo.enviados == []
    r = main.cadastro_alerta_tick(_Req({"X-Tick-Secret": "s3gredo"}))
    assert r["status"] == "ok" and len(mundo.enviados) == 1


def test_a_rota_respeita_o_desligamento_geral(mundo, monkeypatch):
    monkeypatch.setattr(main, "TICK_SECRET", "")
    monkeypatch.setenv("EMAILS_AUTO", "0")
    mundo.conta("fulano@exemplo.test", minutos=10)
    assert main.cadastro_alerta_tick(_Req()) == {"status": "off"}
    assert mundo.enviados == []


def test_a_rota_nao_e_async(mundo):
    """Corpo bloqueante em `async def` congela o servidor (28/08)."""
    import inspect
    assert not inspect.iscoroutinefunction(main.cadastro_alerta_tick)


def test_o_tick_HORARIO_so_passa_pela_MESMA_funcao(mundo, monkeypatch):
    """O tick horário é REDE DE SEGURANÇA do cron de 5 min (revisão de 21/09):
    chama `_alertas_de_cadastro_ao_pedro` — mesma trava, mesmas marcas. Não
    pode ter caminho próprio: o bloco antigo mandava "Cadastro novo" por conta
    e disputaria o aviso. Executa o tick de verdade."""
    monkeypatch.setattr(main, "TICK_SECRET", "")
    monkeypatch.setenv("EMAILS_AUTO", "1")
    monkeypatch.setattr(main, "_email_auto_ja_enviado", lambda *a, **k: False)
    monkeypatch.setattr(main, "_email_auto_recente", lambda *a, **k: False)
    monkeypatch.setattr(main, "_email_auto_registrar", lambda *a, **k: None)
    mundo.conta("fulano@exemplo.test", minutos=40)

    def _tudo(path, params=None, **k):
        if path in ("email_sent_log", "projects"):
            return (200, [])
        return mundo.tudo(path, params, **k)

    def _rest(metodo, path, *a, **k):
        if path.startswith("/email_auto_log") or path.strip("/") == "profiles":
            return mundo.rest(metodo, path, *a, **k)
        return (503, None)

    monkeypatch.setattr(main, "_supa_rest_tudo", _tudo)
    monkeypatch.setattr(main, "_supa_rest_service", _rest)

    # 1) com a rodada do cron de 5 min em curso, o tick horário não manda nada
    assert main._ALERTA_CADASTRO_TRAVA.acquire(blocking=False)
    try:
        r = main.emails_auto_tick(_Req(), dry=0)
    finally:
        main._ALERTA_CADASTRO_TRAVA.release()
    assert r.get("status") == "ok", r
    assert r["alertas_cadastro"] == {"status": "ocupado"}
    assert not any("adastro" in a for a in mundo.assuntos()), mundo.assuntos()

    # 2) livre, manda UM — pela função nova (o assunto novo prova o caminho)
    r = main.emails_auto_tick(_Req(), dry=0)
    assert mundo.assuntos() == ["Cadastro incompleto — fulano@exemplo.test"], mundo.assuntos()

    # 3) o cron de 5 min logo depois não repete
    main._alertas_de_cadastro_ao_pedro()
    assert len(mundo.enviados) == 1


def test_o_tick_HORARIO_em_ensaio_nao_manda_nem_grava(mundo, monkeypatch):
    monkeypatch.setattr(main, "TICK_SECRET", "")
    monkeypatch.setenv("EMAILS_AUTO", "1")
    monkeypatch.setattr(main, "_email_auto_ja_enviado", lambda *a, **k: False)
    monkeypatch.setattr(main, "_email_auto_recente", lambda *a, **k: False)
    mundo.conta("fulano@exemplo.test", minutos=40)
    monkeypatch.setattr(main, "_supa_rest_tudo",
                        lambda path, params=None, **k: (200, []) if path in ("email_sent_log", "projects")
                        else mundo.tudo(path, params, **k))
    r = main.emails_auto_tick(_Req(), dry=1)
    assert r["alertas_cadastro"]["status"] == "dry", r
    assert mundo.enviados == [] and mundo.marcas == []
    assert "@" not in repr(r["alertas_cadastro"])


# ══════════════════════════════════════════════════════════════════════════
#  6 · a memória do processo é FILA: marca que falhou é regravada
# ══════════════════════════════════════════════════════════════════════════
def test_marca_que_falhou_UMA_vez_e_regravada_na_rodada_seguinte(mundo):
    """🩸 revisão de 21/09: um soluço do banco logo depois do SMTP deixava a
    marca de fora pra sempre; no próximo reinício o aviso repetia."""
    mundo.conta("fulano@exemplo.test", minutos=10)
    mundo.falha_uma_vez = {"alerta_novo_cadastro", "alerta_cadastro_parou"}
    _rodar()
    assert len(mundo.enviados) == 1 and mundo.marcas == []
    _rodar()                                          # banco voltou
    assert mundo.marcas_de("alerta_novo_cadastro") == ["fulano@exemplo.test"]
    assert mundo.marcas_de("alerta_cadastro_parou") == ["fulano@exemplo.test"]
    main._ALERTA_CADASTRO_SAIU_AQUI.clear()           # reiniciou
    _rodar()
    assert len(mundo.enviados) == 1, "repetiu depois do reinício"


def test_so_a_marca_PAROU_falha_reinicia_e_o_completou_ainda_sai(mundo):
    uid = mundo.conta("fulano@exemplo.test", minutos=10)
    mundo.falha_uma_vez = {"alerta_cadastro_parou"}
    _rodar()
    _rodar()                                          # regrava a pendência
    main._ALERTA_CADASTRO_SAIU_AQUI.clear()           # reiniciou
    mundo.perfil(uid, "fulano@exemplo.test", minutos=0.2)
    _rodar()
    assert mundo.assuntos()[-1] == "Completou o cadastro — fulano@exemplo.test", (
        "o e-mail prometeu 'chega outro aviso' e ele não chegou")


def test_ensaio_nao_regrava_pendencia(mundo):
    mundo.conta("fulano@exemplo.test", minutos=10)
    mundo.falha_uma_vez = {"alerta_novo_cadastro", "alerta_cadastro_parou"}
    _rodar()
    assert mundo.marcas == []
    _rodar(dry=True)
    assert mundo.marcas == [], "o ensaio gravou no banco"
