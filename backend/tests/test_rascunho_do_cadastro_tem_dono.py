# -*- coding: utf-8 -*-
"""O rascunho do cadastro era de todo mundo e de ninguém.

🩸 04/09/2026. A tela do cadastro guarda um rascunho no navegador enquanto a
pessoa preenche — nome, WhatsApp, **CPF/CNPJ**, empresa, área, cargo. A chave era
UMA SÓ, `aiarq_cadastro_draft`, sem dono, e o `clearDraft()` só rodava quando a
ficha era salva com sucesso.

Quem desistia deixava o CPF no navegador. A PRÓXIMA pessoa a abrir esta tela, com
outra conta Google, recebia o formulário preenchido com os dados da anterior — e
um aviso verde dizendo "✓ Restauramos 3 campo(s) do seu cadastro anterior". Se
ela não reparasse e salvasse, o CPF da primeira entrava na ficha da segunda.

🪤 O botão "Sair / usar outra conta" entrou HOJE (`ab7097f`) e pôs a troca de
conta a UM CLIQUE exatamente nesta tela. O vazamento já existia — dava pra chegar
nele deslogando por outro caminho — mas eu deixei ele fácil, e não apaguei nada
ao sair.

📏 MEDIDO no mesmo dia: duas contas Google nasceram às 16:51:42 e 16:52:55, do
MESMO IP e do MESMO navegador (Chrome 148/Mac), com um logout às 16:52:37 entre
as duas. A sessão da primeira não existe mais no banco enquanto uma de dois dias
antes continua lá — ela saiu de propósito. O caminho do vazamento estava aberto.
🚫 NÃO afirmo que os dados dela apareceram pra segunda conta: o rastro que
provaria isso mora no navegador dela, não no nosso banco. O defeito é real por si
só e não depende dessa confirmação.

O que este guarda exige:
  1. a chave do rascunho tem DONO (não é constante compartilhada);
  2. sair APAGA o rascunho, e apaga ANTES de deslogar (depois do signOut já não
     se sabe de quem era);
  3. a chave antiga, sem dono, é removida dos navegadores que já a têm.
"""
import io
import os
import re

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CAD = io.open(os.path.join(_RAIZ, "cadastro.html"), encoding="utf-8").read()

_CHAVE_ANTIGA = "aiarq_cadastro_draft"


def _sem_comentario_html(txt):
    return re.sub(r"<!--.*?-->", "", txt, flags=re.S)


def _bloco_do_rascunho(txt):
    """As três funções do rascunho, do início da primeira ao fim da última.

    🪤 Ancorado nos DOIS extremos de propósito. Um guarda meu de 03/09 usou
    janela de tamanho fixo (3800 chars) e reprovou dois testes corretos só
    porque eu adicionei um comentário acima do trecho.
    """
    i = txt.index("function saveDraft")
    j = txt.index("function clearDraft")
    fim = txt.index("}", txt.index("removeItem", j))
    return txt[i:fim]


def _chaves_de_rascunho_no_bloco(bloco):
    """Toda chave de localStorage usada pelo rascunho, como o código a escreve."""
    return re.findall(
        r"localStorage\.(?:get|set|remove)Item\(\s*([^,)]+)", bloco)


# ══════════════════════════════════════════════════════════════════════════
#  1. A CHAVE TEM DONO
# ══════════════════════════════════════════════════════════════════════════
def test_a_chave_do_rascunho_tem_dono():
    """Duas pessoas no mesmo navegador não podem compartilhar rascunho.

    🪤 Ancorado no FATO (a chave depende de quem está logado), não na forma:
    não exijo função com nome X nem separador Y. A única identidade de pessoa
    que existe nesta página é `currentUser` — se ela não participa da chave,
    a chave é a mesma pra todo mundo.
    """
    bloco = _bloco_do_rascunho(_sem_comentario_html(_CAD))
    assert "currentUser" in bloco, (
        "as funções do rascunho não olham quem está logado — a chave é a mesma "
        "para todo mundo, e o CPF de uma pessoa reaparece pra próxima que abrir "
        "esta tela no mesmo navegador")


def test_as_TRES_funcoes_usam_a_MESMA_chave():
    """O conserto pela METADE é a regressão mais provável, e a mais traiçoeira.

    🪤 Amarrar a chave ao usuário em `saveDraft` e `restoreDraft` e esquecer o
    `clearDraft` deixa o vazamento inteiro de pé: a limpeza apaga uma chave que
    ninguém mais escreve, e o rascunho com CPF fica no disco pra sempre. O teste
    de cima passaria verde, porque `currentUser` apareceria no bloco.

    🩸 Foi exatamente esta a doença de 04/09 de manhã: um guarda meu procurava a
    chamada por NOME e ficava cego pra 3 dos 5 lugares — cobertura tem que ser
    por lugar, não por amostra.
    """
    bloco = _bloco_do_rascunho(_sem_comentario_html(_CAD))
    chaves = {k.strip() for k in _chaves_de_rascunho_no_bloco(bloco)}
    assert chaves, "não achei nenhum acesso ao localStorage — o guarda cegou"
    assert len(chaves) == 1, (
        "as funções do rascunho usam chaves DIFERENTES entre si (%s) — alguma "
        "ficou pra trás, e a que ficou não é apagada por ninguém" %
        ", ".join(sorted(chaves)))


# ══════════════════════════════════════════════════════════════════════════
#  2. SAIR APAGA — E APAGA ANTES DE DESLOGAR
# ══════════════════════════════════════════════════════════════════════════
def _funcao_sair(txt):
    i = txt.index("async function sairDoCadastro")
    return txt[i:txt.index("\n  }", i)]


def test_sair_apaga_o_rascunho():
    corpo = _sem_comentario_html(_CAD)
    fn = _funcao_sair(corpo)
    assert "clearDraft" in fn, (
        "o botão de sair não apaga o rascunho — a pessoa sai achando que "
        "limpou e deixa nome, WhatsApp e CPF no navegador pra próxima")


def test_apaga_ANTES_de_deslogar():
    """Depois do `signOut()` não se sabe mais de quem era o rascunho.

    🪤 Com a chave amarrada ao usuário, limpar depois do signOut não limpa
    coisa nenhuma: `currentUser` da sessão já morreu e a chave calculada seria
    outra (ou nenhuma). O guarda passaria e o dado continuaria lá.
    """
    fn = _funcao_sair(_sem_comentario_html(_CAD))
    assert "clearDraft" in fn and "signOut" in fn, (
        "falta clearDraft ou signOut na função de sair — ver o teste acima")
    assert fn.index("clearDraft") < fn.index("signOut"), (
        "o rascunho é apagado DEPOIS do signOut — nesse ponto já não se sabe "
        "de quem ele era, e a limpeza erra a chave")


# ══════════════════════════════════════════════════════════════════════════
#  2b. O RASCUNHO VEM ANTES DO NOME DO GOOGLE
# ══════════════════════════════════════════════════════════════════════════
def _ordem_no_checkauth(txt):
    """(posição do restoreDraft, posição do preenchimento pelo Google)."""
    i = txt.index("async function checkAuth")
    corpo = txt[i:txt.index("\n  checkAuth();", i)]
    return corpo.index("restoreDraft()"), corpo.index("meta.full_name")


def test_o_rascunho_vence_o_nome_da_conta_google():
    """🩸 Conserto de 09/08 que vivia só num comentário — e eu mexi nele hoje.

    O rascunho só preenche campo VAZIO, de propósito. Se o nome do Google
    entrar primeiro, o campo deixa de estar vazio e o rascunho não devolve mais
    nada: quem digitou "Maria S. Souza Neta" recebe "Maria Souza" de volta.

    Antes de 04/09 a ordem certa era acidental — dependia de uma chamada no fim
    do script rodar antes de uma função async terminar. Agora é explícita, e
    passa a ter guarda: era a única coisa que o meu diff de hoje podia quebrar
    em silêncio.
    """
    i_restore, i_google = _ordem_no_checkauth(_sem_comentario_html(_CAD))
    assert i_restore < i_google, (
        "o nome da conta Google é preenchido ANTES de restaurar o rascunho — "
        "o campo deixa de estar vazio e a edição da pessoa é descartada")


def test_CONTROLE_a_ordem_invertida_e_reprovada():
    invertido = '''
  async function checkAuth() {
    currentUser = session.user;
    if (!nomeInput.value) nomeInput.value = meta.full_name || meta.name || '';
    restoreDraft();
  }
  checkAuth();
'''
    i_restore, i_google = _ordem_no_checkauth(invertido)
    assert i_restore > i_google, "o controle está mal montado"


# ══════════════════════════════════════════════════════════════════════════
#  3. A CHAVE ANTIGA SAI DOS NAVEGADORES QUE JÁ A TÊM
# ══════════════════════════════════════════════════════════════════════════
def test_a_chave_velha_sem_dono_e_removida():
    """Consertar daqui pra frente não tira o CPF de quem já está no disco."""
    corpo = _sem_comentario_html(_CAD)
    assert re.search(
        r"removeItem\(\s*['\"]%s['\"]" % re.escape(_CHAVE_ANTIGA), corpo), (
        "a chave antiga sem dono nunca é removida — quem já tem um rascunho "
        "gravado por ela continua com o dado lá, e a próxima pessoa naquele "
        "navegador ainda pode recebê-lo")


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — a página de ANTES, no MESMO julgamento
# ══════════════════════════════════════════════════════════════════════════
_ANTES = '''
  const DRAFT_KEY = 'aiarq_cadastro_draft';
  const DRAFT_FIELDS = ['nome', 'whatsapp', 'cpf_cnpj'];

  function saveDraft() {
    try {
      const data = {};
      DRAFT_FIELDS.forEach(id => {
        const el = document.getElementById(id);
        if (el) data[id] = el.value;
      });
      localStorage.setItem(DRAFT_KEY, JSON.stringify(data));
    } catch (e) { }
  }

  function restoreDraft() {
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      if (!raw) return;
    } catch (e) { }
  }

  function clearDraft() {
    try { localStorage.removeItem(DRAFT_KEY); } catch (e) {}
  }
'''

_SAIR_ANTES = '''
  async function sairDoCadastro() {
    if (window.trackEvent) trackEvent('clique:sair-do-cadastro');
    try { await sbClient.auth.signOut(); } catch (_) {}
    window.location.href = 'index.html';
  }
'''


def test_CONTROLE_a_chave_de_ANTES_nao_tinha_dono():
    bloco = _bloco_do_rascunho(_ANTES)
    assert "currentUser" not in bloco, (
        "o critério aprova a chave compartilhada de antes — não julga nada")


_CONSERTO_PELA_METADE = '''
  function saveDraft() {
    try {
      localStorage.setItem(draftKey(), JSON.stringify(data));
    } catch (e) { }
  }

  function restoreDraft() {
    try {
      const raw = localStorage.getItem(draftKey());
      if (!raw) return;
    } catch (e) { }
  }

  function clearDraft() {
    try { localStorage.removeItem(DRAFT_KEY); } catch (e) {}
  }
'''


def test_CONTROLE_o_conserto_pela_METADE_e_reprovado():
    """Duas funções amarradas ao dono, a limpeza esquecida com a chave velha.

    Este controle é o que dá sentido ao teste das três chaves: sem ele, eu não
    saberia se aquele teste consegue reprovar alguma coisa. Note que o
    `currentUser` NÃO aparece aqui — o `draftKey()` é que o usa — e mesmo assim
    o defeito precisa ser pego.
    """
    bloco = _bloco_do_rascunho(_CONSERTO_PELA_METADE)
    chaves = {k.strip() for k in _chaves_de_rascunho_no_bloco(bloco)}
    assert len(chaves) > 1, (
        "o controle está mal montado — ele deveria ter chaves diferentes")


def test_CONTROLE_o_sair_de_ANTES_nao_apagava():
    fn = _SAIR_ANTES[_SAIR_ANTES.index("async function sairDoCadastro"):]
    assert "clearDraft" not in fn, "o controle está mal montado"


def test_CONTROLE_limpar_DEPOIS_do_signout_e_reprovado():
    """A regressão mais provável não é apagar a limpeza — é pô-la no lugar errado."""
    tarde = '''
  async function sairDoCadastro() {
    try { await sbClient.auth.signOut(); } catch (_) {}
    clearDraft();
    window.location.href = 'index.html';
  }
'''
    fn = tarde[tarde.index("async function sairDoCadastro"):]
    assert fn.index("clearDraft") > fn.index("signOut"), (
        "o controle está mal montado")
