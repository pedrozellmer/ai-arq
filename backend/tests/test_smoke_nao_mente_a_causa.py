# -*- coding: utf-8 -*-
"""O smoke test dizia "0 projetos" quando o servidor tinha dado 502.

🚨 28/08/2026. O Pedro encaminhou um e-mail de smoke vermelho. Duas linhas:

    GET /api/instagram/scheduler/list exige admin  (HTTP 502 (esperado 401 ou 403))
    GET /api/projects/by-user — lista  (0 projetos)

**A segunda era mentira.** Não eram 0 projetos: era o mesmo 502. O código fazia

    if status != 200:
        return []

e a lista vazia virava a afirmação "o cliente não tem projeto". Erro de
TRANSPORTE virando afirmação sobre o NEGÓCIO — a mesma família do achado de
05/08, quando 53 de 74 falhas que a gente culpava o cliente eram nossas.

🩸 **O custo real:** mandou procurar no lugar errado. A causa verdadeira estava
no log do Render — o servidor congelava por 33 s na virada da hora porque as
rotinas do relógio eram `async` com corpo bloqueante. Se a linha tivesse dito
"HTTP 502", o caminho até lá seria direto.

🪤 O retry é curto de propósito. Retry generoso é o erro OPOSTO: um smoke que
fica verde escondendo instabilidade real é pior que um que grita errado, porque
aí ninguém olha mais. Ver [[project_incidente_smoke_20260820]].
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SCRIPT = os.path.join(_RAIZ, ".github", "scripts", "smoke_test_production.py")


def _fonte():
    return io.open(_SCRIPT, encoding="utf-8").read()


def _carregar():
    """Importa o script do smoke sem executá-lo."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_smoke", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_5xx_e_reconhecido_como_falha_de_TRANSPORTE():
    """🚨 O guarda central. 502/503/504 é 'o servidor não respondeu', nunca
    'o cliente não tem dado'."""
    m = _carregar()
    for status in (500, 502, 503, 504):
        motivo = m._transporte_falhou(status)
        assert motivo, "HTTP %d passou como se fosse resposta legítima" % status
        assert str(status) in motivo, (
            "o motivo não diz qual foi o status: %r" % motivo)


def test_sem_resposta_nenhuma_tambem_e_transporte():
    """Timeout e falha de conexão devolvem status 0 — não podem virar 'vazio'."""
    m = _carregar()
    assert m._transporte_falhou(0), "timeout passou como resposta válida"


def test_CONTROLE_NEGATIVO_4xx_e_200_NAO_sao_transporte():
    """🧪 O guarda tem que ABSOLVER o que é resposta de verdade. 401 e 403 são
    respostas corretas do servidor (o nível 1 do smoke ESPERA 401 nas rotas de
    admin) — tratá-las como falha de transporte esconderia regressão de auth."""
    m = _carregar()
    for status in (200, 400, 401, 403, 404, 422):
        assert m._transporte_falhou(status) is None, (
            "HTTP %d foi classificado como falha de transporte — isso faria o "
            "smoke parar de enxergar quebra de autenticação" % status)


def test_a_listagem_de_projetos_devolve_o_MOTIVO_junto():
    """O caso concreto. A função tem que dizer POR QUE veio vazio."""
    m = _carregar()
    import inspect
    assinatura = inspect.signature(m._list_user_projects)
    assert "tuple" in str(assinatura.return_annotation).lower(), (
        "_list_user_projects voltou a devolver só a lista — sem o motivo, "
        "502 vira '0 projetos' de novo. Assinatura: %s" % assinatura)


def test_o_chamador_USA_o_motivo_em_vez_de_dizer_zero_projetos():
    """🪤 Guarda do CALL SITE. Já passei verde duas vezes com teste que checava
    a função e não quem chama — sabotei o call site e o teste nem piscou."""
    src = _fonte()
    i = src.find('"GET /api/projects/by-user — lista"')
    assert i > 0, "a checagem da listagem sumiu do smoke"
    trecho = src[max(0, i - 400):i + 400]
    assert "motivo or" in trecho, (
        "o call site voltou a reportar só a contagem, ignorando o motivo:\n%s"
        % trecho[-300:])


def test_o_retry_existe_e_e_CURTO():
    """🪤 Os dois erros são simétricos. Sem retry, um soluço de 1 s vira alarme.
    Com retry demais, instabilidade real fica verde e ninguém olha."""
    m = _carregar()
    import inspect
    padrao = inspect.signature(m._get).parameters["tentativas"].default
    assert 2 <= padrao <= 4, (
        "o smoke tenta %d vezes — fora da faixa que separa 'soluço' de "
        "'esconder problema'" % padrao)


def test_o_retry_NAO_insiste_em_4xx():
    """Insistir num 401 só gasta tempo: a resposta não vai mudar, e pior,
    atrasaria o relatório de uma regressão de auth de verdade."""
    src = _fonte()
    i = src.find("def _get(")
    j = src.find("\ndef ", i + 10)
    corpo = "\n".join(l for l in src[i:j].split("\n")
                      if not l.strip().startswith("#"))
    assert re.search(r"500\s*<=\s*e\.code\s*<\s*600", corpo), (
        "o retry deixou de distinguir 5xx de 4xx — passaria a insistir em "
        "resposta legítima")
