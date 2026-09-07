# -*- coding: utf-8 -*-
"""Recado digitado por cliente toca campainha e aparece nos dois painéis.

🩸 06/09/2026 — o achado mais humano da auditoria total. Em 02/09 às 16h30 um
cliente escreveu na tela de revisão (job 17d6e1f2):

    "faça a separação dos tipo, cada um para cada item"

Foi o ÚNICO recado digitado por uma pessoa em toda a história do produto. Ficou
QUATRO DIAS sem resposta. E dois minutos ANTES ele tinha dado nota 7 — essa o
dono recebeu, porque nota tem alerta desde 16/08. O sinal mais caro do produto
era o único sem campainha.

E o recado valia mais que a nota: ele respondia a uma instrução do NOSSO motor,
que mediu 760,6 m de tubulação, escreveu na descrição "subdividir por diâmetro
na revisão" e deixou 5 linhas zeradas pro cliente preencher. Ele devolveu a
tarefa que a gente empurrou — com razão, porque 760 m de tubo sem diâmetro não
se orça.

🔑 POR QUE ANCORAR NO FATO, NÃO EM `action`. O modal "Comentar" grava
`action='approve'`, e os dois painéis onde o dono lê revisão filtram por ação:
um pega `edit`, o outro separa approve/edit/reject/faltou e joga aprovação num
contador. O recado caía exatamente no vão. Consertar mudando o front pra uma
ação nova só salvaria o FUTURO — o recado que já está gravado continuaria
invisível, e o dedupe e o append de 09/08 (que existem por causa do 'approve')
quebrariam junto.

🪤 E não basta "tem texto": 6 dos 7 registros com `comment` são a frase que a
NOSSA tela manda junto do atalho de marcar item como existente. Campainha que
toca nessas é campainha que o dono desliga na primeira semana.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main  # noqa: E402

#: O texto real, como está no banco. É o caso que criou este arquivo.
RECADO_REAL = "faça a separação dos tipo, cada um para cada item"
#: O que a nossa própria tela escreve (revisao.html, atalho de item existente).
AUTOMATICO = "Usuário marcou como EXISTENTE"


# ─────────────────────────────────────────────────────────────────────────────
#  Separar o que a GENTE escreveu do que o CLIENTE escreveu
# ─────────────────────────────────────────────────────────────────────────────

def test_o_recado_de_verdade_atravessa():
    assert main.recado_digitado(RECADO_REAL) == RECADO_REAL


@pytest.mark.parametrize("nada", ["", "   ", None, "\n\n"])
def test_sem_texto_nao_ha_recado(nada):
    assert main.recado_digitado(nada) == ""


def test_CONTROLE_a_frase_da_NOSSA_tela_NAO_conta():
    """🪤 O controle mais importante do arquivo. 6 dos 7 registros com texto no
    banco são esta frase. Se ela passar, a campainha toca em quase tudo e o
    dono desliga — e aí o próximo recado de gente se perde de novo."""
    assert main.recado_digitado(AUTOMATICO) == ""
    assert main.recado_digitado("  " + AUTOMATICO + "  ") == ""
    assert main.recado_digitado(AUTOMATICO.lower()) == ""


def test_o_append_de_09_08_nao_esconde_o_recado():
    """O append junta dois comentários no mesmo registro com um separador. Se a
    pessoa marcou "existente" e DEPOIS escreveu, o texto dela tem que sair —
    senão o automático engole o recado por estar na frente."""
    junto = AUTOMATICO + "\n---\n" + RECADO_REAL
    assert main.recado_digitado(junto) == RECADO_REAL
    # e na ordem inversa
    assert main.recado_digitado(RECADO_REAL + "\n---\n" + AUTOMATICO) == RECADO_REAL


def test_dois_recados_de_gente_sobrevivem_aos_dois():
    junto = "primeiro recado" + "\n---\n" + AUTOMATICO + "\n---\n" + "segundo recado"
    assert main.recado_digitado(junto) == "primeiro recado\n---\nsegundo recado"


# ─────────────────────────────────────────────────────────────────────────────
#  A campainha
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def campainha(monkeypatch):
    """Captura o alerta sem deixar sair e-mail nem thread solta."""
    tocou = []
    monkeypatch.setattr(main, "_alerta_recado",
                        lambda *a, **k: tocou.append(a))
    return tocou


def _payload(comment, action="approve"):
    return main.ReviewPayload(action=action, comment=comment, reviewed_by="x@y.com")


class _ThreadImediata:
    """Roda o alvo na hora, no lugar da thread.

    🪤 A 1ª versão deste truque usava `type("T", (), {"start": target})` — em
    Python isso vira MÉTODO da classe, então `start()` recebia `self` e
    estourava. Classe de verdade, `start` chamando o alvo sem argumento.
    """

    def __init__(self, target=None, **kw):
        self._alvo = target

    def start(self):
        if self._alvo:
            self._alvo()


def _sem_banco(monkeypatch, insert_ok=True, svc=None):
    monkeypatch.setattr(main, "_supa_rest_service",
                        svc or (lambda m, p, b=None, **k: (200, [])))
    monkeypatch.setattr(main, "_supabase_insert", lambda t, r: insert_ok)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_log", lambda *a, **k: None)
    monkeypatch.setattr(main, "_get_user_from_request",
                        lambda r: {"id": "u1", "email": "x@y.com"})
    # 🪤 Regra dura nº2 (isolamento): a rota exige dono do projeto ANTES de
    # qualquer coisa. Sem isto o teste morre no 401 e nunca chega na campainha.
    monkeypatch.setattr(main, "_require_project_owner", lambda r, j: None)
    return type("R", (), {"headers": {}})()


@pytest.fixture
def rota(monkeypatch):
    """A rota inteira, com o banco de mentira: nada de rede."""
    return _sem_banco(monkeypatch)


def test_a_campainha_TOCA_quando_o_cliente_digita(rota, campainha, monkeypatch):
    """O invariante central: texto de gente → alerta, na hora."""
    main.submit_item_review("17d6e1f2", "item-1", _payload(RECADO_REAL), rota)
    assert len(campainha) == 1, "o recado do cliente não tocou campainha nenhuma"
    _job, _item, _texto, _quem = campainha[0]
    assert _texto == RECADO_REAL
    assert _job == "17d6e1f2"


def test_CONTROLE_a_campainha_NAO_toca_no_texto_automatico(rota, campainha):
    """O outro lado: a frase da nossa tela não pode acordar ninguém."""
    main.submit_item_review("j1", "item-1", _payload(AUTOMATICO, action="edit"), rota)
    assert not campainha, (
        "a campainha tocou na frase que a NOSSA tela escreve — em 2 dias o dono "
        "desliga o alerta e o próximo recado de gente se perde")


def test_CONTROLE_a_campainha_NAO_toca_sem_comentario(rota, campainha):
    main.submit_item_review("j1", "item-1", _payload(""), rota)
    assert not campainha


def test_a_campainha_NAO_toca_se_a_escrita_falhou(monkeypatch, campainha):
    """🪤 Avisar sobre recado que não gravou manda o dono procurar no painel uma
    coisa que não está lá — pior que não avisar."""
    req = _sem_banco(monkeypatch, insert_ok=False)   # a escrita RECUSOU
    # A rota devolve 502 nesse caso (comportamento de 24/08: "a escrita PEGOU?").
    # O que este guarda cobra é que a campainha NÃO toque no caminho do erro.
    with pytest.raises(main.HTTPException) as ex:
        main.submit_item_review("j1", "item-1", _payload(RECADO_REAL), req)
    assert ex.value.status_code == 502
    assert not campainha, "avisou sobre um recado que o banco recusou"


def test_a_campainha_toca_TAMBEM_no_caminho_do_append(monkeypatch, campainha):
    """🪤 O append de 09/08 é o caminho de quem JÁ tinha aprovado o item e
    depois escreveu. Se a campainha só cobrisse o insert, esse cliente — o mais
    engajado, que voltou pra falar — seria justamente o que não avisa."""
    def _svc(m, p, b=None, **k):
        if m == "GET" and "item_reviews" in p:
            return (200, [{"id": "rev-1", "comment": ""}])   # já existe
        return (204, None)
    req = _sem_banco(monkeypatch, svc=_svc)
    main.submit_item_review("j1", "item-1", _payload(RECADO_REAL), req)
    assert len(campainha) == 1, "o caminho do append não toca campainha"


# ─────────────────────────────────────────────────────────────────────────────
#  O alerta não vaza dado nem marcação
# ─────────────────────────────────────────────────────────────────────────────

def test_o_alerta_ESCAPA_o_texto_do_cliente(monkeypatch):
    """🚨 O texto é digitado pelo cliente e vai pro corpo de um e-mail HTML que
    o dono abre. Mesma classe do XSS do painel admin (consertado em ce7846a)."""
    corpos = []
    monkeypatch.setattr(main, "_notify_admin",
                        lambda a, b: corpos.append((a, b)) or True)
    monkeypatch.setattr(main, "_supa_rows", lambda *a, **k: [])
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    import threading
    monkeypatch.setattr(threading, "Thread", _ThreadImediata)
    main._alerta_recado("j1", "i1", '<img src=x onerror="alert(1)">', "a@b.com")
    assert corpos, "o alerta não chegou a montar e-mail"
    _assunto, corpo = corpos[0]
    assert "<img src=x" not in corpo, "marcação do cliente entrou CRUA no e-mail do dono"
    assert "&lt;img" in corpo


def test_o_log_do_alerta_NAO_leva_email_de_cliente(monkeypatch):
    """🔒 LGPD. Em 06/09 achei 19 linhas de error_log com endereço de cliente
    dentro. O aviso precisa do e-mail (o dono responde a alguém); o LOG não —
    ele leva o job_id, que já é opaco."""
    logs = []
    monkeypatch.setattr(main, "_notify_admin", lambda a, b: True)
    monkeypatch.setattr(main, "_supa_rows", lambda *a, **k: [])
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, job=None, **k: logs.append((stage, msg)))
    import threading
    monkeypatch.setattr(threading, "Thread", _ThreadImediata)
    main._alerta_recado("j1", "i1", "texto qualquer", "cliente-nn@example.com")
    assert logs, "o alerta não deixou rastro nenhum"
    _stage, msg = logs[0]
    assert "cliente-nn@example.com" not in msg, (
        "o e-mail do cliente foi parar no error_log — regra dura nº6")


# ─────────────────────────────────────────────────────────────────────────────
#  Os dois painéis onde o dono lê revisão
# ─────────────────────────────────────────────────────────────────────────────

def test_a_voz_do_cliente_tem_secao_de_RECADO(monkeypatch):
    """Guarda de comportamento: a rota tem que DEVOLVER o recado — e o caso que
    ela precisa enxergar é o real, com action='approve'."""
    linha = {"item_id": "i1", "job_id": "17d6e1f2", "action": "approve",
             "comment": RECADO_REAL, "reviewed_at": "2026-09-02T19:30:00Z"}

    def _svc(m, p, b=None, **k):
        if "item_reviews" in p and "comment=not.is.null" in p:
            return (200, [linha, {"item_id": "i2", "job_id": "j2",
                                  "action": "edit", "comment": AUTOMATICO,
                                  "reviewed_at": "2026-08-30T14:14:00Z"}])
        return (200, [])
    monkeypatch.setattr(main, "_supa_rest_service", _svc)
    monkeypatch.setattr(main, "_require_admin", lambda r: {"email": main.ADMIN_EMAIL})
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    out = main.admin_voz_do_cliente(type("R", (), {"headers": {}})())
    assert "recados" in out, "a seção de recado não existe na voz-do-cliente"
    assert len(out["recados"]) == 1, (
        "esperava 1 recado de gente e 1 automático descartado; veio %d"
        % len(out["recados"]))
    assert out["recados"][0]["recado"] == RECADO_REAL


def test_a_consulta_dos_recados_NAO_filtra_por_acao(monkeypatch):
    """🔑 O invariante do conserto. Se voltar a filtrar por ação, o recado real
    (gravado como 'approve') desaparece de novo — foi assim que ele ficou 4
    dias invisível. Este guarda olha a CONSULTA que a rota manda."""
    vistas = []

    def _svc(m, p, b=None, **k):
        vistas.append(p)
        return (200, [])
    monkeypatch.setattr(main, "_supa_rest_service", _svc)
    monkeypatch.setattr(main, "_require_admin", lambda r: {"email": main.ADMIN_EMAIL})
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    main.admin_voz_do_cliente(type("R", (), {"headers": {}})())
    q = [p for p in vistas if "comment=not.is.null" in p]
    assert q, "a rota não consulta por comentário — voltou a depender da ação"
    assert "action=eq." not in q[0], (
        "a consulta de recado voltou a filtrar por ação: o recado gravado como "
        "aprovação some outra vez")


def test_o_resumo_do_admin_conta_recado_de_qualquer_acao(monkeypatch):
    """O outro painel. Ele separa por ação e aprovação vira só um número — era
    o segundo lugar onde o recado sumia."""
    import inspect
    fonte = inspect.getsource(main)
    i = fonte.index('resumo["revisao_inline"] = {')
    bloco = fonte[i:i + 1400]
    assert '"recados"' in bloco, "o resumo não conta recado digitado"
    assert '"recados_itens"' in bloco, (
        "o resumo conta o recado mas não mostra o TEXTO — número sozinho não "
        "diz o que responder")


def test_a_TELA_do_admin_mostra_o_recado():
    """🪤 Arquivo certo ≠ tela certa. Em 05/09 o botão 'faltou um item' subiu e
    o painel não lia — conserto pela metade. Aqui a tela precisa desenhar as
    duas fontes: a faixa da voz-do-cliente e o bloco do resumo."""
    import io
    admin = io.open(os.path.join(os.path.dirname(_BACKEND), "admin.html"),
                    encoding="utf-8").read()
    assert "d.recados" in admin, "a voz-do-cliente não lê recados na tela"
    assert "ri.recados" in admin, "o resumo não desenha recados na tela"
    assert "recadosHtml" in admin and "recadosHtml + faltouHtml" in admin, (
        "o bloco de recado existe mas não foi ligado no HTML final — código "
        "morto, que é exatamente o defeito de 05/09")
