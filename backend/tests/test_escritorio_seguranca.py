# -*- coding: utf-8 -*-
"""Escritório — revisão de segurança de 24/09/2026 (pedido do Pedro: "isso deixa o site
muito mais sensível com infos de terceiros").

O que estes guardas provam:
  • XSS guardado: texto que vem de PESSOA (nome, título, e-mail) não entra dentro de
    atributo on*="..." — ali o esc() NÃO protege, porque o navegador desfaz &#39; em '
    ANTES de rodar o JS do atributo. O botão @menção fazia isso com o nome do colega
    (que vem do cadastro dele): um nome-armadilha rodaria JS no navegador da admin;
  • o texto do convite não carrega quebra de linha pro ASSUNTO do e-mail;
  • o convite sai pelo nosso e-mail, então tem teto por dia — e "não consegui contar"
    é 502, nunca "zero" (zero liberaria o envio justamente quando não sei);
  • a tela pede as colunas de escritorio_membros POR NOME, sem e-mail/telefone: contato
    da equipe só pelo RPC do admin.
🧪 Controles positivos: o detector de XSS reprova o trecho antigo, literal.
"""
import os
import re
import sys
import types

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(os.path.dirname(_AQUI))
sys.path.insert(0, os.path.dirname(_AQUI))

import escritorio as esc  # noqa: E402



@pytest.fixture(autouse=True)
def _devolve_as_pecas_do_modulo():
    """🩸 24/09: estes testes trocam as peças do módulo por dublês; sem devolver, a
    PRÉVIA do painel (test_todo_email_que_sai_tem_ficha) rodava depois com a moldura
    falsa e reprovava — só no CI, onde a ordem dos testes é outra."""
    antes = (esc._SERVICO, esc._COMO_USUARIO, esc._USUARIO, esc._ENVIAR, esc._MOLDURA, esc._REGISTRAR)
    yield
    (esc._SERVICO, esc._COMO_USUARIO, esc._USUARIO, esc._ENVIAR, esc._MOLDURA, esc._REGISTRAR) = antes

PAGINAS = ("escritorio.html", "convite.html")
# dentro de um on*="..." com interpolação, só pode entrar ID (uuid), índice ou chave fixa
_ATRIB = re.compile(r'\bon[a-z]+="([^"]*\$\{[^"]*)"')
_PERIGO = re.compile(r"\$\{\s*esc\(|\$\{[^}]*\b(nome|titulo|texto|email|curto|nomeDe)\b")


def _achados(fonte: str):
    return [m.group(1)[:90] for m in _ATRIB.finditer(fonte) if _PERIGO.search(m.group(1))]


@pytest.mark.parametrize("pagina", PAGINAS)
def test_texto_de_pessoa_nao_entra_em_atributo_de_clique(pagina):
    fonte = open(os.path.join(_RAIZ, pagina), encoding="utf-8").read()
    assert not _achados(fonte), f"{pagina}: texto de pessoa dentro de on*=: {_achados(fonte)}"


def test_controle_o_detector_reprova_o_botao_antigo_da_mencao():
    antigo = """<button type="button" class="chip" onclick="mencionar('${esc(curto(m))}')">@x</button>"""
    assert _achados(antigo), "o detector não viu o XSS que existia — guarda cego"
    assert not _achados("""<button onclick="mencionar('${m.id}')">@x</button>""")


def test_a_tela_pede_membro_sem_email_nem_telefone():
    fonte = open(os.path.join(_RAIZ, "escritorio.html"), encoding="utf-8").read()
    cols = re.search(r"const COLS_MEMBRO = '([^']+)'", fonte).group(1).split(",")
    assert "email" not in cols and "telefone" not in cols and "*" not in cols
    assert "from('escritorio_membros').select('*')" not in fonte
    assert "rpc('escritorio_contatos'" in fonte


def test_quebra_de_linha_nao_chega_no_assunto():
    assert "\n" not in esc.assunto_do_convite("Fulano\nBcc: x@y.com", "Projeto")
    assert esc.texto_curto("Nome\r\nBcc: x@y.com", "nome") == "Nome Bcc: x@y.com"


# ── teto de convites ──
class _Banco:
    """Conta ENVIOS em escritorio_convites_enviados (A3, 24/09): por conta (admin=) e por destino."""
    def __init__(self, n_convites, falha=False, n_destino=0):
        self.n, self.falha, self.n_destino, self.escritas = n_convites, falha, n_destino, []

    def __call__(self, method, path, body=None, params=None, prefer=None, timeout=15, **_k):
        params = params or {}
        if method != "GET":
            self.escritas.append(path)
            return (201, [{"id": "m-novo"}])
        if "escritorio_piloto" in path:
            return (200, [{"user_id": "uid-admin"}])
        if "escritorio_projetos" in path:
            return (200, [{"id": "p1", "nome": "Projeto Exemplo", "dono": "uid-admin"}])
        if "escritorio_convites_enviados" in path:
            if self.falha:
                return (500, None)
            assert "enviado_em" in params and params["enviado_em"].startswith("gte.")
            if "admin" in params:
                assert params["admin"] == "eq.uid-admin"
                return (200, [{"id": i} for i in range(self.n)])
            assert params["destino_hash"] == "eq." + esc.hash_do_token("nova@exemplo.com")
            assert params["projeto_id"] == "eq.p1"          # teto do destinatário é POR PROJETO
            return (200, [{"id": i} for i in range(self.n_destino)])
        return (200, [])


ENVIADOS = []


def _montar(banco):
    ENVIADOS.clear()
    esc.configurar(servico=banco, como_usuario=lambda *a, **k: (200, "dono"),
                   usuario=lambda r: {"id": "uid-admin", "email": "admin@exemplo.com"},
                   enviar=lambda *a, **k: ENVIADOS.append(a[0]) or True, moldura=lambda *a, **k: "", registrar=None)


REQ = types.SimpleNamespace(headers={"Authorization": "Bearer x"})


# O fake devolve n linhas pra contagem — que JÁ inclui a reserva deste envio (reserva antes, conta depois).
def test_no_teto_do_dia_o_convite_nasce_mas_o_email_nao_sai():
    banco = _Banco(esc.CONVITES_POR_DIA + 1)
    _montar(banco)
    r = esc.convidar("p1", REQ, {"email": "nova@exemplo.com"})
    assert r["ok"] and r["email_enviado"] is False and r["motivo_sem_email"] == "teto_conta" and r["link"]
    assert ENVIADOS == []
    assert "escritorio_convites_enviados" in banco.escritas            # reservou…
    assert banco.escritas.count("escritorio_convites_enviados") == 2   # …e desfez a reserva (POST + DELETE)


def test_no_teto_exato_ainda_sai():
    banco = _Banco(esc.CONVITES_POR_DIA)
    _montar(banco)
    assert esc.convidar("p1", REQ, {"email": "nova@exemplo.com"})["email_enviado"] is True
    assert ENVIADOS == ["nova@exemplo.com"]


def test_nao_conseguir_contar_nao_manda_email_mas_entrega_o_link():
    banco = _Banco(0, falha=True)
    _montar(banco)
    r = esc.convidar("p1", REQ, {"email": "nova@exemplo.com"})
    assert r["email_enviado"] is False and r["motivo_sem_email"] == "nao_contou" and r["link"]
    assert ENVIADOS == []


def test_A3_o_mesmo_destinatario_tem_teto_proprio_por_projeto():
    banco = _Banco(1, n_destino=esc.CONVITES_POR_DESTINO_DIA + 1)
    _montar(banco)
    r = esc.convidar("p1", REQ, {"email": "nova@exemplo.com"})
    assert r["email_enviado"] is False and r["motivo_sem_email"] == "teto_destino" and ENVIADOS == []


def test_A3_abaixo_dos_dois_tetos_passa_e_registra_o_envio():
    banco = _Banco(esc.CONVITES_POR_DIA, n_destino=esc.CONVITES_POR_DESTINO_DIA)
    _montar(banco)
    assert esc.convidar("p1", REQ, {"email": "nova@exemplo.com"})["ok"] is True
    assert "escritorio_convites_enviados" in banco.escritas


def test_A5_A13_convite_pede_clique_e_sair_limpa_o_pendente():
    fonte = open(os.path.join(_RAIZ, "convite.html"), encoding="utf-8").read()
    ini = fonte.index("async function iniciar()")
    corpo_iniciar = fonte[ini:fonte.index("async function aceitarAgora()")]
    assert "convite/aceitar" not in corpo_iniciar, "aceitou sem clique"
    assert 'id="btn-aceitar"' in fonte and "Este convite já foi usado" in fonte
    for arq in ("dashboard.html", "menu-lateral.js"):
        f = open(os.path.join(_RAIZ, arq), encoding="utf-8").read()
        i = f.index("signOut")
        assert "aiarqConvite.limpar()" in f[max(0, i - 600):i], f"{arq}: Sair não limpa o convite pendente"


def test_A7_cancelar_convite_so_apaga_convite_pendente_e_confere():
    fonte = open(os.path.join(_RAIZ, "escritorio.html"), encoding="utf-8").read()
    assert ".delete({ count: 'exact' }).eq('id', id).eq('status', 'convidado')" in fonte
    assert "Essa pessoa já tinha entrado no projeto" in fonte


def test_revisao_convite_tem_saida_e_nao_prende_ninguem():
    fonte = open(os.path.join(_RAIZ, "convite.html"), encoding="utf-8").read()
    assert 'onclick="agoraNao()"' in fonte and "function agoraNao()" in fonte
    assert "aiarqConvite.limparSe(token)" in fonte          # link velho não derruba o convite novo
    ac = fonte[fonte.index("async function aceitarAgora()"):]
    assert "getSession()" in ac.split("convite/aceitar")[0], "o aceite tem que ler a sessão NA HORA do clique"
    painel = open(os.path.join(_RAIZ, "dashboard.html"), encoding="utf-8").read()
    assert "aiarq_convite_levado" in painel                 # leva ao convite 1x por sessão
    cad = open(os.path.join(_RAIZ, "cadastro.html"), encoding="utf-8").read()
    sair = cad[cad.index("async function sairDoCadastro()"):]
    assert "aiarqConvite.limpar()" in sair.split("signOut")[0]


def test_revisao_botao_excluir_bate_com_o_banco():
    fonte = open(os.path.join(_RAIZ, "escritorio.html"), encoding="utf-8").read()
    assert "!t.passou_pela_admin" in fonte and "ST_EQUIPE.includes(t.status)" in fonte


def _checa_convite_nao_guarda_antes_do_ver(fonte):
    frag = fonte[fonte.index("if (m) {"):]
    frag = frag[:frag.index("} else {")]
    assert "guardar" not in frag, "guardou o token do link antes do servidor dizer que ele vale"
    assert "sessionStorage.setItem('aiarq_convite_aba', token)" in frag, "F5 antes do servidor responder perde o token"
    ini = fonte[fonte.index("async function iniciar()"):fonte.index("async function aceitarAgora()")]
    assert "guardar(" not in ini[:ini.index("api('convite/ver'")]
    soluco = ini[ini.index("if (v.status !== 200)"):]
    soluco = soluco[:soluco.index("\n")]
    assert "guardar(" not in soluco, "no soluço o token NÃO conferido passava por cima do pendente bom"
    # a cópia da aba só sai no aceite, no recusado e no "agora não" (ela prova que o convite veio desta aba)
    ac = fonte[fonte.index("async function aceitarAgora()"):]
    assert "esquecerAba()" in ac and "window.aiarqConvite.limparSe(token);" in ac and "aiarqConvite.limpar()" not in ac


def test_revisao2_link_morto_nao_apaga_o_convite_pendente_bom():
    fonte = open(os.path.join(_RAIZ, "convite.html"), encoding="utf-8").read()
    _checa_convite_nao_guarda_antes_do_ver(fonte)
    ini = fonte[fonte.index("async function iniciar()"):fonte.index("async function aceitarAgora()")]
    # o visto sai assim que há sessão, ANTES da checagem da ficha (quem para no cadastro também conta) —
    # mas SÓ com o convite aberto nesta aba; pendente de outra pessoa espera a confirmação ("Não sou eu")
    i_visto = ini.index("if (destaAba && !desistiu) VISTO = api('convite/visto', { token }, sessao);")
    assert i_visto < ini.index("if (!temFicha)")
    assert "const destaAba = !!token && token === daAba;" in fonte
    assert "if (!VISTO && !desistiu) VISTO = api('convite/visto', { token }, sessao);" in ini[ini.index("mostrar('st-confirmar')"):]
    assert ini.index("if (desistiu) return;") < ini.index("if (!temFicha)")
    for f in ("async function agoraNao()", "async function sairEUsarOutraConta()"):
        corpo = fonte[fonte.index(f):]
        assert "desligarConta()" in corpo[:corpo.index("\n  }\n")], f
    dc = fonte[fonte.index("async function desligarConta()"):]
    dc = dc[:dc.index("\n  }\n")]
    assert dc.index("await noMaximo(VISTO, 3000)") < dc.index("dispensar"), "o visto em voo chegava depois e religava a conta"
    assert "getSession()" in dc and "SESSAO" not in dc, "sessão da carga vence com a aba parada"
    # o pedido de volta pro convite já foi cumprido: apaga (ancorado na INSTRUÇÃO, não na palavra)
    assert r"if (_r && /^convite\.html/i.test(_r.para || '')) localStorage.removeItem('aiarq_redirect');" in fonte


def test_revisao3_cadastro_liga_a_conta_ao_convite_antes_da_ficha():
    cad = open(os.path.join(_RAIZ, "cadastro.html"), encoding="utf-8").read()
    bloco = cad[cad.index("// Chegou aqui = precisa preencher"):]
    bloco = bloco[:bloco.index("mostrarFormulario(")]
    assert "/api/escritorio/convite/visto" in bloco
    # só com o convite aberto NESTA aba — o pendente do navegador pode ser de outra pessoa
    assert "const _tAba = sessionStorage.getItem('aiarq_convite_aba')" in bloco
    # aba nova da confirmação de e-mail: o pendente vale só pra conta criada DEPOIS da visita ao convite
    assert "|| (_convite.em && Date.parse(session.user.created_at || '') >= _convite.em ? _convite.t : null);" in bloco
    assert "body: JSON.stringify({ token: _tAba })" in bloco and "token: _convite.t" not in bloco


def test_checagem5_sair_do_cadastro_desfaz_a_marca_antes_do_signout():
    cad = open(os.path.join(_RAIZ, "cadastro.html"), encoding="utf-8").read()
    sair = cad[cad.index("async function sairDoCadastro()"):]
    sair = sair[:sair.index("\n  }\n")]
    assert sair.index("await desligarDoConvite();") < sair.index("await sbClient.auth.signOut()")
    dc = cad[cad.index("async function desligarDoConvite()"):]
    dc = dc[:dc.index("\n  }\n")]
    assert "body: JSON.stringify({ token: t, dispensar: true })," in dc
    assert "new Promise((r) => setTimeout(r, 3000))" in dc         # sair nunca fica preso no servidor


def test_rodada_seca2_copia_velha_da_aba_cai_no_convite_guardado():
    fonte = open(os.path.join(_RAIZ, "convite.html"), encoding="utf-8").read()
    rec = fonte[fonte.index("function recusado(r) {"):]
    rec = rec[:rec.index("\n  }\n")]
    desvio = "if (!m && daAba === token && _p && _p.t !== token) { esquecerAba(); location.reload(); return; }"
    assert desvio in rec and rec.index(desvio) < rec.index("limparSe(token)")


def test_revisao4_link_colado_na_mesma_aba_e_lido():
    fonte = open(os.path.join(_RAIZ, "convite.html"), encoding="utf-8").read()
    assert "window.addEventListener('hashchange', () => { if (/(?:^#|&)t=/.test(location.hash)) location.reload(); });" in fonte


def test_revisao4_admin_que_ja_esta_no_projeto_nao_le_convite_usado():
    fonte = open(os.path.join(_RAIZ, "convite.html"), encoding="utf-8").read()
    ac = fonte[fonte.index("async function aceitarAgora()"):]
    assert ac.index("if (a.dados.ja_membro)") < ac.index("mostrar('st-pronto')")


def test_controle_o_detector_reprova_o_guardar_antigo():
    antigo = """  if (m) {
    token = m[1];
    const antes = window.aiarqConvite.pendente();
    window.aiarqConvite.guardar(token, {});
    history.replaceState(null, '', location.pathname);
  } else {
  async function iniciar() {
    const v = await api('convite/ver', { token });
    if (v.status !== 200) return erro('x', 'y', true);
  async function aceitarAgora() {"""
    with pytest.raises(AssertionError):
        _checa_convite_nao_guarda_antes_do_ver(antigo)


def test_revisao2_modal_nao_diz_enviado_quando_o_email_nao_saiu():
    fonte = open(os.path.join(_RAIZ, "escritorio.html"), encoding="utf-8").read()
    assert "abrirModal(d.email_enviado ? 'Convite enviado' : 'Convite criado, e-mail não saiu'" in fonte
