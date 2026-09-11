# -*- coding: utf-8 -*-
"""Zero item não vira "PDF escaneado" sem prova, e o alerta não afirma e-mail que não saiu.

🩸 11/09/2026 — orçamentista de construtora, 1º projeto: marcou "Estrutura" e mandou
3 PDFs VETORIAIS de arquitetura. O leitor vetorial mediu os três; o prompt de
estrutura devolveu 0 itens; o guarda "parece ARQUITETURA" não dispara com lista
vazia; e a mensagem disse "o PDF é uma imagem escaneada" e pediu "a planta exportada
do CAD" — o que ele tinha mandado. O alerta que chegou ao fundador afirmava "O
cliente já recebeu o email de falha" e o cliente não tinha recebido (nenhum registro
de envio). Ele reenviou duas vezes marcando Estrutura de novo; o projeto que deu
certo depois do anexo ficou "done" com o erro antigo gravado.

🩸 A revisão adversarial do 1º conserto pegou, ANTES de subir:
  1. `error_message=None` no store derrubava o /api/status com 500 em TODO projeto
     concluído (e as conclusões de complemento já faziam isso desde 15-16/07);
  2. no banco a limpeza era inerte: a RPC faz COALESCE e ignora None;
  3. o meu guarda de AST aprovava os dois defeitos e reprovava os consertos;
  4. a TELA seguia dizendo "PDF escaneado" pro vetorial, e no tipo Estrutura
     mandava "Salve em DXF" com o botão que anexa ao MESMO projeto Estrutura;
  5. o alerta diria "NÃO há registro" pra quem foi avisado pelo projeto irmão
     (freio de 15 min) — 18 de 20 casos medidos.

Estes guardas CHAMAM o código: `_mensagem_sem_itens`, `_build_falha_email`,
`_linha_do_email_ao_cliente`, `_supabase_update`, a rota `/api/status`, o fim real do
`process_job` (`_fim_do_job`), o alerta `_auto_retry_erros_transitorios` e as
receitas da tela rodando no duktape. AST só onde não dá pra chamar: o `raise` do
meio do `process_job`.
"""
import ast
import io
import json
import os
import sys
from datetime import datetime, timedelta
from urllib.parse import unquote

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
_RAIZ = os.path.dirname(_BACKEND)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main  # noqa: E402


# ── a mensagem do cliente ─────────────────────────────────────────────────────
def test_tipo_ESTRUTURA_sem_item_aponta_ler_como_arquitetura_e_nao_culpa_o_pdf():
    msg = main._mensagem_sem_itens(True, 3)
    assert "Ler como Arquitetura" in msg and "Estrutura" in msg, msg
    assert "escaneada" not in msg.lower() and "dxf" not in msg.lower(), msg


def test_PDF_vetorial_lido_nunca_vira_escaneado():
    msg = main._mensagem_sem_itens(False, 3)
    assert "escaneada" not in msg.lower(), msg
    assert "vetorial (3 pranchas)" in msg, msg
    assert "vetorial (1 prancha)" in main._mensagem_sem_itens(False, 1)


def test_CONTROLE_sem_sinal_nenhum_continua_o_texto_de_sempre():
    msg = main._mensagem_sem_itens(False, 0)
    assert "escaneada ou fotografada" in msg, msg


@pytest.mark.parametrize("args", [(True, 3), (True, 0), (False, 2), (False, 0)])
def test_nenhuma_das_mensagens_parece_erro_PASSAGEIRO(args):
    msg = main._mensagem_sem_itens(*args)
    assert not main._TRANSIENT_ERR_RX.search(msg), "cairia em auto-retry: %s" % msg


# ── o e-mail de falha ─────────────────────────────────────────────────────────
def _falha(msg):
    return main._build_falha_email("Fulano", "Edifício Teste", False, error_hint=msg)


def test_email_do_tipo_estrutura_aponta_o_reprocessar_e_nao_pede_outro_arquivo():
    subject, html = _falha(main._mensagem_sem_itens(True, 3))
    baixo = html.lower()
    assert "ler como arquitetura" in baixo, html[:900]
    # a arte falha-arquivo.png desenha "DWG → DXF, um ajuste no arquivo resolve"
    for proibido in ("escaneada", "dxf", "não vai resolver", "outro arquivo",
                     "outra prancha", "falha-arquivo.png", "revisar o arquivo"):
        assert proibido not in baixo, (proibido, html[:900])
    assert "outro arquivo" not in subject.lower() and "reenvie" not in subject.lower(), subject
    assert "estrutura" in subject.lower(), subject


def test_email_de_pdf_vetorial_nao_fala_em_escaneado():
    subject, html = _falha(main._mensagem_sem_itens(False, 2))
    assert "escaneada" not in html.lower(), html[:600]
    assert "DXF" in html, html[:600]


def test_CONTROLE_email_generico_segue_igual():
    subject, html = _falha(main._mensagem_sem_itens(False, 0))
    assert "escaneada" in html.lower()
    assert "outro arquivo" in subject, subject


# ── o process_job ─────────────────────────────────────────────────────────────
def _process_job():
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    arvore = ast.parse(src)
    return next(n for n in ast.walk(arvore)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "process_job")


def test_o_process_job_monta_o_erro_de_zero_item_com_o_TIPO_e_as_PRANCHAS_lidas():
    fn = _process_job()
    usos = [n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_mensagem_sem_itens"]
    assert usos, "o process_job não chama _mensagem_sem_itens"

    def _arg(chamada, pos, nome):
        if len(chamada.args) > pos:
            return chamada.args[pos]
        return next((k.value for k in chamada.keywords if k.arg == nome), None)

    for u in usos:
        tipo, pranchas = _arg(u, 0, "is_structural"), _arg(u, 1, "paginas_vetoriais")
        assert isinstance(tipo, ast.Name) and tipo.id == "is_structural", \
            "o 1º argumento tem que ser o tipo do projeto (is_structural)"
        assert pranchas is not None and any(
            isinstance(x, ast.Name) and x.id == "_pdfvec_por_prancha" for x in ast.walk(pranchas)), \
            "as pranchas vetoriais lidas não chegam na mensagem — o PDF vetorial volta a ser 'escaneado'"
    literais = [n.value for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert not any("Nenhum item quantificável foi identificado neste" in t for t in literais), \
        "o texto antigo voltou solto dentro do process_job"


# ── a tela de acompanhamento não cai (o 500 que a revisão pegou) ─────────────
@pytest.fixture
def cliente_status(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(main, "JOBS_FILE", str(tmp_path / "_jobs.json"))
    monkeypatch.setattr(main, "_require_project_owner", lambda request, job_id: None)
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.mark.parametrize("gravado", [
    {"status": "done", "error_message": None},
    # a forma exata das duas conclusões de complemento
    {"status": "done", "progress": 100, "error_message": None,
     "current_step": "Complemento sem itens — planilha anterior mantida"},
])
def test_status_de_projeto_concluido_nao_cai_com_erro_None_no_store(cliente_status, gravado):
    jid = "guarda-status-none"
    main.jobs[jid] = main.ProcessingStatus(job_id=jid, status="processing", progress=90)
    main.jobs.update_field(jid, **gravado)
    r = cliente_status.get("/api/status/%s" % jid)
    assert r.status_code == 200, "a tela do projeto nunca recarrega: %s" % r.text[:200]
    assert r.json()["status"] == "done" and r.json()["error_message"] == "", r.json()


def test_CONTROLE_status_com_erro_de_verdade_continua_mostrando_o_erro(cliente_status):
    jid = "guarda-status-erro"
    main.jobs[jid] = main.ProcessingStatus(job_id=jid, status="processing", progress=40)
    main.jobs.update_field(jid, status="error", error_message="falhou de verdade")
    r = cliente_status.get("/api/status/%s" % jid)
    assert r.status_code == 200 and r.json()["error_message"] == "falhou de verdade", r.text[:200]


# ── limpar o erro no banco funciona de verdade ───────────────────────────────
def _espiona_banco(monkeypatch, rpc_ok=True):
    ch = {"rpc": [], "patch": []}
    monkeypatch.setattr(main, "_rpc_update_project_status",
                        lambda j, d: ch["rpc"].append((j, dict(d))) or rpc_ok)
    monkeypatch.setattr(main, "_projeto_patch",
                        lambda j, c: ch["patch"].append((j, dict(c))) or True)
    return ch


def test_None_explicito_de_error_message_LIMPA_no_banco_por_patch(monkeypatch):
    ch = _espiona_banco(monkeypatch)
    main._supabase_update("projects", "job_id", "j1", {"status": "done", "error_message": None})
    assert ch["rpc"], "o status tem que continuar indo pela RPC"
    assert ch["patch"] == [("j1", {"error_message": None})], (
        "a RPC faz COALESCE e ignora None — sem o PATCH o erro antigo fica gravado: %r" % ch)


@pytest.mark.parametrize("dados,rpc_ok", [
    ({"status": "done"}, True),                                # ninguém pediu pra limpar
    ({"status": "error", "error_message": "falhou"}, True),    # erro novo vai pela RPC
    ({"status": "done", "error_message": None}, False),        # status não gravou
])
def test_CONTROLE_sem_pedido_de_limpar_ou_status_que_nao_gravou_nao_mexe_no_erro(monkeypatch, dados, rpc_ok):
    ch = _espiona_banco(monkeypatch, rpc_ok)
    main._supabase_update("projects", "job_id", "j1", dados)
    assert ch["rpc"] and not ch["patch"], ch


def test_a_conclusao_REAL_do_process_job_pede_pra_limpar_o_erro_antigo():
    from _fim_do_job import roda_ate_o_email
    from models import BudgetItem, Confidence
    itens = [BudgetItem(item_num="1.%d" % k, description="Serviço %d" % k, unit="m²",
                        quantity=10.0 + k,
                        confidence=(Confidence.CONFIRMADO if k == 0 else Confidence.ESTIMADO),
                        origem="dxf_geom")
             for k in range(2)]
    gravado = []
    roda_ate_o_email(itens, antes_do_email={
        "_supabase_update": lambda *a, **k: gravado.append(a) or True})
    concl = [a[3] for a in gravado
             if len(a) >= 4 and isinstance(a[3], dict)
             and a[3].get("status") == "done" and "items_count" in a[3]]
    assert concl, "não achei a gravação de conclusão: %r" % (gravado,)
    for d in concl:
        assert "error_message" in d and d["error_message"] is None, (
            "a conclusão não pede pra limpar o erro antigo: %r" % d)


# ── a tela do projeto e o painel (o JS de verdade, no duktape) ───────────────
@pytest.fixture(scope="module")
def tela():
    from _bancada_js import Pagina
    from _jsbancada import funcao_js
    p = Pagina(("aiarq-utils.js",))
    p.eval("var _RECEITAS_ERRO = window.AIARQ_RECEITAS_ERRO; 1;")
    p.eval(funcao_js("_receitaPara", "projeto.html") + "\n1;")
    p.eval(funcao_js("_erroEmTopicos", "projeto.html") + "\n1;")
    p.eval(funcao_js("_rotularTipoDoReprocesso", "projeto.html") + "\n1;")
    return p


def _receita(tela, msg):
    return json.loads(tela.eval("JSON.stringify(window.aiArqReceitaPara(%s) || null)" % json.dumps(msg)))


def _cartao(tela, msg):
    return tela.eval("_erroEmTopicos(%s)" % json.dumps(msg))


def _painel(tela, msg):
    return tela.eval("window.aiArqErroComReceita(%s)" % json.dumps(msg))


def test_TELA_pdf_vetorial_nao_vira_pdf_escaneado(tela):
    msg = main._mensagem_sem_itens(False, 3)
    cartao, painel = _cartao(tela, msg), _painel(tela, msg)
    assert "escanead" not in cartao.lower(), cartao
    assert "escanead" not in painel.lower(), painel
    assert "DXF" in cartao, cartao


def test_TELA_tipo_estrutura_aponta_ler_como_arquitetura_e_esconde_o_envio_de_arquivo(tela):
    msg = main._mensagem_sem_itens(True, 3)
    rec = _receita(tela, msg)
    assert rec and rec.get("semUpload") is True, (
        "o botão 'Enviar outro arquivo' anexa ao MESMO projeto Estrutura — repete o ciclo: %r" % rec)
    cartao, painel = _cartao(tela, msg), _painel(tela, msg)
    for texto in (cartao, painel):
        assert "Ler como Arquitetura" in texto, texto
        assert "Salve o arquivo em DXF" not in texto and "escanead" not in texto.lower(), texto


def test_CONTROLE_TELA_mensagem_generica_e_a_historica_seguem_no_escaneado(tela):
    for msg in (main._mensagem_sem_itens(False, 0), main._MSG_SEM_ITENS_GENERICA):
        assert "PDF escaneado" in _cartao(tela, msg), msg


# ── o alerta interno ──────────────────────────────────────────────────────────
class _Resp:
    def __init__(self, dados):
        self._b = json.dumps(dados).encode("utf-8")

    def read(self):
        return self._b


_CRIADO = "2026-09-11T12:36:10+00:00"


def _linha(monkeypatch, dados=None, erro=None, email="cliente@exemplo.com", criado=_CRIADO):
    pedidos = []

    def falso(req, timeout=None):
        pedidos.append(getattr(req, "full_url", str(req)))
        if erro is not None:
            raise erro
        return _Resp(dados)
    monkeypatch.setattr(main, "SUPABASE_URL", "https://exemplo.supabase.co")
    monkeypatch.setattr("urllib.request.urlopen", falso)
    return main._linha_do_email_ao_cliente(email, criado), pedidos


def _parametro(url, nome):
    for par in url.split("?", 1)[1].split("&"):
        if par.startswith(nome + "="):
            return par[len(nome) + 1:]
    return None


def test_alerta_sem_registro_diz_ATE_AGORA_e_olha_desde_15_min_ANTES_de_criado(monkeypatch):
    linha, pedidos = _linha(monkeypatch, dados=[])
    assert "não há e-mail de falha registrado" in linha, linha
    assert pedidos and "erro_trocar" in pedidos[0], pedidos
    desde = unquote(_parametro(pedidos[0], "sent_at")[len("gte."):])
    assert datetime.fromisoformat(desde) == datetime.fromisoformat(_CRIADO) - timedelta(minutes=15), (
        "o freio de 15 min avisa pelo projeto irmão, ANTES deste ser criado: %s" % pedidos[0])


def test_alerta_de_quem_foi_avisado_pelo_projeto_IRMAO_nao_diz_que_falta_aviso(monkeypatch):
    linha, _ = _linha(monkeypatch, dados=[{"kind": "erro_trocar", "sent_at": "2026-09-11T12:31:10+00:00"}])
    assert linha.startswith("O cliente recebeu e-mail de falha") and "ANTERIOR" in linha, linha


def test_alerta_diz_que_recebeu_quando_o_envio_e_depois_do_projeto(monkeypatch):
    linha, _ = _linha(monkeypatch, dados=[{"kind": "erro_trocar", "sent_at": "2026-09-11T12:38:40+00:00"}])
    assert linha.startswith("O cliente recebeu e-mail de falha"), linha
    assert "ANTERIOR" not in linha and "12:38" in linha, linha


def test_alerta_sem_data_de_criacao_nao_consulta_nem_afirma(monkeypatch):
    linha, pedidos = _linha(monkeypatch, dados=[{"kind": "erro_trocar", "sent_at": "2020-01-01T00:00:00+00:00"}],
                            criado="")
    assert "Não deu pra confirmar" in linha and not pedidos, (linha, pedidos)


def test_alerta_de_conta_interna_nao_diz_que_falta_aviso(monkeypatch):
    linha, pedidos = _linha(monkeypatch, dados=[], email=main.ADMIN_EMAIL)
    assert "Conta interna" in linha and not pedidos, (linha, pedidos)


def test_alerta_codifica_o_mais_do_email(monkeypatch):
    _, pedidos = _linha(monkeypatch, dados=[], email="cliente+obra@exemplo.com")
    assert _parametro(pedidos[0], "email") == "ilike.cliente%2Bobra%40exemplo.com", pedidos[0]


def test_alerta_diz_que_nao_deu_pra_confirmar_quando_a_consulta_falha(monkeypatch):
    linha, _ = _linha(monkeypatch, erro=OSError("rede fora"))
    assert "Não deu pra confirmar" in linha, linha


def test_o_alerta_terminal_pede_created_at_e_entrega_pra_linha_do_email(monkeypatch):
    linha_args, urls, avisos = [], [], []
    row = {"job_id": "job-guarda", "user_email": "cliente@exemplo.com",
           "project_name": "Projeto teste", "error_message": main._mensagem_sem_itens(True, 3),
           "typology": "office", "project_type": "estrutura", "auto_resume_count": 0,
           "created_at": _CRIADO}

    def falso(req, timeout=None):
        urls.append(getattr(req, "full_url", str(req)))
        return _Resp([row])
    monkeypatch.setattr(main, "SUPABASE_URL", "https://exemplo.supabase.co")
    monkeypatch.setattr("urllib.request.urlopen", falso)
    monkeypatch.setattr(main, "_email_auto_ja_enviado", lambda *a, **k: False)
    monkeypatch.setattr(main, "_email_auto_registrar", lambda *a, **k: None)
    monkeypatch.setattr(main, "_error_log_causa_real", lambda j: "")
    monkeypatch.setattr(main, "_notify_admin", lambda assunto, corpo: avisos.append(corpo) or True)
    monkeypatch.setattr(main, "_retomar_job_do_storage",
                        lambda *a, **k: pytest.fail("erro de tipo não é passageiro"))
    monkeypatch.setattr(main, "_linha_do_email_ao_cliente",
                        lambda e, c: linha_args.append((e, c)) or "LINHA-DO-EMAIL")
    main._auto_retry_erros_transitorios()
    assert "created_at" in _parametro(urls[0], "select").split(","), urls[0]
    assert linha_args == [("cliente@exemplo.com", _CRIADO)], linha_args
    assert avisos and "LINHA-DO-EMAIL" in avisos[0], avisos


def test_o_alerta_nao_tem_mais_a_frase_FIXA():
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    literais = [n.value for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert not any("O cliente já recebeu o email de falha" in t for t in literais)


# ── o Reprocessar da página e o botão do painel (a 2ª revisão) ───────────────
# 🩸 A mensagem de zero item passou a mandar o cliente pro Reprocessar › "Ler como
# Arquitetura" — e a página, sem o tipo do projeto, escondia essa opção num projeto
# Estrutura; no painel, o único botão reenviava como Estrutura.
def test_o_meta_do_api_items_traz_o_TIPO_do_projeto(monkeypatch):
    from fastapi.testclient import TestClient
    urls = []

    def falso(req, timeout=None):
        urls.append(getattr(req, "full_url", str(req)))
        return _Resp([{"project_name": "Projeto teste", "status": "error",
                       "project_type": "estrutura"}])
    monkeypatch.setattr(main, "_require_project_owner", lambda request, job_id: None)
    monkeypatch.setattr(main, "_itens_do_projeto_completos", lambda job_id, timeout=15: ([], True))
    monkeypatch.setattr(main, "SUPABASE_URL", "https://exemplo.supabase.co")
    monkeypatch.setattr("urllib.request.urlopen", falso)
    r = TestClient(main.app, raise_server_exceptions=False).get("/api/items/job-guarda")
    assert r.status_code == 200, r.text[:200]
    assert urls and "project_type" in _parametro(urls[0], "select").split(","), urls
    assert r.json()["project"].get("project_type") == "estrutura", r.json()


_SELETOR = r"""(function(){
  var ops = [{value:'', textContent:'Mesmo tipo de antes'},
             {value:'arquitetura', textContent:'Ler como Arquitetura'},
             {value:'estrutura', textContent:'Ler como Estrutura'}];
  ops.forEach(function(o){ o.remove = function(){ ops.splice(ops.indexOf(o), 1); }; });
  _rotularTipoDoReprocesso({ options: ops }, %s);
  return JSON.stringify(ops.map(function(o){ return [o.value, o.textContent]; }));
})()"""


@pytest.mark.parametrize("tipo_js,tem_arq,tem_est,rotulo", [
    ("undefined", True, True, "Mesmo tipo de antes"),        # a forma da lista by-user
    ("'estrutura'", True, False, "Mesmo tipo (Estrutura)"),
    ("'arquitetura'", False, True, "Mesmo tipo (Arquitetura)"),
])
def test_TELA_reprocessar_de_projeto_estrutura_oferece_ler_como_arquitetura(tela, tipo_js, tem_arq, tem_est, rotulo):
    ops = json.loads(tela.eval(_SELETOR % tipo_js))
    valores = [v for v, _ in ops]
    assert ("arquitetura" in valores) == tem_arq, ops
    assert ("estrutura" in valores) == tem_est, ops
    assert ops[0] == ["", rotulo], ops


def test_a_pagina_do_projeto_entrega_o_tipo_do_meta_ao_reprocessar():
    src = io.open(os.path.join(_RAIZ, "projeto.html"), encoding="utf-8").read()
    liga = "if (proj && !proj.project_type && pmeta.project_type) proj.project_type = pmeta.project_type;"
    assert liga in src, "o tipo do meta não entra no proj"
    assert src.index(liga) < src.index("renderHeader(proj)"), "o tipo entra DEPOIS de desenhar o cabeçalho"
    assert "_rotularTipoDoReprocesso(_selTipo, p.project_type)" in src
    assert "(p.project_type || 'arquitetura')" not in src, "a suposição de 'arquitetura' voltou"


def _botao(tela, msg, job):
    return json.loads(tela.eval("JSON.stringify(window.aiArqBotaoDoErro(%s, %s))"
                                % (json.dumps(msg), json.dumps(job))))


def test_PAINEL_erro_de_estrutura_troca_o_botao_por_abrir_o_projeto(tela):
    b = _botao(tela, main._mensagem_sem_itens(True, 3), "job 1")
    assert b == {"rotulo": "Abrir o projeto", "href": "projeto.html?job_id=job%201#processamento"}, b


def test_PAINEL_o_botao_do_erro_de_verdade_troca_e_DESFAZ_rotulo_e_destino(tela):
    """O `_botaoDoErro` do dashboard.html rodando: troca pro erro de Estrutura e
    desfaz no erro seguinte (senão o "Abrir o projeto" fica grudado)."""
    from _jsbancada import funcao_js
    tela.eval("var btnRetry = {textContent: 'Enviar outro arquivo', dataset: {}}; 1;")
    tela.eval(funcao_js("_botaoDoErro", "dashboard.html") + "\n1;")
    estado = "JSON.stringify([btnRetry.textContent, btnRetry.dataset.abrir])"
    tela.eval("_botaoDoErro(%s, 'job-1'); 1;" % json.dumps(main._mensagem_sem_itens(True, 3)))
    assert json.loads(tela.eval(estado)) == ["Abrir o projeto", "projeto.html?job_id=job-1#processamento"]
    tela.eval("_botaoDoErro('', null); 1;")
    assert json.loads(tela.eval(estado)) == ["Enviar outro arquivo", ""]


@pytest.mark.parametrize("msg,job", [
    (main._mensagem_sem_itens(True, 3), None),                                   # sem job, sem link
    ("Não conseguimos abrir automaticamente o seu DWG (versão muito recente).", "job-1"),
    ("Reenvio duplicado: a versão boa é a mais recente.", "job-1"),              # semUpload sem vista
    (main._mensagem_sem_itens(False, 0), "job-1"),
])
def test_CONTROLE_PAINEL_outros_erros_mantem_enviar_outro_arquivo(tela, msg, job):
    assert _botao(tela, msg, job) == {"rotulo": "Enviar outro arquivo", "href": ""}, msg


def test_PAINEL_toda_tela_de_erro_passa_pelo_botao_do_erro():
    src = io.open(os.path.join(_RAIZ, "dashboard.html"), encoding="utf-8").read()
    linhas = src.splitlines()
    sitios = [i for i, l in enumerate(linhas) if "showState(stateError)" in l]
    assert sitios, "não achei tela de erro no painel"
    for i in sitios:
        assert any("_botaoDoErro(" in l for l in linhas[max(0, i - 3):i]), (
            "tela de erro sem _botaoDoErro na linha %d — o rótulo do erro anterior fica" % (i + 1))
    assert "_botaoDoErro(_txtErro, currentJobId)" in src
    assert "if (btnRetry.dataset.abrir) { window.location.href = btnRetry.dataset.abrir; return; }" in src
