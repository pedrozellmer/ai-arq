# -*- coding: utf-8 -*-
"""Origem capturada no blog E sbClient vivo no login — os DOIS lados.

🩸 31/08/2026, duas falhas no mesmo dia:
1. O bloco de first-touch estava DEPOIS do `return` do guarda do supabase-js:
   no blog (página estática) a captura NUNCA rodava. Dos 9 `view_blog_post`,
   os 4 com `src` eram do mesmo navegador (que já tinha o dado salvo); os 5
   sem `src` eram visitantes novos. Quem chegava do Google num post e depois
   se cadastrava era carimbado "direto".
2. 🚨 O CONSERTO QUEBROU O LOGIN EM PRODUÇÃO por 12 minutos. Recortei o bloco
   por índice de string e deixei o `};` final pra trás: a função ficou ABERTA
   e engoliu o resto do arquivo — inclusive `window.sbClient = _sbClient`.
   Sintaxe VÁLIDA (nenhum erro no console), semântica morta. Eu vi
   `sbClient: undefined` num teste e segui assim mesmo; quem pegou foi o smoke
   de browser real e o Pedro, que não conseguia entrar.

🔑 Por isso este guarda cobra as DUAS coisas: a captura subir E o sbClient
continuar no escopo do módulo (nunca dentro de outra função).
"""
import io
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UTILS = os.path.join(RAIZ, "aiarq-utils.js")


def _fonte():
    return io.open(UTILS, encoding="utf-8").read()


def _pos_guarda(src):
    i = src.index("if (!window.supabase || typeof window.supabase.createClient")
    return src.index("return;", i)


def test_captura_de_origem_roda_ANTES_do_guarda():
    src = _fonte()
    assert src.index("_captureSource") < _pos_guarda(src), (
        "a captura de first-touch voltou pra DEPOIS do return do guarda — no "
        "blog ela não roda e todo visitante novo perde a origem")


def test_trackEvent_tambem_antes_do_guarda():
    src = _fonte()
    assert src.index("window.trackEvent = function") < _pos_guarda(src)


def test_aiArqSource_disponivel_no_blog():
    src = _fonte()
    assert src.index("window.aiArqSource = function") < _pos_guarda(src)


def test_o_BLOCO_DA_ORIGEM_esta_FECHADO():
    """🚨 O teste que teria evitado o login morto: entre o início do bloco de
    origem e o guarda, as chaves têm que fechar. Se um `};` ficar pra trás, o
    resto do arquivo vira corpo de uma função que ninguém chama — e o
    `window.sbClient` nunca é criado."""
    src = _fonte()
    ini = src.index("─── Origem (first-touch attribution)")
    # 🪤 corta ANTES da linha do guarda: ela abre uma chave que só fecha
    # depois, e contá-la daria falso positivo (me custou uma bancada vermelha)
    fim = src.index("if (!window.supabase || typeof window.supabase.createClient")
    trecho = src[ini:fim]
    # tira strings e regex literais, que podem conter chaves soltas
    limpo = re.sub(r"'[^'\n]*'|\"[^\"\n]*\"|/\[[^\]]*\][^/\n]*/", "", trecho)
    assert limpo.count("{") == limpo.count("}"), (
        "chaves desbalanceadas entre o bloco de origem e o guarda: alguma "
        "função ficou ABERTA e vai engolir o resto do arquivo (foi assim que "
        "o login morreu em 31/08)")


def test_sbClient_e_criado_no_ESCOPO_DO_MODULO():
    """A linha que cria o cliente tem que estar com indentação de módulo (2
    espaços). Se aparecer mais funda, é sinal de que caiu dentro de outra
    função — o sintoma exato do bug de 31/08."""
    src = _fonte()
    linha = next(l for l in src.split("\n") if "window.sbClient = _sbClient" in l)
    recuo = len(linha) - len(linha.lstrip())
    assert recuo <= 2, (
        "window.sbClient está indentado com %d espaços — provavelmente caiu "
        "dentro de outra função e nunca vai executar" % recuo)


def test_CONTROLE_POSITIVO_o_detector_pega_a_ordem_errada():
    """🧪 Prova que o guarda de ordem reprova mesmo."""
    falso = ("window.trackEvent = function () {};\n"
             "if (!window.supabase || typeof window.supabase.createClient !== 'function') {\n"
             "  return;\n}\n"
             "(function _captureSource() {})();\n")
    g = falso.index("return;", falso.index(
        "if (!window.supabase || typeof window.supabase.createClient"))
    assert falso.index("_captureSource") > g


def test_CONTROLE_POSITIVO_o_detector_pega_bloco_ABERTO():
    """🧪 E que o guarda de chaves reprova mesmo — o erro que me custou o
    login."""
    trecho = "─── Origem (first-touch attribution)\nfunction a() { if (x) {\n"
    limpo = re.sub(r"'[^'\n]*'|\"[^\"\n]*\"", "", trecho)
    assert limpo.count("{") != limpo.count("}")
