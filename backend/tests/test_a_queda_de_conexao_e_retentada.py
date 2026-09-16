# -*- coding: utf-8 -*-
"""Conexão que cai no meio da resposta da IA tem que ser retentada.

🩸 16/09/2026, ao vivo. Cliente NOVO (chegou por indicação, cadastrou 14:48)
subiu o primeiro projeto às 14:52 — um PDF. A leitura quebrou com
`httpx.RemoteProtocolError: peer closed connection without sending complete
message body (incomplete chunked read)`: a conexão caiu no meio do streaming.

DUAS RÉGUAS DISCORDAVAM, e as duas estavam neste arquivo:
  · `_is_retryable` tinha lista PRÓPRIA e curta (429 · 529 · overloaded ·
    timeout). `RemoteProtocolError` não casava → `call_with_retry_stream`, com
    teto de 8 tentativas, usou ZERO;
  · `_TRANSIENT_TOKENS`, que decide o TEXTO mostrado ao cliente, já reconhecia
    ("remoteprotocolerror", "connection", "reset by peer") → a tela dizia
    "provedor sobrecarregado, o sistema já tentou várias vezes, é só
    reprocessar". Uma tentativa que nunca aconteceu.

O cliente reprocessou às 14:55, 14:57, 14:58 e 14:59 — quatro quedas no mesmo
lugar, porque cada rodada tentava uma vez só.

📏 Alcance: 6 linhas com essa assinatura em 60 dias, em 2 arquivos — sempre
REPETIDO no mesmo arquivo, nunca espalhado (não era sobrecarga do provedor).

🚨 Estes guardas CHAMAM a régua e o laço de verdade.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402
import pytest  # noqa: E402

import llm_retry  # noqa: E402

_CORTE = ("peer closed connection without sending complete message body "
          "(incomplete chunked read)")


# ── a régua ────────────────────────────────────────────────────────────────
def test_a_queda_no_meio_do_streaming_e_retentavel():
    assert llm_retry._is_retryable(httpx.RemoteProtocolError(_CORTE)) is True


@pytest.mark.parametrize("erro", [
    httpx.RemoteProtocolError(_CORTE),
    httpx.ReadError("connection reset by peer"),
    ConnectionResetError("[Errno 104] Connection reset by peer"),
    BrokenPipeError("[Errno 32] Broken pipe"),
    TimeoutError("read timed out"),
])
def test_as_quedas_de_rede_cruas_sao_retentaveis(erro):
    assert llm_retry._is_retryable(erro) is True, type(erro).__name__


@pytest.mark.parametrize("erro", [
    ValueError("invalid_request_error: messages.0.content: image too large"),
    ValueError("invalid high surrogate in string"),
    RuntimeError("authentication_error: invalid x-api-key"),
    RuntimeError("not_found_error: model claude-inexistente"),
])
def test_CONTROLE_erro_NOSSO_continua_sem_retentar(erro):
    """Retentar 400/401/404 só empurra o mesmo lixo de novo — e faz o cliente
    esperar cinco minutos por uma falha que já era certa."""
    assert llm_retry._is_retryable(erro) is False, str(erro)


def test_CONTROLE_erro_desconhecido_nao_vira_retry():
    assert llm_retry._is_retryable(ValueError("deu ruim")) is False


def test_o_TIPO_do_erro_conta_quando_a_mensagem_nao_diz_nada():
    """🪤 A mensagem crua nem sempre traz palavra conhecida — o httpx corta com
    'peer closed' e pronto. Quem identifica o caso é a CLASSE, e é por isso que
    ela entra no texto que vai pra régua."""
    assert llm_retry._is_retryable(httpx.RemoteProtocolError("peer closed")) is True


def test_permanente_vence_transitorio_na_regua_unica():
    """🪤 Agora que o retry usa o classificador, a ordem dele virou regra de
    retry: erro NOSSO com a palavra 'connection' junto não pode virar 8 tentativas."""
    assert llm_retry.classify_error_text(
        "[status=400] invalid_request; connection reset") == "permanent"
    assert llm_retry._is_retryable(
        RuntimeError("[status=400] invalid_request; connection reset")) is False


def test_as_DUAS_reguas_dao_a_MESMA_resposta():
    """🔑 O defeito não era a lista curta: era existirem duas. Se o texto conta
    ao cliente que a falha é transitória, o motor TEM que ter retentado."""
    casos = [
        _CORTE,
        "RemoteProtocolError: " + _CORTE,
        "connection reset by peer",
        "Broken pipe",
        "overloaded_error: server overloaded",
        "rate_limit_error",
        "Request timed out",
    ]
    for texto in casos:
        diz_ao_cliente = llm_retry.classify_error_text(texto) == "transient"
        motor_retenta = llm_retry._is_retryable(RuntimeError(texto))
        assert diz_ao_cliente == motor_retenta, (
            "as réguas discordam em %r: texto=%s retry=%s"
            % (texto, diz_ao_cliente, motor_retenta))


# ── o laço de verdade ──────────────────────────────────────────────────────
class _ClienteFalso:
    """Dublê do cliente da Anthropic: derruba a conexão N vezes e então responde."""

    def __init__(self, quedas):
        self.quedas = quedas
        self.tentativas = 0
        self.messages = self

    def stream(self, **kwargs):
        self.tentativas += 1
        cliente = self

        class _Ctx:
            def __enter__(self_):
                if cliente.tentativas <= cliente.quedas:
                    raise httpx.RemoteProtocolError(_CORTE)
                return self_

            def __exit__(self_, *a):
                return False

            def get_final_message(self_):
                class _Msg:
                    content = [type("T", (), {"text": '{"items": []}'})()]
                    stop_reason = "end_turn"
                    usage = type("U", (), {"input_tokens": 1, "output_tokens": 1})()
                return _Msg()

        return _Ctx()


def test_o_laco_do_streaming_RETENTA_depois_da_queda(monkeypatch):
    monkeypatch.setattr(llm_retry.time, "sleep", lambda *_a: None)
    cliente = _ClienteFalso(quedas=2)
    resp = llm_retry.call_with_retry_stream(
        cliente, tag="guarda", model="claude-x", max_tokens=10,
        messages=[{"role": "user", "content": "oi"}])
    assert cliente.tentativas == 3, "tentou %d vez(es) — o retry não entrou" % cliente.tentativas
    assert resp.content[0].text == '{"items": []}'


def test_CONTROLE_erro_permanente_NAO_vira_oito_tentativas(monkeypatch):
    """O outro lado da moeda: chave errada não pode custar 5 minutos ao cliente."""
    monkeypatch.setattr(llm_retry.time, "sleep", lambda *_a: None)

    class _Permanente(_ClienteFalso):
        def stream(self, **kwargs):
            self.tentativas += 1
            raise RuntimeError("authentication_error: invalid x-api-key")

    cliente = _Permanente(quedas=0)
    with pytest.raises(RuntimeError):
        llm_retry.call_with_retry_stream(
            cliente, tag="guarda", model="claude-x", max_tokens=10,
            messages=[{"role": "user", "content": "oi"}])
    assert cliente.tentativas == 1, "retentou erro permanente %d vezes" % cliente.tentativas


def test_o_laco_SEM_streaming_tambem_retenta(monkeypatch):
    """🪤 São DOIS laços no arquivo. O do streaming é o que quebrou ao vivo, mas
    o outro atende memorial/cronograma/chat — consertar só um deixa metade do
    produto com a régua velha."""
    monkeypatch.setattr(llm_retry.time, "sleep", lambda *_a: None)

    class _Msgs:
        def __init__(self, dono):
            self.dono = dono

        def create(self, **kwargs):
            self.dono.tentativas += 1
            if self.dono.tentativas <= self.dono.quedas:
                raise httpx.RemoteProtocolError(_CORTE)

            class _Msg:
                content = [type("T", (), {"text": "ok"})()]
                stop_reason = "end_turn"
                usage = type("U", (), {"input_tokens": 1, "output_tokens": 1})()
            return _Msg()

    class _Cli:
        def __init__(self, quedas):
            self.quedas = quedas
            self.tentativas = 0
            self.messages = _Msgs(self)

    cliente = _Cli(quedas=2)
    resp = llm_retry.call_with_retry(
        cliente, tag="guarda", model="claude-x", max_tokens=10,
        messages=[{"role": "user", "content": "oi"}])
    assert cliente.tentativas == 3, "tentou %d vez(es)" % cliente.tentativas
    assert resp.content[0].text == "ok"


def test_a_queda_esgota_o_teto_e_ai_sim_desiste(monkeypatch):
    monkeypatch.setattr(llm_retry.time, "sleep", lambda *_a: None)
    cliente = _ClienteFalso(quedas=99)
    with pytest.raises(httpx.RemoteProtocolError):
        llm_retry.call_with_retry_stream(
            cliente, tag="guarda", model="claude-x", max_tokens=10, max_retries=3,
            messages=[{"role": "user", "content": "oi"}])
    assert cliente.tentativas == 4, cliente.tentativas


def test_ao_desistir_a_falha_VAI_pra_conta_e_nao_sobra_dormida(monkeypatch):
    """🪤 Achado por sabotagem: o laço tem DUAS saídas e só uma presta contas.

    Sair pelo `raise` de dentro do `except` grava a linha de custo; sair pelo
    fim do `for` não grava nada — e a chamada que estourou DEPOIS de o modelo já
    ter gerado saída é COBRADA pela Anthropic. Custo ausente, somado por SUM,
    é indistinguível de custo baixo. De quebra, a saída errada ainda dorme uma
    vez a mais, depois da última tentativa, sem ninguém pra esperar.
    """
    dormidas = []
    gravados = []
    monkeypatch.setattr(llm_retry.time, "sleep", lambda *_a: dormidas.append(1))
    monkeypatch.setattr(llm_retry, "_gravar_uso", lambda **kw: gravados.append(kw))

    cliente = _ClienteFalso(quedas=99)
    with pytest.raises(httpx.RemoteProtocolError):
        llm_retry.call_with_retry_stream(
            cliente, tag="guarda", model="claude-x", max_tokens=10, max_retries=2,
            messages=[{"role": "user", "content": "oi"}])

    assert cliente.tentativas == 3, cliente.tentativas
    assert [g for g in gravados if g.get("resultado") == "falhou"], (
        "desistiu sem gravar a linha de custo — a chamada cobrada sumiu da conta")
    assert len(dormidas) == cliente.tentativas - 1, (
        "dormiu %d vez(es) pra %d tentativa(s): sobra espera depois da última"
        % (len(dormidas), cliente.tentativas))
