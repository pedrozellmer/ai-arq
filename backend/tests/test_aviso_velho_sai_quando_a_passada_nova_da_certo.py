# -*- coding: utf-8 -*-
"""O aviso da passada anterior sai quando a passada nova dá certo.

🩸 28/09/2026 (estudo de leitura, achado 25). Desde 04/09 o fim de cada passada
grava `_avisos_com(job_id, project_data.warnings)`, que lê o banco e só
ACRESCENTA. Quando o projeto passa de novo pelo motor (anexo, nova tentativa,
reprocesso), o aviso de antes fica ao lado do de agora: 9 dos 10 projetos de
cliente com mais de uma passada mostravam aviso velho na tela e no .xlsx
refeito. O pior: "📐 Nenhuma linha deste projeto foi MEDIDA" ao lado de
centenas de itens medidos pelo CAD que o próprio aviso mandou anexar.

🔑 O conserto: `projects.avisos_do_motor` guarda o que o motor gravou na última
passada. SÓ a passada que deu certo (os itens acabaram de ser trocados) tira
esses e põe os dela. Aviso de outra rota (prancha perdida da retomada, arquivo
extenso do anexo, área informada) não está na lista e fica. Erro e anexo que
falhou mantêm a planilha — e os avisos que a descrevem —, mas somam os deles à
lista, pra saírem quando uma próxima der certo.

Tudo aqui roda o código de produção contra um banco de mentira em memória: só
`_supa_rest_service` (leitura e PATCH) e a RPC (`_supabase_update`) são dublês.
"""
import ast
import copy
import os
import re
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import main  # noqa: E402
from _corpo import fonte  # noqa: E402

_JOB = "job-de-teste"
_VELHO = "📐 Nenhuma linha deste projeto foi MEDIDA — só PDF. Anexe o CAD neste mesmo projeto."
_VELHO2 = "⚠ Plano B do conversor acionado em 2 prancha(s)"
_DA_ROTA = "⚠ A prancha 03 não foi encontrada no armazenamento"   # retomada: fica
_NOVO = "⚠ Escala conferida por 14 cotas"


class _Banco:
    """A linha de `projects` deste job, com a semântica do banco de verdade.

    RPC `update_project_status`: `warnings = COALESCE(p_warnings, warnings)` —
    None mantém, [] limpa. `avisos_do_motor` só muda por PATCH.
    """

    def __init__(self, warnings, avisos_do_motor=None, falha=(), rpc_ok=True):
        self.linha = {"warnings": list(warnings),
                      "avisos_do_motor": (None if avisos_do_motor is None
                                          else list(avisos_do_motor))}
        self.falha = set(falha)       # colunas cuja leitura devolve HTTP 500
        self.rpc_ok = rpc_ok
        self.patches = []

    def rest(self, metodo, caminho, params=None, body=None, prefer=None, **k):
        caminho = str(caminho)
        if metodo == "GET" and caminho.startswith("project_items"):
            return 200, [{"id": 1}]
        if metodo == "GET" and caminho.startswith("projects"):
            col = (params or {}).get("select")
            if col in self.falha:
                return 500, None
            return 200, [{col: copy.deepcopy(self.linha.get(col))}]
        if metodo == "PATCH" and caminho.startswith("projects"):
            self.patches.append(dict(body or {}))
            self.linha.update(copy.deepcopy(body or {}))
            return 204, None
        return 200, []

    def rpc(self, tabela, campo, valor, dados, *a, **k):
        assert (tabela, campo, valor) == ("projects", "job_id", _JOB)
        if not self.rpc_ok:
            return False
        if dados.get("warnings") is not None:
            self.linha["warnings"] = list(dados["warnings"])
        return True


@pytest.fixture
def logs(monkeypatch):
    lista = []
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, job_id=None, severity="error":
                        lista.append((stage, msg, severity)))
    return lista


def _no_banco(monkeypatch, banco):
    monkeypatch.setattr(main, "_supa_rest_service", banco.rest)
    monkeypatch.setattr(main, "_supabase_update", banco.rpc)


# ── O fim da passada que deu certo: o código REAL, tirado do process_job ────
def _fim_da_passada_que_deu_certo():
    """Do `_avisos_agora = ...` até o `if` que grava — o pedaço de produção.

    Recorte por AST (a lista de instruções que contém a atribuição), nunca por
    tamanho fixo.
    """
    arv = ast.parse(fonte("main.py"))
    pj = [n for n in ast.walk(arv)
          if isinstance(n, ast.FunctionDef) and n.name == "process_job"]
    assert len(pj) == 1, "process_job sumiu ou virou duas definições"
    achados = []
    for n in ast.walk(pj[0]):
        for campo in ("body", "orelse", "finalbody"):
            lst = getattr(n, campo, None)
            if not isinstance(lst, list):
                continue
            for i, st in enumerate(lst):
                if (isinstance(st, ast.Assign) and len(st.targets) == 1
                        and getattr(st.targets[0], "id", "") == "_avisos_agora"):
                    js = [j for j in range(i + 1, len(lst))
                          if isinstance(lst[j], ast.If)
                          and "_avisos_antes" in ast.unparse(lst[j].test)]
                    assert js, "sumiu o `if` que grava os avisos no fim da passada"
                    achados.append(lst[i:js[0] + 1])
    assert len(achados) == 1, (
        "esperava UM fim de passada que grava os avisos, achei %d" % len(achados))
    return ast.unparse(ast.Module(body=achados[0], type_ignores=[]))


def _roda_o_fim(banco, avisos_do_motor, monkeypatch):
    _no_banco(monkeypatch, banco)

    class _PD:
        warnings = list(avisos_do_motor)

    escopo = {
        "job_id": _JOB, "project_data": _PD(),
        "_supabase_update": banco.rpc,
        "_avisos_com": main._avisos_com,
        "_avisos_do_motor_da_passada_anterior": main._avisos_do_motor_da_passada_anterior,
        "_lembrar_avisos_do_motor": main._lembrar_avisos_do_motor,
    }
    exec(compile(_fim_da_passada_que_deu_certo(), "fim_da_passada", "exec"), escopo)


def test_o_aviso_da_passada_anterior_SAI_e_o_da_rota_FICA(monkeypatch, logs):
    banco = _Banco([_VELHO, _DA_ROTA, _VELHO2], avisos_do_motor=[_VELHO, _VELHO2])
    _roda_o_fim(banco, [_NOVO], monkeypatch)
    assert banco.linha["warnings"] == [_DA_ROTA, _NOVO], banco.linha["warnings"]
    assert banco.linha["avisos_do_motor"] == [_NOVO], banco.linha["avisos_do_motor"]
    assert any(s == "motor:avisos-velhos" and "sairam=2" in m for s, m, _ in logs), logs


def test_sai_MESMO_quando_a_passada_nova_nao_tem_aviso(monkeypatch, logs):
    """🔑 O caso em que o velho mais mente: o CAD anexado mediu tudo, o motor
    não tem nada a dizer — e a tela seguia dizendo que nada foi medido."""
    banco = _Banco([_VELHO, _DA_ROTA], avisos_do_motor=[_VELHO])
    _roda_o_fim(banco, [], monkeypatch)
    assert banco.linha["warnings"] == [_DA_ROTA], banco.linha["warnings"]
    assert banco.linha["avisos_do_motor"] == [], banco.linha["avisos_do_motor"]


def test_o_aviso_que_se_REPETE_fica_uma_vez(monkeypatch, logs):
    banco = _Banco([_VELHO2, _DA_ROTA], avisos_do_motor=[_VELHO2])
    _roda_o_fim(banco, [_VELHO2, _NOVO], monkeypatch)
    assert banco.linha["warnings"] == [_DA_ROTA, _VELHO2, _NOVO], banco.linha["warnings"]


def test_CONTROLE_projeto_de_antes_do_conserto_nao_perde_nada(monkeypatch, logs):
    """Lista nula = nada a tirar: o comportamento de antes, sem apagar às cegas."""
    banco = _Banco([_VELHO, _DA_ROTA], avisos_do_motor=None)
    _roda_o_fim(banco, [_NOVO], monkeypatch)
    assert banco.linha["warnings"] == [_VELHO, _DA_ROTA, _NOVO], banco.linha["warnings"]
    assert banco.linha["avisos_do_motor"] == [_NOVO]
    assert not [s for s, _m, _v in logs if s == "motor:avisos-velhos"], logs


def test_CONTROLE_projeto_sem_aviso_nenhum_nao_escreve_nada(monkeypatch, logs):
    banco = _Banco([], avisos_do_motor=None)
    _roda_o_fim(banco, [], monkeypatch)
    assert banco.patches == [] and banco.linha["warnings"] == []


def test_se_os_avisos_NAO_gravaram_a_lista_nao_muda(monkeypatch, logs):
    """🪤 A lista diz o que a próxima passada vai tirar. Se ela andasse sem o
    `warnings` ter gravado, a próxima deixaria o aviso velho na tela pra sempre
    (ele sairia da lista sem ter saído do banco)."""
    banco = _Banco([_VELHO, _DA_ROTA], avisos_do_motor=[_VELHO], rpc_ok=False)
    _roda_o_fim(banco, [_NOVO], monkeypatch)
    assert banco.linha["avisos_do_motor"] == [_VELHO], banco.linha["avisos_do_motor"]
    assert banco.patches == []


def test_leitura_da_lista_que_falha_nao_apaga_nada_e_deixa_rastro(monkeypatch, logs):
    banco = _Banco([_VELHO, _DA_ROTA], avisos_do_motor=[_VELHO], falha={"avisos_do_motor"})
    _roda_o_fim(banco, [_NOVO], monkeypatch)
    assert banco.linha["warnings"] == [_VELHO, _DA_ROTA, _NOVO], banco.linha["warnings"]
    assert [v for s, _m, v in logs if s == "motor:avisos-velhos-sem-lista"] == ["warning"], logs


def test_leitura_dos_avisos_que_falha_NAO_grava_lista_vazia_as_cegas(monkeypatch, logs):
    """🪤 Sem aviso novo e sem conseguir ler o que está lá, gravar [] apagaria
    tudo o que outras rotas escreveram. None = a RPC mantém."""
    banco = _Banco([_VELHO, _DA_ROTA], avisos_do_motor=[_VELHO], falha={"warnings"})
    _roda_o_fim(banco, [], monkeypatch)
    assert banco.linha["warnings"] == [_VELHO, _DA_ROTA], banco.linha["warnings"]


# ── _avisos_com: a régua ────────────────────────────────────────────────────
def test_sem_saem_o_avisos_com_e_o_de_sempre(monkeypatch, logs):
    banco = _Banco([_VELHO, _DA_ROTA])
    _no_banco(monkeypatch, banco)
    assert main._avisos_com(_JOB, [_NOVO]) == [_VELHO, _DA_ROTA, _NOVO]
    banco.falha = {"warnings"}
    assert main._avisos_com(_JOB, [_NOVO]) == [_NOVO]
    assert main._avisos_com(_JOB, []) == []
    assert main._avisos_com(_JOB, [], saem=[_VELHO]) is None
    assert main._avisos_com(_JOB, [_NOVO], saem=[_VELHO]) == [_NOVO]


def test_sai_pelo_texto_EXATO_nunca_por_prefixo(monkeypatch, logs):
    parecido = _VELHO + " (outra rota)"
    banco = _Banco([_VELHO, parecido])
    _no_banco(monkeypatch, banco)
    assert main._avisos_com(_JOB, [], saem=[_VELHO]) == [parecido]


def test_o_estagio_do_log_e_diagnostico_e_a_falha_nao():
    assert "motor:avisos-velhos" in main._STAGES_DIAGNOSTICO
    assert "motor:avisos-velhos-sem-lista" not in main._STAGES_DIAGNOSTICO


# ── Erro e anexo que falhou: NADA sai, e o que eles gravaram entra na lista ──
def test_o_ramo_de_erro_nao_tira_nada_e_SOMA_o_dele_a_lista(monkeypatch, logs):
    from test_erro_nao_apaga_o_que_o_motor_descobriu import (
        _codigo_do_except_do_process_job, _JobsFalso)
    banco = _Banco([_VELHO, _DA_ROTA], avisos_do_motor=[_VELHO])
    _no_banco(monkeypatch, banco)

    class _PD:
        warnings = [_VELHO2]

    escopo = {
        "e": RuntimeError("a IA devolveu 0 itens"), "job_id": _JOB,
        "jobs": _JobsFalso(), "project_data": _PD(), "is_complement": False,
        "_log_error": main._log_error, "_supabase_update": banco.rpc,
        "_avisos_com": main._avisos_com,
        "_lembrar_avisos_do_motor": main._lembrar_avisos_do_motor,
        "_TRANSIENT_ERR_RX": re.compile("sobrecarregad|timeout", re.I),
        "_email_falha_cliente": lambda *a, **k: None,
        "_tipo_e_tela_da_falha": main._tipo_e_tela_da_falha,
        "_registrar_tipo_da_falha": lambda *a, **k: None,
        "print": lambda *a, **k: None,
    }
    exec(_codigo_do_except_do_process_job(), escopo)
    assert banco.linha["warnings"] == [_VELHO, _DA_ROTA, _VELHO2], banco.linha["warnings"]
    assert banco.linha["avisos_do_motor"] == [_VELHO, _VELHO2], banco.linha["avisos_do_motor"]

    # e a próxima passada que der certo tira os dois
    _roda_o_fim(banco, [_NOVO], monkeypatch)
    assert banco.linha["warnings"] == [_DA_ROTA, _NOVO], banco.linha["warnings"]


def test_o_anexo_que_falhou_mantem_os_avisos_e_SOMA_o_dele(monkeypatch, logs):
    banco = _Banco([_VELHO, _DA_ROTA], avisos_do_motor=[_VELHO])
    _no_banco(monkeypatch, banco)
    monkeypatch.setattr(main, "_ler_marca_do_anexo", lambda j: (False, None))
    monkeypatch.setattr(main, "_email_anexo_sem_mudanca", lambda *a, **k: None)
    monkeypatch.setattr(main, "_limpar_marca_do_anexo", lambda *a, **k: True)
    aviso = "⚠ O arquivo anexado não pôde ser lido — a planilha anterior foi mantida."
    assert main._anexo_falhou_mantem_a_base(_JOB, "falhou", aviso) is True
    assert banco.linha["warnings"] == [_VELHO, _DA_ROTA, aviso], banco.linha["warnings"]
    assert banco.linha["avisos_do_motor"] == [_VELHO, aviso], banco.linha["avisos_do_motor"]

    # o próximo anexo que der certo tira o "planilha anterior mantida" também
    _roda_o_fim(banco, [], monkeypatch)
    assert banco.linha["warnings"] == [_DA_ROTA], banco.linha["warnings"]


def test_so_o_fim_da_passada_que_deu_certo_tira_aviso():
    """🪤 Pôr `saem=` no erro, no anexo que falhou ou dentro do próprio
    `_avisos_com` apagaria os avisos da planilha que FICOU."""
    arv = ast.parse(fonte("main.py"))
    com_saem = [n.lineno for n in ast.walk(arv)
                if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_avisos_com"
                and any(k.arg == "saem" for k in n.keywords)]
    assert len(com_saem) == 1, "esperava UMA chamada com saem=, achei %r" % com_saem
    pj = [n for n in ast.walk(arv)
          if isinstance(n, ast.FunctionDef) and n.name == "process_job"][0]
    assert pj.lineno < com_saem[0] <= pj.end_lineno, "o saem= saiu do process_job"
    assert "saem=" in _fim_da_passada_que_deu_certo()


def test_a_migracao_da_coluna_esta_no_repo():
    caminho = os.path.join(os.path.dirname(_AQUI), "migrations_pendentes",
                           "projects_avisos_do_motor.sql")
    sql = open(caminho, encoding="utf-8").read().lower()
    assert "add column if not exists avisos_do_motor jsonb" in sql
