# -*- coding: utf-8 -*-
"""Import que ninguém chama é o sintoma de um LADO MORTO — e ele grita antes.

🩸 09/09/2026. Três defeitos de produção deste dia nasceram da MESMA armação:
uma função que o `main.py` **importava e nunca chamava**, com consertos dentro
que a produção nunca recebeu:

  · o marcador de página no `ref_sheet` — **0 de 12.818 itens em 4 meses**
  · `confirmado + 0` virando `qty = 1` com selo de MEDIDO — 14 dias no ar
  · o conselho "reprocessar", aposentado em 24/08 e ainda saindo pro PDF

Em todos, o guarda ficou VERDE porque testava a função morta. Em um deles o
docstring do próprio guarda confessava: *"na 1ª versão chamei `analyze_sheet` e
os testes reprovaram sozinhos; quem saneia é `analyze_all_sheets`"* — o guarda
foi MOVIDO até onde ele passava.

🔑 E havia um sinal barato, visível o tempo todo, 4 meses antes: **a linha de
import**. `from analyzer import analyze_all_sheets` estava lá, sozinha, sem uma
única chamada no arquivo. Este guarda transforma esse sinal em alarme.

🚫 Não é caça a código morto em geral (isso é caro e dá falso positivo). É uma
pergunta estreita e barata: *o `main.py` importa nome que ele nunca usa?*
"""
import ast
import io
import os

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)

#: 🪤 Import cujo VALOR é o efeito colateral de importar, não o nome. Aqui
#: entra só o que for justificado por escrito — cada linha desta lista é uma
#: exceção que alguém vai ler daqui a meses.
_EFEITO_COLATERAL = {
    # (nome importado, por que não é chamado pelo nome)
    "router",              # routers de FastAPI entram via include_router(...)
    "instagram_router",
    "whatsapp_router",
}


def _arvore(nome):
    return ast.parse(io.open(os.path.join(_BACKEND, nome),
                             encoding="utf-8").read())


def _importados_de_modulo_nosso(arvore, modulos):
    """[(modulo, nome_local)] dos `from <nosso> import X` no topo do arquivo."""
    fora = []
    for n in ast.walk(arvore):
        if not isinstance(n, ast.ImportFrom) or not n.module:
            continue
        if n.module.split(".")[0] not in modulos:
            continue
        for a in n.names:
            if a.name == "*":
                continue
            fora.append((n.module, a.asname or a.name, n.lineno))
    return fora


def _nomes_usados(arvore, ignorar_linhas):
    """Todo Name/Attribute usado no arquivo, FORA das linhas de import."""
    usados = set()
    for n in ast.walk(arvore):
        if getattr(n, "lineno", None) in ignorar_linhas:
            continue
        if isinstance(n, ast.Name):
            usados.add(n.id)
        elif isinstance(n, ast.Attribute):
            usados.add(n.attr)
    return usados


_MODULOS_NOSSOS = {
    "analyzer", "processor", "spreadsheet", "consolidator", "engine_rules",
    "dwg_extractor", "structural_extractor", "pdf_vector", "pdfvec_views",
    "pdfvec_rooms", "pdfvec_walls", "pdfvec_cotas", "pdfvec_carimbo",
    "pdfvec_layers", "pdfvec_escala_por_vista", "cronograma", "memorial",
    "revision_feedback", "density", "cashback", "llm_retry", "llm_cache",
    "sinapi_matcher", "spec_extract", "models", "pdf_seguro",
}


def test_main_nao_importa_o_que_nao_chama():
    """🩸 O guarda que teria pegado a `analyze_all_sheets` em ABRIL."""
    arv = _arvore("main.py")
    imports = _importados_de_modulo_nosso(arv, _MODULOS_NOSSOS)
    assert imports, "não achei import nenhum de módulo nosso — a peneira quebrou"
    linhas_de_import = {ln for _m, _n, ln in imports}
    usados = _nomes_usados(arv, linhas_de_import)
    orfaos = [(m, n, ln) for m, n, ln in imports
              if n not in usados and n not in _EFEITO_COLATERAL]
    assert not orfaos, (
        "o main.py IMPORTA e NUNCA USA: %s\n"
        "Isso é o sintoma de um LADO MORTO — em 09/09 três defeitos vieram de "
        "uma função importada e nunca chamada, com consertos dentro que a "
        "produção nunca recebeu. Apague o import; se a função também estiver "
        "morta, apague a função."
        % [("%s.%s" % (m, n), "linha %d" % ln) for m, n, ln in orfaos])


def test_a_lista_de_EXCECAO_nao_pode_engordar():
    """🪤 A MUTAÇÃO PEGOU ESTE BURACO: dava pra calar o guarda inteiro só
    acrescentando o nome órfão a `_EFEITO_COLATERAL`.

    É o caminho mais fácil e o pior — apagar a defesa pra calar o alarme, em
    vez de tirar o import morto. Aqui a saída fica cara: a exceção só vale pra
    import cujo valor É o efeito colateral, e hoje isso significa ROUTER de
    FastAPI (entra por `include_router`, nunca pelo nome).
    """
    assert len(_EFEITO_COLATERAL) <= 5, (
        "a lista de exceção cresceu pra %d. Cada nome aqui é um import que o "
        "guarda deixa de vigiar — foi por um import não vigiado que três "
        "defeitos passaram 4 meses." % len(_EFEITO_COLATERAL))
    for nome in _EFEITO_COLATERAL:
        assert nome.endswith("router"), (
            "%r entrou na exceção sem ser router. Import que não é efeito "
            "colateral e ninguém chama é import MORTO: apague o import, não "
            "o alarme." % nome)


def test_CONTROLE_a_peneira_ACHA_um_import_orfao_plantado(tmp_path):
    """🧪 Sem isto, uma peneira que devolvesse lista vazia passaria sempre."""
    p = tmp_path / "falso.py"
    p.write_text("from analyzer import monta_ref_sheet, coisa_morta\n"
                 "x = monta_ref_sheet('a', 0, 1, '')\n", encoding="utf-8")
    arv = ast.parse(p.read_text(encoding="utf-8"))
    imports = _importados_de_modulo_nosso(arv, _MODULOS_NOSSOS)
    usados = _nomes_usados(arv, {ln for _m, _n, ln in imports})
    orfaos = [n for _m, n, _ln in imports if n not in usados]
    assert orfaos == ["coisa_morta"], orfaos


def test_CONTROLE_a_peneira_NAO_acusa_import_que_e_usado(tmp_path):
    """🧪 O outro lado: uma peneira que acusasse tudo faria alguém desligá-la."""
    p = tmp_path / "ok.py"
    p.write_text("from engine_rules import retrato_do_selo\n"
                 "y = retrato_do_selo([])\n", encoding="utf-8")
    arv = ast.parse(p.read_text(encoding="utf-8"))
    imports = _importados_de_modulo_nosso(arv, _MODULOS_NOSSOS)
    usados = _nomes_usados(arv, {ln for _m, _n, ln in imports})
    assert not [n for _m, n, _ln in imports if n not in usados]


def test_a_funcao_MORTA_nao_voltou():
    """🪦 `analyze_all_sheets` foi apagada em 09/09 com motivo escrito no lugar.

    🚫 Ressuscitar significa ter DOIS laços de item outra vez, e foi disso que
    saíram os três defeitos do dia. Se alguém precisar dela de volta, que seja
    uma decisão consciente que apague este teste junto — não um `git revert`
    silencioso.
    """
    import analyzer
    assert not hasattr(analyzer, "analyze_all_sheets"), (
        "a `analyze_all_sheets` voltou. Ela era o LADO MORTO de uma cópia "
        "dupla do laço de item: o main.py importava e nunca chamava, e os "
        "consertos caíam nela em vez de na produção.")
    fonte = io.open(os.path.join(_BACKEND, "analyzer.py"), encoding="utf-8").read()
    assert "FOI APAGADA AQUI" in fonte, (
        "sumiu o comentário que explica por que ela foi apagada — sem ele, "
        "o próximo leitor só vê uma ausência e a recria")


@pytest.mark.parametrize("nome", ["sanear_qtd_e_selo", "monta_ref_sheet"])
def test_as_reguas_que_sobraram_dela_CONTINUAM_vivas(nome):
    """🔑 O que ela tinha de útil virou régua chamada pelos dois lados. Apagar
    a função não pode ter levado junto o que a produção usa."""
    import analyzer
    assert hasattr(analyzer, nome), (
        "%s sumiu do analyzer — o main.py chama essa régua" % nome)
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    assert nome in fonte, "o main.py deixou de citar %s" % nome
