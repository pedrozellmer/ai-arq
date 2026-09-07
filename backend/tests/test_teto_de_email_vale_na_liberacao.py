# -*- coding: utf-8 -*-
"""O teto de 1 e-mail por semana não valia na porta da liberação.

🚨 29/08/2026. A cliente-20 (a cliente do NPS 2) recebeu TRÊS e-mails num dia:

    08:00  "Que tal ajudar a afinar seu quantitativo?"   esteira automática
    13:59  "ARMAÇÃO FUNDAÇÃO — refizemos a leitura"      disparado pela liberação
    14:23  o do Pedro, escrito à mão

Os dois últimos dizem a mesma coisa, com 24 minutos de diferença. E o Pedro
mandou o dele porque **eu garanti que nenhum automático sairia** — eu tinha lido
a trava de "cliente que revisou não recebe" e concluído que ela pegaria. Não
pegou: as 3 correções dela são em OUTRO projeto, e a trava olha o projeto-pai.
Descobri esse fato sozinho minutos depois e não voltei a ligar os pontos.

🔑 A CAUSA ESTRUTURAL: o cooldown de 7 dias (`_email_auto_recente`) mora DENTRO
do `emails_auto_tick` — ele filtra a esteira de nutrição. A liberação de filhote
chama `_email_leitura_nova` por fora, então nunca passava por ele. A regra do
Pedro é "no máximo 1 automático por pessoa por semana"; esta porta estava fora
da regra desde que nasceu.

🪤 O CONSERTO NÃO É BLOQUEAR CALADO. Segurar o aviso e não dizer nada seria pior:
o cliente deixa de saber que a leitura melhorou, que é o ponto do mecanismo
inteiro (Pedro, 08/08: *"aviso só na tela não resolve — 1 de 44 clientes voltou
numa semana diferente"*). No botão manual o motivo VOLTA na resposta, e quem
libera decide se fala à mão. No caminho automático não há ninguém pra decidir,
então ele segura e registra no log.

📌 Mesma saída da trava de cliente-que-revisou: a máquina não manda, e o humano
sabe que precisa mandar.

🪤 05/09/2026 — ESTES GUARDAS ERAM CEGOS. Quatro deles liam STRING do main.py e
ficavam verdes com o defeito aberto: `dias=7` virava `dias=0` (a janela do
cooldown some e a trava nunca pega) e o nome da função continuava escrito
exatamente onde o assert procurava; o PATCH da liberação automática perdia o
`user_id` e o guarda só media a ORDEM de duas strings, que não mudou. Agora
eles CHAMAM a rota e conferem a saída.
"""
import io
import json as _jsonb
import os
import sys
import time as _timeb
import urllib.parse as _uparse
import urllib.request as _ureq
from datetime import datetime as _dtb, timedelta as _tdb, timezone as _tzb

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import main as M  # noqa: E402

_MAIN = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _sem_comentarios(txt):
    """🪤 Sexta ou sétima vez que preciso disto: comentário não é código, e
    testes que leem comentário aprovam pelo motivo errado."""
    return "\n".join(l for l in txt.split("\n") if not l.strip().startswith("#"))


def _bloco(marca, tamanho=2600):
    i = _MAIN.find(marca)
    assert i > 0, "não achei %r em main.py" % marca
    return _sem_comentarios(_MAIN[i:i + tamanho])


# ══════════════════════════════════════════════════════════════════════════
#  🧪 BANCADA QUE EXECUTA — Supabase de mentira, nunca a rede
# ══════════════════════════════════════════════════════════════════════════
class _RespostaFalsa:
    """O que `urlopen` devolve: algo com `.read()` que dá bytes de JSON."""

    def __init__(self, payload):
        self._b = _jsonb.dumps(payload).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _corte_da_url(url):
    """O `sent_at=gte.<iso>` que a própria função montou.

    🔑 É ISTO que faz o guarda enxergar `dias=7 → dias=0`: quem decide se a
    pessoa "recebeu recente" é a data que `_email_auto_recente` CALCULOU e
    escreveu na consulta — não um mock que devolve True de graça.
    """
    q = _uparse.parse_qs(_uparse.urlparse(url).query, keep_blank_values=True)
    bruto = (q.get("sent_at") or [""])[0]
    assert bruto.startswith("gte."), (
        "a consulta do cooldown perdeu o filtro de data: %r" % url)
    return _dtb.fromisoformat(bruto[4:])


def _quem_da_url(url):
    """O `email=eq.<quem>` que a consulta do cooldown perguntou.

    🪤 06/09/2026 — O DUBLÊ SÓ LIA A DATA. Com isso os quatro guardas provavam
    que a JANELA de 7 dias é obedecida, mas nunca que ela é consultada PARA A
    PESSOA CERTA. Qualquer estrago no escopo por pessoa (filtro removido, quote
    errado, refactor pra `user_id`, e-mail vazio) deixava a consulta perguntando
    pelo ninguém: em produção o PostgREST não acha linha nenhuma,
    `_email_auto_recente` devolve False e o e-mail sai pra TODO MUNDO — o caso
    cliente-20 (3 e-mails num dia) de volta, com a bancada verde.

    Devolve "" quando o filtro sumiu — e "" nunca casa com o endereço esperado.
    """
    q = _uparse.parse_qs(_uparse.urlparse(url).query, keep_blank_values=True)
    bruto = (q.get("email") or [""])[0]
    return bruto[3:] if bruto.startswith("eq.") else ""


def _urlopen_de_mentira(dias_desde_o_ultimo_auto=None, email_esperado=None,
                        perguntados=None):
    """`email_auto_log` que RESPEITA a janela E o destinatário pedidos na URL.

    Imita o PostgREST de verdade nos DOIS eixos: só devolve linha quando a
    consulta pergunta pela janela certa E pela pessoa que de fato recebeu.
    Perguntou por outro (ou por ninguém)? Volta vazio, como o banco voltaria.
    """
    def _fake(req, timeout=None):
        _esperado = _EMAIL if email_esperado is None else email_esperado
        url = getattr(req, "full_url", str(req))
        if "email_auto_log" in url:
            quem = _quem_da_url(url)
            if perguntados is not None:
                perguntados.append(quem)
            if quem != _esperado:
                return _RespostaFalsa([])      # o banco não tem linha dessa pessoa
            if dias_desde_o_ultimo_auto is None:
                return _RespostaFalsa([])
            corte = _corte_da_url(url)
            quando = _dtb.now(_tzb.utc) - _tdb(days=dias_desde_o_ultimo_auto)
            return _RespostaFalsa([{"id": 1}] if quando >= corte else [])
        return _RespostaFalsa([])
    return _fake


def _rest_de_mentira(projetos, itens, revisoes=(), patches=None):
    """Substitui `_supa_rest_service` — e com ele o `_supa_rows`, que o chama."""
    def _fake(method, path, body=None, params=None, prefer=None, timeout=15):
        params = params or {}
        jid = str(params.get("job_id", "")).replace("eq.", "")
        if method == "PATCH" and path == "projects":
            if patches is not None:
                patches.append({"body": body, "job_id": jid})
            return 200, []
        if path == "projects":
            linha = projetos.get(jid)
            return 200, ([dict(linha)] if linha else [])
        if path == "project_items":
            return 200, [dict(x) for x in itens.get(jid, [])]
        if path == "item_reviews":
            return 200, [dict(x) for x in revisoes]
        return 200, []
    return _fake


_PAI = "pai00020"
_FILHOTE = "ev000020"
_EMAIL = "cliente-20@example.com"

_PROJETOS = {
    _PAI: {"job_id": _PAI, "user_id": "u-cliente-20", "user_email": _EMAIL,
           "user_name": "Cliente 20", "project_name": "Residencial 20",
           "status": "done"},
    _FILHOTE: {"job_id": _FILHOTE, "parent_job_id": _PAI, "is_eval": True,
               "user_id": "eval", "status": "done", "warnings": [],
               "project_name": "[TESTE] Residencial 20 - avaliacao"},
}
# o filhote mede o que o pai deixou zerado — é o caso que dispara o aviso
_ITENS = {
    _PAI: [{"description": "Forro de gesso", "unit": "m2", "quantity": 0,
            "confidence": "estimado", "ref_sheet": "ARQ-01"},
           {"description": "Piso", "unit": "m2", "quantity": 12,
            "confidence": "confirmado", "ref_sheet": "ARQ-01"}],
    _FILHOTE: [{"description": "Forro de gesso", "unit": "m2", "quantity": 26.54,
                "confidence": "confirmado", "ref_sheet": "ARQ-01"},
               {"description": "Piso", "unit": "m2", "quantity": 12,
                "confidence": "confirmado", "ref_sheet": "ARQ-01"},
               {"description": "Revestimento", "unit": "m2", "quantity": 268.39,
                "confidence": "confirmado", "ref_sheet": "ARQ-02"},
               {"description": "Parede nova", "unit": "m", "quantity": 302.14,
                "confidence": "estimado", "ref_sheet": "ARQ-02"}],
}


class _RequisicaoFalsa:
    headers = {"user-agent": "bancada"}
    query_params = {}


def _bancada_da_liberacao(monkeypatch, dias_desde_o_ultimo_auto, patches, enviados,
                          perguntados=None):
    """Botão MANUAL: `/api/admin/liberar-filhote/{job}` sem rede e sem banco."""
    monkeypatch.setattr(M, "_require_admin", lambda request: {"email": "admin@example.com"})
    monkeypatch.setattr(M, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(M, "_notify_admin", lambda *a, **k: True)
    monkeypatch.setattr(M, "_supa_rest_service",
                        _rest_de_mentira(_PROJETOS, _ITENS, (), patches))
    monkeypatch.setattr(_ureq, "urlopen",
                        _urlopen_de_mentira(dias_desde_o_ultimo_auto,
                                            perguntados=perguntados))

    def _registra(pai, *a, **k):
        enviados.append(pai.get("user_email"))
        return True
    monkeypatch.setattr(M, "_email_leitura_nova", _registra)
    monkeypatch.setattr(M, "_email_leitura_combinada", lambda pai, *a, **k: _registra(pai))


def _bancada_do_automatico(monkeypatch, dias_desde_o_ultimo_auto, patches, enviados, logs,
                           perguntados=None):
    """Caminho AUTOMÁTICO: a juíza libera, o resto é o código de verdade."""
    import anthropic as _an
    import llm_retry as _lr

    monkeypatch.setattr(_timeb, "sleep", lambda s: None)   # a espera de 30 s do vigia
    monkeypatch.setattr(M, "_supa_rest_service",
                        _rest_de_mentira(_PROJETOS, _ITENS, (), patches))
    monkeypatch.setattr(_ureq, "urlopen",
                        _urlopen_de_mentira(dias_desde_o_ultimo_auto,
                                            perguntados=perguntados))
    monkeypatch.setattr(M, "_notify_admin", lambda *a, **k: True)
    monkeypatch.setattr(M, "_log_error",
                        lambda stage, message, job_id=None, severity="error":
                        logs.append("%s|%s" % (stage, message)))

    def _registra(pai, *a, **k):
        enviados.append(pai.get("user_email"))
        return True
    monkeypatch.setattr(M, "_email_leitura_nova", _registra)

    class _ClienteFalso:
        def __init__(self, *a, **k):
            pass
    monkeypatch.setattr(_an, "Anthropic", _ClienteFalso)

    class _Bloco:
        text = '{"liberar": true, "motivo": "preencheu forro e revestimento"}'

    class _Resp:
        content = [_Bloco()]
    monkeypatch.setattr(_lr, "call_with_retry", lambda *a, **k: _Resp())


# ══════════════════════════════════════════════════════════════════════════
#  Os guardas
# ══════════════════════════════════════════════════════════════════════════
def test_o_botao_MANUAL_consulta_o_teto_antes_de_mandar(monkeypatch):
    """🚨 O caso da cliente-20: liberar disparava e-mail mesmo pra quem já
    tinha recebido outro automático na mesma semana.

    Isto EXECUTA a rota. O Supabase de mentira respeita a janela que a própria
    `_email_auto_recente` escreveu na consulta — então encurtar o cooldown
    (`dias=7` → `dias=0`) reprova aqui, e não passa mais só porque o nome da
    função continua escrito no arquivo.
    """
    patches, enviados, perguntados = [], [], []
    _bancada_da_liberacao(monkeypatch, 3, patches, enviados, perguntados)   # há 3 dias

    resp = M.admin_liberar_filhote(_FILHOTE, _RequisicaoFalsa())

    # 🔑 metade da pergunta é "a janela está certa?"; a outra é "É A PESSOA
    # CERTA?". Sem esta linha, perguntar pelo ninguém passava verde.
    assert perguntados == [_EMAIL], (
        "o cooldown não foi consultado para o dono do projeto — perguntou %r"
        % (perguntados,))
    assert resp["email_enviado"] is False, (
        "a liberação manual disparou e-mail pra quem já recebeu um automático "
        "há 3 dias — foi assim que a cliente-20 recebeu 3 num dia (%r)"
        % (resp.get("email_motivo"),))
    assert enviados == [], "o e-mail chegou a ser montado: %r" % enviados
    motivo = resp["email_motivo"] or ""
    assert "NÃO enviado" in motivo, "não devolve o motivo pra quem libera: %r" % motivo
    assert "painel" in motivo, (
        "o motivo não diz que a leitura JÁ está no painel — quem lê vai achar "
        "que a liberação falhou")
    assert "à mão" in motivo or "a mão" in motivo, (
        "não aponta a saída (falar à mão), que é o que a regra do Pedro manda "
        "quando a máquina se cala")


def test_CONTROLE_quem_NAO_recebeu_na_semana_continua_avisado(monkeypatch):
    """🧪 O contrapeso: a trava não pode ter virado "nunca manda".

    Bloquear calado é pior que mandar — o cliente deixa de saber que a leitura
    melhorou, que é o ponto do mecanismo inteiro.
    """
    patches, enviados = [], []
    _bancada_da_liberacao(monkeypatch, 30, patches, enviados)   # último há 30 dias

    resp = M.admin_liberar_filhote(_FILHOTE, _RequisicaoFalsa())
    assert resp["email_enviado"] is None and "em envio" in (resp["email_motivo"] or ""), (
        "o teto passou a segurar até quem não recebeu nada no mês (%r)"
        % (resp.get("email_motivo"),))


def test_e_o_caminho_AUTOMATICO_tambem(monkeypatch):
    """A liberação automática (juíza) usa a mesma porta e tem o mesmo risco —
    com o agravante de não ter ninguém pra ler o aviso.

    Executa `_auto_liberar_filhote_quando_pronto` inteiro: juíza de mentira
    liberando, e o cooldown REAL consultado contra um log que diz "recebeu há
    3 dias". Se a janela encolher, o e-mail sai e este guarda reprova.
    """
    patches, enviados, logs, perguntados = [], [], [], []
    _bancada_do_automatico(monkeypatch, 3, patches, enviados, logs, perguntados)

    M._auto_liberar_filhote_quando_pronto(_FILHOTE, _PAI, timeout_min=1)

    assert perguntados == [_EMAIL], (
        "o cooldown automático não perguntou pelo dono do projeto — perguntou "
        "%r. Com a chave errada o banco não acha linha, a trava devolve False e "
        "o e-mail sai pra todo mundo." % (perguntados,))
    assert enviados == [], (
        "o caminho automático mandou e-mail pra quem já recebeu um automático "
        "há 3 dias — e aqui não há ninguém pra ver o aviso e decidir")
    assert any("SEGURADO" in x for x in logs), (
        "segurou o e-mail sem deixar rastro: 'não mandei' e 'falhou o SMTP' "
        "viram a mesma coisa no escuro")


@pytest.mark.parametrize("dias_do_ultimo,email_sai", [(3, False), (30, True)])
def test_a_liberacao_acontece_com_o_email_segurado_E_com_ele_saindo(
        monkeypatch, dias_do_ultimo, email_sai):
    """🔒 O que NÃO pode: o teto de e-mail impedir a leitura nova de chegar ao
    painel. São duas coisas diferentes — uma é avisar, a outra é entregar.

    Confere a LINHA QUE SERIA GRAVADA. O guarda antigo media a ORDEM de duas
    strings no fonte e ficou verde quando o PATCH perdeu o `user_id`: o job era
    renomeado e nunca chegava ao painel do cliente.

    🪤 06/09/2026 — E ELE SÓ EXERCITAVA O RAMO "E-MAIL SEGURADO". Bastava
    pendurar o PATCH nesse mesmo teto (entregar só quando o aviso NÃO pode sair)
    pra tudo ficar verde — e no caminho em que o cliente RECEBE o "refizemos a
    leitura", o job jamais seria apontado pro dono: e-mail avisando de uma
    planilha que não aparece no painel dele. Agora os DOIS ramos passam por aqui:
    entregar não depende de avisar.
    """
    patches, enviados, logs = [], [], []
    _bancada_do_automatico(monkeypatch, dias_do_ultimo, patches, enviados, logs)

    M._auto_liberar_filhote_quando_pronto(_FILHOTE, _PAI, timeout_min=1)

    assert enviados == ([_EMAIL] if email_sai else []), (
        "cenário errado: com o último automático há %d dias o e-mail deveria "
        "%s (saiu para %r)" % (dias_do_ultimo,
                               "SAIR" if email_sai else "ficar segurado", enviados))
    assert patches, ("a liberação não gravou nada — o filhote não chegou ao "
                     "painel (último automático há %d dias)" % dias_do_ultimo)
    p = patches[-1]
    assert p["job_id"] == _FILHOTE, "gravou no job errado: %r" % p["job_id"]
    assert p["body"].get("user_id") == _PROJETOS[_PAI]["user_id"], (
        "o filhote foi renomeado mas NÃO foi apontado pro dono do original — "
        "ele nunca aparece no painel do cliente (%r)" % (p["body"],))
    assert "nova leitura" in str(p["body"].get("project_name", "")), (
        "o cliente não tem como saber qual das duas linhas é a nova")


@pytest.mark.parametrize("dias_do_ultimo,email_segurado", [(3, True), (30, False)])
def test_o_botao_MANUAL_tambem_aponta_o_filhote_pro_DONO(
        monkeypatch, dias_do_ultimo, email_segurado):
    """A porta MANUAL grava o MESMO patch — e nenhum guarda olhava o corpo dele.

    🪤 06/09/2026: perder o `user_id` aqui é exatamente o defeito que já tinha
    sido mutado no caminho automático, e passava verde nesta porta. Os dois
    ramos do teto entram, porque o PATCH acontece ANTES da decisão do e-mail e
    não pode depender dela.
    """
    patches, enviados = [], []
    _bancada_da_liberacao(monkeypatch, dias_do_ultimo, patches, enviados)

    resp = M.admin_liberar_filhote(_FILHOTE, _RequisicaoFalsa())

    assert (resp["email_enviado"] is False) is email_segurado, (
        "cenário errado (último automático há %d dias): %r"
        % (dias_do_ultimo, resp.get("email_motivo")))
    assert patches, "a liberação manual não gravou nada — o filhote não chegou ao painel"
    p = patches[-1]
    assert p["job_id"] == _FILHOTE, "gravou no job errado: %r" % p["job_id"]
    assert p["body"].get("user_id") == _PROJETOS[_PAI]["user_id"], (
        "o botão manual renomeou o filhote mas NÃO o apontou pro dono do "
        "original — ele nunca aparece no painel do cliente (%r)" % (p["body"],))
    assert "nova leitura" in str(p["body"].get("project_name", "")), (
        "o cliente não tem como saber qual das duas linhas é a nova (%r)"
        % (p["body"].get("project_name"),))


def test_CONTROLE_o_teto_existe_e_e_de_7_dias(monkeypatch):
    """🧪 Executa `_email_auto_recente` contra um log de envios de mentira.

    O antigo lia a assinatura `dias: int = 7` e o `return True` no fonte — com
    isso o parâmetro podia virar decorativo (janela de zero dia) e o guarda
    continuava verde. Aqui a janela é medida pelo COMPORTAMENTO.
    """
    # 6 dias atrás: DENTRO da semana → segura
    perguntados = []
    monkeypatch.setattr(_ureq, "urlopen",
                        _urlopen_de_mentira(6, perguntados=perguntados))
    assert M._email_auto_recente(_EMAIL) is True, (
        "quem recebeu automático há 6 dias não está mais protegido pelo teto "
        "de 1 por semana — a janela do cooldown encolheu")
    assert perguntados == [_EMAIL], (
        "a consulta perdeu o escopo POR PESSOA (`email=eq.<quem>`): perguntou "
        "%r. Em produção isso não acha linha nenhuma, a trava devolve False e o "
        "e-mail sai pra quem recebeu um há 3 dias." % (perguntados,))

    # 🔑 A OUTRA METADE DA PERGUNTA: o teto é POR PESSOA. Quem NÃO recebeu nada
    # não pode ser segurado só porque um vizinho recebeu — e uma consulta que
    # ignora o endereço pedido (chave fixa, filtro removido) reprova aqui.
    _OUTRO = "cliente-77@example.com"
    assert M._email_auto_recente(_OUTRO) is False, (
        "o cooldown segurou o e-mail de quem nunca recebeu nada — a consulta "
        "não está perguntando pelo endereço que recebeu, e sim por outro")

    # 8 dias atrás: FORA da semana → deixa passar
    monkeypatch.setattr(_ureq, "urlopen", _urlopen_de_mentira(8))
    assert M._email_auto_recente(_EMAIL) is False, (
        "o teto passou a segurar e-mail de quem não recebe nada há 8 dias")

    # o parâmetro `dias` tem que ser OBEDECIDO, não decorativo
    assert M._email_auto_recente(_EMAIL, dias=30) is True, (
        "`dias` virou enfeite: pedi 30 dias e a função ignorou")

    # falha FECHADA: erro de rede não pode virar e-mail
    def _explode(req, timeout=None):
        raise OSError("supabase fora do ar")
    monkeypatch.setattr(_ureq, "urlopen", _explode)
    assert M._email_auto_recente(_EMAIL) is True, (
        "o cooldown passou a falhar ABERTO — erro de rede vira e-mail extra")


# ── guardas de forma que continuam valendo (não foram provados cegos) ──────
def test_o_motivo_VOLTA_pra_quem_libera_em_vez_de_sumir():
    """🪤 Bloquear calado seria pior que mandar: o cliente deixaria de saber que
    a leitura melhorou, e ninguém saberia que ele não soube.

    O texto tem que dizer as duas coisas: que não mandou, e que a leitura já
    está no painel — senão quem lê acha que a liberação falhou."""
    b = _bloco('email_motivo = "NÃO enviado: a versão nova não ficou melhor')
    i = b.find("_email_auto_recente")
    trecho = b[i:i + 700]
    assert "NÃO enviado" in trecho, "não devolve motivo pra quem libera"
    assert "painel" in trecho, (
        "o motivo não diz que a leitura JÁ está no painel — quem lê vai achar "
        "que a liberação falhou")
    assert "à mão" in trecho or "a mão" in trecho, (
        "não aponta a saída (falar à mão), que é o que a regra do Pedro manda "
        "quando a máquina se cala")


def test_o_automatico_deixa_RASTRO_quando_segura():
    """Sem log, "não mandei" e "falhou o SMTP" viram a mesma coisa no escuro."""
    b = _bloco("# LIBERAR — mesmo movimento do botão manual")
    assert "SEGURADO" in b, "segura o e-mail sem registrar por quê"
