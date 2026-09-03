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
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

from _corpo import corpo_de, corpo_js, fonte, sem_comentarios   # noqa: E402

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
    js = _js_limpo("maybeShowAreaPrompt")
    assert "if (!noArea) return;" not in js, (
        "o veto por ter área na capa voltou — 33 projetos com 358 linhas de m² "
        "em branco somem do convite outra vez")
    assert "const noArea" not in js, "sobrou a variável do veto antigo"


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
    Luana leu e não se cumpriu (ver test_aviso_nao_promete_o_que_nao_fez)."""
    js = _js_limpo("maybeShowAreaPrompt")
    for promessa in ("ganham número", "serão preenchidas", "vão ser preenchidas",
                     "destravam", "linhas completadas"):
        assert promessa not in js, (
            "o convite promete resultado que a tela não controla: %r" % promessa)
    assert "em branco" in js, "o convite parou de dizer o FATO (linhas em branco)"


# ── A tela não pode quebrar em silêncio ────────────────────────────────────
def test_os_ids_que_o_JS_escreve_EXISTEM_no_html():
    """🚨 `getElementById` de id inexistente devolve null, o `.textContent`
    estoura, o `catch` engole e o convite NÃO APARECE — em silêncio, para
    todo mundo. É o modo de falha mais caro possível aqui."""
    for _id in ("area-prompt", "area-prompt-titulo", "area-prompt-texto",
                "area-input", "area-submit"):
        assert ('id="%s"' % _id) in _PROJ, (
            "o id %r sumiu do HTML e o JS escreve nele — o convite morre "
            "calado no catch" % _id)


def test_a_funcao_de_escape_existe():
    assert "function esc(" in _PROJ, (
        "o texto novo usa esc() e ela sumiu — o convite morre no catch")


# ── Backend: confirmar não é informar ──────────────────────────────────────
def _rota():
    return sem_comentarios(corpo_de("inform_project_area"))


def test_confirmar_a_area_MEDIDA_nao_carimba_informado():
    """🚨 `spreadsheet.py` troca a linha de premissa por causa deste campo:
    'Área construída — perímetro externo da laje' viraria 'INFORMADA POR VOCÊ
    (não medida pela planta)' só porque o cliente confirmou o que a planta
    mediu."""
    r = _rota()
    assert "_confirma_o_que_ja_tinha" in r, (
        "a rota voltou a carimbar 'informado' em cima de área medida quando o "
        "cliente apenas confirma o número da capa")
    assert "0.01 * _area_ja_tinha" in r, "a tolerância de confirmação sumiu"


def test_CONTROLE_area_NOVA_continua_sendo_informada():
    """🧪 Se isto quebrar, a correção virou 'nunca carimba' — e aí a área que o
    cliente REALMENTE informou passa a se apresentar como medida, que é a
    regra dura nº1 ao contrário."""
    r = _rota()
    assert 'pd.total_area_source = "informado"' in r, (
        "a rota parou de marcar como informada a área que o cliente informou")


def test_a_ASSINATURA_da_rota_sobrevive_nos_dois_avisos():
    """🪤 'Preenchemos os itens de piso/forro/laje' é a única marca que prova
    que a mini-revisão rodou (foi assim que se mediu 0 usos em 293 projetos).
    Se um dos dois ramos perder a frase, a medição de uso passa a mentir."""
    r = _rota()
    assert r.count("Preenchemos os itens de piso/forro/laje") >= 2, (
        "um dos ramos do aviso perdeu a assinatura da rota — o uso da "
        "mini-revisão vira invisível para metade dos casos")


def test_o_aviso_de_confirmacao_nao_afirma_falta_de_cota():
    r = _rota()
    i = r.find("_confirma_o_que_ja_tinha:")
    j = r.find("elif area > 0:", i)
    assert i > 0 and j > i, "os dois ramos do aviso sumiram"
    assert "não trazia cota" not in r[i:j], (
        "o aviso de confirmação afirma que a planta não tinha cota — e tinha")
    assert "CONFIRMADA POR VOCÊ" in r[i:j], (
        "o aviso de confirmação parou de dizer que foi confirmação")
