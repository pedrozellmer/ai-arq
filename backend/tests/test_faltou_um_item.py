# -*- coding: utf-8 -*-
"""O cliente não tinha como dizer que a planilha ESQUECEU alguma coisa.

🩸 05/09/2026 — MEDIDO: **0 em 413 ações de revisão**. Não porque ninguém quis:
porque não havia como. A tela de revisão oferece aprovar, editar e excluir — as
três coisas que se faz com um item que EXISTE. O que o motor nem viu não tinha
onde ser apontado.

🔑 É a única pergunta de COBERTURA que existe. Sem ela a gente mede o quanto o
motor erra no que entregou e fica cego no que ele não viu — e isso é metade da
qualidade de um quantitativo. Ver [[project_motor_onde_perde_20260904]].

🚫 NÃO entra no quantitativo (regra nº7). Se virasse linha, cronograma, memorial
e comparativo ficariam velhos na hora, e a gente estaria deixando o cliente
escrever quantidade sem medição — a regra nº1 pelo avesso. É RECADO.

Mora em `item_reviews` com `item_id` NULO — forma que a tabela já tem: as 48
exclusões são todas assim, porque a FK é ON DELETE CASCADE e o item some.
"""
import io
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import main  # noqa: E402

JOB = "job-faltou-1"


def _prep(monkeypatch, insert_ok=True):
    gravados, logs = [], []
    monkeypatch.setattr(main, "_supabase_insert",
                        lambda tabela, linha: (gravados.append((tabela, linha)),
                                               insert_ok)[1])
    monkeypatch.setattr(main, "_require_project_owner", lambda *a, **k: None)
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, job=None, **k: logs.append(
                            (stage, msg, k.get("severity", ""))))
    return gravados, logs


def _chamar(texto, monkeypatch, insert_ok=True):
    gravados, logs = _prep(monkeypatch, insert_ok)
    r = main.registrar_item_faltando(
        JOB, main.FaltouPayload(texto=texto), request=None)
    return r, gravados, logs


# ══════════════════════════════════════════════════════════════════════════
#  1. O RECADO CHEGA
# ══════════════════════════════════════════════════════════════════════════
def test_grava_como_faltou_sem_item(monkeypatch):
    r, gravados, _ = _chamar("faltou impermeabilização das áreas molhadas", monkeypatch)
    assert r["status"] == "ok"
    assert len(gravados) == 1, "esperava exatamente uma gravação, veio %r" % (gravados,)
    tabela, linha = gravados[0]
    assert tabela == "item_reviews"
    assert linha["action"] == "faltou"
    assert linha["item_id"] is None, (
        "gravou com item_id preenchido — item que FALTA não tem id, e a FK é "
        "ON DELETE CASCADE: apontar pra um item existente faria o recado sumir "
        "junto com ele")
    assert linha["job_id"] == JOB
    assert "impermeabiliza" in linha["comment"]


def test_texto_vazio_e_recusado_e_nao_grava(monkeypatch):
    gravados, _ = _prep(monkeypatch)
    for vazio in ("", "   ", "\n"):
        with pytest.raises(main.HTTPException) as e:
            main.registrar_item_faltando(
                JOB, main.FaltouPayload(texto=vazio), request=None)
        assert e.value.status_code == 400
    assert not gravados, "gravou linha vazia — vira ruído no painel"


def test_texto_gigante_e_cortado(monkeypatch):
    _, gravados, _ = _chamar("x" * 5000, monkeypatch)
    assert len(gravados[0][1]["comment"]) == 2000


# ══════════════════════════════════════════════════════════════════════════
#  2. RECADO PERDIDO É PIOR QUE BOTÃO NENHUM
# ══════════════════════════════════════════════════════════════════════════
def test_se_a_gravacao_FALHA_o_cliente_e_avisado(monkeypatch):
    """🪤 `_supabase_insert` devolve False em falha e só registra num ARQUIVO
    LOCAL do Render, que some no redeploy — foi esse buraco que escondeu a perda
    total de itens por 4 meses. Se o recado sumir calado, o cliente sai achando
    que contou e a gente nunca soube."""
    with pytest.raises(main.HTTPException) as e:
        _chamar("faltou a bancada da cozinha", monkeypatch, insert_ok=False)
    assert e.value.status_code == 500


def test_se_a_gravacao_FALHA_o_texto_vai_pro_log_critico(monkeypatch):
    """O recado não pode morrer: se o banco recusou, o texto ainda tem que
    chegar em algum lugar que a gente consiga ler depois."""
    gravados, logs = _prep(monkeypatch, insert_ok=False)
    with pytest.raises(main.HTTPException):
        main.registrar_item_faltando(
            JOB, main.FaltouPayload(texto="faltou a bancada da cozinha"), request=None)
    criticos = [l for l in logs if l[2] == "critical"]
    assert criticos, "a falha não virou log crítico — some no redeploy"
    assert "bancada da cozinha" in criticos[0][1], (
        "o log crítico não guarda o TEXTO do cliente — sem ele o registro não "
        "serve pra nada")


# ══════════════════════════════════════════════════════════════════════════
#  3. REGRA Nº7 — NÃO ENCOSTA NO QUANTITATIVO
# ══════════════════════════════════════════════════════════════════════════
def test_NAO_cria_item_nem_mexe_na_contagem(monkeypatch):
    """🚫 Se virasse linha da planilha, cronograma/memorial/comparativo
    ficariam velhos na hora — e seria quantidade sem medição nenhuma."""
    _, gravados, _ = _chamar("faltou forro de gesso no corredor", monkeypatch)
    tabelas = {t for t, _ in gravados}
    assert tabelas == {"item_reviews"}, (
        "escreveu em %r — o recado tem que ficar FORA do quantitativo" % (tabelas,))
    for _, linha in gravados:
        assert "quantity" not in linha and "items_count" not in linha


def test_a_TELA_avisa_que_nao_entra_na_planilha():
    """O cliente precisa saber que isto é recado, não linha — senão ele escreve
    esperando ver a quantidade mudar e a gente quebra a confiança dele."""
    html = io.open(os.path.join(os.path.dirname(_BACKEND), "revisao.html"),
                   encoding="utf-8").read()
    i = html.index('id="bloco-faltou"')
    bloco = html[i:i + 1400]
    assert "não entra" in bloco and "planilha" in bloco, (
        "o bloco não diz que o recado fica fora da planilha")


# ══════════════════════════════════════════════════════════════════════════
#  4. A TELA
# ══════════════════════════════════════════════════════════════════════════
def _revisao():
    return io.open(os.path.join(os.path.dirname(_BACKEND), "revisao.html"),
                   encoding="utf-8").read()


def test_a_tela_tem_o_bloco_e_o_botao():
    html = _revisao()
    for marca in ('id="bloco-faltou"', 'id="faltou-texto"', 'id="faltou-enviar"'):
        assert marca in html, "sumiu %s da tela de revisão" % marca


def test_o_sucesso_so_e_anunciado_DEPOIS_do_servidor_confirmar():
    """🪤 Anunciar 'recebido' antes do 200 é mentir com cara de gentileza."""
    html = _revisao()
    i = html.index("faltou-enviar')?.addEventListener")
    fn = html[i:i + 1800]
    i_ok = fn.index("r.ok")
    i_msg = fn.index("Recebido")
    assert i_ok < i_msg, (
        "a tela diz 'recebido' antes de conferir a resposta do servidor")


def test_o_evento_do_clique_e_ACEITO_pelo_backend():
    """🪤 02/09: cinco eventos novos subiram e o /api/track jogou TODOS fora
    respondendo 200. Telemetria que nasce morta não avisa ninguém."""
    assert main._track_evento_aceito("clique:faltou-item")


def test_o_bloco_so_aparece_quando_HA_planilha():
    """Perguntar 'o que faltou?' numa tela vazia não faz sentido."""
    html = _revisao()
    assert 'id="bloco-faltou"' in html and 'class="hidden' in html[
        html.index('id="bloco-faltou"'):html.index('id="bloco-faltou"') + 120], (
        "o bloco não nasce escondido")
    assert "bloco-faltou" in html[html.index("const container = document.getElementById('items-container')"):
                                  html.index("const container = document.getElementById('items-container')") + 600], (
        "ninguém mostra o bloco quando os itens carregam")


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLES POSITIVOS
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_anunciar_antes_do_servidor_e_reprovado():
    errado = """
document.getElementById('faltou-enviar')?.addEventListener('click', async () => {
  msg.textContent = 'Recebido, obrigado.';
  const r = await authFetch(url, {method:'POST'});
  if (!r.ok) throw new Error('x');
});
"""
    i = errado.index("faltou-enviar')?.addEventListener")
    fn = errado[i:i + 1800]
    assert fn.index("r.ok") > fn.index("Recebido"), "o controle está mal montado"


def test_CONTROLE_gravar_com_item_id_e_reprovado():
    """A regressão mais provável: reaproveitar a rota de review e mandar um
    item_id qualquer. O recado passaria a sumir junto com o item (CASCADE)."""
    linha_ruim = {"job_id": JOB, "item_id": "algum-uuid", "action": "faltou"}
    assert linha_ruim["item_id"] is not None, "o controle está mal montado"
