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


def _agora_br_de_verdade():
    """Carrega a função de PRODUÇÃO, sem subir o app inteiro."""
    src = _main()
    i = src.index("def _agora_br_fn():")
    nl = chr(10)
    j = min(x for x in (src.find(nl + "def ", i + 10), src.find(nl + "@app.", i + 10)) if x > 0)
    ns = {}
    exec(compile(src[i:j], "fuso", "exec"), ns)
    return ns["_agora_br_fn"]


def test_o_offset_e_3h_PARA_TRAS_medido_na_funcao_real():
    """🚨 A 1ª versão deste teste conferia se o TEXTO 'timedelta(hours=3)' estava
    no corpo — verdade tanto pra menos quanto pra MAIS. Invertendo o sinal em
    produção (o erro de 6h), os 7 testes deste arquivo passavam verde.

    E o 'controle positivo' que eu tinha escrito era pior: ele fazia a conta
    DENTRO do teste e conferia a si mesmo, sem tocar na função de produção.

    Agora mede o EFEITO da função real: Brasília está ATRÁS de UTC."""
    from datetime import datetime as _dt
    br = _agora_br_de_verdade()()
    delta = (_dt.utcnow() - br).total_seconds()
    assert 3 * 3600 - 60 < delta < 3 * 3600 + 60, (
        "a função devolve %.1f h de diferença de UTC — Brasília é UTC-3, e "
        "somar em vez de subtrair dá 6h de erro" % (delta / 3600))


def test_controle_positivo_a_sabotagem_seria_pega():
    """Prova que o teste acima reprova: a mesma conta com o sinal trocado tem
    que sair FORA da janela aceita."""
    from datetime import datetime as _dt, timedelta as _td
    errado = _dt.utcnow() + _td(hours=3)
    delta = (_dt.utcnow() - errado).total_seconds()
    assert not (3 * 3600 - 60 < delta < 3 * 3600 + 60), (
        "a janela do teste aceita o sinal invertido — ele não guarda nada")
