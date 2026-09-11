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

Estes guardas CHAMAM `_mensagem_sem_itens`, `_build_falha_email` e
`_linha_do_email_ao_cliente`; a AST do `process_job` só onde não dá pra chamar.
"""
import ast
import io
import json
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import main  # noqa: E402


# ── a mensagem do cliente ─────────────────────────────────────────────────────
def test_tipo_ESTRUTURA_sem_item_manda_marcar_arquitetura_e_nao_culpa_o_pdf():
    msg = main._mensagem_sem_itens(True, 3)
    assert "Arquitetura" in msg and "Estrutura" in msg, msg
    assert "escaneada" not in msg.lower(), msg


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


def test_email_do_tipo_estrutura_manda_reenviar_marcando_arquitetura():
    subject, html = _falha(main._mensagem_sem_itens(True, 3))
    assert "Arquitetura" in html and "escaneada" not in html.lower(), html[:600]
    assert "outro arquivo" not in subject and "Arquitetura" in subject, subject


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


def test_o_process_job_monta_o_erro_de_zero_item_pelo_helper_com_o_TIPO():
    fn = _process_job()
    usos = [n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_mensagem_sem_itens"]
    assert usos, "o process_job não chama _mensagem_sem_itens"
    assert all(isinstance(u.args[0], ast.Name) and u.args[0].id == "is_structural" for u in usos), \
        "o 1º argumento tem que ser o tipo do projeto (is_structural)"
    literais = [n.value for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert not any("Nenhum item quantificável foi identificado neste" in t for t in literais), \
        "o texto antigo voltou solto dentro do process_job"


def test_concluir_o_projeto_LIMPA_o_erro_antigo():
    fn = _process_job()
    gravacoes = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_supabase_update":
            for a in n.args:
                if isinstance(a, ast.Dict):
                    ch = {k.value: v for k, v in zip(a.keys, a.values) if isinstance(k, ast.Constant)}
                    st = ch.get("status")
                    if isinstance(st, ast.Constant) and st.value == "done" and "items_count" in ch:
                        gravacoes.append(ch)
    assert gravacoes, "não achei a gravação de conclusão do process_job"
    for ch in gravacoes:
        em = ch.get("error_message")
        assert isinstance(em, ast.Constant) and em.value is None, "a conclusão não limpa error_message"
    locais = [n for n in ast.walk(fn)
              if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "update_field"
              and any(k.arg == "status" and isinstance(k.value, ast.Constant) and k.value.value == "done"
                      for k in n.keywords)]
    assert locais, "não achei o status local de conclusão"
    for n in locais:
        assert any(k.arg == "error_message" for k in n.keywords), \
            "status local 'done' sem limpar error_message (linha %d)" % n.lineno


# ── o alerta interno ──────────────────────────────────────────────────────────
class _Resp:
    def __init__(self, dados):
        self._b = json.dumps(dados).encode("utf-8")

    def read(self):
        return self._b


def _linha(monkeypatch, dados=None, erro=None):
    pedidos = []

    def falso(req, timeout=None):
        pedidos.append(getattr(req, "full_url", str(req)))
        if erro is not None:
            raise erro
        return _Resp(dados)
    monkeypatch.setattr(main, "SUPABASE_URL", "https://exemplo.supabase.co")
    monkeypatch.setattr("urllib.request.urlopen", falso)
    linha = main._linha_do_email_ao_cliente("cliente@exemplo.com", "2026-09-11T12:36:10+00:00")
    return linha, pedidos


def test_alerta_NAO_afirma_email_sem_registro_e_olha_so_DEPOIS_do_projeto(monkeypatch):
    linha, pedidos = _linha(monkeypatch, dados=[])
    assert "NÃO há registro" in linha, linha
    assert pedidos and "sent_at=gte." in pedidos[0] and "erro_trocar" in pedidos[0], pedidos


def test_alerta_diz_que_recebeu_quando_o_registro_existe(monkeypatch):
    linha, _ = _linha(monkeypatch, dados=[{"kind": "erro_trocar", "sent_at": "2026-09-11T12:38:40+00:00"}])
    assert linha.startswith("O cliente recebeu o e-mail de falha"), linha


def test_alerta_diz_que_nao_deu_pra_confirmar_quando_a_consulta_falha(monkeypatch):
    linha, _ = _linha(monkeypatch, erro=OSError("rede fora"))
    assert "Não deu pra confirmar" in linha, linha


def test_o_alerta_nao_tem_mais_a_frase_FIXA():
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    literais = [n.value for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert not any("O cliente já recebeu o email de falha" in t for t in literais)
