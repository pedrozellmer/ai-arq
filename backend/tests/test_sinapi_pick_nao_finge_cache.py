# -*- coding: utf-8 -*-
"""Ligar prompt caching no `sinapi_pick` seria um conserto que não conserta.

🩸 22/09/2026 — job 1d0751b8 (caderno de apresentação, 35 páginas, 537 itens):
o `sinapi_pick` fez 44 chamadas Haiku com **1.580.446 tokens de entrada** e
`cache_marcado=false`, US$ 1,62 dos US$ 4,10 do job (39,5%). A conclusão óbvia
— "o catálogo é o mesmo em toda chamada, liga o cache" — não sobrevive à
medição:

  • o único trecho que pode virar PREFIXO cacheável é o preâmbulo de instruções
    do `_PICK_PROMPT`: 1.141 chars, ~409 tokens na razão medida em produção
    (2,79 chars/token — ver `_CHARS_POR_TOKEN_MEDIDO`);
  • a chamada média tem 37.324 tokens de entrada → o preâmbulo é **1,2%**;
  • os outros 98,8% são os 60 candidatos SINAPI de cada um dos 12 itens do
    lote — texto novo em toda chamada, porque os itens são outros;
  • a cauda do template (128 chars) também é fixa, mas vem DEPOIS dos itens, e
    cache é casamento de PREFIXO: ela não conta;
  • e ~409 tokens **não cacheiam** no Haiku 4.5, cujo mínimo de prefixo é
    4.096 — nem no Opus 5, cujo mínimo é 512.

Então marcar não renderia 1,2% — renderia ZERO, e ainda gravaria
`cache_marcado=true` na tabela de custo. "Cache ligado, 0% de leitura" é
indistinguível de "a Anthropic está com hit rate ruim": é a investigação de
24/08/2026 de novo, agora com o sintoma apagado por nós mesmos.

Este arquivo é o registro executável desse "não". Ele não proíbe ligar o cache;
ele exige que, quando alguém ligar, o prefixo marcado ALCANCE o mínimo do
modelo — que é a única condição em que ligar deixa de ser um no-op silencioso.

🩸 REVISÃO DO MESMO DIA — a 1ª versão destes guardas tinha três buracos, e os
dois primeiros eram justamente os que o commit existia pra tapar:

  1. o aviso a priori ficava MUDO no único call site de produção que
     PROVADAMENTE tem o marcador ignorado: a prancha de projeto ESTRUTURAL.
     A razão de 2,0 chars/token, escolhida "pra só dizer não com folga",
     estimava 1.350 tok pro SYSTEM_PROMPT_ESTRUTURA (2.701 chars) e o deixava
     passar no mínimo de 1.024 do Sonnet 4.6 — enquanto 20 chamadas reais de
     30 dias vieram com cache_write=0 E cache_read=0. Agora a razão é a MEDIDA
     (2,79), presa por dois testes de âncora, e quem AFIRMA que não houve cache
     é `_registrar_uso`, lendo a resposta — não uma divisão de caracteres;
  2. o atalho que o parâmetro convida a usar — acrescentar `cache_system=True`
     na chamada que manda o prompt inteiro em `messages=` — não marcava nada,
     não avisava nada e ainda gravava `cache_marcado=true`. Agora a telemetria
     grava o que foi FEITO (`prefixo_marcado`), e pedir sem ter o que marcar
     fala alto;
  3. o prefixo marcado num `system` de VÁRIOS blocos não tinha teste: ler só o
     primeiro bloco passava verde.
"""
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import pytest  # noqa: E402

import analyzer  # noqa: E402
import llm_retry  # noqa: E402
import sinapi_matcher  # noqa: E402
from llm_retry import (_AVISO_CACHE_SEM_MARCA, _apply_system_cache,  # noqa: E402
                       _CHARS_POR_TOKEN_MEDIDO, call_with_retry,
                       prefixo_cacheia, prefixo_marcado)

# A string EXATA que o call site manda (sinapi_matcher.py). O sufixo de data faz
# parte do modelo em produção e é justamente o que uma régua ingênua erraria.
_MODELO_DO_PICK = "claude-haiku-4-5-20251001"
_MIN_HAIKU_45 = 4096

# Prefixo que cacheia com FOLGA em qualquer modelo da tabela (4.096 tok é o
# maior mínimo; aqui vão ~7.100 tok estimados). 🪤 Dimensionar o "grande" com a
# régua velha de 2,0 chars/token deixaria este texto ABAIXO do mínimo do Haiku
# assim que a régua passasse a usar a razão medida — controle positivo que vira
# negativo sozinho.
_PREFIXO_FOLGADO = "X" * 20000


# ── Dublês ──────────────────────────────────────────────────────────────────
class _Bloco:
    def __init__(self, texto):
        self.text = texto
        self.type = "text"


class _Uso:
    """Só os contadores que `_registrar_uso` lê."""

    def __init__(self, le=0, esc=0, novo=0, out=0):
        self.cache_read_input_tokens = le
        self.cache_creation_input_tokens = esc
        self.input_tokens = novo
        self.output_tokens = out


class _RespostaFalsa:
    def __init__(self, texto, usage=None):
        self.content = [_Bloco(texto)]
        self.stop_reason = "end_turn"
        self.usage = usage
        self.model = _MODELO_DO_PICK


class _Messages:
    def __init__(self, chamadas, usage=None):
        self._chamadas = chamadas
        self._usage = usage

    # 🪤 `**k` de propósito: parâmetro novo no call site não pode desarmar o
    # guarda em silêncio (feedback_duble_com_assinatura_exata_desarma_calado).
    def create(self, **k):
        self._chamadas.append(k)
        return _RespostaFalsa('[{"i": 0, "codigo": null}]', self._usage)


class _ClienteFalso:
    def __init__(self, chamadas, usage=None):
        self.messages = _Messages(chamadas, usage)


def _capturar_telemetria(monkeypatch):
    """As linhas que IRIAM pro `llm_uso`. 🪤 `**k` de propósito: campo novo em
    `_gravar_uso` não pode desarmar isto calado."""
    linhas = []
    monkeypatch.setattr(llm_retry, "_gravar_uso", lambda **k: linhas.append(k))
    return linhas


def _item(desc, unidade="m²", n_candidatos=3):
    return {"description": desc, "unit": unidade,
            "candidates": [{"codigo": "8%04d" % i,
                            "descricao": "COMPOSICAO DE TESTE %d" % i,
                            "unidade": unidade} for i in range(n_candidatos)]}


def _rodar_o_pick(monkeypatch, itens, batch_size=1):
    """Roda a FUNÇÃO REAL (pick_best_batch + call_with_retry + o marcador de
    cache) e devolve os kwargs que chegaram em `messages.create`."""
    chamadas = []
    monkeypatch.setenv("LLM_CACHE_TELEMETRIA", "0")
    monkeypatch.setattr(sinapi_matcher, "_client",
                        lambda: _ClienteFalso(chamadas))
    sinapi_matcher.pick_best_batch(itens, batch_size=batch_size,
                                   job_id="1d0751b8")
    return chamadas


def _prompt(chamada):
    return chamada["messages"][0]["content"]


def _preambulo(texto):
    """O trecho ANTES dos itens — o único candidato a prefixo cacheável."""
    return texto.split("ITENS:", 1)[0]


def _prefixo_marcado(chamada):
    """O texto que foi marcado como cacheável, ou "" se não houve marcação.

    🪤 Pergunta à régua REAL (`llm_retry.prefixo_marcado`) em vez de reimplementar
    a conta aqui: cópia de régua envelhece separada do original, e o guarda
    passaria a medir a cópia (feedback_nao_reimplemente_a_regua_pergunte_ao_guarda).
    """
    return prefixo_marcado(chamada)


# ── O FATO que decide a frente ──────────────────────────────────────────────
def test_o_trecho_fixo_e_o_MESMO_entre_chamadas(monkeypatch):
    """Metade da tese está certa: o preâmbulo é idêntico byte a byte."""
    chamadas = _rodar_o_pick(monkeypatch, [_item("Piso porcelanato 60x60"),
                                           _item("Spot LED de embutir")])
    assert len(chamadas) == 2, "esperava um lote por item: %d" % len(chamadas)
    a, b = _preambulo(_prompt(chamadas[0])), _preambulo(_prompt(chamadas[1]))
    assert a == b, "o preâmbulo do _PICK_PROMPT mudou entre chamadas"
    assert len(a) > 500, "preâmbulo curto demais pra ser o que medi: %d" % len(a)


def test_e_o_resto_do_prompt_NAO_e(monkeypatch):
    """A outra metade está errada: o corpo é outro em toda chamada, e é ele que
    paga a conta. Sem isto, 'o catálogo é o mesmo' passaria por verdade.

    🪤 O lote aqui tem a FORMA da produção — 12 itens × 60 candidatos, que é o
    que `main.py` manda (`candidates_for(..., limit=60)`, batch_size=12). Com
    itens de brinquedo o preâmbulo vira maioria do prompt e o guarda diria o
    contrário do que acontece com cliente."""
    itens = [_item("Item de teste %d" % i, n_candidatos=60) for i in range(24)]
    chamadas = _rodar_o_pick(monkeypatch, itens, batch_size=12)
    assert len(chamadas) == 2, "esperava 2 lotes de 12: %d" % len(chamadas)
    p0, p1 = _prompt(chamadas[0]), _prompt(chamadas[1])
    assert p0 != p1, "dois lotes diferentes geraram o MESMO prompt"
    fixo = len(_preambulo(p0))
    assert fixo < len(p0) * 0.05, (
        "o trecho fixo deveria ser migalha do prompt; aqui %d de %d chars (%.1f%%)"
        % (fixo, len(p0), 100.0 * fixo / len(p0)))


def test_o_trecho_fixo_NAO_alcanca_o_minimo_do_haiku_45(monkeypatch):
    """1.276 chars (~500 tok) contra um mínimo de 4.096 tok. É por isto que
    ligar o cache aqui não rende 1,2%: rende ZERO."""
    chamadas = _rodar_o_pick(monkeypatch, [_item("Piso porcelanato 60x60")])
    fixo = _preambulo(_prompt(chamadas[0]))
    assert not prefixo_cacheia(_MODELO_DO_PICK, fixo), (
        "o preâmbulo tem %d chars (~%d tok na razão medida) e o mínimo do Haiku "
        "4.5 é %d tok — se esta medida mudou, refaça a conta de custo antes de "
        "ligar o cache"
        % (len(fixo), int(len(fixo) / _CHARS_POR_TOKEN_MEDIDO), _MIN_HAIKU_45))


# ── O GUARDA: ligar o cache aqui exige alcançar o mínimo ────────────────────
def test_se_o_pick_marcar_cache_o_prefixo_tem_que_alcancar_o_minimo(monkeypatch):
    chamadas = _rodar_o_pick(monkeypatch, [_item("Piso porcelanato 60x60"),
                                           _item("Spot LED de embutir")])
    for i, ch in enumerate(chamadas):
        marcado = _prefixo_marcado(ch)
        if not marcado:
            continue
        assert prefixo_cacheia(ch.get("model"), marcado), (
            "chamada %d marcou %d chars como cacheável em %s, e isso não "
            "alcança o mínimo do modelo: a API IGNORA o marcador, o cache_read "
            "fica em 0 e a telemetria grava cache_marcado=true assim mesmo"
            % (i, len(marcado), ch.get("model")))


def test_CONTROLE_o_guarda_acima_REPROVA_um_marcador_curto():
    """Controle positivo: a asserção do guarda tem que FALHAR quando alguém
    marca o preâmbulo curto. Sem isto, o guarda passaria por vacuidade."""
    fixo = sinapi_matcher._PICK_PROMPT.split("ITENS:", 1)[0]
    ch = _apply_system_cache({"model": _MODELO_DO_PICK, "system": fixo})
    marcado = _prefixo_marcado(ch)
    assert marcado, "o _apply_system_cache real não marcou nada — controle inútil"
    assert not prefixo_cacheia(ch["model"], marcado), (
        "o controle positivo virou negativo: o preâmbulo passou a alcançar o "
        "mínimo do Haiku 4.5 e o guarda acima nunca mais reprovaria nada")


def test_CONTROLE_prefixo_grande_no_mesmo_modelo_PASSA():
    ch = _apply_system_cache({"model": _MODELO_DO_PICK,
                              "system": _PREFIXO_FOLGADO})
    assert prefixo_cacheia(ch["model"], _prefixo_marcado(ch))


# ── A régua é do MODELO, não uma constante ──────────────────────────────────
def test_o_preambulo_do_pick_nao_cacheia_em_MODELO_NENHUM():
    """1.141 chars ≈ 409 tok na razão medida — abaixo até do MENOR mínimo que
    existe (512, o do Opus 5). Ligar o cache no `sinapi_pick` não rende 1,2%:
    rende ZERO em qualquer modelo que a gente possa escolher.

    🩸 A 1ª versão deste teste dizia o contrário ("cacheia em quem pede 512") —
    era a razão otimista de 2,0 chars/token falando. Com 2,79 (medido em
    produção, ver `_CHARS_POR_TOKEN_MEDIDO`) o preâmbulo não alcança nada."""
    fixo = sinapi_matcher._PICK_PROMPT.split("ITENS:", 1)[0]
    for modelo in list(llm_retry._MIN_PREFIXO_CACHE_TOK) + ["modelo-que-nao-existe"]:
        assert prefixo_cacheia(modelo, fixo) is False, (
            "o preâmbulo (%d chars) passou a cachear em %s — refaça a conta de "
            "custo antes de ligar o cache no pick" % (len(fixo), modelo))


@pytest.mark.parametrize("modelo,minimo", [
    ("claude-opus-5", 512),
    ("claude-opus-4-8", 1024),
    ("claude-sonnet-5", 1024),
    ("claude-sonnet-4-6", 1024),          # o da leitura de prancha
    ("claude-sonnet-4-5", 1024),
    ("claude-opus-4-7", 2048),
    ("claude-haiku-3-5", 2048),
    ("claude-opus-4-6", 4096),
    ("claude-opus-4-5", 4096),
    ("claude-haiku-4-5", 4096),
    ("claude-haiku-4-5-20251001", 4096),  # sufixo de data do call site real
    ("modelo-que-nao-existe", 512),       # desconhecido cai no MENOR mínimo
])
def test_a_regua_vira_no_minimo_DAQUELE_modelo(modelo, minimo):
    """Cada linha da tabela conferida nos DOIS lados do seu próprio mínimo.

    🪤 Uma parametrização com um texto só de tamanho fixo cobriria umas linhas e
    deixaria outras passando por sorte: trocar 4.096 por 2.048 no Haiku 4.5
    ficaria verde. Aqui cada modelo é testado contra o SEU número, então mexer
    em qualquer célula da tabela reprova."""
    margem = int(200 * _CHARS_POR_TOKEN_MEDIDO)
    folgado = "X" * (int(minimo * _CHARS_POR_TOKEN_MEDIDO) + margem)
    curto = "X" * (int(minimo * _CHARS_POR_TOKEN_MEDIDO) - margem)
    assert prefixo_cacheia(modelo, folgado) is True, (
        "%s: %d chars deveriam alcançar o mínimo de %d tok"
        % (modelo, len(folgado), minimo))
    assert prefixo_cacheia(modelo, curto) is False, (
        "%s: %d chars NÃO deveriam alcançar o mínimo de %d tok"
        % (modelo, len(curto), minimo))


def test_a_regua_do_minimo_e_do_MODELO_nao_uma_constante():
    """O MESMO texto de 3.000 chars (~1.075 tok medidos) cacheia no Sonnet 4.6
    da leitura de prancha (mínimo 1.024) e NÃO cacheia no Haiku 4.5 do
    sinapi_pick (mínimo 4.096). Uma constante única erraria dos dois lados."""
    meio = "X" * 3000
    assert prefixo_cacheia("claude-sonnet-4-6", meio) is True
    assert prefixo_cacheia(_MODELO_DO_PICK, meio) is False


def test_prefixo_vazio_nao_cacheia():
    assert prefixo_cacheia("claude-opus-5", "") is False
    assert prefixo_cacheia(None, "") is False


# ── O aviso que separa "rende pouco" de "nunca existiu" ─────────────────────
def test_marcador_abaixo_do_minimo_AVISA(capsys):
    _apply_system_cache({"model": _MODELO_DO_PICK, "system": "curto demais"})
    saida = capsys.readouterr().out
    assert "NAO alcanca o minimo" in saida, (
        "prefixo abaixo do mínimo saiu calado — é exatamente assim que "
        "'cache ligado, 0%% de leitura' vira um mês de investigação: %r" % saida)


def test_CONTROLE_marcador_suficiente_fica_CALADO(capsys):
    _apply_system_cache({"model": _MODELO_DO_PICK, "system": _PREFIXO_FOLGADO})
    saida = capsys.readouterr().out
    assert "NAO alcanca o minimo" not in saida, (
        "aviso em prefixo que cacheia: alarme que sempre toca ninguém lê. %r"
        % saida)


def test_o_aviso_diz_que_e_ESTIMATIVA_e_de_onde_veio_o_numero(capsys):
    """🚨 Regra nº1 em outra roupa: o texto do aviso nasce de uma DIVISÃO DE
    CARACTERES, não de uma medição da chamada. A 1ª versão afirmava o futuro no
    indicativo ("a API vai IGNORAR o marcador e o cache_read fica em 0") — e o
    log de custo é justamente onde estimativa vestida de fato vira diagnóstico
    errado. Quem afirma é `_registrar_uso`, lendo a resposta."""
    _apply_system_cache({"model": _MODELO_DO_PICK, "system": "curto demais"})
    saida = capsys.readouterr().out
    assert "ESTIMADOS" in saida and "provavelmente" in saida, (
        "o aviso afirma como fato o que é estimativa por caractere: %r" % saida)
    assert "%.2f" % _CHARS_POR_TOKEN_MEDIDO in saida, (
        "o aviso não diz a razão chars/token que usou — sem ela ninguém sabe "
        "refazer a conta: %r" % saida)


def test_o_aviso_nao_derruba_a_marcacao(capsys):
    """Avisar é telemetria. Nunca pode virar decisão de não marcar: o erro pra
    esse lado é dinheiro real, se a tabela de mínimos estiver velha."""
    ch = _apply_system_cache({"model": _MODELO_DO_PICK, "system": "curto"})
    capsys.readouterr()
    assert _prefixo_marcado(ch), "o aviso comeu o marcador"
    assert "prompt-caching" in (ch.get("extra_headers") or {}).get(
        "anthropic-beta", "")


def test_kill_switch_do_cache_continua_valendo(monkeypatch, capsys):
    monkeypatch.setenv("LLM_PROMPT_CACHE", "0")
    ch = _apply_system_cache({"model": _MODELO_DO_PICK, "system": "curto"})
    assert ch.get("system") == "curto", "o kill switch parou de ser no-op"
    assert capsys.readouterr().out == "", "desligado e ainda assim falando"


# ── A régua presa no que PRODUÇÃO mediu, não no que eu achei ────────────────
# 🩸 22/09/2026 — a 1ª versão desta frente calibrou a régua em 2,0 chars/token
# "pra só dizer não com folga", e nenhum teste prendia esse número: baixá-lo pra
# 1,5 deixava os 19 guardas verdes. Pior, o viés comprou o silêncio no ÚNICO
# call site de produção que provadamente tem o marcador ignorado.
#
# As duas âncoras abaixo são fatos de `llm_uso` (30 d, consulta de 22/09/2026
# 18:51 Brasília, `now() at time zone 'America/Sao_Paulo'` de testemunha), e
# prendem a constante entre 2,64 e 17,0 chars/token — quem mexer nela sem
# refazer a medida reprova aqui.
def test_a_razao_chars_por_token_esta_presa_no_QUE_A_API_MEDIU():
    """Âncora de CIMA: o SYSTEM_PROMPT da leitura de prancha de ARQUITETURA tem
    17.399 chars e a API devolveu `cache_creation_input_tokens` = 6.231 em TODAS
    as 64 escritas de 30 dias (`prancha` e `dxf`), sem um único valor diferente.
    17.399 / 6.231 = 2,79 chars/token — e esse prefixo CACHEIA de verdade
    (2.430.090 tokens lidos do cache no período)."""
    assert prefixo_cacheia("claude-sonnet-4-6", analyzer.SYSTEM_PROMPT) is True, (
        "a régua passou a dizer que o SYSTEM_PROMPT de arquitetura não cacheia "
        "— mas a produção mostra 6.231 tok de cache_write e 2,4 mi de "
        "cache_read nele. %d chars" % len(analyzer.SYSTEM_PROMPT))


def test_o_prompt_de_ESTRUTURA_e_a_ancora_DE_BAIXO_e_ele_NAO_cacheia():
    """Âncora de BAIXO, e o achado que derrubou a 1ª versão: o
    SYSTEM_PROMPT_ESTRUTURA tem 2.701 chars e, em 20 chamadas de produção (18
    `prancha` + 2 `dxf`, jobs 0745bfc3 de 11/09, 08ba5752 de 17/09, ee801b82 de
    21/09 e o eval ev03e158), veio SEMPRE com cache_write = 0 E cache_read = 0
    — a API ignorou o marcador, logo ele está abaixo dos 1.024 tok do Sonnet 4.6.

    Com a régua antiga (2,0 chars/token) isto dava 1.350 tok e passava: o aviso
    ficava mudo justamente no caso real. É este teste que prende o número."""
    assert prefixo_cacheia("claude-sonnet-4-6",
                           analyzer.SYSTEM_PROMPT_ESTRUTURA) is False, (
        "a régua diz que o preâmbulo de estrutura (%d chars) cacheia no Sonnet "
        "4.6, mas 20 chamadas de produção vieram com cache_write=0 E "
        "cache_read=0. Se o prompt cresceu, remeça contra a API antes de "
        "afrouxar a régua" % len(analyzer.SYSTEM_PROMPT_ESTRUTURA))


def test_o_caminho_REAL_da_prancha_de_estrutura_AVISA(capsys):
    """O mesmo `system` que o `analyzer` manda em prancha estrutural, pelo
    `_apply_system_cache` real. Antes deste commit o ramo do aviso não tocava
    aqui — e era o único lugar de produção onde ele precisava tocar."""
    _apply_system_cache({"model": "claude-sonnet-4-6",
                         "system": analyzer.SYSTEM_PROMPT_ESTRUTURA})
    assert "NAO alcanca o minimo" in capsys.readouterr().out, (
        "o preâmbulo de estrutura saiu calado — é o caso com 20 chamadas de "
        "produção provando que o marcador foi ignorado")


def test_CONTROLE_o_caminho_de_ARQUITETURA_continua_CALADO(capsys):
    """Controle do outro lado: 427 chamadas de `prancha` de arquitetura cacheiam
    de verdade. Aviso ali seria alarme que sempre toca — ninguém lê."""
    _apply_system_cache({"model": "claude-sonnet-4-6",
                         "system": analyzer.SYSTEM_PROMPT})
    assert "NAO alcanca o minimo" not in capsys.readouterr().out


# ── O FATO: a resposta diz se houve cache, e ela não é estimativa ───────────
def _registrar(usage, marcado, capsys, tag="prancha"):
    llm_retry._registrar_uso(tag, _RespostaFalsa("x", usage), marcado,
                             model="claude-sonnet-4-6", job_id="0745bfc3")
    return capsys.readouterr().out


def test_marcador_que_a_API_IGNOROU_sai_do_silencio(capsys):
    """🩸 O caso real: marcamos, e a resposta veio com cache_creation=0 E
    cache_read=0. Sem esta linha, `cache_marcado=true` com 0% de leitura é
    indistinguível de "a Anthropic está com hit rate ruim" — a investigação de
    24/08/2026 de novo, com o sintoma apagado por nós.

    🔑 Este guarda lê a RESPOSTA; a régua de chars não é consultada aqui. É por
    isso que ele pega o caso que a régua deixou passar por 11 dias."""
    saida = _registrar(_Uso(le=0, esc=0, novo=9212), True, capsys)
    assert "MARCADOR IGNORADO" in saida, (
        "cache marcado, zero criado e zero lido, e o log não disse nada: %r"
        % saida)


@pytest.mark.parametrize("rotulo,usage", [
    ("primeira chamada: escreveu o cache", _Uso(le=0, esc=6231, novo=3000)),
    ("chamadas seguintes: leu o cache", _Uso(le=6231, esc=0, novo=3000)),
    ("leu e escreveu", _Uso(le=6231, esc=6231, novo=3000)),
])
def test_CONTROLE_cache_que_FUNCIONOU_nao_vira_alarme(capsys, rotulo, usage):
    """Sem isto o guarda acima poderia virar "avisa sempre", e alarme que sempre
    toca ninguém lê. Os três formatos de cache que funciona ficam calados."""
    saida = _registrar(usage, True, capsys)
    assert "MARCADOR IGNORADO" not in saida, "[%s] %r" % (rotulo, saida)


def test_CONTROLE_chamada_sem_marcacao_nao_e_acusada(capsys):
    """O `sinapi_pick` roda com cache NÃO marcado e cache_read=0 o tempo todo —
    913 chamadas em 30 d. Acusar isso seria 913 alarmes por nada."""
    saida = _registrar(_Uso(le=0, esc=0, novo=37324), False, capsys, tag="sinapi_pick")
    assert "MARCADOR IGNORADO" not in saida, saida


# ── PEDIR cache ≠ FAZER cache ──────────────────────────────────────────────
# 🪤 22/09/2026 — `cache_system=True` lê como "liga o cache aqui", mas
# `_apply_system_cache` só sabe marcar o que está em `system=`. O caminho mais
# curto pra "ligar o cache no pick" — acrescentar o parâmetro na chamada que
# manda o prompt inteiro em `messages=` — não marcava NADA, não avisava NADA, e
# ainda gravava `cache_marcado=true` na tabela de custo.
def _chamar(monkeypatch, capsys, usage=None, **kw):
    """Roda `call_with_retry` de verdade e devolve (linhas_de_telemetria, saída)."""
    linhas = _capturar_telemetria(monkeypatch)
    cli = _ClienteFalso([], usage=usage or _Uso(le=0, esc=0, novo=5000, out=10))
    call_with_retry(cli, tag="sinapi_pick", job_id="1d0751b8",
                    model=_MODELO_DO_PICK, max_tokens=100,
                    messages=[{"role": "user", "content": "x" * 5000}], **kw)
    return linhas, capsys.readouterr().out


def test_pedir_cache_sem_system_NAO_grava_que_marcou(monkeypatch, capsys):
    linhas, saida = _chamar(monkeypatch, capsys, cache_system=True)
    assert linhas, "nenhuma linha de telemetria"
    assert linhas[-1]["cache_marcado"] is False, (
        "gravou cache_marcado=true numa chamada em que NADA foi marcado: os "
        "tokens foram cheios e a conta de custo passa a dizer 'cache ligado, "
        "0%% de leitura', que é a investigação errada. Linha: %s" % (linhas[-1],))
    assert _AVISO_CACHE_SEM_MARCA in saida, (
        "pedir cache e não marcar nada saiu calado: %r" % saida)


def test_CONTROLE_pedir_cache_COM_system_grava_que_marcou(monkeypatch, capsys):
    """Controle positivo do caminho comum: quando há `system` de sobra, a marca
    acontece, a telemetria diz `true` e ninguém é avisado de nada."""
    linhas, saida = _chamar(monkeypatch, capsys, cache_system=True,
                            system=_PREFIXO_FOLGADO,
                            usage=_Uso(le=6231, esc=0, novo=5000, out=10))
    assert linhas[-1]["cache_marcado"] is True, linhas[-1]
    assert _AVISO_CACHE_SEM_MARCA not in saida, saida


def test_CONTROLE_sem_pedir_cache_grava_false_e_fica_calado(monkeypatch, capsys):
    """O `sinapi_pick` de hoje: não pede cache, não marca, não avisa."""
    linhas, saida = _chamar(monkeypatch, capsys)
    assert linhas[-1]["cache_marcado"] is False, linhas[-1]
    assert _AVISO_CACHE_SEM_MARCA not in saida, saida


def test_prefixo_marcado_so_conta_o_que_tem_cache_control():
    """🪤 "Tem `system` em lista" não é "foi marcado". Um payload que já chega
    dividido em blocos continua uma lista mesmo quando ninguém marcou nada — e
    é assim que o kill switch devolve o que recebeu. Sem esta distinção, a
    telemetria volta a gravar o PEDIDO no lugar do FEITO."""
    assert prefixo_marcado({"system": [{"type": "text", "text": "abc"}]}) == "", (
        "bloco sem cache_control contou como marcado")
    assert prefixo_marcado({"system": [
        {"type": "text", "text": "abc",
         "cache_control": {"type": "ephemeral"}}]}) == "abc"
    assert prefixo_marcado({"system": "abc"}) == "", "string crua não é marcação"
    assert prefixo_marcado({}) == ""


def test_kill_switch_com_system_JA_EM_BLOCOS_tambem_nao_mente(monkeypatch, capsys):
    """O mesmo kill switch, mas com o `system` que já chega dividido em blocos:
    a lista sobrevive intacta e ninguém marcou nada. A telemetria tem que
    gravar `false` — dizer `true` aqui inventaria economia que não houve."""
    monkeypatch.setenv("LLM_PROMPT_CACHE", "0")
    linhas, _ = _chamar(monkeypatch, capsys, cache_system=True,
                        system=[{"type": "text", "text": _PREFIXO_FOLGADO}],
                        usage=_Uso(le=0, esc=0, novo=5000, out=10))
    assert linhas[-1]["cache_marcado"] is False, (
        "kill switch ligado, `system` em blocos e nenhum cache_control — e a "
        "telemetria disse que marcou: %s" % (linhas[-1],))


def test_CONTROLE_o_MESMO_system_em_blocos_com_o_cache_ligado_marca(monkeypatch, capsys):
    """Controle do outro lado do teste acima: sem o kill switch, a MESMA lista
    de blocos é marcada e a telemetria diz `true`."""
    linhas, _ = _chamar(monkeypatch, capsys, cache_system=True,
                        system=[{"type": "text", "text": _PREFIXO_FOLGADO}],
                        usage=_Uso(le=6231, esc=0, novo=5000, out=10))
    assert linhas[-1]["cache_marcado"] is True, linhas[-1]


def test_kill_switch_desliga_sem_virar_alarme_e_sem_mentir(monkeypatch, capsys):
    """Com `LLM_PROMPT_CACHE=0` nada é marcado DE PROPÓSITO: não é defeito, não
    vira aviso — mas a telemetria também não pode dizer que marcou."""
    monkeypatch.setenv("LLM_PROMPT_CACHE", "0")
    linhas, saida = _chamar(monkeypatch, capsys, cache_system=True,
                            system=_PREFIXO_FOLGADO,
                            usage=_Uso(le=0, esc=0, novo=5000, out=10))
    assert _AVISO_CACHE_SEM_MARCA not in saida, (
        "kill switch ligado virou alarme por chamada: %r" % saida)
    assert linhas[-1]["cache_marcado"] is False, (
        "kill switch ligado e a telemetria ainda diz que marcou: %s" % (linhas[-1],))


def test_o_pick_de_hoje_nao_pede_cache_que_nao_tem_como_marcar(monkeypatch, capsys):
    """O guarda na FUNÇÃO REAL: se alguém acrescentar `cache_system=True` na
    chamada do `pick_best_batch` sem mover o preâmbulo pro `system=`, este teste
    reprova — era a mutação que passava pelos 19 guardas da 1ª versão."""
    _rodar_o_pick(monkeypatch, [_item("Piso porcelanato 60x60")])
    saida = capsys.readouterr().out
    assert _AVISO_CACHE_SEM_MARCA not in saida, (
        "o pick pede prompt caching e não tem `system` pra marcar: não economiza "
        "um token e ainda confunde a conta de custo. %r" % saida)


# ── O prefixo marcado é a SOMA dos blocos, não o primeiro ──────────────────
def test_system_de_DOIS_blocos_soma_os_dois_no_prefixo(capsys):
    """🪤 Hoje os dois call sites mandam `system` como string, mas dividir o
    prompt em blocos é justamente o que se faz pra pôr o breakpoint no lugar
    certo — o próximo passo natural de quem for ligar o cache. Ler só o primeiro
    bloco faria o aviso tocar num prefixo que cacheia."""
    blocos = [{"type": "text", "text": "instruções curtas do começo"},
              {"type": "text", "text": _PREFIXO_FOLGADO}]
    ch = _apply_system_cache({"model": _MODELO_DO_PICK, "system": blocos})
    saida = capsys.readouterr().out
    assert _prefixo_marcado(ch) == "instruções curtas do começo" + _PREFIXO_FOLGADO, (
        "o prefixo marcado não é a junção dos blocos até o breakpoint")
    assert "NAO alcanca o minimo" not in saida, (
        "somando os dois blocos o prefixo cacheia, e mesmo assim avisou — sinal "
        "de que a conta olhou só um bloco: %r" % saida)


def test_CONTROLE_dois_blocos_curtos_AVISAM(capsys):
    """O simétrico: somados, os dois continuam curtos, e aí o aviso tem que
    tocar. Sem este controle, o teste acima passaria com um aviso morto."""
    blocos = [{"type": "text", "text": "a" * 100},
              {"type": "text", "text": "b" * 100}]
    _apply_system_cache({"model": _MODELO_DO_PICK, "system": blocos})
    assert "NAO alcanca o minimo" in capsys.readouterr().out
