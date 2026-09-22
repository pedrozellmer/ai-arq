# -*- coding: utf-8 -*-
"""Ligar prompt caching no `sinapi_pick` seria um conserto que não conserta.

🩸 22/09/2026 — job 1d0751b8 (caderno de apresentação, 35 páginas, 537 itens):
o `sinapi_pick` fez 44 chamadas Haiku com **1.580.446 tokens de entrada** e
`cache_marcado=false`, US$ 1,62 dos US$ 4,10 do job (39,5%). A conclusão óbvia
— "o catálogo é o mesmo em toda chamada, liga o cache" — não sobrevive à
medição:

  • o único trecho que pode virar PREFIXO cacheável é o preâmbulo de instruções
    do `_PICK_PROMPT`: 1.141 chars, ~450 tokens;
  • a chamada média tem 37.324 tokens de entrada → o preâmbulo é **1,2%**;
  • os outros 98,8% são os 60 candidatos SINAPI de cada um dos 12 itens do
    lote — texto novo em toda chamada, porque os itens são outros;
  • a cauda do template (128 chars) também é fixa, mas vem DEPOIS dos itens, e
    cache é casamento de PREFIXO: ela não conta;
  • e 450 tokens **não cacheiam** no Haiku 4.5, cujo mínimo de prefixo é 4.096.

Então marcar não renderia 1,2% — renderia ZERO, e ainda gravaria
`cache_marcado=true` na tabela de custo. "Cache ligado, 0% de leitura" é
indistinguível de "a Anthropic está com hit rate ruim": é a investigação de
24/08/2026 de novo, agora com o sintoma apagado por nós mesmos.

Este arquivo é o registro executável desse "não". Ele não proíbe ligar o cache;
ele exige que, quando alguém ligar, o prefixo marcado ALCANCE o mínimo do
modelo — que é a única condição em que ligar deixa de ser um no-op silencioso.
"""
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import pytest  # noqa: E402

import sinapi_matcher  # noqa: E402
from llm_retry import _apply_system_cache, prefixo_cacheia  # noqa: E402

# A string EXATA que o call site manda (sinapi_matcher.py). O sufixo de data faz
# parte do modelo em produção e é justamente o que uma régua ingênua erraria.
_MODELO_DO_PICK = "claude-haiku-4-5-20251001"
_MIN_HAIKU_45 = 4096


# ── Dublês ──────────────────────────────────────────────────────────────────
class _Bloco:
    def __init__(self, texto):
        self.text = texto
        self.type = "text"


class _RespostaFalsa:
    def __init__(self, texto):
        self.content = [_Bloco(texto)]
        self.stop_reason = "end_turn"
        self.usage = None
        self.model = _MODELO_DO_PICK


class _Messages:
    def __init__(self, chamadas):
        self._chamadas = chamadas

    # 🪤 `**k` de propósito: parâmetro novo no call site não pode desarmar o
    # guarda em silêncio (feedback_duble_com_assinatura_exata_desarma_calado).
    def create(self, **k):
        self._chamadas.append(k)
        return _RespostaFalsa('[{"i": 0, "codigo": null}]')


class _ClienteFalso:
    def __init__(self, chamadas):
        self.messages = _Messages(chamadas)


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
    """O texto que foi marcado como cacheável, ou "" se não houve marcação."""
    sysv = chamada.get("system")
    if not isinstance(sysv, list):
        return ""
    if not any(isinstance(b, dict) and b.get("cache_control") for b in sysv):
        return ""
    return "".join(b.get("text") or "" for b in sysv if isinstance(b, dict))


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
        "o preâmbulo tem %d chars (~%d tok no cenário mais otimista) e o mínimo "
        "do Haiku 4.5 é %d tok — se esta medida mudou, refaça a conta de custo "
        "antes de ligar o cache" % (len(fixo), len(fixo) // 2, _MIN_HAIKU_45))


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
    grande = "X" * (_MIN_HAIKU_45 * 2)
    ch = _apply_system_cache({"model": _MODELO_DO_PICK, "system": grande})
    assert prefixo_cacheia(ch["model"], _prefixo_marcado(ch))


# ── A régua é do MODELO, não uma constante ──────────────────────────────────
@pytest.mark.parametrize("modelo,esperado", [
    ("claude-haiku-4-5-20251001", False),   # mínimo 4.096 — o do sinapi_pick
    ("claude-haiku-4-5", False),
    ("claude-opus-4-6", False),             # 4.096 também
    ("claude-opus-4-7", False),             # 2.048
    ("claude-sonnet-4-6", False),           # 1.024 — nem lá o preâmbulo passa
    ("claude-opus-5", True),                # 512
    ("modelo-que-nao-existe", True),        # desconhecido cai no MENOR mínimo
])
def test_o_preambulo_so_cacheia_nos_modelos_de_minimo_512(modelo, esperado):
    """~450 tokens só alcançam o mínimo de quem pede 512. O sufixo de data do
    modelo de produção não pode enganar a régua."""
    fixo = sinapi_matcher._PICK_PROMPT.split("ITENS:", 1)[0]
    assert prefixo_cacheia(modelo, fixo) is esperado, (
        "%s com %d chars: esperava %s" % (modelo, len(fixo), esperado))


def test_a_regua_do_minimo_e_do_MODELO_nao_uma_constante():
    """O MESMO texto de 3.000 chars (~1.500 tok no melhor caso) cacheia no
    Sonnet 4.6 da leitura de prancha (mínimo 1.024) e NÃO cacheia no Haiku 4.5
    do sinapi_pick (mínimo 4.096). Uma constante única erraria dos dois lados."""
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
    _apply_system_cache({"model": _MODELO_DO_PICK,
                         "system": "X" * (_MIN_HAIKU_45 * 2)})
    saida = capsys.readouterr().out
    assert "NAO alcanca o minimo" not in saida, (
        "aviso em prefixo que cacheia: alarme que sempre toca ninguém lê. %r"
        % saida)


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
