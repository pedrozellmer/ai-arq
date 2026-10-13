# -*- coding: utf-8 -*-
"""A FAMÍLIA DE ANOTAÇÃO do Revit não é peça — pelo nome, lido pela família.

🩸 13/10/2026 — "Cabeça de grade / grelha de cobertura — fornecimento e
instalação — 20 un", com selo, numa planilha entregue: eram as 20 BOLHAS DE EIXO
("Eixo - M_Cabeça da grade - …"). E "Identificador parede — 205 un", "Tags de
revestimento — 18 un", com selo. O guarda de anotação do extrator é em inglês e
só olha o começo do nome.
📏 Medido pelo motor (114 arquivos de 55 jobs): 1.842 inserções contadas como
peça em 18 jobs, em quatro formas de FAMÍLIA — identificador · a categoria
(corte, elevação, eixo, grid) com tipo · anotacao_ · tag depois de prefixo.
🪤 O lado falso, medido em 24.898 nomes de bloco contados e no banco: "tag"
dentro de palavra é peça (porta, cesta), luminária "SPOT" é peça, e "símbolo",
"chamada" e "seta" nomeiam serviço de verdade (símbolo de acessibilidade,
chamada de enfermeira, seta de fluxo de garagem) — não são forma desta régua.

Todo caso de contagem passa pelo `extract_dxf` (um DXF sintético de verdade).
🪤 Nomes e siglas FICTÍCIOS, com a mesma forma dos medidos (repositório público).
"""
import io
import os
import re
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import dwg_extractor as dx  # noqa: E402

CHAVE = "FAMILIA_DE_ANOTACAO_DO_REVIT"

ANOTACAO = [
    # I — a família começa por "Identificador" / "M_Identificador" (o Tag do Revit em português)
    "Identificador de porta1 - Identificador de porta-2528254-PORTARIA",
    "Identificador de Janela - Completo _ marca de tipo_ altura_ largura-2198330-Térreo",
    "Identificador de parede1 - 12mm-2538960-PORTARIA",
    "Identificador parede - Tipo _ Descrição-323359-05 - Tipo - NO",
    "Identificador de piso 1-75 - Identificador de piso 1-75-1727100-3 PAVIMENTO",
    "Identificador de nota-chave - Número da nota-chave-2275981-TÉRREO",
    "Identificador ambiente XPTO - Identificador de ambiente com área-1764123-A",
    "M_Identificador da porta - M_Identificador da porta-1233-1º Piso",
    "M_Identificador da janela 2 - M_Identificador da janela 2-761570-1º Piso",
    "IDENTIFICADOR", "Identificador_porta", "identificador2",
    # C — a CATEGORIA de anotação como família, com tipo depois de " - "
    "Corte - M_Cabeça do corte - Preenchida-1049-COBERTURA",
    "Corte - Cabeça do corte - Preenchido-381576-02 - SUPERIOR",
    "Corte - Extremidade superior do corte - Preenchido-531658-TORRE",    # sem "cabeça" no tipo
    "Corte - _LEGENDA DE CORTE-376670-FORRO", "Corte - CORTE-467403-TIPO-001",
    "Corte - LR - Section Head - Filled-2723877-Nível Terreno",
    "Eixo - M_Cabeça da grade - Círculo 2-1358373-COBERTURA",
    "Eixo - M_Cabeça da grade - EIXO Círculo-377171-02 - SUPERIOR",
    "Elevação - Número de detalhe 2-2330074-COBERTURA", "Elevação - Seta preenchida-1468441-02 - SUPERIOR",
    "Elevação - Interna-Horizontal-1920509-PLANTA CIVIL",
    "Grid - Extremidade superior da grelha - Círculo-388906-TÉRREO", "Grid - PE-362919-PLANTA TÉRREO",
    "CORTE - A", "Eixo - 1",                                             # sem id do Revit: a família e o tipo bastam
    # A — a família começa por "Anotacao_"
    "Anotacao_Coluna - Coluna-1332778-TÉRREO - PLANTA", "Anotacao_Coluna - Coluna que Desce-1914123-Legenda",
    "Anotacao_Tubo - Diâmetro _ Sentido Acima-1915696-2_ Pavimento", "Anotação_Tubo - Sentido Abaixo-11623705-A",
    "Anotações-Gerais - Seta-123456-Térreo",
    # T — "TAG" como palavra, depois de um prefixo de padrão
    "XPTO-TAG-REVESTIMENTOS - XPTO-TAG-CIRCULO-1736611-COBERTURA", "XPTO-TAG-PORTA - XPTO-TAG-PORTA-1842839-PLANTA",
    "ZZ_TAG_DOOR - ZZ_TAG_DOOR-409952-PLANTA TÉRREO", "ZZ_TAG_Room_Material - 2_0 P-10782143-PLANTA TÉRREO",
    "YY-TAG-AREA-Nome_Comentário-Área - Nome-1558212-Térreo", "QQ TAG 01",
]

PECA = [
    # "tag" DENTRO de palavra: porta e cesta (medidos); no fim e no começo de uma palavra maior
    "XX_ESQ_PortaGiroAcessivel_P - P06 90x210cm-4411223-Térreo", "CESTAGOL", "Montagem - Suporte-123456-Térreo",
    "ESTAG - Estrutura-112233-Térreo", "ZZ_Taguatinga - Banco-112233-Praça",
    # "tag" só na VISTA, num nome sem tipo: a família acaba no "-<id>-"
    "Porta de abrir-1842839-ZZ-TAG - Térreo",
    # a categoria SEM tipo, ou em outra palavra: bloco de CAD comum
    "Corte", "CORTE", "Eixo", "eixo", "Elevação", "Grid", "Corte - ", "Eixos do pilar", "Corte AA", "Cortes 9T",
    "Eixo-1", "CORTE1S", "Elevacao_01",
    # a categoria só na VISTA do Revit: a peça vista num corte, numa elevação
    "Montante retangular - 3x5-2518207-Corte AA", "Guarda-corpo - Vidro-683686-Elevação Frontal",
    "Pilar estrutural - 15x40-2654842-Eixo 3", "Porta - Corte Fogo 80x210-1234567-Térreo",
    # as três palavras que o banco mostrou serem PEÇA em planilha de cliente
    "Símbolo Internacional Acessível 26", "simbolo acessibilidade", "CHAMADA DE ENFERMEIRA TOALETE",
    "Seta de fluxo - Seta de fluxo-366160-TÉRREO", "XX_Seta fluxo veículos - Sentido duplo-998877-Garagem",
    "Simbolo Janelas - Simbolo Janelas-2298104-Elevação Frontal",        # medido como dano; fica fora desta régua
    # luminária
    "SPOT-01 - SPOT-01-1570321-PLANTA DO FORRO", "SPOT DE EMBUTIR - PISO", "l-spot",
    # "identificador" e "anotação" em outra posição, e o que a régua não promete
    "Placa identificadora - 20x30-556677-Térreo", "Porta com identificador - 80-112233-Térreo", "Identificadores",
    "Caixa de anotação", "Anotacao", "anotacaox - y", "Painel anotacao_obra - 60x90-445566-Térreo",
    "PORTA 80", "", None,
]


@pytest.fixture(autouse=True)
def _chave(monkeypatch):
    monkeypatch.delenv(CHAVE, raising=False)


@pytest.mark.parametrize("nome", ANOTACAO)
def test_o_nome_e_de_familia_de_anotacao(nome):
    assert dx.nome_de_anotacao_do_revit(nome) is True, nome


@pytest.mark.parametrize("nome", PECA)
def test_CONTROLE_o_nome_nao_e_de_familia_de_anotacao(nome):
    assert dx.nome_de_anotacao_do_revit(nome) is False, nome


def test_a_regua_olha_a_familia_nao_o_tipo_nem_a_vista():
    """A mesma palavra em três lugares do nome do Revit: só na FAMÍLIA ela decide."""
    assert dx.nome_de_anotacao_do_revit("Corte - Cabeça do corte-381576-Térreo")
    assert not dx.nome_de_anotacao_do_revit("Painel - Corte-381576-Térreo"), "no tipo"
    assert not dx.nome_de_anotacao_do_revit("Painel - Vidro-381576-Corte AA"), "na vista"
    assert dx.nome_de_anotacao_do_revit("Identificador de porta - Simples-381576-Térreo")
    assert not dx.nome_de_anotacao_do_revit("Porta - Identificador de porta-381576-Térreo"), "no tipo"
    assert not dx.nome_de_anotacao_do_revit("Porta - Simples-381576-Identificador"), "na vista"
    assert dx.nome_de_anotacao_do_revit("XPTO-TAG-PORTA - Simples-381576-Térreo")
    assert not dx.nome_de_anotacao_do_revit("Porta - XPTO-TAG-381576-Térreo"), "no tipo"
    # o id pode vir como "V<n>" (cópia de vista): corta do mesmo jeito
    assert dx.nome_de_anotacao_do_revit("Eixo - M_Cabeça da grade-V51-Corte 3D")
    assert not dx.nome_de_anotacao_do_revit("Montante - 3x3-V255-Eixo - A")


def test_a_categoria_pede_tipo_e_o_acento_nao_importa():
    assert dx.nome_de_anotacao_do_revit("ELEVAÇÃO - Vista-9479271-GARAGEM")
    assert dx.nome_de_anotacao_do_revit("Elevacao - Vista-9479271-GARAGEM")
    assert not dx.nome_de_anotacao_do_revit("Elevação")
    assert not dx.nome_de_anotacao_do_revit("Elevação -  ")
    assert not dx.nome_de_anotacao_do_revit("Corte - -381576-Térreo"), "o tipo vazio antes do id não é tipo"
    assert not dx.nome_de_anotacao_do_revit("Elevação de ponto - Corte-870094-Corte"), "essa é da régua do nível"
    assert dx.nome_de_simbolo_de_nivel("Elevação de ponto - Corte-870094-Corte")


def test_a_primeira_palavra_TAG_e_do_guarda_antigo_nao_desta_regua():
    """ "tag - PORTAS" já saía pelo guarda em inglês; esta régua pega a TAG depois
    de um prefixo. As duas juntas tiram as duas formas."""
    assert not dx.nome_de_anotacao_do_revit("tag - PORTAS - SIMPLES-4325128-RESERVATÓRIO")
    assert dx.nome_de_anotacao_do_revit("XPTO-TAG - PORTAS-4325128-RESERVATÓRIO")


# ── do DXF à contagem ────────────────────────────────────────────────────────

_BLOCOS = [("Eixo - M_Cabeça da grade - Círculo 2-1358373-COBERTURA", 5),
           ("Corte - M_Cabeça do corte - Preenchida-1049-COBERTURA", 2),
           ("Identificador de porta1 - Identificador de porta-2528254-PORTARIA", 4),
           ("Anotacao_Coluna - Coluna-1332778-TÉRREO - PLANTA", 3),
           ("XPTO-TAG-PORTA - XPTO-TAG-PORTA-1842839-PLANTA", 2),
           ("TAG-porta", 2),                                           # este o guarda antigo já tirava
           ("PORTA 80", 3), ("Montante retangular - 3x5-2518207-Corte AA", 4), ("CESTAGOL", 2),
           ("Símbolo Internacional Acessível 26", 1)]
_ANOT = _BLOCOS[:5]
_PECAS = dict(_BLOCOS[6:])


def _dxf(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (40, 0), (40, 30), (0, 30)], close=True, dxfattribs={"layer": "ARQ-PAREDE"})
    for k, (nome, n) in enumerate(_BLOCOS):
        b = doc.blocks.new(name=nome)
        b.add_circle((0, 0), 0.15)
        b.add_line((-0.3, 0), (0.3, 0))
        b.add_line((0, -0.3), (0, 0.3))
        b.add_lwpolyline([(0, 0), (0.2, 0.2), (0.4, 0)])
        for i in range(n):
            msp.add_blockref(nome, (2 + 3 * i, 2 + 2 * k), dxfattribs={"layer": "ARQ-SIMB"})
    p = str(tmp_path / "anotacao.dxf")
    doc.saveas(p)
    return p


def _contagem(ex):
    return {b.name: b.count for b in ex.blocks}


def _linhas_de_bloco(ex):
    """As linhas "<nome>: N un" do prompt (o prompt escreve o bloco do Revit pela
    FAMÍLIA: "Eixo: 5 un" — é assim que a bolha de eixo chegava à IA)."""
    return {l.strip().split(" un")[0] for l in ex.to_structured_prompt().splitlines() if " un" in l}


#: como o prompt escreve os cinco blocos de anotação do desenho do teste
_NO_PROMPT = {"Eixo: 5", "Corte: 2", "Anotacao_Coluna: 3",
              "Identificador de porta1 - Identificador de porta-2528254-PORTARIA: 4",
              "XPTO-TAG-PORTA - XPTO-TAG-PORTA-1842839-PLANTA: 2"}


def test_a_familia_de_anotacao_sai_da_contagem_e_a_peca_fica(tmp_path):
    ex = dx.extract_dxf(_dxf(tmp_path))
    assert _contagem(ex) == _PECAS
    assert ex.blocos_descartados["anotacao"] == sum(n for _nm, n in _ANOT) + 2      # o descarte é CONTADO
    linhas = _linhas_de_bloco(ex)
    assert not (linhas & _NO_PROMPT), "nenhuma das cinco chega ao prompt"
    assert {"PORTA 80: 3", "Montante retangular: 4", "CESTAGOL: 2", "Símbolo Internacional Acessível 26: 1"} <= linhas


def test_CONTROLE_com_a_chave_em_zero_e_como_hoje(tmp_path, monkeypatch):
    monkeypatch.setenv(CHAVE, "0")
    ex = dx.extract_dxf(_dxf(tmp_path))
    assert _contagem(ex) == {n: k for n, k in _BLOCOS if n != "TAG-porta"}     # só o que o guarda antigo já tirava
    assert ex.blocos_descartados["anotacao"] == 2
    assert _NO_PROMPT <= _linhas_de_bloco(ex), "sem a régua as cinco vão ao prompt como peça"


def test_o_que_nao_e_anotacao_nao_muda_com_a_chave(tmp_path, monkeypatch):
    com = dx.extract_dxf(_dxf(tmp_path))
    monkeypatch.setenv(CHAVE, "0")
    sem = dx.extract_dxf(_dxf(tmp_path))
    c_com, c_sem = _contagem(com), _contagem(sem)
    assert all(c_sem[n] == k for n, k in c_com.items())
    assert set(c_sem) - set(c_com) == {n for n, _k in _ANOT}
    assert len(com.walls) == len(sem.walls) and len(com.texts) == len(sem.texts)


def test_a_chave_do_nivel_nao_liga_nem_desliga_esta(tmp_path, monkeypatch):
    """Duas réguas, duas chaves: desligar a do nível não devolve a anotação."""
    monkeypatch.setenv("SIMBOLO_DE_NIVEL_E_ANOTACAO", "0")
    assert _contagem(dx.extract_dxf(_dxf(tmp_path))) == _PECAS


def test_a_chave_e_lida_no_extrator_e_e_avaliavel():
    fonte = io.open(os.path.join(_BACKEND, "dwg_extractor.py"), encoding="utf-8").read()
    assert fonte.count('os.environ.get("%s"' % CHAVE) == 1
    main = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    bloco = re.search(r"_CHAVES_AVALIAVEIS = frozenset\(\{(.*?)\}\)", main, re.S).group(1)
    assert '"%s"' % CHAVE in bloco
