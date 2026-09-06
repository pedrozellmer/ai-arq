# -*- coding: utf-8 -*-
"""O conversor renomeia bloco por instância — juntar sim, mas só o que é IGUAL.

🚨 26/08/2026, caso cliente-16 (job 43a799c0, "Harmonia - 9º Pavimentos").
De 4 pranchas, 1 chegou na planilha. As duas densas devolveram ZERO item com
`stop=max_tokens`, e o log ainda dizia `perdidos=0`.

O que o acervo mostrou (4 leituras, correlação perfeita com CONTAGEM DE BLOCOS
e NENHUMA com tamanho de arquivo):

    Andre     78 MB DXF ·     0 blocos → entrada 13.499 tokens → 64 itens ✔
    Amanda02  27 MB     ·    27 blocos → entrada 15.804        → 25 itens ✔
    Amanda03  45 MB     ·   763 blocos → entrada 53.832        →  0 itens ✖
    Amanda04  53 MB     · 1.570 blocos → entrada 74.875        →  0 itens ✖

O arquivo do Andre é o MAIOR dos quatro e gerou o MENOR prompt: parede entra
somada por layer, bloco entra UMA LINHA POR NOME. E o libredwg — que faz 88%
das conversões — dá um nome por instância. Num DXF real: 1.202 nomes para
1.349 peças, e a seção virou 44% do prompt.

Efeito colateral que o cliente via: "Viga_1_1: 1 un" repetido 209 vezes, em vez
de "Viga: 209 un". A contagem certa estava lá e saía pulverizada.

🪤 O QUE QUASE DEU ERRADO. A primeira versão agrupava só pelo NOME-RAIZ. Um
controle geométrico mostrou que `Parede_1_1` e `Parede_2_1` tinham SEIS
definições diferentes na amostra — são trechos distintos de parede. Somar
aquilo seria repetir o bug da bitola, em que Ø8 e Ø16 viraram um número só e
18.168 kg desabaram para 508 kg. Por isso só junta quando a ASSINATURA da
definição (tipos de entidade e quantos de cada) é idêntica.

Este guarda RODA a extração num DXF construído aqui, com os três casos de
propósito. Ler o fonte não serviria: o que importa é o texto que sai.
"""
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

ezdxf = pytest.importorskip("ezdxf")

from dwg_extractor import extract_from_file   # noqa: E402


def _linha(bloco, comprimento):
    bloco.add_line((0, 0), (comprimento, 0))


@pytest.fixture
def dxf_com_blocos_renomeados(tmp_path):
    """Três situações no mesmo arquivo:

    1. `Viga_1_1` .. `Viga_4_1`  — definições IDÊNTICAS (2 LINE cada).
       É a mesma peça que o conversor renomeou → tem que virar "Viga: 4 un".
    2. `Parede_1_1` e `Parede_2_1` — definições DIFERENTES (1 LINE × 3 LINE).
       São peças distintas → NÃO podem ser somadas.
    3. `Pilar` — nome sem sufixo, sozinho → segue como está.
    """
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    for i in range(1, 5):                      # mesma definição
        b = doc.blocks.new(name="Viga_%d_1" % i)
        _linha(b, 3.0)
        _linha(b, 1.0)
        msp.add_blockref("Viga_%d_1" % i, (i * 10, 0), dxfattribs={"layer": "ESTRUTURA"})

    p1 = doc.blocks.new(name="Parede_1_1")     # 1 LINE
    _linha(p1, 5.0)
    msp.add_blockref("Parede_1_1", (0, 50), dxfattribs={"layer": "ARQ"})

    p2 = doc.blocks.new(name="Parede_2_1")     # 3 LINE  → OUTRA peça
    for c in (5.0, 2.0, 2.0):
        _linha(p2, c)
    msp.add_blockref("Parede_2_1", (20, 50), dxfattribs={"layer": "ARQ"})

    pil = doc.blocks.new(name="Pilar")
    _linha(pil, 0.4)
    msp.add_blockref("Pilar", (0, 90), dxfattribs={"layer": "ESTRUTURA"})

    caminho = str(tmp_path / "renomeado.dxf")
    doc.saveas(caminho)
    return caminho


def _secao_blocos(texto):
    if "CONTAGEM DE BLOCOS" not in texto:
        return ""
    i = texto.index("CONTAGEM DE BLOCOS")
    resto = texto[i:]
    fim = resto.find("\n\n")
    return resto[:fim] if fim > 0 else resto


def test_mesma_peca_renomeada_vira_UMA_linha_com_a_soma(dxf_com_blocos_renomeados):
    texto = extract_from_file(dxf_com_blocos_renomeados).to_structured_prompt()
    secao = _secao_blocos(texto)
    assert secao, "não saiu seção de blocos"
    assert "Viga" in secao, secao
    assert "4 un" in secao, (
        "as 4 vigas idênticas tinham que virar 'Viga: 4 un'. Saiu:\n%s" % secao)
    # e não podem continuar aparecendo como nomes soltos
    assert "Viga_1_1" not in secao and "Viga_3_1" not in secao, (
        "sobrou nome fragmentado do conversor:\n%s" % secao)


def test_pecas_DIFERENTES_com_o_mesmo_nome_NAO_sao_somadas(dxf_com_blocos_renomeados):
    """O controle que impede repetir o bug da bitola.

    `Parede_1_1` (1 LINE) e `Parede_2_1` (3 LINE) são peças distintas. Se
    virarem "Parede: 2 un", o agrupamento está somando coisa diferente.
    """
    texto = extract_from_file(dxf_com_blocos_renomeados).to_structured_prompt()
    secao = _secao_blocos(texto)
    linhas_parede = [l for l in secao.splitlines() if "Parede" in l]
    assert len(linhas_parede) == 2, (
        "as duas paredes têm geometria DIFERENTE e viraram %d linha(s) — "
        "isso é o bug da bitola de volta:\n%s" % (len(linhas_parede), secao))
    for l in linhas_parede:
        assert ": 1 un" in l, "parede distinta saiu somada: %s" % l


def test_bloco_sem_homonimo_continua_igual(dxf_com_blocos_renomeados):
    """Controle negativo: o conserto não pode mexer em quem não tem duplicata."""
    texto = extract_from_file(dxf_com_blocos_renomeados).to_structured_prompt()
    secao = _secao_blocos(texto)
    assert any(l.strip().startswith("Pilar: 1 un") for l in secao.splitlines()), (
        "o 'Pilar' sozinho foi alterado sem necessidade:\n%s" % secao)


def test_homonimos_ganham_discriminador_pro_cliente(dxf_com_blocos_renomeados):
    """Duas linhas "Parede" iguais na planilha são indistinguíveis pra quem lê."""
    texto = extract_from_file(dxf_com_blocos_renomeados).to_structured_prompt()
    secao = _secao_blocos(texto)
    linhas = [l for l in secao.splitlines() if "Parede" in l]
    assert all("tipo" in l for l in linhas), (
        "peças diferentes com o mesmo nome precisam de 'tipo N' pra o cliente "
        "conseguir separar:\n%s" % secao)


def test_a_secao_ENCOLHE_de_verdade(dxf_com_blocos_renomeados):
    """O motivo de existir: o prompt tem que ficar menor.

    Sem isso, o conserto pode estar 'certo' e não resolver o problema que a
    cliente-16 teve — que foi a seção inflar até a leitura devolver zero.
    """
    ext = extract_from_file(dxf_com_blocos_renomeados)
    secao = _secao_blocos(ext.to_structured_prompt())
    # como seria SEM agrupar: uma linha por nome
    nomes = {b.name for b in ext.blocks}
    sem_agrupar = sum(len("  %s: %d un" % (n, 1)) + 1 for n in nomes)
    assert len(secao) < sem_agrupar + 200, (
        "a seção não encolheu: %d chars contra ~%d sem agrupar"
        % (len(secao), sem_agrupar))


def test_sem_assinatura_NAO_agrupa_nada(dxf_com_blocos_renomeados, monkeypatch):
    """Falha fechada: sem conseguir ler a definição, mantém o comportamento antigo.

    🪤 Agrupar por nome quando não dá pra comparar geometria é justamente o
    caminho que somaria peça diferente. Na dúvida, não junta.
    """
    import dwg_extractor as dx
    ext = extract_from_file(dxf_com_blocos_renomeados)
    for b in ext.blocks:
        b.assinatura = ""          # simula definição ilegível
    secao = _secao_blocos(ext.to_structured_prompt())
    assert "Viga_1_1" in secao and "Viga_2_1" in secao, (
        "sem assinatura o código agrupou assim mesmo — é aí que mora o risco "
        "de somar peça diferente:\n%s" % secao)
    assert dx is not None
