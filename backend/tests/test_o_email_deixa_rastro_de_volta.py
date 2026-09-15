# -*- coding: utf-8 -*-
"""537 e-mails saíram e NADA media o que acontece depois.

🩸 15/09/2026 — a varredura mediu: zero marcador nos links, zero evento de
volta, zero atribuição. O e-mail de calibração pede revisão há 57 dias e não
produziu UMA; a esteira de resgate (retorno_30d, nudge_onboarding,
nudge_cadastro) tem 0 conversões em 64 pessoas. Sem marcador não dá pra
separar "o texto não convence" de "o e-mail nem chega" — e "não sei" vinha
sendo lido como "não funciona".

🔑 O conserto tem TRÊS partes acopladas, e cada uma é inútil sozinha:
  (1) o link do e-mail sai marcado (`_send_email_smtp`, a porta única);
  (2) a tela guarda o ÚLTIMO empurrão ao lado do first-touch (`aiarq_ult`) —
      sem isso o marcador não aparece em lugar nenhum, porque quem recebe
      e-mail já tem conta e o `src` de first-touch nunca se sobrescreve;
  (3) o `/api/track` deixa a chave `ult` passar — senão ela chega e é
      DESCARTADA CALADA, que é o que já aconteceu com `campo` (27/08) e com
      `chars`/`n`/`restam` (14/09).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import main  # noqa: E402
from _corpo import corpo_de, fonte, sem_comentarios, sem_comentarios_js  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
#  (1) O marcador no link
# ─────────────────────────────────────────────────────────────────────────────

def test_link_NOSSO_sai_marcado():
    u = main._marcar_url_do_email("https://ai.arq.br/revisao.html?job=abc",
                                  "calibracao")
    assert "utm_source=email" in u and "utm_campaign=calibracao" in u, u
    assert "job=abc" in u, "o marcador comeu o parâmetro que já existia: %s" % u


def test_o_marcador_entra_ANTES_do_fragmento():
    """🪤 O GoTrue devolve o token no `#fragmento`. Parâmetro colado depois do
    `#` não é parâmetro — vira parte do fragmento e nunca chega ao servidor."""
    u = main._marcar_url_do_email("https://ai.arq.br/login.html#tok=1",
                                  "retorno_30d")
    assert u.index("utm_source") < u.index("#"), u
    assert u.endswith("#tok=1"), u


def test_o_LINK_MAGICO_e_marcado_por_dentro():
    """🚨 O caso que decide. O CTA dos e-mails de RESGATE — justamente os de 0%
    — aponta pro host do GoTrue, não pro nosso. Marcar só o host de fora
    deixaria de fora exatamente quem eu quero medir."""
    from urllib.parse import unquote
    u = main._marcar_url_do_email(
        "https://kqja.supabase.co/auth/v1/verify?token=T&type=magiclink"
        "&redirect_to=https%3A%2F%2Fai.arq.br%2Flogin.html", "retorno_30d")
    assert "supabase.co/auth/v1/verify" in u, "o link mágico foi desfigurado: %s" % u
    assert "token=T" in u, "o token do login se perdeu na marcação: %s" % u
    assert "utm_campaign=retorno_30d" in unquote(u), u


def test_CONTROLE_nao_marca_o_que_NAO_e_nosso():
    """O WhatsApp é `wa.me` e está dentro de TODO e-mail (na assinatura). Marcar
    link de terceiro é sujeira, e ainda vaza o nome da campanha pra fora."""
    for fora in ("https://wa.me/5521999999999?text=oi",
                 "mailto:alguem@example.com",
                 "https://outro.com/x",
                 "#ancora"):
        assert main._marcar_url_do_email(fora, "calibracao") == fora, fora


def test_CONTROLE_nao_marca_duas_vezes():
    ja = "https://ai.arq.br/x?utm_source=instagram"
    assert main._marcar_url_do_email(ja, "calibracao") == ja


# ─────────────────────────────────────────────────────────────────────────────
#  (2) A PORTA ÚNICA — o guarda que impede o tipo novo de nascer cego
# ─────────────────────────────────────────────────────────────────────────────

def test_TODO_email_sai_marcado_pela_porta_unica(monkeypatch):
    """🚨 O guarda mais importante deste arquivo. A marcação mora em
    `_send_email_smtp`, que é por onde os 18 tipos de e-mail saem e que já
    recebe o `log_kind`. Se alguém mover isso pro `_email_wrap`, cada chamador
    passa a ter que lembrar do tipo — e o que esquecer fica cego, em silêncio.
    """
    enviados = []

    class _Servidor(object):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def ehlo(self):
            pass

        def starttls(self):
            pass

        def login(self, *a):
            pass

        def sendmail(self, de, para, corpo):
            enviados.append(corpo)

    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: _Servidor())
    for var in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.setenv(var, "x")
    monkeypatch.setattr(main, "_supabase_insert", lambda *a, **k: True)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    # 🪤 Sem isto o teste faz REDE de verdade: a checagem de supressão bate no
    # Supabase a cada execução da bancada. Ferramenta que a produção tem e o
    # teste não deveria usar.
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (200, []))

    ok = main._send_email_smtp(
        "cliente-nn@example.com", "assunto",
        '<a href="https://ai.arq.br/revisao.html">abrir</a>',
        log_kind="calibracao")
    assert ok and enviados, "o e-mail nem saiu — o teste não mediu nada"
    # 🪤 O corpo sai em BASE64, não em texto cru — procurar a string no MIME
    # bruto dá falso negativo. Decodificar é o que o cliente de e-mail faz.
    import email as _email
    msg = _email.message_from_string(enviados[0])
    html = ""
    for parte in msg.walk():
        if parte.get_content_type() == "text/html":
            html = parte.get_payload(decode=True).decode("utf-8", "replace")
    assert html, "não achei a parte HTML do e-mail: %s" % enviados[0][:200]
    assert "utm_source=email" in html, (
        "o e-mail saiu SEM marcador — 537 envios voltam a ser inauditáveis: %s"
        % html)
    assert "utm_campaign=calibracao" in html, (
        "o marcador saiu sem o TIPO do e-mail: %s" % html)


def test_CONTROLE_o_email_sem_tipo_nao_ganha_marcador_falso():
    """Sem `log_kind` não há o que atribuir — e inventar `utm_campaign=email`
    seria pior que não marcar: viraria um balde onde tudo cai."""
    u = "https://ai.arq.br/x"
    assert main._marcar_url_do_email(u, "") == u


# ─────────────────────────────────────────────────────────────────────────────
#  (3) O PAR ACOPLADO — link marcado ↔ chave liberada
# ─────────────────────────────────────────────────────────────────────────────

def test_a_chave_ult_ATRAVESSA_o_saneamento_do_track():
    """🩸 As duas metades moram em arquivos diferentes e NADA as liga. Foi assim
    que `campo` morreu no dia em que nasceu (27/08) e que `chars`/`n`/`restam`
    quase morreram ontem."""
    corpo = sem_comentarios(corpo_de("track_event"))
    assert '_meta["ult"]' in corpo, (
        "a chave `ult` não é copiada pro meta — o marcador do e-mail chega ao "
        "servidor e é jogado fora em silêncio, e a atribuição volta a zero")
    assert 'payload.meta.get("ult")' in corpo, corpo[-400:]


def test_a_tela_MANDA_o_ult_junto_do_src():
    """A outra metade: de nada adianta o servidor aceitar se a tela não manda.
    E `src` (first-touch) tem que continuar indo — o funil depende dele."""
    js = sem_comentarios_js(fonte("aiarq-utils.js"))
    assert "aiarq_ult" in js, "a tela parou de guardar o último empurrão"
    assert "ult: _ult" in js, (
        "o `ult` não é mandado no meta do evento — a tela guarda e não conta")
    assert "src: _src" in js, (
        "o first-touch sumiu do evento: consertar o alcance não pode trocar o "
        "padrão do funil")


def test_o_ultimo_empurrao_NAO_vem_do_referrer():
    """🪤 Se o último empurrão fosse lido do `document.referrer`, navegação
    interna o sobrescreveria a cada clique — e dado que muda sozinho a cada
    página não atribui nada. Só marcador EXPLÍCITO na URL grava."""
    js = fonte("aiarq-utils.js")
    i = js.index("_capturaUltimoEmpurrao")
    bloco = js[i:js.index("})();", i)]
    assert "referrer" not in bloco, (
        "o último empurrão passou a ler o referrer: %s" % bloco[:300])
    assert "utm_source" in bloco and "origem" in bloco, bloco[:300]


def test_o_first_touch_continua_sem_se_sobrescrever():
    """🚨 CONTROLE do de cima, e regra da casa: consertar o ALCANCE não pode
    trocar o PADRÃO. O `aiarq_src` é first-touch e tem que continuar sendo."""
    js = fonte("aiarq-utils.js")
    i = js.index("_captureSource")
    bloco = js[i:js.index("})();", i)]
    assert "localStorage.getItem('aiarq_src')" in bloco and "return;" in bloco, (
        "o first-touch passou a se sobrescrever — o funil inteiro muda de "
        "significado sem ninguém pedir: %s" % bloco[:300])


# ─────────────────────────────────────────────────────────────────────────────
#  (4) O DOWNLOAD CONTADO NO SERVIDOR
# ─────────────────────────────────────────────────────────────────────────────

def test_o_download_deixa_rastro_no_SERVIDOR():
    """🩸 O arquivo saía e ninguém anotava. O clique do navegador mente de três
    jeitos: tem DOIS nomes de evento e o painel conta um; a tela de revisão não
    conta em lugar nenhum; e o caminho principal só registra desde 06/09."""
    corpo = sem_comentarios(corpo_de("download_file"))
    assert '"entrega:download"' in corpo, (
        "a rota voltou a entregar a planilha sem anotar que entregou")
    assert corpo.index('"entrega:download"') < corpo.index("return FileResponse("), (
        "o registro ficou DEPOIS do return — nunca roda")


def test_o_registro_do_download_NAO_trava_o_laco():
    """🪤 A rota é `async` e `_log_error` faz urllib bloqueante. Chamada direta,
    ela congelaria o servidor inteiro a cada download — a mesma doença que a
    trava de cobrança tinha e que foi consertada hoje."""
    corpo = sem_comentarios(corpo_de("download_file"))
    i = corpo.index('"entrega:download"')
    trecho = corpo[max(0, i - 220):i]
    assert "run_in_threadpool" in trecho, (
        "o registro do download roda no laço de eventos: %s" % trecho[-200:])


def test_entrega_download_e_diagnostico_e_nao_erro():
    """Uma linha por planilha entregue é bookkeeping. Fora da lista de
    diagnóstico, ela entope o painel de erros do motor no primeiro dia — foi
    exatamente o que `cobranca:regua` fez por 8 dias."""
    assert "entrega:download" in main._STAGES_DIAGNOSTICO

# ─────────────────────────────────────────────────────────────────────────────
#  (5) O ÚLTIMO EMPURRÃO RODANDO — não o fonte dele
#
#  🩸 Se este carimbo não gravar, as TRÊS partes do conserto ficam inertes e
#  eu só descubro em semanas — o padrão "nasceu morto" que já matou o
#  `download_memorial` e o `campo` do signup. Guarda de forma não responde
#  "gravou?"; este roda a função num motor JS e olha o que ficou guardado.
#
#  🪤 duktape não tem URLSearchParams nem localStorage: os dois são encenados
#  aqui. O que está sendo medido é a LÓGICA (leu o marcador? gravou? apagou o
#  que já estava?), não a implementação do navegador.
# ─────────────────────────────────────────────────────────────────────────────

_PALCO = r"""
var __GUARDADO = {};
var localStorage = {
  getItem: function(k){ return (k in __GUARDADO) ? __GUARDADO[k] : null; },
  setItem: function(k,v){ __GUARDADO[k] = String(v); }
};
var location = { search: '' };
function URLSearchParams(qs){
  this._m = {};
  String(qs || '').replace(/^\?/, '').split('&').forEach(function(par){
    if (!par) return;
    var i = par.indexOf('=');
    var k = i < 0 ? par : par.slice(0, i);
    var v = i < 0 ? '' : decodeURIComponent(par.slice(i + 1).replace(/\+/g, ' '));
    this._m[decodeURIComponent(k)] = v;
  }, this);
}
URLSearchParams.prototype.get = function(k){
  return (k in this._m) ? this._m[k] : null;
};
function __visita(qs){ location.search = qs; _capturaUltimoEmpurrao(); return __ult(); }
function __ult(){ return __GUARDADO['aiarq_ult'] || ''; }
'palco pronto';
"""


def _palco_js():
    from _jsbancada import motor
    from _corpo import corpo_js as _cjs
    return motor(_PALCO + _cjs("_capturaUltimoEmpurrao", "aiarq-utils.js"))


def test_a_visita_VINDA_DO_EMAIL_fica_guardada():
    """🚨 O guarda funcional. Sem isto, as três partes do conserto podem estar
    todas no lugar e a atribuição continuar em zero."""
    js = _palco_js()
    js.evaljs("__visita('?utm_source=email&utm_campaign=calibracao')")
    guardado = js.evaljs("__ult()")
    assert guardado, (
        "a visita vinda do e-mail NÃO foi guardada — o marcador do link morre "
        "no navegador e os 537 envios seguem inauditáveis")
    assert "email" in guardado and "calibracao" in guardado, guardado


def test_visita_SEM_marcador_nao_apaga_o_que_ja_estava():
    """🪤 O e-mail traz a pessoa hoje e o projeto nasce três dias depois. Se
    uma visita comum limpasse o carimbo, a conversão que mais importa — a que
    demora — seria justamente a que some."""
    js = _palco_js()
    js.evaljs("__visita('?utm_source=email&utm_campaign=retorno_30d')")
    antes = js.evaljs("__ult()")
    js.evaljs("__visita('')")
    js.evaljs("__visita('?job=abc')")
    assert js.evaljs("__ult()") == antes, (
        "navegação comum apagou o último empurrão: %r -> %r"
        % (antes, js.evaljs("__ult()")))


def test_um_empurrao_NOVO_sobrescreve_o_anterior():
    """CONTROLE do de cima: ele não pode virar first-touch disfarçado. Este
    carimbo responde 'o que trouxe a pessoa HOJE' — marcador novo manda."""
    js = _palco_js()
    js.evaljs("__visita('?utm_source=email&utm_campaign=retorno_30d')")
    js.evaljs("__visita('?utm_source=instagram')")
    agora = js.evaljs("__ult()")
    assert "instagram" in agora and "retorno_30d" not in agora, agora
