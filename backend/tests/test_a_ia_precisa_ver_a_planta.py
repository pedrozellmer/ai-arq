# -*- coding: utf-8 -*-
"""Em prancha de ARQUITETURA a IA não via o desenho — só as legendas.

🩸 MEDIDO em 02/09/2026. O `analyzer` manda `sheet.crops[:4]` pra IA. Nos
`CROP_REGIONS` de ARQUITETURA há SEIS recortes, e os quatro primeiros são as
quatro legendas — `planta_esquerda` e `planta_centro` ficavam de fora.

Ninguém escolheu isso: é a ordem em que o dicionário foi escrito. O teto de 4
existe por MEMÓRIA, e acabou decidindo *o que a IA enxerga*.

📏 O TAMANHO: rodei a função de detecção real contra 98 nomes de arquivo do
acervo. **57 (58%) caem em ARQUITETURA** — e não só os que se chamam
"arquitetura": o fallback de tipo NÃO DETECTADO é ARQUITETURA
(main.py, "tipo não detectado, usando PROMPT_ARQUITETURA como genérico"), então
`Folha 01.pdf`, `ccProjeto.pdf` e `prancha 2 -JAILTON....pdf` caem no único
tipo que descarta o desenho.

📏 O EFEITO, medido na prancha real 0326.CGR.14.400.ARQUITETURA (A1, mesmo
prompt, duas rodadas por configuração porque o motor não é determinístico):

    4 legendas (como era)     31 e 34 itens ·  0 e  0 com quantidade
    planta primeiro (agora)   47 e 40 itens · 46 e 39 com quantidade

**Zero itens com quantidade, nas duas rodadas.** O recorte descartado tem nome
e área de cada ambiente, o PÉ-DIREITO de cada um (PD=255cm, PD=340cm...) e as
etiquetas de tipo aplicadas na planta — o elo que liga a legenda ("divisória
tipo 2 = drywall ST 9,5cm") à quantidade. A gente mandava o dicionário e
escondia o texto.

🪤 Mandar TUDO (6 recortes) foi PIOR que trocar duas legendas pela planta:
43 itens contra 47. Não faltava imagem — faltava *a* imagem certa. Por isso o
teto de 4 continua de pé: o conserto é de ORDEM, não de volume, e não custa
memória nem token a mais.

🧪 CONTROLE de que não estraga quem estava bem: FORRO cabe no teto (3 recortes),
então lá a mudança só altera a ordem. Medido: 24→26 itens, 22→26 com
quantidade. Sem regressão.

🔑 O critério da ordem: **o que o texto não recupera vem primeiro.** Legenda é
tabela — com camada de texto no PDF, boa parte dela chega pelo `text_content`.
Desenho não chega por texto de jeito nenhum.
"""
import io
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import analyzer                                   # noqa: E402
from processor import CROP_REGIONS, SheetType     # noqa: E402


def _crops(stem, tipo):
    """Os recortes na ORDEM em que o `render_crops` gera (ordem do dicionário)."""
    return [os.path.join("/tmp", "%s_%s.jpg" % (stem, nome))
            for nome in CROP_REGIONS[tipo]]


def _nomes(caminhos, stem):
    return [os.path.basename(c).replace(stem + "_", "").replace(".jpg", "")
            for c in caminhos]


STEM = "0326.CGR.14.400.ARQUITETURA.02-A1"


# ── O conserto ─────────────────────────────────────────────────────────────
def test_a_planta_entra_nos_4_que_vao_pra_IA():
    """🩸 O que a IA deixou de ver por dois meses."""
    crops = _crops(STEM, SheetType.ARQUITETURA)
    vao = _nomes(analyzer._crops_por_importancia(crops)[:4], STEM)
    assert "planta_esquerda" in vao and "planta_centro" in vao, (
        "a planta continua fora das 4 imagens que a IA recebe — ela lê a "
        "legenda e não vê o desenho: %s" % vao)


def test_CONTROLE_POSITIVO_sem_a_ordenacao_a_planta_FICA_DE_FORA():
    """🧪 O controle que prova que o teste acima guarda alguma coisa. Esta é a
    ordem que o `render_crops` gera — a que estava valendo em produção."""
    crops = _crops(STEM, SheetType.ARQUITETURA)
    vao_sem_conserto = _nomes(crops[:4], STEM)
    assert "planta_esquerda" not in vao_sem_conserto, (
        "o controle não reproduz o comportamento antigo — sem ele, o teste "
        "principal poderia estar passando por outro motivo")
    assert vao_sem_conserto == ["legenda_fechamentos", "legenda_revestimentos",
                                "legenda_portas", "legenda_divisorias"]


def test_a_planta_vem_ANTES_das_legendas():
    crops = _crops(STEM, SheetType.ARQUITETURA)
    ordem = _nomes(analyzer._crops_por_importancia(crops), STEM)
    assert ordem[:2] == ["planta_esquerda", "planta_centro"], ordem


def test_o_teto_de_4_continua_de_pe():
    """🪤 O conserto é de ORDEM, não de volume. Mandar tudo mediu PIOR
    (43 itens contra 47) e custaria memória e token a mais."""
    assert analyzer.MAX_IMGS_POR_PRANCHA == 4, (
        "o teto mudou — se foi de propósito, refaça a medição das 3 "
        "configurações antes, porque 'tudo' já mediu pior que 'planta primeiro'")


# ── O que NÃO pode quebrar ─────────────────────────────────────────────────
def test_CONTROLE_nome_de_ARQUIVO_com_planta_nao_confunde():
    """🪤 Um PDF chamado "Planta 1 - Galpão.pdf" gera
    "Planta 1 - Galpão_legenda_portas.jpg". Procurar "planta" no caminho
    inteiro classificaria a LEGENDA como desenho e o conserto viraria ruído."""
    stem = "Planta 1 - Galpao"
    crops = _crops(stem, SheetType.ARQUITETURA)
    vao = _nomes(analyzer._crops_por_importancia(crops)[:4], stem)
    assert vao[:2] == ["planta_esquerda", "planta_centro"], vao
    assert "legenda_portas" not in vao[:2], (
        "a legenda foi classificada como desenho por causa do nome do arquivo")


def test_CONTROLE_quem_CABE_no_teto_nao_perde_nada():
    """FORRO, PISO e PONTOS têm 3 ou menos recortes: todos continuam indo.
    A ordem muda, o conteúdo não. Medido no forro: 24→26 itens, sem regressão."""
    for tipo in (SheetType.FORRO, SheetType.PISO, SheetType.PONTOS):
        crops = _crops("X", tipo)
        assert len(crops) <= 4
        depois = analyzer._crops_por_importancia(crops)
        assert sorted(depois) == sorted(crops), (
            "%s perdeu ou ganhou recorte na ordenação" % tipo)


def test_a_ordem_dentro_de_cada_grupo_e_ESTAVEL():
    """🪤 `sorted` com chave booleana preserva a ordem original dentro do grupo.
    Sem isso a ordem das legendas viraria loteria e comparar duas rodadas
    deixaria de fazer sentido."""
    crops = _crops(STEM, SheetType.ARQUITETURA)
    ordem = _nomes(analyzer._crops_por_importancia(crops), STEM)
    assert ordem == ["planta_esquerda", "planta_centro",
                     "legenda_fechamentos", "legenda_revestimentos",
                     "legenda_portas", "legenda_divisorias"], ordem


def test_a_lista_de_desenho_sai_do_PROPRIO_CROP_REGIONS():
    """🪤 Recorte novo com "planta"/"layout" no nome entra na regra sozinho.
    Lista fixa no código envelheceria calada — foi assim que os IPs da casa
    quase viraram estatística errada."""
    # 🪤 `corpo_de` acha o FIM REAL da função. Eu tinha escrito
    # `fonte[i:i+1800]` aqui e o guarda `test_nenhum_guarda_novo_recorta_por_
    # tamanho_fixo` reprovou — janela fixa maior que a função lê o vizinho e
    # passa verde por engano; menor, não vê o que diz guardar. Hoje mesmo eu
    # tinha caído nisso numa checagem do `mostrarAvisoAec`.
    from _corpo import corpo_de
    corpo = corpo_de("_crops_por_importancia", "analyzer.py")
    assert "CROP_REGIONS" in corpo, (
        "a lista de nomes de desenho virou fixa — recorte novo não entra sozinho")


def test_o_analyzer_USA_a_ordenacao():
    """Guarda de ponto de chamada — o controle abaixo prova que sabe reprovar."""
    limpo = "\n".join(
        l for l in io.open(os.path.join(_BACKEND, "analyzer.py"),
                           encoding="utf-8").read().splitlines()
        if not l.lstrip().startswith("#"))
    assert "_crops_por_importancia(sheet.crops)[:MAX_IMGS_POR_PRANCHA]" in limpo, (
        "o laço voltou a cortar a lista crua — a planta sai de novo")


def test_CONTROLE_a_checagem_de_chamada_sabe_REPROVAR():
    falso = "    for crop_path in sheet.crops[:MAX_IMGS_POR_PRANCHA]:"
    assert "_crops_por_importancia(sheet.crops)" not in falso
