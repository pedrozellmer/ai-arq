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
var MEMBROS = [], GRAVANDO = {}, CONTA = 1, releu = 0;
function recarregar() { releu++; }
function povoar() { MEMBROS = []; for (var i = 0; i < CLIENTES; i++) MEMBROS.push({ status: 'ativo', papel: 'cliente' }); }
var sb = { from: function (t) { return {
  update: function (m, o) { gravado.push({ t: t, m: m, contou: !!(o && o.count === 'exact') });
    return { eq: function () { return { error: null, count: CONTA }; } }; },
  insert: function (o) { gravado.push({ t: t, o: o });
    return { error: null, select: function () { return { single: function () { return { data: Object.assign({ id: 'novo' }, o), error: null }; } }; } }; } }; } };
"""
_QUADRO = [_QUADRO_BASE, _linha(E, "const podeLevar = "), _linha(E, "const clientesAtivos = "),
           _linha(E, "const saiDaListaDoCliente = "),
           sem_await(funcao_js("umaGravacao", "escritorio.html", E)), sem_await(funcao_js("semAcessoAoCartao", "escritorio.html", E)),
           sem_await(funcao_js("mover", "escritorio.html", E)), sem_await(funcao_js("criarCartao", "escritorio.html", E))]


def _mover(status, do_cliente, destino, clientes=1, seguir=False, conta=1):
    cena = ("CLIENTES = %d; CONTA = %d; povoar(); var TAR = [{ id: 't1', status: %s, do_cliente: %s, posicao: 1 }];"
            % (clientes, conta, json.dumps(status), "true" if do_cliente else "false"))
    acao = "mover('t1', " + json.dumps(destino) + ", 0);" + (" if (SEGUIR) SEGUIR();" if seguir else "")
    return _js(_QUADRO + [cena, acao], "{ gravado: gravado, avisos: avisos, perguntou: perguntou, cartao: TAR[0], releu: releu }")


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


# ══ 9. trocar o projeto medido ligado (NAV-4 — Pedro, 12/10: "Botão pra trocar") ══
def _candidatos(lista, atual, ligados):
    return _js([funcao_js("candidatosDeMedido", "escritorio.html", E)],
               "candidatosDeMedido(" + json.dumps(lista) + ", " + json.dumps(atual) + ", new Set(" + json.dumps(ligados)
               + ")).map(function (p) { return [p.job_id, p.novaLeitura]; })")


_MEDIDOS = [                                            # na ordem do banco: o mais recente primeiro
    {"job_id": "antigo", "status": "done"},
    {"job_id": "atual", "status": "done"},
    {"job_id": "filho", "status": "done", "parent_job_id": "atual"},
    {"job_id": "processando", "status": "processing", "parent_job_id": "atual"},
    {"job_id": "erro", "status": "error"},
    {"job_id": "arquivado", "status": "done", "archived": True},
    {"job_id": "de-outro", "status": "done"},
]


def test_quem_pode_ser_ligado_e_a_leitura_nova_vem_primeiro():
    """Reprocessar cria outro projeto medido: é ele (pronto) que a admin quer ligar. Fica de fora o de hoje, o que
    ainda processa ou deu erro, o arquivado e o que já está noutro projeto do Escritório."""
    assert _candidatos(_MEDIDOS, "atual", ["de-outro"]) == [["filho", True], ["antigo", False]]
    # projeto que nasceu sem prancha: ninguém é "leitura nova" e a ordem é a do banco
    assert _candidatos(_MEDIDOS, None, ["de-outro"]) == [["antigo", False], ["atual", False], ["filho", False]]
    assert _candidatos([], "atual", []) == [] and _candidatos(None, "atual", []) == []


def _ligar(resposta, antes="velho", admin="true"):
    pre = ("var ADMIN = " + admin + ", avisos = [], gravou = null, fechou = 0;"
           "var PROJ = { id: 'p1', job_id: " + json.dumps(antes) + " }, OBRA = { projeto: 'p1', pct: 50 };"
           "function souAdmin() { return ADMIN; } function toast(t, erro) { avisos.push([t, !!erro]); }"
           "function falhou(e, t) { avisos.push([t, true]); } function fecharModal() { fechou++; } function render() {}"
           "var guardado = { aiarq_esc_mapa: JSON.stringify({ velho: { id: 'p1' }, outro: { id: 'p2' } }) };"
           "var localStorage = { getItem: function (k) { return guardado[k] || null; }, setItem: function (k, v) { guardado[k] = v; } };"
           "var sb = { from: function () { return { update: function (m) { gravou = m; return { eq: function () {"
           "  return { select: function () { return " + json.dumps(resposta) + "; } }; } }; } }; } };")
    return _js([pre, sem_await(funcao_js("ligarMedido", "escritorio.html", E)), "ligarMedido('novo');"],
               "{ job: PROJ.job_id, avisos: avisos, gravou: gravou, fechou: fechou,"
               "  mapa: Object.keys(JSON.parse(guardado.aiarq_esc_mapa)), obra: OBRA }")


def test_trocar_o_medido_grava_esquece_o_antigo_e_pede_o_cronograma_de_novo():
    r = _ligar({"data": [{"id": "p1"}], "error": None})
    assert r["gravou"] == {"job_id": "novo"} and r["job"] == "novo" and r["fechou"] == 1
    assert r["mapa"] == ["outro"]                                   # a lembrança do navegador sobre o antigo saiu
    assert r["obra"] == {"projeto": None, "pct": None}              # o % da obra era do cronograma do antigo
    assert r["avisos"] == [["Projeto medido trocado: a equipe já vê o novo", False]]
    assert _ligar({"data": [{"id": "p1"}], "error": None}, antes=None)["avisos"][0][0].startswith("Projeto medido ligado")


def test_troca_que_o_banco_nao_fez_nao_vira_trocado():
    r = _ligar({"data": [], "error": None})                         # a RLS filtrou calada (não é a admin)
    assert r["job"] == "velho" and r["fechou"] == 0 and r["avisos"][0][1] is True and "só a admin" in r["avisos"][0][0]
    r = _ligar({"data": None, "error": {"code": "23505"}})          # o medido já está noutro projeto do Escritório
    assert r["job"] == "velho" and "já está ligado a outro projeto" in r["avisos"][0][0]
    r = _ligar({"data": None, "error": {"code": "42501"}})          # o gatilho: o medido não é da conta dela
    assert r["job"] == "velho" and "não é da sua conta" in r["avisos"][0][0]
    r = _ligar({"data": [{"id": "p1"}], "error": None}, admin="false")
    assert r["gravou"] is None and r["job"] == "velho"              # a equipe nem tenta


def test_o_botao_de_trocar_e_so_da_admin_e_trocar_pede_confirmacao():
    """Guarda de TEXTO, declarado."""
    c = funcao_js("telaCapa", "escritorio.html", E)
    assert "${souAdmin() ? '<p class=\"sub\" style=\"margin:10px 0 0\">Reprocessou este projeto ou ligou o errado? <button type=\"button\" class=\"lnk\" onclick=\"trocarMedido()\">" in c
    assert "Este projeto nasceu sem prancha.${souAdmin() ? ' Já mediu ele no AI.arq? <button type=\"button\" class=\"lnk\" onclick=\"trocarMedido()\">" in c
    assert "use <b>Trazer projeto medido</b> na lista do Escritório" not in c        # criava um SEGUNDO projeto
    t = funcao_js("trocarMedido", "escritorio.html", E)
    assert t.strip().split(NL)[1].strip() == "if (!souAdmin()) return;"
    assert ".eq('user_id', EU.id)" in t                    # a conta de administração do site lê os projetos de todos
    assert "b.onclick = () => (PROJ.job_id ? confirmarTrocaDeMedido(job, nome) : umaVez(b, () => ligarMedido(job)));" in t
    assert "PROJETOS.filter((p) => p.id !== PROJ.id)" in t


# ══ 10. concluir o projeto (ADM-13 — Pedro, 12/10: "Sim, criar") ══
def _andamento(args):
    i = E.index("const LOGO_OK")
    bloco = E[i:E.index("function pillPrazo", i)]
    return _js([_linha(E, "const MODELO_DTZ = "), bloco], "calcAndamento(MODELO_DTZ, " + args + ")")


def test_projeto_concluido_conta_100_e_sem_concluir_a_ultima_etapa_sem_tarefa_fica_em_89():
    a = _andamento("8, {}, 0, 0, null, true")
    assert a["pct"] == 100 and a["concluido"] is True and a["pAntes"] == 100 and a["pAtual"] == 0
    assert _andamento("8, {}, 0, 0, null, false")["pct"] == 89            # o que o Pedro via: 8 de 9
    assert _andamento("8, {}, 0, 0, null")["pct"] == 89                   # controle: sem o argumento, como antes
    assert _andamento("8, { Entrega: 5 }, 1, 4, null, true")["pct"] == 100  # peso e tarefas não mudam o concluído


_CONCLUIR_BASE = """
var ADMIN = true, avisos = [], gravou = null, PERGUNTOU = 0, ACEITA = true;
var PROJ = { id: 'p1', etapas: ['Briefing', 'Obra', 'Entrega'], etapa_atual: 'Entrega', concluido_em: null }, TAR = [];
function souAdmin() { return ADMIN; } function aberta(t) { return t.status !== 'ok'; }
function toast(t, erro) { avisos.push([t, !!erro]); } function falhou(e, t) { avisos.push([t, true]); } function render() {}
function confirm() { PERGUNTOU++; return ACEITA; }
var RESPOSTA = { data: [{ id: 'p1' }], error: null };
var sb = { from: function () { return { update: function (m) { gravou = m; return { eq: function () {
  var r = { error: RESPOSTA.error, select: function () { return RESPOSTA; } }; return r; } }; } }; } };
"""
_CONCLUIR = [_CONCLUIR_BASE, sem_await(funcao_js("concluirProjeto", "escritorio.html", E)),
             sem_await(funcao_js("marcarAtual", "escritorio.html", E))]


def _concluir(cena, acao):
    return _js(_CONCLUIR + [cena, acao], "{ gravou: gravou, concluido: PROJ.concluido_em, etapa: PROJ.etapa_atual,"
                                         "  avisos: avisos, perguntou: PERGUNTOU }")


def test_concluir_o_projeto_na_ultima_etapa_grava_a_data_e_reabrir_limpa():
    r = _concluir("", "concluirProjeto(true);")
    assert list(r["gravou"]) == ["concluido_em"] and r["gravou"]["concluido_em"] and r["concluido"] == r["gravou"]["concluido_em"]
    assert r["avisos"] == [["Projeto concluído: 100%", False]] and r["perguntou"] == 0
    r = _concluir("PROJ.concluido_em = '2026-10-12T12:00:00Z';", "concluirProjeto(false);")
    assert r["gravou"] == {"concluido_em": None} and r["concluido"] is None and r["avisos"][0][0] == "Projeto reaberto"


def test_controles_do_concluir():
    r = _concluir("PROJ.etapa_atual = 'Obra';", "concluirProjeto(true);")          # não é a última etapa
    assert r["gravou"] is None and r["concluido"] is None and r["avisos"][0][1] is True
    r = _concluir("ADMIN = false;", "concluirProjeto(true);")                      # a equipe não conclui
    assert r["gravou"] is None and r["concluido"] is None
    r = _concluir("RESPOSTA = { data: [], error: null };", "concluirProjeto(true);")   # a RLS filtrou calada
    assert r["concluido"] is None and r["avisos"][0][1] is True
    cena = "TAR = [{ etapa: 'Entrega', status: 'dev' }]; ACEITA = false;"          # tarefa aberta: pergunta; "não" = nada
    r = _concluir(cena, "concluirProjeto(true);")
    assert r["perguntou"] == 1 and r["gravou"] is None
    r = _concluir(cena + " ACEITA = true;", "concluirProjeto(true);")
    assert r["perguntou"] == 1 and r["concluido"]


def test_mudar_a_etapa_atual_reabre_o_projeto_concluido():
    r = _concluir("PROJ.concluido_em = '2026-10-12T12:00:00Z';", "marcarAtual(1);")
    assert r["gravou"] == {"etapa_atual": "Obra", "concluido_em": None} and r["concluido"] is None and r["etapa"] == "Obra"
    assert "projeto reaberto" in r["avisos"][0][0]
    r = _concluir("", "marcarAtual(1);")                                           # controle: sem concluir, só a etapa
    assert r["gravou"] == {"etapa_atual": "Obra"} and "reaberto" not in r["avisos"][0][0]


def test_o_cliente_recebe_so_a_data_e_a_admin_ve_o_botao():
    """Guarda de TEXTO, declarado."""
    a = funcao_js("andamentoAtual", "escritorio.html", E)
    assert "const concluido = souEquipe() ? !!p.concluido_em : !!CONCL_EXT;" in a
    assert "OBRA.projeto === p.id ? OBRA.pct : null, concluido);" in a
    c = funcao_js("carregarProjeto", "escritorio.html", E)
    assert "papel.data === 'cliente' ? await sb.rpc('escritorio_projeto_concluido', { p_projeto: id }) : null" in c
    assert "CONCL_EXT = ce && !ce.error && typeof ce.data === 'string' ? ce.data : null;" in c
    v = funcao_js("avancoEtapa", "escritorio.html", E)
    assert "onclick=\"concluirProjeto(true)\">Concluir ${esc(atual)} e o projeto ✓</button>" in v
    assert "onclick=\"concluirProjeto(false)\">Reabrir</button>" in v
    assert v.index("if (!souAdmin()) return") < v.index("concluirProjeto(true)")      # o botão vem depois da porta da admin
    assert "pct = p.concluido_em ? 100 : et.length && i >= 0 ?" in funcao_js("telaLista", "escritorio.html", E)


# ══ 11. grupo A dos achados pequenos (12/10): dado que se perdia e gravação que mentia ══
def test_gravacao_que_o_banco_filtrou_nao_vira_movido():
    """BANCO-5: quem perdeu o acesso ao cartão com ele aberto lia "Movido" — o banco devolve 0 linha, sem erro."""
    r = _mover("dev", False, "afazer", conta=0)
    assert r["gravado"][0]["contou"] is True                       # a gravação pede a contagem
    assert r["cartao"]["status"] == "dev"                          # o cartão volta pro lugar
    assert r["avisos"] == ["Não gravei: este cartão foi excluído ou você não tem mais acesso a ele. Atualizei a tela."]
    assert r["releu"] == 1
    r = _mover("dev", False, "afazer")                             # controle: gravou 1 linha
    assert r["cartao"]["status"] == "afazer" and r["avisos"] == ["Movido para afazer"] and r["releu"] == 0


def test_salvar_o_cartao_tambem_confere_a_contagem():
    """BANCO-5. Guarda de TEXTO, declarado."""
    g = funcao_js("gravarCartao", "escritorio.html", E)
    assert ".update(mud, { count: 'exact' }).eq('id', id);" in g
    assert g.index("if (!count) { fecharModal(); return semAcessoAoCartao(); }") < g.index("escritorio_tarefa_pessoas")
    assert ".update({ status: st, posicao: pos }, { count: 'exact' })" in funcao_js("salvarColuna", "escritorio.html", E)


def test_uma_gravacao_por_vez():
    """ADM-8: enquanto a 1ª não voltou, a 2ª (Enter repetido, clique duplo) não faz nada."""
    real = funcao_js("umaGravacao", "escritorio.html", E)
    r = _js(["var GRAVANDO = {}, n = 0;", real,
             "umaGravacao('x', function () { n++; return new Promise(function () {}); });"      # a 1ª fica pendurada
             "umaGravacao('x', function () { n += 10; });"                                      # a 2ª do MESMO tipo: nada
             "umaGravacao('y', function () { n += 100; });"],                                   # outro tipo: passa
            "[n, !!GRAVANDO.x]")
    assert r == [101, True]
    solta = sem_await(real)                                         # sem o adiamento: uma depois da outra, as duas gravam
    assert _js(["var GRAVANDO = {}, n = 0;", solta, "umaGravacao('x', function () { n++; }); umaGravacao('x', function () { n++; });"],
               "[n, Object.keys(GRAVANDO).length]") == [2, 0]
    assert _js(["var GRAVANDO = {};", solta, "try { umaGravacao('x', function () { throw new Error('caiu'); }); } catch (e) {}"],
               "Object.keys(GRAVANDO).length") == 0                 # erro não deixa a trava presa


def test_quem_grava_passa_pela_trava():
    """ADM-8. Guarda de TEXTO, declarado: cartão, item do checklist, comentário, cancelar convite e virar tarefa."""
    for fn, chave in (("criarCartao", "'cartao:' + st + ':' + txt"), ("addChk", "'chk:' + tid + ':' + txt"),
                      ("comentar", "'comentario:' + id + ':' + txt"), ("confirmarTirar", "'tirar:' + id"),
                      ("virarTarefa", "'virar:' + evId")):
        corpo = funcao_js(fn, "escritorio.html", E)
        assert ("return umaGravacao(%s, async () => {" % chave) in corpo, fn
        assert corpo.index("umaGravacao(") < corpo.index("sb.from("), fn        # a trava vem ANTES de gravar


def test_a_trava_e_da_gravacao_igual_nao_do_tipo():
    """Revisão do próprio conserto (12/10): com uma chave só por tipo, o cartão digitado noutra coluna enquanto o 1º
    ainda gravava sumia calado — e tirar duas pessoas em seguida parava na segunda (a 1ª esperando o Drive)."""
    pendurado = ("sb = { from: function (t) { return { insert: function (o) { gravado.push(o.status + '/' + o.titulo);"
                 "  return { select: function () { return { single: function () { return new Promise(function () {}); } }; } }; } }; } };")
    cena = ("var TAR = []; CLIENTES = 0; povoar();"
            "criarCartao('afazer', 'Planta'); criarCartao('afazer', 'Planta'); criarCartao('afazer', ' Planta ');"    # o Enter repetido
            "criarCartao('afazer', 'Corte'); criarCartao('dev', 'Planta');")                                           # outra gravação
    r = _js([_QUADRO_BASE, _linha(E, "const clientesAtivos = "), funcao_js("umaGravacao", "escritorio.html", E),
             funcao_js("criarCartao", "escritorio.html", E), pendurado, cena], "gravado")
    assert r == ["afazer/Planta", "afazer/Corte", "dev/Planta"]


def _rascunho(extra=""):
    pre = ("var campos = { 'ct-t': { value: 'Título digitado' }, 'ct-e': { value: 'Obra' }, 'ct-p': { value: '2026-11-01' },"
           "  'ct-d': { value: 'Três parágrafos' }, 'ct-cli': { checked: true }, 'ct-st': { value: 'dev' }, 'ct-com': { value: '@Fulana confere' } };"
           "function $(id) { return campos[id] || null; }"
           "var TAR = [{ id: 't1', status: 'afazer' }], CART = { id: 't1', pessoas: ['m1', 'm2'] }, abriu = [];"
           "function abrirCartao(id, r) { abriu.push([id, r]); }")
    fns = [funcao_js(n, "escritorio.html", E) for n in ("rascunhoDoCartao", "sairDoCartao", "voltarAoCartao")]
    return [pre, "var RASC = null;"] + fns + [extra]


def test_o_que_estava_digitado_no_cartao_volta():
    """ADM-6: subir/descer, editar ou apagar comentário e "Excluir → Voltar" reabriam o cartão do banco."""
    r = _js(_rascunho(), "rascunhoDoCartao('t1')")
    assert r == {"mud": {"titulo": "Título digitado", "etapa": "Obra", "prazo": "2026-11-01", "descricao": "Três parágrafos",
                         "do_cliente": True}, "st": "dev", "pessoas": ["m1", "m2"], "comentario": "@Fulana confere"}
    r = _js(_rascunho("sairDoCartao('t1'); campos = {}; voltarAoCartao('t1'); voltarAoCartao('t1');"), "abriu")
    assert r[0][0] == "t1" and r[0][1]["mud"]["descricao"] == "Três parágrafos"      # volta com o digitado
    assert r[1] == ["t1", None]                                                      # e só uma vez: depois é o do banco
    r = _js(_rascunho("TAR.push({ id: 't2', status: 'afazer' }); sairDoCartao('t1'); voltarAoCartao('t2');"), "abriu")
    assert r == [["t2", None]]                                                       # o digitado num cartão não vaza pra outro
    assert _js(_rascunho("CART = { id: 'outro', pessoas: [] };"), "rascunhoDoCartao('t1')") is None
    assert _js(_rascunho("delete campos['ct-t'];"), "rascunhoDoCartao('t1')") is None    # o cartão do fornecedor não tem título


def test_os_caminhos_de_volta_do_cartao_usam_o_rascunho():
    """ADM-6. Guarda de TEXTO, declarado."""
    for fn in ("editarComentario", "apagarComentario", "apagarCartao"):
        corpo = funcao_js(fn, "escritorio.html", E)
        assert corpo.index("sairDoCartao(") < corpo.index("abrirModal("), fn
        assert "onclick=\"voltarAoCartao('${" in corpo and "onclick=\"abrirCartao('${" not in corpo, fn
    s = funcao_js("subirDescer", "escritorio.html", E)
    assert "const digitado = rascunhoDoCartao(id);" in s and "abrirCartao(id, digitado);" in s
    a = funcao_js("abrirCartao", "escritorio.html", E)
    assert "if (rascunho && rascunho.comentario && $('ct-com')) $('ct-com').value = rascunho.comentario;" in a


def _pedido(tarefas):
    pre = ("var EMI = [{ id: 'e1', copia_nome: 'Planta_R01.pdf', arquivo_nome: 'Planta.pdf' }];"
           "var TAR = " + json.dumps(tarefas) + ";")
    x = {"emissao_id": "e1", "nota": "falta a tomada da ilha", "criado_em": "2026-10-10T12:00:00+00:00"}
    return _js([pre, _linha(E, "const tituloDaRevisao = "), funcao_js("tarefaDoPedido", "escritorio.html", E)],
               "(tarefaDoPedido(" + json.dumps(x) + ") || {}).id || null")


def test_pedido_de_revisao_que_ja_virou_tarefa_nao_vira_de_novo():
    """ADM-9: o link "virar tarefa" seguia lá depois de usado e cada clique criava mais um cartão igual."""
    titulo = "Revisão pedida pelo cliente: Planta_R01.pdf"
    feito = {"id": "t9", "titulo": titulo, "descricao": "falta a tomada da ilha", "criado_em": "2026-10-10T12:05:00+00:00"}
    assert _pedido([feito]) == "t9"
    assert _pedido([]) is None
    assert _pedido([{**feito, "descricao": "outro pedido"}]) is None            # outro texto: outro pedido
    assert _pedido([{**feito, "criado_em": "2026-10-09T08:00:00+00:00"}]) is None   # cartão de ANTES deste pedido (o da vez passada)
    v = funcao_js("virarTarefa", "escritorio.html", E)
    assert v.index("if (tarefaDoPedido(x)) return toast(") < v.index("umaGravacao('virar:' + evId")
    assert "tarefaDoPedido(x) ? ' · <span class=\"sub\" style=\"margin:0\">já virou tarefa</span>'" in E


_PESSOA_BASE = """
var gravado = [], avisos = [], fechou = 0;
var campos = { 'pe-n': { value: 'Fulana' }, 'pe-f': { value: 'Arquiteta' }, 'pe-t': { value: '' }, 'pe-o': { value: '' } };
function $(id) { return campos[id] || null; }
var PROJ = { id: 'p1' }, MEMBROS = [{ id: 'm1' }];
function falhou(e, t) { avisos.push(t); } function toast(t) { avisos.push(t); } function fecharModal() { fechou++; } function recarregar() {}
var sb = { from: function (t) { return {
  update: function (m) { gravado.push([t, 'update', m]); return { eq: function () { return { error: null }; } }; },
  upsert: function (m) { gravado.push([t, 'upsert', m]); return { error: null }; },
  delete: function () { return { eq: function () { gravado.push([t, 'delete']); return { error: null }; } }; } }; } };
"""


def _salvar_pessoa(contatos, notas):
    return _js([_PESSOA_BASE, "var CONTATOS_LIDOS = %s, NOTAS_LIDAS = %s, PASTA_DE_HOJE = '__a_de_hoje__';" % (contatos, notas),
                sem_await(funcao_js("salvarPessoa", "escritorio.html", E)), "salvarPessoa('m1');"], "gravado")


def test_o_que_a_tela_nao_leu_nao_e_gravado():
    """ADM-7: a leitura de contatos falhava calada e salvar o "Editar" gravava telefone nulo e APAGAVA a anotação."""
    assert _salvar_pessoa("false", "false") == [["escritorio_membros", "update", {"nome": "Fulana", "funcao": "Arquiteta"}]]
    r = _salvar_pessoa("true", "true")                                   # controle: leu tudo — o vazio É vontade da admin
    assert r == [["escritorio_membros", "update", {"nome": "Fulana", "funcao": "Arquiteta", "telefone": None}],
                 ["escritorio_membro_notas", "delete"]]
    assert _salvar_pessoa("false", "true")[1] == ["escritorio_membro_notas", "delete"]
    assert _salvar_pessoa("true", "false") == [["escritorio_membros", "update", {"nome": "Fulana", "funcao": "Arquiteta", "telefone": None}]]
    c = funcao_js("carregarProjeto", "escritorio.html", E)
    assert "else contatosLidos = false;" in c and "else notasLidas = false;" in c
    assert "CONTATOS_LIDOS = contatosLidos; NOTAS_LIDAS = notasLidas;" in c
    ed = funcao_js("editarPessoa", "escritorio.html", E)
    assert "${CONTATOS_LIDOS ? '' : ' disabled'}" in ed and "${NOTAS_LIDAS ? '' : ' disabled placeholder=" in ed


def _sincronizar(dados):
    pre = ("var avisos = [], releu = 0, SINC_EM_CURSO = false, PROJ = { id: 'p1' };"
           "function toast(t, erro) { avisos.push([t, !!erro]); } function recarregar() { releu++; }"
           "function apiEsc() { return { ok: true, dados: " + json.dumps(dados) + " }; }")
    return _js([pre, sem_await(funcao_js("sincronizarPasta", "escritorio.html", E)), "sincronizarPasta();"], "{ avisos: avisos, releu: releu }")


def test_atualizar_acesso_avisa_quando_o_fornecedor_fica_sem_pasta_e_rele_a_equipe():
    """ADM-10: a tela dizia só "1 saiu" e a Equipe seguia mostrando "vê a pasta X"."""
    r = _sincronizar({"compartilhados": 0, "tirados": 1, "fornecedor_sem_pasta": ["m1"]})
    assert r["releu"] == 1 and r["avisos"][0][1] is True and "1 fornecedor ficou sem pasta" in r["avisos"][0][0]
    r = _sincronizar({"compartilhados": 2, "tirados": 0})                 # controle: ninguém perdeu a pasta
    assert r["releu"] == 1 and r["avisos"] == [["Acesso atualizado: 2 entrou, 0 saiu", False]]


def test_o_sair_do_portal_limpa_o_cadastro_completo_e_o_convite():
    """FORA-4: a próxima conta no mesmo navegador entrava no painel sem ficha, sem Termos e sem declarar 18 anos."""
    pre = ("var apagou = [], limpou = 0, saiu = 0;"
           "var localStorage = { removeItem: function (k) { apagou.push(k); } }, sessionStorage = { removeItem: function (k) { apagou.push(k); } };"
           "var window = { aiarqConvite: { limpar: function () { limpou++; } } }, location = { href: '' };"
           "var sb = { auth: { signOut: function () { saiu++; return { finally: function (f) { f(); } }; } } };")
    r = _js([pre, funcao_js("sairDaConta", "escritorio.html", E), "sairDaConta();"],
            "{ apagou: apagou, limpou: limpou, saiu: saiu, foi: location.href }")
    assert "aiarq_profile_complete" in r["apagou"] and r["limpou"] == 1
    assert {"aiarq_esc_mapa", "aiarq_esc_ctx", "aiarq_escritorio_levou"} <= set(r["apagou"])      # o que já limpava
    assert r["saiu"] == 1 and r["foi"] == "login.html"
    # controle: é o mesmo que o Sair das outras páginas limpa
    assert "localStorage.removeItem('aiarq_profile_complete')" in ML and "window.aiarqConvite.limpar()" in ML


# (13/10) o teste de texto do SERV-3 na tela virou teste de comportamento: está na seção 12, com o resumo do envio


# ══ 12. grupo B dos achados pequenos (13/10): a tela que dizia o que não sabia ══
_ESC = 'function esc(s) { return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }'


def _trecho(src, comeco, fim):
    """De uma declaração que começa a linha com `comeco` até o primeiro `fim` depois dela (inclusive)."""
    i = src.index(NL + comeco) + 1
    return src[i:src.index(fim, i) + len(fim)]


def _resumo(d):
    return _js([funcao_js("resumoDoEnvio", "escritorio.html", E)], "resumoDoEnvio(" + json.dumps(d) + ")")


def test_o_resumo_do_envio_diz_o_que_mandou_o_que_nao_deu_e_o_que_nao_registrou():
    assert _resumo({"mandados": 0, "falhas": []}) == ""
    assert _resumo({"mandados": 2, "falhas": []}) == " · mandado pra 2 pessoas"
    assert _resumo({"mandados": 1, "falhas": ["m9"]}) == " · mandado pra 1 pessoa · 1 não deu: mande de novo em Emissões"
    # SERV-3: o motivo que o servidor mandou vale mais que o texto genérico
    motivo = "A cópia foi feita no Drive, mas não consegui registrar. Não mandei pra ninguém: emita de novo."
    assert _resumo({"mandados": 0, "falhas": ["banco"], "erro": motivo}) == " · " + motivo
    # FORA-6: recebeu, mas o registro "Enviada ao cliente" não gravou
    assert 'não consegui registrar "Enviada ao cliente"' in _resumo({"mandados": 1, "falhas": [], "enviado_registrado": False})
    for registrou in (True, None):                                   # controle: gravou, ou não foi pra cliente nenhum
        assert "registrar" not in _resumo({"mandados": 1, "falhas": [], "enviado_registrado": registrou})


def _emite(dados):
    pre = ("var modais = [], avisos = [], EMITINDO = false, PROJ = { id: 'p1' }, botao = { disabled: false, textContent: '' };"
           "function $(id) { return id === 'em-ok' ? botao : null; }"
           "function paraMarcados() { return []; } function fecharModal() {} function recarregar() {}"
           "function abrirModal(t, h) { modais.push([t, h]); } function toast(t, e) { avisos.push([t, !!e]); }"
           + _ESC + "function apiEsc() { return { ok: true, status: 200, dados: " + json.dumps(dados) + " }; }")
    return _js([pre, funcao_js("resumoDoEnvio", "escritorio.html", E), sem_await(funcao_js("confirmarEmissao", "escritorio.html", E)),
                "confirmarEmissao('ARQ');"], "{ modais: modais, avisos: avisos }")


def test_emitido_sem_trava_tambem_diz_o_que_houve_com_o_envio():
    """ADM-11: com a trava E o envio falhando juntos, o aviso "sem trava" não dizia que 1 cliente não tinha recebido."""
    r = _emite({"nome": "Planta_R02.pdf", "travada": False, "mandados": 1, "falhas": ["m2"]})
    (titulo, html), = r["modais"]
    assert titulo == "Emitido, mas sem trava" and "<b>O envio:</b> mandado pra 1 pessoa · 1 não deu: mande de novo em Emissões." in html
    assert "color:#B91C1C" in html and r["avisos"] == []
    r = _emite({"nome": "Planta_R02.pdf", "travada": False, "mandados": 0, "falhas": []})      # controle: não mandou nada
    assert "O envio:" not in r["modais"][0][1]
    r = _emite({"nome": "Planta_R02.pdf", "travada": False, "mandados": 2, "falhas": []})      # deu certo: diz, sem vermelho
    assert "<b>O envio:</b> mandado pra 2 pessoas." in r["modais"][0][1] and "#B91C1C" not in r["modais"][0][1]


def test_emitir_diz_quando_nao_mandou_por_falta_do_registro_da_copia():
    """SERV-3 (a metade da tela) e FORA-6: o aviso sai em vermelho quando algo do envio não deu."""
    motivo = "A cópia foi feita no Drive, mas não consegui registrar. Não mandei pra ninguém: emita de novo."
    r = _emite({"nome": "Planta_R02.pdf", "travada": True, "mandados": 0, "falhas": ["banco"], "erro": motivo})
    assert r["avisos"] == [["Emitido: Planta_R02.pdf · " + motivo, True]] and r["modais"] == []
    r = _emite({"nome": "Planta_R02.pdf", "travada": True, "mandados": 1, "falhas": [], "enviado_registrado": False})
    assert r["avisos"][0][1] is True and "Registrar retorno" in r["avisos"][0][0]
    r = _emite({"nome": "Planta_R02.pdf", "travada": True, "mandados": 1, "falhas": [], "enviado_registrado": True})
    assert r["avisos"] == [["Emitido: Planta_R02.pdf · mandado pra 1 pessoa", False]]          # controle


def _espera(ev, dest, expr, cliente=True, emitido="2026-09-30T12:00:00+00:00"):
    i = E.index(NL + "const evDa = ") + 1
    bloco = E[i:E.index(NL + "const quemRespondeu", i)]
    assert "const esperaResposta = (e) => {" in bloco and "const enviadaPraMimEm = (e) => {" in bloco
    pre = ("var EU = { id: 'u-eu' }, MEMBROS = [];"
           "var EMI = [{ id: 'e0', arquivo_id: 'A', revisao: 0, emitido_em: " + json.dumps(emitido) + " }];"
           "var EMI_EV = " + json.dumps(ev) + "; var DEST = " + json.dumps(dest) + ";"
           "function souCliente() { return " + ("true" if cliente else "false") + "; }"
           "function meuMembro() { return { id: 'm-eu' }; } function deFora() { return true; }")
    return _js([pre, bloco], expr)


def test_emissao_mandada_pro_cliente_sem_registro_nenhum_tambem_espera_por_ele():
    """FORA-6: o registro "enviado" não gravou (soluço do banco no envio) — o cliente recebia "Pra você aprovar" e não
    achava os botões."""
    minha = [{"emissao_id": "e0", "membro_id": "m-eu", "permission_id": "p0"}]
    assert _espera([], minha, "esperaResposta(EMI[0])") is True
    assert _espera([], [], "esperaResposta(EMI[0])") is False                                    # não foi mandada pra ele
    assert _espera([], [{"emissao_id": "e0", "membro_id": "m-eu", "permission_id": None}], "esperaResposta(EMI[0])") is False
    assert _espera([], [{"emissao_id": "e0", "membro_id": "m-outro", "permission_id": "p9"}], "esperaResposta(EMI[0])") is False
    assert _espera([], minha, "esperaResposta(EMI[0])", cliente=False) is False                  # o escritório: só com o "enviado"
    respondi = [{"emissao_id": "e0", "tipo": "aprovado", "pelo_cliente": True, "registrado_por": "u-eu"}]
    assert _espera(respondi, minha, "esperaResposta(EMI[0])") is False                           # já respondeu: não espera mais
    a_mao = [{"emissao_id": "e0", "tipo": "aprovado", "pelo_cliente": False, "registrado_por": "u-admin"}]
    assert _espera(a_mao, minha, "esperaResposta(EMI[0])") is False                              # o escritório registrou à mão: fechada


def test_enviada_em_e_a_data_em_que_esta_pessoa_recebeu():
    """FORA-7: o cartão mostrava a data do último registro de qualquer um — até a resposta do outro cliente do casal."""
    ev = [{"emissao_id": "e0", "tipo": "enviado", "em": "2026-10-01"},
          {"emissao_id": "e0", "tipo": "aprovado", "em": "2026-10-05", "pelo_cliente": True, "registrado_por": "u-outra"}]
    minha = {"emissao_id": "e0", "membro_id": "m-eu", "permission_id": "p0", "enviado_em": "2026-10-08T15:00:00+00:00"}
    dela = {"emissao_id": "e0", "membro_id": "m-outra", "permission_id": "p1", "enviado_em": "2026-10-01T12:00:00+00:00"}
    assert _espera(ev, [dela, minha], "enviadaPraMimEm(EMI[0])") == "2026-10-08T15:00:00+00:00"
    assert _espera(ev, [dela, {**minha, "enviado_em": None}], "enviadaPraMimEm(EMI[0])") == "2026-10-01"    # o "enviado", não a resposta dela
    assert _espera(ev[1:], [dela], "enviadaPraMimEm(EMI[0])") == "2026-09-30T12:00:00+00:00"                # sem nada: a emissão
    assert "Enviada em ${esc(dBR(enviadaPraMimEm(e)))}" in E and "Enviada em ${esc(dBR((ultimoEv(e) || {}).em" not in E


def test_mandar_avisa_a_admin_quando_o_enviado_nao_foi_registrado():
    """FORA-6 (o "Mandar pra…"). Guarda de TEXTO, declarado."""
    m = funcao_js("mandarDepois", "escritorio.html", E)
    assert "const semRegistro = r.dados.enviado_registrado === false;" in m
    assert "registre em Registrar retorno' : ''), !!f || semRegistro);" in m


def _lista(piloto_lido, resumo_lido, projetos, no_piloto="false"):
    pre = ("var NO_PILOTO = %s, PILOTO_LIDO = %s, RESUMO_LIDO = %s, EU = { id: 'u1' };" % (no_piloto, piloto_lido, resumo_lido)
           + "var PROJETOS = " + json.dumps(projetos) + ";"
           + _ESC + "function faixa(i, t, s, botoes) { return '[FAIXA ' + (botoes || 'sem botoes') + ']'; }"
           "function corDe() { return ['#111111', '#222222']; } function iniciais() { return 'CE'; }")
    return _js([pre, _trecho(E, "const naoLiNaLista = ", NL + "].filter(Boolean);"), _trecho(E, "const oQueALista = () => {", NL + "};"),
                funcao_js("telaLista", "escritorio.html", E)], "telaLista()")


def test_lista_nao_chama_de_piloto_fechado_o_que_nao_conseguiu_ler():
    """ADM-17: num soluço do banco, a admin do piloto lia "O Escritório está em piloto fechado"."""
    assert "piloto fechado" in _lista("true", "true", [])                                        # controle: leu e não é do piloto
    for piloto, resumo in (("false", "true"), ("true", "false"), ("false", "false")):
        t = _lista(piloto, resumo, [])
        assert "Não consegui carregar agora" in t and "piloto fechado" not in t, (piloto, resumo)


def test_lista_com_projetos_diz_o_que_nao_leu():
    """ADM-17: os botões de criar sumiam sem aviso, e os projetos de fora sumiam da lista."""
    casa = [{"id": "p1", "nome": "Casa Exemplo", "etapas": [], "dono": "u1"}]
    t = _lista("false", "true", casa)
    assert "<b>Não consegui ler agora:</b> se esta conta cria projetos" in t and "cliente ou fornecedor" not in t
    t = _lista("true", "false", casa, no_piloto="true")
    assert "os projetos em que você entrou como cliente ou fornecedor" in t and "se esta conta cria" not in t
    assert "Trazer projeto medido" in t                                                          # os botões da admin seguem lá
    assert "Não consegui ler agora" not in _lista("true", "true", casa, no_piloto="true")        # controle
    c = funcao_js("carregarProjetos", "escritorio.html", E)
    assert "PILOTO_LIDO = !pil.error; RESUMO_LIDO = !fora.error;" in c


_NAV_BASE = """
var NAV_PEDIDO = 0, VIEW = 'lista', PROJ = null, MEMBROS = [], NO_PILOTO = true, pintou = [], leu = [], valeu = [];
var PROJETOS = [{ id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa' }, { id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb' }];
var A = PROJETOS[0].id, B = PROJETOS[1].id, ROTA = { id: A, view: 'tarefas' }, NO_MEIO = null;
var location = { hash: '', replace: function (u) { location.hash = u; } }, main = { innerHTML: '' };
function $(id) { return main; } function menu() {} function lerRota() { return ROTA; }
function souEquipe() { return true; } function souFornecedor() { return false; }
var NO_MEIO_DA_LISTA = null, ESTOURA = false, console = { error: function () {} };
function carregarProjetos() { if (NO_MEIO_DA_LISTA) { var f = NO_MEIO_DA_LISTA; NO_MEIO_DA_LISTA = null; f(); } }
function abrirPeloJob() {}
function render() { pintou.push(VIEW + ':' + (PROJ ? PROJ.id.slice(0, 1) : '-')); }
function carregarProjeto(id, vale) {
  leu.push(id.slice(0, 1));
  if (NO_MEIO) { var f = NO_MEIO; NO_MEIO = null; f(); }      // a pessoa faz outra coisa ENQUANTO este projeto carrega
  if (ESTOURA === id.slice(0, 1)) { ESTOURA = false; throw new Error('o banco caiu no meio'); }   // só a leitura DESTE projeto
  valeu.push(vale ? vale() : null);
  if (vale && !vale()) return false;                          // o mesmo contrato da de verdade: atrasada não troca nada
  PROJ = { id: id }; MEMBROS = [{}];
  return true;
}
"""


def _navega(cena):
    return _js([_NAV_BASE, sem_await(funcao_js("navegar", "escritorio.html", E)), sem_await(funcao_js("recarregar", "escritorio.html", E)),
                cena], "{ pintou: pintou, leu: leu, valeu: valeu, view: VIEW, proj: PROJ && PROJ.id.slice(0, 1), hash: location.hash,"
                       "  erro: main.innerHTML }")


def test_resposta_atrasada_do_projeto_anterior_nao_pinta_por_cima_do_novo():
    """ADM-18: clicou no A e, antes de ele carregar, no B — a resposta do A chegava por último e a tela ficava no A
    com o endereço do B."""
    r = _navega("NO_MEIO = function () { ROTA = { id: B, view: 'equipe' }; navegar(); }; navegar();")
    assert r["leu"] == ["a", "b"] and r["valeu"] == [True, False]        # a leitura do A soube que não era mais a da vez
    assert r["pintou"] == ["equipe:b"] and r["view"] == "equipe" and r["proj"] == "b" and r["hash"] == ""
    r = _navega("navegar();")                                            # controle: sem ninguém no meio, o A abre
    assert r["pintou"] == ["tarefas:a"] and r["valeu"] == [True]


def test_ir_pra_lista_enquanto_o_projeto_carrega_nao_volta_pro_projeto():
    r = _navega("NO_MEIO = function () { ROTA = { id: null, view: 'lista' }; navegar(); }; navegar();")
    assert r["pintou"] == ["lista:-"] and r["proj"] is None and r["view"] == "lista"


def test_abrir_um_projeto_enquanto_a_lista_carrega_nao_pinta_duas_vezes():
    """ADM-18, o caminho da lista: a lista atrasada pintava de novo por cima do projeto que a pessoa acabou de abrir."""
    r = _navega("ROTA = { id: null, view: 'lista' };"
                "NO_MEIO_DA_LISTA = function () { ROTA = { id: A, view: 'tarefas' }; navegar(); }; navegar();")
    assert r["pintou"] == ["tarefas:a"] and r["proj"] == "a" and r["view"] == "tarefas"
    r = _navega("ROTA = { id: null, view: 'lista' }; navegar();")        # controle: a lista sozinha pinta a lista
    assert r["pintou"] == ["lista:-"]


def test_navegacao_deixada_pra_tras_nao_le_o_projeto_nem_pinta_o_erro_dela():
    # a lista dos projetos ainda carregava quando a pessoa foi pra lista: o projeto A nem chega a ser lido
    r = _navega("PROJETOS.length = 0; NO_MEIO_DA_LISTA = function () { ROTA = { id: null, view: 'lista' }; navegar(); }; navegar();")
    assert r["leu"] == [] and r["pintou"] == ["lista:-"]
    # a leitura do A estourou DEPOIS de a pessoa ir pro B: o "Não consegui carregar" do A não cobre o B
    r = _navega("ESTOURA = 'a'; NO_MEIO = function () { ROTA = { id: B, view: 'capa' }; navegar(); }; navegar();")
    assert r["erro"] == "" and r["pintou"] == ["capa:b"]
    r = _navega("ESTOURA = 'a'; navegar();")                             # controle: o erro da navegação da vez aparece
    assert "Não consegui carregar agora" in r["erro"] and r["pintou"] == []


def test_reler_o_projeto_nao_pinta_depois_que_a_pessoa_foi_pra_outro():
    """ADM-18, o outro caminho: o reler que vem depois de toda gravação."""
    r = _navega("navegar(); pintou = []; NO_MEIO = function () { ROTA = { id: B, view: 'capa' }; }; recarregar();")
    assert r["pintou"] == [] and r["valeu"][-1] is False
    r = _navega("navegar(); pintou = []; NO_MEIO = function () { ROTA = { id: A, view: 'arquivos' }; }; recarregar();")
    assert r["pintou"] == ["tarefas:a"] and r["valeu"][-1] is True        # controle: trocar de TELA no mesmo projeto não descarta
    r = _navega("navegar(); pintou = []; recarregar();")
    assert r["pintou"] == ["tarefas:a"]


def test_a_troca_do_projeto_pergunta_se_ainda_vale_depois_de_ler_tudo():
    """ADM-18. Guarda de TEXTO, declarado: a pergunta vem depois da ÚLTIMA ida ao banco e antes da troca."""
    c = funcao_js("carregarProjeto", "escritorio.html", E)
    pergunta = c.index("if (aindaVale && !aindaVale()) return false;")
    assert c.rindex("await ") < pergunta < c.index("PROJ = proj; MEMBROS = membros;")
    assert pergunta < c.index("ARQ_PASTA = ''; ARQ_TRILHA = [];")        # nem os filtros do projeto que está na tela são zerados


def _cria(admin, equipe):
    pre = ("var ST_EQUIPE = ['afazer', 'dev', 'revdtz'];"
           "function souAdmin() { return %s; } function souEquipe() { return %s; }" % (admin, equipe))
    return _js([pre, _linha(E, "const criaNaColuna = ")],
               "['afazer', 'dev', 'revdtz', 'revsol', 'cliente', 'aprov', 'ok'].filter(criaNaColuna)")


def test_o_botao_de_adicionar_cartao_so_aparece_onde_a_pessoa_cria():
    """ADM-15: a equipe via "+ Adicionar cartão" nas 7 colunas e, em 4 delas, o clique só dava erro."""
    assert _cria("true", "true") == ["afazer", "dev", "revdtz", "revsol", "cliente", "aprov", "ok"]
    assert _cria("false", "true") == ["afazer", "dev", "revdtz"]
    assert _cria("false", "false") == []                                 # o fornecedor não cria em coluna nenhuma
    assert "${criaNaColuna(s.k) ? `<div><button class=\"add\"" in funcao_js("telaTarefas", "escritorio.html", E)
    assert "if (!criaNaColuna(st)) return toast('Nesta coluna quem cria é a admin do projeto.', true);" in funcao_js("addCartao", "escritorio.html", E)


def _fotos(papel, pasta, resposta, acao="subirFotos();"):
    pre = ("var PAPEL = %s, PROJ = { id: 'p1', pasta_id: %s }, modais = [], abriu = 0, perguntou = [];" % (json.dumps(papel), json.dumps(pasta))
           + "function souAdmin() { return PAPEL === 'dono'; } function souEquipe() { return PAPEL === 'dono' || PAPEL === 'freela'; }"
           "function souCliente() { return PAPEL === 'cliente'; }"
           "function abrirModal(t, h) { modais.push([t, h]); } function formularioDeFotos() { abriu++; }"
           + _ESC + "function apiEsc(c) { perguntou.push(c); return " + json.dumps(resposta) + "; }")
    return _js([pre, _linha(E, "const semPastaPraFotos = "), _trecho(E, "const avisoSemPastaPraFotos = ", NL + "  : 'Ainda não dá pra subir fotos: a admin precisa ligar a pasta do Drive a este projeto.');"),
                sem_await(funcao_js("subirFotos", "escritorio.html", E)), funcao_js("naoDaPraSubirFotos", "escritorio.html", E), acao],
               "{ modais: modais, abriu: abriu, perguntou: perguntou, sem: semPastaPraFotos() }")


_PODE = {"ok": True, "status": 200, "dados": {"pode": True}}
_SEM_PASTA = {"ok": True, "status": 200, "dados": {"pode": False, "motivo": "A admin ainda não ligou a pasta do Drive a este projeto."}}


def test_o_fornecedor_fica_sabendo_antes_de_escolher_as_fotos():
    """FORA-9: na obra, no 4G, ele mandava até 40 MB pra só então ler "a admin ainda não ligou a pasta"."""
    r = _fotos("fornecedor", None, _SEM_PASTA)
    assert r["perguntou"] == ["projetos/p1/pode-subir-fotos"] and r["abriu"] == 0
    (titulo, html), = r["modais"]
    assert titulo == "Ainda não dá pra subir fotos" and "A admin ainda não ligou a pasta do Drive" in html and "Nada foi enviado" in html
    r = _fotos("fornecedor", None, _PODE)                                # controle: liberado → o formulário abre
    assert r["abriu"] == 1 and r["modais"] == []
    r = _fotos("fornecedor", None, {"ok": False, "status": 0, "dados": {"detail": "Sem conexão"}})
    assert r["abriu"] == 1 and r["modais"] == []                         # a pergunta sem resposta não tranca: o envio decide
    assert _fotos("cliente", None, _PODE) == {"modais": [], "abriu": 0, "perguntou": [], "sem": False}


def test_equipe_sem_pasta_ligada_nem_pergunta_ao_servidor():
    """ADM-12: a equipe e a admin leem a pasta do projeto — a tela já sabe."""
    r = _fotos("freela", None, _PODE)
    assert r["sem"] is True and r["perguntou"] == [] and r["abriu"] == 0 and "a admin precisa ligar a pasta" in r["modais"][0][1]
    r = _fotos("dono", None, _PODE)
    assert 'href="#/p/p1/arquivos"' in r["modais"][0][1] and r["abriu"] == 0          # pra admin: onde ligar
    r = _fotos("freela", "PASTA_1", _PODE)                                            # controle: com pasta, segue o caminho normal
    assert r["sem"] is False and r["perguntou"] == ["projetos/p1/pode-subir-fotos"] and r["abriu"] == 1
    r = _fotos("freela", "PASTA_1", {"ok": True, "status": 200, "dados": {"pode": False, "motivo": "O Google Drive do projeto está desconectado. Avise a admin."}})
    assert r["abriu"] == 0 and "desconectado" in r["modais"][0][1]                    # o que a tela da equipe não tinha como saber
    assert _fotos("fornecedor", None, _PODE)["sem"] is False                          # o fornecedor não lê a pasta: pergunta


def test_a_tela_de_fotos_troca_o_botao_pelo_aviso_e_o_409_nao_oferece_tentar_de_novo():
    """ADM-12/FORA-9. Guarda de TEXTO, declarado."""
    t = funcao_js("telaFotos", "escritorio.html", E)
    assert "const podeSubir = !souCliente() && !semPastaPraFotos();" in t
    assert "${semPastaPraFotos() ? `<div class=\"aviso\">${avisoSemPastaPraFotos()}</div>` : ''}" in t
    e = funcao_js("enviarFotos", "escritorio.html", E)
    assert e.index("if (r.status === 409) { fecharModal(); return naoDaPraSubirFotos(") < e.index("b.textContent = 'Tentar de novo'")


# ══ 13. grupo C dos achados pequenos (13/10): o que o cliente, o fornecedor e a equipe LEEM ══
CV = _ler("convite.html")
CAD = _ler("cadastro.html")
_CV_BASE = """
var el = {}, foi = { limpou: [], erro: null, desligou: 0, esqueceu: 0 };
function $(id) { return el[id] || (el[id] = { textContent: '', hidden: false, href: '' }); }
var location = { href: '' }, sessionStorage = { removeItem: function () {} };
var window = { aiarqConvite: { limparSe: function (t) { foi.limpou.push(t); }, pendente: function () { return null; } } };
var token = 'tok-1', daAba = 'tok-1', m = null, SESSAO = null;
function desligarConta() { foi.desligou++; } function esquecerAba() { foi.esqueceu++; }
function erro(t, x, tentar) { foi.erro = [t, x, !!tentar]; }
function semCodigo() { foi.semCodigo = true; }
"""
_CV_PERFIL = [_linha(CV, "  let PERFIL = "), _trecho(CV, "  const OQUE_VAI_PRA_CONTA = {", NL + "  };"),
              funcao_js("aplicarPerfil", "convite.html", CV), funcao_js("textoDoVencido", "convite.html", CV)]


def _convite(cena, expr):
    return _js([_CV_BASE] + _CV_PERFIL + [sem_await(funcao_js("agoraNao", "convite.html", CV)), funcao_js("recusado", "convite.html", CV), cena], expr)


def test_convite_vencido_diz_de_quem_e_pra_qual_projeto_e_oferece_a_conta():
    """FORA-8: lia-se só "Peça um novo a quem te convidou", sem o nome de quem nem do projeto (o servidor manda os
    dois), e o único botão levava à página de vendas."""
    r = _convite("recusado({ status: 410, dados: { projeto: 'Casa Exemplo', convidado_por: 'Estúdio Exemplo' } });",
                 "{ erro: foi.erro, botao: [el['btn-site'].textContent, el['btn-site'].href] }")
    assert r["erro"] == ["Este convite venceu", "O convite de Estúdio Exemplo para o projeto Casa Exemplo venceu. Peça um novo a quem te convidou.", False]
    assert r["botao"] == ["Entrar na minha conta", "login.html?redirect=escritorio.html"]
    r = _convite("SESSAO = { user: {} }; recusado({ status: 410, dados: {} });", "{ erro: foi.erro, botao: el['btn-site'].textContent }")
    assert r == {"erro": ["Este convite venceu", "O convite venceu. Peça um novo a quem te convidou.", False], "botao": "Abrir o Escritório"}
    r = _convite("recusado({ status: 410, dados: { detail: 'Este convite venceu em 01/10.' } });", "foi.erro[1]")
    assert r == "Este convite venceu em 01/10."                         # o texto do servidor, quando ele manda, vale
    assert _js(_CV_PERFIL, "textoDoVencido({ projeto: ' Casa Exemplo ' })") == "O convite para o projeto Casa Exemplo venceu. Peça um novo a quem te convidou."
    # controle: link trocado (404, sem conta) continua com o texto dele e sem mexer no botão
    r = _convite("recusado({ status: 404, dados: {} });", "{ erro: foi.erro, botao: (el['btn-site'] || {}).textContent || '' }")
    assert r == {"erro": ["Este link não vale mais", "Peça um novo a quem te convidou.", False], "botao": ""}
    assert "recusado({ status: 410, dados: { projeto: v.dados.projeto, convidado_por: v.dados.convidado_por } })" in CV


def test_agora_nao_de_quem_e_de_fora_nao_manda_pro_painel_do_quantitativo():
    """FORA-8: o dono da obra clicava "Agora não · voltar ao painel" — um painel que nunca foi dele — e caía em
    "envie sua prancha", sem porta pro Escritório e sem volta pro convite."""
    for perfil in ("cliente", "fornecedor"):
        r = _convite("aplicarPerfil('%s'); agoraNao();" % perfil,
                     "{ foi: location.href, erro: foi.erro, limpou: foi.limpou, desligou: foi.desligou, botao: el['btn-agora-nao'].textContent, site: el['btn-site'].hidden }")
        assert r["foi"] == "" and r["erro"][0] == "Tudo bem, fica pra depois" and "abra o link de novo" in r["erro"][1], perfil
        assert r["botao"] == "Agora não · entro depois pelo link do e-mail" and r["site"] is True
        assert r["limpou"] == ["tok-1"] and r["desligou"] == 1          # o que já fazia: o painel não traz mais pra cá
    r = _convite("aplicarPerfil('equipe'); agoraNao();", "{ foi: location.href, erro: foi.erro, botao: el['btn-agora-nao'].textContent }")
    assert r == {"foi": "dashboard.html", "erro": None, "botao": "Agora não · voltar ao painel"}      # controle: a equipe tem painel
    assert _convite("aplicarPerfil('qualquer coisa');", "PERFIL") == "equipe"                          # perfil inventado não vira "de fora"


def test_conta_com_outro_email_nao_ouve_falar_de_pasta_que_o_perfil_nao_ganha():
    """FORA-12: "a pasta de arquivos vai ser compartilhada com esta conta" aparecia pro cliente, que nunca recebe pasta."""
    oque = lambda p: _convite("aplicarPerfil('%s');" % p, "el['p-outra-oque'].textContent")       # noqa: E731
    assert oque("cliente") == "os arquivos que o escritório mandar pra você vão ser compartilhados com"
    assert oque("fornecedor") == "a pasta que o escritório separar pra você vai ser compartilhada com"
    assert oque("equipe") == "a pasta de arquivos vai ser compartilhada com"
    assert 'só lembre que <span id="p-outra-oque">a pasta de arquivos vai ser compartilhada com</span> <b>esta</b> conta.' in CV
    # o perfil chega nos DOIS caminhos (com o código do convite e pelo e-mail da conta)
    assert "aplicarPerfil(perfil);" in funcao_js("iniciar", "convite.html", CV)
    assert "aplicarPerfil(c.perfil);" in funcao_js("escolherConvite", "convite.html", CV)
    assert '<meta name="description" content="Você foi convidado para um projeto no AI.arq.">' in CV


def test_cadastro_curto_de_quem_e_de_fora_nao_vende_o_quantitativo():
    """FORA-11. Guarda de TEXTO, declarado: a caixa do beta some e os textos do WhatsApp falam do projeto."""
    i = CAD.index("if (_convite.perfil === 'cliente' || _convite.perfil === 'fornecedor') {")
    curto = CAD[i:CAD.index("mostrarFormulario(erroDaChecagem", i)]
    assert "_conviteDeFora = true;" in curto
    assert "const beta = document.getElementById('caixa-beta');" in curto and "beta.hidden = true; beta.style.display = 'none';" in curto
    assert "porque.textContent = 'Usamos seu e-mail pra te avisar sobre este projeto, e o WhatsApp se der algum problema." in curto
    assert "planilha" not in curto.split("// 🩸 13/10")[1].split("_conviteDeFora = true;")[1]        # o que ele passa a ler não fala de planilha
    assert '<div id="caixa-beta" class="flex items-start' in CAD and '<p id="whats-porque" class="text-xs' in CAD
    assert "let _conviteDeFora = false;" in CAD
    j = CAD.index("showError(_conviteDeFora")
    assert "se der algum problema.'" in CAD[j:j + 400] and "quando a planilha ficar pronta.');" in CAD[j:j + 520]   # o de sempre continua pros outros


def _perfis(admin):
    return _js(["function souAdmin() { return %s; }" % admin, _trecho(E, "const textoDosPerfis = () => (souAdmin()", NL + "      escolhe: 'a admin escolher', marca: 'a equipe marcar', drive: 'Drive da admin' });")],
               "textoDosPerfis()")


def test_a_equipe_nao_le_que_convida_nem_que_libera():
    """ADM-16: "Quem você convida…", "só quem você liberar abaixo", "o resto do seu Drive" apareciam pra qualquer um da equipe."""
    eq, adm = _perfis("false"), _perfis("true")
    assert "você" not in " ".join(eq.values()) and eq["libera"] == "a admin liberar" and eq["drive"] == "Drive da admin"
    assert adm["titulo"].startswith("Quem você convida") and adm["libera"] == "você liberar abaixo" and adm["drive"] == "seu Drive"
    t = funcao_js("telaEquipe", "escritorio.html", E)
    assert "<b>${quemFala.titulo}</b>" in t and "só quem ${quemFala.libera}." in t and "o resto do ${quemFala.drive}." in t
    assert "você convida" not in t and "você liberar" not in t and "seu Drive" not in t          # nada mais fixo na tela
    assert "souAdmin() ? 'Ligar a pasta do Drive' : 'Pasta do Drive ainda não ligada'" in E


def _conta_google(papel):
    pre = "var PAPEL = %s; function souAdmin() { return PAPEL === 'dono'; } function souFornecedor() { return PAPEL === 'fornecedor'; }" % json.dumps(papel)
    return _js([pre, _trecho(E, "const avisoDaContaGoogle = () => (souAdmin() ? ''", "</p>`);")], "avisoDaContaGoogle()")


def test_o_fornecedor_nao_le_que_pode_editar_os_arquivos():
    """FORA-12: a pasta dele é só pra ler."""
    assert "abrir e editar" not in _conta_google("fornecedor") and "Você só lê" in _conta_google("fornecedor")
    assert "Pra abrir e editar os arquivos" in _conta_google("freela")
    assert _conta_google("dono") == ""


def _lista_diz(projetos):
    return _js(["var PROJETOS = " + json.dumps(projetos) + ";", _trecho(E, "const oQueALista = () => {", NL + "};")], "oQueALista()")


def test_a_lista_de_quem_e_so_de_fora_nao_promete_atas_equipe_nem_pasta():
    """FORA-12: o cliente com dois projetos lia "tarefas, atas, equipe e a pasta do Drive de cada um"."""
    cli, forn, meu = {"externo": True, "papel_externo": "cliente"}, {"externo": True, "papel_externo": "fornecedor"}, {"dono": "u1"}
    assert _lista_diz([cli, cli]) == "as emissões, as pendências e as fotos de cada um"
    assert _lista_diz([forn, forn]) == "as suas tarefas, os arquivos e as fotos de cada um"
    assert _lista_diz([cli, forn]) == "o que o escritório separou pra você em cada um"
    assert _lista_diz([meu, cli]) == "tarefas, atas, equipe e a pasta do Drive de cada um"      # controle: quem tem projeto próprio
    assert "${n} projeto${n > 1 ? 's' : ''}: ${oQueALista()}." in funcao_js("telaLista", "escritorio.html", E)


def test_o_cronograma_do_cliente_nao_promete_o_que_pode_nunca_vir():
    """FORA-13. Guarda de TEXTO, declarado."""
    c = funcao_js("carregarCronogramaCliente", "escritorio.html", E)
    assert "<b>Este projeto ainda não tem cronograma por aqui</b><p>Se o escritório montar o cronograma da obra no AI.arq," in c
    assert "<p>Quando o escritório montar" not in E and "O cronograma ainda não foi montado" not in E     # a promessa saiu da tela
