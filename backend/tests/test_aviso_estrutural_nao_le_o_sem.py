# -*- coding: utf-8 -*-
"""O aviso "parece projeto ESTRUTURAL" para de disparar em "SEM ESTRUTURAL".

🩸 02/09/2026 — Karina (TEKOA), primeira cliente do dia, mandou
"TEKOÁ RESERVA_EXE_REV01_SEM ESTRUTURAL.pdf" e o envio respondeu "esses
arquivos parecem de projeto ESTRUTURAL". Medido no error_log: foi a ÚNICA vez
que o aviso disparou desde que existe (01/08) — e disparou errado. Aviso falso
na primeira tela que a pessoa vê é o pior lugar pra errar.

🧪 Chama a função, não lê fonte. Controle positivo primeiro: os nomes que o
aviso EXISTE pra pegar continuam pegos.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest  # noqa: E402
import main as _m  # noqa: E402


def test_CONTROLE_nome_estrutural_de_verdade_CONTINUA_avisando():
    for nome in ("FORMA.pdf", "fundacao_rev2.dwg", "PROJETO ESTRUTURAL.pdf",
                 "Armacao-Laje-Tipo.pdf", "pilares e vigas.dxf", "ESTRUT_TERREO.pdf",
                 "PLANTA DE FORMAS.pdf"):
        assert _m._nome_parece_estrutural(nome), "%r deixou de avisar" % nome


def test_nome_NEGADO_nao_avisa():
    for nome in ("TEKOÁ RESERVA_EXE_REV01_SEM ESTRUTURAL.pdf", "ARQ_sem_estrutura.pdf",
                 "casa - s/ estrutural.pdf", "executivo NAO estrutural.pdf",
                 "projeto exceto fundação.pdf", "PLANTA SEM-FORMAS.pdf"):
        assert not _m._nome_parece_estrutural(nome), (
            "%r está NEGADO e o aviso disparou — foi exatamente o erro da Karina" % nome)


def test_CONTROLE_a_negacao_precisa_ser_palavra_inteira():
    """"SEMANA_ESTRUTURAL" não é "sem"; "informativo" não é "forma"."""
    assert _m._nome_parece_estrutural("SEMANA_ESTRUTURAL.pdf")
    assert not _m._nome_parece_estrutural("informativo.pdf")
    assert not _m._nome_parece_estrutural("plataforma.pdf")
    assert not _m._nome_parece_estrutural("")


def test_NAO_existe_uma_SEGUNDA_copia_da_regra_no_arquivo():
    """🪤 02/09 — a regra vivia solta dentro do `/api/process` e ficou lá depois
    que a detecção virou esta função. Continuava sendo compilada a cada upload,
    ninguém lia, e o pyflakes acusava "assigned to but never used".

    O risco não é desempenho: é a próxima pessoa achar a cópia velha primeiro e
    consertar a errada — foi exatamente assim que o "SEM ESTRUTURAL" da Karina
    passou, com a regra certa já escrita a duzentas linhas de distância.
    """
    import io
    import os
    fonte = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()
    # o miolo da regra, que não pode aparecer duas vezes
    # 🪤 03/09/2026 — este guarda ancorava no TEXTO do regex antigo
    # ("|pilar|viga|laje|baldrame|sapata") e quebrou quando o regex mudou pra
    # ter fronteira de palavra. O que ele quer garantir é "a regra existe UMA
    # vez", não "a regra está escrita com estas letras" — então a âncora passa
    # a ser a atribuição, que sobrevive a reescrita do padrão.
    assert fonte.count("_RX_ESTRUT_NOME = _re.compile(") == 1, (
        "existe mais de uma cópia da regra de nome estrutural em main.py — "
        "a próxima correção vai cair na cópia errada")


# ══════════════════════════════════════════════════════════════════════════
#  🩸 03/09/2026 — SEGUNDO DISPARO DESTE AVISO NA VIDA, E O SEGUNDO ERRADO
# ══════════════════════════════════════════════════════════════════════════
# Cliente `v.anjos.ia.81@` mandou "CIQUANTA-CABEAMENTO ESTRUTURADO.dwg" e leu
# "esses arquivos parecem de projeto ESTRUTURAL". Cabeamento ESTRUTURADO é rede
# de dados. O pedaço solto `estrut` casava com "estruturado".
#
# 🔑 Placar do aviso na vida inteira: 2 disparos, 2 errados (o outro é o caso
# Karina, logo acima). Aviso que só erra treina o cliente a ignorar TODOS os
# nossos avisos — o custo não fica no aviso falso, fica nos verdadeiros.

def test_cabeamento_ESTRUTURADO_nao_e_projeto_estrutural():
    """🩸 O arquivo real do cliente de 03/09."""
    assert not _m._nome_parece_estrutural(
        "CIQUANTA-CABEAMENTO ESTRUTURADO.dwg"), (
        "cabeamento estruturado (rede de dados) voltou a ser confundido com "
        "projeto estrutural")


def test_palavra_curta_dentro_de_outra_palavra_nao_dispara():
    """Rodei a versão antiga contra nomes plausíveis e achei mais dois."""
    assert not _m._nome_parece_estrutural("NAVIGATION-PLAN.dwg"), (
        "'viga' dentro de naVIGAtion")
    assert not _m._nome_parece_estrutural("LAJEADO-CENTRO.dwg"), (
        "'laje' dentro de Lajeado, que é cidade")


@pytest.mark.parametrize("nome", [
    "PROJETO ESTRUTURAL.pdf",
    "ESTRUTURA_R02.dwg",
    "ESTRUTURAS-METALICAS.dwg",
    "DETALHES ESTRUTURAIS.pdf",
    "FORMA_PAV_TIPO.dwg",
    "armacao-vigas.pdf",
    "FUNDACAO-BLOCOS.dwg",
    "planta-de-lajes.dwg",
    "PILARES-P1-P8.dwg",
    "BALDRAME.dwg",
    "sapatas-isoladas.dwg",
])
def test_CONTROLE_o_estrutural_de_VERDADE_continua_disparando(nome):
    """Apertar o regex não pode virar 'nunca avisa'.

    Sem estes, o conserto do falso positivo seria satisfeito por um regex que
    não casa com nada — e aí a gente perde o aviso legítimo, que é o motivo de
    ele existir (01/08: só 3 de 107 projetos escolhiam o modo estrutura, e
    FORMA.pdf/fundacao.pdf passavam como arquitetura).
    """
    assert _m._nome_parece_estrutural(nome), nome
