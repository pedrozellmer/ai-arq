# -*- coding: utf-8 -*-
"""11/10/2026 — os consertos da 2ª auditoria do Escritório (27/09), nas TELAS.

O Pedro: "quando entro num projeto que já tá no escritório ele ainda abre na página antiga". E mais o que a auditoria
achou em volta: a pendência do cliente que nunca desligava, o cartão que nascia "do cliente" sem aviso, a revisão
antiga que seguia pedindo aprovação, o e-mail do reenvio que virava convite de equipe.

🔑 O que é DECISÃO roda no motor JS (dukpy), com o código da página: o guarda cobra pra onde a pessoa vai e o que é
gravado, não o texto do fonte. O que é só ligação entre peças (um link, um atributo) fica em guarda de texto, declarado.
"""
import io
import json
import os
import re
import sys

import dukpy  # noqa: F401  — a falta dele é ERRO, nunca skip (ver _jsbancada.py)

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

from _jsbancada import funcao_js  # noqa: E402
from _navegador import sem_await  # noqa: E402

NL = chr(10)
UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def _ler(nome):
    return io.open(os.path.join(_RAIZ, nome), encoding="utf-8").read()


E = _ler("escritorio.html")
ML = _ler("menu-lateral.js")
D = _ler("dashboard.html")
P = _ler("projeto.html")


def _linha(src, comeco):
    """A declaração de UMA linha que começa com `comeco` (um `const x = ...;`)."""
    i = src.index(NL + comeco) + 1
    return src[i:src.index(NL, i)]


def _js(pedacos, expr):
    return json.loads(dukpy.evaljs(list(pedacos) + ["JSON.stringify(" + expr + ")"]))


# ══ 1. projeto.html na Visão geral de um projeto LIGADO ao Escritório → a Página do projeto ══
_IR = [funcao_js("talvezIrProEscritorio", "menu-lateral.js", ML), funcao_js("confirmouEscritorio", "menu-lateral.js", ML)]


def _vai(arq="projeto.html", onde="", pronto="true", banco=UUID, esc="null", do_mapa="false"):
    """Pra onde a página foi mandada (None = ficou). `banco` = o id que o banco confirmou (None = não confirmou)."""
    pre = ("var foi = null; var window = { aiarqProjetoPronto: " + pronto + " };"
           "var location = { hash: " + json.dumps(onde) + ", replace: function (u) { foi = u; } };"
           "var UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;"
           "var ARQ = " + json.dumps(arq) + "; var ESC = " + esc + "; var ESC_DO_MAPA = " + do_mapa + ";"
           "var ESC_CONFIRMADO = '';")
    chama = ("confirmouEscritorio(" + json.dumps(banco) + ");") if banco is not None else "talvezIrProEscritorio();"
    return _js([pre] + _IR + [chama], "foi")


def test_visao_geral_de_projeto_ligado_e_pronto_vai_pra_pagina_do_projeto():
    destino = "escritorio.html#/p/" + UUID + "/capa"
    assert _vai() == destino
    assert _vai(onde="#visao") == destino
    assert _vai(arq="projeto") == destino                       # endereço servido sem o .html


def test_controles_fica_onde_esta():
    assert _vai(onde="#quantitativo") is None                   # outra vista: é pra lá que a pessoa quer ir
    assert _vai(onde="#processamento") is None
    assert _vai(pronto="false") is None                         # processando ou com erro: acompanha e reprocessa aqui
    assert _vai(pronto="undefined") is None                     # a página ainda não disse nada
    assert _vai(arq="cronograma.html") is None                  # só a projeto.html tem "Visão geral"
    assert _vai(banco="id-que-nao-e-uuid") is None              # só UUID vira endereço


def test_a_lembranca_do_navegador_nao_manda_ninguem_mas_a_marca_da_aba_sim():
    lembrado = json.dumps({"id": UUID, "job": "j1"})
    assert _vai(banco=None, esc=lembrado, do_mapa="true") is None        # lembrança velha: espera o banco
    assert _vai(banco=None, esc=lembrado, do_mapa="false") == "escritorio.html#/p/" + UUID + "/capa"
    assert _vai(banco=None) is None                                      # nem banco nem marca: projeto fora do Escritório


def test_quem_confirma_e_o_banco_e_a_pagina_diz_quando_esta_pronta():
    """Guarda de TEXTO, declarado: a ligação entre as peças (quem chama quem)."""
    d = funcao_js("descobrirEscritorio", "menu-lateral.js", ML)
    assert d.index("if (!r.data) {") < d.index("confirmouEscritorio(c.id);")           # só com a linha do banco
    m = funcao_js("montarEquipe", "menu-lateral.js", ML)
    assert "if (a.escritorio_id) confirmouEscritorio(a.escritorio_id);" in m
    assert "talvezIrProEscritorio: talvezIrProEscritorio" in ML
    assert "window.aiarqProjetoPronto = !emProcesso && !emErro;" in P
    assert P.count("window.aiarqMenu.talvezIrProEscritorio()") == 2                    # ao carregar e no voltar do navegador


# ══ 2. o painel manda direto ══
_DEST = funcao_js("destinoDoProjeto", "dashboard.html", D)


def _destino(mapa, job, pronto):
    return _js(["var ESC_POR_JOB = " + json.dumps(mapa) + ";", _DEST],
               "destinoDoProjeto(" + json.dumps(job) + ", " + ("true" if pronto else "false") + ")")


def test_painel_projeto_ligado_e_pronto_abre_a_pagina_do_projeto():
    assert _destino({"job1": UUID}, "job1", True) == "escritorio.html#/p/" + UUID + "/capa"
    assert _destino({"job1": UUID}, "job1", False) == "projeto.html?job_id=job1"       # em erro: vê o motivo lá
    assert _destino({"job1": UUID}, "job2", True) == "projeto.html?job_id=job2"        # fora do Escritório
    assert _destino({}, "a b&c", True) == "projeto.html?job_id=a%20b%26c"


def test_painel_o_mapa_que_chega_depois_acerta_os_links_ja_desenhados():
    doc = ("var links = [{ a: { 'data-abrir': 'job1', 'data-pronto': '1', href: 'x' } },"
           "             { a: { 'data-abrir': 'job1', 'data-pronto': '0', href: 'x' } },"
           "             { a: { 'data-abrir': 'job9', 'data-pronto': '1', href: 'x' } }];"
           "links.forEach(function (l) { l.getAttribute = function (k) { return l.a[k]; };"
           "  l.setAttribute = function (k, v) { l.a[k] = v; }; });"
           "var document = { querySelectorAll: function (s) { return s === 'a[data-abrir]' ? links : []; } };")
    r = _js(["var ESC_POR_JOB = " + json.dumps({"job1": UUID}) + ";", _DEST,
             funcao_js("ligarPortasDoEscritorio", "dashboard.html", D), doc, "ligarPortasDoEscritorio();"],
            "links.map(function (l) { return l.a.href; })")
    assert r == ["escritorio.html#/p/" + UUID + "/capa", "projeto.html?job_id=job1", "projeto.html?job_id=job9"]


def test_painel_as_tres_portas_usam_o_destino_e_o_mapa_e_so_dos_projetos_da_pessoa():
    """Guarda de TEXTO, declarado."""
    c = funcao_js("renderProjectCard", "dashboard.html", D)
    assert "window.location.href=destinoDoProjeto('${escProj(p.job_id)}',${done})" in c
    assert 'href="${escProj(destinoDoProjeto(p.job_id, done))}" data-abrir="${escProj(p.job_id)}" data-pronto="${done ? 1 : 0}"' in c
    assert "projeto.html?job_id=${escProj(p.job_id)}'" not in c                         # a porta antiga do cartão saiu
    assert 'href="${escapeH(destinoDoProjeto(p.job_id, _st === \'done\'))}" data-abrir="${escapeH(p.job_id)}"' in D
    assert "sbClient.from('escritorio_projetos').select('id,job_id').eq('dono', currentUser.id).not('job_id', 'is', null)" in D


# ══ 3. o quadro: a pendência do cliente ══
_QUADRO_BASE = """
var ADMIN = true, CLIENTES = 1, gravado = [], avisos = [], perguntou = null, SEGUIR = null;
var PROJ = { id: 'p1', etapa_atual: 'Briefing' }, EU = { id: 'u1' }, PESSOAS_T = [];
var ST_EQUIPE = ['afazer', 'dev', 'revdtz'];
function souAdmin() { return ADMIN; }
function render() {} function falhou() {} function visivel() { return true; }
function toast(t) { avisos.push(t); } function stT(k) { return k; }
function etapaDoFiltro() { return ''; } function meuMembro() { return { id: 'm-eu' }; }
function avisoCliente() { return 'AVISO'; }
function confirmarDeFora(av, botao, seguir) { perguntou = botao; SEGUIR = seguir; }
var MEMBROS = [];
function povoar() { MEMBROS = []; for (var i = 0; i < CLIENTES; i++) MEMBROS.push({ status: 'ativo', papel: 'cliente' }); }
var sb = { from: function (t) { return {
  update: function (m) { gravado.push({ t: t, m: m }); return { eq: function () { return { error: null }; } }; },
  insert: function (o) { gravado.push({ t: t, o: o });
    return { error: null, select: function () { return { single: function () { return { data: Object.assign({ id: 'novo' }, o), error: null }; } }; } }; } }; } };
"""
_QUADRO = [_QUADRO_BASE, _linha(E, "const podeLevar = "), _linha(E, "const clientesAtivos = "),
           _linha(E, "const saiDaListaDoCliente = "),
           sem_await(funcao_js("mover", "escritorio.html", E)), sem_await(funcao_js("criarCartao", "escritorio.html", E))]


def _mover(status, do_cliente, destino, clientes=1, seguir=False):
    cena = ("CLIENTES = %d; povoar(); var TAR = [{ id: 't1', status: %s, do_cliente: %s, posicao: 1 }];"
            % (clientes, json.dumps(status), "true" if do_cliente else "false"))
    acao = "mover('t1', " + json.dumps(destino) + ", 0);" + (" if (SEGUIR) SEGUIR();" if seguir else "")
    return _js(_QUADRO + [cena, acao], "{ gravado: gravado, avisos: avisos, perguntou: perguntou, cartao: TAR[0] }")


def test_cartao_que_volta_de_aguardando_cliente_sai_da_lista_do_cliente():
    """ADM-5: o cartão ficava pra sempre em "O que depende de você" do cliente, com a bola de volta no escritório."""
    for destino in ("afazer", "dev", "revdtz", "revsol"):
        r = _mover("cliente", True, destino)
        assert r["gravado"][0]["m"]["do_cliente"] is False and r["gravado"][0]["m"]["status"] == destino, destino
        assert r["cartao"]["do_cliente"] is False and "saiu da lista do cliente" in r["avisos"][0]


def test_controles_do_caminho_de_volta():
    for destino in ("aprov", "ok"):                       # resolvido: continua com ele ("Já resolvidas")
        r = _mover("cliente", True, destino)
        assert "do_cliente" not in r["gravado"][0]["m"] and r["cartao"]["do_cliente"] is True, destino
    r = _mover("dev", True, "afazer")                     # marcada à mão no cartão, fora da coluna: ninguém mexe
    assert "do_cliente" not in r["gravado"][0]["m"] and r["cartao"]["do_cliente"] is True
    r = _mover("cliente", False, "dev")                   # nunca foi do cliente: nada a tirar
    assert "do_cliente" not in r["gravado"][0]["m"] and "saiu da lista" not in r["avisos"][0]


def test_controle_levar_pra_aguardando_cliente_continua_perguntando():
    r = _mover("dev", False, "cliente")
    assert r["perguntou"] == "Mostrar e mover" and r["gravado"] == []
    r = _mover("dev", False, "cliente", seguir=True)
    assert r["gravado"][0]["m"]["do_cliente"] is True and r["gravado"][0]["m"]["status"] == "cliente"
    assert _mover("dev", False, "cliente", clientes=0)["perguntou"] is None       # sem cliente no projeto: só move


def _criar(coluna, clientes, seguir=False):
    cena = "CLIENTES = %d; povoar(); var TAR = [];" % clientes
    acao = "criarCartao(" + json.dumps(coluna) + ", 'Cobrar a resposta do piso');" + (" if (SEGUIR) SEGUIR();" if seguir else "")
    return _js(_QUADRO + [cena, acao], "{ gravado: gravado.filter(function (g) { return g.t === 'escritorio_tarefas'; }), perguntou: perguntou }")


def test_criar_direto_em_aguardando_cliente_avisa_antes_de_mostrar_ao_cliente():
    """FORA-1/ADM-4: o cartão nascia `do_cliente` sem o aviso que o arrastar e o salvar mostram."""
    r = _criar("cliente", 1)
    assert r["perguntou"] == "Criar e mostrar" and r["gravado"] == []          # nada gravado antes do ok
    r = _criar("cliente", 1, seguir=True)
    assert len(r["gravado"]) == 1 and r["gravado"][0]["o"]["do_cliente"] is True and r["gravado"][0]["o"]["status"] == "cliente"


def test_sem_cliente_no_projeto_o_cartao_nao_fica_marcado_a_espera_do_convite():
    """FORA-1: os cartões criados na coluna antes do convite apareciam todos de uma vez pro cliente quando ele entrava."""
    r = _criar("cliente", 0)
    assert r["perguntou"] is None and r["gravado"][0]["o"]["do_cliente"] is False and r["gravado"][0]["o"]["status"] == "cliente"
    r = _criar("afazer", 1)                                # controle: coluna da equipe nunca pergunta nem marca
    assert r["perguntou"] is None and r["gravado"][0]["o"]["do_cliente"] is False


def test_o_convite_de_cliente_diz_os_cartoes_que_ele_ja_vai_ver():
    pre = ("var AVISO_PERFIL = { equipe: 'EQ', fornecedor: 'FO', cliente: 'CLI.' };"
           "function esc(s) { return String(s).replace(/</g, '&lt;').replace(/>/g, '&gt;'); }")
    i = E.index(NL + "const avisoDoPerfil = (p) => {") + 1
    fn = E[i:E.index(NL + "};", i) + 3]
    com = "var TAR = [{ titulo: 'Aprovar <b>piso</b>', do_cliente: true }, { titulo: 'Interno', do_cliente: false }];"
    r = _js([pre, com, fn], "[avisoDoPerfil('cliente'), avisoDoPerfil('equipe')]")
    assert "já existe 1 cartão marcado" in r[0] and "Aprovar &lt;b&gt;piso&lt;/b&gt;" in r[0] and "Interno" not in r[0]
    assert r[1] == "EQ"
    assert _js([pre, "var TAR = [{ titulo: 'x', do_cliente: false }];", fn], "avisoDoPerfil('cliente')") == "CLI."


# ══ 4. emissões: a revisão substituída ══
def _emissoes(cliente, r01_pra_mim=True, respondi_r01=False):
    i = E.index(NL + "const evDa = ") + 1
    bloco = E[i:E.index(NL + "const quemRespondeu", i)]
    assert "const esperaResposta = (e) => {" in bloco and "const substituidaPor = " in bloco and len(bloco) < 6000
    ev = [{"emissao_id": "e0", "tipo": "enviado"}, {"emissao_id": "e1", "tipo": "enviado"}]
    if respondi_r01:
        ev.append({"emissao_id": "e1", "tipo": "aprovado", "pelo_cliente": True, "registrado_por": "u-cli"})
    dest = [{"emissao_id": "e0", "membro_id": "m-cli", "permission_id": "p0"}]
    if r01_pra_mim:
        dest.append({"emissao_id": "e1", "membro_id": "m-cli", "permission_id": "p1"})
    pre = ("var EU = { id: 'u-cli' }, MEMBROS = [];"
           "var EMI = [{ id: 'e0', arquivo_id: 'A', revisao: 0 }, { id: 'e1', arquivo_id: 'A', revisao: 1 },"
           "           { id: 'x0', arquivo_id: 'B', revisao: 0 }];"
           "var EMI_EV = " + json.dumps(ev + [{"emissao_id": "x0", "tipo": "enviado"}]) + ";"
           "var DEST = " + json.dumps(dest + [{"emissao_id": "x0", "membro_id": "m-cli", "permission_id": "px"}]) + ";"
           "function souCliente() { return " + ("true" if cliente else "false") + "; }"
           "function meuMembro() { return { id: 'm-cli' }; } function deFora() { return true; }")
    return _js([pre, bloco], "{ r00: esperaResposta(EMI[0]), r01: esperaResposta(EMI[1]), outro: esperaResposta(EMI[2]),"
                             "  pela: (substituidaPor(EMI[0]) || {}).id || null }")


def test_revisao_antiga_deixa_de_pedir_aprovacao_quando_a_nova_chega_pro_cliente():
    """BANCO-3: o cliente via R00 e R01 com Aprovar e aprovava a versão errada."""
    r = _emissoes(cliente=True)
    assert r == {"r00": False, "r01": True, "outro": True, "pela": "e1"}


def test_controles_da_revisao_substituida():
    assert _emissoes(cliente=True, r01_pra_mim=False)["r00"] is True          # a nova não foi pra ele: a antiga segue
    r = _emissoes(cliente=True, respondi_r01=True)
    assert r["r00"] is False and r["r01"] is False                            # respondeu a nova: nada mais espera por ele
    assert _emissoes(cliente=False) == {"r00": True, "r01": True, "outro": True, "pela": "e1"}   # o escritório vê as duas "com o cliente"


def test_a_tela_do_cliente_diz_por_qual_revisao_foi_substituida_e_nao_atribui_a_aprovacao_a_ele():
    """Guarda de TEXTO, declarado."""
    t = funcao_js("telaEmissoesDeFora", "escritorio.html", E)
    assert "const nova = cli && !espera && (ultimoEv(e) || {}).tipo === 'enviado' ? substituidaPor(e) : null;" in t
    assert "Substituída pela ${revTxt(nova.revisao)}" in t
    assert "O escritório registrou uma aprovação" in t and "registrou a sua aprovação" not in E          # FORA-5


# ══ 5. o convite: reenviar com o e-mail trocado ══
def test_reenvio_trava_o_email_e_so_omite_o_perfil_no_mesmo_email():
    """ADM-1 (a metade da tela; a do servidor recusa convite novo sem perfil). Guarda de TEXTO, declarado."""
    c = funcao_js("convidar", "escritorio.html", E)
    assert "${pre.email ? ' readonly style=\"background:#F8FAFC\"' : ''}" in c
    assert "cancele este convite e convide o e-mail certo" in c
    e = funcao_js("enviarConvite", "escritorio.html", E)
    assert e.index("const mesmoEmail = ") < e.index("delete corpo.perfil;")
    assert e.count("delete corpo.perfil;") == 1 and "if (mesmoEmail && CV_PRE.perfil" in e


# ══ 6. Editar do fornecedor: a pasta de hoje ══
def test_editar_do_fornecedor_acha_a_pasta_de_hoje_pelo_nome_e_nenhuma_tira():
    """ADM-2/BANCO-1. Guarda de TEXTO, declarado: a função é DOM do começo ao fim."""
    f = funcao_js("carregarPastasDoFornecedor", "escritorio.html", E)
    assert "const igual = ps.find((p) => p.nome === atual.nome);" in f
    assert "else { ps.unshift({ id: PASTA_DE_HOJE, nome: atual.nome + ' (a de hoje)' }); deHoje = PASTA_DE_HOJE; }" in f
    assert "sel.value = deHoje; sel.dataset.inicial = deHoje; sel.dataset.pronto = '1';" in f
    ed = funcao_js("editarPessoa", "escritorio.html", E)
    assert "m.drive_pasta_nome ? { nome: m.drive_pasta_nome } : null" in ed and "m.drive_pasta_id" not in ed
    s = funcao_js("salvarPessoa", "escritorio.html", E)
    assert ("sel.dataset.pronto && sel.value !== PASTA_DE_HOJE && (sel.value || '') !== (sel.dataset.inicial || '')") in s
    assert "m.drive_pasta_id" not in s
    assert "{ pasta: sel.value || null }" in s


# ══ 7. um clique por vez no que mexe no Drive ══
def test_um_clique_por_vez():
    """ADM-3 (a metade da tela). `umaVez` roda de verdade; o resto é ligação."""
    pre = "var n = 0; var b = { disabled: false, isConnected: true };"
    fn = sem_await(funcao_js("umaVez", "escritorio.html", E))
    # durante o pedido o botão está travado: um 2º clique não entra
    r = _js([pre, fn, "umaVez(b, function () { n++; umaVez(b, function () { n += 10; }); });"], "[n, b.disabled]")
    assert r == [1, False]
    r = _js([pre, fn, "try { umaVez(b, function () { throw new Error('x'); }); } catch (e) {}"], "b.disabled")
    assert r is False                                                          # erro não deixa o botão preso
    assert "onclick=\"umaVez(this, () => salvarPessoa('${id}'))\"" in E
    u = funcao_js("usarPasta", "escritorio.html", E)
    assert u.index("if (SINC_EM_CURSO) return;") < u.index("apiEsc(`projetos/${PROJ.id}/pasta`, 'POST', { pasta: String(pasta).trim() })")
    s = funcao_js("sincronizarPasta", "escritorio.html", E)
    assert s.index("if (SINC_EM_CURSO) {") < s.index("apiEsc(`projetos/${PROJ.id}/drive/sincronizar`, 'POST')")
    assert "finally { SINC_EM_CURSO = false; }" in s


# ══ 8. saídas de quem é de fora, Processamento, Fotos e o login que devolve pro destino ══
def test_saidas_de_quem_e_de_fora():
    """FORA-3/NAV-9. Guarda de TEXTO, declarado."""
    c = funcao_js("carregarProjetos", "escritorio.html", E)
    assert "TEM_PAINEL = NO_PILOTO || PROJETOS.some((p) => !p.externo) || !!meus.error || (meus.count || 0) > 0;" in c
    r = funcao_js("renderMoldura", "escritorio.html", E)
    assert "const casaDeFora = PROJ && PROJETOS.length <= 1 ? `#/p/${PROJ.id}/capa` : '#/';" in r
    assert "sm.setAttribute('href', mk && !souEquipe() ? casaDeFora : TEM_PAINEL ? 'dashboard.html' : '#/');" in r
    assert "← ${PROJETOS.length > 1 ? 'Seus projetos' : 'Escritório'}" not in r        # o link que recarregava a mesma tela
    assert "const voltaDeFora = PROJETOS.length > 1 ?" in r and '<a href="${casaDeFora}">${esc(nomeEscritorio())}</a>' in r
    assert "${TEM_PAINEL ? '<a class=\"s-it\" href=\"dashboard.html\">← Painel do AI.arq</a>' : ''}" in r


def test_processamento_e_fotos_no_menu_do_escritorio():
    """NAV-5/NAV-11. O menu do Escritório é montado de verdade, com os grupos reais."""
    g = funcao_js("gruposProjeto", "menu-lateral.js", ML) + funcao_js("gruposEscritorio", "menu-lateral.js", ML)
    pre = "var JOB = 'j1', ESC = { id: '" + UUID + "' }; function url(p) { return p + '?job_id=' + JOB; }"
    grupos = _js([pre, g], "gruposEscritorio().map(function (x) { return x.itens.map(function (i) { return i.rotulo; }); })")
    assert grupos[0] == ["Página do projeto", "Tarefas", "Arquivos", "Emissões", "Fotos", "Atas", "Equipe"]
    assert "Processamento" in grupos[1] and "Visão geral" not in grupos[1]
    # pra equipe quem tira o Processamento continua sendo o tirarItensDoDono (pelo data-track)
    assert "data-track=\"menu-processamento\"" in funcao_js("tirarItensDoDono", "menu-lateral.js", ML)
    assert "${souAdmin() ? fora(`projeto.html?job_id=${J}#processamento`, 'proc', 'Processamento') : ''}" in E
    assert "${souAdmin() ? tool(`projeto.html?job_id=${J}#processamento`, 'proc', 'Processamento'," in E
    assert re.search(r"\n  proc: '<path", E) and "proc: ['#475569'" in E


def test_sem_sessao_o_login_devolve_pro_destino_inteiro():
    """NAV-6. Guarda de TEXTO, declarado."""
    assert "location.href = 'login.html?redirect=' + encodeURIComponent('escritorio.html' + location.hash);" in E
    for pagina in ("projeto", "revisao", "memorial"):
        src = P if pagina == "projeto" else _ler(pagina + ".html")
        assert ("'login.html?redirect=' + encodeURIComponent('%s.html' + location.search + location.hash)" % pagina) in src, pagina
        assert "window.location.href = 'login.html'; return;" not in src, pagina
    # o login e o painel aceitam o destino com # (senão o hash do Escritório se perdia de novo)
    aceita = "/^[a-z0-9_-]+\\.html(\\?[^\\s]*)?(#[^\\s]*)?$/i"
    assert aceita in _ler("login.html") and aceita in D


def test_recusado_pelo_servidor_nao_e_problema_de_conexao():
    """NAV-12. Guarda de TEXTO, declarado."""
    i = P.index("if (!proj) {")
    bloco = P[i:P.index("Não consegui carregar este projeto.", i)]
    assert "negado = !!(a && a.negado);" in bloco and 'href="escritorio.html"' in bloco
    assert "Sua conta não tem acesso a esta página do projeto." in bloco


def test_apagar_projeto_com_a_pasta_sumida_pede_confirmacao():
    """SERV-1 (a metade da tela). Guarda de TEXTO, declarado."""
    a = funcao_js("apagarProjeto", "escritorio.html", E)
    assert '<div class="aviso" id="ap-aviso" hidden' in a and "$('ap-ok').textContent = 'Apagar mesmo assim';" in a


def test_a_ata_diz_quem_e_de_fora():
    """ADM-4/BANCO-4: o "Quem?" roda de verdade — o homônimo de fora aparece com o perfil, depois da equipe."""
    pre = ("var MEMBROS = [{ id: 'm1', nome: 'Ana Fornecedora', papel: 'fornecedor', status: 'ativo' },"
           "               { id: 'm2', nome: 'Ana Equipe', papel: 'freela', status: 'ativo' },"
           "               { id: 'm3', nome: 'Caio Cliente', papel: 'cliente', status: 'ativo' },"
           "               { id: 'm4', nome: 'Saiu', papel: 'freela', status: 'removido' }];"
           "function esc(s) { return String(s); } function curto(m) { return m.nome.split(' ')[0]; }"
           "function deFora(m) { return m.papel === 'cliente' || m.papel === 'fornecedor'; }")
    html = _js([pre, _linha(E, "const PERFIL_CURTO = "), funcao_js("linhaTarefaAta", "escritorio.html", E)], "linhaTarefaAta(0)")
    opcoes = re.findall(r'<option value="([^"]*)">([^<]*)</option>', html)
    assert opcoes == [("", "Quem?"), ("m2", "Ana"), ("m1", "Ana (fornecedor)"), ("m3", "Caio (cliente)"), ("cliente", "O cliente")]
    assert 'onchange="avisoDaLinhaDaAta(this)"' in html and 'data-c="aviso" hidden' in html
