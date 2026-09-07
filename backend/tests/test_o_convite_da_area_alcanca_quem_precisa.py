# -*- coding: utf-8 -*-
"""O convite da área existia há 43 dias e não chegava em 46 dos 76 que precisam.

🩸 02/09/2026. A mini-revisão (`/api/project/{job}/inform-area`) refaz a planilha
na hora, sem IA e sem custo, desde 21/07. Medido no acervo:

    precisam da mini-revisão ......... 76 projetos
    são convidados hoje ............. 30  (39 em cada 100)
    NUNCA foram usados ................ 0 acionamentos em 293 projetos

E não é falta de tráfego: o convite apareceu em 18 projetos de 15 clientes, e
**10 deles estavam com a tela de revisão aberta**. Viram e não clicaram.

Duas condições calavam o convite exatamente para quem mais precisa:

  🚪 PORTA 1 — ter área na capa era VETO ABSOLUTO (`if (!noArea) return;`).
     33 projetos, 358 linhas de m² em branco (mediana 7, máximo 43), nunca
     viram o convite porque a capa trazia um número. 12 deles já cumpriam
     todo o resto da regra: era um veto de uma linha só.
     🪤 E a área da capa já foi medida como MÉDIA DE CÔMODOS — às vezes não é
     a área do imóvel. Era esse número que calava o pedido.

  🚪 PORTA 2 — o gatilho era uma PENEIRA DE TEXTO: só aparecia se a IA tivesse
     escrito uma de 4 frases exatas em `observations`. Em 22 projetos (127
     linhas) ela disse a mesma coisa com outras palavras — "Área total não
     extraída do DXF" — e o convite não saiu. Gatilho de produto pendurado no
     vocabulário livre do modelo.

🔑 Agora o gatilho é o FATO (existe linha de m² zerada) e a área da capa muda o
TEXTO do convite, não a decisão de mostrá-lo. Alcance: 30 → 76.

🪤 O EFEITO COLATERAL QUE A PORTA 1 CRIA: com o campo pré-preenchido com a área
da capa, o gesto provável é CONFIRMAR. Carimbar "informado por você" em cima de
área que a planta mediu escreveria procedência falsa na capa da planilha (e em
`spreadsheet.py`, que troca a linha de premissa por causa desse mesmo campo).
Confirmar não é informar — ver `_confirma_o_que_ja_tinha`.
"""
import html as _html
import json
import os
import re
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import dukpy                                                    # noqa: E402
import pytest                                                   # noqa: E402

from _corpo import corpo_js, fonte                              # noqa: E402
from _navegador import sem_await                                # noqa: E402

# 🪤 A bancada que EXECUTA `inform_project_area` (só rede, banco e disco
# dublados) mora no guarda do pé-direito. Importar em vez de copiar: duas
# cópias da mesma bancada divergem sozinhas, e foi copiando régua que esta casa
# já deixou absolvição pra trás.
from test_pede_o_pe_direito_depois import _bancada              # noqa: E402

import main                                                     # noqa: E402

_PROJ = fonte("projeto.html")


def _corpo_js(nome, src=None):
    """🪤 Este extrator nasceu AQUI e virou cópia quando a tela da revisão
    ganhou o mesmo convite (02/09). Duas cópias da mesma regra é exatamente o
    defeito que a gente passou o dia inteiro consertando — mora em `_corpo.py`,
    junto do `corpo_de`."""
    return corpo_js(nome, "projeto.html", _PROJ if src is None else src)


def _js_limpo(nome):
    return "\n".join(l for l in _corpo_js(nome).splitlines()
                     if not l.strip().startswith("//"))


#: Todo id que EXISTE em projeto.html. getElementById de qualquer outro
#: devolve null — igualzinho ao navegador.
_IDS_DA_TELA = sorted(set(re.findall(r'\bid="([^"\s]+)"', _PROJ)))


def _bloco_do_script():
    """O <script> onde o convite mora — o escopo que ele tem no navegador."""
    i = _PROJ.find("function maybeShowAreaPrompt(")
    assert i > 0, "o convite sumiu de projeto.html"
    ini = _PROJ.rfind("<script", 0, i)
    fim = _PROJ.find("</script>", i)
    assert 0 < ini < i < fim, "não achei o <script> que contém o convite"
    return _PROJ[ini:fim]


def _dependencias_js(bloco):
    """As MESMAS coisas que o convite tem à mão no navegador — nada além."""
    linha = re.search(r"^const _AREA_M2_UI = .*$", bloco, re.M)
    assert linha, "a lista de unidades de área sumiu do bloco do convite"
    return linha.group(0) + "\n" + corpo_js("esc", src=bloco) + "\n"


def _dom_de_ensaio():
    """Um DOM com EXATAMENTE os ids da tela — id que a página não tem devolve
    null, igualzinho ao navegador, e entra em `_faltaram`."""
    return """
var _pedidos = [], _faltaram = [], _avisos = [], _escChamado = 0;
var _IDS = %s;
var _els = {};
for (var _i = 0; _i < _IDS.length; _i++) {
  (function(id){
    _els[id] = { id: id, textContent: '', innerHTML: '', value: '',
                 className: '', disabled: false,
                 escondido: true,
                 classList: {
                   remove: function(c){ if (c === 'hidden') _els[id].escondido = false; },
                   add: function(c){ if (c === 'hidden') _els[id].escondido = true; } } };
  })(_IDS[_i]);
}
var document = { getElementById: function(id){
  _pedidos.push(id);
  if (!_els[id]) { _faltaram.push(id); return null; }
  return _els[id];
} };
var window = {};
var console = {
  warn: function(){ _avisos.push(Array.prototype.slice.call(arguments).join(' ')); },
  log: function(){},
  error: function(){ _avisos.push('erro'); } };
""" % json.dumps(_IDS_DA_TELA)


def rodar_o_convite(proj, items):
    """EXECUTA `maybeShowAreaPrompt` num DOM montado com os ids REAIS da tela."""
    bloco = _bloco_do_script()
    # o `esc` da PÁGINA, só que contado.
    conta_esc = ("\nvar _escReal = esc; "
                 "esc = function(s){ _escChamado++; return _escReal(s); };\n")
    chamada = """
maybeShowAreaPrompt(%s, %s);
JSON.stringify({
  apareceu: !_els['area-prompt'].escondido,
  titulo: _els['area-prompt-titulo'].textContent,
  texto: _els['area-prompt-texto'].innerHTML,
  valor: String(_els['area-input'].value),
  faltaram: _faltaram, avisos: _avisos, esc: _escChamado
});
""" % (json.dumps(proj), json.dumps(items))
    return json.loads(dukpy.evaljs(
        _dom_de_ensaio() + _dependencias_js(bloco) + conta_esc
        + corpo_js("maybeShowAreaPrompt", src=bloco) + chamada))


def rodar_o_envio(valor_digitado, resposta=None):
    """EXECUTA `submitInformedArea` — o BOTÃO que o convite oferece.

    🪤 06/09/2026 — este caminho não era executado por teste nenhum. O guarda
    dos ids conferia só `maybeShowAreaPrompt`, que nunca toca em `area-submit`:
    sumindo esse id, o cliente via o convite, digitava a área, clicava em
    "Completar itens de área" e o `btn.disabled = true` estourava em null. Nada
    acontecia e a bancada ficava verde.

    🪤 `await` não roda no Duktape — `sem_await` tira o adiamento e mantém a
    sequência (mesma régua do `_navegador.py`). Os dublês são SÍNCRONOS.
    """
    bloco = _bloco_do_script()
    resposta = ({"ok": True, "status": 200, "filled_count": 7}
                if resposta is None else resposta)
    dubles = """
var _fetches = [], _recarregou = 0;
var API_BASE = 'https://api.example.com';
var jobId = 'job-guarda-01';
var sb = { auth: { getSession: function(){
  return { data: { session: { access_token: 'jwt-de-mentira' } } }; } } };
var _RESP = %s;
function fetch(url, opts){
  opts = opts || {};
  _fetches.push({url: String(url), method: opts.method || 'GET',
                 body: String(opts.body || '')});
  return { ok: !!_RESP.ok, status: _RESP.status,
           json: function(){ return _RESP; },
           text: function(){ return String(_RESP.texto || ''); } };
}
function setTimeout(f, ms){ _recarregou++; }
""" % json.dumps(resposta)
    chamada = """
_els['area-input'].value = %s;
submitInformedArea();
JSON.stringify({
  faltaram: _faltaram, avisos: _avisos, fetches: _fetches,
  msg: String(_els['area-msg'].textContent),
  desabilitou: !!_els['area-submit'].disabled,
  recarregou: _recarregou
});
""" % json.dumps(str(valor_digitado))
    return json.loads(dukpy.evaljs(
        _dom_de_ensaio() + dubles
        + sem_await(corpo_js("submitInformedArea", src=bloco)) + chamada))


def _linha_vazia(unidade="m²", obs=""):
    return {"unit": unidade, "quantity": 0, "description": "Piso ceramico",
            "observations": obs}


def test_CONTROLE_o_banco_de_ensaio_reprova_id_que_nao_existe():
    """🧪 O DOM de mentira só vale se ele NÃO inventar elemento."""
    assert "area-prompt" in _IDS_DA_TELA and "area-prompt-titulo" in _IDS_DA_TELA
    assert "area-prompt-box" not in _IDS_DA_TELA
    r = rodar_o_convite({"total_area": 290.0}, [_linha_vazia()])
    assert r["apareceu"] and not r["faltaram"] and not r["avisos"], r


# ── O extrator, antes de confiar nele ──────────────────────────────────────
def test_CONTROLE_o_extrator_js_para_no_fim_da_funcao():
    c = _corpo_js("maybeShowAreaPrompt")
    assert "area-prompt" in c, "não pegou a função certa"
    assert "maybeShowPeDireitoPrompt" not in c, (
        "vazou para a função seguinte — é o defeito da janela fixa, de novo")
    assert c.count("{") == c.count("}"), "recorte desbalanceado"


def test_CONTROLE_o_extrator_js_reclama_de_funcao_que_nao_existe():
    try:
        _corpo_js("funcaoQueNaoExisteBatataFrita")
    except AssertionError:
        return
    raise AssertionError("o extrator aceitou função inexistente")


# ── Porta 1: ter área na capa não cala mais ────────────────────────────────
def test_PORTA_1_ter_area_na_capa_NAO_cala_mais_o_convite():
    """🩸 33 projetos e 358 linhas em branco moravam atrás desta linha."""
    r = rodar_o_convite({"total_area": 290.0}, [_linha_vazia()])
    assert r["apareceu"], (
        "com 290 m² na capa e uma linha de m² zerada o convite NÃO apareceu — "
        "o veto por ter área na capa voltou e 33 projetos com 358 linhas de m² "
        "em branco somem outra vez")
    js = _js_limpo("maybeShowAreaPrompt")
    assert "if (!noArea) return;" not in js, "o veto antigo voltou, escrito"
    assert "const noArea" not in js, "sobrou a variável do veto antigo"


def test_so_existe_UMA_declaracao_do_convite():
    """🪤 06/09/2026 — EM JS A ÚLTIMA DECLARAÇÃO VENCE, e `corpo_js` lê a
    PRIMEIRA. Uma segunda `function maybeShowAreaPrompt` declarada depois no
    mesmo <script> é quem roda no navegador; o guarda mediria a que ninguém
    executa e ficaria verde com o convite morto.

    🪤 O `esc` do bloco tem o mesmo risco e a mesma cura: o harness monta o
    escape a partir da PRIMEIRA definição do bloco.
    """
    bloco = _bloco_do_script()
    assert bloco.count("function maybeShowAreaPrompt(") == 1, (
        "há %d declarações de maybeShowAreaPrompt no <script> que o navegador "
        "roda — a última vence e o guarda mede a primeira"
        % bloco.count("function maybeShowAreaPrompt("))
    assert _PROJ.count("function maybeShowAreaPrompt(") == 1, (
        "o convite foi declarado em mais de um lugar de projeto.html")
    assert bloco.count("function esc(") == 1, (
        "há %d declarações de `esc` no bloco do convite — a que o teste mede "
        "não é a que escapa no navegador" % bloco.count("function esc("))


#: O trecho REAL do pipeline de render, do primeiro ao último `safeRun`.
_PIPELINE_INI = "safeRun(() => renderHeader(proj), 'renderHeader');"
_PIPELINE_FIM = "safeRun(() => renderFiles(proj, items), 'renderFiles');"


def _fatia_do_pipeline():
    i = _PROJ.find(_PIPELINE_INI)
    j = _PROJ.find(_PIPELINE_FIM)
    assert 0 < i < j, "o pipeline de render de projeto.html mudou de forma"
    return _PROJ[i:j + len(_PIPELINE_FIM)]


def test_a_CHAMADA_do_convite_e_INCONDICIONAL():
    """🪤 06/09/2026 — O GUARDA NUNCA ENCOSTAVA NA LINHA QUE CHAMA. Ele executa
    a função; o veto de uma linha que calava 33 projetos e 358 linhas de m² em
    branco pode voltar no CHAMADOR (`if (algo) safeRun(...)`) e a bancada segue
    verde.

    Aqui a fatia REAL do pipeline roda, com dublês no lugar de cada render: o
    convite tem que ser chamado UMA vez, sem condição nenhuma.
    """
    js = """
var _chamados = [];
var proj = { total_area: 290, warnings: [] }, items = [];
function safeRun(fn, label){ fn(); }
function renderHeader(){ _chamados.push('header'); }
function renderMetrics(){ _chamados.push('metrics'); }
function renderWarnings(){ _chamados.push('warnings'); }
function maybeShowAreaPrompt(){ _chamados.push('area'); }
function maybeShowPeDireitoPrompt(){ _chamados.push('pe'); }
function renderDates(){ _chamados.push('dates'); }
function renderFiles(){ _chamados.push('files'); }
""" + _fatia_do_pipeline() + "\nJSON.stringify(_chamados);"
    chamados = json.loads(dukpy.evaljs(js))
    assert chamados.count("area") == 1, (
        "o pipeline de render chamou o convite %d vez(es): %r — a chamada "
        "ganhou condição ou sumiu, e o convite morre calado"
        % (chamados.count("area"), chamados))

    # 🪤 Um `if (...) {` ENVOLVENDO a chamada ficaria fora da fatia acima:
    # o recorte roda o miolo e não vê a chave que abriu antes dele. Entre a
    # chamada anterior e esta não pode sobrar chave aberta.
    a = _PROJ.find("'renderWarnings');") + len("'renderWarnings');")
    b = _PROJ.find("maybeShowAreaPrompt(proj", a)
    assert 0 < a < b, "as âncoras do pipeline mudaram"
    entre = _PROJ[a:b]
    assert entre.count("{") == entre.count("}"), (
        "abriu um bloco entre o render dos avisos e a chamada do convite — a "
        "chamada virou condicional: %r" % entre.strip()[:200])


def test_a_area_da_capa_agora_so_muda_TEXTO_e_preenche_o_campo():
    js = _js_limpo("maybeShowAreaPrompt")
    assert "area-prompt-titulo" in js and "area-prompt-texto" in js, (
        "o convite parou de trocar o texto — quem tem área na capa lê 'sua "
        "planta não tinha cota de área', que é falso pra ele")
    assert "inp.value = areaCapa" in js, (
        "o campo parou de vir pré-preenchido com a área que já conhecemos")


# ── Porta 2: o gatilho é o fato, não a frase ───────────────────────────────
def test_PORTA_2_o_gatilho_nao_depende_mais_da_FRASE_da_IA():
    """🩸 22 projetos e 127 linhas: a IA disse 'Área total não extraída do
    DXF' em vez de uma das 4 frases que a tela procurava."""
    js = _js_limpo("maybeShowAreaPrompt")
    for frase in ("não medida", "nao medida", "informe a metragem",
                  "preencha a metragem"):
        assert frase not in js, (
            "o convite voltou a depender da frase %r escrita pela IA — "
            "vocabulário livre do modelo decidindo produto" % frase)
    assert "it.observations" not in js, (
        "voltou a ler a observação para decidir se mostra")


def test_o_convite_EXIGE_linha_de_m2_em_branco():
    """🧪 A trava que sobra. Sem ela o convite apareceria em projeto completo —
    e pedir dado que não resolve queima confiança."""
    js = _js_limpo("maybeShowAreaPrompt")
    assert "if (!vazias) return;" in js, (
        "o convite passou a aparecer sem haver linha de m² zerada")
    assert "Number(it.quantity || 0) === 0" in js, (
        "o critério de 'em branco' sumiu")


def test_o_convite_conta_as_linhas_pela_UNIDADE_certa():
    js = _js_limpo("maybeShowAreaPrompt")
    assert "_AREA_M2_UI.includes(u)" in js, (
        "parou de filtrar por unidade de área — contaria linha de metro linear")


# ── O que o convite DIZ ────────────────────────────────────────────────────
def test_quem_TEM_area_nao_le_que_a_planta_nao_tinha_cota():
    """🚨 Afirmação falsa é a doença que a gente vive consertando."""
    js = _corpo_js("maybeShowAreaPrompt")
    i = js.find("if (areaCapa > 0)")
    j = js.find("} else {", i)
    assert i > 0 and j > i, "os dois ramos de texto sumiram"
    ramo_com_area = js[i:j]
    assert "não tinha cota" not in ramo_com_area, (
        "o texto de quem TEM área voltou a afirmar que a planta não tinha cota")
    assert "capa deste projeto traz" in ramo_com_area, (
        "o texto parou de dizer de onde veio o número que está no campo")


def test_os_DOIS_ramos_reescrevem_os_DOIS_campos():
    """🩸 PEGO NO DOM VIVO, 02/09 — não no fonte. Rodando o ramo "tem área" e
    depois o ramo "não tem", o parágrafo continuava dizendo "A capa deste
    projeto traz 1.324,5 m²" para um projeto SEM área nenhuma: o `else`
    trocava só o título.

    Hoje a função roda uma vez por carga e isso não apareceria em produção —
    mas afirmação falsa que só não acontece porque ninguém chama duas vezes é
    bomba armada, não conserto. Os dois ramos escrevem os dois campos.
    🔑 Isto é o que o guarda de fonte não pegaria sozinho: ver
    [[feedback_arquivo_correto_nao_e_tela_correta]]."""
    js = _corpo_js("maybeShowAreaPrompt")
    i = js.find("} else {")
    assert i > 0, "o ramo de quem não tem área na capa sumiu"
    ramo_sem_area = js[i:]
    assert "area-prompt-titulo" in ramo_sem_area, "o ramo sem área não escreve o título"
    assert "area-prompt-texto" in ramo_sem_area, (
        "o ramo de quem NÃO tem área na capa deixou de reescrever o parágrafo — "
        "o texto do outro ramo sobrevive e afirma uma área que não existe")


def test_o_convite_NAO_promete_quantas_linhas_serao_preenchidas():
    """🪤 Quem decide item a item é `_apply_area_honesty`, no backend. A tela
    não sabe — e prometer número que não depende dela é como o aviso que a
    cliente-31 leu e não se cumpriu (ver test_aviso_nao_promete_o_que_nao_fez)."""
    js = _js_limpo("maybeShowAreaPrompt")
    for promessa in ("ganham número", "serão preenchidas", "vão ser preenchidas",
                     "destravam", "linhas completadas"):
        assert promessa not in js, (
            "o convite promete resultado que a tela não controla: %r" % promessa)
    assert "em branco" in js, "o convite parou de dizer o FATO (linhas em branco)"


# ── A tela não pode quebrar em silêncio ────────────────────────────────────
@pytest.mark.parametrize("proj,vazias,titulo,no_texto,fora_do_texto", [
    # quem TEM área na capa: o texto fala da capa e NÃO afirma falta de cota
    ({"total_area": 290.0}, 1,
     "1 linha de área ainda está em branco",
     "A capa deste projeto traz <b>290 m²</b>",
     "não tinha cota"),
    # 🪤 plural: o mesmo ramo com mais de uma linha — a concordância é montada
    # por pedaços, que é exatamente onde esta casa já errou três vezes.
    ({"total_area": 290.0}, 7,
     "7 linhas de área ainda estão em branco",
     "essas linhas",
     "essa linha"),
    # quem NÃO tem: o ramo do `else` reescreve os DOIS campos
    ({"total_area": 0}, 1,
     "Sua planta não tinha cota de área",
     "a gente não inventa metragem",
     "A capa deste projeto traz"),
])
def test_os_ids_que_o_JS_escreve_EXISTEM_no_html(
        proj, vazias, titulo, no_texto, fora_do_texto):
    """🚨 `getElementById` de id inexistente devolve null, o `.textContent`
    estoura, o `catch` engole e o convite NÃO APARECE — em silêncio, para
    todo mundo. É o modo de falha mais caro possível aqui.

    🪤 06/09/2026 — o guarda anterior tinha lista fixa de 5 ids e conferia
    só o lado do HTML. Trocar a chamada pra `area-prompt-box` (com o
    `id="area-prompt"` intacto no HTML) matava o convite pra todo mundo e ele
    passava verde. Agora o DOM de ensaio tem EXATAMENTE os ids da tela e quem
    responde é a função rodando: id que ela pede e a tela não tem aparece em
    `faltaram`.

    🪤 06/09/2026, 2ª volta — E `faltaram` SÓ ACUSA ID QUE NÃO EXISTE EM LUGAR
    NENHUM da página. Apontar a escrita pra outro elemento REAL passava
    despercebido: o convite abria com o texto padrão "Sua planta não tinha cota
    de área" para um projeto que tem 290 m² na capa — a afirmação falsa que o
    guarda irmão existe pra impedir. Por isso agora se cobra o CONTEÚDO que
    chegou em cada campo, e nos DOIS ramos.
    """
    r = rodar_o_convite(proj, [_linha_vazia()] * vazias)
    assert not r["faltaram"], (
        "o convite pediu %r, que NÃO existe na tela: getElementById devolve "
        "null, o catch engole e o convite morre calado pra todo mundo"
        % (r["faltaram"],))
    assert not r["avisos"], "o convite caiu no catch: %r" % (r["avisos"],)
    assert r["apareceu"], "o convite não apareceu (proj=%r)" % (proj,)
    assert r["titulo"] == titulo, (
        "o título ficou %r e não %r — ou o ramo errado escreveu, ou a escrita "
        "foi parar em outro elemento e o campo ficou com o texto de fábrica"
        % (r["titulo"], titulo))
    assert no_texto in r["texto"], (
        "o parágrafo não diz %r; diz %r" % (no_texto, r["texto"][:200]))
    assert fora_do_texto not in r["texto"], (
        "o parágrafo afirma %r, que é FALSO neste caso: %r"
        % (fora_do_texto, r["texto"][:200]))


def test_o_campo_chega_PRE_PREENCHIDO_com_a_area_da_capa():
    """🪤 É o pré-preenchimento que cria o gesto "confirmar" — e é por isso que
    o backend precisa distinguir confirmar de informar."""
    assert rodar_o_convite({"total_area": 290.0}, [_linha_vazia()])["valor"] == "290"
    assert rodar_o_convite({"total_area": 0}, [_linha_vazia()])["valor"] == "", (
        "sem área na capa o campo não pode vir preenchido com nada")


#: Conteúdo hostil que o `esc` da página tem que neutralizar. Não é hipótese:
#: `project_name` é digitado pelo cliente e chega inteiro nas telas.
_HOSTIS = [
    "<script>alert(1)</script>",
    '"><img src=x onerror=alert(1)>',
    "Reforma & Cia <b>negrito</b>",
    "O'Brien \"Arquitetura\"",
]


@pytest.mark.parametrize("cru", _HOSTIS)
def test_a_funcao_de_escape_REALMENTE_neutraliza_o_conteudo(cru):
    """🪤 06/09/2026 — o guarda anterior só provava que `esc` EXISTE (e o irmão
    dele, que ela é CHAMADA). Chamada sobrevivente absolve a linha inteira: dá
    pra pendurar ao lado dela qualquer valor cru vindo do banco. O que importa
    é o que ela FAZ com conteúdo hostil.
    """
    bloco = _bloco_do_script()
    saida = dukpy.evaljs(corpo_js("esc", src=bloco)
                         + "\nesc(%s);" % json.dumps(cru))
    for bruto in ("<", ">", '"', "'"):
        assert bruto not in saida, (
            "esc(%r) devolveu %r com %r cru — dá pra fechar a tag e injetar "
            "script na tela do cliente" % (cru, saida, bruto))
    assert "&" not in saida.replace("&amp;", "").replace("&lt;", "") \
        .replace("&gt;", "").replace("&quot;", "").replace("&#39;", ""), (
        "sobrou `&` solto em %r — entidade pela metade volta a abrir caminho"
        % saida)
    # 🧪 CONTROLE: escapar não é apagar. Um `esc` que devolvesse '' passaria em
    # tudo acima e deixaria a tela em branco. Desfazendo as entidades tem que
    # voltar EXATAMENTE o que entrou — escape sem perda.
    assert _html.unescape(saida) == cru, (
        "esc(%r) devolveu %r, que desescapado vira %r — o escape comeu ou "
        "trocou conteúdo, e o texto chega errado na tela"
        % (cru, saida, _html.unescape(saida)))


def test_o_convite_ESCAPA_o_que_interpola_no_paragrafo():
    """🪤 Guarda de CALL SITE do escape: a função pode estar certa e o convite
    montar o HTML sem ela."""
    r = rodar_o_convite({"total_area": 290.0}, [_linha_vazia()])
    assert r["esc"] >= 1, (
        "o ramo que interpola a área da capa montou o innerHTML sem passar "
        "por esc() — qualquer valor cru que chegue ali vira markup")


# ── O botão que o convite oferece ─────────────────────────────────────────
def test_o_BOTAO_do_convite_manda_a_area_pra_rota_certa():
    """🚨 06/09/2026 — COBERTURA QUE A CONVERSÃO TINHA PERDIDO. `area-submit` é
    de `submitInformedArea`, que nenhum teste executava. Sumindo o id, o cliente
    vê o convite, digita a área, clica em "Completar itens de área" e o
    `btn.disabled = true` estoura em null: nada acontece, e a bancada fica
    verde.

    De quebra o caminho inteiro fica coberto: a rota chamada, o verbo e o
    número que sai no corpo.
    """
    r = rodar_o_envio("290")
    assert not r["faltaram"], (
        "o envio pediu %r, que não existe na tela — o clique morre em null e "
        "o cliente fica olhando o botão sem resposta" % (r["faltaram"],))
    assert len(r["fetches"]) == 1, "esperava UMA chamada, veio %r" % (r["fetches"],)
    ida = r["fetches"][0]
    assert ida["url"].endswith("/api/project/job-guarda-01/inform-area"), (
        "o botão chama %r — a rota da mini-revisão é "
        "/api/project/{job}/inform-area e o clique some num 404"
        % ida["url"])
    assert ida["method"] == "POST", "o botão manda %r" % ida["method"]
    assert json.loads(ida["body"]) == {"area": 290.0}, (
        "o corpo saiu %r — o número que o cliente digitou não chega na rota"
        % ida["body"])
    assert r["desabilitou"], (
        "o botão não foi desabilitado — dois cliques viram duas mini-revisões")


@pytest.mark.parametrize("digitado", ["", "0", "-3", "abc"])
def test_o_BOTAO_nao_manda_area_invalida(digitado):
    """🧪 CONTROLE: sem isto, um botão que dispara sempre passaria no guarda de
    cima. Área inválida tem que morrer na tela, não virar chamada."""
    r = rodar_o_envio(digitado)
    assert r["fetches"] == [], (
        "o botão mandou %r pra rota com o campo em %r" % (r["fetches"], digitado))
    assert "área válida" in r["msg"], (
        "a tela não explicou por que não fez nada (msg=%r)" % r["msg"])


# ── Backend: confirmar não é informar — A ROTA RODANDO ─────────────────────
#
# 🪤 06/09/2026 — OS TRÊS GUARDAS ABAIXO LIAM O FONTE, e a versão convertida
# que os substituiu só tinha caso nas PONTAS: capa zero (delta 100%) e 200
# contra 450 (delta 125%). A tolerância de 1% podia ser afrouxada até ~124%,
# zerada, ou virar `<`, sem que nenhum dos dois casos mudasse de lado. E a
# faixa que interessa é justamente a estreita: o campo chega PRÉ-PREENCHIDO com
# a área da capa arredondada, então quem confirma 290 numa capa de 290,37 cai
# no ramo do `elif` e lê "a planta não trazia cota pra medir" — afirmação
# falsa — levando "informado" carimbado em cima de área que a planta mediu.
_JOB = "job-convite-da-area"


def _projeto(capa, fonte_da_capa="medido"):
    """A linha de `projects` como o banco entrega."""
    return {"job_id": _JOB, "project_name": "Projeto cliente-NN",
            "typology": "office", "total_area": capa,
            "total_area_source": fonte_da_capa, "warnings": [],
            "user_pe_direito": 0, "layout_area": 0, "address": "",
            "user_total_area": 0}


def _linha_em_branco_de_area():
    return [{"item_num": "1.1", "description": "Piso em porcelanato",
             "unit": "m2", "quantity": 0.0, "confidence": "estimado",
             "observations": "", "ref_sheet": "", "origem": "",
             "discipline": "Arquitetura"}]


def _informar_area(monkeypatch, tmp_path, capa, digitado, fonte_da_capa="medido"):
    """RODA `inform_project_area` de verdade. Devolve (ProjectData, avisos)."""
    reg = _bancada(monkeypatch, tmp_path, proj=_projeto(capa, fonte_da_capa),
                   rows=_linha_em_branco_de_area())
    main.inform_project_area(
        _JOB, main.InformAreaPayload(area=digitado, pe_direito=0), request=None)
    assert reg["planilha"], "a rota não chegou a gerar planilha"
    pd = reg["planilha"][0][0]
    avisos = [str(a) for u in reg["update"] for a in (u.get("warnings") or [])]
    return pd, avisos, reg


#: (capa, digitado, procedência esperada, é confirmação?)
#: A faixa inteira, não só as pontas — 1% de 200 é 2,00.
_CASOS_DA_TOLERANCIA = [
    (0.0,    290.0, "informado", False),   # capa vazia: informação nova
    (200.0,  450.0, "informado", False),   # nada a ver com a capa
    (200.0,  203.0, "informado", False),   # 1,5% acima → FORA da tolerância
    (200.0,  201.0, "medido",    True),    # 0,5% → é confirmação
    (200.0,  199.0, "medido",    True),    # 0,5% ABAIXO: a faixa é dos dois lados
    (200.0,  197.0, "informado", False),   # 1,5% abaixo → FORA
    (290.37, 290.0, "medido",    True),    # o campo pré-preenchido, arredondado
    (290.37, 320.0, "informado", False),   # 10% acima
]


@pytest.mark.parametrize("capa,digitado,procedencia,confirma", _CASOS_DA_TOLERANCIA)
def test_confirmar_a_area_MEDIDA_nao_carimba_informado(
        capa, digitado, procedencia, confirma, monkeypatch, tmp_path):
    """🚨 `spreadsheet.py` troca a linha de premissa por causa deste campo:
    'Área construída — perímetro externo da laje' viraria 'INFORMADA POR VOCÊ
    (não medida pela planta)' só porque o cliente confirmou o que a planta
    mediu.

    🧪 E o CONTROLE mora na mesma lista: se a correção virasse "nunca carimba",
    a área que o cliente REALMENTE informou passaria a se apresentar como
    medida — a regra dura nº1 ao contrário.
    """
    pd, _avisos, _reg = _informar_area(monkeypatch, tmp_path, capa, digitado)
    assert pd.total_area_source == procedencia, (
        "capa %s, cliente digitou %s (%.2f%% de diferença): a planilha saiu "
        "com procedência %r e devia ser %r"
        % (capa, digitado,
           (abs(digitado - capa) / capa * 100) if capa else 100.0,
           pd.total_area_source, procedencia))
    assert pd.total_area == digitado, (
        "a capa saiu com %r e o cliente digitou %r" % (pd.total_area, digitado))


@pytest.mark.parametrize("capa,digitado,procedencia,confirma", _CASOS_DA_TOLERANCIA)
def test_o_aviso_de_confirmacao_nao_afirma_falta_de_cota(
        capa, digitado, procedencia, confirma, monkeypatch, tmp_path):
    """🚨 "a planta não trazia cota pra medir" é uma AFIRMAÇÃO, e ela é falsa
    para quem só confirmou o número que a capa já trazia.

    🪤 'Preenchemos os itens de piso/forro/laje' é a única marca que prova que
    a mini-revisão rodou (foi assim que se mediu 0 usos em 293 projetos) — ela
    tem que sobreviver nos DOIS ramos, e é por isso que os dois rodam aqui.
    """
    _pd, avisos, _reg = _informar_area(monkeypatch, tmp_path, capa, digitado)
    texto = " ".join(avisos)
    assert texto.count("Preenchemos os itens de piso/forro/laje") == 1, (
        "o ramo (%s → %s) perdeu a assinatura da rota — o uso da mini-revisão "
        "vira invisível pra metade dos casos: %r" % (capa, digitado, avisos))
    if confirma:
        assert "CONFIRMADA POR VOCÊ" in texto, (
            "capa %s, digitado %s: era confirmação e o aviso não diz isso: %r"
            % (capa, digitado, avisos))
        assert "não trazia cota" not in texto, (
            "o aviso afirma que a planta não tinha cota — e ela trazia %s m²: "
            "%r" % (capa, avisos))
    else:
        assert "INFORMADA POR VOCÊ" in texto, (
            "capa %s, digitado %s: a área é nova e o aviso não diz que foi "
            "informada: %r" % (capa, digitado, avisos))
        assert "CONFIRMADA POR VOCÊ" not in texto, (
            "área NOVA se apresentando como confirmação do que a planta "
            "media: %r" % (avisos,))


def test_o_selo_da_planilha_vem_da_procedencia_e_nao_do_gesto(
        monkeypatch, tmp_path):
    """🧪 CONTROLE do par acima: os dois lados da mesma capa, no mesmo teste.

    Sem ele, uma rota que devolvesse SEMPRE a procedência do banco passaria em
    metade dos casos e uma que carimbasse SEMPRE "informado" na outra — cada
    uma verde num teste diferente.
    """
    confirma, _, _ = _informar_area(monkeypatch, tmp_path, 290.37, 290.0)
    informa, _, _ = _informar_area(monkeypatch, tmp_path, 290.37, 320.0)
    assert (confirma.total_area_source, informa.total_area_source) \
        == ("medido", "informado"), (
        "a MESMA capa de 290,37 m² produziu %r ao ser confirmada e %r ao ser "
        "trocada — a rota parou de olhar a diferença"
        % (confirma.total_area_source, informa.total_area_source))
