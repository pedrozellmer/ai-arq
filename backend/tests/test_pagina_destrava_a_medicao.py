# -*- coding: utf-8 -*-
"""PDF com várias pranchas: a medição agora acha o dono.

🩸 CASO LUANA OLIVEIRA, 02/09/2026 (job `bf72d192`). Ela mandou **10 pranchas
dentro de um único PDF**. O motor mediu todas as dez — soma 583,6 m², a maior
com 95,7 — e entregou:

    preenchidos=0  criados_prancha=0  resgate_pdf=0
    motor:passo7-ambiguo: [('casa bruna - plantas anteprojeto.pdf', 'multipagina', 10)]

**A medição existia e não chegava em item nenhum.** A causa: o item guardava só
o NOME DO ARQUIVO no `ref_sheet`, e com dez pranchas de mesmo nome não havia como
saber de qual pavimento cada item veio. A trava 4 então se recusava a atribuir a
QUALQUER um — corretamente, porque chutar a prancha errada é pior.

📏 4 de 10 jobs de PDF mensuráveis do acervo têm PDF de várias páginas.

🔑 O conserto é levar a PÁGINA até o item: `SheetInfo` passou a carregar
`page_index`/`page_count`, e `ref_sheet` vira `arquivo.pdf (p3)` — mas SÓ quando
o arquivo tem mais de uma página, pra não mexer no `ref_sheet` dos 90% que não
têm o problema.

🪤 A página vai DENTRO dos parênteses de propósito: `projeto.html` faz
`raw.split('(')[0]` pra achar o arquivo, `_nome_limpo_da_prancha` corta no
" (", e o casamento do `_apply_area_honesty` é por prefixo. Tudo que está entre
parênteses já era descartado por quem precisa do filename — é por isso que o
hint da IA sempre morou lá. O botão "Ver prancha" continua funcionando.

🪤 A TRAVA 4 CONTINUA DE PÉ: item sem página (job antigo, ou `ref_sheet` que a
IA reescreveu) cai no caminho de sempre e o arquivo multipágina segue ambíguo.
Ganhar a página é bônus, nunca requisito — e a falta dela jamais vira chute.
"""
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import analyzer                                  # noqa: E402
import main                                      # noqa: E402
from models import SheetInfo, SheetType          # noqa: E402


def _sheet(nome, idx=0, cnt=1):
    return SheetInfo(filename=nome, sheet_type=SheetType.ARQUITETURA,
                     page_index=idx, page_count=cnt)


class _Item:
    def __init__(self, desc, unit, qty, ref_sheet="", obs="", origem="",
                 conf="estimado"):
        self.description, self.unit, self.quantity = desc, unit, qty
        self.ref_sheet, self.observations = ref_sheet, obs
        self.origem, self.confidence = origem, conf


def _prancha(arquivo, pagina, m2):
    return {"arquivo": arquivo, "pagina": pagina, "rooms_m2": m2, "n_rooms": 8,
            "walls_m": 0, "n_walls": 0, "grupo_maior_m2": m2, "scale": 50,
            "scale_src": "cotas", "escala_validada": True, "cotas_batem": 44}


# as pranchas reais do job da cliente-31 (3 das 10, com os m² do error_log)
CADERNO_LUANA = {
    "p0": _prancha("casa bruna - plantas anteprojeto.pdf", 0, 29.1),
    "p3": _prancha("casa bruna - plantas anteprojeto.pdf", 3, 85.6),
    "p5": _prancha("casa bruna - plantas anteprojeto.pdf", 5, 95.7),
}
ARQ = "casa bruna - plantas anteprojeto.pdf"


# ── O formato do ref_sheet ─────────────────────────────────────────────────
def test_arquivo_de_UMA_pagina_nao_ganha_pN():
    """🪤 90% dos casos. Pôr "(p1)" ali seria ruído e mexeria no `ref_sheet` de
    quem não tem o problema."""
    assert analyzer._monta_ref_sheet(_sheet("casa.pdf"), "") == "casa.pdf"
    assert analyzer._monta_ref_sheet(_sheet("casa.pdf"), "Planta Baixa") == \
        "casa.pdf (Planta Baixa)"


def test_arquivo_MULTIPAGINA_ganha_a_pagina():
    assert analyzer._monta_ref_sheet(_sheet("casa.pdf", 2, 10), "") == "casa.pdf (p3)"
    assert analyzer._monta_ref_sheet(_sheet("casa.pdf", 2, 10), "Corte AA") == \
        "casa.pdf (p3 · Corte AA)"


def test_a_pagina_volta_a_ser_lida():
    f = analyzer._pagina_do_ref_sheet
    assert f("casa.pdf (p3)") == 2
    assert f("casa.pdf (p3 · Corte AA)") == 2
    assert f("casa.pdf (p10)") == 9
    assert f("casa.pdf") is None
    assert f("casa.pdf (Planta Baixa)") is None


def test_CONTROLE_hint_com_pN_no_meio_NAO_vira_pagina():
    """🪤 Procurar `p<numero>` solto casaria com "planta p2 do bloco" e
    inventaria atribuição — pior que não atribuir."""
    assert analyzer._pagina_do_ref_sheet("casa.pdf (planta p2 do bloco)") is None


def test_CONTROLE_o_NOME_DO_ARQUIVO_continua_recuperavel():
    """🚨 É assim que o botão "Ver prancha" acha o PDF. Se isto quebrar, o
    cliente perde o visualizador — troca de problema, não conserto."""
    for ref in ("casa.pdf", "casa.pdf (p3)", "casa.pdf (p3 · Corte AA)"):
        assert ref.split("(")[0].strip() == "casa.pdf", ref
        assert main._nome_limpo_da_prancha(ref) == "casa.pdf", ref


# ── A atribuição, que é o ponto ────────────────────────────────────────────
def test_com_a_pagina_o_item_RECEBE_a_medicao_da_prancha_dele():
    """🩸 O que a cliente-31 não teve. O item da página 3 recebe os 85,6 m² da
    página 3 — não os 95,7 da maior, não zero."""
    it = _Item("Piso cerâmico", "m²", 0, ref_sheet="%s (p4)" % ARQ)
    main._apply_area_honesty([it], pdfvec_m2=210.4,
                             pdfvec_por_prancha=CADERNO_LUANA)
    assert it.quantity == 85.6, (
        "o item da página 4 não recebeu a medição dela (recebeu %r)" % it.quantity)


def test_cada_pagina_recebe_a_SUA_medicao():
    p1 = _Item("Piso cerâmico", "m²", 0, ref_sheet="%s (p1)" % ARQ)
    p6 = _Item("Piso vinílico", "m²", 0, ref_sheet="%s (p6)" % ARQ)
    main._apply_area_honesty([p1, p6], pdfvec_m2=210.4,
                             pdfvec_por_prancha=CADERNO_LUANA)
    assert (p1.quantity, p6.quantity) == (29.1, 95.7), (p1.quantity, p6.quantity)


def test_CONTROLE_POSITIVO_SEM_a_pagina_continua_ambiguo():
    """🧪 O comportamento ANTIGO, que é o que a cliente-31 pegou. Se este teste
    passar a preencher, a trava 4 caiu e a gente voltou a chutar prancha."""
    it = _Item("Piso cerâmico", "m²", 0, ref_sheet=ARQ)   # sem (pN)
    main._apply_area_honesty([it], pdfvec_m2=210.4,
                             pdfvec_por_prancha=CADERNO_LUANA)
    assert it.quantity == 0, (
        "item SEM página foi preenchido num arquivo de 10 pranchas — isso é "
        "chute: não há como saber de qual pavimento ele veio")


def test_CONTROLE_pagina_que_NAO_foi_medida_nao_inventa():
    """Página 8 não está no caderno medido: fica zerada."""
    it = _Item("Piso cerâmico", "m²", 0, ref_sheet="%s (p9)" % ARQ)
    main._apply_area_honesty([it], pdfvec_m2=210.4,
                             pdfvec_por_prancha=CADERNO_LUANA)
    assert it.quantity == 0


def test_CONTROLE_o_selo_continua_ESTIMADO():
    """🚨 Regra dura nº1: item de PDF nunca sai confirmado, nem quando a
    atribuição acerta a prancha."""
    it = _Item("Piso cerâmico", "m²", 0, ref_sheet="%s (p4)" % ARQ)
    main._apply_area_honesty([it], pdfvec_m2=210.4,
                             pdfvec_por_prancha=CADERNO_LUANA)
    assert str(getattr(it.confidence, "value", it.confidence)) == "estimado"


def test_CONTROLE_arquivo_de_uma_pagina_nao_mudou_de_comportamento():
    """O caminho antigo (um arquivo, uma prancha) segue igual."""
    uma = {"u": _prancha("planta baixa.pdf", 0, 80.5)}
    it = _Item("Piso cerâmico", "m²", 0, ref_sheet="planta baixa.pdf")
    main._apply_area_honesty([it], pdfvec_m2=80.5, pdfvec_por_prancha=uma)
    assert it.quantity == 80.5


def test_a_observacao_NOMEIA_a_prancha_certa():
    """🪤 Em 31/08 a observação chegou a NOMEAR a prancha errada. Se a gente
    atribui por página, o texto tem que dizer de onde veio."""
    it = _Item("Piso cerâmico", "m²", 0, ref_sheet="%s (p4)" % ARQ)
    main._apply_area_honesty([it], pdfvec_m2=210.4,
                             pdfvec_por_prancha=CADERNO_LUANA)
    assert "85.6" in (it.observations or "") or "85,6" in (it.observations or ""), (
        "a observação não cita a medição que foi usada: %r" % it.observations)
