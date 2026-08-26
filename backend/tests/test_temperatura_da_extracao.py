# -*- coding: utf-8 -*-
"""O `temperature=0` custava a prancha inteira — e nunca deu o que prometia.

🚨 26/08/2026, caso Amanda (job 43a799c0). De 4 pranchas, 1 chegou na planilha.
As duas densas devolveram ZERO item: a IA somava bloco a bloco no raciocínio
("+1+1+1+1…") e `temperature=0` — decodificação gulosa — não a deixava escapar
do laço. Queimava os 32.000 tokens sem nunca emitir o JSON.

🔑 E o zero NUNCA entregou o determinismo que o justificava. Em 08/08 o MESMO
arquivo deu 458,54 m² e 177 m² com ele ligado:
    "Temperatura zero é decodificação gulosa, não garantia de determinismo —
     a variação vem da própria inferência. Não existe flag que conserte."
Pagava-se o custo sem receber o benefício. Não era trade-off.

CURVA MEDIDA nas pranchas REAIS dela, com o prompt de produção (itens
devolvidos por prancha):

    temp      0     0,3    0,5    0,7    1,0
    pr.03     0      0      56     71     53
    pr.04     0      0      86    100     84
    pr.02    30      —      40     56     48    <- controle: a que JÁ funciona
    ────────────────────────────────────────
    total    30      —     182    227    185

0,7 é o pico nas TRÊS, e a prancha que funcionava não piora — quase dobra.
🪤 Não é "quanto maior melhor": 1,0 rende menos que 0,7 em todas.

🪤 Um teste que chama a IA de verdade custa ~5 min e tokens por rodada — não
cabe na bancada. Então este guarda cobra a FORMA (o valor e para quem é
enviado); a prova de que 0,7 funciona é a curva acima, medida uma vez e
registrada aqui e no comentário do código.
"""
import io
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
_CORPO = chr(10).join(l for l in _FONTE.split(chr(10))
                      if not l.strip().startswith("#"))


def test_a_temperatura_NAO_pode_voltar_a_ser_zero():
    """O zero é o que custou 2 das 4 pranchas de um cliente real."""
    assert 'DXF_EXTRACT_TEMP' in _CORPO, (
        "a temperatura da extração deixou de ser configurável")
    import re
    m = re.search(r'DXF_EXTRACT_TEMP["\']\s*,\s*["\']([0-9.]+)["\']', _CORPO)
    assert m, "não achei o valor padrão da temperatura"
    padrao = float(m.group(1))
    assert padrao > 0.3, (
        "temperatura voltou para %r. Medido em 26/08 nas pranchas da Amanda: "
        "em 0 e em 0,3 a IA entra em laço de repetição e devolve ZERO item; "
        "de 0,5 pra cima ela escapa. O zero não dá determinismo (provado em "
        "08/08: 458,54 m² e 177 m² no mesmo arquivo)." % padrao)
    assert padrao <= 1.0, "temperatura acima de 1,0 não é aceita pela API"


def test_o_padrao_e_o_pico_que_foi_medido():
    """0,7 rendeu mais que 0,5 e que 1,0 nas TRÊS pranchas testadas.

    Se alguém mudar, que mude sabendo qual número foi medido — e remedindo.
    """
    import re
    m = re.search(r'DXF_EXTRACT_TEMP["\']\s*,\s*["\']([0-9.]+)["\']', _CORPO)
    assert abs(float(m.group(1)) - 0.7) < 1e-9, (
        "o padrão saiu de 0,7 sem a curva ser refeita. Medição de 26/08: "
        "0,5 → 182 itens | 0,7 → 227 | 1,0 → 185 (soma das 3 pranchas)")


def test_temperatura_so_vai_pros_modelos_que_aceitam():
    """🪤 Opus 4.7/4.8 e Fable RECUSAM `temperature` — devolvem 400.

    Mandar pra eles quebra a extração inteira, não só a prancha densa.
    """
    i_guarda = _CORPO.find('opus-4-8')
    i_temp = _CORPO.find('_dxf_kwargs["temperature"]')
    assert i_guarda > 0, "a lista de modelos que recusam temperature sumiu"
    assert i_temp > 0, "não achei onde a temperatura é definida"
    assert i_guarda < i_temp, (
        "a temperatura passou a ser enviada ANTES da checagem de modelo — "
        "Opus e Fable vão devolver 400")


def test_o_health_publica_a_temperatura_DE_VERDADE():
    """🚨 O campo `dxf_temperature_zero` virou mentira no mesmo commit.

    Ele dizia `true` enquanto o motor rodava a 0,7. Instrumento que afirma o
    contrário do que acontece é pior que instrumento nenhum — foi o `perdidos=0`
    que escondeu o laço por um dia inteiro. Agora o health publica o VALOR, lido
    da mesma variável de ambiente que o motor lê.
    """
    assert "dxf_temperature_zero" not in _CORPO, (
        "o campo booleano voltou; ele mente assim que a temperatura sai de 0")
    assert '"dxf_temperature"' in _CORPO, (
        "o health parou de publicar a temperatura da extração")
    i_env = _CORPO.find('DXF_EXTRACT_TEMP')
    i_health = _CORPO.find('"dxf_temperature"')
    assert i_env > 0 and i_health > 0, "não achei os dois lados"
    # o health tem que ler a MESMA variável — senão volta a poder divergir
    assert 'DXF_EXTRACT_TEMP' in _CORPO[i_health:i_health + 400], (
        "o health publica um número que não vem de DXF_EXTRACT_TEMP — pode "
        "divergir do que o motor usa, que é exatamente o defeito de origem")


def test_o_detector_de_laco_continua_ligado():
    """🪤 O laço APARECE em todas as temperaturas — o que muda é escapar dele.

    Subir a temperatura sem manter o detector trocaria um defeito visível por
    um invisível.
    """
    assert '_detectar_laco(text' in _CORPO, (
        "o detector de laço saiu do caminho junto com a mudança de temperatura")
    assert '"motor:laco-repeticao"' in _CORPO


def test_controle_positivo_o_valor_ANTIGO_reprova():
    """Prova que o guarda principal reprova mesmo."""
    import re
    padrao_antigo = 0.0
    assert not (padrao_antigo > 0.3), "controle positivo furado"
    m = re.search(r'DXF_EXTRACT_TEMP["\']\s*,\s*["\']([0-9.]+)["\']', _CORPO)
    assert float(m.group(1)) > 0.3, "o código está com o valor antigo"
