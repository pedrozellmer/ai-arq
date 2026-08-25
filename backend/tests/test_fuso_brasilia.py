# -*- coding: utf-8 -*-
"""O painel dizia "projetos hoje" contando o dia UTC.

🚨 24/08/2026. O Pedro, lendo os horários que eu reportava: *"vc ta no fuso
errado"*. Era verdade — o banco grava UTC e eu vinha lendo cru, três horas de
diferença em tudo.

Mas o meu erro de leitura tinha um irmão DENTRO do produto, e esse custava
informação: o contador de "projetos hoje" do painel filtrava por
`datetime.utcnow().strftime('%Y-%m-%d')`. Entre 21:00 e a meia-noite de
Brasília, o UTC já virou o dia seguinte — então o painel mostrava só o que
entrou depois das 21h e chamava aquilo de "hoje".

Medido no instante do conserto (22:15 de Brasília):

    projetos do dia, de verdade ....... 5
    o que o painel mostrava ........... 1
    janela cega ....................... 21:00 → 00:00, TODO dia

Três horas por dia em que o Pedro olhava o painel e via quase zero.

🪤 A conta `now - 3h` já existia copiada inline no lembrete da newsletter.
Regra de fuso espalhada é regra que diverge — agora é um lugar só.
"""
import io
import os
from datetime import datetime, timedelta

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _main():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def test_existe_um_lugar_so_que_sabe_o_fuso():
    src = _main()
    assert "def _agora_br_fn():" in src
    assert "def _hoje_br():" in src


def test_o_contador_de_hoje_NAO_usa_a_data_utc():
    src = _main()
    assert "created_at=gte.{datetime.utcnow().strftime('%Y-%m-%d')}" not in src, (
        "voltou a contar 'projetos hoje' pelo dia UTC — das 21h à meia-noite o "
        "painel some com quase tudo")


def test_o_contador_de_hoje_usa_o_helper():
    src = _main()
    i = src.index("# Contar projetos hoje")
    trecho = src[i:i + 700]
    assert "_hoje_br()" in trecho


def test_o_corte_do_dia_e_03h_UTC_que_e_meia_noite_em_brasilia():
    """🪤 Não basta usar a DATA de Brasília: se o corte continuasse em T00:00:00
    (UTC), ainda estaria pegando de 21h do dia anterior. Meia-noite de Brasília
    é 03:00 UTC."""
    src = _main()
    i = src.index("# Contar projetos hoje")
    trecho = src[i:i + 700]
    assert 'T03:00:00' in trecho, "o corte não é meia-noite de Brasília"


def test_a_newsletter_nao_tem_mais_a_conta_de_fuso_copiada():
    src = _main()
    assert "now - _td_nl(hours=3)" not in src, (
        "a conta do fuso voltou a existir em duplicata — é assim que as duas "
        "divergem depois")


def test_o_offset_e_3h_sem_horario_de_verao():
    """O Brasil aboliu o horário de verão em 2019; -3 vale o ano inteiro. Se um
    dia voltar, este teste é o lugar de descobrir."""
    src = _main()
    i = src.index("def _agora_br_fn():")
    corpo = src[i:i + 1400]
    assert "timedelta(hours=3)" in corpo.replace("_t(hours=3)", "timedelta(hours=3)")


def test_controle_a_conta_bate_com_o_esperado():
    """Controle positivo do sentido: Brasília está ATRÁS de UTC, não à frente.
    Somar em vez de subtrair daria 6h de erro e passaria despercebido."""
    utc = datetime(2026, 8, 25, 1, 15, 0)     # 01:15 UTC
    br = utc - timedelta(hours=3)
    assert br.day == 24 and br.hour == 22, "a conversão inverteu o sinal"
