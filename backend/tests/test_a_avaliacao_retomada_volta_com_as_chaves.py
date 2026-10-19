# -*- coding: utf-8 -*-
"""A avaliação que atravessa um reinício volta com as chaves que pediu — ou para.

🩸 18/10/2026, avaliação do grupo B: um deploy saiu 6 s depois de ela começar.
A 1ª leitura (com as chaves) morreu antes da IA; a retomada relançou o job com
o dicionário das chaves vazio — ele mora na memória — e a avaliação rodou
INTEIRA com as chaves do servidor (em 0), calada. O log e o nome do projeto
diziam "com chaves próprias"; a planilha era o motor sem elas, e o resultado
foi lido como "a régua não pega esse nome".

🔑 O pedido já fica escrito no fim do nome do projeto, na mesma linha que a
retomada lê antes de relançar. Estes testes:
  * rodam a ROTA de verdade e releem o nome que ela gravou (a forma que o
    leitor espera é a que a rota escreve, não uma cópia dela aqui);
  * rodam a RETOMADA de verdade (`_retomar_job_do_storage`, com o banco de
    mentira que avalia os filtros, de `test_a_retomada_nao_apaga_o_anexo`) e
    olham o que o motor recebe NO MOMENTO do disparo;
  * e provam o lado que não pode mudar: job de cliente nunca ganha chave, e
    avaliação sem pedido retoma como antes.
"""
import os
import sys
import urllib.parse
import urllib.request

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main  # noqa: E402
from test_a_retomada_nao_apaga_o_anexo import (  # noqa: E402
    JOB, _Banco, _armar, _itens, _json, _projeto)

#: ids e nomes fictícios — o repositório é público.
EV = "ev0a1b2c"
NOME = "[TESTE] Obra nn"
CHAVES = {"FAMILIA_DE_ANOTACAO_DO_REVIT": "1", "SIMBOLO_DE_NIVEL_E_ANOTACAO": "1"}
FIM_COM_CHAVES = " — avaliação [FAMILIA_DE_ANOTACAO_DO_REVIT=1, SIMBOLO_DE_NIVEL_E_ANOTACAO=1]"


@pytest.fixture(autouse=True)
def _memoria_zerada(monkeypatch):
    """O servidor acabou de reiniciar: nada na memória."""
    monkeypatch.setattr(main, "_CHAVES_DA_AVALIACAO", {})
    monkeypatch.setattr(main, "_SEM_SINAPI_DA_AVALIACAO", set())


# ══════════════════════════════════════════════════════════════════════════
#  1. O leitor relê o que a ROTA escreve
# ══════════════════════════════════════════════════════════════════════════
def _rodar_a_rota(monkeypatch, tmp_path, chaves, sem_sinapi, nome_do_original):
    """`admin_eval_reprocess` de verdade; devolve a linha que ela inseriu."""
    original = {"job_id": "job-orig", "is_eval": False, "typology": "office",
                "project_type": "arquitetura", "status": "done",
                "user_total_area": 0, "user_pe_direito": 0,
                "user_email": "cliente-nn@example.com", "project_name": nome_do_original}

    def _urlopen(req, *a, **k):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/storage/v1/object/list/" in url:
            return _json([{"name": "planta.pdf"}])
        if "/rest/v1/projects" in url and "job-orig" in urllib.parse.unquote(url):
            return _json([original])
        raise AssertionError("pedido inesperado da rota: %s" % url)

    inseridas = []
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    # a rota monta a URL com ela: vazia no ambiente, o Request recusa antes do dublê
    monkeypatch.setattr(main, "SUPABASE_URL", "https://banco-de-mentira.example")
    monkeypatch.setattr(main, "_require_admin", lambda *a, **k: {"email": "x"})
    monkeypatch.setattr(main, "WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setattr(main, "JOBS_FILE", str(tmp_path / "_jobs.json"))
    monkeypatch.setattr(main, "_supabase_storage_download_prancha", lambda *a, **k: b"%PDF-1.4\n")
    monkeypatch.setattr(main, "_supabase_insert", lambda tabela, linha: inseridas.append(linha))
    monkeypatch.setattr(main, "_process_job_throttled", lambda *a, **k: None)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.delenv("AUTO_LIBERAR_FILHOTE", raising=False)
    resposta = main.admin_eval_reprocess("job-orig", request=None, chaves=chaves,
                                         sem_sinapi=sem_sinapi)
    (linha,) = inseridas
    assert linha["job_id"] == resposta["eval_job_id"]
    return linha


@pytest.mark.parametrize("chaves, sem_sinapi, esperado", [
    (None, None, ({}, False)),
    (None, "1", ({}, True)),
    ("SIMBOLO_DE_NIVEL_E_ANOTACAO=1,FAMILIA_DE_ANOTACAO_DO_REVIT=1", None, (CHAVES, False)),
    ("LEGENDA_PELA_FORMA=0", "1", ({"LEGENDA_PELA_FORMA": "0"}, True)),
])
@pytest.mark.parametrize("nome_do_original", [
    "Obra nn",
    # o nome do CLIENTE com a forma da rota dentro: só o fim conta
    "Obra nn — avaliação [AMBIENTE_AREA_ESCRITA=1] [sem SINAPI]",
])
def test_o_leitor_rele_o_que_a_rota_grava(monkeypatch, tmp_path, chaves, sem_sinapi, esperado,
                                          nome_do_original):
    linha = _rodar_a_rota(monkeypatch, tmp_path, chaves, sem_sinapi, nome_do_original)
    assert main._pedido_no_nome_da_avaliacao(linha["project_name"]) == esperado, linha["project_name"]


@pytest.mark.parametrize("nome, esperado", [
    (NOME + " — avaliação", ({}, False)),
    (NOME + " — avaliação [sem SINAPI]", ({}, True)),
    (NOME + FIM_COM_CHAVES, (CHAVES, False)),
    (NOME + FIM_COM_CHAVES + " [sem SINAPI]", (CHAVES, True)),
    # a `eval-combine` não aceita chaves: o nome dela não é da forma
    (NOME + " — combinado (1 PDF, 1 DXF)", ({}, False)),
    ("", ({}, False)),
    (None, ({}, False)),
])
def test_o_fim_do_nome(nome, esperado):
    assert main._pedido_no_nome_da_avaliacao(nome) == esperado


@pytest.mark.parametrize("nome", [
    NOME + " — avaliação [CHAVE_QUE_SAIU_DA_LISTA=1]",       # um deploy tirou a chave
    NOME + " — avaliação [SIMBOLO_DE_NIVEL_E_ANOTACAO=2]",
    NOME + " — avaliação []",
    NOME + FIM_COM_CHAVES + " [sem SINAPI] [sem SINAPI]",
    NOME + " [sem SINAPI]",                                  # a marca sem a forma da rota
])
def test_CONTROLE_o_fim_que_nao_se_rele_nao_vira_pedido_vazio(nome):
    """None, e não ({}, …): pedido vazio é rodar SEM as chaves, o defeito."""
    assert main._pedido_no_nome_da_avaliacao(nome) is None


# ══════════════════════════════════════════════════════════════════════════
#  2. A retomada de verdade
# ══════════════════════════════════════════════════════════════════════════
def _retomar(monkeypatch, tmp_path, job_id, nome, *, antes_do_patch=None):
    banco = _Banco(_projeto(job_id=job_id, project_name=nome, status="processing",
                            is_eval=job_id.startswith("ev"),
                            user_email="" if job_id.startswith("ev") else "cliente-nn@example.com"),
                   [dict(i, job_id=job_id) for i in _itens()])
    banco.storage = {job_id: ["planta.pdf", "forro.dxf"]}
    banco.antes_do_patch = antes_do_patch
    cena = _armar(monkeypatch, tmp_path, banco)
    monkeypatch.setattr(main, "SUPABASE_URL", "https://banco-de-mentira.example")
    cena.logs_completos = []

    def _log(etapa, msg="", jid=None, *a, **k):
        cena.logs_completos.append((etapa, msg, jid, k.get("severity")))
    monkeypatch.setattr(main, "_log_error", _log)

    def _dispara(*a, **k):
        # o que o motor vai ler, NO MOMENTO do disparo
        jid = a[0]
        cena.disparos.append({"job_id": jid,
                              "env": main._env_da_extracao(jid),
                              "chaves": dict(main._CHAVES_DA_AVALIACAO.get(jid) or {}),
                              "sem_sinapi": main._avaliacao_sem_sinapi(jid),
                              # a chave lida no PRÓPRIO process_job, não no extrator
                              "bloco_sem_linha": main._chave_do_job(jid, "BLOCO_SEM_LINHA")})
        cena.disparou.set()
    monkeypatch.setattr(main, "_process_job_throttled", _dispara)
    cena.ret = main._retomar_job_do_storage(job_id, "residential", "arquitetura")
    return cena


def _retomadas(cena):
    return [l for l in cena.logs_completos if l[0] == main._ETAPA_RETOMADA_DA_AVALIACAO]


def test_a_avaliacao_retomada_dispara_com_as_chaves_que_pediu(monkeypatch, tmp_path):
    """O caso de 18/10."""
    cena = _retomar(monkeypatch, tmp_path, EV, NOME + FIM_COM_CHAVES)
    assert cena.ret is True and cena.esperar_disparo()
    (d,) = cena.disparos
    assert d["chaves"] == CHAVES, "a avaliação retomada rodaria SEM as chaves que pediu"
    assert d["env"] is not None and all(d["env"].get(c) == v for c, v in CHAVES.items()), (
        "o filho da extração não receberia as chaves")
    assert d["sem_sinapi"] is False
    (log,) = _retomadas(cena)
    assert log[2] == EV and log[3] == "info"
    assert "FAMILIA_DE_ANOTACAO_DO_REVIT=1" in log[1] and "SIMBOLO_DE_NIVEL_E_ANOTACAO=1" in log[1], (
        "quem confere a avaliação precisa ver no log que ela voltou com as chaves")
    assert cena.banco.inesperados == []


def test_a_chave_lida_no_process_job_tambem_volta(monkeypatch, tmp_path):
    """Nem toda chave é lida no extrator: `_chave_do_job` lê no process_job,
    do mesmo dicionário. Servidor em 0, avaliação pediu 1."""
    monkeypatch.setenv("BLOCO_SEM_LINHA", "0")
    cena = _retomar(monkeypatch, tmp_path, EV, NOME + " — avaliação [BLOCO_SEM_LINHA=1]")
    assert cena.ret is True and cena.esperar_disparo()
    (d,) = cena.disparos
    assert d["bloco_sem_linha"] == "1", "o process_job leria a chave do servidor, não a pedida"


def test_a_marca_sem_sinapi_tambem_volta(monkeypatch, tmp_path):
    cena = _retomar(monkeypatch, tmp_path, EV, NOME + " — avaliação [sem SINAPI]")
    assert cena.ret is True and cena.esperar_disparo()
    (d,) = cena.disparos
    assert d["sem_sinapi"] is True and d["chaves"] == {} and d["env"] is None
    (log,) = _retomadas(cena)
    assert "[sem SINAPI]" in log[1]


def test_o_pedido_que_nao_se_rele_PARA_a_avaliacao(monkeypatch, tmp_path):
    """Chave que saiu da lista num deploy: rodar sem ela é a planilha de outro
    pedido. A avaliação para, com o motivo na tela."""
    cena = _retomar(monkeypatch, tmp_path, EV, NOME + " — avaliação [CHAVE_QUE_SAIU_DA_LISTA=1]")
    banco = cena.banco
    assert cena.ret == "ocupado", (
        "False faria o chamador marcar o erro genérico de reinício (e mandar e-mail)")
    assert cena.nao_disparou(), "o motor foi disparado sem as chaves que a avaliação pediu"
    projeto = banco.projetos[0]
    assert projeto["status"] == "error"
    assert "chaves" in projeto["error_message"] and projeto.get("completed_at")
    assert not main._TRANSIENT_ERR_RX.search(projeto["error_message"]), (
        "a mensagem casaria com erro passageiro e a varredura poderia relançar")
    assert banco.chamadas("DELETE", "project_items") == []
    assert int(projeto.get("auto_resume_count") or 0) == 0
    assert main._CHAVES_DA_AVALIACAO == {} and main._SEM_SINAPI_DA_AVALIACAO == set()
    (log,) = _retomadas(cena)
    assert log[3] == "warning"
    assert banco.inesperados == []


def test_CONTROLE_job_de_cliente_nunca_ganha_chave_pelo_nome(monkeypatch, tmp_path):
    """O nome é do cliente: em job de cliente ele não pode virar chave."""
    cena = _retomar(monkeypatch, tmp_path, JOB, "Obra nn" + FIM_COM_CHAVES)
    assert cena.ret is True and cena.esperar_disparo()
    (d,) = cena.disparos
    assert d["chaves"] == {} and d["env"] is None and d["sem_sinapi"] is False
    assert main._CHAVES_DA_AVALIACAO == {}
    assert _retomadas(cena) == []


@pytest.mark.parametrize("nome", [NOME + " — avaliação", NOME + " — combinado (1 PDF, 1 DXF)"])
def test_CONTROLE_avaliacao_sem_pedido_retoma_como_antes(monkeypatch, tmp_path, nome):
    cena = _retomar(monkeypatch, tmp_path, EV, nome)
    assert cena.ret is True and cena.esperar_disparo()
    (d,) = cena.disparos
    assert d["chaves"] == {} and d["env"] is None and d["sem_sinapi"] is False
    assert _retomadas(cena) == []
    assert cena.banco.projetos[0]["status"] == "queued"


def test_o_que_ja_esta_na_memoria_vale(monkeypatch, tmp_path):
    """Mesmo processo que registrou (a varredura periódica): a memória manda."""
    main._CHAVES_DA_AVALIACAO[EV] = {"SIMBOLO_DE_NIVEL_E_ANOTACAO": "0"}
    cena = _retomar(monkeypatch, tmp_path, EV, NOME + FIM_COM_CHAVES)
    assert cena.ret is True and cena.esperar_disparo()
    (d,) = cena.disparos
    assert d["chaves"] == {"SIMBOLO_DE_NIVEL_E_ANOTACAO": "0"}
    assert _retomadas(cena) == []


def test_quem_perde_a_trava_nao_rele_nem_para(monkeypatch, tmp_path):
    """Outro motor pegou o projeto entre a leitura e a trava: a retomada sai
    sem gravar — nem a memória, nem o erro."""
    def _outro_pegou(banco):
        banco.projetos[0]["status"] = "done"
    cena = _retomar(monkeypatch, tmp_path, EV, NOME + " — avaliação [CHAVE_QUE_SAIU_DA_LISTA=1]",
                    antes_do_patch=_outro_pegou)
    assert cena.ret == "ocupado" and cena.nao_disparou()
    assert cena.banco.projetos[0]["status"] == "done"
    assert _retomadas(cena) == []
