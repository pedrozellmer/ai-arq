# -*- coding: utf-8 -*-
"""A prancha sumia da planilha e o log dizia que não tinha perdido nada.

🚨 26/08/2026, caso Amanda (job 43a799c0, "Harmonia - 9º Pavimentos"). De 4
pranchas, 1 chegou. Duas devolveram ZERO item com `stop=max_tokens`, e a linha
de log era `itens=0 perdidos=0` — ou seja, o motor afirmava não ter perdido
nada enquanto entregava metade do projeto a menos.

O que a IA estava escrevendo (ninguém tinha aberto o texto até hoje):

    RACIOCÍNIO: Passo 1 — Inventário de layers: … [15 mil chars corretos]
    +1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1+1
    [até esgotar os 32.000 tokens — nunca emite o JSON]

Ela soma bloco a bloco porque o conversor dá um nome por INSTÂNCIA (1.570 nomes
para 1.570 peças), e `temperature=0` — decodificação gulosa — não deixa escapar.

🔑 DOIS SINAIS, porque um só engana:
  1. DENSIDADE. "+1" é UM token de dois caracteres, então a resposta fica com
     ~1,05 caractere por token contra 2,5-3,0 de texto normal.
     Medido nos textos reais: laço 1,03/1,05/1,06/1,08 | normal 2,46/2,47/2,53.
  2. REPETIÇÃO LITERAL no fim do texto, que é onde o laço mora.

🪤 Densidade sozinha não basta (resposta cheia de número também tokeniza denso)
e repetição sozinha também não (lista JSON repete estrutura por natureza).

🪤 E a prancha 04 repetia "+2", não "+1". Um detector que procurasse a string
literal "+1+1+1" perderia metade dos casos reais. Foi a densidade que salvou.

Este guarda NÃO testa se o laço foi consertado — testa se ele fica VISÍVEL.
O defeito viveu desde 24/08 porque era invisível.
"""
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from engine_rules import detectar_laco_repeticao   # noqa: E402


def _resposta_com_laco(padrao="+1", cabeca=15000, repeticoes=1500):
    """Imita a resposta real: raciocínio válido e depois o laço."""
    return ("RACIOCÍNIO:\nPasso 1 — Inventário de layers:\n"
            + ("- A-WALL: comprimentos — 737.99 m — paredes\n" * (cabeca // 45))
            + padrao * repeticoes)


def _resposta_normal(n=400):
    linhas = []
    for i in range(n):
        linhas.append('{"item_num":"%d","description":"Alvenaria de vedação em '
                      'bloco cerâmico %d×19×19 cm com reboco","unit":"m2",'
                      '"quantity":%.2f,"confidence":"estimado"}' % (i, 9 + i % 5, 12.5 + i))
    return '{"items":[' + ",".join(linhas) + "]}"


def test_pega_o_laco_que_custou_as_pranchas_da_Amanda():
    t = _resposta_com_laco("+1")
    d = detectar_laco_repeticao(t, tokens_saida=32000)
    assert d["laco"] is True, (
        "o laço que custou 2 pranchas da Amanda passaria despercebido: %s" % d)
    assert d["repeticoes"] >= 60, d
    assert d["densidade"] <= 1.8, d


def test_pega_padrao_DIFERENTE_de_mais_um():
    """🪤 A prancha 04 dela repetia '+2'. Detector ancorado em '+1' perderia."""
    d = detectar_laco_repeticao(_resposta_com_laco("+2"), tokens_saida=32000)
    assert d["laco"] is True, "só pegou o '+1' — o caso real da prancha 04 escapa"


def test_resposta_NORMAL_nao_e_acusada():
    """Controle negativo. Lista JSON repete estrutura por natureza — se isso
    acusar, o alarme toca em todo job e vira ruído que ninguém lê."""
    t = _resposta_normal()
    d = detectar_laco_repeticao(t, tokens_saida=int(len(t) / 2.6))
    assert d["laco"] is False, (
        "acusou resposta legítima de 400 itens: %s" % d)


def test_resposta_curta_nao_e_avaliada():
    """Texto curto não dá pra julgar — e julgar dá falso positivo."""
    assert detectar_laco_repeticao("+1" * 50, tokens_saida=100)["laco"] is False


def test_densidade_sozinha_NAO_condena():
    """🪤 Resposta densa em número (coordenada, código) sem repetição não é laço."""
    import random
    random.seed(7)
    denso = " ".join("%d.%d" % (random.randint(1000, 9999), random.randint(10, 99))
                     for _ in range(4000))
    d = detectar_laco_repeticao(denso, tokens_saida=int(len(denso) / 1.2))
    assert d["laco"] is False, (
        "texto denso mas SEM repetição foi acusado — exigir os dois sinais é "
        "o que separa: %s" % d)


def test_a_ROTA_registra_o_laco_no_log():
    """🪤 Guarda que só testa a função não vê o CALL SITE.

    Sem a chamada em main.py o detector existe e nunca roda — que é
    exatamente o estado em que `_resgatar_dxf_gigante` ficou por semanas.
    Lê o corpo sem comentários (comentário já me enganou 3 vezes num dia).
    """
    import io as _io
    fonte = _io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    linhas = [l for l in fonte.split(chr(10)) if not l.strip().startswith("#")]
    corpo = chr(10).join(linhas)
    assert "_detectar_laco(text" in corpo, (
        "o detector não é chamado no caminho da extração — existe e nunca roda")
    assert '"motor:laco-repeticao"' in corpo, (
        "o laço é detectado e não vira linha no log — continua invisível")
    i_det = corpo.find("_detectar_laco(text")
    i_log = corpo.find('"motor:laco-repeticao"')
    assert i_det < i_log, "detecta depois de registrar?"


def test_controle_positivo_o_detector_ANTIGO_nao_via_nada():
    """Prova que o guarda reprova mesmo: antes, o único sinal era o stop_reason,
    e ele não distingue 'cortou no fim' de 'queimou tudo em laço'."""
    from engine_rules import response_truncated
    assert response_truncated("max_tokens") is True
    # ...mas isso vale IGUAL pra uma leitura boa que só encostou no teto:
    # em 24/08 três pranchas deram stop=max_tokens e entregaram 112, 156 e 162
    # itens. Ou seja, o sinal antigo não separava os dois casos.
    boa = _resposta_normal(600)
    assert detectar_laco_repeticao(boa, tokens_saida=int(len(boa) / 2.6))["laco"] is False, (
        "controle positivo furado: o detector novo tem que distinguir "
        "'cortou no teto entregando itens' de 'queimou tudo em laço'")
