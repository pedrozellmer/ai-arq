# -*- coding: utf-8 -*-
"""Quem entra pelo Google e não termina a ficha ficava preso sem saída.

🩸 04/09/2026, investigando por que 15 de 96 contas nunca subiram projeto.
Entrar com Google cria a conta NA HORA, antes de preencher qualquer coisa. Quem
não terminasse a ficha caía num circuito:

    login.html   → tem sessão → manda pro dashboard
    dashboard    → não tem perfil → manda pro cadastro
    cadastro     → não tinha "sair", não tinha menu lateral

Conferido no arquivo: **zero** ocorrências de `signOut`, "Sair" ou logout, e o
`menu-lateral.js` (que traz o Sair nas outras páginas) não é carregado aqui. Os
6 links do rodapé são páginas públicas — preços, FAQ, termos, privacidade,
licenças e voltar ao site. Nenhum desloga nem troca de conta.

🪤 MEDIDO: 14 contas Google nunca completaram a ficha, e 6 delas têm evento de
tela nesta página. Uma foi e voltou entre cadastro e landing **6 vezes em 28
segundos**; outra, 81 segundos depois de abrir o cadastro, foi clicar em
**"Entrar"** — já estando logada.

🚫 **NÃO afirmo que o beco causou essas perdas.** Nenhuma das 14 tentou trocar
de conta ou sair, e a amostra (14 em meses) nunca daria número pra atribuir
efeito. Isto é HIGIENE, não conversão: pessoa logada numa tela sem saída é
defeito por si só, e custa dez linhas. Vender como conversão seria inventar
causa — o pecado que este projeto passou o dia inteiro tirando do motor.
"""
import io
import os
import re

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CAD = io.open(os.path.join(_RAIZ, "cadastro.html"), encoding="utf-8").read()


def _sem_comentario_html(txt):
    """🪤 O comentário do conserto CITA o defeito ("não tinha signOut") pra
    explicar por que ele saiu. Acusar isso seria acusar a própria lápide."""
    return re.sub(r"<!--.*?-->", "", txt, flags=re.S)


def test_existe_saida_no_cadastro():
    corpo = _sem_comentario_html(_CAD)
    assert "signOut" in corpo, (
        "o cadastro voltou a não ter porta de saída — quem entra pelo Google e "
        "não termina a ficha fica preso: login manda pro dashboard, dashboard "
        "manda pro cadastro, e daqui não se sai")
    assert "sairDoCadastro" in corpo


def test_a_saida_DESLOGA_antes_de_navegar():
    """🪤 A ordem é o que faz o conserto funcionar. Navegar com a sessão viva
    devolve a pessoa pro dashboard, o dashboard devolve pro cadastro, e o beco
    continua igual — só que agora com um botão que parece funcionar."""
    corpo = _sem_comentario_html(_CAD)
    i = corpo.index("async function sairDoCadastro")
    fn = corpo[i:i + 500]
    i_out = fn.index("signOut")
    i_nav = fn.index("location.href")
    assert i_out < i_nav, (
        "o botão navega ANTES de deslogar — a sessão sobrevive e o circuito "
        "recomeça")


def test_a_saida_so_aparece_pra_quem_TEM_sessao():
    """Pra quem chegou aqui sem login, "Sair" não significa nada."""
    corpo = _sem_comentario_html(_CAD)
    assert 'id="btn-sair"' in corpo and 'style="display:none"' in corpo, (
        "o botão perdeu o estado inicial escondido")
    assert "getSession" in corpo, (
        "ninguém confere a sessão — ou o botão aparece pra todo mundo, ou pra "
        "ninguém")


def test_o_clique_deixa_rastro():
    """Sem evento, daqui a um mês ninguém sabe se alguém usou — e a gente volta
    a discutir isso por opinião."""
    assert "clique:sair-do-cadastro" in _CAD, (
        "sumiu a telemetria do botão")


def test_o_evento_novo_e_ACEITO_pelo_backend():
    """🪤 02/09: cinco eventos novos subiram e o `/api/track` jogou TODOS fora
    respondendo 200 — o guarda da allowlist passou verde porque nem conseguia
    ler o formato. Aqui a conferência é contra a regra real do backend."""
    import main as _m
    assert _m._track_evento_aceito("clique:sair-do-cadastro"), (
        "o backend descarta este evento em silêncio — a telemetria do botão "
        "nasce morta")


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — a página de ANTES, no MESMO julgamento
# ══════════════════════════════════════════════════════════════════════════
_ANTES = '''
<nav>
  <a href="index.html">Voltar ao site</a>
</nav>
<script>
  const sbClient = window.sbClient;
  if (window.trackEvent) trackEvent('view_cadastro');
</script>
'''


def test_CONTROLE_a_pagina_de_ANTES_REPROVA():
    corpo = _sem_comentario_html(_ANTES)
    assert "signOut" not in corpo and "sairDoCadastro" not in corpo, (
        "o critério aprova a página que não tinha saída — ele não está "
        "julgando nada")


_NAVEGA_ANTES = '''
async function sairDoCadastro() {
  window.location.href = 'index.html';
  await sbClient.auth.signOut();
}
'''


def test_CONTROLE_deslogar_DEPOIS_de_navegar_e_reprovado():
    """A regressão mais provável não é apagar o botão — é inverter a ordem."""
    i = _NAVEGA_ANTES.index("async function sairDoCadastro")
    fn = _NAVEGA_ANTES[i:i + 500]
    assert fn.index("signOut") > fn.index("location.href"), (
        "o controle está mal montado")


# ══════════════════════════════════════════════════════════════════════════
#  A outra porta: criar conta por SENHA e nunca conseguir entrar
# ══════════════════════════════════════════════════════════════════════════
_LOGIN = io.open(os.path.join(_RAIZ, "login.html"), encoding="utf-8").read()


def test_a_confirmacao_de_email_avisa_do_SPAM():
    """🩸 04/09 — a mensagem de "conta criada" NÃO falava de spam, enquanto a
    de redefinir senha, duas telas acima, fala. É a assimetria ao contrário:
    sem confirmar o e-mail a pessoa não ENTRA, e o remetente é o
    `noreply@mail.app.supabase.io`, que filtro corporativo segura.

    🪤 Achado com o cliente-28 (Tenda) parado nisso: ficha completa numa conta
    Google de manhã, e 5 h depois criou outra com o e-mail da empresa —
    `email_confirmed_at` nulo, `last_sign_in_at` nulo, nunca entrou.

    🚫 Isto NÃO prova que o e-mail dele caiu no spam (n=1, 1 hora, e 3 de 4
    contas corporativas por senha confirmaram normal). A frase entra porque a
    inconsistência é real e custa nada.
    """
    corpo = _sem_comentario_html(_LOGIN)
    i = corpo.index("Conta criada!")
    msg = corpo[i:i + 320]
    assert "spam" in msg.lower(), (
        "a mensagem de conta criada voltou a não avisar do spam — e sem "
        "confirmar o e-mail a pessoa nem consegue entrar")


def test_CONTROLE_a_redefinicao_de_senha_ja_avisava():
    """O paralelo que revelou a assimetria: se ESTA também perder o aviso, o
    teste de cima vira exigência arbitrária em vez de consistência."""
    corpo = _sem_comentario_html(_LOGIN)
    i = corpo.index("link de redefini")
    assert "spam" in corpo[i:i + 260].lower(), (
        "a mensagem de redefinição perdeu o aviso de spam — era ela o padrão "
        "que a de conta criada estava quebrando")
