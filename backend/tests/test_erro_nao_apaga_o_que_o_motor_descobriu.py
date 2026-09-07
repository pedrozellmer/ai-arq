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

import pytest

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
# ── helpers: o except do process_job, tirado por AST e RODADO ──────────
import ast as _ast
_ARVORE = _ast.parse(fonte("main.py"))


def _codigo_do_except_do_process_job():
    """O corpo do `except` de `process_job` — o código REAL, pronto pra rodar."""
    achados = []
    for no in _ast.walk(_ARVORE):
        if not (isinstance(no, _ast.FunctionDef) and no.name == "process_job"):
            continue
        for t in _ast.walk(no):
            if not isinstance(t, _ast.Try):
                continue
            for h in t.handlers:
                txt = _ast.unparse(_ast.Module(body=h.body, type_ignores=[]))
                if "_avisos_ate_aqui" in txt and "_supabase_update" in txt:
                    achados.append(txt)
    assert len(achados) == 1, (
        "esperava UM except de process_job que salve avisos e grave no banco, "
        "achei %d" % len(achados))
    return achados[0]


class _JobsFalso:
    def __init__(self):
        self.campos = {}

    def update_field(self, job_id, **kw):
        self.campos.update(kw)


#: O job usado em todo este arquivo — a linha que o pacote TEM que endereçar.
_JOB = "job-de-teste"


def _rodar_o_except(project_data=..., log_error=None, erro=None,
                    avisos_no_banco=("aviso que JA estava no banco",)):
    """Executa o tratamento de erro de verdade e devolve (pacotes, logs).

    🔬 07/09/2026 — o `_avisos_com` aqui é o DE PRODUÇÃO, não um dublê. A versão
    anterior injetava uma cópia que fundia as duas listas, e a asserção sobre o
    clobber de 04/09 media o dublê, não o motor: apagar a fusão real no main.py
    deixava este arquivo verde. Agora só o acesso ao banco é dublado
    (`_supa_rest_service`), e a fusão que roda é a que vai pro ar.
    """
    import re
    pacotes, logs = [], []

    def _log(stage, message, job_id=None, severity="error"):
        logs.append((stage, message, severity))
        if log_error:
            log_error(stage, message, job_id, severity)

    escopo = {
        "e": erro or RuntimeError("a IA devolveu 0 itens"),
        "job_id": _JOB,
        "jobs": _JobsFalso(),
        "_log_error": _log,
        "_supabase_update": lambda tab, campo, valor, dados:
            pacotes.append({"tabela": tab, "campo": campo,
                            "valor": valor, "dados": dados}),
        "_avisos_com": m._avisos_com,          # 🔑 o de produção
        "_TRANSIENT_ERR_RX": re.compile("sobrecarregad|timeout", re.I),
        "_email_falha_cliente": lambda *a, **k: None,
        "print": lambda *a, **k: None,
    }
    if project_data is not ...:
        escopo["project_data"] = project_data

    _orig = m._supa_rest_service

    def _rest(metodo, caminho, **kw):
        if metodo == "GET" and str(caminho).startswith("projects"):
            return 200, [{"warnings": list(avisos_no_banco)}]
        return 200, []
    m._supa_rest_service = _rest
    try:
        exec(_codigo_do_except_do_process_job(), escopo)
    finally:
        m._supa_rest_service = _orig
    return pacotes, logs


def test_o_erro_SALVA_os_avisos_acumulados():
    """🩸 94 projetos em erro (42 de cliente) com ZERO aviso gravado."""
    class _PD:
        warnings = ["prancha 03 cortada por tamanho",
                    "plano B do conversor acionado"]

    pacotes, _logs = _rodar_o_except(project_data=_PD())
    assert len(pacotes) == 1, pacotes
    dados = pacotes[0]["dados"]
    assert dados.get("status") == "error"
    assert "warnings" in dados, (
        "o pacote de erro voltou a gravar só status e mensagem — os %d avisos "
        "que o motor tinha acumulado morreram junto com o job" % len(_PD.warnings))
    for _a in _PD.warnings:
        assert _a in dados["warnings"], (
            "o aviso %r não chegou ao banco: %r" % (_a, dados["warnings"]))
    assert "aviso que JA estava no banco" in dados["warnings"], (
        "o pacote passou por cima do que já estava lá (o clobber de 04/09)")


@pytest.mark.parametrize("no_banco,do_motor,esperado", [
    # o caso normal: o que já estava lá VEM PRIMEIRO e o do motor entra atrás
    (["prancha perdida no storage"],
     ["prancha 03 cortada", "plano B acionado"],
     ["prancha perdida no storage", "prancha 03 cortada", "plano B acionado"]),
    # banco vazio: só o do motor, sem inventar linha
    ([], ["plano B acionado"], ["plano B acionado"]),
    # repetido não duplica (o cliente lia o mesmo aviso duas vezes)
    (["plano B acionado"], ["plano B acionado", "escala não validada"],
     ["plano B acionado", "escala não validada"]),
])
def test_a_fusao_do_ramo_de_erro_e_a_DE_PRODUCAO(no_banco, do_motor, esperado):
    """🚨 07/09/2026 — a asserção do clobber media o DUBLÊ.

    Aqui a lista sai igualzinha, em ordem e sem repetição, com o `_avisos_com`
    de produção no caminho. Apagar a fusão real (voltar a gravar só o array de
    memória) reprova nos três casos.
    """
    class _PD:
        warnings = list(do_motor)

    pacotes, _ = _rodar_o_except(project_data=_PD(), avisos_no_banco=no_banco)
    assert pacotes[0]["dados"].get("warnings") == esperado, (
        "com %r no banco e %r do motor, o pacote gravaria %r"
        % (no_banco, do_motor, pacotes[0]["dados"].get("warnings")))


def test_o_pacote_de_erro_ENDERECA_a_linha_certa():
    """🪤 07/09/2026 — lacuna do cético: `tabela`, `campo` e `valor` eram
    capturados pelo dublê e IGNORADOS pela asserção. Um pacote perfeito
    endereçado a `projects.id` (em vez de `job_id`) não acha linha nenhuma:
    o UPDATE não estoura, não grava, e o guarda seguia verde — a escrita que
    falha calada de novo, agora no próprio conserto contra escrita calada.
    """
    class _PD:
        warnings = ["prancha 03 cortada por tamanho"]

    pacotes, _ = _rodar_o_except(project_data=_PD())
    p = pacotes[0]
    assert (p["tabela"], p["campo"], p["valor"]) == ("projects", "job_id", _JOB), (
        "o pacote de erro foi endereçado a %r/%r=%r — fora de "
        "`projects.job_id` ele não casa com linha nenhuma e o UPDATE não grava"
        % (p["tabela"], p["campo"], p["valor"]))


def test_a_mensagem_do_cliente_vai_INTEIRA_no_pacote():
    """🚨 O corte era [:500] e decapitava a instrução ("1. Abra o arqui").
    Conteúdo, não presença: o guarda confere a ÚLTIMA frase, que é a que
    diz ao cliente o que fazer."""
    passos = ("Não consegui ler este arquivo. 1. Abra o arquivo no seu CAD. "
              "2. Exporte como DXF. 3. Suba o arquivo novo aqui no site.")
    pacotes, _ = _rodar_o_except(erro=RuntimeError(passos))
    assert pacotes[0]["dados"].get("error_message") == passos, (
        "a mensagem chegou ao banco como %r — o cliente fica sabendo que deu "
        "errado e não o que fazer" % (pacotes[0]["dados"].get("error_message"),))


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
