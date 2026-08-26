# -*- coding: utf-8 -*-
"""O aprendizado da revisão gravava SUCESSO como ERRO.

🚨 26/08/2026. A Cassia é a cliente que mais revisou no produto: **28 itens
tocados, 8 correções de verdade e 3 planilhas revisadas devolvidas** — sozinha,
num dia. O job dela aparecia no painel com **"3 erros"**, e os três eram:

    11:13  error  motor:revisao-aprendizado  "automatico (sem clique) gerou_linha=True"
    11:19  error  motor:revisao-aprendizado  "gerou_linha=True"
    11:20  error  motor:revisao-aprendizado  "automatico (sem clique) gerou_linha=True"

`gerou_linha=True` é o motor **aprendendo** com a revisão dela. Era o melhor que
aconteceu no produto naquele dia, gravado como falha.

🔑 E o estrago não é cosmético: no mesmo stage, em 30 dias, **12 linhas dizem
sucesso e 11 dizem falha — todas com o mesmo rótulo**. Quem olhasse o painel não
tinha como separar. Uma falha real do aprendizado (que é a resposta pra "por que
`revision_feedback` não enche") ficava indistinguível de uma revisão bem
sucedida.

🪤 **Por isso NÃO dá pra pôr o stage em `_STAGES_DIAGNOSTICO`** — a lista rebaixa
o stage inteiro pra `info` e esconderia as 11 falhas junto com os 12 sucessos.
A severidade tem que seguir o DESFECHO.

📌 Contexto: até 23/08 quase todo o log do motor saía como `error`
(`motor:unidade` 166 linhas, `motor:consenso-area` 135, `motor:geometria` 115 —
todas informativas). Isso foi consertado com a lista de diagnóstico. Este stage
foi o que sobrou, porque ele é o único que mistura os dois desfechos.
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
_CORPO = chr(10).join(l for l in _FONTE.split(chr(10))
                      if not l.strip().startswith("#"))


def _chamadas_de_sucesso():
    """As três chamadas que registram `gerou_linha=` (as de exceção têm texto
    próprio: FALHOU / NAO INICIOU)."""
    achados = []
    for m in re.finditer(r'_log_error\(\s*"motor:revisao-aprendizado",'
                         r'(.{0,320}?)\)\s*$', _CORPO, re.M | re.S):
        trecho = m.group(1)
        if "gerou_linha=" in trecho:
            achados.append(trecho)
    return achados


def test_as_tres_chamadas_de_desfecho_existem():
    """Se o número mudar, o guarda precisa ser revisto de propósito."""
    achados = _chamadas_de_sucesso()
    assert len(achados) == 3, (
        "esperava 3 chamadas com `gerou_linha=` (automática, manual do admin e "
        "esteira); achei %d. Se nasceu uma quarta, ela também precisa da "
        "severidade por desfecho." % len(achados))


def test_sucesso_do_aprendizado_NAO_e_gravado_como_erro():
    """O caso da Cassia: 3 sucessos vestidos de erro no painel."""
    for trecho in _chamadas_de_sucesso():
        assert "severity=" in trecho, (
            "chamada sem severidade explícita — o padrão do `_log_error` é "
            "'error', então o sucesso volta a aparecer como falha: %r" % trecho)
        assert '"info"' in trecho, (
            "a severidade não tem o ramo de sucesso: %r" % trecho)


def test_FALHA_do_aprendizado_continua_sendo_erro():
    """🚨 A metade que importa. `gerou_linha=False` é a resposta pra 'por que o
    `revision_feedback` não enche' — não pode virar `info` e sumir do painel."""
    for trecho in _chamadas_de_sucesso():
        assert '"error"' in trecho, (
            "o ramo de falha sumiu — `gerou_linha=False` viraria `info` e a "
            "falha do aprendizado deixaria de aparecer: %r" % trecho)
        # a severidade tem que depender do resultado, não ser fixa
        assert re.search(r'if\s+_?gerou', trecho), (
            "a severidade não depende do desfecho: %r" % trecho)


def test_o_stage_NAO_entrou_na_lista_de_diagnostico():
    """🪤 O atalho errado. A lista rebaixa o stage INTEIRO pra `info`, o que
    esconderia as 11 falhas reais junto com os 12 sucessos."""
    i = _CORPO.find("_STAGES_DIAGNOSTICO")
    fim = _CORPO.find(")", i)
    bloco = _CORPO[i:fim if fim > i else i + 2500]
    assert '"motor:revisao-aprendizado"' not in bloco, (
        "o stage foi para a lista de diagnóstico — isso silencia as FALHAS do "
        "aprendizado, que é justamente o sinal que a gente precisa ver")


def test_as_chamadas_de_EXCECAO_seguem_sem_severidade_explicita():
    """Elas devem continuar caindo no padrão `error` — são falhas de verdade."""
    for marca in ("AUTOMATICO FALHOU", "MANUAL FALHOU", "ESTEIRA FALHOU",
                  "NAO INICIOU"):
        assert marca in _CORPO, (
            "sumiu o registro de falha %r do aprendizado da revisão" % marca)


def test_controle_positivo_o_padrao_do_log_error_e_error():
    """Prova que os guardas acima cobram algo: sem `severity=`, é 'error'."""
    assert 'def _log_error(stage, message, job_id=None, severity="error")' in _CORPO, (
        "o padrão do `_log_error` mudou — reveja se os guardas acima ainda "
        "fazem sentido")
