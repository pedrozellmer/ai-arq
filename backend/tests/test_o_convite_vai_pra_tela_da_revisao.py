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
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

from _corpo import corpo_de, corpo_js, fonte, sem_comentarios   # noqa: E402

_RV = fonte("revisao.html")


def _js(nome):
    corpo = corpo_js(nome, "revisao.html", _RV)
    return "\n".join(l for l in corpo.splitlines() if not l.strip().startswith("//"))


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
    página onde o convite morava."""
    for _id in ("convite-area", "convite-area-titulo", "convite-area-texto",
                "convite-area-input", "convite-area-submit", "convite-area-msg"):
        assert ('id="%s"' % _id) in _RV, (
            "o id %r sumiu — o JS escreve nele e o convite morre calado no "
            "catch (getElementById devolve null)" % _id)


def test_a_caixa_fica_ANTES_da_lista_de_itens():
    """Depois da lista ela ficaria abaixo de dezenas de cards — e a janela de
    atenção é de 3 minutos."""
    i_caixa = _RV.find('id="convite-area"')
    i_lista = _RV.find('id="items-container"')
    assert 0 < i_caixa < i_lista, (
        "o convite foi parar depois da lista de itens")


def test_chama_a_MESMA_rota_e_nao_uma_copia():
    js = _js("submitConviteArea")
    assert "/api/project/${jobId}/inform-area" in js, (
        "a tela da revisão parou de usar a rota que já existe — cópia de regra "
        "é a próxima pessoa consertando o lado errado")
    assert "authFetch(" in js, (
        "usou fetch cru: sem o header de autorização a rota devolve 401")


# ── O gatilho é o FATO ─────────────────────────────────────────────────────
def test_o_gatilho_e_a_LINHA_VAZIA_nao_a_frase_da_IA():
    """🩸 Em projeto.html a peneira de texto calava 22 projetos porque a IA
    escrevia 'Área total não extraída do DXF' em vez de uma das 4 frases."""
    js = _js("maybeShowConviteArea")
    assert "Number(it.quantity || 0) === 0" in js, "o critério de vazio sumiu"
    assert "_AREA_M2_RV.includes(u)" in js, "parou de filtrar por unidade de área"
    for frase in ("não medida", "nao medida", "informe a metragem", "observations"):
        assert frase not in js, (
            "o convite voltou a depender do texto escrito pela IA: %r" % frase)


def test_some_quando_NAO_ha_linha_vazia():
    js = _js("maybeShowConviteArea")
    assert "if (!vazias)" in js and "classList.add('hidden')" in js, (
        "o convite passou a aparecer em planilha completa — pedir dado que não "
        "resolve queima confiança")


def test_some_quando_o_cliente_JA_informou():
    """🪤 Repetir o pedido depois de atendido é cobrar duas vezes."""
    js = _js("maybeShowConviteArea")
    assert "projMeta.user_total_area" in js, (
        "o convite não confere se o cliente já informou a área")


def test_os_DOIS_ramos_escrevem_os_DOIS_campos():
    """🩸 Pego no DOM em projeto.html no mesmo dia: o ramo sem área trocava só
    o título e o parágrafo do outro ramo sobrevivia, afirmando uma área de capa
    que não existia."""
    js = corpo_js("maybeShowConviteArea", "revisao.html", _RV)
    i = js.find("} else {")
    assert i > 0, "sumiu o ramo de quem não tem área na capa"
    ramo = js[i:]
    assert "tit.textContent" in ramo and "txt.innerHTML" in ramo, (
        "o ramo sem área não reescreve os dois campos — o texto do outro "
        "ramo sobrevive e afirma uma área que não existe")


# ── Guarda de ponto de chamada ─────────────────────────────────────────────
def test_o_render_CHAMA_o_convite():
    """🪤 A função pode estar perfeita e nunca ser chamada — foi exatamente o
    caso da derivação de pintura, que existia e a rota não invocava."""
    render = sem_comentarios(corpo_js("render", "revisao.html", _RV))
    assert "maybeShowConviteArea()" in render, (
        "o render parou de chamar o convite — ele nunca aparece")


def test_CONTROLE_a_checagem_de_chamada_sabe_REPROVAR():
    falso = "function render() {\n  const x = 1;\n}"
    assert "maybeShowConviteArea()" not in falso


# ── A instrumentação, que é o ponto ────────────────────────────────────────
def test_o_convite_registra_que_foi_EXIBIDO():
    """🚨 O DENOMINADOR. Sem ele, 'ninguém clicou' e 'ninguém viu' são a mesma
    linha do banco — foi essa cegueira que custou 43 dias."""
    js = _js("maybeShowConviteArea")
    assert "'convite-area:exibido'" in js, (
        "o convite voltou a aparecer sem deixar registro de exibição")
    assert "linhas_vazias" in js, "o evento não guarda o tamanho do problema"


def test_o_botao_tem_rastreio_de_clique():
    assert 'data-track="convite-area-completar"' in _RV, (
        "o botão perdeu o data-track — o ouvinte de aiarq-utils.js converte "
        "[data-track] em clique:<nome> sem JS novo, e sem isso o clique é invisível")


def test_os_TRES_caminhos_de_falha_deixam_rastro():
    corpo = _js("maybeShowConviteArea") + _js("submitConviteArea")
    for ev in ("convite-area:render-falhou", "convite-area:submit-invalido",
               "convite-area:submit-erro"):
        assert ("'%s'" % ev) in corpo, (
            "a falha %r só existe no console do cliente — some pra sempre" % ev)


def test_a_telemetria_NAO_manda_texto_livre_do_cliente():
    """🔒 A 1ª versão mandava `bruto` (o que a pessoa digitou) e `erro` (a
    mensagem da exceção). O `/api/track` é rota ABERTA e o painel do admin lê
    o meta — texto livre não vira linha de banco por conveniência de depuração.
    Quem reprovou foi o guarda irmão `test_track_meta_allowlist`."""
    corpo = _js("maybeShowConviteArea") + _js("submitConviteArea")
    for chave in ("bruto:", "erro:"):
        assert chave not in corpo, (
            "o convite voltou a mandar %r na telemetria — texto do cliente" % chave)
    assert "status: Number(e && e.status)" in corpo, (
        "sumiu o status HTTP no erro — é o que separa 'morreu na autorização' "
        "de 'morreu no servidor'")


def test_o_sucesso_registra_QUANTAS_linhas_foram_preenchidas():
    js = _js("submitConviteArea")
    assert "'convite-area:submit-ok'" in js and "preenchidos" in js, (
        "o sucesso não registra o efeito — não dá pra saber se o convite "
        "resolve alguma coisa")


def test_a_mensagem_diz_o_que_ACONTECEU_nao_o_que_era_esperado():
    """🪤 O aviso que a Luana leu prometia que a área 'entra como base' e a
    regra impedia. Aqui a mensagem lê `filled_count`, que é o fato."""
    js = _js("submitConviteArea")
    assert "data.filled_count" in js, "a mensagem não lê o que o servidor fez"
    assert "nenhuma linha pôde ser completada" in js, (
        "sumiu o caminho honesto de 'recebi e não deu pra completar nada'")


# ── Backend: o canal que não depende de cookie ─────────────────────────────
def _rota():
    return corpo_de("inform_project_area")


def test_a_rota_registra_a_ENTRADA_e_nao_so_o_sucesso():
    """🩸 O log rodava na ÚLTIMA linha do caminho feliz. '0 acionamentos' era
    '0 acionamentos BEM-SUCEDIDOS'."""
    r = sem_comentarios(_rota())
    assert '"entrou area=' in r or "entrou area=" in r, (
        "a rota voltou a registrar só o fim do sucesso — clique que morre no "
        "meio some do sistema inteiro")


def test_o_registro_de_entrada_vem_ANTES_da_checagem_de_dono():
    """🔑 Clique que morre em 401 é exatamente o caso que precisamos poder
    descartar. Se o log ficar depois da autorização, ele nunca vê esse caso."""
    r = sem_comentarios(_rota())
    i_log = r.find("entrou area=")
    i_dono = r.find("_require_project_owner")
    assert i_log > 0 and i_dono > 0, "sumiu o log de entrada ou a checagem de dono"
    assert i_log < i_dono, (
        "o log de entrada foi parar DEPOIS da checagem de dono — volta a ser "
        "cego justamente pro clique que morre na autorização")


def test_toda_RECUSA_deixa_rastro():
    r = sem_comentarios(_rota())
    assert "def _recusa(" in r, "as validações voltaram a recusar em silêncio"
    for motivo in ("area-fora-da-faixa", "pe-direito-fora-da-faixa", "veio-vazio"):
        assert motivo in r, "a recusa %r não deixa motivo" % motivo


def test_o_log_de_entrada_NAO_derruba_o_clique():
    """🪤 Instrumentação que quebra o que mede é pior que não medir."""
    r = sem_comentarios(_rota())
    i = r.find("entrou area=")
    assert "try:" in r[max(0, i - 400):i], (
        "o log de entrada não está protegido por try — falha de banco passaria "
        "a derrubar o clique do cliente")


def test_CONTROLE_o_stage_continua_o_MESMO_e_registrado():
    """🪤 Stage novo precisaria entrar na lista de stages conhecidos. Reusar o
    registrado mantém o funil inteiro numa consulta só."""
    src = fonte("main.py")
    assert '"motor:informou-depois",' in src[:src.find("async def")], (
        "o stage saiu da lista de stages conhecidos do log")
    r = sem_comentarios(_rota())
    assert "concluiu area=" in r, "o log de sucesso perdeu o prefixo do funil"


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
