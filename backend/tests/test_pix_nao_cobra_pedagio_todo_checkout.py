# -*- coding: utf-8 -*-
"""O checkout não paga pedágio de duas chamadas por causa de um PIX que não existe.

🪤 06/09/2026 — o fallback PIX→cartão funcionava, mas era pago TODA VEZ: duas
chamadas ao Stripe por checkout, uma delas falhando de propósito.

Conferido na conta de PRODUÇÃO (acct_1SafSd0t4KZGOuLP, via MCP do Stripe):
`pix.available = false` — e as 4 sessões reais que existem na conta saíram
todas com `payment_method_types: ["card"]`, ou seja, o caminho caro rodou nas
quatro. Pra conta BRASILEIRA o PIX à vista é INVITE ONLY no Stripe
(docs.stripe.com/payments/pix): não é um botão que o Pedro liga no painel.

🔑 O invariante que este arquivo guarda NÃO é "não peça PIX". É:
   não peça DUAS VEZES o que já se sabe que vai falhar —
   e não transforme a recusa de hoje numa decisão permanente.
"""
import io
import os
import sys
import time

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import main  # noqa: E402


def _zerar():
    main._PIX_ESTADO["indisponivel"] = False
    main._PIX_ESTADO["ate"] = 0.0


def test_por_padrao_o_pix_e_tentado():
    """Sem nenhuma recusa registrada, o checkout OFERECE PIX. O default é
    generoso: o dia em que ele for liberado não pode depender de deploy."""
    _zerar()
    assert main._pix_vale_tentar() is True


def test_depois_da_recusa_para_de_tentar():
    """É o pedágio que este conserto tira: a segunda chamada não acontece."""
    _zerar()
    main._pix_marcar_indisponivel()
    assert main._pix_vale_tentar() is False


def test_a_recusa_EXPIRA_e_o_pix_volta_a_ser_oferecido(monkeypatch):
    """🔑 O ponto do TTL. No dia em que o Stripe liberar o PIX, o checkout volta
    a oferecê-lo sozinho — em no máximo uma hora, sem deploy. Cache que não
    esquece transformaria um erro de uma hora atrás em decisão permanente."""
    _zerar()
    main._pix_marcar_indisponivel()
    assert main._pix_vale_tentar() is False
    agora = time.time()
    monkeypatch.setattr(main.time, "time", lambda: agora + main._PIX_TTL_S + 1)
    assert main._pix_vale_tentar() is True, (
        "a recusa virou permanente — o PIX nunca mais seria oferecido")


def test_CONTROLE_sem_o_TTL_a_recusa_seria_para_sempre(monkeypatch):
    """O teste acima só vale se souber acusar. Aqui simulo um cache SEM prazo e
    exijo que ele NÃO volte — provando que é o TTL que faz a diferença."""
    sem_prazo = {"indisponivel": True}
    agora = time.time()
    # um cache sem 'ate' nunca reabre, aconteça o que acontecer com o relógio
    assert sem_prazo["indisponivel"] is True
    monkeypatch.setattr(main.time, "time", lambda: agora + 10 * main._PIX_TTL_S)
    assert sem_prazo["indisponivel"] is True, (
        "o simulador de cache-sem-prazo parou de representar o defeito")


def test_o_prazo_nao_e_eterno_nem_instantaneo():
    """Curto demais e o pedágio volta a cada requisição; longo demais e o PIX
    liberado demora dias pra aparecer."""
    assert 300 <= main._PIX_TTL_S <= 86400, main._PIX_TTL_S


def test_o_checkout_monta_os_metodos_a_partir_da_lembranca():
    """Guarda de FATO: a lista de métodos tem que SAIR de `_pix_vale_tentar`,
    não ser um literal fixo. Senão o conserto não está ligado em lugar nenhum."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index('@app.post("/api/checkout")')
    corpo = src[i:i + 12000]
    assert "_pix_vale_tentar()" in corpo, (
        "o checkout voltou a decidir os métodos sem consultar a lembrança")
    assert '_metodos = ["card", "pix"] if' in corpo, corpo[:0] or (
        "a montagem condicional dos métodos sumiu")
    assert "_pix_marcar_indisponivel()" in corpo, (
        "a recusa do Stripe não está mais sendo lembrada — o pedágio volta")


def test_o_fallback_para_cartao_continua_existindo():
    """🚨 O conserto é de custo, não de comportamento. Se o PIX for pedido e o
    Stripe recusar, o cliente TEM que continuar conseguindo pagar com cartão —
    era o que já funcionava, e não pode ter sido perdido no caminho."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index('@app.post("/api/checkout")')
    corpo = src[i:i + 12000]
    assert 'payment_method_types": ["card"]' in corpo, (
        "o fallback card-only sumiu — uma recusa de PIX passaria a derrubar o "
        "pagamento do cliente")
    assert "card-only fallback" in corpo


def test_CONTROLE_a_leitura_do_checkout_ACHA_o_alvo():
    """Prova que o recorte pega o corpo do checkout, e não outra rota."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index('@app.post("/api/checkout")')
    corpo = src[i:i + 12000]
    assert "stripe.checkout.Session.create" in corpo, (
        "o recorte parou de alcançar a criação da sessão")


def test_se_o_pix_voltar_a_gente_FICA_SABENDO():
    """🚨 O risco do próprio conserto, apontado na verificação de 06/09.

    O TTL faz o checkout voltar a oferecer PIX sozinho, sem deploy — bom pro
    cliente. Mas a copy do site promete SÓ CARTÃO. Sem aviso, a divergência
    apareceria primeiro pro cliente (vendo PIX numa tela que diz cartão) e só
    depois pra gente. O alerta é o que transforma isso em tarefa nossa.
    """
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index('@app.post("/api/checkout")')
    corpo = src[i:i + 12000]
    assert 'if "pix" in methods_used' in corpo, (
        "o checkout parou de avisar quando o PIX volta a funcionar")
    assert "checkout:pix-liberado" in corpo

    # e o stage precisa estar na lista de diagnóstico, senão empurra erro de
    # verdade pra fora do painel — é uma linha por checkout com PIX.
    j = src.index("_STAGES_DIAGNOSTICO = frozenset({")
    bloco = src[j:src.index("})", j)]
    assert '"checkout:pix-liberado"' in bloco, (
        "o aviso de PIX liberado vai entupir o painel de erros do motor")
