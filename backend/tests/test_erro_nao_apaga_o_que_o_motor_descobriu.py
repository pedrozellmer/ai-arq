# -*- coding: utf-8 -*-
"""Projeto que dá erro perdia tudo que o motor já tinha descoberto.

🩸 03/09/2026, achado pela varredura "o que mais nasce morto". O `except` do
`process_job` gravava `status` e `error_message` — e mais nada. Os avisos que o
motor já tinha acumulado sobre as pranchas (prancha cortada por tamanho, plano
B do conversor acionado, página não lida, escala não validada) morriam junto
com o job.

📏 Medido: **94 projetos em erro, 42 de cliente, com ZERO aviso gravado** —
contra 59% dos concluídos que têm aviso. O cliente lia só "deu erro". E nós
também: o estado se perdia pra sempre, então nem dava pra investigar depois.

🪤 A ARMADILHA DESTE CONSERTO: `project_data` nasce DEPOIS do `try` começar. Se
a falha for precoce, a variável não existe — e citá-la dentro do `except`
levantaria `NameError` ali, escondendo o erro ORIGINAL do cliente. Instrumento
que estoura dentro do tratamento de erro é pior que instrumento nenhum.

🔑 `warnings` é um dos sete campos que a RPC `update_project_status` aceita
(ver [[test_update_de_projeto_nao_descarta_campo]]), então vai no MESMO pacote
— sem chamada extra e sem risco de outra escrita falhar calada.
"""
import os
import re
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main as m                                    # noqa: E402
from _corpo import corpo_de, fonte, sem_comentarios   # noqa: E402

# 🪤 NÃO dá pra usar `corpo_de("process_job")`: a função tem um prompt em
# f-string cujo texto começa na coluna 0, e o extrator cortava ali — devolvia
# 1.270 de ~3.900 linhas EM SILÊNCIO. Descoberto escrevendo este arquivo; o
# `corpo_de` agora reprova esse recorte em vez de entregar meia função.
# Aqui a âncora é o fonte inteiro, que não corta nada.
_CORPO = sem_comentarios(fonte("main.py"))


# ── O conserto ─────────────────────────────────────────────────────────────
def test_o_erro_SALVA_os_avisos_acumulados():
    """🩸 Os 94 projetos. Se cair, o motor volta a esquecer o que descobriu."""
    assert '"warnings": _avisos_ate_aqui' in _CORPO, (
        "o pacote de erro voltou a gravar só status e mensagem")
    assert "_avisos_ate_aqui" in _CORPO


def test_o_aviso_so_vai_QUANDO_EXISTE():
    """🧪 Gravar lista vazia por cima sobrescreveria aviso que já estivesse
    lá — e ainda faria parecer que a gente mediu algo que não mediu."""
    assert 'if _avisos_ate_aqui else {}' in _CORPO, (
        "o pacote passou a mandar `warnings` mesmo quando não há aviso")


def test_a_leitura_do_project_data_e_DEFENSIVA():
    """🪤 A variável nasce DEPOIS do try. Falha precoce → NameError dentro do
    except → o cliente perde o erro de verdade e recebe outro."""
    i = _CORPO.find("_avisos_ate_aqui = []")
    assert i > 0, "sumiu a inicialização defensiva"
    trecho = _CORPO[i:i + 400]
    assert "try:" in trecho and "except Exception:" in trecho, (
        "a leitura de project_data ficou sem proteção — instrumentação que "
        "estoura dentro do except esconde o erro original")
    assert 'getattr(project_data, "warnings", None)' in trecho, (
        "voltou a acessar project_data.warnings direto")


def test_CONTROLE_o_padrao_defensivo_REALMENTE_sobrevive_a_variavel_ausente():
    """🧪 Prova que o jeito escolhido funciona — não basta ter try/except em
    volta de qualquer coisa."""
    escopo = {}
    codigo = ("avisos = []\n"
              "try:\n"
              "    avisos = [str(a) for a in (getattr(project_data, 'warnings', None) or [])]\n"
              "except Exception:\n"
              "    avisos = []\n")
    exec(codigo, escopo)                      # project_data NÃO existe aqui
    assert escopo["avisos"] == [], "o padrão defensivo não sobreviveu"
    # e com a variável presente, ele lê
    class _PD:
        warnings = ["prancha cortada", "plano B acionado"]
    escopo2 = {"project_data": _PD()}
    exec(codigo, escopo2)
    assert escopo2["avisos"] == ["prancha cortada", "plano B acionado"]


# ── O rastro pra medir da próxima vez ──────────────────────────────────────
def test_registra_no_log_quantos_avisos_foram_salvos():
    assert '"motor:avisos-no-erro"' in _CORPO, (
        "sem rastro no log não dá pra saber se o conserto pegou")
    assert "salvos={len(_avisos_ate_aqui)}" in _CORPO


def test_o_stage_novo_e_DIAGNOSTICO():
    """🪤 Stage fora de _STAGES_DIAGNOSTICO entra como severity='error' e
    operação normal vira alarme vermelho no painel do admin."""
    assert "motor:avisos-no-erro" in m._STAGES_DIAGNOSTICO


def test_o_log_NAO_pode_derrubar_o_tratamento_de_erro():
    # 🪤 A âncora tem que ser a CHAMADA, não o nome solto: a primeira
    # ocorrência no arquivo é o registro em _STAGES_DIAGNOSTICO.
    i = _CORPO.find('_log_error("motor:avisos-no-erro"')
    assert i > 0
    assert "try:" in _CORPO[max(0, i - 200):i], (
        "o log do conserto ficou fora de try — falha de banco passaria a "
        "engolir o erro original do cliente")


# ── E o campo tem que sobreviver ao caminho de escrita ─────────────────────
def test_warnings_e_um_campo_que_a_RPC_ACEITA():
    """🔑 De nada adianta pôr no pacote se o caminho de escrita descarta —
    foi exatamente o que aconteceu com files_count e com os dados do projeto.
    A lista vem do próprio código, não escrita à mão aqui."""
    corpo_rpc = corpo_de("_rpc_update_project_status")
    aceitos = {k[2:] for k in re.findall(r'"(p_[a-z_]+)"\s*:', corpo_rpc)}
    assert "warnings" in aceitos, (
        "a RPC parou de aceitar `warnings` — o conserto vira escrita descartada")


def test_CONTROLE_a_checagem_da_RPC_sabe_REPROVAR():
    corpo_rpc = corpo_de("_rpc_update_project_status")
    aceitos = {k[2:] for k in re.findall(r'"(p_[a-z_]+)"\s*:', corpo_rpc)}
    assert "address" not in aceitos and len(aceitos) >= 5
