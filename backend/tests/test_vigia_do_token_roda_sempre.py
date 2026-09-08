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
@pytest.fixture
def tick_hermetico(monkeypatch):
    """O tick, SEM tocar rede e SEM depender do meu `.env`.

    🪤 08/09 — A 1ª VERSÃO DESTE TESTE PASSOU NA MINHA MÁQUINA E DEIXOU O CI
    VERMELHO, por dois erros meus:
      1. eu fingia `iw.api`, mas o tick cria o SEU: `api = MetaGraphAPI()`
         dentro da função. O fingimento não servia pra nada;
      2. sem `META_ACCESS_TOKEN` o tick sai em "token não configurado" — e o
         `backend/.env` da minha máquina TEM a variável, o CI não. Passei
         medindo com ferramenta que o outro lado não tem (mesma família do
         incidente do dukpy, 07/09).
    🚨 E o pior: `pending` sai de `_supa_select`, que é leitura REAL do
    Supabase. A bancada estava tocando produção — já custou caro antes.
    """
    def montar(token="tok", pendentes=None):
        chamou = {"vigia": 0}
        monkeypatch.setattr(iw, "_vigia_do_token",
                            lambda: chamou.__setitem__("vigia", chamou["vigia"] + 1))

        class _Api:
            access_token = token
            ig_user_id = "123" if token else ""

        monkeypatch.setattr(iw, "MetaGraphAPI", lambda *a, **k: _Api())
        # 🔒 nada de rede: se o teste chamar o Supabase, é defeito do teste
        monkeypatch.setattr(iw, "_supa_select",
                            lambda *a, **k: list(pendentes or []))
        monkeypatch.delenv("TICK_SECRET", raising=False)
        req = type("R", (), {"headers": {}})()
        return chamou, iw.scheduler_tick(req)
    return montar


def test_o_vigia_roda_no_tick_que_NAO_publica_nada(tick_hermetico):
    """🩸 O caminho de 95 das 96 chamadas do dia."""
    chamou, r = tick_hermetico(pendentes=[])
    assert chamou["vigia"] == 1, (
        "🚨 o tick saiu sem publicar nada e NÃO passou pelo vigia (saída: %r)" % (r,))


def test_o_vigia_roda_ATE_com_o_token_nao_configurado(tick_hermetico):
    """🚨 A saída que derrubou o CI — e o estado em que o aviso MAIS importa.

    Sem `META_ACCESS_TOKEN` o tick sai antes de tudo. Se o vigia estiver depois
    dessa saída, ele nunca roda justamente quando a credencial está faltando.
    """
    chamou, r = tick_hermetico(token="")
    assert chamou["vigia"] == 1, (
        "o tick saiu por falta de token e não passou pelo vigia (saída: %r)" % (r,))


def test_CONTROLE_a_ordem_no_fonte_poe_o_vigia_antes_de_TODA_saida():
    """Controle de posição: o vigia tem que vir antes do PRIMEIRO `return` da
    função, não só antes de um deles. A 1ª versão comparava com uma saída só
    e por isso não pegou a outra."""
    import io
    import re
    fonte = io.open(os.path.join(_BACKEND, "instagram_webhook.py"),
                    encoding="utf-8").read()
    i_def = fonte.index("def scheduler_tick(")
    corpo = fonte[i_def:]
    i_vigia = corpo.index("    _vigia_do_token()")
    m = re.search(r"\n {4,}return ", corpo)
    assert m, "não achei retorno nenhum em scheduler_tick"
    assert i_vigia < m.start(), (
        "o vigia está DEPOIS do primeiro retorno da função — em produção ele "
        "só rodaria em parte das chamadas, que é o defeito de 08/09")
