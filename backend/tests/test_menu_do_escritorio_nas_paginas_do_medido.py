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
# controle positivo (25/09): tirar "c.job === JOB && " do menu-lateral.js reprovou o 2º teste.
