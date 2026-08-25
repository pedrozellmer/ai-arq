# -*- coding: utf-8 -*-
"""Marca, código e cor saem de dentro do texto e vão pra campo próprio.

Pedro, 24/08/2026, desenhando o Caderno de acabamentos: *"ele revisa a qtd em
quantitativos, e depois no caderno vai especificando a marca, modelo, o sku,
justamente pra mandar pra orçar (...) quando tiver o sku no projeto a gente
sugere"*.

O ponto de partida é que **já está escrito**: o prompt do motor manda extrair
"fabricante + referência + cor" (analyzer.py:57) e depois cola tudo num campo
de texto único. 304 itens do acervo citam marca; 226 trazem código.

🚨 A ARMADILHA, vista em dado real ANTES de eu escrever a primeira linha: nem
todo "cód."/"ref."/"modelo" é código de fabricante. Do banco:

    "Janela JA04 — ... (código JA04)"             ← tag do quadro de esquadrias
    "Cadeira — ref. bloco 'CADEIRA 19'"           ← nome de bloco do CAD
    "Detalhe de porta (ref. 1008831)"             ← referência de detalhe
    "Estaca tipo EST60" / "Armadura CA-50"        ← nomenclatura de projeto

Regex ingênuo encheria o caderno de lixo — e lixo com cara de especificação é
pior que campo vazio, porque o cliente manda pro fornecedor.

**A regra: código só é de fabricante se houver FABRICANTE por perto.** Falha
fechada — sem marca, não se afirma nada.

🪤 Três defeitos que só apareceram ao rodar contra descrição REAL do acervo, e
que a minha bateria inventada não teria pego:
  1. "pintura cor coral" virava marca=Coral (Coral é tinta E é cor);
  2. "2315.C.060" não era achado — eu exigia 2+ caracteres no segmento do meio,
     e ali tem um "C" sozinho (barra de apoio Deca, item real);
  3. "cor branca" não era achada — eu exigia maiúscula.
"""
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from spec_extract import extrair_spec, spec_origem


# ══════════════════════════════════════════════════════════════════════════
#  Especificação de VERDADE — tudo veio do banco de produção
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("desc,marca,codigo", [
    ("Papeleira cromada Quadratta — Deca, Cód. 2020.CB3 — 1 unidade",
     "Deca", "2020.CB3"),
    ("Torneira com alavanca e fechamento automático Dematic Eco Conforto "
     "cod. 1173.C.CONF Deca — lavatório PCD", "Deca", "1173.C.CONF"),
    ("Deca Barra de Apoio Articulada Conforto - Aço Inox 2315.C.060 60 cm",
     "Deca", "2315.C.060"),
    ("Fornecimento e instalação de unidade condensadora Carrier modelo 38KCX22",
     "Carrier", "38KCX22"),
    ("Geladeira Brastemp Frost Free French Door Inox — Ref. BRH85MK",
     "Brastemp", "BRH85MK"),
    ("Curva de alumínio ref. TEL-779 para SPDA — fabricante Termotécnica",
     "Termotécnica", "TEL-779"),
    ("Lixeira Artplan modelo 5000, dimensões 38x38x50cm", "Artplan", "5000"),
])
def test_acha_a_especificacao_real(desc, marca, codigo):
    r = extrair_spec(desc)
    assert r["marca"] == marca, r
    assert r["codigo"] == codigo, r


def test_pega_fabricante_fora_da_lista_quando_o_texto_DIZ_que_e_fabricante():
    """A lista de marcas nunca vai ser completa. Quando o autor escreve
    'fabricante X' ou 'marca X', ele mesmo rotulou — isso vale mais que a lista."""
    r = extrair_spec("Torre de resfriamento marca: Alpina modelo AT-300")
    assert r["marca"] == "Alpina"
    assert r["codigo"] == "AT-300"


# ══════════════════════════════════════════════════════════════════════════
#  🚨 O que NÃO pode ser confundido com especificação
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("desc", [
    "Janela JA04 — esquadria conforme quadro de esquadrias do projeto (código JA04)",
    "Cadeira para refeitório — ref. bloco 'CADEIRA 19 - PLANTA BAIXA'",
    "Detalhe de porta em sistema drywall (ref. 1008831)",
    "Piso tátil de alerta — bloco de referência PODOTÁTIL ALERTA — NBR 9050",
    "Estaca tipo EST60 (Ø≈60cm ou similar) — fundação profunda",
    "QDFL-VEST — Quadro de Distribuição de Força e Luz dos Vestiários",
    "Armadura CA-50 Ø8,0 mm — vigas V49 a V68, pavimento térreo",
    "Visita técnica padrão AW 45x45 - tampa de inspeção",
    "Alvenaria em bloco cerâmico, chapisco e emboço",
    "Rodapé 3m de altura instalado",
    "Poste de energia elétrica (EDP) — fornecimento e instalação",
])
def test_nao_inventa_especificacao_onde_nao_ha(desc):
    """🚨 Sem marca, nada é afirmado — nem que o 'código' que está ali seja de
    fabricante. Todos estes vieram do acervo e todos PARECEM ter código."""
    r = extrair_spec(desc)
    assert r["marca"] is None, r
    assert r["codigo"] is None, r


def test_codigo_SEM_marca_nunca_e_afirmado():
    """A regra que separa SKU de tag do projeto, isolada."""
    assert extrair_spec("Peça cód. 9988.AB1 conforme prancha")["codigo"] is None


def test_cor_a_definir_nao_e_cor():
    for d in ("Pintura cor a definir conforme memorial",
              "Pintura cor da legenda do projeto"):
        assert extrair_spec(d)["cor"] is None, d


# ══════════════════════════════════════════════════════════════════════════
#  🪤 Os três defeitos que só o dado real revelou
# ══════════════════════════════════════════════════════════════════════════
def test_coral_como_COR_nao_vira_marca():
    """Coral é fabricante de tinta E é nome de cor. 'pintura cor coral' é cor."""
    r = extrair_spec("Pintura acrílica cor coral sobre massa corrida")
    assert r["marca"] is None, "confundiu a cor coral com a marca Coral"
    assert r["cor"] == "coral"


def test_coral_como_MARCA_continua_funcionando():
    """Controle do teste acima: não pode ter matado o caso legítimo."""
    r = extrair_spec("Pintura cor Branco Coral Fosco — Coral — em parede")
    assert r["marca"] == "Coral"


def test_codigo_com_segmento_de_um_caractere():
    """'2315.C.060' — o 'C' sozinho no meio. Exigir 2+ perdia um item real."""
    assert extrair_spec("Deca Barra de Apoio 2315.C.060")["codigo"] == "2315.C.060"


def test_cor_em_minuscula():
    """'cor branca' vale tanto quanto 'cor Branco Neve'."""
    assert extrair_spec("Revestimento — Eliane, cor branca")["cor"] == "branca"


def test_a_cor_para_onde_a_marca_comeca():
    """🪤 'cor Branco Neve Suvinil' — sem corte, o fabricante virava parte da cor."""
    r = extrair_spec("Pintura tinta acrílica cor Branco Neve Suvinil, 3 demãos")
    assert r["marca"] == "Suvinil"
    assert r["cor"] == "Branco Neve", r


def test_a_cor_para_na_preposicao():
    """Sem isto, 'cor coral sobre massa corrida' saía inteiro como nome da cor."""
    assert extrair_spec("Pintura cor coral sobre massa corrida")["cor"] == "coral"


def test_dimensao_nao_e_codigo():
    r = extrair_spec("Janela de alumínio Sasazaki 52,5x42,5cm")
    assert r["codigo"] != "52,5x42,5"


# ══════════════════════════════════════════════════════════════════════════
#  Procedência: a mesma disciplina do medido/estimado
# ══════════════════════════════════════════════════════════════════════════
def test_quem_tem_spec_e_marcado_como_LIDO():
    """🚨 Quem lê a planilha precisa saber se aquilo o arquiteto escreveu ou se
    alguém sugeriu. Hoje só existe 'lido'; quando entrar sugestão por catálogo,
    ela NÃO pode se passar por isto."""
    assert spec_origem(extrair_spec("Carrier modelo 38KCX22")) == "lido"
    assert spec_origem(extrair_spec("Alvenaria em bloco cerâmico")) == ""


def test_descricao_vazia_nao_quebra():
    for v in (None, "", "   "):
        assert extrair_spec(v) == {"marca": None, "codigo": None, "cor": None}


def test_nao_consulta_catalogo_nem_precifica():
    """🚫 Regras duras nº2 e nº5: isto só lê o texto do próprio projeto. Nada de
    rede, nada de outro cliente, nada de preço."""
    import io
    src = io.open(os.path.join(_BACKEND, "spec_extract.py"), encoding="utf-8").read()
    for proibido in ("requests", "urllib", "http", "preco", "preço", "price", "R$"):
        assert proibido not in src.replace("# ", "").split('"""')[-1], (
            "spec_extract passou a fazer %s — ele só pode LER o texto" % proibido)
