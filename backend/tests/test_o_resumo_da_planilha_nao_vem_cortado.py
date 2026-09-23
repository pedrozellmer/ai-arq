# -*- coding: utf-8 -*-
"""O resumo por disciplina conta a planilha INTEIRA — nunca 10% dela.

🩸 23/09/2026 — MEDIDO nas 26 conversas reais do chat do projeto.
*"Me dá um resumo dos itens da planilha por disciplina"* é a pergunta mais
feita (**4 de 26**) e é **sugestão do próprio produto**: o texto chega idêntico
nas quatro vezes, é botão. **Duas das quatro falharam**, com esta resposta:

    "A lista veio incompleta — a planilha tem mais de 200 itens e o resultado
     foi cortado, então não consigo dar um resumo por disciplina"

O cliente com a maior planilha do dia (609 itens) clicou na sugestão que a
gente oferece e levou um "não consigo".

📊 A conta que explica: no job `9fa1fed7` a planilha ocupa **477.640
caracteres — 60× o teto de 8.000**, porque cada linha carrega 742 caracteres
(a observação traz a prova da medição). O chat enxergava **47 de 609 linhas**.

🔑 Agregar é contagem, não leitura. Dez linhas de resposta, completas, de
graça — em vez de mandar meio milhão de caracteres pro modelo ler.

🚫 Aumentar o teto não resolveria: a RESPOSTA do modelo também tem teto, e uma
já saiu cortada no meio da frase (15/09).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import (  # noqa: E402
    _TETO_RESULTADO_FERRAMENTA,
    _conteudo_da_ferramenta,
    resumo_por_disciplina,
    titulos_de_disciplina,
)

_TITULOS = {"1": "SERVIÇOS GERAIS", "2": "ARQUITETURA", "3": "ELÉTRICA"}


def _linha(num, selo="estimado", unit="m²", qty=10.0, obs=""):
    return {"item_num": num, "description": "Item " + num, "unit": unit,
            "quantity": qty, "selo": selo, "observations": obs}


def _planilha_grande(n_por_disc=203):
    """609 linhas em 3 disciplinas — o tamanho REAL do job que falhou."""
    linhas = []
    for d in ("1", "2", "3"):
        for i in range(1, n_por_disc + 1):
            linhas.append(_linha("%s.%d" % (d, i),
                                 selo="medido" if i % 3 == 0 else "estimado"))
    return linhas


# ══════════════════════════════════════════════════════════════════════════
#  O CASO REAL: 609 linhas
# ══════════════════════════════════════════════════════════════════════════
def test_conta_as_609_linhas_do_job_que_falhou():
    r = resumo_por_disciplina(_planilha_grande(), _TITULOS)
    assert r["total_itens"] == 609, r["total_itens"]
    assert r["n_disciplinas"] == 3
    assert sum(d["itens"] for d in r["disciplinas"]) == 609


def test_o_resumo_de_609_linhas_CABE_no_teto_da_ferramenta():
    """🔑 É isto que impede a resposta 'a lista veio incompleta'."""
    r = resumo_por_disciplina(_planilha_grande(), _TITULOS)
    txt = _conteudo_da_ferramenta(r)
    assert "[RESULTADO CORTADO" not in txt, (
        "o resumo AINDA trunca — o conserto nao serviu pra nada")
    assert len(json.dumps(r, ensure_ascii=False)) < _TETO_RESULTADO_FERRAMENTA


def test_CONTROLE_a_planilha_CRUA_de_609_linhas_estoura_o_teto():
    """Prova que o problema era real, e que agregar é o que resolve."""
    cru = {"count": 609, "items": [
        dict(_linha("1.%d" % i),
             observations="✓ MEDIDO — contagem medido no layer 'A-WALL' = "
                          "13,00 (conferido contra a geometria do arquivo)")
        for i in range(1, 610)]}
    txt = _conteudo_da_ferramenta(cru)
    assert "[RESULTADO CORTADO" in txt, (
        "o controle parou de provar: a planilha crua TINHA que estourar")


def test_uma_planilha_ABSURDA_de_6000_linhas_ainda_cabe():
    """O resumo não cresce com a planilha — cresce com o nº de disciplinas."""
    r = resumo_por_disciplina(_planilha_grande(2000), _TITULOS)
    assert r["total_itens"] == 6000
    assert len(json.dumps(r, ensure_ascii=False)) < _TETO_RESULTADO_FERRAMENTA


# ══════════════════════════════════════════════════════════════════════════
#  A CONTA — o número tem que bater com a planilha
# ══════════════════════════════════════════════════════════════════════════
def test_separa_medido_de_estimado_por_disciplina():
    """🚨 Regra dura nº1: em 15/09 o resumo pôs '✓ medido' em 20 linhas
    ESTIMADAS, com o orçamentista lendo. O selo vem da PLANILHA."""
    linhas = [_linha("1.1", "medido"), _linha("1.2", "estimado"),
              _linha("1.3", "medido"), _linha("2.1", "estimado")]
    r = resumo_por_disciplina(linhas, _TITULOS)
    d1 = [d for d in r["disciplinas"] if d["n"] == "1"][0]
    assert (d1["medidos"], d1["estimados"]) == (2, 1), d1
    assert (r["medidos"], r["estimados"]) == (2, 2), r


def test_a_capa_0x_e_METADADO_e_nao_entra_como_servico():
    """Linha 0.x é a capa (área do projeto) — não é medida nem estimativa."""
    linhas = [_linha("0.1", "metadado"), _linha("1.1", "medido")]
    r = resumo_por_disciplina(linhas, _TITULOS)
    assert r["metadados"] == 1
    assert r["medidos"] == 1
    assert r["estimados"] == 0


def test_conta_as_linhas_SEM_quantidade():
    """É o número que o cliente mais reclama: 'a planilha veio com zeros'."""
    linhas = [_linha("1.1", qty=0), _linha("1.2", qty=None),
              _linha("1.3", qty=12.5), _linha("1.4", qty="")]
    r = resumo_por_disciplina(linhas, _TITULOS)
    d1 = r["disciplinas"][0]
    assert d1["sem_quantidade"] == 3, d1


def test_agrupa_as_unidades_de_cada_disciplina():
    linhas = [_linha("1.1", unit="m²"), _linha("1.2", unit="m²"),
              _linha("1.3", unit="un")]
    d1 = resumo_por_disciplina(linhas, _TITULOS)["disciplinas"][0]
    assert d1["unidades"] == {"m²": 2, "un": 1}


def test_as_disciplinas_saem_na_ORDEM_da_planilha():
    linhas = [_linha("3.1"), _linha("1.1"), _linha("10.1"), _linha("2.1")]
    r = resumo_por_disciplina(linhas, _TITULOS)
    assert [d["n"] for d in r["disciplinas"]] == ["1", "2", "3", "10"], (
        "10 depois de 3: ordenar como TEXTO poria o 10 antes do 2")


def test_disciplina_sem_titulo_nao_quebra():
    r = resumo_por_disciplina([_linha("7.1")], _TITULOS)
    assert r["disciplinas"][0]["nome"] == "(sem título)"


def test_planilha_vazia_devolve_zero_sem_explodir():
    r = resumo_por_disciplina([], _TITULOS)
    assert r["total_itens"] == 0 and r["disciplinas"] == []


# ══════════════════════════════════════════════════════════════════════════
#  OS TÍTULOS — lidos da planilha de verdade
# ══════════════════════════════════════════════════════════════════════════
class _AbaFalsa:
    def __init__(self, linhas):
        self._l = linhas

    def iter_rows(self, **k):
        return iter(self._l)


class _WbFalso:
    def __init__(self, linhas):
        self.sheetnames = ["Orçamento"]
        self._aba = _AbaFalsa(linhas)

    def __getitem__(self, nome):
        return self._aba


def test_le_o_cabecalho_como_spreadsheet_py_escreve():
    """`f'{disc_num}. {disc_name.upper()}'` — o formato real do gerador."""
    wb = _WbFalso([("1. SERVIÇOS GERAIS", None), ("1.1", "Administração"),
                   ("2. ARQUITETURA", None), ("2.1", "Alvenaria")])
    assert titulos_de_disciplina(wb) == {"1": "SERVIÇOS GERAIS",
                                         "2": "ARQUITETURA"}


def test_NAO_confunde_item_1_1_com_titulo_de_disciplina():
    """🪤 Sem o espaço obrigatório no padrão, o título comeria a 1ª linha."""
    wb = _WbFalso([("1.1", "Item qualquer"), ("1.10", "Outro")])
    assert titulos_de_disciplina(wb) == {}


def test_aba_sem_orcamento_devolve_vazio():
    class _Vazio:
        sheetnames = ["Capa"]
    assert titulos_de_disciplina(_Vazio()) == {}


# ══════════════════════════════════════════════════════════════════════════
#  A FERRAMENTA está no catálogo do chat
# ══════════════════════════════════════════════════════════════════════════
def test_a_ferramenta_existe_e_o_dispatcher_conhece():
    import agent
    nomes = [t["name"] for t in agent.TOOLS]
    assert "resumo_por_disciplina" in nomes, nomes
    fonte = open(agent.__file__, encoding="utf-8").read()
    assert 'if name == "resumo_por_disciplina"' in fonte, (
        "a ferramenta existe no catalogo mas o dispatcher nao chama — "
        "o modelo pediria e receberia erro")


def test_a_descricao_DESVIA_o_modelo_do_list_items():
    """Sem isso o modelo continua escolhendo `list_items` e truncando."""
    import agent
    t = [x for x in agent.TOOLS if x["name"] == "resumo_por_disciplina"][0]
    d = t["description"].lower()
    assert "list_items" in d, "a descricao tem que dizer o que NAO usar"
    assert "nunca" in d or "never" in d
    assert "truncad" in d or "cortad" in d
