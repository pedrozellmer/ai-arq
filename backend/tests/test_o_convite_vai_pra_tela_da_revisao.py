# -*- coding: utf-8 -*-
"""O convite mudou de tela — e agora deixa rastro.

🩸 02/09/2026. A mini-revisão existia só em `projeto.html` desde 21/07 e teve
**ZERO acionamentos em 43 dias**. A investigação (7 agentes) mostrou que a
pergunta "por que ninguém clica" estava mal posta:

    3 de 18 VIRAM (comprovado) · 0 NÃO VIRAM · 15 INDETERMINADOS

E o motivo principal é estrutural, não de design:

  · **O caminho principal DESVIA da página onde a caixa morava.** O botão
    "Revisar" do dashboard (dashboard.html:1755 e :4702) e o menu lateral
    (menu-lateral.js:273) linkam `revisao.html?job_id=` direto. Desde 24/08,
    **8 de 19 donos (42%)** chegaram na revisão sem nunca abrir projeto.html.
  · **7 das 10 "visitas de cliente" eram do ADMIN.** 101 dos 338 `open_project`
    da base inteira (30%) são meus, abrindo o projeto do cliente.
  · **A janela de atenção é de 3 MINUTOS** (mediana até a 1ª ação; 9 de 12 em
    ≤7 min). Dos 11 que receberam e-mail de reengajamento, 11 de 11 não
    voltaram. Não existe "voltar depois" nesta base.

🔑 O convite passa a existir onde o cliente JÁ está, olhando a linha vazia.

🚨 E O MAIS IMPORTANTE: o único log da rota rodava na ÚLTIMA linha do caminho de
sucesso. Então "0 acionamentos" era, com rigor, "0 acionamentos BEM-SUCEDIDOS" —
clique que morria em 401, 500 ou na validação não deixava rastro em lugar
nenhum. **"O convite não convence" e "o convite está quebrado" davam o mesmo
zero.** Agora o mesmo stage registra ENTROU / RECUSADO / CONCLUIU, e o ENTROU
fica ANTES da checagem de dono, que é justamente o caso a descartar.

🪤 O canal do navegador só grava pra quem aceita cookie (cobertura medida: 53%
dos donos que comprovadamente agem no app). O log do backend é o único imune —
por isso ele é o guarda que este arquivo trata como obrigatório.
"""
import json
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

from _corpo import corpo_js, fonte                              # noqa: E402
import _navegador as nav                                        # noqa: E402

_RV = fonte("revisao.html")
_UTILS = fonte("aiarq-utils.js")

_IDS = ["convite-area", "convite-area-titulo", "convite-area-texto",
        "convite-area-input", "convite-area-submit", "convite-area-msg",
        "items-container"]


def _js(nome):
    corpo = corpo_js(nome, "revisao.html", _RV)
    return "\n".join(l for l in corpo.splitlines() if not l.strip().startswith("//"))


# ─────────────────────────────────────────────────────────────────────────────
#  A TELA RODANDO — Duktape + o DOM mínimo de `_navegador.py`
# ─────────────────────────────────────────────────────────────────────────────
#  🩸 06/09/2026 — o que a leitura de arquivo não pega, e a mutação provou:
#    • `style="display:none"` no `<div id="convite-area">` — o id continua lá;
#    • `.after(items-container)` dentro da função — a ordem no arquivo não muda;
#    • `inform-area` → `inform-area-v2` — o trecho procurado é prefixo do novo;
#    • `if (false) maybeShowConviteArea()` — a chamada continua no arquivo;
#    • `=== 0 && false`, `remove` no lugar de `add`, `> 0` virando `< 0`.
#  Todas viram falha na hora em que a função RODA.
import re                                                      # noqa: E402

_LINHA_UNIDADES = re.search(r"const _AREA_M2_RV\s*=.*?;", _RV).group(0)


def _preambulo():
    """O que a página já tem em volta do convite, tirado do PRÓPRIO arquivo."""
    return """
var jobId = 'job-teste';
var API_BASE = 'https://api.ai.arq.br';
var projMeta = {};
var items = [];
var _conviteAreaContado = false;
%s
function escapeHtml(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;'); }
function loadItems(){ return null; }
var authFetch = null;
""" % _LINHA_UNIDADES


def _tela(passos, expressao, ids=None, com_utils=False):
    """Monta a tela da revisão a partir do HTML REAL e roda os passos."""
    els = nav.elementos(_RV, ids if ids is not None else _IDS)
    pedacos = [nav.montar(els), _preambulo(),
               nav.sem_await(corpo_js("maybeShowConviteArea", "revisao.html", _RV)),
               nav.sem_await(corpo_js("submitConviteArea", "revisao.html", _RV)),
               "_ligarTelemetria();"]
    if com_utils:
        pedacos.append(nav.bloco_a_partir_de(
            _UTILS, "document.addEventListener('click'", "aiarq-utils.js"))
    return nav.rodar(pedacos + list(passos), expressao)


_UMA_LINHA_VAZIA = ("items = [{unit: 'm\\u00b2', quantity: 0, "
                    "observations: 'texto qualquer que a IA escreveu'},"
                    " {unit: 'un', quantity: 5}];")
_NADA_VAZIO = "items = [{unit: 'm\\u00b2', quantity: 42}, {unit: 'un', quantity: 5}];"


# ── O extrator, antes de confiar nele ──────────────────────────────────────
def test_CONTROLE_o_extrator_para_no_fim_da_funcao():
    c = corpo_js("maybeShowConviteArea", "revisao.html", _RV)
    assert "convite-area" in c, "não pegou a função certa"
    assert "function submitConviteArea" not in c, "vazou pra função seguinte"
    assert c.count("{") == c.count("}"), "recorte desbalanceado"


def test_CONTROLE_o_extrator_reclama_de_funcao_inexistente():
    try:
        corpo_js("funcaoQueNaoExisteBatataFrita", "revisao.html", _RV)
    except AssertionError:
        return
    raise AssertionError("o extrator aceitou função inexistente")


# ── A caixa existe e está inteira ──────────────────────────────────────────
def test_a_caixa_existe_na_TELA_DA_REVISAO():
    """🩸 O ponto do conserto: 42% dos donos chegam aqui sem passar pela
    página onde o convite morava.

    🩸 06/09 — o guarda antigo só cobrava `id="..."`. Um `style="display:none"`
    na mesma tag deixa todos os ids intactos e a caixa INVISÍVEL pra sempre:
    `classList.remove('hidden')` não desfaz estilo inline. Aqui a tag é montada
    com os atributos REAIS do arquivo e a pergunta é se o cliente VÊ.
    """
    r = json.loads(_tela([_UMA_LINHA_VAZIA, "maybeShowConviteArea();"],
                         "JSON.stringify({vis: _visivel('convite-area')})"))
    assert r["vis"] is True, (
        "com uma linha de área em branco o convite NÃO ficou visível — "
        "provavelmente um estilo inline ou uma classe que `remove('hidden')` "
        "não desfaz")


def test_a_caixa_fica_ANTES_da_lista_de_itens():
    """Depois da lista ela ficaria abaixo de dezenas de cards — e a janela de
    atenção é de 3 minutos.

    🩸 06/09 — a ordem no ARQUIVO não é a ordem na TELA: um `.after()` dentro
    da função move a caixa pra baixo sem mexer no HTML. Aqui a ordem medida é a
    do documento DEPOIS que o convite roda.
    """
    r = json.loads(_tela(
        [_UMA_LINHA_VAZIA, "maybeShowConviteArea();"],
        "JSON.stringify({caixa: _posicao('convite-area'), "
        "lista: _posicao('items-container')})"))
    assert 0 <= r["caixa"] < r["lista"], (
        "o convite foi parar depois da lista de itens (posições %r) — o "
        "cliente rola dezenas de cards antes de ver o pedido" % r)


def test_chama_a_MESMA_rota_e_nao_uma_copia():
    """🩸 06/09 — `'/api/project/${jobId}/inform-area' in js` passa verde com
    `inform-area-v2`, porque o procurado é PREFIXO do escrito. Aqui a URL que
    sai é comparada por igualdade.
    """
    r = json.loads(_tela([
        "var _pedido = {};",
        "authFetch = function(url, opts){ _pedido = {url: url, opts: opts};"
        " return {ok: true, json: function(){ return {filled_count: 1,"
        " catch: function(){ return this; }}; }}; };",
        "__els['convite-area-input'].value = '120';",
        "submitConviteArea();",
    ], "JSON.stringify(_pedido)"))
    assert r["url"] == "https://api.ai.arq.br/api/project/job-teste/inform-area", (
        "a tela da revisão chamou %r — cópia de rota é a próxima pessoa "
        "consertando o lado errado" % r.get("url"))
    assert (r["opts"] or {}).get("method") == "POST", r["opts"]


def test_CONTROLE_a_tela_usa_authFetch_e_nao_fetch_cru():
    """Sem o header de autorização a rota devolve 401 — e o clique some."""
    assert "authFetch(" in _js("submitConviteArea"), (
        "usou fetch cru: sem o header de autorização a rota devolve 401")


# ── O gatilho é o FATO ─────────────────────────────────────────────────────
def test_o_gatilho_e_a_LINHA_VAZIA_nao_a_frase_da_IA():
    """🩸 Em projeto.html a peneira de texto calava 22 projetos porque a IA
    escrevia 'Área total não extraída do DXF' em vez de uma das 4 frases.

    Aqui: a linha vazia tem uma observação que NÃO diz nada de área, e mesmo
    assim o convite aparece. E a contagem tem que ser a das linhas vazias.
    """
    r = json.loads(_tela([_UMA_LINHA_VAZIA, "maybeShowConviteArea();"],
                         "JSON.stringify({vis: _visivel('convite-area'), ev: __eventos})"))
    assert r["vis"] is True, (
        "linha de área ZERADA e o convite não apareceu — o gatilho deixou de "
        "ser o fato (quantidade 0 numa unidade de área)")
    assert r["ev"] and r["ev"][0][1]["linhas_vazias"] == 1, r["ev"]

    # e unidade que não é área não conta, nem com quantidade zero
    r2 = json.loads(_tela(["items = [{unit: 'un', quantity: 0}];",
                           "maybeShowConviteArea();"],
                          "JSON.stringify({vis: _visivel('convite-area')})"))
    assert r2["vis"] is False, (
        "o convite apareceu por causa de uma linha em 'un' — parou de filtrar "
        "por unidade de área e vai pedir metragem em planilha que não precisa")


def test_some_quando_NAO_ha_linha_vazia():
    r = json.loads(_tela([_NADA_VAZIO, "maybeShowConviteArea();"],
                         "JSON.stringify({vis: _visivel('convite-area')})"))
    assert r["vis"] is False, (
        "o convite apareceu em planilha completa — pedir dado que não resolve "
        "queima confiança")


def test_some_quando_o_cliente_JA_informou():
    """🪤 Repetir o pedido depois de atendido é cobrar duas vezes."""
    r = json.loads(_tela([_UMA_LINHA_VAZIA,
                          "projMeta = {user_total_area: 120};",
                          "maybeShowConviteArea();"],
                         "JSON.stringify({vis: _visivel('convite-area')})"))
    assert r["vis"] is False, (
        "o cliente já informou 120 m² e o convite pediu de novo")


def test_os_DOIS_ramos_escrevem_os_DOIS_campos():
    """🩸 Pego no DOM em projeto.html no mesmo dia: o ramo sem área trocava só
    o título e o parágrafo do outro ramo sobrevivia, afirmando uma área de capa
    que não existia.

    Encenado: primeiro renderiza COM área de capa, depois SEM. O texto do
    primeiro ramo não pode sobreviver ao segundo.
    """
    r = json.loads(_tela([
        _UMA_LINHA_VAZIA,
        "projMeta = {total_area: 200};",
        "maybeShowConviteArea();",
        "var _com = __els['convite-area-texto'].innerHTML;",
        "projMeta = {total_area: 0};",
        "_conviteAreaContado = false;",
        "maybeShowConviteArea();",
    ], "JSON.stringify({com: _com, sem: __els['convite-area-texto'].innerHTML,"
       " tit: __els['convite-area-titulo'].textContent})"))
    assert "A capa deste projeto" in r["com"], (
        "o ramo COM área de capa não escreveu o parágrafo dele: %r" % r["com"][:120])
    assert "A capa deste projeto" not in r["sem"], (
        "o ramo SEM área deixou o parágrafo do outro ramo vivo — a tela afirma "
        "uma área de capa que não existe: %r" % r["sem"][:160])
    assert "informe aqui pra completar" in r["sem"], (
        "o ramo sem área não escreveu o próprio texto: %r" % r["sem"][:160])
    assert "em branco" in r["tit"], r["tit"]


# ── Guarda de ponto de chamada ─────────────────────────────────────────────
def test_o_render_CHAMA_o_convite():
    """🪤 A função pode estar perfeita e nunca ser chamada — foi exatamente o
    caso da derivação de pintura, que existia e a rota não invocava.

    🩸 06/09 — `"maybeShowConviteArea()" in render` passa verde com
    `if (false) maybeShowConviteArea();`. Aqui o `render()` do arquivo é
    EXECUTADO e o convite é um espião.
    """
    els = nav.elementos(_RV, _IDS + ["rv-medido", "rv-estimado", "bloco-faltou"])
    saida = nav.rodar([
        nav.montar(els), _preambulo(),
        "var showOnlyEstimates = false; var reviewState = {};",
        "function renderItem(){ return ''; } function updateCounters(){}",
        nav.sem_await(corpo_js("render", "revisao.html", _RV)),
        "var _chamou = 0;",
        "function maybeShowConviteArea(){ _chamou++; }",
        "items = [];",
        "render();",
    ], "JSON.stringify({chamou: _chamou})")
    assert json.loads(saida)["chamou"] == 1, (
        "o render rodou e NÃO chamou o convite — ele nunca aparece na tela")


def test_CONTROLE_a_checagem_de_chamada_sabe_REPROVAR():
    """🧪 O espião só vale se souber acusar quem não chama."""
    saida = nav.rodar([
        "var _chamou = 0;",
        "function maybeShowConviteArea(){ _chamou++; }",
        "function renderFalso(){ var x = 1; return x; }",
        "renderFalso();",
    ], "JSON.stringify({chamou: _chamou})")
    assert json.loads(saida)["chamou"] == 0


# ── A instrumentação, que é o ponto ────────────────────────────────────────
def test_o_convite_registra_que_foi_EXIBIDO():
    """🚨 O DENOMINADOR. Sem ele, 'ninguém clicou' e 'ninguém viu' são a mesma
    linha do banco — foi essa cegueira que custou 43 dias.
    """
    r = json.loads(_tela([
        "items = [{unit: 'm\\u00b2', quantity: 0}, {unit: 'm2', quantity: 0}];",
        "projMeta = {total_area: 200};",
        "maybeShowConviteArea();",
        "maybeShowConviteArea();",     # 2º render: não pode contar de novo
    ], "JSON.stringify(__eventos)"))
    exibidos = [e for e in r if e[0] == "convite-area:exibido"]
    assert exibidos, (
        "o convite apareceu sem deixar registro de exibição — 'ninguém clicou' "
        "e 'ninguém viu' voltam a ser a mesma linha do banco. Eventos: %r" % r)
    assert len(exibidos) == 1, (
        "cada render contou uma exibição nova (%d) — o denominador infla"
        % len(exibidos))
    meta = exibidos[0][1]
    assert meta["linhas_vazias"] == 2, (
        "o evento não guarda o tamanho do problema: %r" % meta)
    assert meta["tem_area_capa"] == 1 and meta["tela"] == "revisao", meta


def test_o_botao_tem_rastreio_de_clique():
    """O ouvinte de `aiarq-utils.js` converte `[data-track]` em `clique:<nome>`.

    🩸 06/09 — o guarda antigo lia `data-track="convite-area-completar"` no
    HTML e passava verde com o ouvinte procurando `[data-track-nunca]`: o
    atributo continuava lá e ninguém mais o lia. Aqui o clique é DISPARADO.
    """
    r = json.loads(_tela(
        ["_disparar('click', __els['convite-area-submit']);"],
        "JSON.stringify(__eventos)", com_utils=True))
    cliques = [e for e in r if str(e[0]).startswith("clique:")]
    assert cliques, (
        "clicaram no botão do convite e nada foi registrado — o ouvinte de "
        "[data-track] parou de enxergar o botão. Eventos: %r" % r)
    assert cliques[0][0] == "clique:convite-area-completar", cliques[0][0]


def test_os_TRES_caminhos_de_falha_deixam_rastro():
    """Os três jeitos de o clique morrer, encenados um a um."""
    # 1) render que estoura: sem o parágrafo, o `txt.innerHTML` explode
    ids_capengas = [i for i in _IDS if i != "convite-area-texto"]
    r1 = json.loads(_tela([_UMA_LINHA_VAZIA, "maybeShowConviteArea();"],
                          "JSON.stringify({ev: __eventos, vis: _visivel('convite-area')})",
                          ids=ids_capengas))
    nomes1 = [e[0] for e in r1["ev"]]
    assert "convite-area:render-falhou" in nomes1, (
        "o render quebrou e a falha só existiu no console do cliente: %r" % nomes1)
    assert r1["vis"] is False, "render quebrado deixou a caixa meio montada na tela"

    # 2) submit sem número
    r2 = json.loads(_tela(["__els['convite-area-input'].value = '';",
                           "submitConviteArea();"],
                          "JSON.stringify({ev: __eventos, "
                          "msg: __els['convite-area-msg'].textContent})"))
    assert "convite-area:submit-invalido" in [e[0] for e in r2["ev"]], r2
    assert "m²" in r2["msg"], r2["msg"]

    # 3) submit que morre no servidor
    r3 = json.loads(_tela([
        "authFetch = function(){ var e = new Error('500'); e.status = 500; throw e; };",
        "__els['convite-area-input'].value = '120';",
        "submitConviteArea();",
    ], "JSON.stringify({ev: __eventos, "
       "msg: __els['convite-area-msg'].textContent, "
       "botao: __els['convite-area-submit'].disabled})"))
    erros = [e for e in r3["ev"] if e[0] == "convite-area:submit-erro"]
    assert erros, "o clique morreu no servidor e sumiu do sistema: %r" % r3["ev"]
    assert erros[0][1]["status"] == 500, (
        "sem o status HTTP não dá pra separar 'morreu na autorização' de "
        "'morreu no servidor': %r" % erros[0][1])
    assert r3["botao"] is False, "o botão ficou travado depois do erro"


def test_a_telemetria_NAO_manda_texto_livre_do_cliente():
    """🔒 A 1ª versão mandava `bruto` (o que a pessoa digitou) e `erro` (a
    mensagem da exceção). O `/api/track` é rota ABERTA e o painel do admin lê
    o meta — texto livre não vira linha de banco por conveniência de depuração.
    Quem reprovou foi o guarda irmão `test_track_meta_allowlist`.

    🩸 06/09 — procurar `"bruto:"` no fonte passa verde com `'bruto':` (aspas
    do outro lado). Aqui o que se olha é o que foi MANDADO.
    """
    digitado = "120,5 conforme o memorial do escritório"
    r = json.loads(_tela([
        "authFetch = function(){ var e = new Error('500'); e.status = 500; throw e; };",
        "__els['convite-area-input'].value = %s;" % json.dumps(digitado),
        "submitConviteArea();",
        "__els['convite-area-input'].value = '';",
        "submitConviteArea();",
    ], "JSON.stringify(__eventos)"))
    assert r, "nenhum evento saiu — o teste não chegou a medir nada"
    for nome, meta in r:
        assert set(meta) <= {"job_id", "status", "tela", "area", "preenchidos",
                             "linhas_vazias", "tem_area_capa"}, (
            "o evento %r ganhou chave fora da lista branca do /api/track: %r"
            % (nome, sorted(meta)))
        for chave, valor in meta.items():
            assert "memorial" not in str(valor) and "conforme" not in str(valor), (
                "o convite mandou o texto que o cliente digitou em %r=%r"
                % (chave, valor))
    assert any(e[0] == "convite-area:submit-erro" and "status" in e[1] for e in r), (
        "sumiu o status HTTP no erro — é o que separa 'morreu na autorização' "
        "de 'morreu no servidor'")


def test_o_sucesso_registra_QUANTAS_linhas_foram_preenchidas():
    """Sem o número, não dá pra saber se o convite resolve alguma coisa."""
    r = json.loads(_tela([
        "authFetch = function(){ return {ok: true, json: function(){"
        " return {filled_count: 7, catch: function(){ return this; }}; }}; };",
        "__els['convite-area-input'].value = '120';",
        "submitConviteArea();",
    ], "JSON.stringify(__eventos)"))
    oks = [e for e in r if e[0] == "convite-area:submit-ok"]
    assert oks, ("o convite foi usado com sucesso e não registrou nada — o "
                 "efeito dele fica invisível de novo: %r" % r)
    assert oks[0][1]["preenchidos"] == 7, oks[0][1]
    assert oks[0][1]["area"] == 120, oks[0][1]


def test_a_mensagem_diz_o_que_ACONTECEU_nao_o_que_era_esperado():
    """🪤 O aviso que a cliente-31 leu prometia que a área 'entra como base' e a
    regra impedia. Aqui a mensagem lê `filled_count`, que é o fato.

    O caso duro é `filled_count = 0`: recebido e nada pôde ser completado.
    """
    def _msg(filled):
        return json.loads(_tela([
            "authFetch = function(){ return {ok: true, json: function(){"
            " return {filled_count: %d, catch: function(){ return this; }}; }}; };"
            % filled,
            "__els['convite-area-input'].value = '120';",
            "submitConviteArea();",
        ], "JSON.stringify({msg: __els['convite-area-msg'].textContent})"))["msg"]

    zero = _msg(0)
    assert "nenhuma linha pôde ser completada" in zero, (
        "o servidor não completou nada e a tela disse %r — é a promessa que "
        "não se cumpre, de novo" % zero)
    assert _msg(1).count("linha completada") == 1, _msg(1)
    assert "3 linhas completadas" in _msg(3), _msg(3)


# ── Backend: o canal que não depende de cookie ─────────────────────────────
#  🩸 06/09/2026 — os cinco guardas abaixo liam o fonte da rota e passaram
#  VERDE com o registro DESLIGADO: trocar `_log_error(...)` por `print(...)`
#  deixa o texto `entrou area=` no arquivo, e envolver o log num `def` chamado
#  depois da autorização não muda a ordem em que as strings aparecem. Agora
#  eles CHAMAM a rota e olham as linhas que ela produziu.
import main as _m       # noqa: E402


class _Payload:
    def __init__(self, area=0, pe_direito=0):
        self.area = area
        self.pe_direito = pe_direito


def _logs_da_rota(monkeypatch, payload, dono=None, log_explode=False):
    """Chama `inform_project_area` e devolve (o que foi logado, o que voltou).

    `dono` é o que o `_require_project_owner` faz (por padrão, deixa passar).
    """
    linhas = []

    def _log(stage, msg, job_id=None, **k):
        linhas.append((stage, msg, job_id, k))
        if log_explode:
            raise RuntimeError("o banco de log caiu")

    chamou_dono = []

    def _dono(request, job_id):
        chamou_dono.append(job_id)
        if dono is not None:
            raise dono

    monkeypatch.setattr(_m, "_log_error", _log)
    monkeypatch.setattr(_m, "_require_project_owner", _dono)
    try:
        r = _m.inform_project_area("job-teste", payload, request=None)
        erro = None
    except Exception as e:          # HTTPException, ou o que vazar
        r, erro = None, e
    return linhas, chamou_dono, r, erro


def test_a_rota_registra_a_ENTRADA_e_nao_so_o_sucesso(monkeypatch):
    """🩸 O log rodava na ÚLTIMA linha do caminho feliz. '0 acionamentos' era
    '0 acionamentos BEM-SUCEDIDOS'.

    Aqui o clique MORRE na autorização — o caso que a gente precisa poder
    descartar — e mesmo assim tem que sobrar uma linha dizendo que ele entrou.
    """
    from fastapi import HTTPException
    linhas, _, _, erro = _logs_da_rota(
        monkeypatch, _Payload(area=120), dono=HTTPException(403, "não é seu"))
    assert isinstance(erro, HTTPException) and erro.status_code == 403, erro
    entradas = [l for l in linhas if "entrou area=" in str(l[1])]
    assert entradas, (
        "clique morreu em 403 e não deixou rastro em lugar NENHUM — 'o convite "
        "não convence' e 'o convite está quebrado' voltam a dar o mesmo zero. "
        "Linhas registradas: %r" % [l[:2] for l in linhas])
    assert entradas[0][0] == "motor:informou-depois", entradas[0][0]
    assert "120" in str(entradas[0][1]), entradas[0][1]


def test_o_registro_de_entrada_vem_ANTES_da_checagem_de_dono(monkeypatch):
    """🔑 Clique que morre em 401 é exatamente o caso que precisamos poder
    descartar. Se o log ficar depois da autorização, ele nunca vê esse caso.

    🪤 Não dá pra medir isso por ordem de linhas no arquivo: basta pôr o log
    dentro de um `def` lá em cima e chamá-lo lá embaixo. Aqui a ordem medida é
    a de EXECUÇÃO: a checagem de dono levanta, e o log já tem que ter saído.
    """
    from fastapi import HTTPException
    linhas, chamou_dono, _, erro = _logs_da_rota(
        monkeypatch, _Payload(area=120), dono=HTTPException(401, "sem token"))
    assert chamou_dono == ["job-teste"], chamou_dono
    assert isinstance(erro, HTTPException) and erro.status_code == 401
    assert [l for l in linhas if "entrou area=" in str(l[1])], (
        "o log de entrada foi parar DEPOIS da checagem de dono — volta a ser "
        "cego justamente pro clique que morre na autorização")


def test_toda_RECUSA_deixa_rastro(monkeypatch):
    """Cliente barrado na validação é indistinguível de cliente que nunca
    clicou — a menos que a recusa deixe o MOTIVO."""
    from fastapi import HTTPException
    casos = [
        (_Payload(area=99_999_999), "area-fora-da-faixa"),
        (_Payload(pe_direito=42), "pe-direito-fora-da-faixa"),
        (_Payload(), "veio-vazio"),
    ]
    for payload, motivo in casos:
        linhas, _, _, erro = _logs_da_rota(monkeypatch, payload)
        assert isinstance(erro, HTTPException) and erro.status_code == 400, (
            motivo, erro)
        recusas = [l for l in linhas if "recusado motivo=" in str(l[1])]
        assert recusas, (
            "a recusa %r não deixou rastro — as linhas foram %r"
            % (motivo, [l[:2] for l in linhas]))
        assert motivo in str(recusas[0][1]), (
            "a recusa registrou %r em vez de %r" % (recusas[0][1], motivo))
        assert recusas[0][0] == "motor:informou-depois", recusas[0][0]


def test_o_log_de_entrada_NAO_derruba_o_clique(monkeypatch):
    """🪤 Instrumentação que quebra o que mede é pior que não medir.

    Com o log EXPLODINDO, a rota tem que seguir até a checagem de dono. Se o
    `try` sumir de volta, o cliente leva 500 por causa do instrumento.
    """
    from fastapi import HTTPException
    linhas, chamou_dono, _, erro = _logs_da_rota(
        monkeypatch, _Payload(area=120), dono=HTTPException(403, "não é seu"),
        log_explode=True)
    assert chamou_dono == ["job-teste"], (
        "o log de entrada estourou e levou o clique junto (erro: %r) — a rota "
        "nem chegou na checagem de dono" % erro)
    assert isinstance(erro, HTTPException) and erro.status_code == 403, erro
    assert linhas, "o log nem foi tentado"


def test_CONTROLE_o_stage_continua_o_MESMO_e_registrado(monkeypatch):
    """🪤 Stage novo precisaria entrar na lista de stages conhecidos. Reusar o
    registrado mantém o funil inteiro numa consulta só.

    Aqui a rota roda até o fim e a gente cobra ENTROU e CONCLUIU no MESMO
    stage — é essa igualdade que faz o funil caber numa consulta só.
    """
    import json
    import urllib.request as _ur
    import spreadsheet as _sp

    proj = {"job_id": "job-teste", "typology": "office", "total_area": 0,
            "total_area_source": "", "warnings": [], "user_pe_direito": 0,
            "project_name": "Projeto de teste", "user_email": "",
            "user_name": "", "status": "done"}
    rows = [{"item_num": "1", "description": "Piso cerâmico", "unit": "m²",
             "quantity": 0, "observations": "", "ref_sheet": "",
             "confidence": "estimado", "origem": "", "discipline": "Pisos"}]

    class _Resp:
        def read(self):
            return json.dumps(rows).encode("utf-8")

    monkeypatch.setattr(_m, "_supa_rest_as_user",
                        lambda *a, **k: (200, [dict(proj)]))
    monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=None: _Resp())
    monkeypatch.setattr(_sp, "generate_spreadsheet",
                        lambda *a, **k: open(a[2], "wb").write(b"xlsx"))
    monkeypatch.setattr(_m, "_supabase_storage_upload", lambda *a, **k: True)
    monkeypatch.setattr(_m, "_persist_items_to_supabase", lambda *a, **k: 1)
    monkeypatch.setattr(_m, "_carimbar_planilha", lambda *a, **k: None)
    monkeypatch.setattr(_m, "_supabase_update", lambda *a, **k: True)
    monkeypatch.setattr(_m, "_projeto_patch", lambda *a, **k: True)

    linhas, _, r, erro = _logs_da_rota(monkeypatch, _Payload(area=120))
    assert erro is None, "a rota não chegou ao fim: %r" % erro
    assert r and r.get("status") == "ok", r

    stages = {l[0] for l in linhas}
    assert stages == {"motor:informou-depois"}, (
        "o funil da rota deixou de caber num stage só: %r" % stages)
    assert [l for l in linhas if "entrou area=" in str(l[1])], linhas
    assert [l for l in linhas if "concluiu area=" in str(l[1])], (
        "o log de sucesso perdeu o prefixo do funil — sem ele não dá pra "
        "separar 'entrou' de 'terminou': %r" % [l[1] for l in linhas])
    assert "motor:informou-depois" in _m._STAGES_DIAGNOSTICO, (
        "o stage saiu da lista de stages conhecidos do log")


# ── A armadilha que já mordeu duas vezes ───────────────────────────────────
def test_as_classes_do_convite_estao_VIVAS_no_css():
    """🚨 Tailwind aqui é build ESTÁTICO: classe fora do `tailwind.min.css`
    nasce INERTE e some calada — foi assim que um botão ficou branco no branco
    e o Pedro não achou."""
    import io
    import re
    css = io.open(os.path.join(os.path.dirname(_BACKEND), "tailwind.min.css"),
                  encoding="utf-8").read()
    i = _RV.find('id="convite-area"')
    trecho = _RV[i:_RV.find('id="items-container"')]
    classes = set()
    for grupo in re.findall(r'class="([^"]+)"', trecho):
        classes.update(grupo.split())
    mortas = [c for c in sorted(classes)
              if not re.search(re.escape("." + c.replace(":", "\\:")) +
                               r"(?=[\s,{:.>+~\[])", css)]
    assert not mortas, (
        "estas classes do convite NÃO estão no CSS compilado e vão nascer "
        "invisíveis: %s" % mortas)


def test_CONTROLE_o_detector_de_classe_morta_sabe_REPROVAR():
    """🧪 A 1ª versão deste detector, em 24/08, acusou 103 classes por bug de
    escape e passou verde acusando o site inteiro."""
    import io
    import re
    css = io.open(os.path.join(os.path.dirname(_BACKEND), "tailwind.min.css"),
                  encoding="utf-8").read()
    assert not re.search(r"\.bg-violet-700(?=[\s,{:.>+~\[])", css), (
        "bg-violet-700 passou a existir — troque o controle por outra classe "
        "ausente, senão este detector deixa de provar que reprova")
    assert re.search(r"\.bg-indigo-600(?=[\s,{:.>+~\[])", css), (
        "o detector não acha nem uma classe que existe — está quebrado")
