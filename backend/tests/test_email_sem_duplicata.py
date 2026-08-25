# -*- coding: utf-8 -*-
"""Boas-vindas duplicado: o cliente novo levou DOIS em 2 minutos.

🚨 24/08/2026, caso Alan (alansilvacosta@gmail.com), primeiro dia de conta:

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
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 🪤 Janela de tamanho fixo mede o vizinho (ou um pedaço) e passa
# verde por engano — a auditoria de 25/08 achou 17 assim. O recorte
# certo mora num lugar só.
from _corpo import corpo_de  # noqa: E402

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _endpoint():
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index('@app.post("/api/notify/welcome")')
    j = src.index("\n@app.", i + 10)
    return src[i:j]


def test_o_boas_vindas_confere_se_ja_saiu():
    corpo = _endpoint()
    assert '_ja_recebeu_kind(email, "boas_vindas")' in corpo, (
        "o boas-vindas voltou a sair sem conferir se já foi enviado — duas "
        "cargas do dashboard na 1ª hora mandam dois")


def test_a_checagem_vem_ANTES_do_envio():
    """Conferir depois de mandar não conserta nada."""
    corpo = _endpoint()
    i_check = corpo.index('_ja_recebeu_kind(email, "boas_vindas")')
    i_send = corpo.index("_send_welcome_email(")
    assert i_check < i_send


def test_a_checagem_falha_FECHADA():
    """Se a consulta ao log falhar, NÃO manda. Um e-mail a menos é recuperável;
    um a mais, na caixa de quem acabou de chegar, não."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
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
