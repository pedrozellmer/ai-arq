# -*- coding: utf-8 -*-
"""A leitura guardada do PDF: mesmo arquivo, mesma leitura; reprocesso lê de novo.

🩸 31/10/2026 (jobs edcc6564 e 627413ca): o mesmo PDF de 1 página, enviado com
2 minutos de diferença, deu 24 e 18 linhas. A chave do `llm_cache` acertou no
2º job, mas o modo era SOMBRA: a resposta guardada não foi servida.

🪤 Ao preparar o modo `on`, o caminho do PDF tinha `cache=True` fixo. O DXF já
respeitava `reprocess_count`; o PDF devolveria a mesma leitura a quem clicou
em reprocessar, e a saída de emergência do cliente morreria só neste formato.

🧪 Os guardas rodam `analyze_sheet` e o `call_with_retry_stream` de verdade,
com o modo `on` e só o banco dublado: esse caminho nunca rodou em produção.
"""
import ast
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import analyzer  # noqa: E402
import llm_cache  # noqa: E402
import llm_retry  # noqa: E402
from analyzer import SheetType  # noqa: E402


_ITENS = {"items": [{"item_num": "1", "description": "Condensadora 57.000 BTU/h",
                     "unit": "un", "quantity": 3, "confidence": "estimado"}],
          "project_data": {}}
_LEITURA = "Raciocínio.\n```json\n%s\n```" % json.dumps(_ITENS, ensure_ascii=False)


class _Sheet:
    def __init__(self):
        self.text_content = ""
        self.crops = []
        self.sheet_type = SheetType.ARQUITETURA
        self.filename = "prancha.pdf"


class _RespostaDaIA:
    stop_reason = "end_turn"
    usage = None

    def __init__(self, texto):
        class _Bloco:
            text = texto
        self.content = [_Bloco()]


class _ClienteQueConta:
    """A IA de mentira: conta as chamadas e responde `texto`."""

    def __init__(self, texto=_LEITURA):
        self.chamadas = 0
        self.texto = texto
        self.messages = self

    def stream(self, **kwargs):
        self.chamadas += 1
        resposta = _RespostaDaIA(self.texto)

        class _Ctx:
            def __enter__(s):
                return s

            def __exit__(s, *a):
                return False

            def get_final_message(s):
                return resposta
        return _Ctx()


@pytest.fixture
def modo_on(monkeypatch):
    """Modo `on` real; só o banco e a telemetria de uso são dublados."""
    guardado = {}
    usos = []
    monkeypatch.setenv("LLM_CACHE", "on")
    monkeypatch.setattr(llm_cache, "ler", lambda chave: guardado.get("resposta"))
    monkeypatch.setattr(llm_cache, "gravar", lambda chave, resp, meta: None)
    monkeypatch.setattr(llm_retry, "_gravar_uso", lambda **k: usos.append(k))
    return guardado, usos


def test_o_mesmo_arquivo_devolve_a_leitura_guardada_sem_chamar_a_ia(modo_on):
    guardado, usos = modo_on
    guardado["resposta"] = {"response_text": _LEITURA, "stop_reason": "end_turn"}
    ia = _ClienteQueConta(texto="não deveria ser lido")
    out = analyzer.analyze_sheet(ia, _Sheet())
    assert ia.chamadas == 0, "a leitura guardada não foi servida"
    assert [i["quantity"] for i in out["items"]] == [3]
    assert [u["resultado"] for u in usos] == ["cache"], (
        "a leitura guardada não ficou registrada no uso de IA")


def test_CONTROLE_sem_leitura_guardada_a_ia_e_chamada(modo_on):
    ia = _ClienteQueConta()
    out = analyzer.analyze_sheet(ia, _Sheet())
    assert ia.chamadas == 1
    assert [i["quantity"] for i in out["items"]] == [3]


def test_quem_reprocessa_recebe_leitura_nova(modo_on):
    guardado, _ = modo_on
    guardado["resposta"] = {"response_text": "leitura velha", "stop_reason": "end_turn"}
    ia = _ClienteQueConta()
    out = analyzer.analyze_sheet(ia, _Sheet(), usa_cache=False)
    assert ia.chamadas == 1, "o reprocesso de PDF devolveu a leitura guardada"
    assert [i["quantity"] for i in out["items"]] == [3]


def test_resposta_guardada_que_nao_abre_e_lida_de_novo_uma_vez(modo_on):
    guardado, _ = modo_on
    guardado["resposta"] = {"response_text": "```json\n{quebrado\n```",
                            "stop_reason": "end_turn"}
    ia = _ClienteQueConta()
    out = analyzer.analyze_sheet(ia, _Sheet())
    assert ia.chamadas == 1, "a resposta guardada quebrada não foi trocada"
    assert not out.get("error")
    assert [i["quantity"] for i in out["items"]] == [3]


def test_resposta_nova_que_nao_abre_continua_sendo_erro_sem_repetir(modo_on):
    ia = _ClienteQueConta(texto="```json\n{quebrado\n```")
    out = analyzer.analyze_sheet(ia, _Sheet())
    assert ia.chamadas == 1, "leitura nova quebrada não pode entrar em repetição"
    assert "JSON parse error" in out.get("error", "")


def _chamada_do_analyze_sheet():
    caminho = os.path.join(os.path.dirname(__file__), "..", "main.py")
    with open(caminho, encoding="utf-8") as f:
        arvore = ast.parse(f.read())
    achadas = [n for n in ast.walk(arvore) if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Name) and n.func.id == "analyze_sheet"]
    assert len(achadas) == 1, "esperava uma chamada de analyze_sheet no main.py"
    return achadas[0]


def _reproc_na_chamada(valor):
    usa = [k for k in _chamada_do_analyze_sheet().keywords if k.arg == "usa_cache"]
    assert usa, "o motor não diz se a leitura pode vir do cache: reprocesso reaproveita"
    return eval(compile(ast.Expression(usa[0].value), "usa_cache", "eval"),
                {"_reproc_atual": valor})


@pytest.mark.parametrize("reproc", [1, 2, 7])
def test_o_motor_manda_reprocesso_ler_de_novo(reproc):
    assert _reproc_na_chamada(reproc) is False


def test_CONTROLE_o_primeiro_envio_pode_usar_a_leitura_guardada():
    assert _reproc_na_chamada(0) is True
