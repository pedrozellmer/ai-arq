# -*- coding: utf-8 -*-
"""A lista de chaves de `meta` matava instrumento novo — calada.

🚨 27/08/2026, achado na auditoria do próprio dia. Uma hora depois de subir o
`signup_saiu_da_tela` — o evento que grava EM QUE CAMPO a pessoa parou no
cadastro — fui conferir se ele estava gravando. Estava. E o `campo` não:

    {"cid": "cmrmo1hoqp3q7xegu", "src": "direto"}

O `/api/track` tem uma lista fechada de chaves de `meta` (`cid`, `type`, `src`)
e **descarta o resto sem avisar**. O instrumento nasceu, chegou ao banco, e
perdeu a única informação pra qual foi feito.

🪤 **Existia guarda pro NOME do evento** (`test_track_allowlist`) — e foi ele que
me barrou o commit hoje de manhã, salvando o instrumento de nascer morto.
**Não existia guarda pras CHAVES de meta.** Por isso este passou.

É a mesma família do achado de 23/08, quando 9 eventos que o front disparava há
semanas eram descartados com `200 {"status":"ignored"}`.

🔒 A lista fechada existe por SEGURANÇA e continua: nada de HTML/JS arbitrário
chega ao painel admin. O que este teste cobra é que ela seja mantida em dia com
o que o front realmente manda.
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RAIZ = os.path.dirname(_BACKEND)

_MAIN = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _chaves_aceitas_no_backend():
    """As chaves que o /api/track realmente grava.

    🪤 Duas formas no código, e a 1ª versão deste detector só via a primeira —
    então acusava como "perdidas" sete chaves que EU tinha acabado de aceitar:
      (a) `_meta["cid"] = ...`            → nome literal
      (b) `for _k in ("a","b"): _meta[_k] = ...` → tupla do laço
    Detector que só vê metade acusa errado, e guarda que acusa errado é
    ignorado — pior que guarda nenhum.
    """
    i = _MAIN.find('@app.post("/api/track")')
    assert i > 0, "não achei a rota /api/track"
    trecho = _MAIN[i:i + 5000]
    chaves = set(re.findall(r'_meta\["(\w+)"\]\s*=', trecho))
    # (b) o laço: pega os literais da tupla que alimenta `_meta[_k]`
    for tupla in re.findall(r'for\s+_k\s+in\s*\(([^)]*)\)\s*:', trecho, re.S):
        chaves.update(re.findall(r'"(\w+)"', tupla))
    return chaves


def _chaves_enviadas_pelo_front():
    """As chaves de meta que o site manda em `trackEvent(evento, {...})`.

    🪤 O `aiarq-utils.js` sempre acrescenta `cid` e `src`; o resto vem de quem
    chama, espalhado pelos .html.
    """
    chaves = {"cid", "src"}
    for nome in os.listdir(_RAIZ):
        if not nome.endswith((".html", ".js")):
            continue
        try:
            txt = io.open(os.path.join(_RAIZ, nome), encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            continue
        # trackEvent('x', { chave: ... })  /  trackEvent("x", {chave: ...})
        for corpo in re.findall(r"trackEvent\(\s*['\"][^'\"]+['\"]\s*,\s*\{([^}]*)\}",
                                txt):
            for k in re.findall(r"(\w+)\s*:", corpo):
                chaves.add(k)
    return chaves


def test_toda_chave_que_o_front_manda_o_backend_ACEITA():
    """🚨 O guarda que faltava. Chave nova no front sem linha aqui = dado
    descartado calado, exatamente como aconteceu com o `campo`."""
    front = _chaves_enviadas_pelo_front()
    backend = _chaves_aceitas_no_backend()
    # 🪤 `job_id` NÃO é perda: o payload tem coluna própria pra ele
    # (`usage_events.job_id`), e o front manda nos dois lugares. Se eu não
    # excluísse, o guarda acusaria falso positivo pra sempre — e guarda que
    # acusa errado é ignorado, que é pior que guarda nenhum.
    front = front - {"job_id"}
    perdidas = sorted(front - backend)
    assert not perdidas, (
        "o front manda %s e o /api/track descarta CALADO. Ou acrescente a "
        "chave no bloco `_meta` (saneada!), ou pare de mandar." % perdidas)


def test_o_campo_do_cadastro_sobrevive():
    """O caso concreto que motivou este arquivo."""
    assert "campo" in _chaves_aceitas_no_backend(), (
        "o `campo` voltou a ser descartado — o `signup_saiu_da_tela` deixa de "
        "responder ONDE a pessoa parou, que é a única coisa que ele faz")


def test_o_campo_e_SANEADO_e_nao_entra_cru():
    """🔒 A lista fechada existe por segurança. Chave nova não pode virar porta
    de HTML/JS pro painel admin."""
    i = _MAIN.find('@app.post("/api/track")')
    trecho = _MAIN[i:i + 4000]
    j = trecho.find('_campo = ')
    assert j > 0, "não achei o saneamento do campo"
    linha = trecho[j:j + 260]
    assert "a-z0-9_-" in linha, (
        "o `campo` entra sem lista branca de caracteres: %r" % linha)
    assert "[:40]" in linha, "o `campo` entra sem teto de tamanho"


def test_o_backend_NAO_grava_o_valor_digitado():
    """🔒 A tela de cadastro tem WhatsApp e nome. Se algum dia alguém mandar
    `valor` junto, o backend não pode aceitar."""
    backend = _chaves_aceitas_no_backend()
    for proibida in ("valor", "value", "conteudo", "texto", "telefone",
                     "whatsapp", "email_digitado"):
        assert proibida not in backend, (
            "o /api/track passou a aceitar a chave %r — isso é conteúdo "
            "digitado pelo cliente" % proibida)


def test_CONTROLE_POSITIVO_o_detector_pega_chave_orfa():
    """🧪 Sem isto, o teste principal passaria verde com um detector quebrado —
    foi assim que eu deixei passar guarda inútil quatro vezes hoje."""
    front_falso = {"cid", "src", "campo", "chave_que_ninguem_aceita"}
    backend = _chaves_aceitas_no_backend()
    assert sorted(front_falso - backend) == ["chave_que_ninguem_aceita"], (
        "o cruzamento não detecta chave órfã")
