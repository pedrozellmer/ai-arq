# -*- coding: utf-8 -*-
"""Avaliacao em 1 clique: nota do projeto (1-5) e NPS (0-10) — 31/08/2026.

Pedro pediu duas coisas separadas: uma avaliacao da ENTREGA pegando carona no
e-mail de "planilha pronta", e o NPS como pesquisa relacional de tempos em
tempos. Sao perguntas diferentes e escalas diferentes DE PROPOSITO — se a nota
por projeto caisse em `nps_responses` com escala 0-10, o NPS deixaria de medir
relacao e viraria media de qualidade de planilha (medido: 1 pessoa com 11
projetos em 49 dias puxaria a nota sozinha).

🪤 O TESTE MAIS IMPORTANTE DESTE ARQUIVO e o do PRE-CARREGAMENTO. Gmail,
Outlook e antivirus corporativo abrem os links do e-mail pra checar se sao
maliciosos. Se a nota gravasse no GET do link, um scanner varrendo os 5 botoes
registraria uma nota sozinho — sempre a mesma — envenenando exatamente o dado
que a gente esta tentando criar (5 avaliacoes em toda a historia do produto).
Por isso o link aponta pra uma PAGINA, que grava por POST em JavaScript.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

JOB = "job-abc"
EMAIL = "cliente@exemplo.com"


def _prep(monkeypatch, insert_ok=True):
    gravados = []
    monkeypatch.setattr(main, "_supabase_insert",
                        lambda tabela, linha: (gravados.append((tabela, linha)),
                                               insert_ok)[1])
    monkeypatch.setattr(main, "_supa_rows", lambda *a, **k: [])
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_alerta_nps", lambda *a, **k: None)
    monkeypatch.setattr(main, "_alerta_avaliacao_projeto", lambda *a, **k: None)
    return gravados


def _tok_proj():
    return main._nota_token("proj", f"{JOB}|{EMAIL}")


def _tok_nps():
    return main._nota_token("nps", EMAIL)


# ── o link do e-mail NAO pode gravar sozinho ─────────────────────────────
def test_LINK_DO_EMAIL_aponta_pra_pagina_e_nao_grava_no_GET():
    """Se este teste cair, um scanner de e-mail passa a votar pelos clientes."""
    bloco = main._bloco_avaliar_projeto(JOB, EMAIL)
    hrefs = re.findall(r'href="([^"]+)"', bloco)
    assert hrefs, "o bloco de nota nao tem link nenhum"
    for h in hrefs:
        assert "/obrigado.html?" in h, (
            "link do e-mail tem que abrir a PAGINA (que grava por JS). "
            f"Achei: {h}")
        assert "/api/" not in h, (
            "link do e-mail aponta pra API — pre-carregamento do Gmail viraria "
            f"nota gravada sem ninguem clicar: {h}")


def test_nao_existe_rota_GET_que_grave_avaliacao():
    """Guarda de arquitetura: gravar avaliacao e POST, sempre."""
    # 🪤 31/08 (auditoria): o laco nao tinha CONTADOR. Se alguem renomear a
    # rota (/api/nota, /api/feedback...), o `if` nunca casa, o laco nao roda e
    # o teste passa VERDE guardando coisa nenhuma — o modo de falha classico do
    # guarda que varre. Agora ele exige ter visto as rotas que conhece.
    vistas = 0
    for rota in main.app.routes:
        caminho = getattr(rota, "path", "")
        if caminho.startswith("/api/avaliar"):
            vistas += 1
            metodos = set(getattr(rota, "methods", []) or [])
            assert metodos <= {"POST"}, (
                f"{caminho} aceita {metodos} — GET aqui deixa o scanner de "
                "e-mail gravar nota sozinho")
    assert vistas >= 2, (
        "esperava ao menos /api/avaliar e /api/avaliar/comentario, achei %d — "
        "a rota foi renomeada e este guarda parou de vigiar qualquer coisa"
        % vistas)


# ── nota do PROJETO (1-5) ────────────────────────────────────────────────
def test_nota_do_projeto_vai_pra_processing_survey(monkeypatch):
    g = _prep(monkeypatch)
    r = main.registrar_avaliacao(main.NotaAvaliacao(
        tipo="projeto", k=JOB, e=EMAIL, t=_tok_proj(), n=4))
    assert r["status"] == "ok" and r["escala"] == "1a5"
    assert len(g) == 1
    tabela, linha = g[0]
    assert tabela == "processing_survey", (
        "nota da entrega em `nps_responses` contamina o NPS")
    assert linha["question_key"] == "nota_entrega_1a5"
    assert linha["answer"] == "4" and linha["job_id"] == JOB


@pytest.mark.parametrize("n", [0, 6, -1, 10])
def test_nota_do_projeto_fora_da_escala_e_recusada(monkeypatch, n):
    _prep(monkeypatch)
    with pytest.raises(main.HTTPException) as ex:
        main.registrar_avaliacao(main.NotaAvaliacao(
            tipo="projeto", k=JOB, e=EMAIL, t=_tok_proj(), n=n))
    assert ex.value.status_code == 400


def test_token_de_OUTRO_projeto_nao_serve(monkeypatch):
    """Sem isto, quem tem um link consegue avaliar projeto alheio."""
    _prep(monkeypatch)
    with pytest.raises(main.HTTPException) as ex:
        main.registrar_avaliacao(main.NotaAvaliacao(
            tipo="projeto", k="outro-job", e=EMAIL, t=_tok_proj(), n=5))
    assert ex.value.status_code == 403


def test_token_vazio_nao_serve(monkeypatch):
    _prep(monkeypatch)
    with pytest.raises(main.HTTPException) as ex:
        main.registrar_avaliacao(main.NotaAvaliacao(
            tipo="projeto", k=JOB, e=EMAIL, t="", n=5))
    assert ex.value.status_code == 403


def test_falha_de_gravacao_NAO_responde_ok(monkeypatch):
    """O erro que a casa persegue: agradecer por nota que nao gravou."""
    _prep(monkeypatch, insert_ok=False)
    with pytest.raises(main.HTTPException) as ex:
        main.registrar_avaliacao(main.NotaAvaliacao(
            tipo="projeto", k=JOB, e=EMAIL, t=_tok_proj(), n=3))
    assert ex.value.status_code == 502


# ── NPS (0-10) ───────────────────────────────────────────────────────────
def test_nps_vai_pra_nps_responses_com_contexto_proprio(monkeypatch):
    g = _prep(monkeypatch)
    r = main.registrar_avaliacao(main.NotaAvaliacao(
        tipo="nps", e=EMAIL, t=_tok_nps(), n=9))
    assert r["status"] == "ok" and r["escala"] == "0a10"
    tabela, linha = g[0]
    assert tabela == "nps_responses"
    assert linha["score"] == 9
    assert linha["context"] == "email_relacional", (
        "sem contexto proprio nao da pra separar o que veio do e-mail do que "
        "veio de dentro do site")


@pytest.mark.parametrize("n", [-1, 11])
def test_nps_fora_da_escala_e_recusado(monkeypatch, n):
    _prep(monkeypatch)
    with pytest.raises(main.HTTPException) as ex:
        main.registrar_avaliacao(main.NotaAvaliacao(
            tipo="nps", e=EMAIL, t=_tok_nps(), n=n))
    assert ex.value.status_code == 400


def test_token_de_projeto_nao_vale_pra_nps(monkeypatch):
    """Escopos separados: um token nao atravessa pro outro tipo."""
    _prep(monkeypatch)
    with pytest.raises(main.HTTPException) as ex:
        main.registrar_avaliacao(main.NotaAvaliacao(
            tipo="nps", e=EMAIL, t=_tok_proj(), n=10))
    assert ex.value.status_code == 403


# ── comentario ───────────────────────────────────────────────────────────
def test_comentario_do_projeto_grava_com_o_mesmo_token(monkeypatch):
    g = _prep(monkeypatch)
    r = main.avaliar_comentario(main.ComentarioAvaliacao(
        tipo="projeto", k=JOB, e=EMAIL, t=_tok_proj(), texto="faltou o forro"))
    assert r["status"] == "ok"
    tabela, linha = g[0]
    assert tabela == "processing_survey"
    assert linha["question_key"] == "comentario_entrega"
    assert linha["answer"] == "faltou o forro"


def test_comentario_com_token_errado_e_recusado(monkeypatch):
    _prep(monkeypatch)
    with pytest.raises(main.HTTPException) as ex:
        main.avaliar_comentario(main.ComentarioAvaliacao(
            tipo="projeto", k=JOB, e=EMAIL, t="xxx", texto="oi"))
    assert ex.value.status_code == 403


# ── os e-mails ───────────────────────────────────────────────────────────
# 🪤 31/08, 2ª auditoria: estes dois conferiam o e-mail REAL passando pelo
# `_render_email_by_type`, que é o caminho do PREVIEW. Quando o preview passou a
# NEUTRALIZAR os links de nota (o e-mail de teste gravava avaliação de verdade em
# produção), os dois quebraram — e estavam certos em quebrar: eles guardam uma
# coisa que o preview não representa mais. Agora chamam os builders do envio
# REAL, que é onde o link TEM que estar vivo.
def test_email_de_planilha_pronta_LEVA_os_botoes():
    _subj, html = main._build_planilha_pronta_email(
        "Pedro", "Residencial Vila Nova", "job-1234", 42, "",
        email="cliente@exemplo.com")
    assert "/obrigado.html?tipo=projeto" in html, (
        "o e-mail REAL perdeu o link de avaliação")
    assert "A planilha ficou boa?" in html


def test_email_de_nps_LEVA_os_botoes_e_a_foto():
    _subj, html = main._build_nps_relacional_email("Pedro", "cliente@exemplo.com")
    assert "/obrigado.html?tipo=nps" in html, (
        "o e-mail REAL de NPS perdeu o link de avaliação")
    assert "nps-foto.jpg" in html, "e-mail sem a foto do padrao da casa"
    for n in range(0, 11):
        assert f'>{n}</a>' in html, f"faltou o botao {n} na escala 0-10"


def test_o_PREVIEW_neutraliza_o_que_o_e_mail_real_leva_vivo():
    """🧪 O par dos dois de cima: a mesma coisa TEM que estar viva no envio real
    e MORTA no exemplo. Sem este teste, neutralizar o preview poderia ter
    escondido uma regressão no e-mail de verdade — foi o que quase aconteceu."""
    _s1, real = main._build_planilha_pronta_email(
        "Pedro", "Projeto", "job-1234", 42, "", email="cliente@exemplo.com")
    _s2, exemplo = main._render_email_by_type("planilha_pronta")
    assert "/obrigado.html?tipo=projeto" in real
    assert "/obrigado.html?tipo=projeto" not in exemplo


def test_os_dois_aparecem_no_catalogo_do_admin():
    """Pedro: *"deixa os exemplos de e-mail pra ver no admin"*."""
    chaves = {c["key"] for c in main._EMAIL_CATALOG}
    assert "planilha_pronta" in chaves and "nps_relacional" in chaves
    for k in ("planilha_pronta", "nps_relacional"):
        subj, html = main._render_email_by_type(k)
        assert subj and len(html) > 1000, f"{k} nao renderiza no preview"


def test_escalas_sao_DIFERENTES_entre_os_dois_emails():
    """1-5 na entrega, 0-10 no NPS: quem le o painel tem que saber, batendo o
    olho, qual pergunta gerou o numero."""
    proj = main._bloco_avaliar_projeto(JOB, EMAIL)
    nps = main._bloco_avaliar_nps(EMAIL)
    assert proj.count("obrigado.html") == 5, "a entrega tem que ter 5 botoes"
    assert nps.count("obrigado.html") == 11, "o NPS tem que ter 11 botoes"


def test_bloco_nao_sai_sem_email_nem_sem_job():
    """Sem chave nao da pra assinar — melhor nao mostrar botao do que mostrar
    botao que nao funciona."""
    assert main._bloco_avaliar_projeto("", EMAIL) == ""
    assert main._bloco_avaliar_projeto(JOB, "") == ""
    assert main._bloco_avaliar_nps("") == ""


def test_copy_muda_quando_o_motor_NAO_MEDIU():
    """Perguntar "a planilha ficou boa?" depois de nao medir nada e surdo."""
    normal = main._bloco_avaliar_projeto(JOB, EMAIL)
    ruim = main._bloco_avaliar_projeto(JOB, EMAIL, sem_medida=True)
    assert "A planilha ficou boa?" in normal
    assert "A planilha ficou boa?" not in ruim
    assert "faltou" in ruim.lower()


def test_CONTROLE_kind_desconhecido_NAO_manda_retorno30():
    """🪤 O laço de envio tinha `else: retorno30` — qualquer tipo novo saía como
    'sentimos sua falta'. O `nps_relacional` teria nascido assim."""
    import inspect
    src = inspect.getsource(main.emails_auto_tick)
    assert 'elif a["kind"] == "retorno_30d"' in src, (
        "o retorno_30d voltou a ser o ramo `else` — tipo novo vira e-mail errado")
    assert "kind-desconhecido" in src, "sumiu o alarme de tipo desconhecido"
