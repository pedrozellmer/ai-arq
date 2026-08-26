# -*- coding: utf-8 -*-
"""Uma coluna de ordenação errada matou a esteira de e-mail inteira por 42h.

🚨 26/08/2026. O paginador `_supa_rest_tudo` (nascido em 25/08 pra furar o teto
de 1000 linhas do PostgREST) ordena por **`id.asc` por padrão**. A tabela
`profiles` NÃO tem coluna `id` — a chave é `user_id`. O PostgREST devolve
**HTTP 400 `column profiles.id does not exist`**, quem chama levanta, e o
`emails_auto_tick` **aborta no primeiro passo**.

O abort mata o tick INTEIRO, não só um e-mail: boas-vindas de resgate,
`boas_vindas_cadastro`, `nudge_cadastro`, `nudge_onboarding`, `calibracao`,
`proximo_projeto`, `retorno_30d`, `cronograma_checkin` e o alerta de cadastro
novo pro Pedro. Último e-mail automático: **24/08 20:00 BRT**.

🪤 NADA APITOU. O `cron.job_run_details` dizia `succeeded` e o HTTP do
`net.http_post` era **200** — o erro estava no CORPO da resposta. Olhar o status
do cron é olhar pro lugar errado.

🪤 `boas_vindas_cadastro` foi ao ar em 25/08 e tem **0 envios na vida**: nasceu
dentro de um tick já morto. Um deploy validado por leitura de código passaria —
o código da esteira está certo, o CHAMADOR é que estava.

Conferido no banco em 26/08: das 10 tabelas que o paginador toca, **`profiles` é
a única sem `id`**. O estrago é contido, mas o padrão silencioso continua sendo
uma armadilha — por isso o guarda cobra as DUAS pontas: o chamador certo e o
paginador dizendo o nome da coluna quando levar 400.
"""
import io
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
_CORPO = chr(10).join(l for l in _FONTE.split(chr(10))
                      if not l.strip().startswith("#"))


def _trecho_da_leitura_de_perfis():
    """O bloco em volta da chamada que leu `profiles` no tick de e-mail."""
    i = _CORPO.find('_supa_rest_tudo(\n            "profiles"')
    if i < 0:
        i = _CORPO.find('"profiles", params={"select": "user_id,email"}')
    assert i > 0, "não achei mais a leitura de perfis do tick de e-mail"
    return _CORPO[max(0, i - 200):i + 300]


def test_a_leitura_de_perfis_ordena_por_user_id():
    """A linha que custou 42h de esteira parada."""
    trecho = _trecho_da_leitura_de_perfis()
    assert "user_id.asc" in trecho, (
        "a leitura de `profiles` voltou a usar a ordenação padrão `id.asc`. "
        "A tabela não tem `id` → HTTP 400 → o tick de e-mail aborta INTEIRO, "
        "os 8 tipos de uma vez, e o cron continua marcando 'succeeded'.")


def test_controle_positivo_o_padrao_do_paginador_AINDA_e_id():
    """Prova que o teste acima cobra algo de verdade.

    Se um dia o padrão virar `user_id.asc`, o teste de cima passa de graça e
    para de proteger — este aqui avisa que a razão mudou.
    """
    assert 'ordem: str = "id.asc"' in _CORPO, (
        "o padrão do paginador mudou. Reveja se o guarda acima ainda faz "
        "sentido — ele existe porque o padrão NÃO serve pra `profiles`.")


def test_o_paginador_DIZ_qual_coluna_quebrou():
    """🪤 O defeito viveu 42h porque não havia UMA linha nomeando a coluna.

    HTTP 400 sem mensagem é indistinguível de rede ruim, RLS ou tabela errada.
    """
    assert "supa-paginador" in _CORPO, (
        "o paginador voltou a engolir o 400 sem dizer nada")
    i_erro = _CORPO.find("supa-paginador")
    janela = _CORPO[i_erro - 300:i_erro + 400]
    assert "400" in janela, "a mensagem não está presa ao caso do 400"
    assert "ordem" in janela, (
        "a mensagem não cita a coluna de ordenação — que é a informação que "
        "faltou por 42 horas")


def test_o_tick_continua_abortando_quando_nao_le_perfis():
    """🚨 Isto NÃO é o bug — é a trava de segurança, e tem que ficar.

    Sem a lista de perfis, todo mundo pareceria "sem perfil" e levaria cutucada
    indevida de 'termine seu cadastro'. Na dúvida, NÃO envia (regra nº1 aplicada
    a e-mail). O conserto foi a ordenação, nunca afrouxar isto.
    """
    assert "abortando por segurança" in _CORPO, (
        "a trava que impede cutucar cliente errado quando `profiles` falha foi "
        "removida — isso troca um defeito visível por e-mail errado em cliente")
