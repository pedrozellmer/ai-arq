# -*- coding: utf-8 -*-
"""Consertos da 2ª rodada de auditoria (31/08/2026).

30 achados de gravidade média/leve tinham ficado fora do corte de verificação da
1ª auditoria. Atacados um a um por um cético com ordem de REFUTAR: 21 procediam,
4 já tinham sido consertados durante o dia, 5 caíram.

Este arquivo cobre os quatro que o CLIENTE sente.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


class _Item:
    def __init__(self, desc, unit, qty, ref_sheet="", obs="", origem=""):
        self.description = desc
        self.unit = unit
        self.quantity = qty
        self.ref_sheet = ref_sheet
        self.observations = obs
        self.origem = origem
        self.confidence = "estimado"


def _prancha(arq, m2):
    return {"arquivo": arq, "rooms_m2": m2, "n_rooms": 10, "walls_m": 0,
            "n_walls": 0, "grupo_maior_m2": m2, "scale": 50, "scale_src": "cotas",
            "escala_validada": True, "cotas_batem": 29}


# ── #10 · a família era decidida por SUBSTRING ───────────────────────────────
def test_ARQUITETO_nao_vira_forro():
    """🩸 `"teto" in "arquiteto"` é True. "Piso de porcelanato do arquiteto" ia
    pro balde do FORRO, gastava a cota dele, e aí DOIS pisos podiam receber a
    área do pavimento — o erro do 'resumo somado em dobro' (28/08)."""
    pp = {"p0": _prancha("planta.pdf", 80.5)}
    piso = _Item("Piso de porcelanato do arquiteto", "m²", 0, "planta.pdf")
    forro = _Item("Forro acústico", "m²", 0, "planta.pdf")
    main._apply_area_honesty([piso, forro], pdfvec_por_prancha=pp)
    assert piso.quantity == 80.5 and forro.quantity == 80.5, (
        "as duas famílias colidiram: piso=%s forro=%s" % (piso.quantity, forro.quantity))


def test_DOIS_pisos_continuam_ambiguos_mesmo_com_arquiteto_no_nome():
    """🧪 Controle: a trava 4 não pode ter afrouxado junto."""
    pp = {"p0": _prancha("planta.pdf", 80.5)}
    a = _Item("Piso de porcelanato do arquiteto", "m²", 0, "planta.pdf")
    b = _Item("Piso vinílico", "m²", 0, "planta.pdf")
    main._apply_area_honesty([a, b], pdfvec_por_prancha=pp)
    assert a.quantity == 0 and b.quantity == 0, "dois pisos da mesma prancha preencheram"


def test_CONTROLE_teto_e_forro_de_verdade_seguem_sendo_forro():
    pp = {"p0": _prancha("planta.pdf", 80.5)}
    for d in ("Pintura de teto", "Forro de gesso", "Tetos rebaixados"):
        piso = _Item("Piso cerâmico", "m²", 0, "planta.pdf")
        outro = _Item(d, "m²", 0, "planta.pdf")
        main._apply_area_honesty([piso, outro], pdfvec_por_prancha=pp)
        assert piso.quantity == 80.5 and outro.quantity == 80.5, d


# ── #2 · o passo 7 não tinha teto ────────────────────────────────────────────
def test_area_MUITO_maior_que_a_informada_ganha_REVISAR():
    """🩸 O passo 7 é o único ramo que CRIA número e era o único sem teto: o
    `_check_plausibility` da casa roda ANTES, com a linha ainda zerada. Rodando,
    ele gravava 2.000 m² num imóvel que o cliente declarou ter 400."""
    # 🪤 Escrevi este teste com UM item só e ele falhou: com área informada, o
    # ramo da declaração preenche ANTES e o item nunca chega ao passo 7. O teto
    # só é alcançável quando a cota daquela família já foi gasta por outro item
    # — que é justamente o caso que a auditoria reproduziu.
    pp = {"p0": _prancha("planta.pdf", 2000.0)}
    gasta_cota = _Item("Piso cerâmico", "m²", 0)          # sem prancha
    it = _Item("Contrapiso", "m²", 0, "planta.pdf")        # único da prancha
    main._apply_area_honesty([gasta_cota, it], total_area=400,
                             total_area_source="informado", pdfvec_por_prancha=pp)
    assert gasta_cota.quantity == 400.0, "cenário mudou: a cota não foi gasta"
    assert it.quantity == 2000.0, "não é pra zerar — ratio ALERTA, não decide (nº3)"
    assert "REVISAR" in (it.observations or ""), (
        "2.000 m² num imóvel de 400 passou sem nenhum aviso")


def test_CONTROLE_area_plausivel_NAO_ganha_alarme():
    """🧪 Alarme que sai sempre vira ruído que ninguém lê."""
    pp = {"p0": _prancha("planta.pdf", 380.0)}
    gasta_cota = _Item("Piso cerâmico", "m²", 0)
    it = _Item("Contrapiso", "m²", 0, "planta.pdf")
    main._apply_area_honesty([gasta_cota, it], total_area=400,
                             total_area_source="informado", pdfvec_por_prancha=pp)
    assert it.quantity == 380.0
    assert "REVISAR" not in (it.observations or ""), "alarmou medição plausível"


# ── #1 e #11 · o log dizia "preservei" pro número que o passo 7 CRIOU ────────
def test_o_passo_7_tem_contador_PROPRIO():
    """🪤 Somava em `preservados`, e o log saía "preservei N item(ns) com
    procedência de geometria do PDF (0.00 m² de ambientes)" — verbo errado e uma
    procedência que não participou da conta. Mesma família do
    `preservados_por_pe_direito` que já custou um conserto em 26/08."""
    pp = {"p0": _prancha("planta.pdf", 80.5)}
    it = _Item("Piso cerâmico", "m²", 0, "planta.pdf")
    main._apply_area_honesty([it], pdfvec_por_prancha=pp)
    assert getattr(main._apply_area_honesty, "ultimo_criados_prancha", 0) == 1, (
        "o número CRIADO pelo passo 7 não tem contador próprio")
    assert getattr(main._apply_area_honesty, "ultimo_preservados", 0) == 0, (
        "o número criado ainda está sendo contado como PRESERVADO")


def test_CONTROLE_preservacao_de_verdade_continua_contando_como_preservada():
    """🧪 Separar os contadores não pode zerar o que era legítimo."""
    it = _Item("Piso cerâmico", "m²", 13.6,
               obs="Medido da GEOMETRIA do PDF (13.60 m² de ambientes).")
    main._apply_area_honesty([it], pdfvec_m2=13.6)
    assert it.quantity == 13.6
    assert getattr(main._apply_area_honesty, "ultimo_preservados", 0) == 1


# ── #17 · o e-mail de TESTE levava link de avaliação VÁLIDO ──────────────────
def test_email_de_exemplo_nao_grava_nota_de_verdade():
    """🩸 Preview e "Enviar teste pra mim" usam os MESMOS builders do envio real,
    então as estrelinhas saíam com token HMAC VÁLIDO. Clicar gravava nota real em
    produção e disparava o alerta pro admin. Com 5 avaliações em toda a história
    do produto, poluir com nota de teste estraga o pouco que existe."""
    _sub, html = main._render_email_by_type("planilha_pronta")
    import re
    vivos = re.findall(r'href="([^"]*obrigado\.html\?[^"]*)"', html or "")
    assert not vivos, "o e-mail de exemplo leva %d link(s) de nota VÁLIDOS: %s" % (
        len(vivos), vivos[:2])


def test_CONTROLE_o_email_de_exemplo_continua_mostrando_as_estrelas():
    """🧪 Neutralizar o link não pode apagar o convite — senão o preview deixa
    de mostrar o que o cliente vai ver."""
    _sub, html = main._render_email_by_type("planilha_pronta")
    assert "link desativado no teste" in html, "sumiu a marca de neutralização"
    assert html.count('href="#"') >= 3, (
        "as estrelas sumiram do exemplo — o preview deixou de representar o real")
