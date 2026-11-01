# -*- coding: utf-8 -*-
"""A prancha de PDF cortada no teto de tokens é lida de novo com o teto dobrado.

🩸 01/11/2026 (job 01e6bfad): 5 de 5 pranchas bateram nos 16000 tokens. A entrada
era idêntica entre as rodadas e a saída não (250 × 254 linhas): cada uma cortava
em outro ponto, e leitura cortada não vai pro cache.

🔑 LEITURA_CORTADA_RELE_MAIOR=1 relê só a prancha cortada; com 0 o motor só conta.
O risco é pagar duas vezes por prancha sem corte, ou perder a 1ª leitura quando a
releitura falha.
"""
import ast
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import analyzer  # noqa: E402
import main  # noqa: E402
from analyzer import SheetType  # noqa: E402


def _texto(n):
    corpo = {"items": [{"item_num": str(i), "description": "Linha %d" % i, "unit": "un",
                        "quantity": 1, "confidence": "estimado"} for i in range(n)],
             "project_data": {}}
    return "Raciocínio.\n```json\n%s\n```" % json.dumps(corpo, ensure_ascii=False)


class _Resp:
    def __init__(self, texto, stop_reason="end_turn"):
        class _B:
            text = texto
        self.content = [_B()]
        self.stop_reason = stop_reason


class _Sheet:
    def __init__(self):
        self.text_content = ""
        self.crops = []
        self.sheet_type = SheetType.ARQUITETURA
        self.filename = "prancha.pdf"


def _roda(monkeypatch, respostas, **kw):
    fila, chamadas = list(respostas), []

    def _ia(*a, **k):
        chamadas.append(k)
        r = fila.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(analyzer, "call_with_retry_stream", _ia)
    return analyzer.analyze_sheet(None, _Sheet(), **kw), chamadas


def _cortada(n=3):
    return _Resp(_texto(n), "max_tokens")


def test_sem_a_chave_a_cortada_fica_como_esta(monkeypatch):
    out, ch = _roda(monkeypatch, [_cortada()])
    assert len(ch) == 1 and out["_truncated"] and "_teto_maior" not in out


def test_com_a_chave_a_cortada_le_de_novo_com_o_teto_dobrado(monkeypatch):
    out, ch = _roda(monkeypatch, [_cortada(), _Resp(_texto(8))], reler_cortada=True)
    assert [c["max_tokens"] for c in ch] == [16000, 32000]
    assert ch[0]["messages"] == ch[1]["messages"]
    assert ch[1]["tag"].endswith("#teto-maior")
    assert len(out["items"]) == 8 and "_truncated" not in out
    assert out["_teto_maior"] == {"antes": 3, "depois": 8, "ainda_cortada": False}


def test_prancha_sem_corte_nao_paga_a_segunda_leitura(monkeypatch):
    out, ch = _roda(monkeypatch, [_Resp(_texto(3))], reler_cortada=True)
    assert len(ch) == 1 and "_teto_maior" not in out


def test_releitura_ainda_cortada_segue_avisando(monkeypatch):
    out, _ = _roda(monkeypatch, [_cortada(), _cortada(8)], reler_cortada=True)
    assert len(out["items"]) == 8 and out["_truncated"]
    assert out["_teto_maior"]["ainda_cortada"] is True


def test_releitura_completa_vence_mesmo_com_menos_linhas(monkeypatch):
    # job evd8dc53: a 5ª prancha terminou com 66 itens, e a cortada tinha 76
    out, _ = _roda(monkeypatch, [_cortada(5), _Resp(_texto(2))], reler_cortada=True)
    assert len(out["items"]) == 2 and "_truncated" not in out
    assert out["_teto_maior"] == {"antes": 5, "depois": 2, "ainda_cortada": False}


def test_releitura_cortada_com_menos_linhas_nao_troca_a_primeira(monkeypatch):
    out, _ = _roda(monkeypatch, [_cortada(5), _cortada(2)], reler_cortada=True)
    assert len(out["items"]) == 5 and out["_truncated"]
    assert out["_teto_maior"]["depois"] == 2


def test_releitura_completa_e_vazia_nao_apaga_a_primeira(monkeypatch):
    out, _ = _roda(monkeypatch, [_cortada(5), _Resp(_texto(0))], reler_cortada=True)
    assert len(out["items"]) == 5 and out["_truncated"]


def test_releitura_que_falha_preserva_a_primeira(monkeypatch):
    out, _ = _roda(monkeypatch, [_cortada(), RuntimeError("boom")], reler_cortada=True)
    assert len(out["items"]) == 3 and out["_truncated"] and not out.get("error")
    assert "boom" in out["_teto_maior"]["falhou"]


def test_reprocesso_nao_le_a_releitura_do_cache(monkeypatch):
    _, ch = _roda(monkeypatch, [_cortada(), _Resp(_texto(8))],
                  reler_cortada=True, usa_cache=False)
    assert [c["cache"] for c in ch] == [False, False]


def _logs(monkeypatch):
    logs = []
    monkeypatch.setattr(main, "_log_error",
                        lambda st, msg, j=None, severity="error": logs.append((st, msg, severity)))
    return logs


def test_a_prancha_cortada_e_contada_com_a_chave_em_0(monkeypatch):
    logs = _logs(monkeypatch)
    main._registra_leitura_cortada({"_truncated": True}, "p1", "j")
    assert logs == [("motor:leitura-cortada",
                     "arq=p1 releu=0 antes=None depois=None ainda_cortada=1", "info")]


def test_a_releitura_que_completou_e_registrada(monkeypatch):
    logs = _logs(monkeypatch)
    main._registra_leitura_cortada({"_teto_maior": {"antes": 3, "depois": 8}}, "p1", "j")
    assert logs[0][1] == "arq=p1 releu=1 antes=3 depois=8 ainda_cortada=0"


def test_a_falha_da_releitura_aparece_no_registro(monkeypatch):
    logs = _logs(monkeypatch)
    main._registra_leitura_cortada({"_truncated": True, "_teto_maior": {
        "antes": 3, "depois": 0, "falhou": "RuntimeError: boom"}}, "p1", "j")
    assert logs[0][1].endswith("falhou=RuntimeError: boom")


def test_leitura_sem_corte_nao_registra_nada(monkeypatch):
    logs = _logs(monkeypatch)
    main._registra_leitura_cortada({"items": []}, "p1", "j")
    assert logs == []


@pytest.mark.parametrize("valor,liga", [("1", True), ("0", False)])
def test_a_chave_vem_do_job(monkeypatch, valor, liga):
    monkeypatch.setattr(main, "_chave_do_job", lambda j, n, p="0": valor if n == "LEITURA_CORTADA_RELE_MAIOR" else "x")
    assert main._liga_releitura_cortada("j") is liga


def test_a_chave_nasce_em_0_e_e_avaliavel():
    assert "LEITURA_CORTADA_RELE_MAIOR" in main._CHAVES_AVALIAVEIS
    assert "motor:leitura-cortada" in main._STAGES_DIAGNOSTICO
    assert main._liga_releitura_cortada("job-sem-avaliacao") is False


def test_o_laco_do_pdf_passa_a_chave_e_registra():
    with open(os.path.join(os.path.dirname(__file__), "..", "main.py"), encoding="utf-8") as f:
        arvore = ast.parse(f.read())
    chamada = [n for n in ast.walk(arvore) if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Name) and n.func.id == "analyze_sheet"]
    assert len(chamada) == 1
    valor = [k.value for k in chamada[0].keywords if k.arg == "reler_cortada"]
    assert len(valor) == 1 and isinstance(valor[0], ast.Call), (
        "o laço do PDF não pergunta à chave se relê a prancha cortada")
    assert valor[0].func.id == "_liga_releitura_cortada"
    assert [a.id for a in valor[0].args] == ["job_id"]
    registra = [n for n in ast.walk(arvore) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name) and n.func.id == "_registra_leitura_cortada"]
    assert len(registra) == 1
