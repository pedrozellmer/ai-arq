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

    def __enter__(self, *a, **k):
        return self

    def __exit__(self, *a, **k):
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
            raise erro
        self.dono.enviados.append((de, list(para), corpo))


class _Servidor:
    """Faz as vezes de `smtplib.SMTP`: um roteiro de exceções por tentativa
    (None = aceita a mensagem). `no_connect=True` derruba já na conexão."""

    def __init__(self, roteiro=(), no_connect=None):
        self.roteiro = list(roteiro)
        self.no_connect = no_connect
        self.tentativas = 0
        self.enviados = []

    def __call__(self, *a, **k):
        self.tentativas += 1
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
