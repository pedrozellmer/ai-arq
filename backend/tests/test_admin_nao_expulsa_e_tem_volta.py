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
que mordeu o motor o dia inteiro: falha tratada como resposta.

CAUSA 2 — A ABA NÃO EXISTIA NA URL.
`switchTab` trocava a aba só no DOM. Nada ia pra barra de endereço, nenhuma
entrada entrava no histórico. Então o "voltar" do navegador não voltava uma
aba: saía do painel inteiro (e caía no portão, que deslogava). A mesma falta
explicava por que não dava pra mandar link de aba nem voltar do projeto pro
lugar certo.

🩸 02/09 — A LIÇÃO QUE ESTE ARQUIVO QUASE NÃO APRENDEU.
A 1ª versão deste guarda lia SÓ `admin.html`. Consertei o portão de lá, a
bancada ficou verde, e `admin-usuario.html` — que é justamente onde o Pedro cai
ao clicar num usuário, o caminho EXATO da queixa dele — continuou com a versão
antiga: uma tentativa e `catch` -> login. Um cético achou. O guarda dava a
sensação de cobertura que não tinha. Agora ele é parametrizado, e
`test_TODA_pagina_com_portao_esta_na_lista` cobra a próxima que nascer.

🪤 O `interno` do `switchTab` existe pra não empilhar histórico quando a
navegação VEIO do histórico — sem ele, um Voltar dispararia outro Voltar.

🪤 A barra de "voltar ao painel" na tela do projeto exige `?adm=1` **E** sessão
de admin. O parâmetro sozinho não pode bastar: qualquer cliente digitaria e
veria uma barra de admin. Ela é conveniência, não controle de acesso — por isso
falha fechando (não mostra), nunca abrindo.
"""
import glob
import io
import os
import re

import pytest

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: toda página que tem portão de admin. Nasceu outra? entra aqui.
PAGINAS_COM_PORTAO = ["admin.html", "admin-usuario.html"]


def _pagina(nome):
    return io.open(os.path.join(_RAIZ, nome), encoding="utf-8").read()


def _sem_comentarios_js(txt):
    """Tira // e /* */ e <!-- --> pra que comentário não conte como código."""
    txt = re.sub(r"/\*.*?\*/", "", txt, flags=re.S)
    txt = re.sub(r"<!--.*?-->", "", txt, flags=re.S)
    return "\n".join(l for l in txt.splitlines() if not l.strip().startswith("//"))


def _bloco_do_portao(pagina):
    """O corpo de `checkAdminAccess`, do começo até a chave que fecha.

    🪤 Cortar no PRIMEIRO `catch` estava errado: depois do conserto existe um
    `catch` interno, o do laço de tentativas, e ele fica antes do que importa.
    O fim da função é a chave sozinha no começo da linha.
    """
    src = _sem_comentarios_js(_pagina(pagina))
    i = src.index("async function checkAdminAccess()")
    m = re.search(r"^\}", src[i:], re.M)
    return src[i:i + m.start()]


def _depois_do_ultimo_catch(bloco):
    """O que roda quando a função inteira estoura — o `catch` de fora."""
    return bloco[bloco.rindex("catch"):]


# ── (f) o portão não expulsa por falha de rede ─────────────────────────────
@pytest.mark.parametrize("pagina", PAGINAS_COM_PORTAO)
def test_o_catch_do_portao_NAO_manda_pro_login(pagina):
    """🩸 A linha que deslogava o dono — nas DUAS páginas."""
    depois = _depois_do_ultimo_catch(_bloco_do_portao(pagina))
    assert "login.html" not in depois, (
        "%s: o catch do portão continua mandando pro login — falha de rede "
        "ainda é lida como 'você não é admin'" % pagina)
    assert ("gate-erro" in depois) or ("_mostraErroDoPortao" in depois), (
        "%s: não mostra a tela de 'não consegui conferir'" % pagina)


@pytest.mark.parametrize("pagina", PAGINAS_COM_PORTAO)
def test_sem_sessao_E_sem_erro_AINDA_manda_pro_login(pagina):
    """🧪 CONTROLE: o conserto não pode virar porta aberta. Quem está
    realmente deslogado tem que ir pro login como sempre foi."""
    assert "login.html" in _bloco_do_portao(pagina), (
        "%s: ninguém mais vai pro login — o portão virou decoração" % pagina)


@pytest.mark.parametrize("pagina", PAGINAS_COM_PORTAO)
def test_tenta_mais_de_uma_vez_antes_de_desistir(pagina):
    """🪤 `getSession()` pode devolver null no primeiro instante depois de uma
    navegação, antes de o cliente do Supabase reidratar. Uma tentativa só
    transformava essa corrida em logout."""
    src = _sem_comentarios_js(_pagina(pagina))
    assert "for (let i = 0; i < 3" in src, "%s: não repete a checagem" % pagina
    assert "setTimeout" in src, "%s: repete sem esperar entre as tentativas" % pagina


@pytest.mark.parametrize("pagina", PAGINAS_COM_PORTAO)
def test_a_tela_de_erro_EXISTE_no_html(pagina):
    """Guarda de ponta a ponta: o código mostra `gate-erro`, e o elemento
    precisa existir — senão o dono vê tela branca, que é pior que o logout."""
    html = _pagina(pagina)
    assert 'id="gate-erro"' in html, (
        "%s: o código mostra um elemento que não existe" % pagina)
    trecho = html[html.index('id="gate-erro"'):][:1200]
    assert "location.reload()" in trecho, (
        "%s: a tela de erro não tem como tentar de novo" % pagina)


def test_TODA_pagina_com_portao_esta_na_lista():
    """🩸 O guarda que não cobria a página vizinha. Se nascer um terceiro
    `checkAdminAccess`, ele entra na lista — ou este teste cai."""
    achadas = [os.path.basename(f) for f in glob.glob(os.path.join(_RAIZ, "*.html"))
               if "checkAdminAccess" in io.open(f, encoding="utf-8").read()]
    assert sorted(achadas) == sorted(PAGINAS_COM_PORTAO), (
        "página com portão de admin fora da cobertura deste guarda: %s"
        % sorted(set(achadas) - set(PAGINAS_COM_PORTAO)))


# ── (f/e) a aba mora na URL ────────────────────────────────────────────────
def test_switchTab_escreve_a_aba_na_URL():
    src = _sem_comentarios_js(_pagina("admin.html"))
    i = src.index("function switchTab(")
    assert "location.hash = tabName" in src[i:i + 700], (
        "trocar de aba não mexe na URL — o Voltar do navegador continua "
        "saindo do painel inteiro")


def test_existe_listener_de_hashchange():
    assert "'hashchange'" in _sem_comentarios_js(_pagina("admin.html")), (
        "a URL muda e o painel não acompanha")


def test_CONTROLE_o_hash_nao_empilha_historico_quando_veio_DO_historico():
    """🪤 Sem o `interno`, responder ao hashchange reescreveria o hash e criaria
    outra entrada — o Voltar viraria um laço."""
    src = _sem_comentarios_js(_pagina("admin.html"))
    i = src.index("function switchTab(")
    assert "interno" in src[i:i + 400], "o parâmetro que evita o laço sumiu"
    j = src.index("'hashchange'")
    assert re.search(r"switchTab\(_abaDoHash\(\),\s*true\)", src[j:j + 200]), (
        "o listener de hashchange não passa `interno` — vira laço de histórico")


def test_hash_invalido_cai_no_dashboard_e_nao_em_tela_branca():
    src = _sem_comentarios_js(_pagina("admin.html"))
    trecho = src[src.index("function _abaDoHash()"):][:400]
    assert "getElementById('tab-'" in trecho, (
        "aceita qualquer hash — `#qualquercoisa` abriria um painel vazio, que "
        "se lê como painel quebrado")
    assert "'dashboard'" in trecho


# ── (g) a volta pro painel existe ──────────────────────────────────────────
@pytest.mark.parametrize("pagina", PAGINAS_COM_PORTAO)
def test_os_links_de_projeto_marcam_que_vem_do_admin(pagina):
    """🪤 `admin-usuario.html` tinha 2 links sem a marca e ficou de fora do
    conserto de ontem — mesmo furo do portão, mesma causa: guarda que olhava
    uma página só."""
    html = _pagina(pagina)
    assert 'href="projeto.html?job_id=' not in html, (
        "%s: sobrou link de projeto sem a marca `adm=1` — dali não há volta"
        % pagina)


def test_o_admin_tem_os_links_marcados():
    assert _pagina("admin.html").count('projeto.html?adm=1&job_id=') >= 6, (
        "os links do painel perderam a marca")


def test_a_mensagem_PRO_CLIENTE_nao_leva_a_marca_de_admin():
    """🧪 CONTROLE: o texto que vai por e-mail/WhatsApp pro CLIENTE aponta pra
    mesma página, e ali `adm=1` não faz sentido — seria confuso e vazaria que
    existe uma visão de admin."""
    html = _pagina("admin.html")
    i = html.index("'Ver: https://ai.arq.br/projeto.html")
    assert "adm=1" not in html[i:i + 120], (
        "a marca de admin vazou pro texto que vai pro cliente")


def test_a_barra_de_volta_existe_e_e_travada_por_sessao():
    proj = _pagina("projeto.html")
    assert 'id="barra-admin"' in proj, "a barra de voltar não existe"
    assert "admin.html#projetos" in proj, "a barra não leva de volta ao painel"
    js = _sem_comentarios_js(proj)
    trecho = js[js.index("mostrarBarraDoAdmin"):][:900]
    assert "urlParams.get('adm')" in trecho, "não checa o parâmetro"
    assert "aiarqEmailMatches" in trecho, (
        "🚨 mostra a barra só pelo parâmetro da URL — qualquer cliente digitaria "
        "`?adm=1` e veria uma barra de admin")
    assert "getSession" in trecho, "não confere a sessão"


def test_CONTROLE_a_barra_nasce_ESCONDIDA():
    """Se nascesse visível, todo cliente veria 'voltar ao painel' por um
    instante antes do JS rodar — e alguns veriam pra sempre, se o JS falhasse."""
    proj = _pagina("projeto.html")
    assert "hidden" in proj[proj.index('id="barra-admin"'):][:160], (
        "a barra nasce visível pro cliente")


def test_CONTROLE_a_barra_falha_FECHANDO():
    """🪤 Ela é conveniência, não controle de acesso. Se a checagem estourar,
    o certo é não mostrar — nunca mostrar por precaução."""
    js = _sem_comentarios_js(_pagina("projeto.html"))
    trecho = js[js.index("mostrarBarraDoAdmin"):][:1100]
    catch = trecho[trecho.index("catch"):]
    assert "remove('hidden')" not in catch, (
        "o catch mostra a barra — falha abrindo, que é o lado errado")
