# -*- coding: utf-8 -*-
"""A tipologia da obra não pode vir escolhida por nós.

🩸 07/11/2026. O `<select id="project-typology">` abria em "Escritório
corporativo", a primeira opção, sem nenhuma em branco. Em 90 dias, 174 de 329
projetos (53%) saíram como escritório, e em 13 deles a própria IA escreveu que
"a prancha é de residência". O código vai longe: dica no prompt da IA
(`analyzer._TYPOLOGY_HINT`), cabeçalho da planilha ("ESCRITÓRIO /
CORPORATIVO", "DEPARTAMENTOS"), linha "Tipologia" do memorial e prazo sugerido
no cronograma. Uma casa de 64 m² saiu com o cabeçalho de escritório.

O conserto: o campo abre vazio e o clique em "Processar" pede a escolha
(`_faltaTipologia`), deixando o rastro `processar_bloqueado` motivo
`tipologia`, como o dos termos.
"""
import json
import os
import re
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)
sys.path.insert(0, os.path.dirname(_AQUI))

from _jsbancada import fonte_html, funcao_js, motor  # noqa: E402


def _site():
    return fonte_html("dashboard.html").replace("\r\n", "\n")


def _select(site):
    return re.search(r'<select id="project-typology".*?</select>', site, re.S).group(0)


def _abre_vazio(bloco):
    """A 1ª opção é a vazia e é ela a marcada; nenhuma tipologia vem marcada."""
    opcoes = re.findall(r"<option\b([^>]*)>", bloco)
    if not opcoes:
        return False
    primeira = opcoes[0]
    return ('value=""' in primeira and "selected" in primeira
            and not any("selected" in o for o in opcoes[1:]))


def test_o_campo_abre_sem_tipologia():
    assert _abre_vazio(_select(_site())), "a tipologia voltou a vir marcada"


def test_CONTROLE_o_campo_de_antes_reprova():
    antes = ('<select id="project-typology" class="x">\n'
             '  <option value="office">Escrit&oacute;rio corporativo</option>\n'
             '  <option value="residential">Residencial</option>\n'
             '</select>')
    assert not _abre_vazio(antes)


def test_o_clique_pede_a_tipologia_antes_de_enviar():
    site = _site()
    i = site.index("btnProcess.addEventListener('click', async () => {")
    corpo = site[i:site.index("ensureCpfBeforeCheckout()", i)]
    k = corpo.index("if (_faltaTipologia()) return;")
    assert corpo.index("termsCheckbox.checked") < k < corpo.index("ensureAgeConfirmed()"), (
        "a conferência da tipologia saiu do lugar (depois dos termos, antes da idade)")
    assert k < corpo.index("_umEnvioPorVez(startProcessing);"), (
        "o envio sai antes de conferir a tipologia")


_PRELUDIO = r"""
var __ev = [], __avisos = [], __foco = 0;
var __sel = { value: '', scrollIntoView: function () {}, focus: function () { __foco++; } };
var document = { getElementById: function (i) { return i === 'project-typology' ? __sel : null; } };
var window = { trackEvent: function (n, m) { __ev.push([n, m]); } };
var notify = { warn: function (m) { __avisos.push(String(m)); } };
1;
"""


def _roda(valor):
    js = motor(_PRELUDIO)
    js.evaljs(funcao_js("_faltaTipologia", "dashboard.html", _site()) + "\n;1;")
    js.evaljs("__sel.value = %s; 1;" % json.dumps(valor))
    falta = js.evaljs("_faltaTipologia()")
    return falta, json.loads(js.evaljs(
        "JSON.stringify({ev: __ev, avisos: __avisos, foco: __foco})"))


def test_sem_escolha_avisa_registra_e_leva_ao_campo():
    falta, e = _roda("")
    assert falta is True
    assert e["ev"] == [["processar_bloqueado", {"motivo": "tipologia"}]], e
    assert e["avisos"] and "tipologia" in e["avisos"][0].lower(), e
    assert e["foco"] == 1, e


def test_com_escolha_segue_calado():
    falta, e = _roda("residential")
    assert falta is False
    assert e == {"ev": [], "avisos": [], "foco": 0}, e
