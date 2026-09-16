# -*- coding: utf-8 -*-
"""Entrar na aba Projetos não pode mostrar só os que deram erro.

🩸 16/09/2026, Pedro: *"quando a gente entra na página de projeto, tá filtrado
automaticamente os com erro. Eu sempre entro e acho que tá tudo errado. Mas, na
verdade, isso é coisa antiga."*

A causa não era o padrão da página (`_projectsFilter` nasce 'tudo'): era o
filtro GRUDANDO. O cartão "Taxa de Sucesso" leva pra aba já filtrada por erro —
de propósito — e esse estado é global. Depois de UM clique nele, toda volta pra
aba Projetos vinha filtrada, mostrando o histórico inteiro de erros como se
fosse hoje.

📏 O que o painel mostrava nessa hora: 11 projetos com erro em 45 dias, sendo 5
avaliações nossas e 6 de cliente — e 5 desses 6 clientes voltaram e concluíram.
Tela de incêndio pra um fogo que já apagou.

🚨 Estes guardas RODAM o JavaScript da tela (dukpy), não leem o fonte: foi uma
varredura por mutação, em 06/09, que provou cegos os guardas de texto.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _jsbancada import fonte_html, funcao_js, motor  # noqa: E402

_ADMIN = "admin.html"

# encena o mínimo de DOM que as três funções tocam
_PRELUDIO = """
var _marcados = [];
var document = {
  querySelectorAll: function(){ return { forEach: function(){} }; },
  querySelector: function(){ return null; },
  getElementById: function(){ return null; }
};
function loadProjects(){ _marcados.push('carregou:' + _projectsFilter); }
function closeSidebar(){}
function loadUsers(){}
function loadFilhotes(){}
function loadDashboardStats(){}
function loadOrigem(){}
function carregarBadgeMensagens(){}
"""


def _tela():
    src = fonte_html(_ADMIN)
    js = motor(_PRELUDIO)
    js.evaljs("var _projectsFilter = 'tudo'; var _projectsRefreshTimer = null;")
    js.evaljs(funcao_js("setProjectsFilter", _ADMIN, src))
    js.evaljs("var _filtroVeioDeCartao = false;")
    js.evaljs(funcao_js("_filtroPadraoAoEntrar", _ADMIN, src))
    js.evaljs(funcao_js("irParaProjetosComErro", _ADMIN, src))
    js.evaljs(funcao_js("irParaProjetos", _ADMIN, src))
    # `switchTab` inteira é grande e mexe em muito DOM; o que este guarda mede é
    # o ramo da aba Projetos, encenado igual ao do fonte (ver o teste de fonte
    # no fim, que prova que o ramo continua chamando as duas funções na ordem).
    js.evaljs("function entrarNaAbaProjetos(){ _filtroPadraoAoEntrar(); loadProjects(); }")
    js.evaljs("function switchTab(){}")
    return js


def _filtro(js):
    return js.evaljs("_projectsFilter")


def test_entrar_na_aba_SOLTA_o_filtro_de_erro_que_ficou_de_antes():
    """O caso do Pedro: o filtro ficou em 'erros' de uma visita anterior e ele
    entra pelo menu. Tem que abrir em 'tudo'."""
    js = _tela()
    js.evaljs("_projectsFilter = 'erros';")        # sobra da navegação de antes
    js.evaljs("entrarNaAbaProjetos();")
    assert _filtro(js) == "tudo", "o filtro de erro grudou na aba"
    assert js.evaljs("_marcados[_marcados.length-1]") == "carregou:tudo"


def test_o_cartao_de_erro_CONTINUA_levando_pra_lista_de_erro():
    """🪤 Controle positivo: soltar o filtro não pode matar o atalho que existe
    justamente pra ver os erros."""
    js = _tela()
    js.evaljs("irParaProjetosComErro(); entrarNaAbaProjetos();")
    assert _filtro(js) == "erros", "o clique explícito no cartão tem que valer"
    assert js.evaljs("_marcados[_marcados.length-1]") == "carregou:erros"


def test_o_cartao_de_erro_vale_UMA_vez_so():
    js = _tela()
    js.evaljs("irParaProjetosComErro(); entrarNaAbaProjetos();")   # 1ª: filtrada
    js.evaljs("entrarNaAbaProjetos();")                            # 2ª: limpa
    assert _filtro(js) == "tudo", "o cartão não pode fixar o filtro pra sempre"


def test_CONTROLE_o_atalho_normal_continua_em_tudo():
    js = _tela()
    js.evaljs("irParaProjetos(); entrarNaAbaProjetos();")
    assert _filtro(js) == "tudo"


def test_CONTROLE_escolher_um_filtro_na_propria_aba_vale():
    """Quem clica em 'Hoje' dentro da aba não pode ser sobrescrito na hora."""
    js = _tela()
    js.evaljs("setProjectsFilter('hoje');")
    assert _filtro(js) == "hoje"
    assert js.evaljs("_marcados[_marcados.length-1]") == "carregou:hoje"


def test_a_aba_de_projetos_no_switchTab_chama_as_duas_na_ordem():
    """🪤 Guarda de FONTE, e assumido como tal: o `switchTab` real é grande
    demais pra encenar aqui. O que ele prova é só que o ramo da aba continua
    chamando `_filtroPadraoAoEntrar()` ANTES de `loadProjects()` — se alguém
    inverter ou remover, a tela volta a abrir filtrada."""
    src = fonte_html(_ADMIN)
    assert "if (tabName === 'projetos') { _filtroPadraoAoEntrar(); loadProjects(); }" in src, (
        "o ramo da aba Projetos mudou — refaça este guarda junto")
