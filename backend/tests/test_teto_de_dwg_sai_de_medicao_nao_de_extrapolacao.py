# -*- coding: utf-8 -*-
"""O teto de DWG recusou um arquivo que a gente lê — por causa de extrapolação.

🩸 03/09/2026, FÁBIO SHIRAISHI (job `75dab573`, "BRB Estadio"), primeiro projeto
dele. DWG de 44,5 MB recusado por um teto de 40 MB, com o log dizendo:

    "converter pediria ~2227 MB de RAM e derrubaria o servidor; nem tentei"

Baixei o arquivo dele do nosso Storage e medi as três etapas:

    conversão: pico   836 MB (18,8×) em 27 s     ← o previsto era 2.227 MB
    DXF gerado:       248,3 MB                    ← abaixo do teto interno (250)
    extração:  pico 1.964 MB (7,9× o DXF) em 87 s, exit 0

Cabia folgado nas três. E ele reagiu subindo um **PDF** — o caminho que só
estima. Recusa errada não devolve o cliente pro lugar certo; empurra ele pro
pior caminho disponível.

🔑 POR QUE A PREVISÃO ERRAVA. As quatro medidas que fixaram o teto de 40 MB
eram todas de arquivo PEQUENO (3,1 a 24,6 MB), onde o fator é 43–53×. Parte do
custo da conversão é FIXA, então o fator CAI conforme o arquivo cresce. Medido
nos grandes, no mesmo dia:

    11,7 MB → ~29×   (produção, Render)
    44,5 MB →  18,8×
    53,2 MB →  26×

Extrapolar 53× de um arquivo de 3 MB para um de 44 MB errou por 2,7 vezes — e
o preço foi um cliente novo recusado no primeiro projeto.

🪤 Este teto protege só a CONVERSÃO, que roda no processo do servidor sem trava
nenhuma. A extração tem o próprio juiz: a trava de 2,5 GB do processo filho.
Confundir os dois foi o que produziu três tetos discordando entre si.
"""
from dwg_extractor import _MAX_DWG_BYTES

MB = 1024 * 1024

# Os três casos reais medidos em 03/09/2026: (nome, MB do DWG, fator medido).
_MEDIDOS = [("Rafael (produção)", 11.7, 29.0),
            ("Fábio 75dab573", 44.5, 18.8),
            ("Patrick dbd0d97e", 53.2, 26.0)]

# Quanto o pico da conversão pode chegar sem ameaçar o container de 4 GiB.
# O processo do servidor fica em ~100–230 MB medidos; 2,2 GB deixa ~1,6 GB.
_ORCAMENTO_MB = 2200
# Pior fator plausível nos grandes — pessimista contra os 18,8–29 medidos.
_FATOR_PESSIMISTA = 35


def test_o_arquivo_do_fabio_passa():
    """44,5 MB: convertia com 836 MB de pico e extraía com 1.964 MB."""
    assert 44.5 * MB <= _MAX_DWG_BYTES, (
        "o DWG de 44,5 MB do Fábio voltou a ser recusado — medido, ele cabe "
        "nas três etapas")


def test_CONTROLE_o_teto_ANTIGO_reprovaria_o_arquivo_do_fabio():
    """Sem isto o teste acima poderia estar medindo nada."""
    assert 44.5 * MB > 40 * MB, (
        "o controle está errado: o teto antigo tem que REPROVAR o arquivo do "
        "Fábio, senão o teste de cima não mede a mudança")


def test_o_teto_novo_cabe_no_orcamento_de_memoria():
    """O teto não pode ser um número escolhido por gosto.

    No pior fator plausível pros arquivos grandes, o pico da conversão tem que
    caber no orçamento — senão a gente troca uma recusa errada por uma queda.
    """
    pico_mb = (_MAX_DWG_BYTES / MB) * _FATOR_PESSIMISTA
    assert pico_mb <= _ORCAMENTO_MB, (
        "com o teto em %.0f MB e o fator pessimista de %d×, a conversão pediria "
        "%.0f MB — acima do orçamento de %d MB"
        % (_MAX_DWG_BYTES / MB, _FATOR_PESSIMISTA, pico_mb, _ORCAMENTO_MB))


def test_CONTROLE_um_teto_grande_demais_REPROVA_neste_criterio():
    """O critério acima precisa saber dizer não."""
    absurdo = 150 * MB
    assert (absurdo / MB) * _FATOR_PESSIMISTA > _ORCAMENTO_MB, (
        "o critério de orçamento aceita qualquer teto — ele não protege nada")


def test_nenhum_caso_medido_desmente_o_fator_pessimista():
    """Se um arquivo real medir acima do fator pessimista, o teto está errado.

    🪤 Este é o teste que avisa quando a próxima medição derrubar a conta —
    em vez de a gente descobrir por um cliente recusado, como hoje.
    """
    piores = [(nome, f) for nome, _mb, f in _MEDIDOS if f > _FATOR_PESSIMISTA]
    assert not piores, (
        "medição real acima do fator pessimista, o orçamento precisa ser "
        "refeito: " + ", ".join("%s = %.1f×" % p for p in piores))


def test_o_log_nao_promete_um_numero_que_a_medicao_ja_desmentiu():
    """O log dizia "pediria ~{tam * 50} MB" — 2,7× acima do medido.

    Número inventado dentro de um log é pior que log nenhum: ele vira a
    justificativa de quem for reavaliar o teto depois.
    """
    import io
    import os
    fonte = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()
    assert "_tam_dwg * 50 /" not in fonte, (
        "o log voltou a estimar a RAM da conversão com o fator 50×, que só "
        "vale pra arquivo pequeno")
    assert "_tam_dwg * 30 /" in fonte, (
        "sumiu a estimativa da RAM no log da recusa — ela é o que permite "
        "auditar a decisão depois")
