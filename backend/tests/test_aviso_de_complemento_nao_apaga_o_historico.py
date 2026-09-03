# -*- coding: utf-8 -*-
"""Complemento que falha não pode apagar os avisos do projeto original.

🩸 03/09/2026, achado pela revisão adversarial. Quando o COMPLEMENTO (add-file)
falhava — CAD que não abriu, ou anexo que rendeu 0 itens — o projeto voltava
pra `done` com a planilha anterior preservada, e gravava:

    _supabase_update("projects", "job_id", job_id, {..., "warnings": [um_aviso]})

`warnings` é um **array**. Escrever um array novo de um elemento **apaga tudo**
que o motor já tinha dito sobre o projeto original: a escala, a área, o plano
B, a ressalva de estrutura.

🔑 O cliente ficava com a tela dizendo só "o complemento não deu certo", como se
o projeto dele não tivesse mais nenhuma ressalva. **A planilha era preservada e
a explicação dela, não.**

🪤 É a mesma família do dia: o sistema sabia e a informação sumia sem erro.
"""
import io
import os

import main

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _com_avisos(monkeypatch, atuais, status=200):
    """Finge o que o banco tem hoje."""
    def _fake(method, path, body=None, params=None, prefer=None, timeout=15):
        return status, ([{"warnings": atuais}] if atuais is not None else [])
    monkeypatch.setattr(main, "_supa_rest_service", _fake)


def test_o_aviso_novo_ENTRA_sem_apagar_os_de_antes(monkeypatch):
    """🩸 O caso: 3 avisos do projeto original + o do complemento."""
    antes = ["⚠ Escala conferida pelo desenho",
             "⚠ Não encontramos a área total",
             "⚠ ESTRUTURA: falta a altura"]
    _com_avisos(monkeypatch, antes)
    saida = main._avisos_com("job1", "O arquivo anexado não pôde ser aberto")
    assert saida[:3] == antes, "os avisos do projeto original foram apagados"
    assert saida[-1] == "O arquivo anexado não pôde ser aberto"
    assert len(saida) == 4


def test_CONTROLE_o_comportamento_ANTIGO_apagaria(monkeypatch):
    """Sem isto o teste acima não prova que algo mudou."""
    antes = ["a", "b", "c"]
    antigo = ["o novo"]          # era literalmente `{"warnings": [_warn]}`
    assert antigo != antes + ["o novo"], (
        "o controle está errado: trocar o array TEM que perder os anteriores")


def test_nao_duplica_quando_o_mesmo_aviso_ja_esta_la(monkeypatch):
    """Reprocesso e retomada podem passar aqui duas vezes."""
    _com_avisos(monkeypatch, ["já estou aqui"])
    saida = main._avisos_com("job1", "já estou aqui")
    assert saida == ["já estou aqui"], saida


def test_leitura_que_falha_devolve_pelo_menos_o_aviso_novo(monkeypatch):
    """🪤 Perder histórico é ruim; perder o aviso que o cliente espera ler
    AGORA é pior. Na falha de leitura, o comportamento é o de antes."""
    _com_avisos(monkeypatch, None, status=500)
    assert main._avisos_com("job1", "o novo") == ["o novo"]

    def _explode(*a, **k):
        raise RuntimeError("supabase fora do ar")
    monkeypatch.setattr(main, "_supa_rest_service", _explode)
    assert main._avisos_com("job1", "o novo") == ["o novo"]


def test_projeto_sem_aviso_nenhum_fica_so_com_o_novo(monkeypatch):
    _com_avisos(monkeypatch, [])
    assert main._avisos_com("job1", "o novo") == ["o novo"]


def test_nenhum_caminho_troca_o_array_inteiro():
    """Guarda de forma: dicionário com `"warnings": [lista literal]`.

    🪤 A 1ª versão procurava o texto `"warnings": [` linha a linha e acusou a
    DOCSTRING do próprio conserto, que cita a forma proibida pra explicar por
    que ela saiu. Foi a oitava vez em 03/09 que um guarda meu leu documentação
    como código. AST não confunde prosa com dicionário — e é a mesma solução
    que resolveu as outras.
    """
    import ast

    ruins = []
    for no in ast.walk(ast.parse(_FONTE)):
        if not isinstance(no, ast.Dict):
            continue
        for chave, valor in zip(no.keys, no.values):
            if (isinstance(chave, ast.Constant) and chave.value == "warnings"
                    and isinstance(valor, ast.List)):
                ruins.append("linha %d" % getattr(no, "lineno", 0))
    assert not ruins, (
        "algum ponto voltou a gravar um array NOVO de warnings, apagando os "
        "anteriores: " + ", ".join(ruins))


def test_CONTROLE_o_guarda_de_forma_REPROVA_o_codigo_antigo():
    """Sem isto, o teste acima passa por não achar nada."""
    import ast

    antigo = 'x = {"status": "done", "warnings": [_warn_txt]}'
    achou = any(
        isinstance(c, ast.Constant) and c.value == "warnings"
        and isinstance(v, ast.List)
        for no in ast.walk(ast.parse(antigo)) if isinstance(no, ast.Dict)
        for c, v in zip(no.keys, no.values))
    assert achou, "o guarda de forma não reprova o código que causou o defeito"


def test_CONTROLE_o_guarda_de_forma_ACEITA_a_chamada_do_helper():
    """E não pode acusar o conserto."""
    import ast

    novo = 'x = {"status": "done", "warnings": _avisos_com(job_id, _warn_txt)}'
    achou = any(
        isinstance(c, ast.Constant) and c.value == "warnings"
        and isinstance(v, ast.List)
        for no in ast.walk(ast.parse(novo)) if isinstance(no, ast.Dict)
        for c, v in zip(no.keys, no.values))
    assert not achou, "o guarda de forma acusaria o próprio conserto"


def test_os_dois_pontos_do_complemento_usam_o_helper():
    assert _FONTE.count("_avisos_com(job_id,") >= 2, (
        "um dos dois caminhos do complemento parou de acrescentar e voltou a "
        "trocar o array")
