# -*- coding: utf-8 -*-
"""Boas-vindas duplicado: o cliente novo levou DOIS em 2 minutos.

🚨 24/08/2026, caso cliente-19 (cliente1@example.com), primeiro dia de conta:

    19:28:35  Bem-vindo ao AI.arq — seu projeto vira planilha medida
    19:30:55  Bem-vindo ao AI.arq — seu projeto vira planilha medida   ← de novo
    19:56:53  sua planilha está pronta
    20:25:17  medimos com o CAD, planilha atualizada

Quatro e-mails em 57 minutos, sendo um deles repetido. A regra do Pedro é no
MÁXIMO 1 por semana por cliente.

🔑 A causa: o único portão de `/api/notify/welcome` era "conta criada há menos
de 1h". O guard do frontend é `localStorage` — POR NAVEGADOR. Duas abas, um
refresh ou outro browser na primeira hora e o e-mail sai de novo.

🪤 O agravante: o alerta interno PRO PEDRO, 20 linhas abaixo no mesmo endpoint,
já tinha dedup (`_email_auto_ja_enviado(..., "alerta_novo_cadastro")`). O do
CLIENTE não tinha. E `_ja_recebeu_kind` existia desde 02/08 exatamente pra isso
— a docstring dela diz "evita e-mail duplicado" — e só o caminho de RESGATE a
chamava. A ferramenta certa estava pronta, guardada, e o caminho principal
passava direto por ela.

🪤 05/09/2026 — DOIS GUARDAS DAQUI ERAM CEGOS. Um lia a string
`_ja_recebeu_kind(email, "boas_vindas")` no fonte e continuou verde com ela em
`if False and ...`, ou seja, código morto: a dedup do cliente sumiu e o
incidente de 24/08 voltou inteiro. O outro media a ORDEM DAS STRINGS no
arquivo e continuou verde com um envio inserido ACIMA da conferência — ordem
no texto não é ordem no tempo. Os dois agora CHAMAM a rota.
"""
import io
import json as _jsonb
import os
import sys
import urllib.request as _ureq
from datetime import datetime as _dtb, timezone as _tzb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# 🪤 Janela de tamanho fixo mede o vizinho (ou um pedaço) e passa
# verde por engano — a auditoria de 25/08 achou 17 assim. O recorte
# certo mora num lugar só.
from _corpo import corpo_de  # noqa: E402

import main as M  # noqa: E402

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _endpoint():
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index('@app.post("/api/notify/welcome")')
    j = src.index("\n@app.", i + 10)
    return src[i:j]


# ══════════════════════════════════════════════════════════════════════════
#  🧪 BANCADA QUE EXECUTA `/api/notify/welcome`
# ══════════════════════════════════════════════════════════════════════════
class _RespostaFalsa:
    def __init__(self, payload):
        self._b = _jsonb.dumps(payload).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _RequisicaoFalsa:
    headers = {"user-agent": "bancada"}
    query_params = {}


def _bancada_do_boas_vindas(monkeypatch, ja_recebeu, linha_do_tempo, enviados):
    """Perfil recém-criado (conta nova) + o log de envios dizendo se já saiu.

    `linha_do_tempo` grava QUANDO cada coisa aconteceu — é o que separa
    "conferiu antes de mandar" de "mandou e depois conferiu".
    """
    monkeypatch.setattr(M, "_get_user_from_request",
                        lambda request, tolerante=False:
                        {"id": "u-cliente-19", "email": "cliente1@example.com"})

    def _fake_urlopen(req, timeout=None):
        url = getattr(req, "full_url", str(req))
        if "email_sent_log" in url:
            linha_do_tempo.append("consultou_dedup")
            return _RespostaFalsa([{"id": 1}] if ja_recebeu else [])
        if "profiles" in url:
            return _RespostaFalsa([{"full_name": "Cliente 19",
                                    "created_at": _dtb.now(_tzb.utc).isoformat()}])
        return _RespostaFalsa([])
    monkeypatch.setattr(_ureq, "urlopen", _fake_urlopen)

    def _envia(email, name="", *a, **k):
        linha_do_tempo.append("enviou")
        enviados.append(email)
        return True
    monkeypatch.setattr(M, "_send_welcome_email", _envia)
    # o alerta interno pro Pedro sai em thread; aqui ele só não pode atrapalhar
    monkeypatch.setattr(M, "_notify_admin", lambda *a, **k: True)
    monkeypatch.setattr(M, "_email_auto_ja_enviado", lambda *a, **k: True)
    monkeypatch.setattr(M, "_email_auto_registrar", lambda *a, **k: None)


def test_o_boas_vindas_confere_se_ja_saiu(monkeypatch):
    """🚨 24/08: o cliente-19 levou DOIS boas-vindas em 2 minutos.

    Executa a rota com o log dizendo que o boas-vindas já saiu. O guarda antigo
    procurava a chamada escrita no fonte — e ficava verde com ela em
    `if False and ...`, ou seja, código morto.
    """
    linha, enviados = [], []
    _bancada_do_boas_vindas(monkeypatch, ja_recebeu=True,
                            linha_do_tempo=linha, enviados=enviados)

    resp = M.notify_welcome(_RequisicaoFalsa())

    assert enviados == [], (
        "mandou o boas-vindas de novo pra quem já tinha recebido — duas cargas "
        "do dashboard na 1ª hora mandam dois")
    assert resp.get("sent") is False and resp.get("reason") == "ja_recebeu", (
        "a rota nem diz que segurou: %r" % (resp,))


def test_a_checagem_vem_ANTES_do_envio(monkeypatch):
    """Conferir depois de mandar não conserta nada.

    Mede a ordem no TEMPO (quem foi chamado primeiro), não a ordem das strings
    no arquivo — era isso que deixava passar um envio inserido acima da
    checagem.
    """
    linha, enviados = [], []
    _bancada_do_boas_vindas(monkeypatch, ja_recebeu=False,
                            linha_do_tempo=linha, enviados=enviados)

    resp = M.notify_welcome(_RequisicaoFalsa())

    assert "consultou_dedup" in linha and "enviou" in linha, (
        "cenário errado: quem nunca recebeu TEM que receber (%r / %r)" % (resp, linha))
    assert linha.index("consultou_dedup") < linha.index("enviou"), (
        "o e-mail saiu ANTES de conferir se já tinha saído — a ordem no arquivo "
        "pode estar certa e a ordem no tempo, errada: %r" % linha)
    assert linha.count("enviou") == 1, (
        "o boas-vindas saiu mais de uma vez na mesma chamada: %r" % linha)
    assert resp.get("sent") is True and enviados == ["cliente1@example.com"], (
        "🧪 controle: quem nunca recebeu TEM que receber (%r)" % (resp,))


def test_a_checagem_falha_FECHADA():
    """Se a consulta ao log falhar, NÃO manda. Um e-mail a menos é recuperável;
    um a mais, na caixa de quem acabou de chegar, não."""
    corpo = corpo_de("_ja_recebeu_kind")
    assert "return True" in corpo.split("except")[1][:200], (
        "a checagem de duplicata passou a falhar ABERTA — erro de rede vira "
        "e-mail repetido")


def test_o_portao_de_conta_nova_continua():
    """Contrapeso: a dedup não pode ter substituído o gate de 'conta nova',
    senão cliente antigo abrindo o dashboard receberia boas-vindas."""
    corpo = _endpoint()
    assert 'reason": "not_new"' in corpo


def test_o_alerta_interno_continua_deduplicado():
    """Ele já era o certo — não pode quebrar junto."""
    corpo = _endpoint()
    assert '_email_auto_ja_enviado(NOTIFY_EMAIL, "alerta_novo_cadastro"' in corpo
