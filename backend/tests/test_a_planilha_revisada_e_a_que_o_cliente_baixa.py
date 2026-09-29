# -*- coding: utf-8 -*-
"""A planilha que o cliente baixa é a ÚLTIMA que a gente gerou.

🩸 29/09/2026. `rebuild_planilha_from_review` (o "Exportar .xlsx" da tela de
revisão, o /finalize, e o refazer-planilha do admin) gerava o arquivo como
`orcamento_<job>_revisado.xlsx` e subia pro Storage — mas o /api/download
entrega PRIMEIRO a cópia local `orcamento_<job>.xlsx`, que o processamento
deixa no disco até o próximo deploy. O cliente revisava, clicava em Exportar e
levava a planilha de ANTES da revisão. No log de downloads (desde 15/09), 5
clientes baixaram depois da última atualização com um arquivo de tamanho
diferente do Storage — um revisou 162 linhas e levou 43.925 bytes, o Storage
tinha 25.023.
🔑 Uma porta só pra publicar: `_publicar_planilha` sobe e troca a cópia que o
download entrega. Se não der pra trocar, a velha SAI — aí o download busca no
Storage, que é a nova.
"""
import ast
import io
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import main  # noqa: E402

JOB = "ab12cd34"


@pytest.fixture
def disco(tmp_path, monkeypatch):
    """WORK_DIR num tmp, Storage de mentira que guarda o que recebeu."""
    monkeypatch.setattr(main, "WORK_DIR", str(tmp_path))
    storage = {}

    def _sobe(local, chave):
        with open(local, "rb") as fh:
            storage[chave] = fh.read()
        return True

    def _desce(chave, local):
        if chave not in storage:
            return False
        os.makedirs(os.path.dirname(local), exist_ok=True)
        with open(local, "wb") as fh:
            fh.write(storage[chave])
        return True

    monkeypatch.setattr(main, "_supabase_storage_upload", _sobe)
    monkeypatch.setattr(main, "_supabase_storage_download", _desce)
    return tmp_path, storage


def _grava(caminho, conteudo):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "wb") as fh:
        fh.write(conteudo)


def _o_que_o_download_entrega():
    p = main.get_planilha_path(JOB)
    with open(p, "rb") as fh:
        return fh.read()


def test_a_revisada_substitui_a_copia_que_o_download_entrega(disco):
    tmp, storage = disco
    _grava(main._planilha_local(JOB), b"ANTES DA REVISAO")        # a do processamento
    gerada = os.path.join(str(tmp), JOB, "orcamento_%s_revisado.xlsx" % JOB)
    _grava(gerada, b"REVISADA")
    assert main._publicar_planilha(JOB, gerada) is True
    assert storage["%s.xlsx" % JOB] == b"REVISADA"
    assert _o_que_o_download_entrega() == b"REVISADA"


def test_o_caminho_do_processamento_so_sobe(disco):
    """Processamento e informar-área já geram no caminho que o download entrega."""
    _, storage = disco
    alvo = main._planilha_local(JOB)
    _grava(alvo, b"PROCESSADA")
    assert main._publicar_planilha(JOB, alvo) is True
    assert storage["%s.xlsx" % JOB] == b"PROCESSADA"
    assert _o_que_o_download_entrega() == b"PROCESSADA"


def test_sem_copia_local_a_revisada_vira_a_copia(disco):
    """Depois de um deploy o disco está vazio: a revisada passa a ser a local."""
    tmp, _ = disco
    gerada = os.path.join(str(tmp), JOB, "orcamento_%s_revisado.xlsx" % JOB)
    _grava(gerada, b"REVISADA")
    main._publicar_planilha(JOB, gerada)
    assert _o_que_o_download_entrega() == b"REVISADA"


def test_se_nao_da_pra_trocar_a_velha_sai_e_o_download_busca_no_storage(disco, monkeypatch):
    tmp, _ = disco
    _grava(main._planilha_local(JOB), b"ANTES DA REVISAO")
    gerada = os.path.join(str(tmp), JOB, "orcamento_%s_revisado.xlsx" % JOB)
    _grava(gerada, b"REVISADA")

    def _falha(*a, **k):
        raise OSError("disco")
    with monkeypatch.context() as m:
        m.setattr(main.os, "replace", _falha)
        main._publicar_planilha(JOB, gerada)
    assert _o_que_o_download_entrega() == b"REVISADA"


# ══════════════════════════════════════════════════════════════════════════
#  Os três que geram a planilha passam pela porta — e ninguém sobe por fora
# ══════════════════════════════════════════════════════════════════════════
def _arvore():
    return ast.parse(io.open(os.path.join(os.path.dirname(_AQUI), "main.py"),
                             encoding="utf-8").read())


def _funcoes(arv):
    return {n.name: n for n in ast.walk(arv)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _chama(fn, nome):
    return [n for n in ast.walk(fn) if isinstance(n, ast.Call)
            and getattr(n.func, "id", "") == nome]


def _e_o_nome_servido(no):
    """`os.path.join(<dir>, f"orcamento_{job_id}.xlsx")` — o nome que o download serve."""
    if not (isinstance(no, ast.Call) and getattr(no.func, "attr", "") == "join" and no.args):
        return False
    ult = no.args[-1]
    if not isinstance(ult, ast.JoinedStr):
        return False
    p = ult.values
    return (len(p) == 3 and isinstance(p[0], ast.Constant) and p[0].value == "orcamento_"
            and isinstance(p[1], ast.FormattedValue) and getattr(p[1].value, "id", "") == "job_id"
            and isinstance(p[2], ast.Constant) and p[2].value == ".xlsx")


def test_quem_sobe_a_planilha_por_fora_da_porta_sobe_o_arquivo_que_o_download_serve():
    """`_supabase_storage_upload(X, f"{job_id}.xlsx")` fora de `_publicar_planilha`
    só com X = `orcamento_{job_id}.xlsx`. Um caminho novo que gere com outro nome
    e suba direto repete o defeito."""
    arv = _arvore()
    porta = _funcoes(arv)["_publicar_planilha"]
    dentro = {id(n) for n in ast.walk(porta)}
    diretos, errados, vistos = [], [], set()
    for fn in _funcoes(arv).values():      # de fora pra dentro: a externa fica com a chamada
        for n in ast.walk(fn):
            if not (isinstance(n, ast.Call)
                    and getattr(n.func, "id", "") == "_supabase_storage_upload"):
                continue
            if id(n) in dentro or id(n) in vistos or len(n.args) < 2 \
                    or not isinstance(n.args[1], ast.JoinedStr):
                continue
            vistos.add(id(n))
            partes = n.args[1].values
            if not (len(partes) == 2 and isinstance(partes[-1], ast.Constant)
                    and partes[-1].value == ".xlsx"):
                continue
            diretos.append(fn.name)
            nome = getattr(n.args[0], "id", None)
            atribs = [a.value for a in ast.walk(fn) if isinstance(a, ast.Assign)
                      and any(getattr(t, "id", None) == nome for t in a.targets)]
            if not atribs or not all(_e_o_nome_servido(v) for v in atribs):
                errados.append("%s:%d" % (fn.name, n.lineno))
    assert sorted(diretos) == ["inform_project_area", "process_job"], diretos
    assert not errados, "sobe `<job>.xlsx` de um arquivo que o download não serve: %s" % errados


def test_o_rebuild_publica_pela_porta():
    fn = _funcoes(_arvore())["rebuild_planilha_from_review"]
    assert _chama(fn, "_publicar_planilha")
    assert not [n for n in _chama(fn, "_supabase_storage_upload")]


def test_o_download_le_o_mesmo_caminho_que_a_porta_troca():
    fn = _funcoes(_arvore())["get_planilha_path"]
    assert _chama(fn, "_planilha_local")
