# -*- coding: utf-8 -*-
"""O peso de aço lido é conferido contra comprimento total × massa nominal.

🩸 22/09/2026 — job f8d8e6d8 (os mesmos 7 PDFs do ee801b82, relidos). Na
prancha da caixa de válvulas, a observação dizia "CTot = 1473,3 m" de ø8 e
"PTot … parcialmente cortado na imagem (lido como '58')" — e a linha saiu com
58 kg. 1.473,3 × 0,395 = 582 kg; o mesmo arquivo, no dia anterior, deu 582.
Erro de 10× com a conta certa escrita na própria linha.

🔑 A conferência já existia, só no caminho do CAD (`structural_extractor`,
faixa 0,70–1,70). O CONSERTO leva a mesma conta pro PDF:
  · peso e comprimento × massa nominal concordam (0,70–1,70, cabe o +10% de
    perdas dos quadros) → nada muda;
  · a razão é ≈ 10ⁿ (dígito perdido) → vira o calculado, ESTIMADO, e a linha diz;
  · diverge de outro jeito → só ALERTA com a conta; o número fica.

🚫 Por que não "diverge > 20% → troca": 📏 medido em 22/09 (90 dias, kg fora do
CAD com comprimento total e bitola na observação), 1 linha tem dígito perdido
(esta) e ~9 em 4 jobs divergem sem padrão — quadros que a própria IA marcou como
inconsistentes (tela soldada lida como ø5? dois quadros somados?). Nesses não se
sabe se errou o peso ou o comprimento; trocar seria escolher no chute. Regra nº3:
razão alerta, não decide.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

_CASO = ("Quantidade extraída diretamente do quadro RESUMO — AÇO CA-50 da Lista de "
         "Ferros: bitola ø8mm, CTot = 1473,3m, PTot ≈ 58kg. O valor exato de PTot "
         "está parcialmente cortado na imagem (lido como '58'). Comprimento total "
         "confirmado: 1473,3m.")


class _Item:
    def __init__(self, desc, qty, obs, unit="kg", origem="vision_pdf"):
        self.description = desc
        self.unit = unit
        self.quantity = qty
        self.observations = obs
        self.ref_sheet = "prancha-C.pdf (DE-X)"
        self.origem = origem
        self.confidence = "estimado"


def test_o_caso_58_kg_vira_582_e_a_linha_diz_por_que():
    it = _Item("Aço CA-50 ø8,0mm — armadura de paredes e laje", 58, _CASO)
    assert main._confere_peso_de_aco([it]) == (1, 0)
    assert abs(it.quantity - 581.8) < 0.2, it.quantity
    assert str(getattr(it.confidence, "value", it.confidence)) == "estimado"
    assert it.observations.startswith("PESO RECALCULADO: a linha dizia 58,00 kg"), (
        it.observations[:120])
    assert "1.473,30 m de ø8 × 0,395 kg/m (massa nominal NBR 7480)" in it.observations
    assert "10× menor" in it.observations
    assert "lido como '58'" in it.observations, "o texto da IA fica"


def test_o_digito_perdido_pra_MAIS_tambem():
    it = _Item("Aço CA-50 ø8,0mm", 5820, _CASO.replace("58kg", "5820kg"))
    assert main._confere_peso_de_aco([it]) == (1, 0)
    assert abs(it.quantity - 581.8) < 0.2 and "10× maior" in it.observations


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLES POSITIVOS — o que NÃO pode mudar
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_o_mesmo_arquivo_lido_certo_nao_muda():
    """ee801b82: a mesma linha com 582 kg. E um quadro com +10% de perdas."""
    certo = _Item("Armadura CA-50 ø8,0 mm", 582,
                  "CTot(ø8mm) = 1473,3 m × 0,395 kg/m = 581,95 kg")
    perdas = _Item("Aço CA-50 ø10,0 mm", 38.1,
                   "Resumo do aço: CA-50 ø10,0 mm — C.TOTAL = 56,2 m — PESO+10% = 38,1 kg")
    antes = (certo.observations, perdas.observations)
    assert main._confere_peso_de_aco([certo, perdas]) == (0, 0)
    assert (certo.quantity, perdas.quantity) == (582, 38.1)
    assert (certo.observations, perdas.observations) == antes


def test_CONTROLE_divergencia_sem_padrao_so_ALERTA():
    """262,8 m de ø8 dão 103,8 kg; a linha diz 262,8 kg (a leitura repetiu o
    número). Não é dígito perdido: o número fica, a conta vai pra frente."""
    it = _Item("Aço CA-50 ø8,0 mm — barras", 262.8,
               "Resumo do aço: CA-50 ø8,0 mm — C.TOTAL = 262,8 m — PESO+10% = 262,8 kg")
    assert main._confere_peso_de_aco([it]) == (0, 1)
    assert it.quantity == 262.8
    assert it.observations.startswith("⚠ CONFERIR: 262,80 m de ø8"), it.observations[:80]
    # 📏 o vizinho mais perto de "dígito perdido" no acervo: razão 8,5 (0,85 de
    # 10¹) — provável tela soldada lida como ø5. Fica, com alerta.
    tela = _Item("Armadura de aço CA-50 Ø 5,0 mm — vigas", 821,
                 "Peso lido do quadro de aço. Comprimento total indicado: 623 m.")
    assert main._confere_peso_de_aco([tela]) == (0, 1)
    assert tela.quantity == 821


def test_CONTROLE_varias_bitolas_na_linha_nao_tem_a_quem_aplicar_a_massa():
    it = _Item("Armadura CA-50 — total geral (Ø6,3 + Ø8 + Ø10mm)", 43.2,
               "Ø6,3mm: CTot = 950,4m; Ø8mm: 123,8m; Ø10mm: 244m.")
    assert main._confere_peso_de_aco([it]) == (0, 0)
    assert it.quantity == 43.2


def test_CONTROLE_numero_do_cliente_nao_se_toca():
    it = _Item("Aço CA-50 ø8,0mm", 58, _CASO, origem="revisao_cliente")
    assert main._confere_peso_de_aco([it]) == (0, 0)
    assert it.quantity == 58


def test_rodar_de_novo_nao_mexe_de_novo():
    ok = _Item("Aço CA-50 ø8,0mm", 58, _CASO)
    alerta = _Item("Aço CA-50 ø8,0 mm", 262.8, "C.TOTAL = 262,8 m — PESO = 262,8 kg")
    main._confere_peso_de_aco([ok, alerta])
    antes = (ok.quantity, ok.observations, alerta.observations)
    assert main._confere_peso_de_aco([ok, alerta]) == (0, 0)
    assert (ok.quantity, ok.observations, alerta.observations) == antes
