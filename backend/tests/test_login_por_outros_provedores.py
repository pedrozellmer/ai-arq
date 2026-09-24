# -*- coding: utf-8 -*-
"""Microsoft, LinkedIn e link por e-mail sem senha na tela de login (23/09/2026).

Pedido do Pedro: "login SSO Microsoft, não apenas Google" — e depois "outras
formas de login". Escolhidos por ele: Microsoft, link por e-mail e LinkedIn.

📊 Por que esses (base de 23/09, 174 contas fora as da casa): 153 Gmail, 6
Hotmail/Outlook, 15 com e-mail de empresa — 6 no Google Workspace, 4 no
Microsoft 365 e 5 em outra hospedagem (esses 5 só tinham a senha; o link por
e-mail serve pra eles). 🪤 É só quem CONSEGUIU entrar: quem desistiu na porta
por não ter a Microsoft não aparece na conta.

O que este arquivo segura:
1. Os botões de Microsoft e LinkedIn NASCEM ESCONDIDOS e só aparecem se o
   provedor estiver ligado no Supabase. Botão que aparece antes de funcionar
   devolve "provider is not enabled" pro cliente — pior que botão nenhum.
2. A Microsoft pede o escopo `email` (o Supabase recusa a conta sem ele) e
   pergunta QUAL conta (mesma dor do Google: pessoal × escritório).
3. As três voltas caem no cadastro.html, como a do Google (09/08: indo pro
   painel, metade dos cadastros se perdia).
4. O link por e-mail responde IGUAL exista a conta ou não, e o limite de envio
   por hora do Supabase vira aviso — nunca um "enviado!" que não chega.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _corpo import fonte, sem_comentarios_js  # noqa: E402


def _login():
    return fonte("login.html")


def _chamada_oauth(src, provedor):
    """O trecho `signInWithOAuth({ ... });` do provedor, sem comentários.

    🪤 A janela termina onde a CHAMADA termina (`});`), não em N caracteres —
    o guarda do Google já reprovou o login certo por medir janela fixa."""
    for m in re.finditer(r"signInWithOAuth\(", src):
        fim = src.find("});", m.start())
        trecho = sem_comentarios_js(src[m.start():fim])
        if re.search(r"provider\s*:\s*['\"]%s['\"]" % re.escape(provedor), trecho):
            return trecho
    return None


def _botao(src, bid):
    m = re.search(r'<button id="%s"[^>]*>' % re.escape(bid), src)
    return m.group(0) if m else None


# ══════════════════════════════════════════════════════════════════════════
#  1. ESCONDIDO ATÉ O PROVEDOR SER LIGADO
# ══════════════════════════════════════════════════════════════════════════
def _nasce_escondido_e_amarrado(tag, provedor):
    return (tag is not None
            and re.search(r'class="[^"]*\bhidden\b', tag) is not None
            and ('data-provedor="%s"' % provedor) in tag)


def test_microsoft_e_linkedin_nascem_escondidos_e_amarrados_ao_provedor():
    src = _login()
    for bid, prov in (("btn-microsoft-login", "azure"),
                      ("btn-linkedin-login", "linkedin_oidc")):
        assert _nasce_escondido_e_amarrado(_botao(src, bid), prov), (
            "o botão %s tem que nascer com `hidden` e `data-provedor=\"%s\"` — "
            "sem isso ele aparece antes de o provedor estar ligado e o cliente "
            "clica num botão que devolve erro" % (bid, prov))


def test_o_que_revela_o_botao_e_o_supabase_dizer_que_esta_ligado():
    src = sem_comentarios_js(_login())
    i = src.find("mostrarProvedoresLigados")
    assert i >= 0, "sumiu a função que revela os botões dos provedores ligados"
    corpo = src[i:src.find("})();", i)]
    assert "/auth/v1/settings" in corpo
    assert re.search(r"===\s*true", corpo), (
        "o botão só pode aparecer com `=== true` — valor ausente ou estranho "
        "tem que deixar escondido")
    assert "classList.remove('hidden')" in corpo


def test_google_continua_sempre_visivel():
    """🧪 Controle: o conserto não pode ter escondido o botão que traz 88% da base."""
    tag = _botao(_login(), "btn-google-login")
    assert tag and not re.search(r'class="[^"]*\bhidden\b', tag)
    assert "data-provedor" not in tag


def test_controle_positivo_botao_visivel_seria_reprovado():
    visivel = ('<button id="btn-microsoft-login" data-provedor="azure" '
               'class="mt-3 w-full flex">')
    sem_amarra = '<button id="btn-microsoft-login" class="hidden mt-3 w-full flex">'
    assert not _nasce_escondido_e_amarrado(visivel, "azure")
    assert not _nasce_escondido_e_amarrado(sem_amarra, "azure")


# ══════════════════════════════════════════════════════════════════════════
#  2 e 3. A CHAMADA DE CADA PROVEDOR
# ══════════════════════════════════════════════════════════════════════════
def _microsoft_ok(trecho):
    return (trecho is not None
            and re.search(r"scopes\s*:\s*['\"][^'\"]*\bemail\b", trecho) is not None
            and re.search(r"queryParams\s*:\s*\{[^}]*prompt\s*:\s*['\"]select_account", trecho) is not None
            and "cadastro.html" in trecho)


def test_microsoft_pede_email_pergunta_a_conta_e_volta_pro_cadastro():
    assert _microsoft_ok(_chamada_oauth(_login(), "azure")), (
        "o login com Microsoft precisa de scopes 'email' (o Supabase recusa a "
        "conta sem e-mail), prompt select_account dentro de queryParams e "
        "redirectTo no cadastro.html")


def test_linkedin_volta_pro_cadastro():
    trecho = _chamada_oauth(_login(), "linkedin_oidc")
    assert trecho is not None, (
        "o LinkedIn tem que usar `linkedin_oidc` — o `linkedin` antigo foi "
        "descontinuado pelo próprio LinkedIn")
    assert "cadastro.html" in trecho


def test_controle_positivo_a_chamada_incompleta_seria_reprovada():
    sem_email = """signInWithOAuth({
      provider: 'azure',
      options: { redirectTo: 'https://ai.arq.br/cadastro.html',
                 queryParams: { prompt: 'select_account' } }
    """
    prompt_fora = """signInWithOAuth({
      provider: 'azure',
      options: { redirectTo: 'https://ai.arq.br/cadastro.html', scopes: 'email',
                 prompt: 'select_account' }
    """
    pro_painel = """signInWithOAuth({
      provider: 'azure',
      options: { redirectTo: 'https://ai.arq.br/dashboard.html', scopes: 'email',
                 queryParams: { prompt: 'select_account' } }
    """
    assert not _microsoft_ok(sem_email)
    assert not _microsoft_ok(prompt_fora)
    assert not _microsoft_ok(pro_painel)


def test_cada_botao_tem_o_seu_ouvinte():
    src = sem_comentarios_js(_login())
    for bid in ("btn-microsoft-login", "btn-linkedin-login"):
        assert re.search(r"getElementById\('%s'\)\.addEventListener\('click'" % bid, src), (
            "o botão %s não tem ouvinte de clique — aparece e não faz nada" % bid)


# ══════════════════════════════════════════════════════════════════════════
#  4. LINK POR E-MAIL, SEM SENHA
# ══════════════════════════════════════════════════════════════════════════
def _corpo_do_link_magico(src):
    i = src.find("const linkMagico")
    return sem_comentarios_js(src[i:src.find("linkSignup.addEventListener", i)]) if i >= 0 else ""


def _link_magico_ok(corpo):
    return (re.search(r"signInWithOtp\(", corpo) is not None
            and re.search(r"emailRedirectTo\s*:\s*['\"]https://ai\.arq\.br/cadastro\.html", corpo) is not None
            # o limite de envio do Supabase tem mensagem própria
            and re.search(r"rate limit", corpo) is not None
            # e o "enviado" é o mesmo pra conta que existe e pra que não existe
            and "Se o e-mail estiver certo" in corpo
            and "não tem conta" not in corpo.lower()
            and "não existe" not in corpo.lower())


def test_link_magico_existe_volta_pro_cadastro_e_nao_entrega_quem_e_cliente():
    src = _login()
    assert 'id="link-magico"' in src, "sumiu o link de acesso por e-mail da tela"
    assert _link_magico_ok(_corpo_do_link_magico(src)), (
        "o link por e-mail precisa: signInWithOtp, voltar pro cadastro.html, "
        "tratar o limite de envio do Supabase e responder igual exista a conta "
        "ou não")


def test_controle_positivo_link_magico_que_entrega_o_cliente_seria_reprovado():
    entrega = """signInWithOtp({ email, options: { emailRedirectTo: 'https://ai.arq.br/cadastro.html' } });
      if (/rate limit/i.test(m)) {}
      if (erro) showEmailError('Esse e-mail não tem conta.');
      showEmailSuccess('Pronto! Se o e-mail estiver certo, o link chega.');"""
    sem_limite = """signInWithOtp({ email, options: { emailRedirectTo: 'https://ai.arq.br/cadastro.html' } });
      showEmailSuccess('Pronto! Se o e-mail estiver certo, o link chega.');"""
    assert not _link_magico_ok(entrega)
    assert not _link_magico_ok(sem_limite)


# ══════════════════════════════════════════════════════════════════════════
#  LGPD — quem recebe o dado tem que estar escrito
# ══════════════════════════════════════════════════════════════════════════
def test_privacidade_e_termos_citam_microsoft_e_linkedin():
    for pagina in ("privacidade.html", "termos.html"):
        txt = fonte(pagina)
        for nome in ("Microsoft", "LinkedIn"):
            assert nome in txt, (
                "%s não cita %s — o site recebe nome e e-mail por ele e a "
                "política tem que dizer" % (pagina, nome))
