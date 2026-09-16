# -*- coding: utf-8 -*-
"""A linha que a consolidação come tem que deixar rastro no log.

🔁 15/09/2026, estudo dos itens repetidos: 45 dobros REAIS em 11 jobs. O
`motor:itens-removidos` (09/09) já dizia QUANTAS linhas cada removedor tirou —
nunca QUAIS. E das passadas de fusão, só uma some calada: a passada 1 quando o
grupo tem a MESMA quantidade. Ela mantém a melhor linha e descarta as outras sem
escrever nada na observação. As outras passadas ao menos deixam "Fundido de N
entradas" ou "(várias variantes)" na linha que fica.

🔑 A verdade de campo diz que 87% do que o cliente corrige é PREENCHER linha
zerada. A linha específica que some é justamente a que ele saberia preencher.

Este passo é SÓ REGISTRO: `motor:fusao-calada`, diagnóstico, sem mexer em selo,
quantidade ou no que o cliente recebe. Ler o log em ~2 semanas e só então decidir.

🔒 O resumo não pode levar `ref_sheet`: é nome de arquivo do cliente e pode trazer
nome de pessoa (o mesmo canal que já existe no `arq=` de outros stages). Vai só a
contagem de pranchas distintas.

🚨 O guarda do fim roda `main.process_job` DE VERDADE (DXF sintético, IA falsa,
sem rede) e olha a linha que o motor gravou — não o fonte.
"""
import json
import os
import socket
import sys
import types
import urllib.request

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

ezdxf = pytest.importorskip("ezdxf")

from main import (_anota_fusao, _consolidate_items, _resumo_de_fusoes,  # noqa: E402
                  _STAGES_DIAGNOSTICO)
from models import BudgetItem, Confidence  # noqa: E402

# nome de arquivo de prancha com cara de cliente — FICTÍCIO
_PRANCHA_A = "ARQ-EX-001-FULANO-FICTICIO-R00.dwg"
_PRANCHA_B = "ARQ-EX-002-FULANO-FICTICIO-R00.dwg"


def _item(desc, unit="un", qty=3.0, disc="Complementares", prancha="", medido=False):
    return BudgetItem(
        item_num="", description=desc, unit=unit, quantity=qty, observations="",
        ref_sheet=prancha,
        confidence=Confidence("confirmado" if medido else "estimado"),
        discipline=disc, origem="dxf_geom" if medido else "ia_texto",
    )


# ── a fusão calada da passada 1 ────────────────────────────────────────────
def test_o_par_identico_some_e_o_registro_conta_isso():
    reg = []
    saida = _consolidate_items(
        [_item("Ponto de tomada 2P+T 10A", prancha=_PRANCHA_A),
         _item("Ponto de tomada 2P+T 10A", prancha=_PRANCHA_B)], registro=reg)
    assert len(saida) == 1, [i.description for i in saida]
    assert len(reg) == 1, reg
    assert reg[0]["passada"] == "p1-igual", reg[0]
    assert reg[0]["n"] == 2 and reg[0]["pranchas"] == 2, reg[0]
    assert reg[0]["qty"] == 3.0 and reg[0]["unidade"] == "un", reg[0]

    # 3 linhas em 2 pranchas: contagem de linha e contagem de prancha são coisas
    # diferentes — a mesma folha lida 2× foi 15 dos 45 dobros do estudo
    reg2 = []
    _consolidate_items([_item("Ralo sifonado 100mm", qty=7.0, prancha=_PRANCHA_A),
                        _item("Ralo sifonado 100mm", qty=7.0, prancha=_PRANCHA_A),
                        _item("Ralo sifonado 100mm", qty=7.0, prancha=_PRANCHA_B)], registro=reg2)
    assert reg2[0]["n"] == 3 and reg2[0]["pranchas"] == 2, reg2[0]


def test_a_linha_que_some_com_selo_de_medida_e_marcada():
    """Sumir com linha MEDIDA é o caso grave: o resumo tem que gritar."""
    reg = []
    _consolidate_items(
        [_item("Ponto de tomada 2P+T 10A", prancha=_PRANCHA_A, medido=True),
         _item("Ponto de tomada 2P+T 10A", prancha=_PRANCHA_B, medido=True)], registro=reg)
    assert reg[0]["medidas"] == 2, reg[0]
    assert "🚩MEDIDA" in _resumo_de_fusoes(reg), _resumo_de_fusoes(reg)


def test_CONTROLE_quantidades_diferentes_nao_somem_nem_viram_registro():
    reg = []
    saida = _consolidate_items(
        [_item("Ponto de tomada 2P+T 10A", qty=3.0, prancha=_PRANCHA_A),
         _item("Ponto de tomada 2P+T 10A", qty=5.0, prancha=_PRANCHA_B)], registro=reg)
    assert len(saida) == 2, [i.description for i in saida]
    assert reg == [], reg


def test_CONTROLE_item_sozinho_nao_vira_registro():
    reg = []
    assert len(_consolidate_items([_item("Porta de madeira 80x210")], registro=reg)) == 1
    assert reg == [], reg
    # 🪤 A consolidação nunca chama `_anota_fusao` com grupo de 1 — as duas
    # passadas saem antes pelo `continue`. A trava só é exercitável na chamada
    # direta, e sem este caso a mutação que a remove sobrevive (medido 16/09).
    _anota_fusao(reg, "p1-igual", [_item("Porta de madeira 80x210")],
                 _item("Porta de madeira 80x210"))
    assert reg == [], "grupo de 1 não é fusão: %r" % reg


def test_a_fusao_por_familia_da_passada_2_tambem_entra():
    reg = []
    saida = _consolidate_items(
        [_item("Alvenaria tijolo cerâmico 9x14x19", unit="ml", qty=491.84, disc="Alvenaria",
               prancha=_PRANCHA_A),
         _item("Execução de alvenaria nova", unit="ml", qty=491.84, disc="Alvenaria",
               prancha=_PRANCHA_B)], registro=reg)
    assert len(saida) == 1, [i.description for i in saida]
    assert [r["passada"] for r in reg] == ["p2-familia"], reg
    assert reg[0]["n"] == 2 and reg[0]["pranchas"] == 2, reg[0]


def test_o_resumo_NAO_leva_o_nome_da_prancha():
    """LGPD: nome de arquivo do cliente não entra no log."""
    reg = []
    _consolidate_items(
        [_item("Ponto de tomada 2P+T 10A", prancha=_PRANCHA_A),
         _item("Ponto de tomada 2P+T 10A", prancha=_PRANCHA_B)], registro=reg)
    linha = _resumo_de_fusoes(reg)
    for proibido in ("FULANO", "FICTICIO", ".dwg", "ARQ-EX"):
        assert proibido not in linha, f"{proibido!r} vazou em {linha!r}"
    assert "pranchas=2" in linha, linha


def test_o_resumo_diz_quantas_linhas_sumiram_e_e_curto():
    reg = []
    for i in range(12):
        _consolidate_items([_item("Luminária LM%d" % i, prancha=_PRANCHA_A),
                            _item("Luminária LM%d" % i, prancha=_PRANCHA_B),
                            _item("Luminária LM%d" % i, prancha="")], registro=reg)
    linha = _resumo_de_fusoes(reg)
    assert "grupos=12" in linha and "linhas_a_menos=24" in linha, linha
    assert linha.count("·") == 4, linha          # só os 5 maiores
    assert len(linha) < 500, len(linha)


def test_CONTROLE_sem_registro_a_consolidacao_funciona_igual():
    """Quem chama sem `registro` (os testes antigos, o guarda de outro passo)
    não pode ver diferença nenhuma."""
    entrada = [_item("Ponto de tomada 2P+T 10A", prancha=_PRANCHA_A),
               _item("Ponto de tomada 2P+T 10A", prancha=_PRANCHA_B)]
    assert len(_consolidate_items(list(entrada))) == 1
    assert _resumo_de_fusoes([]) == ""


def test_CONTROLE_registro_quebrado_nao_derruba_a_consolidacao():
    """O registro é acessório: item sem os campos não pode explodir o job."""
    class _Cru:
        description = "Ponto de tomada"

    class _Explode:
        @property
        def description(self):
            raise RuntimeError("item quebrado")

    reg = []
    _anota_fusao(reg, "p1-igual", [_Cru(), _Cru()], _Cru())
    assert reg == [] or reg[0]["n"] == 2
    _anota_fusao(None, "p1-igual", [_Cru(), _Cru()], _Cru())   # sem lista: não quebra
    _anota_fusao(reg, "p1-igual", [_Explode(), _Explode()], _Explode())  # não levanta


def test_o_stage_e_diagnostico_e_nao_erro():
    assert "motor:fusao-calada" in _STAGES_DIAGNOSTICO


# ── o motor grava de verdade ───────────────────────────────────────────────
def _dxf(path):
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (8, 0), (8, 6), (0, 6), (0, 0)], dxfattribs={"layer": "PAREDE"})
    msp.add_text("PLANTA BAIXA", dxfattribs={"layer": "TEXTO", "insert": (1, 7), "height": 0.4})
    doc.saveas(path)


def _rodar_motor(monkeypatch, tmp_path, itens, nome):
    """Roda `process_job` com a IA devolvendo `itens` e devolve as linhas do log."""
    import llm_retry
    import main

    caminho = str(tmp_path / nome)
    _dxf(caminho)
    logs = []

    class _Resp:
        def __init__(self, corpo):
            self._corpo = corpo

        def read(self, *a):
            return self._corpo

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _JobsMudo:
        def update_field(self, *a, **k):
            pass

    class _Parou(BaseException):
        """BaseException de propósito: `process_job` engole `Exception`."""

    def _ia_falsa(client, **kw):
        corpo = "```json\n" + json.dumps({"project_data": {}, "items": itens},
                                         ensure_ascii=False) + "\n```"
        return types.SimpleNamespace(
            content=[types.SimpleNamespace(text=corpo)], stop_reason="end_turn",
            usage=types.SimpleNamespace(output_tokens=10, input_tokens=10))

    passou = []

    def _freia(*a, **k):
        # o freio fica DEPOIS da consolidação: se ele disparou, o motor passou
        # pelo ponto onde a linha de fusão é gravada
        passou.append(True)
        raise _Parou()

    monkeypatch.setattr(socket.socket, "connect",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("rede bloqueada")))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp(json.dumps(
        [{"auto_resume_count": 0, "reprocess_count": 0}]).encode("utf-8")))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-guarda-local")
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, message, *a, **k: logs.append((stage, str(message))))
    monkeypatch.setattr(main, "_supabase_update", lambda *a, **k: None)
    monkeypatch.setattr(main, "_projeto_patch", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supabase_storage_upload_prancha", lambda *a, **k: True)
    monkeypatch.setattr(main, "jobs", _JobsMudo())
    monkeypatch.setattr(main, "_extract_dxf_isolated",
                        lambda p, u, timeout_s=900, job_id="": main._extract_dxf_inprocess(p, u, job_id))
    monkeypatch.setattr(llm_retry, "call_with_retry_stream", _ia_falsa)
    # freio DEPOIS da consolidação e do log — este passo é o que queremos ver
    monkeypatch.setattr(main, "rebaixar_itens_sem_identidade", _freia)
    try:
        main.process_job("guarda-fusao", [caminho], str(tmp_path), project_type="arquitetura")
    except _Parou:
        pass
    assert passou, (
        "o motor não chegou no passo seguinte à consolidação — o arranjo não rodou, "
        "então este guarda não mediu nada: %r" % [s for s, _ in logs][:25])
    return logs


def _dobro(desc, qty):
    base = {"description": desc, "unit": "un", "quantity": qty,
            "observations": "Contado na geometria.", "discipline": "Elétrica",
            "confidence": "estimado"}
    return [dict(base, item_num="1"), dict(base, item_num="2")]


def test_o_motor_GRAVA_a_fusao_calada_no_log(monkeypatch, tmp_path):
    logs = _rodar_motor(monkeypatch, tmp_path,
                        _dobro("Ponto de tomada 2P+T 10A", 12.0)
                        + [{"item_num": "3", "description": "Luminária de embutir LED 18W",
                            "unit": "un", "quantity": 4.0, "observations": "",
                            "discipline": "Elétrica", "confidence": "estimado"}],
                        "ELE-PLANTA_guarda.dxf")
    linhas = [msg for st, msg in logs if st == "motor:fusao-calada"]
    assert len(linhas) == 1, [s for s, _ in logs]
    assert "p1-igual=1" in linhas[0] and "linhas_a_menos=1" in linhas[0], linhas[0]
    assert "guarda" not in linhas[0].lower(), linhas[0]     # nome de arquivo fora


def test_CONTROLE_sem_item_repetido_o_motor_nao_grava_a_linha(monkeypatch, tmp_path):
    logs = _rodar_motor(monkeypatch, tmp_path,
                        [{"item_num": "1", "description": "Ponto de tomada 2P+T 10A",
                          "unit": "un", "quantity": 12.0, "observations": "",
                          "discipline": "Elétrica", "confidence": "estimado"},
                         {"item_num": "2", "description": "Luminária de embutir LED 18W",
                          "unit": "un", "quantity": 4.0, "observations": "",
                          "discipline": "Elétrica", "confidence": "estimado"}],
                        "ELE-PLANTA-SEM-DOBRO_guarda.dxf")
    assert [msg for st, msg in logs if st == "motor:fusao-calada"] == []
