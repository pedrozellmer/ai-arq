# -*- coding: utf-8 -*-
"""Lote 2 da auditoria completa do Escritório (26/09/2026) — as telas.

Achados cobertos (workflow wf_38b94278-82d):
  • TELA-1/2/7/13 — estado de um projeto vazava pro outro (subpasta, filtro de etapa, resposta atrasada do Drive,
    carregarProjeto que falhava no meio deixando o projeto novo com os dados do anterior);
  • TELA-3 — o KPI "Com o cliente" ignorava a coluna "Aguardando cliente";
  • TELA-4 — "Excluir cartão" apagava na hora, com tudo junto;
  • DRV-2 — conexão do Google morta: a tela não tinha como reconectar nem desconectar;
  • MENU-1 / MAPA-1 — "Projeto não encontrado" pra equipe; quem saiu seguia com o menu do Escritório;
  • PORTA-1 / EDIT-1 — portas do dono visíveis pra equipe (Revisar, avisos, XLSX sem liberação); memorial e
    cronograma "só leitura" que deixavam editar (e o salvar que falhava cancelava o download liberado).
Os guardas leem a INSTRUÇÃO que decide, não a palavra.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
_RAIZ = os.path.dirname(_BACKEND)
sys.path.insert(0, _BACKEND)

import escritorio as esc  # noqa: E402
import escritorio_drive as ed  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def _ler(nome):
    return open(os.path.join(_RAIZ, nome), encoding="utf-8").read()


def _corpo(fonte, cabeca, fim="\n}\n"):
    i = fonte.index(cabeca)
    return fonte[i:fonte.index(fim, i)]


H = None


def _h():
    global H
    if H is None:
        H = _ler("escritorio.html")
    return H


# ── TELA-13 / TELA-1 / TELA-2: um projeto não herda nada do outro ──
def test_carregar_projeto_troca_tudo_junto_no_fim():
    cp = _corpo(_h(), "async function carregarProjeto(id) {")
    i_leituras = cp.index("await Promise.all([")
    i_troca = cp.index("PROJ = proj; MEMBROS = membros;")
    assert i_leituras < i_troca and "PROJ = PROJETOS.find" not in cp, "o PROJ não pode trocar antes das leituras"
    # 26/09 (perfis): o bloco ganhou o filtro das fotos e a limpeza das imagens — a limpeza continua ANTES da troca
    i_se = cp.index("if (!PROJ || PROJ.id !== id) {")
    assert i_se < cp.index("ARQ_PASTA = ''; ARQ_TRILHA = []; FILTRO = 'todas'; FILTRO_E = ''; ETAPA_SEL = null;") < i_troca


def test_etapa_do_filtro_que_nao_existe_no_projeto_nao_filtra_nem_vai_pro_cartao():
    h = _h()
    assert "const etapaDoFiltro = () => ((PROJ && PROJ.etapas) || []).includes(FILTRO_E) ? FILTRO_E : '';" in h
    assert "const visivel = (t) => FILT[FILTRO](t) && (!etapaDoFiltro() || t.etapa === FILTRO_E);" in h
    assert "etapa: etapaDoFiltro() || PROJ.etapa_atual || null" in _corpo(h, "async function criarCartao(st, txt) {")


def test_resposta_velha_do_drive_nao_pinta_a_tela_e_subpasta_alheia_volta_pra_raiz():
    ca = _corpo(_h(), "async function carregarArquivos() {")
    assert ca.index("const pedido = ++ARQ_PEDIDO") < ca.index("await Promise.all(")
    assert "pedido !== ARQ_PEDIDO || !PROJ || PROJ.id !== projAqui) return;" in ca
    assert "if (l.status === 403 && ARQ_PASTA) { ARQ_PASTA = ''; ARQ_TRILHA = []; return carregarArquivos(); }" in ca


# ── TELA-3: "com o cliente" é uma regra só ──
def test_com_o_cliente_conta_a_coluna_aguardando_cliente_em_todo_lugar():
    h = _h()
    assert "const comCliente = (t) => !!t.do_cliente || t.status === 'cliente';" in h
    assert "cliente: comCliente };" in h
    assert "doCli = abertas.filter(comCliente);" in _corpo(h, "function telaCapa() {")


# ── TELA-4: excluir cartão pede confirmação ──
def test_excluir_cartao_pede_confirmacao_antes_de_apagar():
    h = _h()
    pede = _corpo(h, "function apagarCartao(id) {")
    assert ".delete(" not in pede and "abrirModal('Excluir o cartão?'" in pede
    assert ".from('escritorio_tarefas').delete({ count: 'exact' }).eq('id', id)" in _corpo(h, "async function confirmarApagarCartao(id) {")


# ── DRV-2: conexão morta tem saída ──
def test_tela_tem_desconectar_e_reconectar_quando_o_google_corta():
    h = _h()
    ca = _corpo(h, "async function carregarArquivos() {")
    assert "if (l.status === 409) {" in ca and "onclick=\"conectarDrive()\">Conectar de novo</button>" in ca
    assert "onclick=\"desconectarDrive()\">Desconectar o Drive</button>" in ca
    assert "apiEsc('drive/desconectar', 'POST')" in _corpo(h, "function desconectarDrive() {")


class _Banco:
    def __init__(self):
        self.escritas = []
        esc._SERVICO = self
        esc._REGISTRAR = None

    def __call__(self, method, path, body=None, params=None, **_k):
        if method != "GET":
            self.escritas.append((method, path, params))
        if path == "escritorio_drive_conexoes" and method == "GET":
            return 200, [{"user_id": "uid-dona", "google_email": "dona@exemplo.com", "token_cifrado": ed.cifrar("refresh")}]
        return 204, None


@pytest.fixture
def _drive(monkeypatch):
    antes = (esc._SERVICO, esc._REGISTRAR, ed._HTTP, ed.CLIENT_ID)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "segredo-de-teste-do-servidor")
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_SECRET", "segredo-do-cliente")
    ed.CLIENT_ID = "cliente-de-teste.apps.googleusercontent.com"
    ed._CACHE_ACESSO.clear()
    yield
    (esc._SERVICO, esc._REGISTRAR, ed._HTTP, ed.CLIENT_ID) = antes
    ed._CACHE_ACESSO.clear()


def test_google_cortou_a_conexao_morta_e_apagada(_drive):
    b = _Banco()
    ed._HTTP = lambda *a, **k: (400, {"error": "invalid_grant"})
    with pytest.raises(HTTPException) as e:
        ed._acesso("uid-dona")
    assert e.value.status_code == 409
    assert ("DELETE", "escritorio_drive_conexoes", {"user_id": "eq.uid-dona"}) in b.escritas


def test_controle_google_fora_do_ar_nao_apaga_a_conexao(_drive):
    b = _Banco()
    ed._HTTP = lambda *a, **k: (503, None)
    with pytest.raises(HTTPException) as e:
        ed._acesso("uid-dona")
    assert e.value.status_code == 502 and b.escritas == []


def test_cifra_que_nao_abre_mais_apaga_a_conexao(_drive, monkeypatch):
    b = _Banco()
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "outra-chave-girada")   # o token foi cifrado com a de antes
    esc._SERVICO = lambda m, path, **k: (b.escritas.append((m, path, k.get("params"))) or (204, None)) if m != "GET" else \
        (200, [{"user_id": "uid-dona", "token_cifrado": "gAAAA-lixo"}])
    with pytest.raises(HTTPException) as e:
        ed._acesso("uid-dona")
    assert e.value.status_code == 409 and ("DELETE", "escritorio_drive_conexoes", {"user_id": "eq.uid-dona"}) in b.escritas


# ── MENU-1 / MAPA-1 ──
def test_menu_da_equipe_nao_escreve_projeto_nao_encontrado_por_cima_do_escritorio():
    js = _ler("menu-lateral.js")
    sel = js[js.index("function atualizarSelo() {"):]
    assert "if (nx && !ESC) nx.textContent = 'Projeto não encontrado';" in sel[:sel.index("montarEquipe();")]
    eq = js[js.index("function montarEquipe() {"):]
    eq = eq[:eq.index("\n  }\n")]
    assert "if (nx) nx.textContent = ESC ? String(ESC.nome || 'Projeto').slice(0, 160) :" in eq


def test_quem_saiu_da_equipe_perde_o_menu_do_escritorio():
    js = _ler("menu-lateral.js")
    eq = js[js.index("function montarEquipe() {"):]
    eq = eq[:eq.index("\n  }\n")]
    bloco = eq[eq.index("if (a && a.negado) {"):eq.index("if (!a || !a.so_leitura)")]
    for passo in ("gravarMapa(JOB, null);", "sessionStorage.removeItem('aiarq_esc_ctx')", "tirarItensDoDono();"):
        assert passo in bloco, passo
    u = _ler("aiarq-utils.js")
    assert "if (r && (r.status === 403 || r.status === 404)) return { negado: true };" in u


# ── PORTA-1 / EDIT-1 ──
def test_projeto_esconde_as_portas_do_dono_da_equipe():
    p = _ler("projeto.html")
    for sel in (".so-leitura #btn-review", ".so-leitura #expansao-disciplinas", ".so-leitura #pd-prompt",
                ".so-leitura [data-coer]", ".so-leitura #aviso-coerencia", ".sem-baixar #btn-download"):
        assert sel in p, sel
    # o elemento REAL existe com o id que a regra esconde (a regra por texto de onclick não pegava o XLSX)
    for el in ('id="btn-review"', 'id="btn-download"', 'id="expansao-disciplinas"', 'id="pd-prompt"'):
        assert el in p, el
    assert "if (btnId === 'btn-review' && document.documentElement.classList.contains('so-leitura')) return;" in p


def test_memorial_da_equipe_nao_edita_e_o_download_liberado_nao_trava():
    m = _ler("memorial.html")
    sv = m[m.index("async function salvar() {"):]
    assert sv.index("if (ehSoLeitura()) return true;") < sv.index("await authFetch(")
    assert "if (!el || ehSoLeitura()) return;" in m
    assert "el.setAttribute('contenteditable', 'false')" in _corpo(m, "function travarEdicaoDaEquipe() {")
    assert "travarEdicaoDaEquipe();" in m[m.index("c.innerHTML = html;"):m.index("c.innerHTML = html;") + 60]


def test_cronograma_da_equipe_nao_abre_o_editor_nem_tenta_gerar():
    c = _ler("cronograma.html")
    assert ".so-leitura #editor, .so-leitura #inputs-card, .so-leitura #aviso-coerencia { display: none !important; }" in c
    i = c.index("if (_acesso && _acesso.so_leitura) {")
    assert i < c.index("await carregarSugestao();\n    autoGerarPrimeiraVisita();")


def test_revisao_manda_a_equipe_pro_quantitativo_e_so_comemora_com_resposta_ok():
    r = _ler("revisao.html")
    ini = r[r.index("(async function init() {"):r.index("await loadItems();")]
    assert "if (_a && _a.so_leitura) { window.location.replace(" in ini
    fin = r[r.index("const _fin = await authFetch("):]
    assert fin.index("if (!_fin || !_fin.ok) {") < fin.index("trackEvent('revisao_concluida'") < fin.index("'Revisão concluída!")
