# -*- coding: utf-8 -*-
"""RESGATE_PULA_ITEM_QUEBRADO: um item que nao abre nao leva o resto da lista.

🩸 16/11/2026. Numa prancha de teste a IA terminou a resposta normalmente e um
item trazia aspas de polegada sem escape dentro da descricao. O resgate antigo
perde o fio dentro da string e larga tudo o que vem depois: 30 de 36 itens, os
6 do fim inteiros na resposta. E a prancha era tratada como cortada no teto
(aviso + releitura paga com o teto dobrado, que nao conserta escape).

O que este arquivo sustenta:
  - o resgate novo pula o item quebrado e retoma no proximo;
  - com a chave em 0 o leitor devolve EXATAMENTE o que devolvia, so com a marca
    `_json_invalido` (o alcance);
  - com a chave em 1, resposta que terminou normalmente nao paga releitura.

Tudo sintetico.
"""
import json
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import analyzer                                               # noqa: E402
import engine_rules                                           # noqa: E402
from models import SheetInfo, SheetType                       # noqa: E402

_ASPA = chr(34)
_NL = chr(10)
_CERCA = chr(96) * 3


def _item(n, descricao=None):
    return json.dumps({"item_num": str(n), "description": descricao or ("Servico generico %d" % n),
                       "unit": "un", "quantity": n, "confidence": "estimado"})


def _item_quebrado(n):
    """Aspas de polegada SEM escape no meio da descricao."""
    bom = _item(n, "Tubo de 2 pol conforme legenda, lado A")
    return bom.replace("2 pol", "2" + _ASPA + " -")


def _lista(itens, fecha=True):
    corpo = "{" + _ASPA + "project_data" + _ASPA + ": {" + _ASPA + "nome" + _ASPA + ": " \
        + _ASPA + "Planta generica" + _ASPA + "}, " + _ASPA + "items" + _ASPA + ": [" \
        + ("," + _NL).join(itens)
    return corpo + ("]}" if fecha else "")


_QUEBRADA = _lista([_item(1), _item(2), _item(3), _item_quebrado(4), _item(5), _item(6)])


def test_CONTROLE_a_lista_de_teste_nao_abre_e_o_resgate_antigo_perde_o_fim():
    with pytest.raises(json.JSONDecodeError):
        json.loads(_QUEBRADA)
    antigo = engine_rules.salvage_truncated_json(_QUEBRADA)["items"]
    assert [i["item_num"] for i in antigo] == ["1", "2", "3"], (
        "o resgate antigo deixou de perder os itens do fim: este arquivo nao "
        "mede mais nada (%r)" % [i.get("item_num") for i in antigo])


def test_o_resgate_novo_pula_so_o_item_quebrado():
    out, pulados = engine_rules.resgata_pulando_o_item_quebrado(_QUEBRADA)
    assert [i["item_num"] for i in out["items"]] == ["1", "2", "3", "5", "6"]
    assert pulados == 1
    assert out["project_data"] == {"nome": "Planta generica"}


def test_lista_boa_sai_inteira_e_nada_e_pulado():
    out, pulados = engine_rules.resgata_pulando_o_item_quebrado(
        _lista([_item(n) for n in range(1, 8)]))
    assert len(out["items"]) == 7 and pulados == 0


def test_item_do_fim_cortado_conta_como_um_pulado():
    cortada = _lista([_item(1), _item(2), _item(3)[:40]], fecha=False)
    out, pulados = engine_rules.resgata_pulando_o_item_quebrado(cortada)
    assert [i["item_num"] for i in out["items"]] == ["1", "2"] and pulados == 1


def test_dois_quebrados_seguidos_nao_param_a_lista():
    out, pulados = engine_rules.resgata_pulando_o_item_quebrado(
        _lista([_item(1), _item_quebrado(2), _item_quebrado(3), _item(4)]))
    assert [i["item_num"] for i in out["items"]] == ["1", "4"] and pulados == 2


@pytest.mark.parametrize("lixo", ["", "xpto", "{", "[1, 2", None, 7])
def test_lixo_nunca_lanca(lixo):
    out, pulados = engine_rules.resgata_pulando_o_item_quebrado(lixo)
    assert out["items"] == [] and pulados == 0


# ── o leitor ──────────────────────────────────────────────────────────────
def _resposta(json_str):
    return "Raciocinio." + _NL + _CERCA + "json" + _NL + json_str + _NL + _CERCA


def test_DESLIGADA_o_leitor_devolve_o_de_antes_so_com_a_marca():
    parsed, truncado = analyzer._json_da_resposta(_resposta(_QUEBRADA), "end_turn", "p.pdf")
    assert [i["item_num"] for i in parsed["items"]] == ["1", "2", "3"]
    assert truncado is True
    assert parsed["_json_invalido"] == {"parou_normal": True, "salvos": 3, "com_resgate": 5,
                                        "pulados": 1, "usado": False}


def test_LIGADA_o_leitor_fica_com_os_cinco_e_ainda_avisa_que_perdeu_um():
    parsed, truncado = analyzer._json_da_resposta(_resposta(_QUEBRADA), "end_turn", "p.pdf",
                                                  pula_quebrado=True)
    assert [i["item_num"] for i in parsed["items"]] == ["1", "2", "3", "5", "6"]
    assert truncado is True, "um item se perdeu: o cliente continua sendo avisado"
    assert parsed["_json_invalido"]["usado"] is True


def test_LIGADA_json_que_so_tem_sujeira_no_fim_nao_e_leitura_cortada():
    suja = _lista([_item(1), _item(2)]) + " sobra que nao e json"
    with pytest.raises(json.JSONDecodeError):
        json.loads(suja)
    parsed, truncado = analyzer._json_da_resposta(_resposta(suja), "end_turn", "p.pdf",
                                                  pula_quebrado=True)
    assert len(parsed["items"]) == 2 and truncado is False
    # CONTROLE: com a chave em 0 a mesma resposta segue como cortada
    _, antes = analyzer._json_da_resposta(_resposta(suja), "end_turn", "p.pdf")
    assert antes is True


def test_LIGADA_corte_no_teto_de_verdade_continua_cortado():
    cortada = _lista([_item(1), _item(2), _item(3)[:40]], fecha=False)
    parsed, truncado = analyzer._json_da_resposta(_resposta(cortada), "max_tokens", "p.pdf",
                                                  pula_quebrado=True)
    assert len(parsed["items"]) == 2 and truncado is True
    assert parsed["_json_invalido"]["parou_normal"] is False


def test_json_bom_nao_ganha_marca():
    parsed, truncado = analyzer._json_da_resposta(
        _resposta(_lista([_item(1)])), "end_turn", "p.pdf", pula_quebrado=True)
    assert "_json_invalido" not in parsed and truncado is False


# ── a releitura paga ──────────────────────────────────────────────────────
class _Bloco:
    type = "text"

    def __init__(self, texto):
        self.text = texto


class _Resp:
    do_cache = False

    def __init__(self, texto, stop):
        self.content = [_Bloco(texto)]
        self.stop_reason = stop


def _chamadas(monkeypatch, texto, stop, **kw):
    tags = []

    def _fake(client, **k):
        tags.append(k.get("tag", ""))
        return _Resp(texto, stop)

    monkeypatch.setattr(analyzer, "call_with_retry_stream", _fake)
    sheet = SheetInfo(filename="prancha generica.pdf", sheet_type=SheetType.LAYOUT_NOVO,
                      text_content="", crops=[])
    out = analyzer.analyze_sheet(object(), sheet, usa_cache=False, reler_cortada=True, **kw)
    return tags, out


def test_LIGADA_item_quebrado_com_resposta_terminada_nao_paga_releitura(monkeypatch):
    tags, out = _chamadas(monkeypatch, _resposta(_QUEBRADA), "end_turn", pula_quebrado=True)
    assert len(tags) == 1, "pagou releitura por um erro de escape: %r" % tags
    assert len(out["items"]) == 5 and out.get("_truncated") is True
    assert out["_json_invalido"]["usado"] is True


def test_CONTROLE_DESLIGADA_a_mesma_resposta_paga_a_releitura(monkeypatch):
    tags, out = _chamadas(monkeypatch, _resposta(_QUEBRADA), "end_turn")
    assert len(tags) == 2 and tags[1].endswith("#teto-maior"), tags


def test_LIGADA_corte_no_teto_de_verdade_ainda_rele_com_teto_maior(monkeypatch):
    cortada = _lista([_item(1), _item(2), _item(3)[:40]], fecha=False)
    tags, _ = _chamadas(monkeypatch, _resposta(cortada), "max_tokens", pula_quebrado=True)
    assert len(tags) == 2 and tags[1].endswith("#teto-maior"), tags


# ── a chave ───────────────────────────────────────────────────────────────
def test_a_chave_e_avaliavel_e_o_leitor_de_pdf_a_recebe():
    import main
    assert "RESGATE_PULA_ITEM_QUEBRADO" in main._CHAVES_AVALIAVEIS
    fonte = open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    assert "pula_quebrado=_liga_resgate_pula_quebrado(job_id)" in fonte
    assert "_registra_json_invalido(result, _disp, job_id)" in fonte


def test_o_registro_conta_com_a_chave_em_zero_tambem(monkeypatch):
    import main
    visto = []
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: visto.append((a, k)))
    main._registra_json_invalido({"items": []}, "p.pdf", "job-x")
    assert visto == [], "prancha sem a marca nao e registrada"
    main._registra_json_invalido(
        {"_json_invalido": {"parou_normal": True, "salvos": 3, "com_resgate": 5,
                            "pulados": 1, "usado": False}}, "p.pdf", "job-x")
    assert len(visto) == 1 and visto[0][0][0] == "motor:json-invalido"
    assert "liga=0" in visto[0][0][1] and "salvos=3 com_resgate=5 pulados=1" in visto[0][0][1]
