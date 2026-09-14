# -*- coding: utf-8 -*-
"""Quando o ODA recusa um DWG, o log diz POR QUE.

🩸 14/09/2026 — três clientes seguidos tiveram o DWG recusado pelo ODA, e o log
só dizia "(ODA recusou)". Medido em 45 dias e 60 jobs com DWG: **49 caíram no
libredwg** (82%), 8 o ODA deu conta, e 6 tiveram arquivo que não converteu de
jeito nenhum. Sem o motivo não dá pra decidir se vale consertar a conversão —
versão do CAD, objeto AEC e arquivo quebrado pedem consertos diferentes.

🔑 O motivo EXISTIA: o ODA escreve num `.dxf.err` que o código já lia, e o texto
morria num tempdir que o Render apaga. Agora ele viaja até o `error_log`.

🩸 A 1ª versão DESTE arquivo repetia a lógica de recorte dentro do teste, e a
mutação provou o estrago: 3 de 5 mutantes sobreviveram — dava pra parar de
capturar o motivo, pra guardar só a linha genérica, e pro log voltar a ser texto
fixo, tudo verde. Teste que repete a régua não reprova quando a régua muda
([[feedback_nao_reimplemente_a_regua_pergunte_ao_guarda]]).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dwg_extractor as dx  # noqa: E402

# O texto que o ODA escreveu de verdade hoje, no job de um cliente (nome do
# arquivo trocado — repositório público, regra dura nº6).
_ERR_REAL = ('OdError thrown during readFile of drawing '
             '"/tmp/aiarq_jobs/xxxxxxxx/PRANCHA-CLIENTE-NN.dwg" :\n'
             'Unexpected end of file\n')


def test_o_motivo_REAL_sobrevive_e_cabe_numa_linha():
    """Chama a função do motor, não uma cópia."""
    d = dx.detalhe_do_err(_ERR_REAL)
    assert "Unexpected end of file" in d, (
        "o motivo real ficou de fora — é a parte DEPOIS do 'OdError thrown': %r" % d)
    assert "OdError thrown" in d, "o contexto do erro sumiu: %r" % d
    assert "\n" not in d and "\r" not in d, "quebra de linha não cabe no log do banco"
    assert len(d) <= 240


def test_CONTROLE_so_a_linha_generica_NAO_basta():
    """🪤 O defeito que a gente está consertando: parar na 1ª linha devolve uma
    frase que termina em dois-pontos e não diz nada."""
    so_generica = 'OdError thrown during readFile of drawing "/tmp/x/A.dwg" :\n'
    d = dx.detalhe_do_err(so_generica)
    assert d.rstrip().endswith(":"), d
    assert "Unexpected" not in d


def test_CONTROLE_vazio_nao_vira_motivo_inventado():
    assert dx.detalhe_do_err("") == ""
    assert dx.detalhe_do_err(None) == ""
    assert dx.detalhe_do_err("   \n  \n ") == ""


def test_arquivo_sem_erro_registrado_devolve_vazio():
    """Prova que sabe dizer 'não sei': quem não falhou não ganha motivo."""
    assert dx.dwg_failure_detail("/tmp/nunca-vi-esse.dwg") == ""
    assert dx.dwg_failure_detail("") == ""


def test_o_detalhe_fica_guardado_POR_ARQUIVO():
    """O job tem vários DWG; o motivo de um não pode vazar pro outro."""
    dx._FALHA_DETALHE["A.dwg"] = dx.detalhe_do_err(_ERR_REAL)
    assert "Unexpected end of file" in dx.dwg_failure_detail("/tmp/qualquer/A.dwg")
    assert dx.dwg_failure_detail("/tmp/qualquer/B.dwg") == ""


def test_a_classificacao_ANTIGA_continua_funcionando():
    """`dwg_failure_reason` decide o CONSELHO que o cliente lê ('truncado' manda
    reabrir no CAD, não exportar DXF). O detalhe novo não pode ter roubado isso."""
    dx._FALHA_MOTIVO["PRANCHA-CLIENTE-NN.dwg"] = "truncado"
    assert dx.dwg_failure_reason("/x/PRANCHA-CLIENTE-NN.dwg") == "truncado"
    assert dx.dwg_failure_reason("/x/outro.dwg") == ""


def test_o_motor_PoE_o_motivo_DENTRO_da_mensagem_do_log():
    """🪤 Ponto de chamada, cobrado pela ESTRUTURA: não basta `dwg_failure_detail`
    existir no arquivo — a variável com o motivo tem que estar interpolada na
    mensagem que vai pro banco. A 1ª versão deste guarda só via a f-string e
    deixou passar o mutante que devolvia o texto fixo de antes."""
    import ast
    import io
    caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    arv = ast.parse(io.open(caminho, encoding="utf-8").read())

    alvo = None
    for no in ast.walk(arv):
        if (isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
                and no.func.id == "_log_error" and no.args
                and isinstance(no.args[0], ast.Constant)
                and no.args[0].value == "libredwg:usado-no-fluxo"):
            alvo = no
            break
    assert alvo is not None, "não achei o registro do fallback do libredwg"
    assert len(alvo.args) > 1, "o log do fallback perdeu a mensagem"

    nomes = {d.id for d in ast.walk(alvo.args[1])
             if isinstance(d, ast.Name)}
    assert any("oda" in n.lower() or "motivo" in n.lower() or "det" in n.lower()
               for n in nomes), (
        "a mensagem do fallback não carrega a variável do motivo (só achei %s) — "
        "o log volta a dizer 'ODA recusou' sem o porquê" % sorted(nomes))

def test_quem_LE_o_err_GUARDA_o_motivo():
    """🪤 O elo que faltava, e a mutação achou: dá pra ter a função certa, o log
    certo — e ninguém guardando nada. O bloco que lê o `.dxf.err` mora dentro de
    `convert_dwg_to_dxf`, que só roda com o ODA instalado; aqui a cobrança é
    pela ESTRUTURA: aquele bloco tem que escrever em `_FALHA_DETALHE` usando
    `detalhe_do_err`."""
    import ast
    import io as _io
    caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "dwg_extractor.py")
    arv = ast.parse(_io.open(caminho, encoding="utf-8").read())
    fn = next((n for n in ast.walk(arv)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == "convert_dwg_to_dxf"), None)
    assert fn is not None, "não achei `convert_dwg_to_dxf`"

    guarda = []
    for no in ast.walk(fn):
        if not isinstance(no, ast.Assign):
            continue
        escreve = any(isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
                      and t.value.id == "_FALHA_DETALHE" for t in no.targets)
        if not escreve:
            continue
        usa = any(isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
                  and d.func.id == "detalhe_do_err" for d in ast.walk(no.value))
        guarda.append(usa)
    assert guarda, (
        "`convert_dwg_to_dxf` não guarda motivo nenhum em `_FALHA_DETALHE` — "
        "o log vai dizer 'motivo não registrado' pra sempre")
    assert all(guarda), (
        "o motivo está sendo guardado sem passar por `detalhe_do_err` — a régua "
        "de uma linha só deixa de valer")
