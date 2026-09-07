# -*- coding: utf-8 -*-
"""A telemetria do prompt caching não pode derrubar uma extração.

🚨 24/08/2026: a Anthropic avisou de novo que o cache hit rate está baixo. O
caching foi ligado em 23/07 e conferido com DUAS chamadas manuais naquele dia —
e nunca mais foi medido. Não havia nada no backend lendo `response.usage`, então
não dava pra confirmar nem refutar o aviso pelo nosso lado.

Este arquivo guarda duas coisas: que a medição acontece, e que ela é INÓCUA —
telemetria que quebra o caminho da planilha é pior que telemetria nenhuma.
"""
import io
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import pytest  # noqa: E402

import llm_retry  # noqa: E402
from llm_retry import _registrar_uso  # noqa: E402


def _capturar_gravacoes(monkeypatch):
    linhas = []
    monkeypatch.setattr(llm_retry, "_gravar_uso", lambda **kw: linhas.append(kw))
    return linhas


class _Uso:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class _Resp:
    def __init__(self, usage):
        self.usage = usage


def test_mede_e_nao_levanta(capsys):
    _registrar_uso("dxf:teste", _Resp(_Uso(
        cache_read_input_tokens=4800, cache_creation_input_tokens=0,
        input_tokens=95000, output_tokens=3000)), True)
    saida = capsys.readouterr().out
    assert "cache_read=4800" in saida
    assert "total_in=99800" in saida
    assert "4.8%" in saida, (
        "a porcentagem é o número que interessa — é ela que responde ao e-mail "
        "da Anthropic. Saiu: " + saida)


def test_resposta_sem_usage_nao_quebra():
    """Alguns caminhos devolvem objeto sem `usage`. Não pode explodir."""
    _registrar_uso("x", _Resp(None), True)
    _registrar_uso("x", object(), True)
    _registrar_uso("x", None, False)


def test_campos_ausentes_ou_lixo_nao_quebram():
    _registrar_uso("x", _Resp(_Uso()), True)
    _registrar_uso("x", _Resp(_Uso(cache_read_input_tokens=None,
                                   input_tokens="abc")), True)


@pytest.mark.parametrize("rotulo,usage", [
    # o caso que o guarda já tinha: os três contadores de ENTRADA em zero
    ("tudo zero", dict(cache_read_input_tokens=0, cache_creation_input_tokens=0,
                       input_tokens=0)),
    # 🩸 07/09 — a dimensão que faltava. `_tot` só soma ENTRADA; uma resposta que
    # gerou saída e não reportou entrada nenhuma continua sendo "não sei quanto
    # custou". Sem este caso, `_tot = _le + _esc + _novo + _out` (uma linha só de
    # mutação) faz a linha virar `resultado='api'` com ZERO token de entrada:
    # a tabela de custo ganha uma chamada de API que custou nada, que é
    # exatamente a mentira que esta telemetria existe pra não contar.
    ("zero na entrada, com saída", dict(cache_read_input_tokens=0,
                                        cache_creation_input_tokens=0,
                                        input_tokens=0, output_tokens=3000)),
    # e o `usage` que nem traz os contadores de entrada — só a saída
    ("sem contador de entrada", dict(output_tokens=512)),
])
def test_tudo_zero_nao_loga_divisao_por_zero(capsys, monkeypatch, rotulo, usage):
    """🪤 06/09/2026 — este guarda só olhava a AUSÊNCIA de um print, e ausência
    de print é o que acontece dos dois lados.

    Mutação que passava por ele: `if _tot <= 0:` → `if _tot < 0:`. Com tudo
    zerado a linha deixa de ser classificada como `usage_zerado`, é gravada
    como **`resultado='api'` com 0 tokens** e logo depois o `100.0 * 0 / 0`
    estoura uma ZeroDivisionError que o `except` geral engole. O print some
    (guarda velho: verde) e a tabela de custo passa a ter chamadas "de API"
    que custaram zero — que é exatamente a mentira que a telemetria existe
    pra não contar ("não sei quanto custou" ≠ "custou zero").

    🪤 07/09 (cético): o fixture cobria só o zero TOTAL — nem `output_tokens`
    ele passava. Qualquer afrouxamento numa dimensão ausente do fixture voltava
    a produzir linha "de API" que custou zero. Agora as três formas de "sem
    entrada medida" passam pelo mesmo guarda, e a linha gravada é conferida
    contador por contador (nenhum pode sair carimbado com zero).
    """
    linhas = _capturar_gravacoes(monkeypatch)
    _registrar_uso("x", _Resp(_Uso(**usage)), True,
                   model="claude-haiku-4-5-20251001", job_id="job-zero")

    assert "llm_cache" not in capsys.readouterr().out
    assert len(linhas) == 1, (
        "usage zerado tinha que deixar UMA linha (vazio não é falhou): %s"
        % (linhas,))
    assert linhas[0]["resultado"] == "sem_usage", (
        "[%s] gravou resultado=%r sem entrada medida — a trava do zero caiu e "
        "a tabela de custo ganhou uma chamada de API que custou nada"
        % (rotulo, linhas[0]["resultado"]))
    assert linhas[0]["erro"] == "usage_zerado", linhas[0]
    # nenhum dos quatro contadores pode ir carimbado: 0 medido e 0 desconhecido
    # são coisas diferentes, e é a diferença que esta linha existe pra guardar.
    for campo in ("novo", "le", "esc", "out"):
        assert linhas[0].get(campo) is None, (
            "[%s] carimbou %s=%r como se fosse medida: %s"
            % (rotulo, campo, linhas[0].get(campo), linhas[0]))
    assert linhas[0]["job_id"] == "job-zero"


@pytest.mark.parametrize("le,esc,novo,out", [
    (4800, 0, 95000, 3000),      # o caso cheio, que já existia
    (4800, 0, 0, 0),             # só leitura de cache: a chamada mais barata
    (0, 7300, 0, 0),             # só escrita de cache
    (0, 0, 95000, 0),            # cache frio: só input novo
    (0, 0, 1, 0),                # um token só JÁ é uma chamada cobrada
])
def test_CONTROLE_usage_de_verdade_grava_resultado_api(monkeypatch, le, esc, novo, out):
    """Controle do outro lado: com token de entrada de verdade, a linha É 'api'
    e leva os quatro contadores. Sem isto, o guarda acima passaria por um
    `_registrar_uso` que gravasse 'sem_usage' pra tudo.

    🪤 07/09 (cético): o controle só tinha o caso com os QUATRO contadores
    cheios, então não via o meio-termo. Apertar a trava (`if _tot <= 0` →
    `if _tot < 5000`, ou exigir os três contadores juntos) calava as chamadas
    baratas — justamente as que o prompt caching produz quando ele funciona,
    que é o número que a gente foi medir.
    """
    linhas = _capturar_gravacoes(monkeypatch)
    _registrar_uso("dxf:teste", _Resp(_Uso(
        cache_read_input_tokens=le, cache_creation_input_tokens=esc,
        input_tokens=novo, output_tokens=out)), True,
        model="claude-haiku-4-5-20251001", job_id="job-cheio")
    assert len(linhas) == 1 and linhas[0]["resultado"] == "api", (
        "entrada de %d token(s) virou %r — chamada cobrada saiu da tabela de "
        "custo" % (le + esc + novo, linhas))
    assert (linhas[0]["le"], linhas[0]["esc"], linhas[0]["novo"],
            linhas[0]["out"]) == (le, esc, novo, out), linhas[0]

def test_kill_switch(capsys, monkeypatch):
    """Telemetria tem que ter como ser desligada sem deploy."""
    monkeypatch.setenv("LLM_CACHE_TELEMETRIA", "0")
    _registrar_uso("x", _Resp(_Uso(cache_read_input_tokens=10,
                                   input_tokens=10)), True)
    assert capsys.readouterr().out == ""


def test_os_dois_wrappers_medem():
    """🪤 06/09/2026 — este guarda estava preso à FORMA, não ao FATO.

    Ele contava a string exata `_registrar_uso(tag, _resp, cache_system)`. Ao
    acrescentar `model=` e `job_id=` na chamada (pra saber QUANTO custou e DE
    QUEM foi o gasto), o texto mudou e o guarda reprovou uma mudança correta —
    enquanto continuaria VERDE se alguém apagasse a medição e deixasse a linha
    escrita em outro formato. Agora ele ancora no fato: cada wrapper mede, e
    mede passando modelo e dono.
    """
    src = io.open(os.path.join(_BACKEND, "llm_retry.py"), encoding="utf-8").read()
    for wrapper in ("def call_with_retry(", "def call_with_retry_stream("):
        i = src.index(wrapper)
        fim = src.index("\ndef ", i + 10) if "\ndef " in src[i + 10:] else len(src)
        corpo = src[i:fim]
        assert "_registrar_uso(" in corpo, (
            "%s não mede — a extração de prancha usa o stream, e é ela que "
            "domina o gasto" % wrapper)
        assert "model=" in corpo and "job_id=" in corpo, (
            "%s mede sem dizer o modelo e o dono: sem modelo o token não vira "
            "real, sem dono não dá pra dividir por projeto" % wrapper)


def test_CONTROLE_o_guarda_dos_wrappers_REPROVA_quem_nao_mede():
    """O teste acima só vale se souber acusar a ausência da medição."""
    falso = ('def call_with_retry(client, **kw):\n'
             '    return client.messages.create(**kw)\n'
             'def call_with_retry_stream(client, **kw):\n'
             '    return None\n')
    i = falso.index("def call_with_retry(")
    fim = falso.index("\ndef ", i + 10)
    assert "_registrar_uso(" not in falso[i:fim], (
        "o recorte por wrapper parou de isolar o corpo da função")


def test_o_log_nao_entope_o_painel_de_erros():
    """🪤 Uma linha por chamada de IA. Ontem o painel 'Erros do motor' tinha 20
    das 40 linhas ocupadas por bookkeeping; isto aqui repetiria o problema."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("_STAGES_DIAGNOSTICO = frozenset({")
    bloco = src[i:src.index("})", i)]
    assert '"llm:cache"' in bloco, (
        "o stage llm:cache não está na lista de diagnóstico — vai empurrar erro "
        "de verdade pra fora do painel")
