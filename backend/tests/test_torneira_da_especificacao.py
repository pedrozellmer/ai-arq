# -*- coding: utf-8 -*-
"""Enquanto o extrator erra 35%, a especificação NÃO chega no cliente.

🚨 25/08/2026. A auditoria rodou `extrair_spec` sobre as 338 descrições reais
do acervo. Dos **361 itens** que ele marcaria, **127 (35%)** levam marca,
código ou cor que o arquiteto **não escreveu pra aquele item**:

    72 — "Knauf/Placo ou similar", "Deca ou equivalente": sai UMA marca, como
         se fosse decisão tomada. O projeto abriu concorrência de propósito.
    30 — rejunte/argamassa/massa/perfil herdam a marca do acabamento que só
         servem: "Rejunte para porcelanato … Biancogres" (a Biancogres não
         fabrica rejunte).
    17 — norma e bitola viram SKU: "Montal · NBR-5419", "Tigre · DN40".
    13 — cor cortada: "cor CINZA DE GRIFE" sai "CINZA".

🪤 E o mais urgente não era o botão do admin: o carimbo JÁ estava ligado no
fluxo de projeto novo (`_carimbar_spec` no processamento, coluna ESPECIFICAÇÃO
na planilha que o cliente baixa). O próximo upload sairia com os 35% de erro
sem ninguém clicar em nada. Só não pegou ninguém porque nenhum projeto novo
subiu desde ontem.

🔑 Campo vazio é honesto. Campo com cara de especificação e conteúdo errado
vira pedido de orçamento errado — o caderno existe pra ser MANDADO pro
fornecedor. Regra dura nº1 aplicada à especificação: na dúvida, não afirmar.

Este guarda existe pra a trava não ser religada por engano: quando alguém
puser `LIBERADO_PRO_CLIENTE = True`, o teste de baixo exige que a medição do
erro esteja zerada junto.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _corpo import so_o_que_roda  # noqa: E402

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import spec_extract  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
#  A trava existe e é consultada nos DOIS caminhos que chegam no cliente
# ══════════════════════════════════════════════════════════════════════════
def test_a_trava_existe():
    assert hasattr(spec_extract, "LIBERADO_PRO_CLIENTE"), (
        "sumiu a trava que segura a especificação errada longe do cliente")


def test_o_carimbo_do_projeto_novo_consulta_a_trava():
    """Este é o caminho do OBJETO — de onde a planilha do cliente lê."""
    corpo = so_o_que_roda("_carimbar_spec")
    assert "LIBERADO_PRO_CLIENTE" in corpo, (
        "`_carimbar_spec` voltou a carimbar sem consultar a trava — a coluna "
        "ESPECIFICAÇÃO da planilha volta a sair com 35% de erro")


def test_a_gravacao_no_banco_consulta_a_trava():
    """🪤 Não adianta esconder a coluna da planilha e gravar o erro no banco:
    a tela de revisão lê dali, e apagar depois é trabalho na mão."""
    corpo = so_o_que_roda("_spec_campos")
    assert "LIBERADO_PRO_CLIENTE" in corpo, (
        "`_spec_campos` voltou a gravar especificação no banco sem a trava")


def test_com_a_trava_fechada_o_carimbo_nao_poe_nada():
    """Executa `_carimbar_spec` de verdade, com a trava como está hoje."""
    corpo = so_o_que_roda("_carimbar_spec")
    ns = {"print": lambda *a, **k: None}
    exec("def _carimbar_spec(itens) -> int:\n" + corpo.split("\n", 1)[1], ns)

    class _It:
        description = "Rejunte para porcelanato Oregon Gray Satin Biancogres"
        marca = codigo_fabricante = cor = spec_origem = ""

    it = _It()
    n = ns["_carimbar_spec"]([it])
    if spec_extract.LIBERADO_PRO_CLIENTE:
        return                      # liberado: quem manda é o teste de baixo
    assert n == 0, "a trava está fechada e mesmo assim carimbou %d item(ns)" % n
    assert it.marca == "", "gravou marca %r com a trava fechada" % it.marca


# ══════════════════════════════════════════════════════════════════════════
#  🚨 Religar a trava exige ter consertado os 4 defeitos medidos
# ══════════════════════════════════════════════════════════════════════════
#  Cada linha é um caso REAL do acervo, com o que a auditoria mediu saindo
#  errado. São o critério de aceite: enquanto qualquer um destes falhar, a
#  especificação não pode chegar no cliente.
CASOS = [
    # (descrição, campo, o que NÃO pode sair)
    ("Perfil de guia (U) e montante (C) em aço galvanizado — Knauf, Placo ou "
     "similar aprovado pela fiscalização", "marca", "Knauf"),
    ("Split hi-wall 12000 BTUs — Carrier ou similar", "marca", "Carrier"),
    ("Rodapé em poliestireno 10cm — Tarkett ou Santa Luzia ou Interfloor ou "
     "Architech", "marca", "Tarkett"),
    ("Rejunte para porcelanato Oregon Gray Satin 90x90cm Biancogres — cor a "
     "definir compatível com o revestimento", "marca", "Biancogres"),
    ("Argamassa colante AC-II para assentamento de porcelanato Tivoli — Eliane",
     "marca", "Eliane"),
    ("Massa corrida PVA sobre paredes internas — preparo de base para pintura "
     "acrílica Coral Branco Fosco", "marca", "Coral"),
    ("Sistema de proteção contra descargas atmosféricas marca Montal conforme "
     "NBR-5419", "codigo", "NBR-5419"),
    ("Tubo de esgoto Tigre DN40 em PVC branco", "codigo", "DN40"),
    ("Cabo de cobre nu 35mm² marca Termotécnica CA25", "codigo", "CA25"),
]


def _erros_da_regua(extrator):
    """Quais dos casos medidos ainda saem errados com `extrator`."""
    fora = []
    for descricao, campo, proibido in CASOS:
        saiu = extrator(descricao).get(campo)
        if saiu and proibido.lower() in str(saiu).lower():
            fora.append("%s=%r em %r" % (campo, saiu, descricao[:52]))
    return fora


def test_religar_a_trava_exige_os_4_defeitos_consertados():
    """🚨 O critério de aceite, medido em caso real.

    Com a trava fechada este teste apenas RELATA. No dia em que alguém puser
    `LIBERADO_PRO_CLIENTE = True`, ele passa a reprovar enquanto sobrar erro —
    e é isso que impede a especificação errada de sair pro cliente por um
    commit distraído."""
    from spec_extract import extrair_spec
    erram = _erros_da_regua(extrair_spec)
    assert not erram, ("%d de %d casos ainda errados:\n  %s"
                       % (len(erram), len(CASOS), "\n  ".join(erram)))


# ══════════════════════════════════════════════════════════════════════════
#  🪤 O OUTRO LADO: consertar demais também é defeito
# ══════════════════════════════════════════════════════════════════════════
#  Estes casos o extrator TEM que continuar acertando. Cada um é um falso
#  positivo que eu criei consertando os 4 defeitos, e que só apareceu quando
#  comparei ANTES × DEPOIS nas 338 descrições reais — nenhum deles aparecia
#  nos casos que eu já sabia. Guarda contra o remédio virar doença.
NAO_PODE_SUMIR = [
    # "assentamento de X" — aqui o item É o X. Quem denuncia vizinho é "PARA
    # assentamento" (aí o item é a argamassa).
    ("Fornecimento e assentamento de porcelanato Brooklyn Terrazzo 90×90cm — "
     "Biancogres, em parede", "Biancogres"),
    ("Assentamento de porcelanato Brooklyn Terrazzo 90×90 cm — Biancogres em "
     "parede do refeitório", "Biancogres"),
    # "sobre massa corrida" é o SUBSTRATO da tinta, não outro produto
    ("Pintura acrílica premium sobre massa corrida, 3 demãos, cor A Definir — "
     "Coral Fosco Completo", "Coral"),
    # "para piso" é USO, não outro produto: a marca é da própria tinta
    ("Pintura de piso — tinta para piso Suvinil, cor Cinza, sobre concreto "
     "existente regularizado", "Suvinil"),
    # marca dita sem "ou similar" em nenhum lugar
    ("Reservatório de água fria — caixa d'água Tigre com tampa — 750 litros",
     "Tigre"),
]


@pytest.mark.parametrize("descricao,marca", NAO_PODE_SUMIR)
def test_o_conserto_nao_pode_matar_a_marca_legitima(descricao, marca):
    from spec_extract import extrair_spec
    assert extrair_spec(descricao)["marca"] == marca, (
        "sumiu a marca legítima de %r" % descricao[:60])


CODIGO_CERTO = [
    # o SKU de verdade, e não o código do acabamento que vinha antes
    ("Chuveiro monocomando Deca Vogue 2993_C36_034 — alta e baixa pressão — "
     "Cromado CR10", "2993_C36_034"),
    ("Torneira para lavatório Deca Izy 1198_C37 — Mesa Bica Alta — Cromado CR10",
     "1198_C37"),
    # a família não serve: 2310 é a barra, _070_ESC é qual barra
    ("Barra de apoio Deca Conforto — Aço Inox Escovado ESC, 70 cm, "
     "ref. 2310_C_070_ESC", "2310_C_070_ESC"),
    # os que já estavam certos e não podem quebrar
    ("Torneira de mesa bica móvel cromado 1167.C.LNK Deca", "1167.C.LNK"),
    ("Cabide cromado CÓD. 2060-C-LN DECA (2 unid.)", "2060-C-LN"),
    ("Misturador Twin cromado - Cod. 2240.C - Deca", "2240.C"),
]


@pytest.mark.parametrize("descricao,codigo", CODIGO_CERTO)
def test_sai_o_codigo_do_produto_e_nao_o_do_acabamento(descricao, codigo):
    from spec_extract import extrair_spec
    assert extrair_spec(descricao)["codigo"] == codigo


def test_capacidade_nao_e_modelo():
    """🪤 Barrar o nome do bloco de CAD fez o extrator cair na CAPACIDADE:
    "split Hi-Wall Midea 12.000 BTU" saía com código "12.000"."""
    from spec_extract import extrair_spec
    r = extrair_spec("Fornecimento e instalação de split Hi-Wall Midea "
                     "12.000 BTU modelo VA-Hi-Wall-MIDEA-12kBtu-VS")
    assert r["marca"] == "Midea"
    assert r["codigo"] is None, "pegou %r — é a capacidade, não o modelo" % r["codigo"]


def test_controle_positivo_a_regua_PEGA_o_extrator_de_ontem():
    """🧪 Régua que só sabe dar verde não prova nada.

    Aqui ela recebe um extrator de mentira que devolve, em cada caso, o que o
    de ontem devolvia — e tem que reprovar os 9. Sem este controle, o dia em
    que a régua parar de medir chega em silêncio e eu leio o verde como
    'consertado'.

    🪤 A 1ª versão deste controle exigia que a régua visse defeito no extrator
    REAL. Funcionava enquanto o extrator estava quebrado e quebrou no minuto em
    que eu consertei — controle que morre no sucesso não guarda nada."""
    ontem = {d: {c: p} for d, c, p in CASOS}
    erram = _erros_da_regua(lambda d: ontem.get(d, {}))
    assert len(erram) == len(CASOS), (
        "a régua só viu %d dos %d defeitos que o extrator de ontem produzia"
        % (len(erram), len(CASOS)))
