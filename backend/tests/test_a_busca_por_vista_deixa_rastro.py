# -*- coding: utf-8 -*-
"""A busca da escala AO LADO DA VISTA deixa rastro no log e na sombra.

🩸 10/09/2026 — reprocesso interno do job 135fdfac: a página saiu "sem escala"
com o carimbo dizendo `indicadas`, que é justamente o gatilho da busca por
vista. O filho calculava `escala_por_vista` e ninguém gravava: não dava pra
saber se a busca recortou as vistas e não leu rótulo, ou se nem achou vista.

Estes guardas CHAMAM `pdf_vector.rastro_da_escala_por_vista`,
`main._saida_do_filho_pdfvec` e o `_run` da sombra de verdade.
"""
import ast
import json
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

_BBOXES_LONGAS = [[round(1000.123 + i, 3), 2000.456, 3000.789, 4000.012] for i in range(12)]


def _rastro(r):
    import pdf_vector
    return pdf_vector.rastro_da_escala_por_vista(r)


def test_o_rastro_curto_diz_quantas_vistas_e_o_que_leu():
    r = {"indicadas": True,
         "escala_por_vista": {"por_vista": [None, 50, None], "n_vistas": 3,
                              "bboxes": _BBOXES_LONGAS[:3]}}
    assert _rastro(r) == {"n": 3, "lidas": [None, 50, None]}


def test_o_rastro_leva_o_erro_da_busca():
    r = {"indicadas": True, "err_escala_vista": "RateLimitError: " + "x" * 400}
    rastro = _rastro(r)
    assert rastro["erro"].startswith("RateLimitError"), rastro
    assert len(rastro["erro"]) <= 120, len(rastro["erro"])


def test_CONTROLE_sem_indicadas_a_busca_nao_rodou_e_nao_ha_rastro():
    assert _rastro({}) is None
    assert _rastro({"indicadas": False, "scale": 50}) is None
    assert _rastro(None) is None


def test_o_log_sem_escala_mostra_o_que_a_vista_achou_ANTES_das_cotas():
    import main
    vm = {"skip": "sem escala (viewport, carimbo nem cota)", "indicadas": True,
          "escala_por_vista": {"por_vista": [None, None], "n_vistas": 2,
                               "bboxes": _BBOXES_LONGAS[:2]},
          "cotas_derivacao": {"votos": 14, "confianca": 0.29}, "secs": 39.9}
    tipo, det = main._saida_do_filho_pdfvec(0, vm)
    assert tipo == "sem_escala"
    assert "vista=n=2 lidas=[None, None]" in det, det
    assert det.index("vista=") < det.index("cotas="), (
        "o rastro da vista tem que vir antes das cotas, que são longas e cortam a linha")
    assert "carimbo=indicadas" in det and "secs=39.9" in det, det
    assert "1000.123" not in det, "as bboxes vazaram pro log"


def test_CONTROLE_sem_busca_o_log_diz_traco():
    import main
    tipo, det = main._saida_do_filho_pdfvec(0, {"skip": "sem escala (viewport, carimbo nem cota)",
                                               "indicadas": False, "secs": 5.0})
    assert tipo == "sem_escala" and "vista=-" in det, det


def test_o_resumo_da_sombra_leva_o_rastro_sem_as_bboxes(monkeypatch, tmp_path):
    from test_sombras_nao_perdem_evidencia import _roda_a_sombra_gorda
    bruto, payload = _roda_a_sombra_gorda(monkeypatch, tmp_path, 1, {
        "file": "p.pdf", "skip": "sem escala (viewport, carimbo nem cota)", "indicadas": True,
        "escala_por_vista": {"por_vista": [None, 75], "n_vistas": 2,
                             "bboxes": _BBOXES_LONGAS[:2]}})
    assert payload["pages"][0].get("escala_por_vista") == {"n": 2, "lidas": [None, 75]}, payload
    assert "1000.123" not in bruto, "as bboxes vazaram pro resumo da sombra"


def test_o_rastro_nao_estoura_o_orcamento_da_coluna(monkeypatch, tmp_path):
    from test_sombras_nao_perdem_evidencia import _roda_a_sombra_gorda
    bruto, payload = _roda_a_sombra_gorda(monkeypatch, tmp_path, 12, {
        "file": "prancha-de-nome-comprido.pdf", "skip": "sem escala (viewport, carimbo nem cota)",
        "indicadas": True, "err_carimbo": "E" * 300,
        "escala_por_vista": {"por_vista": list(range(10, 22)), "n_vistas": 12,
                             "bboxes": _BBOXES_LONGAS}})
    assert len(bruto) <= 2000, len(bruto)
    json.loads(bruto)


def _chama_dentro(arvore, nome_funcao, nome_chamado):
    for n in ast.walk(arvore):
        if isinstance(n, ast.FunctionDef) and n.name == nome_funcao:
            return any(isinstance(c, ast.Call)
                       and (getattr(c.func, "id", None) == nome_chamado
                            or getattr(c.func, "attr", None) == nome_chamado)
                       for c in ast.walk(n))
    raise AssertionError("não achei a função %s" % nome_funcao)


def test_a_forma_curta_e_decidida_num_lugar_so():
    """Os dois consumidores CHAMAM a mesma função. Resumir de novo num deles é o
    lado morto: um muda, o outro fica pra trás."""
    from _corpo import fonte
    assert _chama_dentro(ast.parse(fonte("main.py")), "_saida_do_filho_pdfvec",
                         "rastro_da_escala_por_vista")
    assert _chama_dentro(ast.parse(fonte("pdf_vector.py")), "_run",
                         "rastro_da_escala_por_vista")
