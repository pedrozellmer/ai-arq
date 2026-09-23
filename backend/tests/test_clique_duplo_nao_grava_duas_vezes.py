# -*- coding: utf-8 -*-
"""Dois cliques no mesmo botão não podem virar duas linhas no banco.

🩸 23/09/2026 — um cliente avaliou o produto UMA vez e o painel mostrou DUAS.
Duas linhas de NPS 10, mesmo projeto (`d4abb4ae`), mesmo contexto
(`after_download`), separadas por **197 milissegundos**:

    9825c2b5 ... 16:36:33.638
    b7b2c94b ... 16:36:33.835

Ninguém avalia duas vezes em dois décimos de segundo. Foi o botão "Enviar"
aceitando o 2º clique enquanto o 1º ainda estava no ar — `submitNPS` do
dashboard não desabilitava nada, e `/api/nps` é INSERT puro.

📊 São **15 avaliações em toda a história do produto**: uma linha fantasma é
**6,7% da base**, move a média e inventa um promotor que não existe.

🔑 O conserto mora em `aiarq-utils.js` (21 das 23 páginas) porque o site tem
**73 chamadas que escrevem** em 14 arquivos. Uma a uma, alguma ficaria de
fora — e a próxima duplicata pode ser um projeto, um e-mail ou um pagamento.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _jsbancada import fonte_html, funcao_js, motor  # noqa: E402

_ARQ = "aiarq-utils.js"

#: Um DOM de mentira: elemento com atributos, e um `closest` que devolve ele
#: mesmo quando o seletor bate com a tag.
_PRELUDIO = """
function Elemento(tag, opts) {
  opts = opts || {};
  this.tagName = tag.toUpperCase();
  this.type = opts.type || '';
  this.disabled = !!opts.disabled;
  this.attrs = opts.attrs || {};
  this.bloqueado = false;
  this.defaultPrevenido = false;
}
Elemento.prototype.hasAttribute = function (n) {
  return Object.prototype.hasOwnProperty.call(this.attrs, n);
};
Elemento.prototype.getAttribute = function (n) {
  return this.hasAttribute(n) ? this.attrs[n] : null;
};
Elemento.prototype.setAttribute = function (n, v) { this.attrs[n] = v; };
Elemento.prototype.closest = function (sel) {
  var t = this.tagName.toLowerCase();
  if (sel.indexOf(t) >= 0) return this;
  if (this.attrs['role'] === 'button' && sel.indexOf('role') >= 0) return this;
  return null;
};
function Evento(el) {
  this.target = el;
  this.parado = false;
  this.prevenido = false;
  var self = this;
  this.stopImmediatePropagation = function () { self.parado = true; };
  this.preventDefault = function () { self.prevenido = true; };
}
null;
"""


def _janela_do_arquivo():
    """O valor REAL de `_JANELA_DUPLO_MS`, lido do fonte que vai pra produção.

    🩸 A 1ª versão deste guarda declarava `_JANELA_DUPLO_MS = 700` no próprio
    prelúdio — e aí a sabotagem que zerava a janela no arquivo de produção
    passava VERDE. O teste exercitava o meu dublê, não o código.
    🔑 Irmã de [[feedback_duble_com_assinatura_exata_desarma_calado]].
    """
    import re
    m = re.search(r"var\s+_JANELA_DUPLO_MS\s*=\s*(\d+)\s*;", fonte_html(_ARQ))
    assert m, "nao achei _JANELA_DUPLO_MS em %s" % _ARQ
    return int(m.group(1))


JANELA = _janela_do_arquivo()


def test_a_janela_precisa_pegar_um_duplo_clique_DE_VERDADE():
    """🚨 Sem isto, zerar a janela no arquivo passa verde e a trava vira enfeite.

    O duplo clique do sistema operacional é ~500 ms; abaixo disso a trava não
    pega o acidente que gerou a linha fantasma (197 ms).
    """
    assert JANELA >= 400, (
        "janela de %d ms nao pega duplo clique: a trava virou decoracao" % JANELA)
    assert JANELA <= 1500, (
        "janela de %d ms atrapalha clique repetido intencional" % JANELA)


def _motor():
    js = motor(_PRELUDIO)
    js.evaljs("var _JANELA_DUPLO_MS = %d; null;" % JANELA)
    js.evaljs(funcao_js("_ehAcionavel", _ARQ))
    js.evaljs(funcao_js("_guardaDeCliqueDuplo", _ARQ))
    return js


def _ler(js, expr):
    """🪤 dukpy recusa `undefined` como resultado — tudo sai por JSON."""
    return json.loads(js.evaljs("JSON.stringify(%s)" % expr))


def _rodar(js, codigo):
    """Declara sem devolver nada — o `null;` no fim é o que dukpy aceita."""
    js.evaljs(codigo + " null;")


def _clicar(js, tag, quando, attrs=None, tipo="", desabilitado=False, elem="el"):
    _rodar(js, "var %s = new Elemento(%s, {type: %s, disabled: %s, attrs: %s});"
           % (elem, json.dumps(tag), json.dumps(tipo),
              "true" if desabilitado else "false", json.dumps(attrs or {})))
    return _reclicar(js, quando, elem)


def _reclicar(js, quando, elem="el"):
    _rodar(js, "var ev = new Evento(%s);" % elem)
    return {
        "barrado": _ler(js, "!!_guardaDeCliqueDuplo(ev, %d)" % quando),
        "parado": _ler(js, "!!ev.parado"),
        "prevenido": _ler(js, "!!ev.prevenido"),
    }


# ══════════════════════════════════════════════════════════════════════════
#  O CASO REAL
# ══════════════════════════════════════════════════════════════════════════
def test_os_197_MILISSEGUNDOS_do_caso_real_sao_barrados():
    """O intervalo exato das duas linhas de NPS que apareceram no painel."""
    js = _motor()
    primeiro = _clicar(js, "button", 1000000)
    assert primeiro["barrado"] is False, "o 1o clique TEM que passar"
    segundo = _reclicar(js, 1000000 + 197)
    assert segundo["barrado"] is True, "o 2o clique virou a linha fantasma"
    assert segundo["parado"] is True, "sem stopImmediatePropagation o POST sai"
    assert segundo["prevenido"] is True


def test_o_PRIMEIRO_clique_nunca_e_atrapalhado():
    js = _motor()
    for tag in ("button", "a", "input"):
        r = _clicar(js, tag, 500000, attrs={"onclick": "x()"}, tipo="submit",
                    elem="e_" + tag)
        assert r["barrado"] is False, tag


def test_depois_da_janela_o_botao_volta_a_funcionar():
    """Quem clica de novo 1s depois quer clicar de novo mesmo."""
    js = _motor()
    _clicar(js, "button", 2000000)
    assert _reclicar(js, 2000000 + JANELA + 1)["barrado"] is False
    assert _reclicar(js, 2000000 + 5000)["barrado"] is False


def test_o_limite_da_janela_e_o_do_ARQUIVO():
    js = _motor()
    _clicar(js, "button", 3000000)
    assert _reclicar(js, 3000000 + JANELA - 1)["barrado"] is True
    js2 = _motor()
    _clicar(js2, "button", 3000000)
    assert _reclicar(js2, 3000000 + JANELA)["barrado"] is False


def test_DOIS_botoes_diferentes_nao_travam_um_ao_outro():
    """Clicar em Salvar e logo em Fechar é uso normal, não duplo clique."""
    js = _motor()
    assert _clicar(js, "button", 4000000, elem="a1")["barrado"] is False
    assert _clicar(js, "button", 4000000 + 50, elem="a2")["barrado"] is False


# ══════════════════════════════════════════════════════════════════════════
#  QUEM ENTRA NA TRAVA, E QUEM NÃO
# ══════════════════════════════════════════════════════════════════════════
def test_botao_e_submit_entram():
    js = _motor()
    assert _ler(js,"_ehAcionavel(new Elemento('button', {}))") is True
    assert _ler(js,"_ehAcionavel(new Elemento('input', {type:'submit'}))") is True
    assert _ler(js,"_ehAcionavel(new Elemento('input', {type:'button'}))") is True


def test_link_de_NAVEGACAO_pura_passa_direto():
    """Link que só leva a outra página pode ser clicado à vontade."""
    js = _motor()
    assert _ler(js,"_ehAcionavel(new Elemento('a', {}))") is False


def test_link_que_AGE_entra_na_trava():
    """🔑 O NPS do dashboard sai de um <a onclick=...> — o caso real."""
    js = _motor()
    assert _ler(js,
        "_ehAcionavel(new Elemento('a', {attrs:{onclick:'baixar()'}}))") is True


def test_campo_de_texto_e_checkbox_ficam_de_FORA():
    js = _motor()
    for t in ("text", "checkbox", "radio", "file", "number"):
        assert _ler(js, "_ehAcionavel(new Elemento('input', {type:%s}))"
                  % json.dumps(t)) is False, t


def test_quem_precisa_de_clique_repetido_marca_data_repetivel():
    """Paginação, +/-, teclado numérico: clique rápido de propósito."""
    js = _motor()
    assert _ler(js,
        "_ehAcionavel(new Elemento('button', {attrs:{'data-repetivel':''}}))") is False
    r = _clicar(js, "button", 6000000, attrs={"data-repetivel": ""})
    assert r["barrado"] is False
    assert _reclicar(js, 6000000 + 10)["barrado"] is False


def test_botao_ja_desabilitado_nao_interessa():
    js = _motor()
    assert _ler(js,"_ehAcionavel(new Elemento('button', {disabled:true}))") is False


def test_clique_fora_de_qualquer_botao_nao_quebra():
    js = _motor()
    _rodar(js, "var vazio = new Elemento('div', {});")
    _rodar(js, "var ev = new Evento(vazio);")
    assert _ler(js, "!!_guardaDeCliqueDuplo(ev, 1)") is False
    assert _ler(js, "!!ev.parado") is False


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLES — provam que o guarda REPROVA
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_sem_a_trava_os_dois_cliques_passariam():
    """Encena o comportamento VELHO: todo clique vira POST."""
    js = _motor()
    _rodar(js, """
    function _semTrava(ev) { return false; }
    var n = 0;
    function _postar() { n++; }
    """)
    _rodar(js, "var el = new Elemento('button', {});")
    for t in (1000000, 1000197):
        _rodar(js, "var ev = new Evento(el);")
        _rodar(js, "if (!_semTrava(ev, %d)) _postar();" % t)
    assert _ler(js, "n") == 2, (
        "o controle parou de provar: sem trava TEM que postar 2x")


def test_CONTROLE_sem_stopImmediatePropagation_o_handler_ainda_rodaria():
    """Barrar sem parar a propagação não impede o POST — só some o efeito."""
    js = _motor()
    _rodar(js, """
    var postou = 0;
    function _meioConserto(ev, agora) {
      var el = ev.target.closest('button');
      var ultimo = Number(el.getAttribute('data-aiarq-clique') || 0);
      if (ultimo && (agora - ultimo) < 700) { return true; }  // sem stop*
      el.setAttribute('data-aiarq-clique', String(agora));
      return false;
    }
    var el2 = new Elemento('button', {});
    var e1 = new Evento(el2); _meioConserto(e1, 1000);
    var e2 = new Evento(el2); _meioConserto(e2, 1100);
    """)
    assert _ler(js, "!!e2.parado") is False, (
        "o controle parou de provar: o meio-conserto NAO para a propagacao")
    # e o nosso para:
    js2 = _motor()
    _clicar(js2, "button", 1000)
    assert _reclicar(js2, 1100)["parado"] is True
