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


def test_religar_a_trava_exige_os_4_defeitos_consertados():
    """🚨 O critério de aceite, medido em caso real.

    Com a trava fechada este teste apenas RELATA. No dia em que alguém puser
    `LIBERADO_PRO_CLIENTE = True`, ele passa a reprovar enquanto sobrar erro —
    e é isso que impede a especificação errada de sair pro cliente por um
    commit distraído."""
    from spec_extract import extrair_spec
    erram = []
    for descricao, campo, proibido in CASOS:
        saiu = extrair_spec(descricao).get(campo)
        if saiu and proibido.lower() in str(saiu).lower():
            erram.append("%s=%r em %r" % (campo, saiu, descricao[:52]))
    if not spec_extract.LIBERADO_PRO_CLIENTE:
        # ainda em conserto: o número é a régua, não a reprovação
        assert len(erram) <= len(CASOS), "medição impossível"
        return
    assert not erram, (
        "a trava foi aberta com %d de %d casos ainda errados:\n  %s"
        % (len(erram), len(CASOS), "\n  ".join(erram)))


def test_controle_a_regua_mede_alguma_coisa():
    """🧪 Um teste que só reprova quando a trava abre precisa provar, com a
    trava fechada, que ele CONSEGUE ver o defeito. Senão o dia da abertura
    chega e ele passa verde sem nunca ter medido nada."""
    from spec_extract import extrair_spec
    vistos = [c for c in CASOS
              if (extrair_spec(c[0]).get(c[1]) or "").lower().find(c[2].lower()) >= 0]
    assert vistos, (
        "a régua não vê NENHUM dos 8 defeitos medidos pela auditoria — ou eles "
        "sumiram todos de uma vez, ou o teste parou de medir")
