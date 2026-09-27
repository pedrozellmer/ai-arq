# -*- coding: utf-8 -*-
"""Lote 1 da auditoria completa do Escritório (26/09/2026) — acesso e o que já estava no ar.

Pedro: "bora, conserta tudo". Os achados (workflows wf_8e056f99-eb5 e wf_38b94278-82d) cobertos aqui:
  • SRV-3 — o cronograma levava previsto × realizado (dinheiro) pra equipe, que não vê financeiro;
  • SRV-1/PRANCHA-1 — "pode baixar" não cobria as pranchas: o PDF original saía pelo visualizador;
  • B-1 — no 1º acesso ao painel, falha de leitura do Escritório mandava o boas-vindas de cliente;
  • RLS-1 (5 lentes) — tirar da equipe não garantia tirar a pasta do Drive: a tela agora espera e diz, e a
    varredura horária tenta de novo (a faxina roda antes da chave dos e-mails);
  • CONV-1 — computador compartilhado: convite de uma pessoa aceito pela conta de outra sem aviso;
  • LOG-A1 / LOG-A3 — convite sem código + sem ficha se perdia; com 2+ convites só aparecia 1;
  • UX-4 / LOG-C1 / LOG-C4 / UX-5 — emissão em dobro, retorno com data futura, número de revisão chutado.
O comportamento do servidor (aceite, Drive, emitir) está nos testes próprios; aqui ficam as rotas do medido e as
telas, lidas pelo que decide (a instrução), não pela palavra.
"""
import asyncio
import os
import sys
import types

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
_RAIZ = os.path.dirname(_BACKEND)
sys.path.insert(0, _BACKEND)

import main  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def _ler(nome):
    return open(os.path.join(_RAIZ, nome), encoding="utf-8").read()


def _corpo(fonte, cabeca, fim="\n}\n"):
    i = fonte.index(cabeca)
    return fonte[i:fonte.index(fim, i)]


# ── SRV-3: o dinheiro da obra fica fora do cronograma da equipe ──
def test_cronograma_sem_dinheiro_tira_o_bloco_e_os_valores_das_fases():
    cron = {"financeiro": {"total_informado": 150000}, "fases": [{"label": "Obra", "valor_previsto": 100, "valor_realizado": 90, "inicio": "2026-10-01"}],
            "fases_custom": [{"label": "X", "valor_previsto": 5}], "gantt": [1, 2]}
    limpo = main._cronograma_sem_dinheiro(cron)
    assert "financeiro" not in limpo and limpo["gantt"] == [1, 2]
    assert limpo["fases"] == [{"label": "Obra", "inicio": "2026-10-01"}] and limpo["fases_custom"] == [{"label": "X"}]
    assert cron["financeiro"] and cron["fases"][0]["valor_previsto"] == 100, "não mexe no original (o dono segue vendo)"


def test_todas_as_saidas_do_cronograma_passam_pelo_corte_pra_equipe():
    src = open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    g = src[src.index("def get_cronograma(job_id"):src.index("@app.post(\"/api/cronograma/{job_id}/save\")")]
    assert "if _so_leitura(request):\n        saved = _cronograma_sem_dinheiro(saved)" in g
    full = src[src.index("def get_cronograma_full("):src.index("def _build_cronograma_for_export(")]
    assert "return _cronograma_sem_dinheiro(cron) if _so_leitura(request) else cron" in full
    for rota in ("async def export_cronograma_pdf(", "async def export_cronograma_xlsx(", "async def export_cronograma_pptx("):
        corpo = src[src.index(rota):]
        corpo = corpo[:corpo.index("\n@app.")]
        assert "if _so_leitura(request):\n        cron = _cronograma_sem_dinheiro(cron)" in corpo, rota


# ── SRV-1: o PDF original só pra quem pode baixar ──
def _sheet(monkeypatch, so_leitura, pode_baixar, arquivo):
    def viewer(request, job_id, baixar=False):
        request.state.so_leitura = so_leitura
        request.state.pode_baixar = pode_baixar
        return "dono"
    monkeypatch.setattr(main, "_require_project_viewer", viewer)
    monkeypatch.setattr(main, "_find_prancha_file", lambda job, ref: arquivo)
    monkeypatch.setattr(main, "WORK_DIR", os.path.join(_AQUI, "__nao_existe__"))
    req = types.SimpleNamespace(headers={}, state=types.SimpleNamespace())
    try:
        asyncio.run(main.get_sheet_pdf("job-exemplo", req, ref="planta.pdf"))
    except HTTPException as e:
        return e
    except Exception as e:   # passou da trava e morreu adiante (sem storage no teste): não é a trava
        return e
    return None


def test_pdf_original_e_recusado_pra_equipe_sem_pode_baixar(monkeypatch):
    e = _sheet(monkeypatch, True, False, "planta.pdf")
    assert isinstance(e, HTTPException) and e.status_code == 403
    assert "liberação de download" in e.detail


@pytest.mark.parametrize("so_leitura,pode,arquivo", [(True, True, "planta.pdf"), (True, False, "planta.png"), (False, False, "planta.pdf")])
def test_controle_quem_pode_baixar_imagem_renderizada_e_o_dono_passam_da_trava(monkeypatch, so_leitura, pode, arquivo):
    e = _sheet(monkeypatch, so_leitura, pode, arquivo)
    assert not (isinstance(e, HTTPException) and e.status_code == 403), e


def test_o_visualizador_esconde_o_baixar_pra_quem_nao_foi_liberado():
    h = _ler("visualizar-prancha.html")
    assert "html.sem-baixar #btn-baixar{display:none!important}" in h
    assert "if (window.aiarqMarcarSoLeitura) window.aiarqMarcarSoLeitura(jobId);" in h
    assert "if (document.documentElement.classList.contains('sem-baixar')) return;" in _corpo(h, "window.downloadPdf = async function()", "\n  };\n")


# ── B-1: na dúvida, o 1º acesso também não manda o boas-vindas de cliente ──
def test_primeiro_acesso_espera_quando_nao_leu_o_escritorio():
    src = open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("# 🏢 quem veio por convite do Escritório não leva o boas-vindas de cliente")
    bloco = src[i:src.index("sent = _send_welcome_email(email, name)", i)]
    assert "if _conv is None or _pend is None:\n        return {\"status\": \"ok\", \"sent\": False, \"reason\": \"escritorio_nao_leu\"}" in bloco
    assert "except Exception:\n        pass" not in bloco, "falha de leitura não pode seguir pro envio"


# ── RLS-1: a faxina roda na varredura horária, antes da chave dos e-mails, e nunca no ensaio ──
def test_faxina_do_drive_roda_no_tick_antes_da_chave_dos_emails():
    src = open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    t = src[src.index("def emails_auto_tick("):]
    t = t[:t.index("now = _dt.now(_tz.utc)")]
    assert t.index("_ed_faxina.faxina()") < t.index('if os.environ.get("EMAILS_AUTO", "1") == "0":')
    assert "if not dry:" in t[:t.index("_ed_faxina.faxina()")]


def test_tirar_da_equipe_espera_o_drive_e_diz_o_que_aconteceu():
    h = _ler("escritorio.html")
    ct = _corpo(h, "async function confirmarTirar(id) {")
    assert "if (m.status !== 'convidado' && PROJ.pasta_id) return tirarDaPasta(m);" in ct
    assert "sincronizarPasta(true)" not in ct, "a retirada calada voltou"
    tp = _corpo(h, "async function tirarDaPasta(m) {")
    assert "else if (d.sem_conexao)" in tp and "if (!r.ok)" in tp
    # 27/09 (board TELA-8): o resultado é o DESTA pessoa (saidas), e a falha dela só pelas falhas de TIRAR
    assert "saida = (d.saidas || {})[m.id]" in tp and "(d.falhas_tirar || []).length" in tp
    assert "(d.falhas || []).length" not in tp, "voltou a culpar quem saiu por falha de DAR acesso a outra pessoa"


# ── CONV-1 / LOG-A1 / LOG-A3: o convite ──
def test_confirmacao_mostra_pra_quem_foi_o_convite_e_trata_o_428():
    h = _ler("convite.html")
    assert "$('cf-para').textContent = v.dados.email || 'o e-mail do convite';" in h
    ac = h[h.index("async function aceitarAgora()"):]
    assert "if (a.status === 428 && a.dados.detail && a.dados.detail.codigo === 'outra_conta') {" in ac
    assert ac.index("a.status === 428") < ac.index("return recusado(a)"), "o 428 não pode cair no 'não vale mais'"
    sair = _corpo(h, "async function sairEUsarOutraConta()", "\n  }\n")
    assert "if (!destaAba) window.aiarqConvite.limparSe(token);" in sair


def test_sem_codigo_sem_ficha_volta_pro_convite_e_mostra_todos_os_convites():
    h = _ler("convite.html")
    s = _corpo(h, "async function semCodigo(opcoes) {", "\n  }\n")
    assert s.index("sessionStorage.setItem('aiarq_convite_sem_codigo', '1')") < s.index("location.href = 'cadastro.html'")
    assert "lista.forEach((c) => {" in s and "b.textContent = " in s and "innerHTML" not in s
    cad = _ler("cadastro.html")
    assert "const destinoDepois = () => ((_convite || _voltaSemCodigo) ? 'convite.html' : 'dashboard.html');" in cad


def test_o_cadastro_so_confia_no_convite_desta_aba_ou_de_conta_nova():
    cad = _ler("cadastro.html")
    assert "let _convite = _pendente && _abaConvite && _pendente.t === _abaConvite ? _pendente : null;" in cad
    assert ("if (!_convite && _pendente && _pendente.em && Date.parse(currentUser.created_at || '') >= _pendente.em) _convite = _pendente;"
            in cad[cad.index("async function checkAuth()"):])


# ── emitir: tela ──
def test_modal_de_emitir_nao_fecha_no_meio_nem_oferece_tentar_de_novo_sem_saber():
    h = _ler("escritorio.html")
    assert "function fecharModal() { if (EMITINDO) return; $('modal').hidden = true; }" in h
    ce = _corpo(h, "async function confirmarEmissao(id) {")
    assert ce.index("EMITINDO = true;") < ce.index("apiEsc(`projetos/${PROJ.id}/emitir`")
    assert "finally { EMITINDO = false; }" in ce
    assert ce.index("if (!r.ok && r.status === 0) {") < ce.index("b.textContent = 'Tentar de novo'")


def test_retorno_nao_aceita_data_futura_e_pode_ser_apagado():
    h = _ler("escritorio.html")
    sr = _corpo(h, "async function salvarRetorno(id) {")
    assert "if (em > hojeISO()) return toast(" in sr
    assert "max=\"${hojeISO()}\"" in _corpo(h, "function registrarRetorno(id) {")
    assert ".from('escritorio_emissao_eventos').delete().eq('id', id).eq('projeto_id', PROJ.id)" in _corpo(h, "function apagarRetorno(id) {")


def test_modal_nao_chuta_a_revisao_sem_as_emissoes_lidas():
    h = _ler("escritorio.html")
    assert "const rotulo = TEM_EMI ? revTxt(prox) : 'nova revisão';" in _corpo(h, "function emitirArquivo(id, nome) {")


# ── o banco (seção 25) ──
def test_a_secao_25_esta_no_sql_do_repo():
    sql = open(os.path.join(_BACKEND, "migrations_pendentes", "escritorio_piloto_dtz_banco.sql"), encoding="utf-8").read()
    s = sql[sql.index("── 25. (26/09"):]
    assert "or new.email_conta is distinct from old.email_conta" in s, "só o servidor escreve o e-mail da conta"
    assert "ja_existia boolean not null default false" in s
    assert "grant execute on function public.escritorio_contatos(uuid) to authenticated, service_role;" in s
    assert "revoke all on function public.escritorio_contatos(uuid) from public, anon;" in s
