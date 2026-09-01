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
import re as _re
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


# ═══════════════════════════════════════════════════════════════════════════
#  01/09/2026 — O MESMO ERRO, TERCEIRA VEZ, E AGORA COM GUARDA
# ═══════════════════════════════════════════════════════════════════════════
# 24/08 o Pedro me corrigiu ("vc ta no fuso errado"). 31/08 ele me corrigiu de
# novo. 01/09 eu li 18:15 UTC e disse que um cliente tinha rodado "de
# madrugada" — era 15:15, ontem à tarde. Ele: *"O último foi ontem de tarde,
# não teve mais nada essa noite."*
#
# Convenção desta casa desde 16/07: TODO horário exibido é America/Sao_Paulo,
# e o jeito certo é `window.fmtBR` / `window.fmtDataBR`, que fixam o fuso por
# último (o caller escolhe os campos, nunca o fuso).
#
# 🩸 Mesmo assim escaparam DOIS pontos no admin que formatavam data/hora sem
# fuso nenhum — `toLocaleDateString`/`toLocaleTimeString` seguem o relógio do
# NAVEGADOR. Pro Pedro, que está em Brasília, ficava certo por acaso; pra
# qualquer um fora do fuso, errado. Guarda que não existia até hoje.
#
# 🪤 `Number.toLocaleString` (dinheiro, milhar) NÃO é fuso e não pode ser
# acusado — é a distinção que faz este guarda ser usável em vez de ruído.

_RX_DATA_SEM_FUSO = _re.compile(
    r"new Date\([^)]*\)\s*\.\s*toLocale(?:Date|Time)?String\s*\([^;]{0,220}",
    _re.S)


def _htmls_do_site():
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for nome in sorted(os.listdir(base)):
        if nome.endswith((".html", ".js")) and not nome.startswith("_"):
            yield nome, io.open(os.path.join(base, nome), encoding="utf-8").read()


def test_nenhuma_data_e_formatada_SEM_fuso():
    """🚨 Data formatada sem `timeZone` segue o relógio do navegador. No Brasil
    parece certa; fora dele mente — e o painel passa a discordar de si mesmo."""
    problemas = []
    vistos = 0
    for nome, txt in _htmls_do_site():
        vistos += 1
        for m in _RX_DATA_SEM_FUSO.finditer(txt):
            trecho = m.group(0)
            if "timeZone" in trecho or "fmtBR" in trecho or "fmtDataBR" in trecho:
                continue
            linha = txt[:m.start()].count(chr(10)) + 1
            problemas.append("%s:%d %s" % (nome, linha, " ".join(trecho.split())[:100]))
    assert vistos > 5, "varri só %d arquivo(s) — guarda inerte" % vistos
    assert not problemas, (
        "data/hora formatada sem fuso (segue o relógio do navegador): " +
        " | ".join(problemas))


def test_CONTROLE_dinheiro_nao_e_acusado():
    """🧪 `Number.toLocaleString('pt-BR')` formata dinheiro, não data. Se o
    guarda acusar isso, vira ruído e alguém desliga ele."""
    assert not _RX_DATA_SEM_FUSO.search(
        "total.toLocaleString('pt-BR', {minimumFractionDigits: 2})")
    assert not _RX_DATA_SEM_FUSO.search("(cents/100).toLocaleString('pt-BR')")


def test_CONTROLE_o_guarda_REPROVA_data_sem_fuso():
    """🧪 E pega o padrão que escapou de verdade no admin."""
    ruim = "return new Date(iso).toLocaleDateString('pt-BR',{day:'2-digit'});"
    m = _RX_DATA_SEM_FUSO.search(ruim)
    assert m and "timeZone" not in m.group(0), (
        "o guarda não pega data formatada sem fuso — não guarda nada")


def test_a_lista_de_projetos_mostra_HORA_e_nao_so_data():
    """🕐 01/09 (Pedro): *"quando vejo os projetos no site só tem data, hora
    nunca"*. Sem a hora ele não consegue saber quando o cliente subiu — e foi
    exatamente por isso que ele teve que me perguntar, e eu respondi em UTC."""
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    dash = io.open(os.path.join(base, "dashboard.html"), encoding="utf-8").read()
    i = dash.find("function renderProjectCard")
    assert i > 0, "não achei renderProjectCard — o guarda perdeu o alvo"
    trecho = dash[i:i + 700]
    assert "fmtBR(" in trecho and "hour:" in trecho, (
        "o card do projeto voltou a mostrar só data, sem hora")
