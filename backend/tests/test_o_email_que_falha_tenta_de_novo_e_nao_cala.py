# -*- coding: utf-8 -*-
"""E-mail que falha tenta de novo — e nunca mais cala (22/09/2026).

🩸 O CASO. Job `1d0751b8` (cliente NOVO, caderno de 35 páginas, 537 itens). O
motor gravou `motor:leu-sem-medir` às 15:39:04 e chamou o envio; às 15:39:29 o
log do Render mostrou

    [email] FALHA -> …: SMTPServerDisconnected: Connection unexpectedly
    closed: The read operation timed out

A sessão SMTP caiu no meio. O cliente ficou sem o aviso da planilha e NINGUÉM
soube: `email_sent_log` só recebe linha quando dá CERTO, e a falha virava
`print()`, que o log do Render descarta em dias. Não era tamanho nem
configuração — o boas-vindas do mesmo cliente saiu 1 h antes pela mesma porta.

O conserto tem duas metades, e as duas estão guardadas aqui:
  (1) falha PASSAGEIRA é retentada (poucas vezes, espera crescente, com teto
      de tempo pra não segurar o job); falha PERMANENTE não é — retentar
      endereço inválido, 5xx ou defeito nosso é repetir o mesmo erro;
  (2) a falha deixa rastro: linha `email:falha` no `error_log` (🔒 SEM o
      endereço — regra dura nº6) e campainha pro Pedro quando quem ficou sem
      o e-mail foi um CLIENTE (aí o aviso leva o contato: é ele quem lê).

🚨 Estes guardas EXECUTAM `_send_email_smtp` de verdade; o que é dublado é o
servidor SMTP, e todo dublê aceita `**k` — dublê de assinatura exata desarma
calado quando a função real ganha parâmetro novo (16 e 18/09).

🧪 Controles positivos: o erro permanente NÃO é retentado; o detector de
e-mail ACHA o endereço no texto cru da exceção (senão "não vazou" passaria por
mérito falso); o alerta ao Pedro CONTINUA levando o contato; falha de e-mail
interno não toca a campainha.
"""
import os
import re
import smtplib
import sys
import threading

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main  # noqa: E402

#: mesmo padrão do guarda do log de NPS — o guarda mede o que a auditoria mede
_RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_CLIENTE = "cliente-nn@example.com"
_JOB = "1d0751b8"

#: a exceção EXATA do log do Render em 22/09 15:39:29
_QUEDA = "Connection unexpectedly closed: The read operation timed out"

#: 🪤 O alerta DE VERDADE, guardado ANTES de qualquer dublê — dentro do teste,
#: `main._notify_admin` já é o dublê, e repô-lo em si mesmo não devolve nada.
_NOTIFY_REAL = main._notify_admin


def _caiu():
    return smtplib.SMTPServerDisconnected(_QUEDA)


def _recusado(codigo=550):
    return smtplib.SMTPRecipientsRefused(
        {_CLIENTE: (codigo, b"5.1.1 User unknown")})


# ── o dublê do servidor ────────────────────────────────────────────────────
class _Sessao:
    """A sessão aberta pelo `with smtplib.SMTP(...)`."""

    def __init__(self, dono, **k):
        self.dono = dono
        self.entregou = False

    def __enter__(self, *a, **k):
        return self

    def __exit__(self, *a, **k):
        # 🩸 22/09, achado A1 (2ª sonda da revisão): o `__exit__` do smtplib
        # manda QUIT, e um 4xx aí vira exceção DEPOIS de a mensagem já ter sido
        # aceita. Sem este dublê, a casa nunca testaria esse caminho.
        if self.entregou and self.dono.cai_no_fecho is not None:
            raise self.dono.cai_no_fecho
        return False

    def ehlo(self, *a, **k):
        pass

    def starttls(self, *a, **k):
        pass

    def login(self, *a, **k):
        pass

    def sendmail(self, de, para, corpo, *a, **k):
        i = self.dono.tentativas - 1
        erro = self.dono.roteiro[i] if i < len(self.dono.roteiro) else None
        if erro is not None:
            # 🔑 O dublê que FALTAVA. No guarda original todo `sendmail`
            # levantava ANTES de registrar a entrega, então a duplicata que a
            # revisão mediu não tinha como aparecer em teste nenhum: `entrega_antes`
            # é o servidor que RECEBE a mensagem e só depois some — o outro lado
            # da mesma exceção de 22/09.
            if self.dono.entrega_antes:
                self.dono.enviados.append((de, list(para), corpo))
            raise erro
        self.dono.enviados.append((de, list(para), corpo))
        self.entregou = True


class _Servidor:
    """Faz as vezes de `smtplib.SMTP`: um roteiro de exceções por tentativa
    (None = aceita a mensagem). `no_connect=True` derruba já na conexão;
    `entrega_antes=True` registra a entrega ANTES de levantar (servidor que
    recebeu e não respondeu); `cai_no_fecho=exc` derruba a sessão no QUIT,
    depois de a mensagem já ter sido aceita."""

    def __init__(self, roteiro=(), no_connect=None, entrega_antes=False,
                 cai_no_fecho=None):
        self.roteiro = list(roteiro)
        self.no_connect = no_connect
        self.entrega_antes = entrega_antes
        self.cai_no_fecho = cai_no_fecho
        self.tentativas = 0
        self.enviados = []
        self.timeouts = []              # o `timeout=` de CADA tentativa (A2)

    def __call__(self, *a, **k):
        self.tentativas += 1
        self.timeouts.append(k.get("timeout", (list(a) + [None, None, None])[2]))
        if self.no_connect is not None:
            raise self.no_connect
        return _Sessao(self)


@pytest.fixture
def bordas(monkeypatch):
    """Ambiente de envio com as bordas dubladas. Devolve (logs, avisos, esperas)."""
    monkeypatch.setenv("SMTP_HOST", "smtp.exemplo")
    monkeypatch.setenv("SMTP_USER", "remetente@exemplo")
    monkeypatch.setenv("SMTP_PASSWORD", "segredo")
    monkeypatch.setattr(main, "_email_suprimido", lambda e: None)
    monkeypatch.setattr(main, "_EMAIL_FALHA_AVISADO", set())
    monkeypatch.setattr(main, "_EMAIL_ALERTANDO", threading.local())
    # 🪤 O freio do rastro e o relógio da campainha são estado de MÓDULO: sem
    # zerar, o 4º guarda do arquivo já entra com o teto estourado pelo 1º e
    # "não gravou a linha" vira falso vermelho (aconteceu comigo hoje).
    monkeypatch.setattr(main, "_EMAIL_FALHA_LINHAS", {})
    monkeypatch.setattr(main, "_EMAIL_ALERTA_ESTADO", {"caiu_em": 0.0})

    logs, avisos, esperas, gravados = [], [], [], []

    def _log(*a, **k):
        stage = a[0] if len(a) > 0 else k.get("stage")
        msg = a[1] if len(a) > 1 else k.get("message")
        job = a[2] if len(a) > 2 else k.get("job_id")
        logs.append({"stage": str(stage), "msg": str(msg), "job": job,
                     "sev": k.get("severity")})

    def _aviso(*a, **k):
        avisos.append(" ".join(str(x) for x in list(a) + list(k.values())))
        return True

    monkeypatch.setattr(main, "_log_error", _log)
    monkeypatch.setattr(main, "_notify_admin", _aviso)
    monkeypatch.setattr(main, "_supabase_insert",
                        lambda tabela, linha, *a, **k: gravados.append((tabela, linha)) or True)
    # 🪤 `time.sleep` de verdade faria a bancada esperar 7 s por guarda — o que
    # interessa é QUANTO ele pediu pra esperar, e isso a lista registra.
    monkeypatch.setattr(main.time, "sleep", lambda s, *a, **k: esperas.append(s))
    return logs, avisos, esperas, gravados


def _linhas(logs, stage):
    return [x for x in logs if x["stage"] == stage]


def _uma(logs, stage):
    achadas = _linhas(logs, stage)
    assert len(achadas) == 1, (
        "esperava 1 linha `%s` e vieram %d — logs=%r" % (stage, len(achadas), logs))
    return achadas[0]


# ── (1) a metade da re-tentativa ───────────────────────────────────────────
def test_a_sessao_que_cai_e_retentada_e_o_email_SAI(bordas, monkeypatch):
    """O caso de 22/09, inteiro: a 1ª tentativa cai como caiu no Render, a 2ª
    passa. Antes do conserto isto devolvia False e o cliente ficava sem nada."""
    logs, _avisos, _esperas, gravados = bordas
    srv = _Servidor([_caiu(), None])
    monkeypatch.setattr(smtplib, "SMTP", srv)

    ok = main._send_email_smtp(_CLIENTE, "Sua planilha está pronta", "<b>oi</b>",
                               log_kind="leu_sem_medir", job_id=_JOB)

    assert ok is True, "a queda de sessão tem que ser retentada, não engolida"
    assert srv.tentativas == 2 and len(srv.enviados) == 1
    assert not _linhas(logs, "email:falha"), "saiu: não pode haver linha de falha"
    linha = _uma(logs, "email:retentado")
    assert "tentativa 2" in linha["msg"] and "leu_sem_medir" in linha["msg"], linha
    assert [t for t, _l in gravados] == ["email_sent_log"], (
        "o envio que deu certo na 2ª tentativa tem que entrar no registro")
    assert gravados[0][1]["job_id"] == _JOB and gravados[0][1]["kind"] == "leu_sem_medir"


def test_duas_quedas_seguidas_e_a_terceira_passa_com_espera_CRESCENTE(bordas, monkeypatch):
    logs, _a, esperas, _g = bordas
    srv = _Servidor([_caiu(), _caiu(), None])
    monkeypatch.setattr(smtplib, "SMTP", srv)

    assert main._send_email_smtp(_CLIENTE, "A", "b", log_kind="planilha_pronta",
                                 job_id=_JOB) is True
    assert srv.tentativas == 3
    assert esperas == [2.0, 5.0], "a espera entre tentativas tem que crescer: %r" % esperas
    assert "tentativa 3" in _uma(logs, "email:retentado")["msg"]


def test_a_queda_na_CONEXAO_tambem_e_retentada(bordas, monkeypatch):
    """A sessão de 22/09 caiu no meio; servidor que nem aceita conectar é o
    mesmo tipo de falha — e o envio nem chega ao `sendmail`."""
    _l, _a, _e, _g = bordas
    srv = _Servidor(no_connect=smtplib.SMTPConnectError(-1, "sem resposta"))
    monkeypatch.setattr(smtplib, "SMTP", srv)
    assert main._send_email_smtp(_CLIENTE, "A", "b", log_kind="planilha_pronta") is False
    assert srv.tentativas == main._EMAIL_TENTATIVAS


def test_CONTROLE_endereco_recusado_NAO_e_retentado(bordas, monkeypatch):
    """O outro lado da régua: 5xx é definitivo. Retentar três vezes só faria o
    cliente esperar por uma falha que já era certa."""
    logs, _a, esperas, _g = bordas
    srv = _Servidor([_recusado(550), _recusado(550), _recusado(550)])
    monkeypatch.setattr(smtplib, "SMTP", srv)

    assert main._send_email_smtp(_CLIENTE, "A", "b", log_kind="planilha_pronta",
                                 job_id=_JOB) is False
    assert srv.tentativas == 1, "endereço inválido não se resolve tentando de novo"
    assert esperas == [], "não esperou à toa"
    assert "permanente" in _uma(logs, "email:falha")["msg"]


def test_CONTROLE_defeito_NOSSO_no_meio_do_envio_nao_vira_tres_tentativas(bordas, monkeypatch):
    """Exceção de programação (a que derrubou o e-mail na bancada em 18/09)
    não é falha de rede: retentar repete o mesmo bug com o cliente esperando."""
    _l, _a, _e, _g = bordas
    srv = _Servidor([ValueError("invalid high surrogate in string")])
    monkeypatch.setattr(smtplib, "SMTP", srv)
    assert main._send_email_smtp(_CLIENTE, "A", "b", log_kind="planilha_pronta") is False
    assert srv.tentativas == 1


@pytest.mark.parametrize("erro,passageira", [
    (smtplib.SMTPServerDisconnected(_QUEDA), True),
    (smtplib.SMTPConnectError(-1, "sem resposta"), True),
    (smtplib.SMTPResponseException(451, "4.7.1 try again later"), True),
    (smtplib.SMTPRecipientsRefused({_CLIENTE: (451, b"greylisted")}), True),
    (TimeoutError("timed out"), True),
    (ConnectionResetError("[Errno 104] reset by peer"), True),
    (smtplib.SMTPResponseException(550, "5.1.1 user unknown"), False),
    (smtplib.SMTPRecipientsRefused({_CLIENTE: (550, b"user unknown")}), False),
    (smtplib.SMTPAuthenticationError(535, "5.7.8 bad credentials"), False),
    (smtplib.SMTPSenderRefused(553, "5.7.1 not allowed", "x@y.z"), False),
    (ValueError("deu ruim"), False),
])
def test_a_regua_do_passageiro_e_a_mesma_pra_todos(erro, passageira):
    assert main._falha_de_email_e_passageira(erro) is passageira, (
        "%s: %s" % (type(erro).__name__, erro))


def test_o_teto_de_tempo_impede_segurar_o_job(bordas, monkeypatch):
    """🪤 O envio acontece DENTRO do job (e dentro do laço da newsletter). Com
    um servidor que só dá timeout, três tentativas de 20 s seriam mais de um
    minuto por e-mail — por isso existe orçamento total."""
    _l, _a, esperas, _g = bordas
    monkeypatch.setattr(main, "_EMAIL_TETO_S", 0.0)
    srv = _Servidor([_caiu(), _caiu(), None])
    monkeypatch.setattr(smtplib, "SMTP", srv)
    assert main._send_email_smtp(_CLIENTE, "A", "b", log_kind="planilha_pronta") is False
    assert srv.tentativas == 1 and esperas == []


def test_o_orcamento_continua_curto():
    """Guarda de forma: alguém subir o teto pra 'garantir a entrega' devolve o
    defeito que o teto existe pra impedir."""
    assert 1 <= main._EMAIL_TENTATIVAS <= 3
    assert main._EMAIL_TETO_S <= 60.0
    assert sum(main._EMAIL_ESPERAS_S) <= 10.0


# ── (2) a metade do rastro ─────────────────────────────────────────────────
def test_a_falha_deixa_linha_no_error_log(bordas, monkeypatch):
    """O que faltava em 22/09: `email_sent_log` só grava sucesso, e a falha
    morria num `print` que o Render descarta em dias."""
    logs, _a, _e, gravados = bordas
    srv = _Servidor([_caiu(), _caiu(), _caiu()])
    monkeypatch.setattr(smtplib, "SMTP", srv)

    assert main._send_email_smtp(_CLIENTE, "Sua planilha está pronta", "<b>oi</b>",
                                 log_kind="leu_sem_medir", job_id=_JOB) is False
    linha = _uma(logs, "email:falha")
    assert "kind=leu_sem_medir" in linha["msg"], linha["msg"]
    assert "job=%s" % _JOB in linha["msg"] and linha["job"] == _JOB, linha
    assert "tentativas=3" in linha["msg"] and "passageira" in linha["msg"], linha["msg"]
    assert "SMTPServerDisconnected" in linha["msg"], (
        "sem o tipo do erro a linha não diagnostica nada: %r" % linha["msg"])
    assert linha["sev"] == "error", "falha de e-mail não é diagnóstico de rotina"
    assert not gravados, "e-mail que não saiu NÃO pode virar linha de enviado"


def test_o_stage_da_falha_aparece_no_painel():
    """🪤 `_log_error` rebaixa a 'info' quem está em `_STAGES_DIAGNOSTICO` — e
    rastro que ninguém vê é o silêncio de volta, com outro nome."""
    assert "email:falha" not in main._STAGES_DIAGNOSTICO


def test_LGPD_o_log_da_falha_NAO_leva_o_endereco(bordas, monkeypatch):
    """🔒 Regra dura nº6, e é armadilha de verdade: a recusa do servidor vem
    COM o destinatário dentro da exceção."""
    logs, _a, _e, _g = bordas
    srv = _Servidor([_recusado(550)])
    monkeypatch.setattr(smtplib, "SMTP", srv)

    main._send_email_smtp(_CLIENTE, "A", "b", log_kind="planilha_pronta", job_id=_JOB)
    msg = _uma(logs, "email:falha")["msg"]
    achado = _RE_EMAIL.search(msg)
    assert achado is None, (
        "o e-mail do cliente (%s) foi parar no error_log — mesmo defeito que o "
        "log de NPS perdeu hoje. Mensagem: %r" % (achado and achado.group(0), msg))
    assert "<e-mail omitido>" in msg, msg


def test_CONTROLE_o_endereco_ESTAVA_no_texto_cru_da_excecao():
    """Prova que o guarda acima reprova: sem isto, "não vazou" poderia ser só
    'não havia endereço nenhum pra vazar'."""
    cru = "%s: %s" % (type(_recusado()).__name__, _recusado())
    achado = _RE_EMAIL.search(cru)
    assert achado and achado.group(0) == _CLIENTE, cru
    assert _RE_EMAIL.search(main._email_sem_endereco(cru)) is None


def test_a_campainha_toca_pro_Pedro_COM_o_contato(bordas, monkeypatch):
    """O contato sai do LOG, não do AVISO — o Pedro precisa saber a quem
    reenviar."""
    _l, avisos, _e, _g = bordas
    srv = _Servidor([_caiu(), _caiu(), _caiu()])
    monkeypatch.setattr(smtplib, "SMTP", srv)

    main._send_email_smtp(_CLIENTE, "Sua planilha está pronta", "<b>oi</b>",
                          log_kind="leu_sem_medir", job_id=_JOB)
    assert len(avisos) == 1, "e-mail de CLIENTE que não sai tem que tocar campainha"
    assert _CLIENTE in avisos[0] and _JOB in avisos[0], avisos[0]
    assert "leu_sem_medir" in avisos[0], avisos[0]


@pytest.mark.parametrize("destino", ["admin", "notify"])
def test_CONTROLE_falha_de_email_INTERNO_nao_toca_a_campainha(bordas, monkeypatch, destino):
    """Avisar o Pedro de que o aviso do Pedro não chegou é ruído — e, no caso
    do próprio endereço do alerta, seria a recursão que a trava impede."""
    logs, avisos, _e, _g = bordas
    srv = _Servidor([_caiu(), _caiu(), _caiu()])
    monkeypatch.setattr(smtplib, "SMTP", srv)

    para = main.ADMIN_EMAIL if destino == "admin" else main.NOTIFY_EMAIL
    main._send_email_smtp(para, "A", "b", log_kind="email")
    assert avisos == [], "falha de e-mail interno não é campainha"
    assert _linhas(logs, "email:falha"), "mas o rastro no error_log continua"


def test_a_campainha_toca_UMA_vez_por_dia_por_tipo_e_job(bordas, monkeypatch):
    """🪤 Uma newsletter de 65 destinatários num servidor fora do ar viraria 65
    campainhas (que também falhariam)."""
    _l, avisos, _e, _g = bordas
    monkeypatch.setattr(smtplib, "SMTP", _Servidor([_caiu(), _caiu(), _caiu()] * 9))

    for _ in range(4):
        main._send_email_smtp(_CLIENTE, "A", "b", log_kind="newsletter")
    assert len(avisos) == 1, "mesmo tipo, mesmo job: uma campainha"
    main._send_email_smtp(_CLIENTE, "A", "b", log_kind="leu_sem_medir", job_id=_JOB)
    assert len(avisos) == 2, "job/tipo diferente é outro cliente sem e-mail"


def test_a_trava_de_reentrancia_segura_o_alerta(bordas):
    """A trava, medida sozinha: com ela marcada, o alerta não sai — é o que
    impede que a campainha que falha peça outra campainha."""
    _l, avisos, _e, _g = bordas
    main._EMAIL_ALERTANDO.dentro = True
    saiu = main._alerta_email_que_nao_saiu(_CLIENTE, "A", "leu_sem_medir", _JOB,
                                           "SMTPServerDisconnected", 3)
    assert saiu is False and avisos == []


def test_o_CAMINHO_COMUM_nao_deixa_rastro_nenhum(bordas, monkeypatch):
    """🧪 O controle positivo do caminho de sempre — e o que faltava (achado A5).

    Sem ele, uma mutação que gravasse `email:retentado` em TODO sucesso passava
    verde, e o instrumento que vai decidir a fila (`quantas falhas a
    re-tentativa salvou`) passaria a responder "todas". Medido: são ~364
    envios por 30 dias; o mutante daria 364 linhas de rastro falso."""
    logs, avisos, esperas, gravados = bordas
    srv = _Servidor([None])
    monkeypatch.setattr(smtplib, "SMTP", srv)

    ok = main._send_email_smtp(_CLIENTE, "Sua planilha está pronta", "<b>oi</b>",
                               log_kind="planilha_pronta", job_id=_JOB)

    assert ok is True and srv.tentativas == 1 and len(srv.enviados) == 1
    assert esperas == [] and avisos == []
    assert logs == [], "envio que deu certo de primeira não escreve no error_log: %r" % logs
    assert [t for t, _l in gravados] == ["email_sent_log"]
    assert gravados[0][1]["kind"] == "planilha_pronta" and gravados[0][1]["job_id"] == _JOB


# ── (3) achado A1: entregou, não entregou, ou não se sabe ──────────────────
def test_o_servidor_ACEITOU_e_a_sessao_caiu_no_FECHO_nao_e_retentado(bordas, monkeypatch):
    """🩸 A 2ª sonda da revisão: 4xx no QUIT levanta DEPOIS de a mensagem ter
    sido aceita, e 4xx é passageiro pela régua — então o conserto de hoje de
    manhã mandava a MESMA mensagem de novo. Duas entregas, uma linha no
    `email_sent_log`: a duplicata invisível."""
    logs, _a, _e, gravados = bordas
    srv = _Servidor([None], cai_no_fecho=smtplib.SMTPResponseException(421, "4.7.0 closing"))
    monkeypatch.setattr(smtplib, "SMTP", srv)

    ok = main._send_email_smtp(_CLIENTE, "A", "b", log_kind="planilha_pronta", job_id=_JOB)

    assert ok is True, "o servidor aceitou a mensagem: isso é entrega, não falha"
    assert srv.tentativas == 1, "retentar aqui manda a mesma mensagem duas vezes"
    assert len(srv.enviados) == 1
    assert [t for t, _l in gravados] == ["email_sent_log"]
    assert "fecho" in _uma(logs, "email:fecho-torto")["msg"]
    assert not _linhas(logs, "email:falha")


def test_a_queda_DENTRO_da_entrega_pode_duplicar_e_o_log_DIZ(bordas, monkeypatch):
    """🩸 Achado A1. A MESMA exceção de 22/09 serve pra "ele nem viu" e pra "ele
    aceitou e a resposta se perdeu" — `SMTP.data()` manda o corpo e só então lê.

    A casa escolheu proteger o CLIENTE (retentar), porque ficar sem o aviso foi
    o que custou caro. O preço é esta linha: o `email_sent_log` continua com uma
    linha só, e sem o rastro a segunda cópia seria invisível."""
    logs, _a, _e, gravados = bordas
    srv = _Servidor([_caiu(), None], entrega_antes=True)
    monkeypatch.setattr(smtplib, "SMTP", srv)

    ok = main._send_email_smtp(_CLIENTE, "Sua planilha está pronta", "<b>oi</b>",
                               log_kind="leu_sem_medir", job_id=_JOB)

    assert ok is True and srv.tentativas == 2
    assert len(srv.enviados) == 2, (
        "o servidor recebeu DUAS mensagens — é exatamente isso que o log precisa dizer")
    assert len([t for t, _l in gravados if t == "email_sent_log"]) == 1
    linha = _uma(logs, "email:pode-ter-duplicado")
    assert "duas cópias" in linha["msg"] and linha["sev"] == "error", linha
    assert "pessoa=" in linha["msg"] and _RE_EMAIL.search(linha["msg"]) is None, (
        "🔒 nem no aviso de duplicata o endereço entra no error_log: %r" % linha["msg"])


@pytest.mark.parametrize("respondeu", [
    smtplib.SMTPRecipientsRefused({_CLIENTE: (451, b"greylisted")}),
    smtplib.SMTPDataError(451, "4.3.0 try again"),
    smtplib.SMTPSenderRefused(451, "4.7.1 try again", "remetente@exemplo"),
])
def test_CONTROLE_quando_o_servidor_RESPONDE_nao_ha_duvida_nenhuma(bordas, monkeypatch,
                                                                   respondeu):
    """A régua olha a RESPOSTA, não o momento: recusa de remetente/destinatário
    acontece ANTES do corpo ir pro fio (`mail` e `rcpt` vêm antes de `data`), e
    erro no DATA é o servidor dizendo que NÃO aceitou. Nos três se sabe o
    desfecho. Sem este controle, "avisou da dúvida" passaria a valer pra toda
    falha e o aviso viraria ruído — e o mutante que faz TODA resposta virar
    dúvida passaria verde (ele passou, na 1ª rodada de sabotagem: o controle só
    cobria `SMTPRecipientsRefused`, que nem é `SMTPResponseException`)."""
    logs, _a, _e, _g = bordas
    srv = _Servidor([respondeu, None])
    monkeypatch.setattr(smtplib, "SMTP", srv)

    assert main._send_email_smtp(_CLIENTE, "A", "b", log_kind="planilha_pronta") is True
    assert srv.tentativas == 2, "4xx é 'tente mais tarde': retenta"
    assert not _linhas(logs, "email:pode-ter-duplicado"), (
        "o servidor respondeu — não há cópia possível pra avisar: %s"
        % type(respondeu).__name__)
    assert main._entrega_ficou_sem_resposta(respondeu) is False


def test_falha_TOTAL_depois_de_entrar_na_entrega_avisa_que_pode_ter_saido(bordas, monkeypatch):
    logs, avisos, _e, gravados = bordas
    srv = _Servidor([_caiu()] * 3, entrega_antes=True)
    monkeypatch.setattr(smtplib, "SMTP", srv)

    assert main._send_email_smtp(_CLIENTE, "Sua planilha está pronta", "<b>oi</b>",
                                 log_kind="leu_sem_medir", job_id=_JOB) is False
    assert not gravados, "sem confirmação, não vira linha de enviado"
    assert "pode ter saído cópia" in _uma(logs, "email:falha")["msg"]
    assert len(avisos) == 1 and "não dá pra saber se ele chegou" in avisos[0], avisos


def test_CONTROLE_falha_ANTES_da_entrega_avisa_o_contrario(bordas, monkeypatch):
    """A campainha do caso comum continua dizendo "NÃO recebeu" — se dissesse
    "pode ter recebido" em toda falha, o Pedro pararia de reenviar."""
    _l, avisos, _e, _g = bordas
    srv = _Servidor(no_connect=smtplib.SMTPConnectError(-1, "sem resposta"))
    monkeypatch.setattr(smtplib, "SMTP", srv)

    main._send_email_smtp(_CLIENTE, "A", "b", log_kind="leu_sem_medir", job_id=_JOB)
    assert len(avisos) == 1
    assert "NÃO recebeu esse aviso" in avisos[0] and "pode ter recebido" not in avisos[0]


# ── (4) achado A2: o orçamento encolhe a tentativa, não só decide o início ──
def test_o_orcamento_ENCOLHE_o_timeout_da_tentativa_seguinte(bordas, monkeypatch):
    """🩸 Achado A2: a verificação do "teto" só decidia se a PRÓXIMA tentativa
    começava. Com 20 s fixos por tentativa, o job ficava preso 42 s, 54 s e —
    com a campainha — 84 s, contra os 30 s anunciados. Agora o que sobrou do
    orçamento vira o `timeout=` do socket."""
    _l, _a, esperas, _g = bordas
    relogio = {"t": 0.0}
    monkeypatch.setattr(main.time, "monotonic", lambda: relogio["t"])
    monkeypatch.setattr(main.time, "sleep",
                        lambda s, *a, **k: (esperas.append(s),
                                            relogio.__setitem__("t", relogio["t"] + s)))
    srv = _Servidor([_caiu(), _caiu(), None])

    def _demora(*a, **k):
        relogio["t"] += 18.0          # servidor que só dá timeout
        return srv(*a, **k)

    monkeypatch.setattr(smtplib, "SMTP", _demora)
    main._send_email_smtp(_CLIENTE, "A", "b", log_kind="planilha_pronta")

    assert srv.timeouts[0] == main._EMAIL_TIMEOUT_S, (
        "a 1ª tentativa leva o timeout cheio — o orçamento não pode estrangular "
        "a única tentativa que quase todo envio faz: %r" % srv.timeouts)
    assert srv.timeouts[1] < srv.timeouts[0], (
        "a 2ª tem que caber no que sobrou do orçamento: %r" % srv.timeouts)
    assert srv.timeouts[1] == 10.0, srv.timeouts    # 30 - (18 gastos + 2 de espera)


def test_o_timeout_encolhido_tem_PISO(bordas, monkeypatch):
    """🪤 Piso, senão a 2ª tentativa nasce com 1 s e falha por ser curta — o
    mesmo defeito de 'catraca no mínimo que passa' que a casa já pagou 7 vezes."""
    _l, _a, esperas, _g = bordas
    relogio = {"t": 0.0}
    monkeypatch.setattr(main.time, "monotonic", lambda: relogio["t"])
    monkeypatch.setattr(main.time, "sleep",
                        lambda s, *a, **k: (esperas.append(s),
                                            relogio.__setitem__("t", relogio["t"] + s)))
    monkeypatch.setattr(main, "_EMAIL_TETO_S", 21.0)
    srv = _Servidor([_caiu(), None])

    def _demora(*a, **k):
        relogio["t"] += 18.0
        return srv(*a, **k)

    monkeypatch.setattr(smtplib, "SMTP", _demora)
    main._send_email_smtp(_CLIENTE, "A", "b", log_kind="planilha_pronta")
    assert srv.timeouts[1] == main._EMAIL_TIMEOUT_MIN_S, srv.timeouts


def test_a_campainha_vai_em_UMA_tentativa_e_com_timeout_curto(bordas, monkeypatch):
    """🩸 Achado A2, a parte que dobrava o tempo: a campainha sai pela MESMA
    porta síncrona e tinha as mesmas 3 tentativas de 20 s. Medido pela revisão:
    84 s presos no job. Ela não vale mais que o e-mail do cliente."""
    _l, _a, _e, _g = bordas
    monkeypatch.setattr(main, "_notify_admin", _NOTIFY_REAL)
    srv = _Servidor([_caiu()] * 30)
    monkeypatch.setattr(smtplib, "SMTP", srv)

    main._send_email_smtp(_CLIENTE, "A", "b", log_kind="leu_sem_medir", job_id=_JOB)

    assert srv.tentativas == main._EMAIL_TENTATIVAS + 1, (
        "3 tentativas do cliente + UMA da campainha: %d" % srv.tentativas)
    assert srv.timeouts[-1] == main._EMAIL_TIMEOUT_ALERTA_S < main._EMAIL_TIMEOUT_S


# ── (5) achado A3: a campainha é por PESSOA, não por tipo ──────────────────
def test_clientes_DIFERENTES_do_mesmo_tipo_tocam_campainhas_DIFERENTES(bordas, monkeypatch):
    """🩸 Achado A3, medido no banco em 22/09: 349 dos 364 e-mails de 30 dias
    NÃO têm `job_id` (96%), e `boas_vindas` — o tipo mais comum, 69 em 30 dias —
    é um deles. Com a chave `(dia, kind, job)`, cinco clientes falhando no mesmo
    tipo davam UMA campainha e os outros quatro ficavam como o de 22/09."""
    _l, avisos, _e, _g = bordas
    monkeypatch.setattr(smtplib, "SMTP", _Servidor([_caiu()] * 60))

    for i in range(5):
        main._send_email_smtp("cliente-%02d@example.com" % i, "A", "b",
                              log_kind="boas_vindas")
    assert len(avisos) == 5, (
        "cinco pessoas sem e-mail são cinco avisos — o tipo não é a pessoa: %d" % len(avisos))


def test_CONTROLE_a_MESMA_pessoa_no_mesmo_tipo_toca_UMA_vez(bordas, monkeypatch):
    """O freio continua existindo: a esteira horária tentaria 24× por dia."""
    _l, avisos, _e, _g = bordas
    monkeypatch.setattr(smtplib, "SMTP", _Servidor([_caiu()] * 60))
    for _ in range(4):
        main._send_email_smtp(_CLIENTE, "A", "b", log_kind="boas_vindas")
    assert len(avisos) == 1


def test_o_rastro_da_falha_identifica_a_PESSOA_sem_o_endereco(bordas, monkeypatch):
    logs, _a, _e, _g = bordas
    monkeypatch.setattr(smtplib, "SMTP", _Servidor([_caiu()] * 9))
    main._send_email_smtp(_CLIENTE, "A", "b", log_kind="boas_vindas")
    msg = _uma(logs, "email:falha")["msg"]
    assert ("pessoa=" + main._marca_do_email(_CLIENTE)) in msg, msg
    assert _RE_EMAIL.search(msg) is None, msg


def test_CONTROLE_a_marca_separa_pessoas_e_e_estavel():
    """Sem isto, um `_marca_do_email` que devolvesse sempre "-" passaria nos
    guardas de LGPD por mérito falso — e o rastro voltaria a juntar clientes."""
    a, b = "cliente-nn@example.com", "outro-cliente@example.com"
    assert main._marca_do_email(a) != main._marca_do_email(b)
    assert main._marca_do_email(a) == main._marca_do_email("  CLIENTE-NN@Example.COM ")
    assert _RE_EMAIL.search(main._marca_do_email(a)) is None
    assert a.split("@")[0] not in main._marca_do_email(a)


def test_a_campainha_que_CAI_nao_queima_o_dia_daquele_tipo(bordas, monkeypatch):
    """🩸 Achado A3, 2ª metade: a chave era marcada ANTES de a campainha tocar.
    Numa queda de SMTP — justamente quando o alerta também falha — o tipo ficava
    calado até a meia-noite, mesmo depois de o servidor voltar."""
    _l, avisos, _e, _g = bordas
    caiu = {"n": 0}

    def _aviso_que_cai(*a, **k):
        caiu["n"] += 1
        return False                      # o alerta não saiu

    monkeypatch.setattr(main, "_notify_admin", _aviso_que_cai)
    monkeypatch.setattr(smtplib, "SMTP", _Servidor([_caiu()] * 60))
    main._send_email_smtp(_CLIENTE, "A", "b", log_kind="boas_vindas")
    assert caiu["n"] == 1 and avisos == []

    # o servidor voltou (o relógio do freio é tempo, não o dia)
    main._EMAIL_ALERTA_ESTADO["caiu_em"] = 0.0
    monkeypatch.setattr(main, "_notify_admin",
                        lambda *a, **k: avisos.append(" ".join(str(x) for x in a)) or True)
    main._send_email_smtp(_CLIENTE, "A", "b", log_kind="boas_vindas")
    assert len(avisos) == 1, "a chave não podia ter sido queimada pela campainha que caiu"


def test_a_campainha_que_CAI_segura_as_proximas_por_um_tempo(bordas, monkeypatch):
    """🪤 O outro lado: sem freio, uma newsletter de 65 destinatários viraria 65
    tentativas de campainha contra um servidor que está fora do ar."""
    _l, _a, _e, _g = bordas
    tentou = {"n": 0}
    monkeypatch.setattr(main, "_notify_admin",
                        lambda *a, **k: (tentou.__setitem__("n", tentou["n"] + 1), False)[1])
    monkeypatch.setattr(smtplib, "SMTP", _Servidor([_caiu()] * 200))
    for i in range(10):
        main._send_email_smtp("cliente-%02d@example.com" % i, "A", "b", log_kind="newsletter")
    assert tentou["n"] == 1, "a 1ª tentou e caiu; as outras nove esperam: %d" % tentou["n"]


def test_o_dia_do_freio_e_o_de_BRASILIA(monkeypatch):
    """🪤 `datetime.utcnow()` vira o dia às 21:00 de Brasília — o freio de "uma
    campainha por dia" reiniciava no meio da noite de trabalho do Pedro."""
    import datetime as _dt
    quando = _dt.datetime(2026, 9, 23, 1, 30)        # 22/09 22:30 em Brasília
    monkeypatch.setattr(main, "datetime",
                        type("D", (), {"utcnow": staticmethod(lambda: quando)}))
    assert main._dia_brasilia() == "2026-09-22"
    assert quando.strftime("%Y-%m-%d") == "2026-09-23", (
        "controle: é exatamente aqui que o jeito antigo errava")


# ── (6) achado A4: o rastro também precisa de freio ────────────────────────
def test_o_rastro_da_falha_tem_FREIO_por_tipo(bordas, monkeypatch):
    """🩸 Achado A4: uma queda de SMTP no meio da newsletter (65 destinatários)
    punha 65 linhas de erro no painel de 40 linhas que o Pedro usa pra achar
    erro de verdade — empurrando o erro real pra fora da tela. O diagnóstico não
    perde nada: o que interessa é "o tipo X parou de sair"."""
    logs, _a, _e, _g = bordas
    monkeypatch.setattr(smtplib, "SMTP", _Servidor([_caiu()] * 200))
    for i in range(20):
        main._send_email_smtp("cliente-%02d@example.com" % i, "A", "b",
                              log_kind="newsletter")

    linhas = _linhas(logs, "email:falha")
    assert len(linhas) == main._EMAIL_FALHA_MAX_LINHAS + 1, (
        "20 falhas do mesmo tipo: %d linhas" % len(linhas))
    assert "teto" in linhas[-1]["msg"], linhas[-1]["msg"]


def test_CONTROLE_o_freio_do_rastro_nao_cala_OUTRO_tipo(bordas, monkeypatch):
    """Um freio que calasse tudo esconderia justamente o segundo problema."""
    logs, _a, _e, _g = bordas
    monkeypatch.setattr(smtplib, "SMTP", _Servidor([_caiu()] * 200))
    for i in range(10):
        main._send_email_smtp("cliente-%02d@example.com" % i, "A", "b",
                              log_kind="newsletter")
    main._send_email_smtp("outro@example.com", "A", "b", log_kind="planilha_pronta")
    assert any("kind=planilha_pronta" in x["msg"] for x in _linhas(logs, "email:falha")), (
        "o tipo que ainda não falhou nesta janela tem que aparecer")


def test_o_alerta_que_FALHA_nao_chama_outro_alerta(bordas, monkeypatch):
    """🪤 O alerta sai pela mesma porta que acabou de falhar. Sem trava, um
    servidor fora do ar viraria recursão sem fim."""
    logs, _avisos, _e, _g = bordas
    # aqui o `_notify_admin` é o DE VERDADE — é ele que reentra no envio
    monkeypatch.setattr(main, "_notify_admin", _NOTIFY_REAL)
    srv = _Servidor([_caiu()] * 30)
    monkeypatch.setattr(smtplib, "SMTP", srv)

    assert main._send_email_smtp(_CLIENTE, "A", "b", log_kind="leu_sem_medir",
                                 job_id=_JOB) is False
    falhas = _linhas(logs, "email:falha")
    assert len(falhas) == 2, (
        "esperava 2 linhas (o e-mail do cliente + o alerta que também não saiu) "
        "e vieram %d — a trava anti-recursão furou: %r" % (len(falhas), falhas))
    assert srv.tentativas <= 2 * main._EMAIL_TENTATIVAS
