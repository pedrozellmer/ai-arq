# -*- coding: utf-8 -*-
"""A página diz por que há linhas em branco e quais são os caminhos.

🩸 30/10/2026 — PDA Moema, 10 DWG, 332 de 378 linhas em branco, nota 2: "faltou eu
saber como usar direito e informar alguns caminhos com mais clareza". A causa era
nossa: a planta inteira num bloco só (`GPA-…-BASE-TER`, 233.844 entidades, 1
inserção), que o motor não lê. Nada na tela explicava isso.
📏 60 dias: 30 projetos com 60%+ das linhas em branco, 13% agiram na revisão.

🚫 O bloco NÃO é aberto: é a base repetida em toda prancha. Abrir mediria o prédio
(115 km de linhas) no lugar do escopo (62 m). O motor só avisa.
🚨 Os guardas rodam o detector num DXF de verdade e o JS real no motor JS.
"""
import json
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import dwg_extractor as _dx  # noqa: E402
import main  # noqa: E402
from _jsbancada import fonte_html, funcao_js, motor  # noqa: E402

NL = chr(10)


# ── o detector ────────────────────────────────────────────────────────────
def _doc(n_no_bloco, soltas=0, nome="BASE-TER"):
    doc = ezdxf.new()
    bl = doc.blocks.new(nome)
    for i in range(n_no_bloco):
        bl.add_line((i, 0), (i, 1))
    msp = doc.modelspace()
    msp.add_blockref(nome, (0, 0))
    for i in range(soltas):
        msp.add_line((i, 5), (i, 6))
    return doc


def test_o_caso_a_planta_inteira_num_bloco_e_reconhecida():
    r = _dx.planta_dentro_de_bloco(_doc(6000))
    assert r == {"bloco": "BASE-TER", "entidades": 6000, "soltas": 0}


def test_conta_o_que_esta_nos_blocos_de_dentro():
    doc = ezdxf.new()
    fora, dentro = doc.blocks.new("FORA"), doc.blocks.new("DENTRO")
    for i in range(6000):
        dentro.add_line((i, 0), (i, 1))
    fora.add_blockref("DENTRO", (0, 0))
    doc.modelspace().add_blockref("FORA", (0, 0))
    assert _dx.planta_dentro_de_bloco(doc)["entidades"] == 6000


def test_CONTROLE_bloco_pequeno_nao_e_a_planta():
    assert _dx.planta_dentro_de_bloco(_doc(4999)) == {}


def test_CONTROLE_desenho_solto_no_modelo_nao_avisa():
    # base em bloco + obra desenhada solta: o motor mede a obra
    assert _dx.planta_dentro_de_bloco(_doc(6000, soltas=200)) == {}


def test_a_razao_tem_borda():
    assert _dx.planta_dentro_de_bloco(_doc(6000, soltas=120))
    assert not _dx.planta_dentro_de_bloco(_doc(6000, soltas=121))


def test_cota_e_texto_soltos_nao_contam_como_desenho():
    doc = _doc(6000)
    for i in range(300):
        doc.modelspace().add_text("x", dxfattribs={"insert": (i, 9)})
    assert _dx.planta_dentro_de_bloco(doc)


def test_bloco_que_se_referencia_nao_trava():
    doc = ezdxf.new()
    a = doc.blocks.new("A")
    b = doc.blocks.new("B")
    a.add_blockref("B", (0, 0))
    b.add_blockref("A", (0, 0))
    doc.modelspace().add_blockref("A", (0, 0))
    assert _dx.planta_dentro_de_bloco(doc) == {}


def test_a_chave_nao_sai_crua_no_prompt():
    assert "planta_em_bloco" in _dx.DXFExtraction._METADADOS_FORA_DO_PROMPT


# ── o aviso ───────────────────────────────────────────────────────────────
def test_o_aviso_diz_quantas_pranchas_e_o_que_fazer():
    arqs = [{"nome": "ARQ100", "planta_em_bloco": {"bloco": "B"}},
            {"nome": "ARQ090", "planta_em_bloco": {"bloco": "B"}}, {"nome": "ARQ301"}]
    linhas = main._linhas_planta_em_bloco(arqs)
    assert len(linhas) == 1 and linhas[0].startswith(main.MARCA_PLANTA_EM_BLOCO)
    assert "2 de 3 prancha(s)" in linhas[0] and "ARQ100, ARQ090" in linhas[0]
    assert "solt" in linhas[0]


def test_CONTROLE_sem_o_caso_nao_ha_aviso():
    assert main._linhas_planta_em_bloco([{"nome": "A"}]) == []
    assert main._linhas_planta_em_bloco([]) == []


def test_lista_longa_e_cortada():
    arqs = [{"nome": "P%d" % i, "planta_em_bloco": {"b": 1}} for i in range(6)]
    assert "P3 e mais 2" in main._linhas_planta_em_bloco(arqs)[0]


def test_o_aviso_entra_junto_do_das_pranchas():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        src = f.read()
    assert "_linhas_esc += _linhas_planta_em_bloco(_escala_arqs)" in src
    assert '_res_esc["planta_em_bloco"] = _md_u["planta_em_bloco"]' in src


def test_o_evento_e_aceito_no_track():
    assert main._track_evento_aceito("caminhos:exibido")
    for acao in ("revisao", "novo", "chat", "area", "pd", "cad"):
        assert main._track_evento_aceito("clique:caminho-" + acao)


# ── o cartão ──────────────────────────────────────────────────────────────
_SRC = fonte_html("projeto.html")
_JS = NL.join([
    "var _CAMINHOS_MIN_LINHAS = 5; var _CAMINHOS_MIN_FRACAO = 0.30;",
    "var _MARCA_PLANTA_EM_BLOCO = 'A PLANTA ESTÁ DENTRO DE UM BLOCO';",
    funcao_js("caminhosDasLinhasEmBranco", "projeto.html", _SRC),
])


def _c(vazias=6, cheias=4, status="done", warnings=(), **vis):
    js = motor(_JS)
    itens = [{"quantity": 0}] * vazias + [{"quantity": 2}] * cheias
    proj = {"status": status, "warnings": list(warnings)}
    r = js.evaljs("JSON.stringify(caminhosDasLinhasEmBranco(%s, %s, %s))" % (
        json.dumps(proj), json.dumps(itens),
        json.dumps({"area": vis.get("area", False), "pd": vis.get("pd", False),
                    "cad": vis.get("cad", False)})))
    return json.loads(r) if r else None


_AVISO = "⚠ A PLANTA ESTÁ DENTRO DE UM BLOCO — em 8 de 10 prancha(s)"


def _acoes(r):
    return [c["acao"] for c in r["caminhos"]]


def test_a_marca_da_tela_e_a_do_motor():
    assert "A PLANTA ESTÁ DENTRO DE UM BLOCO" in main.MARCA_PLANTA_EM_BLOCO
    assert "_MARCA_PLANTA_EM_BLOCO = 'A PLANTA ESTÁ DENTRO DE UM BLOCO'" in _SRC


def test_o_caso_planta_em_bloco():
    r = _c(332, 46, warnings=[_AVISO])
    assert r["caso"] == "bloco" and r["titulo"] == "Por que 332 linhas ficaram em branco"
    assert _acoes(r) == ["novo", "revisao", "chat"] and r["caminhos"][0]["forte"]
    assert "Não foi nada que você fez de errado" in r["porque"]


def test_so_pdf_o_cad_vem_primeiro():
    r = _c(cad=True, area=True)
    assert r["caso"] == "pdf" and _acoes(r) == ["cad", "area", "revisao"]
    assert r["caminhos"][0]["forte"]


def test_so_pdf_sem_o_convite_da_area_nao_oferece_area():
    assert _acoes(_c(cad=True)) == ["cad", "revisao"]


def test_faltou_dado_area_e_pe_direito():
    r = _c(area=True, pd=True)
    assert r["caso"] == "dados" and _acoes(r) == ["area", "pd", "revisao"]
    assert r["caminhos"][0].get("forte") and not r["caminhos"][1].get("forte")


def test_sem_convite_o_forte_e_a_revisao():
    r = _c()
    assert _acoes(r) == ["revisao"] and r["caminhos"][0]["forte"]


def test_so_o_pe_direito():
    r = _c(pd=True)
    assert _acoes(r) == ["pd", "revisao"] and r["caminhos"][0]["forte"]


def test_o_bloco_ganha_do_pdf():
    assert _c(warnings=[_AVISO], cad=True)["caso"] == "bloco"


@pytest.mark.parametrize("vazias,cheias", [(4, 0), (5, 12), (0, 10)])
def test_CONTROLE_poucas_em_branco_nao_mostra(vazias, cheias):
    assert _c(vazias, cheias) is None


@pytest.mark.parametrize("vazias,cheias", [(5, 0), (6, 14), (3 * 3, 21)])
def test_borda_de_30_por_cento_mostra(vazias, cheias):
    assert _c(vazias, cheias) is not None


@pytest.mark.parametrize("status", ["processing", "error", "queued"])
def test_CONTROLE_so_em_projeto_pronto(status):
    assert _c(status=status) is None


def test_CONTROLE_sem_linhas_nao_mostra():
    assert _c(0, 0) is None


def _js_tela(extra=""):
    return motor(NL.join([
        "var jobId = 'j1'; var window = {location: {href: ''}};",
        "var __vista = []; function mostrarVista(v) { __vista.push(v); }",
        "var __el = {}; function __e(id) { return __el[id] || (__el[id] = {id: id, tagName:"
        " id.slice(-5) === 'input' ? 'INPUT' : 'DIV', rolou: 0, focou: 0, hiddenCls: false,"
        " scrollIntoView: function () { this.rolou++; }, focus: function () { this.focou++; }}); }",
        "var document = {getElementById: __e};",
        extra,
        funcao_js("executarCaminho", "projeto.html", _SRC),
        "1;",
    ]))


def test_revisao_leva_pra_tela_de_revisao():
    js = _js_tela()
    js.evaljs("executarCaminho('revisao'); 1;")
    assert js.evaljs("window.location.href") == "revisao.html?job_id=j1"


def test_novo_leva_pro_painel():
    js = _js_tela()
    js.evaljs("executarCaminho('novo'); 1;")
    assert js.evaljs("window.location.href") == "dashboard.html"


def test_chat_abre_a_vista_e_rola():
    js = _js_tela()
    js.evaljs("executarCaminho('chat'); 1;")
    assert js.evaljs("__vista[0]") == "quantitativo"
    assert js.evaljs("__el['chat-quant'].rolou") == 1


@pytest.mark.parametrize("acao,alvo,focou", [("area", "area-input", 1), ("pd", "pd-input", 1),
                                             ("cad", "cad-upgrade-banner", 0)])
def test_os_atalhos_vao_pros_convites_que_ja_existem(acao, alvo, focou):
    js = _js_tela()
    js.evaljs("executarCaminho('%s'); 1;" % acao)
    assert js.evaljs("__el['%s'].rolou" % alvo) == 1
    assert js.evaljs("__el['%s'].focou" % alvo) == focou


def test_os_alvos_existem_na_pagina():
    for alvo in ("area-input", "pd-input", "cad-upgrade-banner", "chat-quant", "caminhos-card",
                 "caminhos-titulo", "caminhos-porque", "caminhos-lista"):
        assert 'id="%s"' % alvo in _SRC, alvo


def test_o_clique_fica_registrado():
    js = _js_tela("var __ev = []; window.trackEvent = function (n, m) { __ev.push(n + '|' + m.job_id); };"
                  "var trackEvent = window.trackEvent;")
    js.evaljs("executarCaminho('novo'); 1;")
    assert js.evaljs("__ev[0]") == "clique:caminho-novo|j1"


def test_quem_so_le_o_projeto_nao_ve_o_cartao():
    assert ".so-leitura #caminhos-card" in _SRC


def test_o_cartao_esta_na_ordem_da_pagina_e_depois_dos_convites():
    assert "'caminhos-card'," in _SRC
    i = _SRC.index("safeRun(() => renderCaminhos(proj, items)")
    assert _SRC.index("safeRun(() => maybeShowPeDireitoPrompt(proj, items)") < i
    assert _SRC.index("safeRun(() => maybeShowAreaPrompt(proj, items)") < i
    assert _SRC.index("safeRun(() => renderMetrics(proj, items)") < i
