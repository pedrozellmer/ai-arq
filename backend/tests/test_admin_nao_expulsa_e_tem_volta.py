# -*- coding: utf-8 -*-
"""O painel admin não pode expulsar o dono nem deixá-lo sem volta.

🩸 TRÊS QUEIXAS DO PEDRO EM 01/09/2026, que pareciam três coisas e eram duas:

  (f) "clico num usuário, volto pelo navegador e SAI"
  (g) "abro um projeto e vejo como CLIENTE, sem botão pra voltar pro admin"
  (e) "na aba Projetos não abro do mesmo jeito que pela página do cliente"

CAUSA 1 — O PORTÃO TRATAVA "NÃO CONSEGUI CONFERIR" COMO "REPROVADO".
`checkAdminAccess()` mandava pra `login.html` dentro do `catch`: qualquer
exceção — inclusive uma falha de rede de um segundo, comum logo depois de um
"voltar" — virava logout. É a mesma família do [[feedback_escrita_que_falha_calada]]
que mordeu o motor o dia inteiro: silêncio e falha tratados como resposta.

CAUSA 2 — A ABA NÃO EXISTIA NA URL.
`switchTab` trocava a aba só no DOM. Nada ia pra barra de endereço, nenhuma
entrada entrava no histórico. Então o "voltar" do navegador não voltava uma
aba: saía do painel inteiro (e caía no portão, que deslogava). A mesma falta
explicava por que não dava pra mandar link de aba nem voltar do projeto pro
lugar certo.

🪤 O `interno` do `switchTab` existe pra não empilhar histórico quando a
navegação VEIO do histórico — sem ele, um Voltar dispararia outro Voltar.

🪤 A barra de "voltar ao painel" na tela do projeto exige `?adm=1` **E** sessão
de admin. O parâmetro sozinho não pode bastar: qualquer cliente digitaria e
veria uma barra de admin. Ela é conveniência, não controle de acesso — por isso
falha fechando (não mostra), nunca abrindo.
"""
import io
import os
import re

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _pagina(nome):
    return io.open(os.path.join(_RAIZ, nome), encoding="utf-8").read()


def _sem_comentarios_js(txt):
    """Tira // e /* */ pra que comentário não conte como código."""
    txt = re.sub(r"/\*.*?\*/", "", txt, flags=re.S)
    txt = re.sub(r"<!--.*?-->", "", txt, flags=re.S)
    return "\n".join(l for l in txt.splitlines() if not l.strip().startswith("//"))


def _bloco_do_portao():
    src = _sem_comentarios_js(_pagina("admin.html"))
    i = src.index("async function checkAdminAccess()")
    return src[i:src.index("\n}", src.index("catch (err)", i))]


# ── (f) o portão não expulsa por falha de rede ─────────────────────────────
def test_o_catch_do_portao_NAO_manda_pro_login():
    """🩸 A linha que deslogava o dono."""
    bloco = _bloco_do_portao()
    depois_do_catch = bloco[bloco.index("catch (err)"):]
    assert "login.html" not in depois_do_catch, (
        "o catch do portão continua mandando pro login — falha de rede ainda "
        "é lida como 'você não é admin'")
    assert "gate-erro" in depois_do_catch, (
        "não mostra a tela de 'não consegui conferir'")


def test_sem_sessao_E_sem_erro_AINDA_manda_pro_login():
    """🧪 CONTROLE: o conserto não pode virar porta aberta. Quem está
    realmente deslogado tem que ir pro login como sempre foi."""
    bloco = _bloco_do_portao()
    assert "window.location.href = 'login.html'" in bloco, (
        "ninguém mais vai pro login — o portão virou decoração")


def test_tenta_mais_de_uma_vez_antes_de_desistir():
    """🪤 `getSession()` pode devolver null no primeiro instante depois de um
    'voltar', antes de o cliente do Supabase reidratar. Uma tentativa só
    transformava essa corrida em logout."""
    bloco = _bloco_do_portao()
    assert "for (let i = 0; i < 3" in bloco, "não repete a checagem"
    assert "setTimeout" in bloco, "repete sem esperar entre as tentativas"


def test_a_tela_de_erro_EXISTE_no_html():
    """Guarda de ponta a ponta: o código mostra `gate-erro`, e o elemento
    precisa existir — senão o dono vê tela branca, que é pior que o logout."""
    html = _pagina("admin.html")
    assert 'id="gate-erro"' in html, "o código mostra um elemento que não existe"
    i = html.index('id="gate-erro"')
    trecho = html[i:i + 1200]
    assert "location.reload()" in trecho, "a tela de erro não tem como tentar de novo"
    assert "login.html" in trecho, "não deixa saída manual pra quem realmente saiu"


# ── (f/e) a aba mora na URL ────────────────────────────────────────────────
def test_switchTab_escreve_a_aba_na_URL():
    src = _sem_comentarios_js(_pagina("admin.html"))
    i = src.index("function switchTab(")
    assert "location.hash = tabName" in src[i:i + 700], (
        "trocar de aba não mexe na URL — o Voltar do navegador continua "
        "saindo do painel inteiro")


def test_existe_listener_de_hashchange():
    src = _sem_comentarios_js(_pagina("admin.html"))
    assert "'hashchange'" in src, "a URL muda e o painel não acompanha"


def test_CONTROLE_o_hash_nao_empilha_historico_quando_veio_DO_historico():
    """🪤 Sem o `interno`, responder ao hashchange reescreveria o hash e criaria
    outra entrada — o Voltar viraria um laço."""
    src = _sem_comentarios_js(_pagina("admin.html"))
    i = src.index("function switchTab(")
    assert "interno" in src[i:i + 400], "o parâmetro que evita o laço sumiu"
    # 🪤 O regex anterior usava [^)]* e não passava pelo `() =>` do arrow —
    # reprovava código correto. Ancorar no listener e olhar o que vem depois.
    j = src.index("'hashchange'")
    assert re.search(r"switchTab\(_abaDoHash\(\),\s*true\)", src[j:j + 200]), (
        "o listener de hashchange não passa `interno` — vira laço de histórico")


def test_hash_invalido_cai_no_dashboard_e_nao_em_tela_branca():
    src = _sem_comentarios_js(_pagina("admin.html"))
    i = src.index("function _abaDoHash()")
    trecho = src[i:i + 400]
    assert "getElementById('tab-'" in trecho, (
        "aceita qualquer hash — `#qualquercoisa` abriria um painel vazio, que "
        "se lê como painel quebrado")
    assert "'dashboard'" in trecho


# ── (g) a volta pro painel existe ──────────────────────────────────────────
def test_os_links_de_projeto_do_admin_marcam_que_vem_do_admin():
    html = _pagina("admin.html")
    assert 'href="projeto.html?job_id=' not in html, (
        "sobrou link de projeto sem a marca `adm=1` — dali o Pedro não tem volta")
    assert html.count('projeto.html?adm=1&job_id=') >= 6, (
        "os links do admin perderam a marca")


def test_a_mensagem_PRO_CLIENTE_nao_leva_a_marca_de_admin():
    """🧪 CONTROLE: o texto que vai por e-mail/WhatsApp pro CLIENTE aponta pra
    mesma página, e ali `adm=1` não faz sentido nenhum — seria confuso e
    vazaria que existe uma visão de admin."""
    html = _pagina("admin.html")
    i = html.index("'Ver: https://ai.arq.br/projeto.html")
    assert "adm=1" not in html[i:i + 120], (
        "a marca de admin vazou pro texto que vai pro cliente")


def test_a_barra_de_volta_existe_e_e_travada_por_sessao():
    proj = _pagina("projeto.html")
    assert 'id="barra-admin"' in proj, "a barra de voltar não existe"
    assert "admin.html#projetos" in proj, "a barra não leva de volta ao painel"
    js = _sem_comentarios_js(proj)
    i = js.index("mostrarBarraDoAdmin")
    trecho = js[i:i + 900]
    assert "urlParams.get('adm')" in trecho, "não checa o parâmetro"
    assert "aiarqEmailMatches" in trecho, (
        "🚨 mostra a barra só pelo parâmetro da URL — qualquer cliente digitaria "
        "`?adm=1` e veria uma barra de admin")
    assert "getSession" in trecho, "não confere a sessão"


def test_CONTROLE_a_barra_nasce_ESCONDIDA():
    """Se nascesse visível, todo cliente veria 'voltar ao painel' por um
    instante antes do JS rodar — e alguns veriam pra sempre, se o JS falhasse."""
    proj = _pagina("projeto.html")
    i = proj.index('id="barra-admin"')
    assert "hidden" in proj[i:i + 120], "a barra nasce visível pro cliente"


def test_CONTROLE_a_barra_falha_FECHANDO():
    """🪤 Ela é conveniência, não controle de acesso. Se a checagem estourar,
    o certo é não mostrar — nunca mostrar por precaução."""
    js = _sem_comentarios_js(_pagina("projeto.html"))
    i = js.index("mostrarBarraDoAdmin")
    trecho = js[i:i + 1100]
    catch = trecho[trecho.index("catch"):]
    assert "remove('hidden')" not in catch, (
        "o catch mostra a barra — falha abrindo, que é o lado errado")
