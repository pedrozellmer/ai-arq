"""25/09/2026 — Pedro: "clico em Financeiro e ele volta pro menu antigo, como se eu fosse pra um projeto
sem escritório". Quem abre Quantitativo, Financeiro, Cronograma... PELO Escritório continua no menu dele.

A escritorio.html grava a marca (sessionStorage 'aiarq_esc_ctx') e o menu-lateral.js lê. As travas:
  • só vale pro MESMO job da URL (o projeto fixado continua morando na URL — decisão de 04/08);
  • o id vai pra um href: só UUID passa;
  • o nome entra por textContent, nunca como HTML;
  • o painel da conta (sem projeto fixado) apaga a marca.
"""
import os
import re

RAIZ = os.path.join(os.path.dirname(__file__), "..", "..")


def _ler(nome):
    with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
        return f.read()


def _bloco_esc(js):
    i = js.index("var ESC = (function () {")
    return js[i:js.index("})();", i)]


def test_escritorio_grava_a_marca_com_o_job_e_o_id_do_projeto():
    h = _ler("escritorio.html")
    i = h.index("function marcarContexto() {")
    f = h[i:h.index("\n}\n", i)]
    assert "sessionStorage.setItem('aiarq_esc_ctx'" in f
    assert "job: PROJ.job_id, id: PROJ.id" in f
    assert "removeItem('aiarq_esc_ctx')" in f, "projeto sem medido ligado precisa apagar a marca velha"
    r = h.index("function render() {")
    assert "marcarContexto();" in h[r:r + 200]


def test_menu_so_vira_escritorio_pro_mesmo_job_e_com_id_uuid():
    b = _bloco_esc(_ler("menu-lateral.js"))
    assert "c.job === JOB" in b, "sem isto, a marca de um projeto mudaria o menu de OUTRO"
    m = re.search(r"/\^\[0-9a-f\]\{8\}-.*?\$/i\.test\(c\.id", b)
    assert m, "o id vai pra um href: só UUID pode passar"
    assert "if (!FIXADO) { sessionStorage.removeItem('aiarq_esc_ctx')" in b, "o painel da conta volta limpo"


def test_nome_do_projeto_entra_como_texto():
    js = _ler("menu-lateral.js")
    i = js.index("if (ESC) {                         // nome e resumo")
    trecho = js[i:i + 500]
    assert "escNome.textContent = " in trecho and "escSub.textContent = " in trecho
    assert "ESC.nome" not in js[:js.index("side.innerHTML =")] + js[js.index("side.innerHTML ="):i], \
        "o nome não pode entrar na string HTML do menu"


def test_grupos_do_escritorio_apontam_pras_telas_dele_e_pras_do_medido():
    js = _ler("menu-lateral.js")
    i = js.index("function gruposEscritorio() {")
    f = js[i:js.index("\n  }\n", i)]
    for tela in ("capa", "tarefas", "arquivos", "atas", "equipe"):
        assert "e + '" + tela + "'" in f
    assert "gruposProjeto()[0].itens.filter(function (it) { return !!it.chave; })" in f
    assert "var GRUPOS = FIXADO ? (ESC ? gruposEscritorio() : gruposProjeto()) : GRUPOS_CONTA;" in js

# 25/09, 2ª parte (Pedro: "faz o que achar mais lógico"): o menu vira o do Escritório SEMPRE que o projeto
# medido está ligado a um — não só quando a pessoa veio de lá nesta aba.
def _funcao_js(js, cabeca):
    i = js.index(cabeca)
    return js[i:js.index("\n  }\n", i)]


def test_aplicar_escritorio_so_aceita_uuid_e_poe_o_nome_como_texto():
    f = _funcao_js(_ler("menu-lateral.js"), "function aplicarEscritorio(c) {")
    assert re.search(r"/\^\[0-9a-f\]\{8\}-.*?\$/i\.test\(c\.id", f), "o id vai pra um href: só UUID"
    assert "nm.textContent = ESC.nome" in f and "innerHTML" not in f
    assert "if (SO_LEITURA) tirarItensDoDono();" in f, "a equipe não pode ganhar de volta Revisão/Financeiro"


def test_descobrir_so_roda_depois_de_saber_que_o_projeto_e_da_pessoa():
    js = _ler("menu-lateral.js")
    i = js.index("function atualizarSelo() {")
    sel = js[i:js.index("\n  }\n", i)]
    # a consulta mora DEPOIS da confirmação de que o job está em /api/meus-entregaveis desta conta
    assert sel.index("if (!p) {") < sel.index("descobrirEscritorio();")
    d = _funcao_js(js, "function descobrirEscritorio() {")
    assert ".from('escritorio_projetos')" in d and ".eq('job_id', JOB)" in d


def test_equipe_vira_o_menu_do_escritorio_pelo_acesso():
    f = _funcao_js(_ler("menu-lateral.js"), "function montarEquipe() {")
    assert "if (a.escritorio_id) aplicarEscritorio(" in f


def test_o_grupo_antigo_nao_aparece_depois_da_troca():
    f = _funcao_js(_ler("menu-lateral.js"), "function montarEscritorio(uid) {")
    assert "if (!ok || ESC) return;" in f


def test_o_menu_da_propria_tela_do_escritorio_tambem_mostra_quantitativo_e_obra():
    # 26/09 — Pedro: "passo pra Equipe e o Quantitativo, Memorial… tudo some"
    h = _ler("escritorio.html")
    i = h.index("function renderMoldura() {")
    f = h[i:h.index("\n}\n", i)]
    assert "const obra = PROJ.job_id ?" in f and "${obra}" in f
    for href in ("projeto.html?job_id=${J}#quantitativo", "cronograma.html?job_id=${J}", "memorial.html?job_id=${J}"):
        assert href in f
    # o que é do dono fica atrás do souAdmin(), como no menu-lateral.js
    for href in ("revisao.html?job_id=${J}", "financeiro.html?job_id=${J}", "projeto.html?job_id=${J}#cotacoes"):
        assert "souAdmin() ? fora(`" + href in f, href

# controle positivo (25/09): tirar "c.job === JOB && " do menu-lateral.js reprovou o 2º teste.
