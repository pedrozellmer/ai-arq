# -*- coding: utf-8 -*-
"""O cronograma não chama de "calculada" uma conta feita de estimativa.

🩸 07/09/2026 — MEDIDO nos 10 cronogramas da base, por percentual de
quantidade LARANJA por trás da conta:

    e0809082    8 itens,  0 medidos → 100% laranja
    55796d1e   33 itens,  0 medidos → 100% laranja
    cae889fa   25 itens,  1 medido  →  96%
    349e75a5  260 itens, 28 medidos →  89%
    …
    c09789af   41 itens, 24 medidos →  41% (o MELHOR da base)

**Dois cronogramas foram calculados com ZERO item medido** e carimbavam
"⚙ calculada das quantidades" do mesmo jeito. Mediana: 85% de laranja.

🔑 `calculada` nesta casa significa SAIU DO DESENHO — é o mesmo vocabulário do
selo BRANCO do quantitativo. Usá-lo numa conta de estimativa é a regra dura nº1
pelo avesso, no lugar mais visível do produto: o prazo que o arquiteto leva pro
cliente dele.

🚫 A ESTIMATIVA NÃO É JOGADA FORA. Ela continua entrando na conta e o número
segue valendo — estimativa ROTULADA é útil; estimativa com cara de medição é
que não é. O que muda é só o que a tela afirma.

🪤 E o caminho `fases_custom` é o PADRÃO, não a exceção: 10 de 10 cronogramas
salvos têm `fases_custom`. Ele trocava a ressalva longa por "Cronograma editado
manualmente pelo usuário" — sumindo com a única frase que explica que laranja
entra na conta, e ainda afirmando edição manual que pode não ter havido.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
_RAIZ = os.path.dirname(_BACKEND)
sys.path.insert(0, _BACKEND)

from cronograma_produtividade import esforco_por_fase  # noqa: E402


def _item(desc, unit, qty, selo):
    return {"discipline": desc, "unit": unit, "quantity": qty, "confidence": selo,
            "description": "linha de teste"}


#: A fase precisa existir no mapa de referências pra a conta rodar.
def _fase(_d):
    return "Alvenaria"


def _so(items):
    """Roda a conta e devolve a entrada da fase, ou None."""
    return esforco_por_fase(items, _fase).get("Alvenaria")


# ═══════════════════════════════════════════════════════════════════════════
#  A origem segue o selo das quantidades
# ═══════════════════════════════════════════════════════════════════════════

def test_tudo_MEDIDO_continua_calculada():
    """O caso bom não pode ter sido perdido no conserto."""
    r = _so([_item("ALVENARIA", "m²", 100.0, "confirmado")])
    assert r, "a conta não rodou — o fixture não casa com o mapa de referências"
    assert r["origem"] == "calculada", r["origem"]
    assert r["pct_medido"] == 100.0


def test_ZERO_medido_vira_ESTIMADA():
    """🚨 Os dois piores da base: 0 item medido, carimbados 'calculada'."""
    r = _so([_item("ALVENARIA", "m²", 100.0, "estimado")])
    assert r["origem"] == "estimada", (
        "conta feita 100%% de estimativa saiu como %r" % r["origem"])
    assert r["pct_medido"] == 0.0


def test_MISTURA_vira_calculada_parcial():
    """O caso mais comum: parte medida, parte não. Nem uma coisa nem outra."""
    r = _so([_item("ALVENARIA", "m²", 30.0, "confirmado"),
             _item("ALVENARIA", "m²", 70.0, "estimado")])
    assert r["origem"] == "calculada-parcial", r["origem"]
    assert r["pct_medido"] == 30.0


def test_a_fronteira_dos_80_por_cento():
    """🪤 Fronteira explícita e testada dos DOIS lados — senão ninguém sabe
    onde ela está, e mexer nela vira acidente."""
    quase = _so([_item("ALVENARIA", "m²", 79.0, "confirmado"),
                 _item("ALVENARIA", "m²", 21.0, "estimado")])
    assert quase["origem"] == "calculada-parcial", quase["pct_medido"]
    exato = _so([_item("ALVENARIA", "m²", 80.0, "confirmado"),
                 _item("ALVENARIA", "m²", 20.0, "estimado")])
    assert exato["origem"] == "calculada", exato["pct_medido"]


def test_o_selo_pode_vir_como_ENUM_ou_string():
    """🪤 O motor passa objeto `Confidence`; o banco devolve texto. Ler só um
    dos dois faria metade dos casos cair no ramo errado — e o pior lado do
    erro é chamar estimativa de medição."""
    class _Selo:
        value = "confirmado"

    r = _so([{"discipline": "ALVENARIA", "unit": "m²", "quantity": 50.0,
              "confidence": _Selo()}])
    assert r["origem"] == "calculada", (
        "o selo em forma de Enum não foi reconhecido — a conta acha que nada "
        "foi medido e rebaixa cronograma correto")


def test_selo_AUSENTE_conta_como_nao_medido():
    """Ausência não é medição. Na dúvida, o rótulo mais fraco."""
    r = _so([{"discipline": "ALVENARIA", "unit": "m²", "quantity": 50.0}])
    assert r["origem"] == "estimada", r["origem"]


def test_a_conta_NAO_muda_de_valor_com_o_conserto():
    """🚫 A estimativa continua entrando: o número é o mesmo, só o rótulo
    mudou. Rebaixar o cálculo puniria o cliente por a gente ser honesto."""
    medido = _so([_item("ALVENARIA", "m²", 100.0, "confirmado")])
    estimado = _so([_item("ALVENARIA", "m²", 100.0, "estimado")])
    assert medido["esforco_hh"] == estimado["esforco_hh"]
    assert medido["dias_corridos"] == estimado["dias_corridos"]


# ═══════════════════════════════════════════════════════════════════════════
#  O gerador repassa, e a tela mostra
# ═══════════════════════════════════════════════════════════════════════════

def test_o_gerador_REPASSA_a_origem_do_calculo():
    """Se ele cravar 'calculada' de novo, todo o resto vira enfeite."""
    import io
    src = io.open(os.path.join(_BACKEND, "cronograma.py"), encoding="utf-8").read()
    assert "calc.get('origem')" in src, (
        "o gerador voltou a cravar a origem em vez de repassar a do cálculo")


@pytest.mark.parametrize("origem,chip", [
    ("calculada-parcial", "calculada em parte"),
    ("estimada", "calculada de ESTIMATIVA"),
])
def test_a_TELA_tem_chip_para_cada_origem(origem, chip):
    """🪤 Arquivo certo ≠ tela certa. Sem o chip, a origem nova cai no `: ''`
    final e o cliente deixa de ver QUALQUER rótulo — que é pior que o rótulo
    errado, porque some a pergunta."""
    import io
    html = io.open(os.path.join(_RAIZ, "cronograma.html"), encoding="utf-8").read()
    assert "fase.origem === '%s'" % origem in html, (
        "a tela não trata a origem %r" % origem)
    assert chip in html, "sumiu o texto do chip %r" % chip


def test_a_TELA_nao_pinta_estimativa_de_AZUL():
    """🔑 Azul é o selo de MEDIDO nesta casa. As origens que envolvem
    estimativa têm que sair em âmbar, como o laranja do quantitativo."""
    import io
    html = io.open(os.path.join(_RAIZ, "cronograma.html"), encoding="utf-8").read()
    for origem in ("calculada-parcial", "estimada"):
        i = html.index("fase.origem === '%s'" % origem)
        trecho = html[i:i + 600]
        assert "bg-amber" in trecho, (
            "o chip de %r não é âmbar: %s" % (origem, trecho[:120]))
        assert "bg-indigo" not in trecho, (
            "o chip de %r saiu AZUL — a cor do medido numa conta de estimativa"
            % origem)


def test_a_ressalva_do_caminho_CUSTOM_fala_das_quantidades_laranja():
    """🩸 10 de 10 cronogramas da base usam `fases_custom`, e a ressalva de lá
    era 'Cronograma editado manualmente pelo usuário' — sem uma palavra sobre
    quantidade estimada entrar na conta."""
    import io
    src = io.open(os.path.join(_BACKEND, "cronograma.py"), encoding="utf-8").read()
    i = src.index("'editado_manualmente': True")
    bloco = src[i:i + 2500]
    assert "laranja" in bloco, (
        "a ressalva do caminho custom não diz que quantidade estimada entra na "
        "conta — e é o caminho que 10 de 10 cronogramas usam")
    assert "SINAPI" in bloco, "sumiu a origem do coeficiente"


# ═══════════════════════════════════════════════════════════════════════════
#  🧪 Controle: reproduz o defeito real
# ═══════════════════════════════════════════════════════════════════════════

def test_CONTROLE_o_caso_REAL_de_zero_medido():
    """Reproduz `55796d1e`: 33 itens, 0 medidos. Antes disto ele saía com
    'calculada das quantidades' em chip AZUL."""
    itens = [_item("ALVENARIA", "m²", 12.5, "estimado") for _ in range(33)]
    r = _so(itens)
    assert r["origem"] == "estimada"
    assert r["qtd_medida"] == 0.0
    assert r["qtd_total"] > 0
