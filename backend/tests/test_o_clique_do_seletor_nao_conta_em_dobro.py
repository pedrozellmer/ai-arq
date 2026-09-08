# -*- coding: utf-8 -*-
"""Um gesto do cliente, um evento. O seletor de arquivo contava dois.

🩸 08/09/2026 — MÉTRICA INFLADA ~1,9× NO ÚNICO PONTO QUE IMPORTA.

Medido em toda a base, pares do MESMO evento a menos de 600 ms:

| evento | total | pares | % |
|---|---|---|---|
| **`clique:abrir-seletor-arquivo`** | 123 | **58** | **47,2%** |
| `clique:processar-projeto` | 47 | 3 | 6,4% |
| os outros sete | — | 0 | 0,0% |

Não é gente clicando duas vezes — é específico deste elemento. `<label for=X>`
dispara o rastreador delegado uma vez E manda o navegador **sintetizar** um
clique em X; como o `<input type=file>` mora DENTRO do label
(dashboard.html ~494), o segundo clique sobe pelo mesmo `data-track` e é
contado de novo.

🚨 Por que dói: é o número que a gente olha pra saber onde o cliente desiste.
"123 abriram o seletor e 47 processaram" parecia 38%; o real é ~65 e ~72%.
Um mede um funil que não existe. Ver
[[project_o_buraco_do_seletor_de_arquivo_20260908]].

Este arquivo RODA o rastreador — ler o `.js` provaria que a linha existe, não
que ela para de contar duas vezes.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

from _bancada_js import Pagina  # noqa: E402

# Captura o handler delegado ANTES de o arquivo ser carregado (o
# `document.addEventListener` da bancada é vazio de propósito).
_PRELUDIO = r"""
window.__cliqueHandler = null;
document.addEventListener = function (tipo, fn) {
  if (tipo === 'click') { window.__cliqueHandler = fn; }
};
1;
"""

# Reproduz o DOM real: um <div> dentro de um <label for="file-input">, e o
# <input id="file-input"> dentro do MESMO label.
_MONTA_DOM = r"""
window.__eventos = [];
window.trackEvent = function (nome, meta) {
  window.__eventos.push({ nome: nome, meta: meta || {} });
};

var input = { tagName: 'INPUT', id: 'file-input' };
var label = {
  tagName: 'LABEL', htmlFor: 'file-input', control: input,
  textContent: 'Arraste os arquivos do projeto aqui ou clique para selecionar',
  getAttribute: function (a) {
    if (a === 'data-track') return 'abrir-seletor-arquivo';
    return null;
  }
};
var divDentro = { tagName: 'DIV', closest: function () { return label; } };
label.closest = function () { return label; };
input.closest = function () { return label; };   // o input mora DENTRO do label

var botao = {
  tagName: 'BUTTON', textContent: 'Processar Projeto',
  getAttribute: function (a) {
    if (a === 'data-track') return 'processar-projeto';
    return null;
  }
};
botao.closest = function () { return botao; };

window.__alvos = { divDentro: divDentro, input: input, label: label, botao: botao };
1;
"""


def _pagina():
    p = Pagina(arquivos=("aiarq-utils.js",), prelude_extra=_PRELUDIO)
    p.eval(_MONTA_DOM)
    return p


def _clica(p, alvo):
    p.chama("window.__cliqueHandler({ target: window.__alvos.%s }); 1;" % alvo)


def _nomes(p):
    import json
    return json.loads(p.eval(
        "JSON.stringify(window.__eventos.map(function(e){return e.nome;}))"))


def test_o_rastreador_foi_mesmo_instalado():
    """Controle de cenário: sem o handler, todo teste daqui é vazio e verde."""
    p = _pagina()
    assert p.eval("window.__cliqueHandler ? 1 : 0") == 1, (
        "o listener delegado não foi capturado — os testes abaixo não provariam nada")


def test_um_gesto_no_seletor_vira_UM_evento():
    """O gesto real: clique no dropzone + o clique que o label sintetiza."""
    p = _pagina()
    _clica(p, "divDentro")   # o cliente clica na área
    _clica(p, "input")       # o navegador sintetiza no controle do label
    assert _nomes(p) == ["clique:abrir-seletor-arquivo"], (
        "dois eventos pro mesmo gesto — a conta de 'abriu o seletor' infla "
        "~1,9×: " + str(_nomes(p)))


def test_clicar_no_proprio_label_continua_registrando():
    """CONTROLE POSITIVO nº1: não pode sumir com o evento."""
    p = _pagina()
    _clica(p, "label")
    assert _nomes(p) == ["clique:abrir-seletor-arquivo"]


def test_botao_normal_nao_e_afetado():
    """CONTROLE POSITIVO nº2: a peneira é SÓ do par label→controle."""
    p = _pagina()
    _clica(p, "botao")
    _clica(p, "botao")
    assert _nomes(p) == ["clique:processar-projeto", "clique:processar-projeto"], (
        "dois cliques de verdade em botão são dois eventos — não é dedupe por "
        "tempo: " + str(_nomes(p)))


def test_input_de_OUTRO_label_nao_e_engolido():
    """🪤 A peneira olha o controle QUE ESTE label comanda. Um input que só
    por acaso mora dentro de outro elemento rastreado continua contando."""
    p = _pagina()
    p.eval("""
      var outro = { tagName: 'INPUT', id: 'nao-e-do-label' };
      outro.closest = function () { return window.__alvos.label; };
      window.__alvos.outro = outro; 1;
    """)
    _clica(p, "outro")
    assert _nomes(p) == ["clique:abrir-seletor-arquivo"], (
        "o label comanda 'file-input', não este: o evento tem que sair")


def test_so_LABEL_e_peneirado():
    """🪤 Sem a checagem de tagName o mutante é EQUIVALENTE num navegador — só
    `<label>` tem `.control`. Mas a regra é "o clique que o LABEL sintetizou",
    não "qualquer elemento que aponte pro alvo", e é a regra que este teste
    fixa: um elemento rastreado que por acaso referencie o alvo continua
    contando. Sem isto, a linha ficaria sem ninguém provando por que existe.
    """
    p = _pagina()
    p.eval("""
      var alvoQualquer = { tagName: 'INPUT', id: 'algum-campo' };
      var caixa = {
        tagName: 'DIV', control: alvoQualquer,
        textContent: 'Envelope do bot\\u00e3o',
        getAttribute: function (a) {
          if (a === 'data-track') return 'processar-bloqueado';
          return null;
        }
      };
      alvoQualquer.closest = function () { return caixa; };
      window.__alvos.alvoQualquer = alvoQualquer; 1;
    """)
    _clica(p, "alvoQualquer")
    assert _nomes(p) == ["clique:processar-bloqueado"], (
        "só o par label→controle é peneirado; um <div> rastreado que aponte "
        "pro alvo não sintetizou clique nenhum: " + str(_nomes(p)))


def test_o_rotulo_visivel_continua_indo_junto():
    """A peneira não pode ter comido o `meta.rotulo`, que é como o painel é
    lido sem abrir o HTML."""
    p = _pagina()
    _clica(p, "divDentro")
    rot = p.eval("window.__eventos[0].meta.rotulo || ''")
    assert "Arraste os arquivos" in rot, rot
