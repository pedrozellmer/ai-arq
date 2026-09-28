# -*- coding: utf-8 -*-
"""Erro do servidor não mostra o texto técnico da exceção pra tela (auditoria SI, 27/09/2026).

37 rotas faziam `raise HTTPException(500, f"Erro ao X: {e}")`: o navegador recebia URL interna, caminho de arquivo e
resposta crua do banco. Agora passam por `_erro_interno`, que devolve a frase em português e manda o detalhe pro log.
"""
import os
import re
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

_CRU = re.compile(r'HTTPException\(\s*5\d\d\s*,[^\n]*(\{(?:e|_e|err|exc|ex)(?:!s|!r)?\}|str\((?:e|_e|err|exc|ex)\)|repr\((?:e|_e|err|exc|ex)\))')


def _fonte():
    return open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def test_nenhum_erro_500_do_main_devolve_a_excecao_crua():
    achados = [(i + 1, l.strip()[:90]) for i, l in enumerate(_fonte().splitlines()) if _CRU.search(l)]
    assert not achados, "erro 5xx devolvendo o texto da exceção pra tela: %s" % achados[:5]


def test_o_ajudante_devolve_a_frase_e_esconde_o_detalhe(monkeypatch):
    import main
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    segredo = "https://interno.exemplo/rest/v1/tabela?select=* /tmp/aiarq_jobs/x.dxf"
    exc = main._erro_interno(500, "Erro ao gerar PDF", RuntimeError(segredo))
    assert exc.status_code == 500
    assert "Erro ao gerar PDF" in exc.detail and "Tente de novo" in exc.detail
    assert segredo not in exc.detail and "RuntimeError" not in exc.detail


def test_CONTROLE_o_detalhe_vai_pro_log(monkeypatch, capsys):
    """Esconder da tela não pode virar perder: o detalhe tem que sair no log do servidor."""
    import main
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    main._erro_interno(502, "Storage não respondeu", ValueError("detalhe-que-importa-pro-diagnostico"))
    assert "detalhe-que-importa-pro-diagnostico" in capsys.readouterr().out


def test_CONTROLE_o_guarda_acusa_a_forma_antiga():
    assert _CRU.search('        raise HTTPException(500, f"Erro ao gerar PDF: {e}")')
    assert _CRU.search('        raise HTTPException(502, "Falhou: " + str(e))')
    assert not _CRU.search('        raise _erro_interno(500, "Erro ao gerar PDF", e)')
