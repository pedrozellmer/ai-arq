# -*- coding: utf-8 -*-
"""O ANEXO guarda o que o cliente corrigiu e rejeitou à mão (regra dura nº7).

🩸 01/10/2026 — a cliente preencheu à mão o concreto (10,5 m³) e a fôrma
(128,51 m²) que a leitura do PDF tinha deixado zerados, anexou o DWG, e as duas
correções sumiram da planilha. O `/add-file` relê no MESMO job; a fusão só
olhava o PAI, e releitura de anexo não tem pai. Desde sempre: 2 jobs.

O bloco do `process_job` é EXECUTADO aqui (recortado por âncora), com o banco
de dublê — ler o fonte já enganou esta casa (ver tests/_fim_do_job.py).
"""
import os
import sys
import textwrap
from types import SimpleNamespace

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import main  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402

JOB, PAI = "jobanexo", "jobpai"


# ── a regra de onde vem a revisão ─────────────────────────────────────────
@pytest.mark.parametrize("pai,anexo,esperado,motivo", [
    (PAI, None, [PAI], "releitura: o pai, como antes"),
    (None, "m1", [JOB], "anexo: o próprio job"),
    (PAI, "m1", [PAI, JOB], "anexo de filhote: o pai e depois o que ele corrigiu por cima"),
    (None, None, [], "1º processamento: nada"),
    (None, "  ", [], "marca em branco não é anexo"),
])
def test_de_onde_vem_a_revisao(pai, anexo, esperado, motivo):
    assert main._de_onde_vem_a_revisao(JOB, pai, anexo) == esperado, motivo


# ── o bloco do process_job, executado ─────────────────────────────────────
def _bloco():
    fonte = open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8").read()
    ini = fonte.index('        _fusao = {"revisoes": 0, "casadas": 0, "acrescentadas": 0}\n')
    fim = fonte.index("        # 🚨 23/08/2026 (auditoria, achado 22)", ini)
    return textwrap.dedent(fonte[ini:fim])


def _linha(desc, unit, q):
    return BudgetItem(item_num="1", description=desc, unit=unit, quantity=q,
                      confidence=Confidence.ESTIMADO, origem="dxf_geom")


LEITURA_DO_DWG = (
    ("Concreto usinado fck=40 MPa (C40) — superestrutura", "m³", 153.0),
    ("Armadura CA-50 Ø 10,0 mm — superestrutura", "kg", 1051.2),
)

#: o que a tela mostra ANTES do anexo — já com o que ela digitou
NA_TELA = [
    {"id": "i1", "description": "Concreto estrutural C-40 — vigas", "unit": "m³",
     "quantity": 10.5, "observations": "", "confidence": "estimado"},
    {"id": "i2", "description": "Fôrma de madeira/compensado — vigas", "unit": "m²",
     "quantity": 128.51, "observations": "", "confidence": "estimado"},
]
EDICOES = [
    {"item_id": "i1", "reviewed_at": "1", "edits": {
        "description": "Concreto estrutural C-40 — vigas", "unit": "m³", "quantity": 10.5,
        "_antes": {"description": "Concreto estrutural C-40 — vigas", "unit": "m³", "quantity": 0}}},
    {"item_id": "i2", "reviewed_at": "2", "edits": {
        "description": "Fôrma de madeira/compensado — vigas", "unit": "m²", "quantity": 128.51,
        "_antes": {"description": "Fôrma de madeira/compensado — vigas", "unit": "m²", "quantity": 0}}},
]


def _rodar(monkeypatch, pai, anexo, edicoes=EDICOES, rejeicoes=(), do_pai=None):
    """`do_pai`: {"edit": [...], "reject": [...]} — o que o PAI devolve."""
    lidos = []
    do_pai = do_pai or {}

    def _svc(metodo, tabela, params=None, **k):
        params = params or {}
        if tabela == "projects":
            # o banco só devolve o que o SELECT pediu
            linha = {"parent_job_id": pai, "anexo_em_curso": anexo}
            campos = str(params.get("select") or "").split(",")
            return 200, [{c: v for c, v in linha.items() if c in campos}]
        if tabela == "item_reviews":
            lidos.append((params.get("job_id"), params.get("action")))
            acao = "edit" if params.get("action") == "eq.edit" else "reject"
            if params.get("job_id") == f"eq.{PAI}":
                return 200, list(do_pai.get(acao) or [])
            if params.get("job_id") != f"eq.{JOB}":
                return 200, []
            return 200, list(edicoes if acao == "edit" else rejeicoes)
        return 200, []

    def _tudo(tabela, params=None, **k):
        if (params or {}).get("job_id") == f"eq.{JOB}":
            return 200, [dict(x) for x in NA_TELA]
        return 200, []

    monkeypatch.setattr(main, "_supa_rest_service", _svc)
    monkeypatch.setattr(main, "_supa_rest_tudo", _tudo)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    ns = dict(main.__dict__)
    ns.update(job_id=JOB, all_items=[_linha(*x) for x in LEITURA_DO_DWG],
              project_data=SimpleNamespace(warnings=[]))
    exec(compile(_bloco(), "bloco_da_fusao", "exec"), ns)
    return ns, lidos


def test_o_caso_o_anexo_traz_de_volta_o_que_ela_digitou(monkeypatch):
    ns, lidos = _rodar(monkeypatch, pai=None, anexo="m1")
    qs = {(i.description, i.unit): i.quantity for i in ns["all_items"]}
    assert qs[("Concreto estrutural C-40 — vigas", "m³")] == pytest.approx(10.5)
    assert qs[("Fôrma de madeira/compensado — vigas", "m²")] == pytest.approx(128.51)
    assert len(ns["all_items"]) == 4, "as 2 do DWG ficam: errar pra duplicado, nunca pra sumiço"
    assert ns["_fusao"]["revisoes"] == 2 and ns["_fusao"]["acrescentadas"] == 2, ns["_fusao"]
    assert any("MANTEVE" in w for w in ns["project_data"].warnings)


def test_o_anexo_tambem_nao_traz_de_volta_o_que_ela_rejeitou(monkeypatch):
    rej = [{"item_id": "x9", "reviewed_at": "3", "edits": {"_antes": {
        "description": "Armadura CA-50 Ø 10,0 mm — superestrutura", "unit": "kg",
        "quantity": 1051.2}}}]
    ns, _ = _rodar(monkeypatch, pai=None, anexo="m1", edicoes=(), rejeicoes=rej)
    assert not any("Armadura" in i.description for i in ns["all_items"])
    assert ns["_fusao"].get("rejeitadas_tiradas") == 1


def test_anexo_de_filhote_le_o_pai_e_o_proprio_job(monkeypatch):
    _, lidos = _rodar(monkeypatch, pai=PAI, anexo="m1")
    jobs_edit = [j for j, a in lidos if a == "eq.edit"]
    assert jobs_edit == [f"eq.{PAI}", f"eq.{JOB}"], lidos


def test_anexo_de_filhote_soma_o_que_veio_dos_dois(monkeypatch):
    """Uma correção do pai (linha que já não existe nele) + as 2 do próprio job;
    uma rejeição em cada. O placar é a SOMA — senão o aviso e a refação da
    planilha contam só a última fonte."""
    do_pai = {
        "edit": [{"item_id": "", "reviewed_at": "0", "edits": {
            "description": "Escoramento metálico — lajes", "unit": "m²", "quantity": 300.0,
            "_antes": {"description": "Escoramento metálico — lajes", "unit": "m²",
                       "quantity": 0}}}],
        "reject": [{"item_id": "p9", "reviewed_at": "0", "edits": {"_antes": {
            "description": "Concreto usinado fck=40 MPa (C40) — superestrutura",
            "unit": "m³", "quantity": 153.0}}}],
    }
    rej = [{"item_id": "x9", "reviewed_at": "3", "edits": {"_antes": {
        "description": "Armadura CA-50 Ø 10,0 mm — superestrutura", "unit": "kg",
        "quantity": 1051.2}}}]
    ns, _ = _rodar(monkeypatch, pai=PAI, anexo="m1", rejeicoes=rej, do_pai=do_pai)
    assert ns["_fusao"]["revisoes"] == 3, ns["_fusao"]
    assert ns["_fusao"].get("rejeitadas_tiradas") == 2, ns["_fusao"]


# ── o que NÃO muda ────────────────────────────────────────────────────────
def test_CONTROLE_releitura_le_so_o_pai(monkeypatch):
    _, lidos = _rodar(monkeypatch, pai=PAI, anexo=None)
    assert {j for j, _ in lidos} == {f"eq.{PAI}"}, lidos


def test_CONTROLE_primeiro_processamento_nao_le_revisao(monkeypatch):
    ns, lidos = _rodar(monkeypatch, pai=None, anexo=None)
    assert lidos == [] and len(ns["all_items"]) == 2
