# -*- coding: utf-8 -*-
"""O site não manda mais converter DWG em DXF antes de enviar.

🔄 11/10/2026 — remedição de 10/10 (Pedro: caminho A, textos aprovados um a um).
Em 01/08/2026, 61,7% dos DWG enviados (29 de 47) não chegavam ao fim, e o site inteiro pedia DXF: "DXF é o
melhor", "o DXF é o que mede melhor", "(DXF de preferência)", e um lembrete âmbar no painel pra quem escolhia um
DWG — "exporte suas pranchas em DXF antes de subir". Nos 30 dias até 10/10 foram 7 em 70 (10,0%), e o DWG que
concluiu saiu com 21,4% das linhas medidas contra 14,0% do DXF (amostra de DXF pequena: 8 envios).

O que o site diz agora: mande o CAD, DWG ou DXF; se o DWG voltar com erro, salve em DXF e envie de novo.
O DXF continua sendo a SAÍDA quando o DWG não abre — as receitas de erro que mandam salvar em DXF ficam.

🪤 A home ficou um push inteiro com os números novos na caixa e a amostra velha no título ("154 projetos: 101 em
CAD, 53 só PDF"): a guarda dos números cobra os percentuais, não o tamanho da base. Este arquivo cobra.
"""
import io
import json
import os
import re

import dukpy

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# frases que diziam "prefira DXF" — como estavam no fonte de cada lugar
APOSENTADAS = (
    "DXF &eacute; o melhor", "DXF é o melhor", "DXF</b> &eacute; o melhor",
    "o DXF &eacute; o que mede melhor", "O DXF é o que mede melhor", "DXF é o que a gente mede melhor",
    # 🪤 o texto novo é "🥇 DWG ou DXF (recomendado)": a frase vigiada leva a medalha colada, senão pega o novo
    "mande DXF</b>", "🥇 DXF (recomendado)", "DXF d&aacute; o melhor resultado",
    "exporte suas pranchas em DXF antes de subir", "O DXF costuma medir mais", "DXF costuma resolver",
    "(DXF de preferência)", "DXF é o formato que dá o melhor resultado", "formato que a gente mede melhor",
    "formato que a gente lê melhor", "DXF quando der; DWG também serve", "exportar o DXF muda o jogo",
    # 11/10/2026: o hero da home dizia "Sobe DXF, DWG ou PDF" com só o DXF em negrito — não é frase de
    # preferência, mas dá o mesmo recado; passou pela 1ª varredura por isso
    "Sobe <strong>DXF</strong>",
)
ONDE = ("index.html", "dashboard.html", "faq.html", "precos.html", "llms.txt", "aiarq-utils.js",
        os.path.join("blog", "gerar_llms.py"), os.path.join("blog", "posts.json"), os.path.join("backend", "main.py"))


def _ler(rel):
    return io.open(os.path.join(_RAIZ, rel), encoding="utf-8").read()


def _aposentadas_em(texto):
    return [f for f in APOSENTADAS if f in texto]


def test_nenhuma_pagina_voltou_a_pedir_dxf_no_lugar_do_dwg():
    achados = ["%s: %s" % (rel, f) for rel in ONDE for f in _aposentadas_em(_ler(rel))]
    assert achados == [], "frase de 'prefira DXF' voltou: " + " | ".join(achados)


def test_CONTROLE_as_frases_antigas_reprovam():
    antiga_da_home = ("Mande <strong>DXF</strong> sempre que puder (ou DWG) &mdash; o DXF &eacute; o que mede melhor "
                      "e n&atilde;o passa pela convers&atilde;o de DWG")
    assert _aposentadas_em(antiga_da_home) == ["o DXF &eacute; o que mede melhor"]
    assert _aposentadas_em("Sobe seu CAD (DXF de preferência) no AI.arq") == ["(DXF de preferência)"]


def test_CONTROLE_a_guarda_le_os_arquivos():
    for rel in ONDE:
        assert len(_ler(rel)) > 2000, rel


def test_o_dxf_continua_sendo_a_saida_quando_o_dwg_nao_abre():
    """O outro lado: tirar a preferência não é tirar o caminho de volta."""
    assert "salve em DXF e envie de novo" in _ler("index.html")
    assert "salve em DXF e envie de novo" in _ler("faq.html")
    assert "salve em <b>DXF</b> e envie de novo" in _ler("dashboard.html")
    assert "Salve como <b>DXF</b>" in _ler("aiarq-utils.js"), "a receita de erro do DWG que não abre sumiu"


# ── a amostra que a home cita é a da página de dados ─────────────────────────────────────────
def _amostra_da_pagina_de_dados():
    m = re.search(r"(\d+) projetos, [\d.]+ linhas de planilha", _ler("dados.html"))
    assert m, "a página de dados não diz mais o tamanho da amostra"
    return m.group(1)


def _amostras_da_home(texto):
    return sorted(set(re.findall(r"(\d+) projetos[:(]? ?\(?\d+ em CAD", texto)))


def test_a_home_cita_a_mesma_amostra_da_pagina_de_dados():
    assert _amostras_da_home(_ler("index.html")) == [_amostra_da_pagina_de_dados()]


def test_CONTROLE_a_amostra_antiga_ao_lado_da_nova_reprova():
    misturada = ("No nosso beta (154 projetos: 101 em CAD, 53 só PDF) ... "
                 "amostra de 240 projetos (165 em CAD, 75 só PDF), out/2026")
    assert _amostras_da_home(misturada) == ["154", "240"]


# ── o recado da hora de escolher os arquivos, rodando ────────────────────────────────────────
def _rotulo_do_cad(nomes):
    """Roda as três linhas do painel que decidem o rótulo do recado verde."""
    src = _ler("dashboard.html")
    m = re.search(r"const _temDwg = [^\n]+\n\s*const _temDxf = [^\n]+\n\s*const _ROTULO_DO_CAD = [^\n]+", src)
    assert m, "o painel não calcula mais o rótulo do CAD assim — releia o recado da escolha de arquivos"
    arquivos = json.dumps([{"name": n} for n in nomes])
    return dukpy.evaljs("var selectedFiles = %s;\n%s\n(_temDwg || _temDxf) ? _ROTULO_DO_CAD : '';"
                        % (arquivos, m.group(0)))


def test_quem_escolhe_dwg_ganha_o_mesmo_elogio_do_dxf():
    assert _rotulo_do_cad(["planta.dwg"]) == "DWG"
    assert _rotulo_do_cad(["planta.DXF"]) == "DXF"
    assert _rotulo_do_cad(["planta.dwg", "cortes.dxf"]) == "DWG e DXF"
    assert _rotulo_do_cad(["planta.dwg", "pranchas.pdf"]) == "DWG"
    assert _rotulo_do_cad(["pranchas.pdf"]) == "", "só PDF não ganha o recado verde — a ressalva âmbar é dele"


def test_o_recado_verde_usa_o_rotulo_e_o_ambar_ficou_so_com_o_pdf():
    src = _ler("dashboard.html")
    assert "' + _ROTULO_DO_CAD + ' &mdash; &oacute;tima escolha!" in src
    assert "} else if (_temDwg || _temDxf) {" in src
    assert "_semDxf" not in src, "voltou o ramo que tratava DWG como 'não é DXF'"
    assert src.count("bg-amber-50 border border-amber-200 px-4 py-3") >= 1, "a ressalva do só-PDF sumiu"
