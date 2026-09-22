# -*- coding: utf-8 -*-
"""O resgate de comprimento não inventa layer num PDF.

🩸 22/09/2026 — job f8d8e6d8 (7 PDFs de estrutura, nenhum CAD). A fôrma de
vigas veio da IA com 24,3 m²; a honestidade de área zerou. Aí o resgate de
comprimento (`corrigir_comprimento_medido`, log `motor:comprimento`) achou na
observação "Comprimento total dos dois níveis: 2×16,20=32,40m" — a conta da
PRÓPRIA IA —, preencheu 32,40, trocou m² por m e escreveu:

    "⚠ QUANTIDADE RECUPERADA: o motor mediu 32,40 m neste layer…"

Três mentiras: PDF não tem layer, o número é da IA, e fôrma é área.

📏 60 d, sem avaliação: 3 recuperações em PDF (3 jobs), as 3 erradas — duas
fôrmas viradas em metro, e um montante de 69,1 m vindo de escala adivinhada
que a honestidade tinha zerado. Em CAD, 19 linhas em 7 jobs: lá o layer existe
e o comportamento fica.

🔑 Em texto lido de PDF: não recupera número (quem decide o número de PDF é a
honestidade, que já passou) e não troca área por comprimento.
"""
import os
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
from engine_rules import (  # noqa: E402
    corrigir_comprimento_medido,
    texto_veio_da_leitura_de_pdf,
)

_DESC_FORMA = "Fôrma de madeira compensada para vigas 20×45cm — dois níveis"
_OBS_FORMA = ("Comprimento total dos dois níveis: 2×16,20=32,40m. Área total: "
              "32,40×1,10=35,64m² bruto — descontando o fundo apoiado, ≈ 24,3m² "
              "líquido estimado.")


# ══════════════════════════════════════════════════════════════════════════
#  A regra, chamada de verdade
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_o_cenario_do_caso_disparava_o_resgate_antigo():
    """Sem dizer de onde veio o texto, vale a regra antiga — e ela reproduz o
    defeito. Prova que o cenário abaixo é o do caso, não um que já passava."""
    fix = corrigir_comprimento_medido(_DESC_FORMA, "m²", 0, _OBS_FORMA)
    assert fix.get("quantity") == 32.4 and fix.get("unit") == "m", fix
    assert "neste layer" in fix.get("motivo", ""), fix


def test_no_pdf_a_conta_da_IA_nao_volta_como_o_motor_mediu():
    fix = corrigir_comprimento_medido(_DESC_FORMA, "m²", 0, _OBS_FORMA,
                                      origem="vision_pdf", tem_cad=False)
    assert fix == {}, fix


def test_linha_sem_origem_num_job_so_de_pdf_tambem_e_pdf():
    """🪤 A consolidação às vezes perde a `origem` (no job, 6 das 91 linhas
    saíram sem ela). Sem CAD legível no envio, não há de onde vir um layer."""
    fix = corrigir_comprimento_medido(_DESC_FORMA, "m²", 0, _OBS_FORMA,
                                      origem="", tem_cad=False)
    assert fix == {}, fix


def test_no_pdf_area_nao_vira_metro_nem_so_no_rotulo():
    """Mesmo número na quantidade e no 'comprimento total': no CAD a regra só
    troca o rótulo; no PDF, área continua área."""
    obs = "Comprimento total = 24,30 m de viga."
    assert corrigir_comprimento_medido(_DESC_FORMA, "m²", 24.3, obs,
                                       origem="vision_pdf", tem_cad=False) == {}
    # CONTROLE: o mesmo texto num job com CAD ainda troca o rótulo
    assert corrigir_comprimento_medido(_DESC_FORMA, "m²", 24.3, obs,
                                       origem="", tem_cad=True).get("unit") == "m"


def test_no_pdf_o_rotulo_de_CONTAGEM_ainda_e_corrigido_sem_falar_de_layer():
    """O que continua valendo no PDF: a quantidade JÁ é o comprimento que a
    própria observação cita e a unidade é de contagem — só o rótulo está
    errado, e o texto não promete medição."""
    fix = corrigir_comprimento_medido("Guarda-corpo metálico", "un", 12.5,
                                      "Comprimento total = 12,50 m.",
                                      origem="vision_pdf", tem_cad=False)
    assert fix.get("unit") == "m", fix
    assert "quantity" not in fix, fix
    assert "layer" not in fix["motivo"] and "motor mediu" not in fix["motivo"], fix


def test_CONTROLE_no_CAD_o_layer_existe_e_o_resgate_continua():
    """O texto real de CAD (soma de layer feita pelo motor) segue recuperando —
    inclusive em m², que é o caso do hidrante da bancada antiga."""
    obs = "Fonte: comprimento total do layer 'HIDRO' = 1.234,50 m."
    for origem in ("", "dxf_geom"):
        fix = corrigir_comprimento_medido("Tubulação de incêndio", "m²", 0, obs,
                                          origem=origem, tem_cad=True)
        assert fix.get("quantity") == 1234.5 and fix.get("unit") == "m", (origem, fix)
        assert fix.get("confidence") == "estimado", fix


def test_quem_e_texto_de_pdf():
    assert texto_veio_da_leitura_de_pdf("vision_pdf", True) is True
    assert texto_veio_da_leitura_de_pdf("VISION_PDF ", True) is True
    assert texto_veio_da_leitura_de_pdf("", False) is True
    assert texto_veio_da_leitura_de_pdf(None, False) is True
    # CONTROLE: CAD no envio, ou origem que não é leitura de PDF
    assert texto_veio_da_leitura_de_pdf("", True) is False
    assert texto_veio_da_leitura_de_pdf("dxf_geom", False) is False
    assert texto_veio_da_leitura_de_pdf("deriv_pd", False) is False


# ══════════════════════════════════════════════════════════════════════════
#  O laço do process_job, recortado e EXECUTADO
# ══════════════════════════════════════════════════════════════════════════
class _It:
    def __init__(self, desc, unit, qty, obs, origem=""):
        self.description, self.unit, self.quantity = desc, unit, qty
        self.observations, self.origem = obs, origem
        self.confidence = "estimado"


def _roda_o_laco(itens, tem_cad):
    """Do `_cita = {}` até o relatório — os dois laços do resgate, como no
    motor. `_tem_cad_compr` é o que o `process_job` calcula logo acima."""
    from _corpo import fonte
    src = fonte("main.py")
    i = src.index("_fix = _corrigir_comprimento_medido(")
    ini = src.rindex(chr(10), 0, src.rindex("_cita = {}", 0, i)) + 1
    fim = src.index('print(f"[comprimento]', i)
    codigo = textwrap.dedent(src[ini:src.rindex(chr(10), 0, fim) + 1])
    ns = {
        "all_items": itens,
        "_corrigir_comprimento_medido": main._corrigir_comprimento_medido,
        "_limpa_aviso_nao_medida": main._limpa_aviso_nao_medida,
        "_medida_comprimento_obs": main._medida_comprimento_obs,
        "_medida_e_base_de_calculo": main._medida_e_base_de_calculo,
        "_Conf2": type("C", (), {"ESTIMADO": "estimado"}),
        "_n_uni": 0, "_n_rec": 0, "_n_ambiguo": 0,
        "_tem_cad_compr": tem_cad,
    }
    exec(compile(codigo, "laco-do-comprimento", "exec"), ns)
    return ns


def test_o_motor_passa_a_origem_do_item_e_a_forma_da_linha_fica():
    it = _It(_DESC_FORMA, "m²", 0, _OBS_FORMA, origem="vision_pdf")
    ns = _roda_o_laco([it], tem_cad=False)
    assert ns["_n_rec"] == 0, "o motor recuperou a conta da IA num PDF"
    assert (it.quantity, it.unit) == (0, "m²"), (it.quantity, it.unit)
    assert "layer" not in it.observations, it.observations


def test_CONTROLE_o_mesmo_laco_recupera_quando_o_job_tem_CAD():
    """Prova que o laço de cima não ficou mudo por outro motivo: com CAD no
    envio e linha sem origem, o resgate antigo roda."""
    it = _It("Rede de drenagem", "ml", 0,
             "Fonte: comprimento total do layer 'PLUVIAL' = 350,94 m.")
    ns = _roda_o_laco([it], tem_cad=True)
    assert ns["_n_rec"] == 1 and it.quantity == 350.94, (ns["_n_rec"], it.quantity)


def test_o_process_job_calcula_o_cad_pelo_dxf_legivel():
    """🪤 Guarda de FONTE: o recorte acima recebe `_tem_cad_compr` pronto; aqui
    se confere que o `process_job` o calcula, do DXF que o motor conseguiu ler
    (`dxf_paths`), não do que o cliente enviou."""
    from _corpo import fonte
    src = fonte("main.py")
    i = src.index("_fix = _corrigir_comprimento_medido(")
    antes = src[src.rindex("from models import Confidence as _Conf2", 0, i):i]
    assert "_tem_cad_compr = bool(dxf_paths)" in antes, antes[:400]
    chamada = src[i:src.index(")", src.index("tem_cad=", i)) + 1]
    assert 'origem=getattr(_it, "origem", "")' in chamada, chamada
    assert "tem_cad=_tem_cad_compr" in chamada, chamada
