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


def test_uma_LISTA_de_avisos_tambem_entra_sem_apagar(monkeypatch):
    """🩸 04/09 — o helper só aceitava UM aviso, e por isso os dois pontos que
    gravam a lista inteira do motor (`project_data.warnings`, no fim do job e
    no ramo de erro) ficaram de fora do conserto de ontem: eles seguiam
    escrevendo o array de memória por cima do banco.

    Na prática isso apagava o aviso de prancha perdida que a retomada acabava
    de gravar — o conserto de um caminho destruído pelo outro.
    """
    _com_avisos(monkeypatch, ["⚠ Escala conferida pelo desenho"])
    saida = main._avisos_com("job1", ["⚠ do motor A", "⚠ do motor B"])
    assert saida == ["⚠ Escala conferida pelo desenho",
                     "⚠ do motor A", "⚠ do motor B"], saida


def test_a_lista_tambem_nao_duplica_nem_deixa_entrar_vazio(monkeypatch):
    _com_avisos(monkeypatch, ["já estou aqui"])
    saida = main._avisos_com("job1", ["já estou aqui", "  ", "", "novo"])
    assert saida == ["já estou aqui", "novo"], saida


def test_CONTROLE_o_comportamento_ANTIGO_apagaria(monkeypatch):
    """🧪 Trocar o array TEM que perder os anteriores — provado no helper.

    🪤 04/09: este controle comparava duas listas escritas nele mesmo
    (`["o novo"] != ["a","b","c","o novo"]`), sem tocar em `_avisos_com`.
    Aritmética, não controle. Agora o comportamento ANTIGO é aplicado ao MESMO
    insumo do teste de cima, pela mesma via.
    """
    antes = ["⚠ Escala conferida pelo desenho", "⚠ ESTRUTURA: falta a altura"]
    _com_avisos(monkeypatch, antes)
    novo = "O arquivo anexado não pôde ser aberto"

    def _antigo(_job, aviso):
        return [aviso]           # era literalmente `{"warnings": [_warn]}`

    assert _antigo("job1", novo) == [novo]
    assert main._avisos_com("job1", novo) == antes + [novo], (
        "o helper parou de preservar o histórico — voltou a ser o antigo")


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
    """O julgamento mora em `test_prancha_perdida_no_storage_nao_some_calada`.

    🩸 04/09, varredura adversarial: a versao daqui tinha DOIS furos.
    (1) So enxergava lista LITERAL, entao bastava passar por uma variavel
        (`{"warnings": _lst_novo}`) pra escapar - provado por mutacao.
    (2) Nao distinguia INSERT de UPDATE, e reprovou um `_supabase_insert`
        LEGITIMO: linha nova nao tem historico pra apagar.

    O julgamento novo cobre as duas coisas e roda la, com controle positivo
    sobre cinco formas. Aqui fica so o elo, pra quem chegar por este arquivo
    saber onde procurar.
    """
    from test_prancha_perdida_no_storage_nao_some_calada import (
        _updates_que_trocam_o_array)
    ruins = _updates_que_trocam_o_array(_FONTE)
    assert not ruins, (
        "UPDATE gravando `warnings` sem ler o que ja existe: linha %s"
        % ", ".join(str(n) for n in ruins))


def test_os_pontos_que_acrescentam_usam_o_helper():
    """🩸 04/09: era `_FONTE.count("_avisos_com(job_id,") >= 2` - e a
    PROPRIA DEFINICAO da funcao casa essa string. Com 3 ocorrencias no fonte
    (1 def + 2 usos), um dos usos podia sumir que a conta ainda fechava.
    Provado por mutacao: devolvi o defeito num dos dois e o arquivo inteiro
    ficou verde.

    🔑 Agora conta CHAMADAS por AST, que nao inclui a definicao.
    """
    import ast
    chamadas = [n.lineno for n in ast.walk(ast.parse(_FONTE))
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "_avisos_com"]
    assert len(chamadas) >= 4, (
        "esperava pelo menos 4 chamadas a `_avisos_com` (os 2 do complemento, "
        "o fim do job e o ramo de erro) e achei %d, nas linhas %s"
        % (len(chamadas), chamadas))
