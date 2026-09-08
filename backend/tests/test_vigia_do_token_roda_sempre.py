# -*- coding: utf-8 -*-
"""O aviso de vencimento do token roda em TODO tick, não só quando publica.

🩸 08/09/2026 — ELE NUNCA IA DISPARAR, E ISSO TINHA DATA.

O vigia existe desde 16/08 porque em 08/08 o token venceu, **ninguém soube**, e
5 posts falharam calados por uma semana na conta que mais traz cadastro. Ele
avisa a partir do dia 53 (D-7 dos 60 dias) e repete no máximo 1×/semana.

Só que ele morava DEPOIS do laço de publicação do tick — e o tick tem um
retorno antecipado:

    if not pending:
        return {"ok": True, "message": "Nada pra publicar agora"}

O pg_cron chama o tick a cada 15 min: **96×/dia**. Publica no máximo 1. Nas
outras 95 vezes a função saía ali e o vigia nunca era alcançado.

E as datas, medidas no banco em 08/09, fecham contra ele:

    último post agendado ......... 03/10
    aviso começaria (dia 53) ..... 08/10
    token morre .................. 15/10
    posts na janela do aviso ..... 0

Entre o dia em que o aviso começaria e o dia em que o token morre **não há
nenhum post agendado**. Nenhum tick chegaria ao vigia. O token morreria calado
pela segunda vez, e a segunda seria pior: a primeira ensinou a construir o
aviso, e ele estava lá, escrito, sem nunca poder rodar.

🔑 Agora o vigia roda ANTES do retorno antecipado. O freio de 1×/semana já
existia e continua sendo o que evita a enxurrada de 96 avisos por dia.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import instagram_webhook as iw  # noqa: E402


def _iso(dias_atras):
    return (datetime.now(timezone.utc) - timedelta(days=dias_atras)).isoformat()


@pytest.fixture
def vigia(monkeypatch):
    """Monta o cenário e devolve o que o vigia FEZ."""
    def montar(idade_token, dias_do_ultimo_aviso=None):
        feito = {"logs": [], "emails": []}

        def _select(tabela, query):
            if "token-renovado" in query:
                return [{"created_at": _iso(idade_token)}]
            if "token-aviso" in query:
                return ([{"created_at": _iso(dias_do_ultimo_aviso)}]
                        if dias_do_ultimo_aviso is not None else [])
            return []

        monkeypatch.setattr(iw, "_supa_select", _select)
        import main
        monkeypatch.setattr(main, "_log_error",
                            lambda stage, msg, *a, **k: feito["logs"].append((stage, msg)))
        monkeypatch.setattr(main, "_notify_admin",
                            lambda assunto, corpo: feito["emails"].append(assunto))
        return feito
    return montar


# ══════════════════════════════════════════════════════════════════════════
#  1 · o vigia avisa na hora certa
# ══════════════════════════════════════════════════════════════════════════
def test_no_dia_53_avisa(vigia):
    feito = vigia(53)
    iw._vigia_do_token()
    assert feito["logs"], "chegou o dia 53 e o vigia não avisou"
    assert feito["emails"], "logou mas não mandou e-mail pro Pedro"
    assert "instagram:token-aviso" == feito["logs"][0][0]


def test_antes_do_dia_53_fica_quieto(vigia):
    feito = vigia(52)
    iw._vigia_do_token()
    assert not feito["logs"] and not feito["emails"], (
        "avisou cedo demais — aviso que chega toda semana vira ruído e o Pedro "
        "para de ler")


def test_repete_no_maximo_uma_vez_por_semana(vigia):
    """96 ticks por dia × 7 dias = 672 chances. O freio é o que separa um aviso
    útil de uma enxurrada."""
    feito = vigia(55, dias_do_ultimo_aviso=2)
    iw._vigia_do_token()
    assert not feito["emails"], "mandou 2 e-mails na mesma semana"
    feito2 = vigia(55, dias_do_ultimo_aviso=7)
    iw._vigia_do_token()
    assert feito2["emails"], "passou uma semana e não repetiu o aviso"


def test_sem_ancora_de_renovacao_nao_chuta(vigia, monkeypatch):
    """Sem a linha `token-renovado` não dá pra saber a idade. Chutar aqui vira
    e-mail toda hora — ou, pior, silêncio com cara de 'está tudo bem'."""
    monkeypatch.setattr(iw, "_supa_select", lambda t, q: [])
    import main
    logs = []
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: logs.append(a))
    iw._vigia_do_token()
    assert not logs


def test_falha_de_leitura_nao_derruba_o_tick(monkeypatch):
    """🚨 O vigia é acessório: o tick publica posts. Se o vigia levantar, o
    Instagram para de publicar — o remédio matando o paciente."""
    monkeypatch.setattr(iw, "_supa_select",
                        lambda t, q: (_ for _ in ()).throw(OSError("banco fora")))
    iw._vigia_do_token()   # não pode levantar


# ══════════════════════════════════════════════════════════════════════════
#  2 · 🚨 o invariante: roda MESMO SEM POST PRA PUBLICAR
# ══════════════════════════════════════════════════════════════════════════
def test_o_vigia_roda_no_tick_que_NAO_publica_nada(monkeypatch):
    """🩸 O defeito de 08/09, no fato.

    O tick sai cedo quando não há post pendente — 95 das 96 chamadas do dia. O
    vigia ficava depois desse retorno. Aqui a gente roda o tick SEM nada
    pendente e exige que ele tenha passado pelo vigia.
    """
    chamou = {"vigia": 0}
    monkeypatch.setattr(iw, "_vigia_do_token",
                        lambda: chamou.__setitem__("vigia", chamou["vigia"] + 1))

    class _Api:
        access_token = "tok"
        ig_user_id = "123"

    monkeypatch.setattr(iw, "api", _Api(), raising=False)
    monkeypatch.setattr(iw, "_posts_pendentes", lambda *a, **k: [], raising=False)
    monkeypatch.setattr(iw, "TICK_SECRET", "", raising=False)

    req = type("R", (), {"headers": {}})()
    try:
        r = iw.scheduler_tick(req)
    except TypeError:
        r = iw.scheduler_tick(req, None)
    assert chamou["vigia"] == 1, (
        "🚨 o tick saiu sem publicar nada e NÃO passou pelo vigia — é o "
        "caminho de 95 das 96 chamadas do dia (saída: %r)" % (r,))


def test_CONTROLE_a_ordem_no_fonte_poe_o_vigia_antes_da_saida(monkeypatch):
    """Controle de posição: se alguém mover o vigia de volta pra depois do
    retorno antecipado, isto reprova mesmo que o teste acima seja driblado."""
    import io
    fonte = io.open(os.path.join(_BACKEND, "instagram_webhook.py"),
                    encoding="utf-8").read()
    i_vigia = fonte.index("    _vigia_do_token()")
    i_saida = fonte.index("    if not pending:")
    assert i_vigia < i_saida, (
        "o vigia voltou pra depois do retorno antecipado — ele só rodaria em "
        "tick que publica post, e não há post entre 08/10 e 15/10")
