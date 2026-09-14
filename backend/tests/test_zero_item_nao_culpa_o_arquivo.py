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
import re
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


def _completa(tela, proj_js, meta_js):
    return json.loads(tela.eval("JSON.stringify(_completarTipo(%s, %s) || null)"
                                % (proj_js, meta_js)))


def test_a_pagina_do_projeto_COPIA_o_tipo_do_meta_e_NUNCA_supoe(tela):
    """🩸 14/09 — o guarda daqui só procurava o TEXTO da linha, e a revisão
    adversarial provou 3 jeitos de trazer a armadilha de volta com ele verde
    (supor 'arquitetura' depois da cópia, no renderHeader, ou no proj
    sintetizado). Agora a decisão é uma função PURA e o teste CHAMA ela."""
    from _jsbancada import funcao_js
    tela.eval(funcao_js("_completarTipo", "projeto.html") + "\n1;")

    # a forma real da lista by-user: sem project_type; o meta tem
    assert _completa(tela, "{job_id:'j'}", "{project_type:'estrutura'}")["project_type"] == "estrutura"
    # 🚨 sem meta, o tipo fica AUSENTE — supor 'arquitetura' esconde o
    # "Ler como Arquitetura" justamente no projeto de Estrutura
    assert not (_completa(tela, "{job_id:'j'}", "{}") or {}).get("project_type")
    assert not (_completa(tela, "{job_id:'j'}", "null") or {}).get("project_type")
    # o que já veio não é sobrescrito
    assert _completa(tela, "{job_id:'j',project_type:'estrutura'}",
                     "{project_type:'arquitetura'}")["project_type"] == "estrutura"
    # projeto ausente não vira objeto do nada
    assert _completa(tela, "null", "{project_type:'estrutura'}") is None


def test_a_tela_do_projeto_nao_SUPOE_arquitetura_em_lugar_nenhum():
    """🪤 Complemento do teste acima: dois dos três mutantes escrevem a suposição
    FORA da função pura (renderHeader, proj sintetizado). Aqui a proibição é do
    LITERAL, em qualquer forma."""
    src = io.open(os.path.join(_RAIZ, "projeto.html"), encoding="utf-8").read()
    achados = [a for a in re.findall(r"project_type[^\n]{0,40}?'arquitetura'", src)
               if "===" not in a and "==" not in a]
    assert not achados, "suposição de 'arquitetura' voltou: %r" % achados
    assert "_rotularTipoDoReprocesso(_selTipo, p.project_type)" in src


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


def _sem_comentarios(arquivo):
    src = io.open(os.path.join(_RAIZ, arquivo), encoding="utf-8").read()
    sem = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", l) for l in sem.splitlines())


def test_PAINEL_toda_tela_de_erro_passa_pelo_botao_do_erro():
    """Regra de ORDEM, não janela de linhas.

    🪤 14/09 — a janela de 3 linhas errava nos DOIS sentidos: aceitava a
    navegação COMENTADA (a substring continua no comentário) e reprovava código
    certo (telemetria ou comentário entre a chamada e o `showState`). O que
    importa é: nenhuma tela de erro aparece sem passar pelo botão antes.
    """
    sem = _sem_comentarios("dashboard.html")
    telas = [m.start() for m in re.finditer(r"showState\(stateError\)", sem)]
    botoes = [m.start() for m in re.finditer(r"_botaoDoErro\(", sem)]
    assert telas and botoes, "não achei tela de erro no painel"
    anterior = 0
    for t in telas:
        assert any(anterior <= b < t for b in botoes), (
            "tela de erro sem _botaoDoErro antes (posição %d) — o rótulo do erro "
            "anterior fica grudado" % t)
        anterior = t
    assert "_botaoDoErro(_txtErro, currentJobId)" in sem


def test_CONTROLE_a_regra_de_ordem_sabe_REPROVAR():
    """🧪 Sem isto, o teste acima passaria com a chamada COMENTADA."""
    sem = "\n".join(re.sub(r"//.*$", "", l) for l in
                    ["// _botaoDoErro(txt, job);", "showState(stateError);"])
    assert re.search(r"showState\(stateError\)", sem)
    assert not re.search(r"_botaoDoErro\(", sem), (
        "a limpeza de comentário não remove nada — a regra de ordem seria cega")


def test_PAINEL_o_clique_do_botao_do_erro_NAVEGA_e_NAO_limpa(tela):
    """O handler REAL do btn-retry rodando: com destino, navega e preserva; sem
    destino, limpa a seleção e volta pra tela de envio (o caso do cliente-61,
    que reenviou o mesmo DWG quebrado 2×)."""
    from _jsbancada import handler_js
    tela.eval("""
      var navegou = null, telaFinal = null;
      var selectedFiles = ['planta.dwg'], currentJobId = 'job-1';
      var stateUpload = {id: 'upload'};
      var btnRetry = {dataset: {}};
      function renderFiles() {}
      function showState(s) { telaFinal = s && s.id; }
      window.location = {};
      Object.defineProperty(window.location, 'href', {
        set: function (v) { navegou = v; }, get: function () { return navegou; }});
      1;
    """)
    tela.eval(handler_js("_cliqueRetry", "btnRetry.addEventListener('click', ",
                         "dashboard.html") + "\n1;")

    tela.eval("btnRetry.dataset.abrir = 'projeto.html?job_id=job-1#processamento';"
              "_cliqueRetry(); 1;")
    com_destino = json.loads(tela.eval(
        "JSON.stringify([navegou, selectedFiles.length, currentJobId, telaFinal])"))
    assert com_destino == ["projeto.html?job_id=job-1#processamento", 1, "job-1", None], com_destino

    tela.eval("btnRetry.dataset.abrir = ''; _cliqueRetry(); 1;")
    sem_destino = json.loads(tela.eval(
        "JSON.stringify([selectedFiles.length, currentJobId, telaFinal])"))
    assert sem_destino == [0, None, "upload"], sem_destino


def test_os_NOMES_que_a_mensagem_cita_existem_na_tela():
    """🪤 A mensagem manda abrir 'Processamento' e escolher 'Ler como
    Arquitetura'. Renomear a vista ou a opção deixaria a instrução apontando pra
    nada — e vista inexistente cai calada na Visão geral (já aconteceu quando
    'dados' virou 'processamento')."""
    proj = io.open(os.path.join(_RAIZ, "projeto.html"), encoding="utf-8").read()
    menu = io.open(os.path.join(_RAIZ, "menu-lateral.js"), encoding="utf-8").read()
    utils = io.open(os.path.join(_RAIZ, "aiarq-utils.js"), encoding="utf-8").read()
    msg = main._mensagem_sem_itens(True, 3)

    opcao = re.search(r'<option value="arquitetura"[^>]*>([^<]+)</option>', proj)
    assert opcao, "sumiu a opção 'arquitetura' do seletor de reprocessamento"
    # 🪤 entre ASPAS, como a mensagem cita: exigir só o pedaço deixa passar o
    # rótulo encurtado ('Arquitetura'), que manda procurar opção inexistente.
    assert ("'%s'" % opcao.group(1).strip()) in msg, (
        "a mensagem cita um rótulo que não é o da opção: %r" % opcao.group(1))

    vista = re.search(r"abrirVista:\s*'([a-z]+)'", utils)
    assert vista, "a receita de Estrutura não manda abrir vista nenhuma"
    assert ('data-vista="%s"' % vista.group(1)) in proj, (
        "a vista %r não existe em projeto.html" % vista.group(1))

    item = re.search(r"#%s'[^}]*rotulo:\s*'([^']+)'" % vista.group(1), menu)
    assert item, "nenhum item de menu aponta pra #%s" % vista.group(1)
    assert ("'%s'" % item.group(1)) in msg, (
        "a mensagem manda abrir %r, mas o menu chama de %r"
        % (vista.group(1), item.group(1)))

# ── o e-mail e o card levam direto ao Reprocessar (14/09) ────────────────────
def _vista_da_receita():
    utils = io.open(os.path.join(_RAIZ, "aiarq-utils.js"), encoding="utf-8").read()
    return re.search(r"abrirVista:\s*'([a-z]+)'", utils).group(1)


def test_email_de_estrutura_abre_o_PROJETO_quando_tem_o_codigo():
    """🩸 14/09: o botão ia pro painel, e o caminho que a mensagem ensina mora
    DENTRO do projeto. O cliente do caso chegou por e-mail."""
    _, html = main._build_falha_email("Fulano", "Projeto Teste", False,
                                      error_hint=main._mensagem_sem_itens(True, 3),
                                      job_id="job 1")
    destino = re.search(r'href="(https://ai\.arq\.br/[^"]+)"', html).group(1)
    assert destino == "https://ai.arq.br/projeto.html?job_id=job%201#processamento", destino
    assert destino.endswith("#" + _vista_da_receita()), (
        "o e-mail manda abrir uma vista diferente da que a receita da tela abre")
    assert "Abrir o projeto" in html and "Abrir meu painel" not in html


def test_CONTROLE_email_sem_o_codigo_do_projeto_cai_no_painel():
    _, html = main._build_falha_email("Fulano", "Projeto Teste", False,
                                      error_hint=main._mensagem_sem_itens(True, 3))
    destino = re.search(r'href="(https://ai\.arq\.br/[^"]+)"', html).group(1)
    assert destino == "https://ai.arq.br/dashboard.html", destino
    assert "Abrir meu painel" in html


def test_o_email_de_falha_LEVA_o_codigo_do_projeto():
    """🪤 Guarda de ponto de chamada: a função pode aceitar o job_id e ninguém
    passar — foi assim que o `files_count` do /add-file nasceu morto."""
    from _corpo import corpo_de
    corpo = corpo_de("_email_falha_cliente")
    assert "job_id=job_id" in corpo, (
        "o e-mail de falha não passa o código do projeto — o botão volta pro painel")


def test_o_card_de_erro_LIGA_o_botao_da_vista(tela):
    """O card da Visão geral: com `semUpload` o botão de enviar some, e sem este
    botão sobra só "Reportar problema". Roda a função de verdade."""
    from _jsbancada import funcao_js
    tela.eval(funcao_js("_ligaBotaoDaVista", "projeto.html") + "\n1;")
    tela.eval("""
      var escondido = null, foiPra = null, clique = null;
      var el = { onclick: null,
                 classList: { toggle: function (c, v) { escondido = !!v; } } };
      function _ir(v) { foiPra = v; }
      1;
    """)
    v = _vista_da_receita()
    assert tela.eval("_ligaBotaoDaVista(el, {abrirVista: '%s'}, _ir)" % v) == v
    assert json.loads(tela.eval("JSON.stringify(escondido)")) is False
    tela.eval("el.onclick({preventDefault: function () { clique = 'barrado'; }}); 1;")
    assert json.loads(tela.eval("JSON.stringify([foiPra, clique])")) == [v, "barrado"], (
        "o clique não levou pra vista (ou não barrou o pulo do link)")

    tela.eval("el.onclick = null; 1;")
    assert tela.eval("_ligaBotaoDaVista(el, {}, _ir)") is None
    assert json.loads(tela.eval("JSON.stringify([escondido, el.onclick])")) == [True, None], (
        "receita sem vista deixou o botão visível")


def test_o_rotulo_do_botao_do_card_e_o_NOME_da_vista_no_menu():
    """🪤 Se o menu renomear a vista, o botão do card passa a prometer um nome
    que não existe na tela."""
    proj = io.open(os.path.join(_RAIZ, "projeto.html"), encoding="utf-8").read()
    menu = io.open(os.path.join(_RAIZ, "menu-lateral.js"), encoding="utf-8").read()
    v = _vista_da_receita()
    rotulo_menu = re.search(r"#%s'[^}]*rotulo:\s*'([^']+)'" % v, menu).group(1)
    botao = re.search(r'id="erro-btn-vista".*?>\s*([^<]+?)\s*</a>', proj, re.S)
    assert botao, "o card de erro não tem o botão da vista"
    assert rotulo_menu in botao.group(1), (
        "o botão do card diz %r e o menu chama de %r" % (botao.group(1), rotulo_menu))

def test_o_botao_da_vista_chama_uma_funcao_que_EXISTE_na_tela():
    """🪤 REVISÃO DO PRÓPRIO CONSERTO (14/09): o guarda de cima roda
    `_ligaBotaoDaVista` com um `irPraVista` DE MENTIRA — ele prova a ligação,
    não o destino. Renomear a função de navegação deixaria o botão mudo com a
    bancada verde, que é a família dos 459 guardas cegos de 06/09.
    Aqui o nome sai do que `mostrarErro` REALMENTE passa, e o extrator da casa
    reprova se essa função não existir no arquivo."""
    from _corpo import corpo_js
    from _jsbancada import funcao_js
    corpo = corpo_js("mostrarErro", "projeto.html")
    m = re.search(r"_ligaBotaoDaVista\(.*?function\s*\([^)]*\)\s*\{\s*"
                  r"([A-Za-z_$][\w$]*)\s*\(", corpo, re.S)
    assert m, "`mostrarErro` não liga mais o botão da vista a função nenhuma"
    nome = m.group(1)
    corpo_do_destino = funcao_js(nome, "projeto.html")   # levanta se não existir
    assert corpo_do_destino.strip(), nome


def test_o_href_do_botao_aponta_pra_MESMA_vista_que_o_clique_abre():
    """O clique dá `preventDefault` e usa a vista da receita — mas o `href` é o
    que vale em "abrir em nova aba", e é o que sobra se o JS não carregar."""
    proj = io.open(os.path.join(_RAIZ, "projeto.html"), encoding="utf-8").read()
    m = re.search(r'id="erro-btn-vista"[^>]*href="([^"]+)"', proj)
    assert m, "o botão da vista perdeu o href"
    assert m.group(1) == "#" + _vista_da_receita(), (
        "o href diz %r e a receita manda abrir %r" % (m.group(1), _vista_da_receita()))

def test_mostrarErro_LIGA_o_botao_da_vista_DE_VERDADE(tela):
    """🩸 14/09, mutante sobrevivente: `if (false) _ligaBotaoDaVista(...)`.

    O guarda de cima chama `_ligaBotaoDaVista` na mão e o outro lê o texto da
    chamada — os dois passam com a ligação DESLIGADA. Aqui o card de erro é
    montado pelo `mostrarErro` de verdade, e quem responde é o botão."""
    from _jsbancada import funcao_js
    tela.eval(funcao_js("_ligaBotaoDaVista", "projeto.html") + "\n1;")
    tela.eval(funcao_js("mostrarErro", "projeto.html") + "\n1;")
    tela.eval("""
      var foiPra = null, escondido = null;
      function mostrarVista(v) { foiPra = v; }
      function aplicarEstadoNasVistas() {}
      var _btnV = document.getElementById('erro-btn-vista');
      _btnV.classList.toggle = function (c, v) { if (c === 'hidden') escondido = !!v; };
      1;
    """)
    tela.eval("mostrarErro(%s, null); 1;" % json.dumps(main._mensagem_sem_itens(True, 3)))
    assert json.loads(tela.eval("JSON.stringify(escondido)")) is False, (
        "o card de erro de ESTRUTURA não mostrou o botão da vista")
    assert tela.eval("typeof _btnV.onclick") == "function", (
        "o botão apareceu mas ninguém ligou o clique nele")
    tela.eval("_btnV.onclick({preventDefault: function () {}}); 1;")
    assert tela.eval("foiPra") == _vista_da_receita()


def test_CONTROLE_erro_sem_receita_nao_mostra_o_botao_da_vista(tela):
    """Prova que o de cima sabe reprovar: erro comum não ganha o botão."""
    from _jsbancada import funcao_js
    tela.eval(funcao_js("_ligaBotaoDaVista", "projeto.html") + "\n1;")
    tela.eval(funcao_js("mostrarErro", "projeto.html") + "\n1;")
    tela.eval("""
      var foiPra = null, escondido = null;
      function mostrarVista(v) { foiPra = v; }
      function aplicarEstadoNasVistas() {}
      var _btnV = document.getElementById('erro-btn-vista');
      _btnV.onclick = null;
      _btnV.classList.toggle = function (c, v) { if (c === 'hidden') escondido = !!v; };
      1;
    """)
    tela.eval("mostrarErro('Erro de rede ao falar com o servidor.', null); 1;")
    assert json.loads(tela.eval("JSON.stringify(escondido)")) is True
    assert json.loads(tela.eval("JSON.stringify([foiPra, _btnV.onclick])")) == [None, None]
