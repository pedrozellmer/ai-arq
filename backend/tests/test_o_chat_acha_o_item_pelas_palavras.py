# -*- coding: utf-8 -*-
"""O chat dizia que um item da planilha não existia — e culpava o DWG que não havia.

🩸 22/09/2026, job 844603fb. Prancha de pontos de elétrica, 1 PDF e nenhum CAD.
A cliente colou 3 linhas da legenda no chat do painel e o agente respondeu
"Nenhum dos três itens foi encontrado na planilha". UM estava lá: o conjunto
tomada + interruptor paralelo (8 un). Os outros dois — tomada em caixa 4x4
embutida no forro, para luminária de emergência, e tomada 4x4 de piso — são
linhas da legenda que a leitura da IA não listou (a planilha tem a tomada para
luminária de emergência em caixa 4x2, que é OUTRA linha da mesma legenda). Na
pergunta anterior, "caixa 4x4" também voltou 0 — e a planilha tem caixa
octogonal 4x4 (60 un).

🔑 Duas causas, as duas nossas:
  • `tool_search_items` procurava a FRASE inteira como pedaço da descrição.
    "tomada caixa 4x2" dava 0 com 8 linhas "Tomada ... em caixa 4x2\"". Em 60
    dias as 10 buscas de mais de uma palavra voltaram 0 — 10 de 10.
  • O prompt não dizia o que o cliente ENVIOU. Num projeto só-PDF o modelo
    culpou "os layers do DWG" e ofereceu "listar os arquivos DXF do projeto".

🩸 A revisão da 1ª versão do conserto (22/09) achou o erro do outro lado:
  • a tomada 4x4 do FORRO voltava com a tomada 4x2 como melhor candidato, e o
    prompt mandava dizer "a tomada está em caixa 4x2, e não 4x4 como na
    legenda" — o chat ia dizer à cliente que um item que NÃO está na planilha
    estava. Agora a linha que diz outra medida/lugar/formato vem marcada
    `outro_item`;
  • `items` trazia linha sem a palavra (portão por porta, quadra por quadro,
    tampa por tampo, "último pavimento" por "pavimento tipo").
  • file_types velho dizia só-PDF em projeto com DWG no Storage.

Este arquivo GERA a planilha de verdade (generate_spreadsheet) com as linhas do
caso e chama a ferramenta real em cima dela; o contexto é conferido rodando
`agent.ask` e a rota `/api/agent/ask` com o modelo trocado por um roteiro.
As descrições são as do caso (texto genérico de item, sem dado de ninguém).
"""
import asyncio
import io
import json
import os
import sys
import types

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

openpyxl = pytest.importorskip("openpyxl")

_ELE = "Instalações Elétricas e Dados"
# (descrição, un, qtd) — linhas da planilha do caso, na ordem em que saíram.
_LINHAS_DO_CASO = [
    ('Tomada simples monopolar hexagonal 2P+T-20A Universal, 250VCA, em caixa 4x2" — H=0,40m — conforme legenda de pontos', "un", 30),
    ('Tomada simples monopolar hexagonal 2P+T-10A Universal, 250VCA, em caixa 4x2" — H=0,40m — conforme legenda de pontos', "un", 40),
    ('Tomada simples monopolar hexagonal 2P+T-10A Universal, 250VCA, em caixa 4x2" — H=1,20m — conforme legenda de pontos', "un", 35),
    ('Tomada simples monopolar hexagonal 2P+T-10A Universal, 250VCA, em caixa 4x2" — H=2,20m — conforme legenda de pontos', "un", 10),
    ('Tomada simples monopolar hexagonal 2P+T-10A, 250VCA, uso em caixa 4x2", para luminária de emergência (LE) — conforme legenda de pontos (símbolo LE)', "un", 12),
    ('Tomada dupla monopolar hexagonal 2P+T-10A Universal, 250VCA, em caixa 4x2" — H=1,20m — conforme legenda de pontos', "un", 20),
    ('Eletroduto PVC rígido roscável Ø25mm (Ø1") — embutido em parede/laje — para alimentação de quadros e circuitos de maior bitola', "ml", 0),
    ('Eletroduto PVC rígido roscável Ø32mm — embutido em parede/laje — para alimentação de quadros de distribuição (coluna)', "ml", 0),
    ('Ponto sensor de presença (infravermelho no teto), em caixa octogonal 4x4" PVC — conforme legenda de pontos', "un", 10),
    ('Ponto luz no teto, em caixa octogonal 4x4" PVC — conforme legenda de pontos (símbolo círculo com SVA)', "un", 50),
    ('Conjunto tomada simples monopolar hexagonal 2P+T-10A Universal com interruptor paralelo, 250VCA, em caixa 4x2" — conforme legenda de pontos', "un", 8),
    ('Interruptor pulsador campainha monopolar 1 tecla, 10A, 250VCA, em caixa 4x2" — H=1,20m — conforme legenda de pontos', "un", 4),
    ('Interruptor simples monopolar 3 teclas, 10A, 250VCA, em caixa 4x2" — H=1,20m — conforme legenda de pontos', "un", 6),
    ('Cigarra campainha bivolt, uso em caixa 4x2 na parede — H=2,20m — conforme legenda de pontos', "un", 4),
    ('Quadro de distribuição de embutir (QD) — para apartamento tipo — com disjuntores eletromagnéticos 5kA 250VCA', "un", 4),
    ('Condutor de cobre eletrolítico, isolamento 750V, BWF 70°C, seção 2,5mm² — para circuitos de tomadas — em eletroduto PVC Ø1/2" embutido', "ml", 0),
    ('Caixa de passagem PVC 4x2" embutida em parede — para tomadas e interruptores — conforme notas gerais da prancha', "un", 200),
    ('Caixa octogonal PVC 4x4" embutida em laje — para pontos de luz no teto — conforme notas gerais da prancha', "un", 60),
    ('Disjuntor eletromagnético monopolar 5kA 250VCA — para circuitos terminais de iluminação e tomadas', "un", 60),
    ('Ponto de conexão para condensadora de ar-condicionado split 9000 BTU/h — CP.01 — H=2,25m — tomada 2P+T, C5 — 900VA, 220V', "un", 8),
    ('Luminária de emergência (LE) — bloco autônomo — conforme símbolo LE identificado na planta do pavimento tipo', "un", 12),
    ('Prever enchimento (eletroduto/caixa reserva) — conforme indicação na planta do último pavimento', "vb", 1),
]
_CONJUNTO = "Conjunto tomada simples monopolar hexagonal 2P+T-10A Universal com interruptor paralelo"
_TOMADA_LE = "Tomada simples monopolar hexagonal 2P+T-10A, 250VCA, uso em caixa 4x2\", para luminária de emergência"
_LUMINARIA_LE = "Luminária de emergência (LE) — bloco autônomo"
_OCTOGONAL = "Caixa octogonal PVC 4x4\" embutida em laje"

# As três linhas que a cliente colou (texto de legenda, genérico)...
_LEGENDA_CONJUNTO = ("CONJUNTO TOMADA SIMPLES MONOPOLAR HEXAGONAL 2P+T-10A UNIVERSAL COM "
                     "INTERRUPTOR PARALELO, 250VCA EM CAIXA 4x2'' - H=1,20m")
_LEGENDA_LE_FORRO = ("TOMADA 2P+T-10A EM CAIXA 4x4\", PARA LUMINÁRIA DE EMERGÊNCIA, EMBUTIDO "
                     "NO FORRO (CONFORME PROJETO ESPECÍFICO)")
_LEGENDA_PISO = "TOMADA 2P+T-10A EM CAIXA 4x4\" NO PISO"
# ...e a OUTRA linha da mesma legenda, que é a que a planilha tem (a tomada LE 4x2).
_LEGENDA_LE_4X2 = ("TOMADA SIMPLES MONOPOLAR HEXAGONAL 2P+T-10A 250VCA UNIVERSAL, USO EM "
                   "CAIXA 4x2'', PARA LUMINÁRIA DE EMERGÊNCIA - H=2,20m")


def _gerar_planilha(tmp_path, monkeypatch, linhas, nome):
    import agent
    from models import BudgetItem, Confidence, ProjectData
    from spreadsheet import generate_spreadsheet
    itens = [BudgetItem(item_num=str(i), description=d, unit=u, quantity=float(q),
                        observations="Contagem visual estimada.",
                        confidence=Confidence.ESTIMADO, origem="vision_pdf",
                        discipline=_ELE)
             for i, (d, u, q) in enumerate(linhas, 1)]
    caminho = str(tmp_path / f"orcamento_{nome}.xlsx")
    generate_spreadsheet(ProjectData(name="t"), itens, caminho, typology="residential")
    monkeypatch.setattr(agent, "_planilha_path", lambda job_id, **k: caminho)
    return caminho


@pytest.fixture
def planilha(tmp_path, monkeypatch):
    return _gerar_planilha(tmp_path, monkeypatch, _LINHAS_DO_CASO, "ele01")


# Palavras vizinhas: a MESMA raiz com outra ponta, e coisas diferentes.
_VIZINHAS = [
    ("Porta de madeira semi-oca 80x210 cm, com batente e ferragens", "un", 12),
    ("Portão de garagem basculante em chapa de aço", "un", 1),
    ("Quadro de distribuição de embutir (QD) 24 disjuntores", "un", 4),
    ("Pintura epóxi de quadra poliesportiva", "m2", 600),
    ("Tampo de granito para bancada da cozinha", "m2", 3),
    ("Tampa de concreto para caixa de inspeção 60x60", "un", 6),
    ("Luminária de emergência (LE) — conforme planta do pavimento tipo", "un", 12),
    ("Eletroduto PVC aparente no teto — conforme planta do último pavimento", "ml", 0),
    ("Quadro de força para elevadores — conforme planta do último pavimento", "un", 2),
    ("Reboco interno em paredes de alvenaria, espessura 2 cm", "m2", 0),
]


@pytest.fixture
def planilha_vizinhas(tmp_path, monkeypatch):
    return _gerar_planilha(tmp_path, monkeypatch, _VIZINHAS, "viz01")


def _buscar(q, job="ele01", **k):
    import agent
    r = agent.tool_search_items(job, q, **k)
    assert "error" not in r, r
    return r


def _descs(linhas):
    return [x["description"] for x in linhas]


def _tem(linhas, pedaco):
    return any(pedaco in d for d in _descs(linhas))


def _linhas_da_planilha(job):
    import agent
    wb = agent._open_planilha(job)
    try:
        return list(agent._iter_orcamento_rows(wb))
    finally:
        wb.close()


def _a_busca_antiga(job, q):
    """A busca de antes de 22/09, letra por letra: pedaço de texto, sem maiúscula."""
    return [r["description"][:120] for r in _linhas_da_planilha(job)
            if q.lower().strip() in r["description"].lower()]


# ── A busca do caso ───────────────────────────────────────────────────────────
def test_CONTROLE_a_armadilha_do_caso_esta_armada(planilha):
    """As buscas do caso NÃO são pedaço de descrição nenhuma — era por isso que
    a busca antiga (frase inteira) dava 0. Se isto mudar, o cenário não prova mais nada."""
    descs = [r["description"].lower() for r in _linhas_da_planilha("ele01")]
    assert len(descs) >= len(_LINHAS_DO_CASO), descs
    for q in ("tomada caixa 4x2", "luminária emergência tomada", "caixa 4x4"):
        assert not any(q in d for d in descs), q


def test_tomada_caixa_4x2_acha_as_linhas_que_a_busca_antiga_dava_como_zero(planilha):
    r = _buscar("tomada caixa 4x2")
    assert _tem(r["items"], _CONJUNTO), _descs(r["items"])
    assert _tem(r["items"], _TOMADA_LE), _descs(r["items"])
    assert r["count"] >= 7, r["count"]
    # 4x2 é 4x2: a caixa octogonal 4x4 não entra
    assert not _tem(r["items"], _OCTOGONAL), _descs(r["items"])
    assert {x["selo"] for x in r["items"]} == {"estimado"}, r["items"]


def test_luminaria_emergencia_tomada_acha_a_tomada_LE_e_sugere_a_luminaria(planilha):
    r = _buscar("luminária emergência tomada")
    assert _tem(r["items"], _TOMADA_LE), _descs(r["items"])
    assert _tem(r.get("candidatos", []), _LUMINARIA_LE), r


def test_caixa_4x4_acha_a_octogonal(planilha):
    r = _buscar("caixa 4x4")
    assert _tem(r["items"], _OCTOGONAL), _descs(r["items"])
    assert not any("4x2" in d for d in _descs(r["items"])), _descs(r["items"])


def test_caixa_4x4_QUADRADA_nao_inventa_e_diz_que_a_octogonal_e_OUTRO_item(planilha):
    """A planilha não tem caixa quadrada. A resposta honesta é "não há quadrada;
    há octogonal 4x4, que é outra caixa" — nem "não existe nada", nem "achei"."""
    r = _buscar("caixa 4x4 quadrada")
    assert r["count"] == 0, r["items"]
    assert r.get("termos_sem_correspondencia") == ["quadrado"], r
    cands = r.get("candidatos", [])
    oct_ = [c for c in cands if _OCTOGONAL in c["description"]]
    assert oct_ and oct_[0]["falta"] == ["quadrado"], cands
    assert oct_[0]["outro_item"] is True, oct_[0]
    assert oct_[0]["diverge"] == {"quadrado": ["octogonal"]}, oct_[0]
    assert "NÃO prova que o item não existe" in r.get("aviso", ""), r


def test_caixa_QUADRADA_com_metade_das_palavras_ainda_traz_candidatos(planilha):
    """2 palavras e 1 casando é METADE — e é o piso dos candidatos. Se o piso
    virar "mais da metade", a busca real "caixa quadrada" da cliente volta sem
    candidato nenhum, e o modelo só tem o "count 0" pra contar."""
    r = _buscar("caixa quadrada")
    assert r["count"] == 0, r["items"]
    cands = r.get("candidatos", [])
    assert cands and all(c["bate"] == ["caixa"] for c in cands), cands
    assert r.get("termos_sem_correspondencia") == ["quadrado"], r


def test_o_CONJUNTO_colado_da_legenda_E_o_item_da_planilha(planilha):
    """O único dos três que ESTAVA na planilha. A linha dela não traz a altura
    (H=1,20m) — falta de detalhe na descrição NÃO é outro item. Se "falta tem
    medida" bastasse pra `outro_item`, o chat voltaria a dizer à cliente que o
    conjunto não está na planilha, que é o erro de 22/09."""
    r = _buscar(_LEGENDA_CONJUNTO)
    primeira = (r["items"] or r.get("candidatos") or [{}])[0]
    assert _CONJUNTO in primeira.get("description", ""), r
    assert primeira.get("outro_item") is False, primeira
    assert primeira.get("falta") == ["1,2"], primeira


def test_a_tomada_LE_do_FORRO_nao_sai_como_a_tomada_LE_4x2_da_planilha(planilha):
    """🩸 A linha colada é a tomada em caixa 4x4 embutida no FORRO. A planilha só
    tem a tomada LE em caixa 4x2 — outra linha da legenda. A busca não pode
    apresentar uma como a outra: a 4x2 vem como `outro_item`, com o `diverge`
    dizendo a medida que muda, e nenhum candidato vem como o mesmo item."""
    r = _buscar(_LEGENDA_LE_FORRO)
    assert r["count"] == 0 and not _tem(r["items"], _TOMADA_LE), _descs(r["items"])
    cands = r.get("candidatos", [])
    alvo = [c for c in cands if _TOMADA_LE in c["description"]]
    assert alvo, cands
    assert alvo[0]["outro_item"] is True and alvo[0]["diverge"] == {"4x4": ["4x2"]}, alvo[0]
    assert all(c["outro_item"] for c in cands), [(c["description"][:50], c["outro_item"]) for c in cands]
    assert "forro" in r.get("termos_sem_correspondencia", []), r
    assert "outro_item" in r.get("aviso", ""), r


def test_CONTROLE_a_linha_da_legenda_que_E_a_tomada_LE_4x2_acha_ela_como_o_mesmo_item(planilha):
    """O par real da legenda: a linha 4x2 (H=2,20m) É a tomada LE da planilha.
    Sem este controle, "tudo vira outro_item" passaria no teste acima."""
    r = _buscar(_LEGENDA_LE_4X2)
    primeira = (r["items"] or r.get("candidatos") or [{}])[0]
    assert _TOMADA_LE in primeira.get("description", ""), r
    assert primeira.get("outro_item") is False, primeira


def test_tomada_em_caixa_4x4_mostra_OS_DOIS_lados_do_que_existe(planilha):
    """A resposta honesta a "tomada em caixa 4x4" tem duas metades: as tomadas
    da planilha estão em caixa 4x2 (são outros itens), e as caixas 4x4 são
    octogonais de teto. Se os candidatos mostrarem só uma, o modelo conta meia
    verdade. Por isso a palavra rara ("4x4", 3 linhas) pesa mais que a comum
    ("caixa", 16)."""
    r = _buscar("tomada caixa 4x4")
    assert r["count"] == 0, _descs(r["items"])
    cands = r.get("candidatos", [])
    # a CAIXA 4x4 em si (a 18ª linha) — na ordem da planilha ficaria atrás das
    # tomadas e fora dos 8 candidatos
    assert any(_OCTOGONAL in c["description"] for c in cands), _descs(cands)
    tomadas = [c for c in cands if c["description"].startswith("Tomada") and "4x2" in c["description"]]
    assert tomadas, _descs(cands)
    assert all(c["outro_item"] and c["diverge"] == {"4x4": ["4x2"]} for c in tomadas), tomadas


def test_caixa_embutida_no_FORRO_nao_e_a_caixa_de_PAREDE(planilha):
    """Lugar também separa item: a caixa de passagem 4x2 da planilha é de
    PAREDE. Pra "caixa 4x2 embutida no forro" ela é candidata — como outro item."""
    r = _buscar("caixa 4x2 embutida no forro")
    assert r["count"] == 0, _descs(r["items"])
    cx = [c for c in r.get("candidatos", []) if "Caixa de passagem" in c["description"]]
    assert cx and cx[0]["outro_item"] and cx[0]["diverge"] == {"forro": ["parede"]}, r


def test_tomada_de_PISO_nao_existe_e_a_busca_diz_isso(planilha):
    r = _buscar(_LEGENDA_PISO)
    assert r["count"] == 0, r["items"]
    assert "piso" in r.get("termos_sem_correspondencia", []), r
    cands = r.get("candidatos", [])
    assert cands and all(c["outro_item"] for c in cands), cands


# ── Normalização ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("q,esperada", [
    ("LUMINARIA EMERGENCIA", _LUMINARIA_LE),         # sem acento, maiúscula
    ("tomadas emergência", _TOMADA_LE),              # plural
    ("interruptor paralelo 4 x 2", _CONJUNTO),       # medida com espaço
    ("2P + T 20 A", "2P+T-20A"),                     # 2P+T e amperagem soltos
    ("cx octogonal", _OCTOGONAL),                    # abreviação de caixa
    ("eletroduto rigido roscavel", "Eletroduto PVC rígido roscável Ø25mm"),  # acento no começo
    ("caixa passagem nota geral", "Caixa de passagem PVC 4x2"),    # gerais -> geral
    ("caixa octogonal embutido", _OCTOGONAL),        # embutido x embutida (adjetivo)
    ("tomada dupla 1.20", "Tomada dupla monopolar"),  # 1.20 = 1,20m
    ("conexões condensadora", "Ponto de conexão para condensadora"),  # plural -ões
])
def test_a_busca_tolera_acento_caixa_plural_e_medida(planilha, q, esperada):
    r = _buscar(q)
    assert _tem(r["items"], esperada), (q, _descs(r["items"]), r.get("candidatos"))


def test_10A_nao_casa_20A(planilha):
    r = _buscar("tomada 20A")
    assert r["count"] == 1 and "2P+T-20A" in r["items"][0]["description"], _descs(r["items"])


def test_CONTROLE_palavra_de_fora_nao_inventa_candidato(planilha):
    r = _buscar("porcelanato")
    assert r["count"] == 0 and not r.get("candidatos"), r
    assert r.get("termos_sem_correspondencia") == ["porcelanato"], r


@pytest.mark.parametrize("q", ["Eletroduto", "LE", "4x2"])
def test_CONTROLE_uma_palavra_acha_as_mesmas_linhas_de_antes(planilha, q):
    """Busca de UMA palavra era a que funcionava (5 de 6 em 60 dias): o conserto
    não pode perder linha que a busca por pedaço de texto achava."""
    antes = _a_busca_antiga("ele01", q)
    r = _buscar(q)
    assert antes and _descs(r["items"]) == antes, (q, antes, _descs(r["items"]))
    assert not r.get("aviso"), r


# ── `items` só traz a palavra IGUAL ──────────────────────────────────────────
@pytest.mark.parametrize("q,intrusa,palavra_dela", [
    ("porta", "Portão de garagem", "portao"),
    ("portão", "Porta de madeira", "porta"),
    ("quadro", "quadra poliesportiva", "quadra"),
    ("tampo", "Tampa de concreto", "tampa"),
])
def test_a_palavra_vizinha_nao_entra_em_items_so_em_candidatos(planilha_vizinhas, q, intrusa, palavra_dela):
    """🩸 Revisão de 22/09: `items` (que a ferramenta promete ao modelo como "as
    linhas com TODAS as palavras") trazia portão por porta, quadra por quadro,
    tampa por tampo — o modelo somaria item errado como se fosse o pedido. A
    vizinha pode aparecer como candidato, dizendo a `variante` que casou."""
    r = _buscar(q, job="viz01")
    assert not _tem(r["items"], intrusa), (q, _descs(r["items"]))
    # uma palavra: exatamente as linhas que a busca antiga já achava
    assert _descs(r["items"]) == _a_busca_antiga("viz01", q), (q, _descs(r["items"]))
    viz = [c for c in r.get("candidatos", []) if intrusa in c["description"]]
    assert viz and viz[0]["variante"] == {r["busca_por_palavras"][0]: palavra_dela}, r


def test_pavimento_TIPO_nao_traz_o_ultimo_pavimento(planilha_vizinhas):
    """"tipo" era palavra vazia: "pavimento tipo" virava "pavimento" e trazia as
    linhas do último pavimento (na planilha real do caso, 5 de 6 erradas)."""
    r = _buscar("pavimento tipo", job="viz01")
    assert r["busca_por_palavras"] == ["pavimento", "tipo"], r
    assert _descs(r["items"]) == ["Luminária de emergência (LE) — conforme planta do pavimento tipo"], r
    ult = [c for c in r.get("candidatos", []) if "último pavimento" in c["description"]]
    assert ult and all(c["falta"] == ["tipo"] for c in ult), r


def test_adjetivo_no_feminino_acha_o_masculino(planilha_vizinhas):
    """A lista fechada de adjetivos (interna = interno) é o que sobra da regra
    a/o: "parede interna" acha o reboco interno em paredes — a busca real de um
    cliente em 02/09 — sem abrir a porta pro quadro/quadra."""
    r = _buscar("parede interna", job="viz01")
    assert _tem(r["items"], "Reboco interno em paredes"), r
    externa = _buscar("parede externa", job="viz01")
    assert externa["count"] == 0, externa["items"]
    reb = [c for c in externa.get("candidatos", []) if "Reboco interno" in c["description"]]
    assert reb and reb[0]["outro_item"] and reb[0]["diverge"] == {"externo": ["interno"]}, externa


def test_o_teto_de_itens_vale_com_mais_de_20_linhas(tmp_path, monkeypatch):
    """O modelo recebe no máximo `max_hits` linhas, na ordem da planilha — sem
    o teto, 200 linhas de caixa estouram o limite do resultado da ferramenta."""
    linhas = [(f"Caixa de passagem PVC 4x2 embutida — trecho {i:02d}", "un", i) for i in range(1, 26)]
    _gerar_planilha(tmp_path, monkeypatch, linhas, "teto01")
    todas = [r["description"][:120] for r in _linhas_da_planilha("teto01")
             if "Caixa de passagem" in r["description"]]
    assert len(todas) == 25, todas
    r = _buscar("caixa passagem", job="teto01")
    assert r["count"] == 20 and _descs(r["items"]) == todas[:20], r["count"]


# ── O contexto: o que o cliente enviou ────────────────────────────────────────
def _rodar_ask(monkeypatch, tipos):
    import agent
    import llm_retry
    monkeypatch.setattr(agent, "_log_conversation", lambda *a, **k: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "teste-sem-rede")
    monkeypatch.setitem(sys.modules, "anthropic",
                        types.SimpleNamespace(Anthropic=lambda **kw: object()))
    vistos = []

    def _falso(client, **kw):
        vistos.append(kw)
        fim = types.SimpleNamespace(type="text", text="ok")
        return types.SimpleNamespace(content=[fim], stop_reason="end_turn")

    monkeypatch.setattr(llm_retry, "call_with_retry", _falso)
    agent.ask("ele01", "quantas caixas 4x4 quadradas?", tipos_de_arquivo=tipos)
    assert vistos, "o modelo nem foi chamado"
    return vistos[0]["system"], [t["name"] for t in vistos[0]["tools"]]


def test_projeto_SO_PDF_o_modelo_sabe_e_perde_a_ferramenta_de_DXF(monkeypatch):
    system, ferramentas = _rodar_ask(monkeypatch, {"pdf": 1, "dxf": 0, "dwg": 0})
    assert "NENHUM DWG ou DXF" in system, system[-700:]
    assert "não ofereça listar DXF" in system, system[-700:]
    # a causa exata do caso: o chat culpou layer/bloco/DWG num projeto de 1 PDF
    assert "nunca explique a falta de um item por layer, bloco ou DWG" in system, system[-700:]
    assert "read_dxf_summary" not in ferramentas, ferramentas
    assert "search_items" in ferramentas, ferramentas


def test_o_prompt_manda_ler_os_candidatos_e_nao_da_o_exemplo_errado(monkeypatch):
    """O SYSTEM_PROMPT é o que o modelo lê TODA vez: a regra da busca vazia tem
    que estar lá, com o `outro_item` — e sem o exemplo da 1ª versão ("a tomada
    está em caixa 4x2, e não 4x4 como na legenda"), que ensinava a apresentar
    outro item como o pedido."""
    system, _ = _rodar_ask(monkeypatch, {"pdf": 1, "dxf": 0, "dwg": 0})
    assert "BUSCA VAZIA NÃO PROVA QUE O ITEM NÃO EXISTE" in system, system[:500]
    assert "`outro_item: true`" in system and "É OUTRO item" in system, system
    assert "e não 4x4 como na legenda" not in system, system


def test_CONTROLE_projeto_COM_DXF_mantem_a_ferramenta(monkeypatch):
    system, ferramentas = _rodar_ask(monkeypatch, {"pdf": 1, "dxf": 2, "dwg": 0})
    assert "read_dxf_summary" in ferramentas, ferramentas
    assert "NENHUM DWG" not in system, system[-700:]
    assert "2 DXF" in system, system[-700:]


def test_CONTROLE_projeto_com_DWG_e_sem_DXF_nao_e_so_PDF(monkeypatch):
    """DWG+PDF (há projetos assim): o DWG é CAD. Sem olhar o DWG, o chat
    esconderia a ferramenta e diria "NENHUM DWG" a quem mandou DWG."""
    system, ferramentas = _rodar_ask(monkeypatch, {"pdf": 1, "dxf": 0, "dwg": 2})
    assert "read_dxf_summary" in ferramentas, ferramentas
    assert "NENHUM DWG" not in system, system[-700:]
    assert "2 DWG" in system, system[-700:]


def test_CONTROLE_sem_saber_os_arquivos_nao_esconde_nada_nem_afirma_CAD(monkeypatch):
    system, ferramentas = _rodar_ask(monkeypatch, None)
    assert "read_dxf_summary" in ferramentas, ferramentas
    assert "não consegui confirmar" in system, system[-700:]


# ── A leitura dos tipos: file_types E o que está guardado ────────────────────
def _supabase_de_mentira(monkeypatch, file_types, objetos=(), linhas_dxf=0, cai=()):
    """Troca a rede por um roteiro, por URL: projects (file_types), a listagem
    do Storage do projeto e as linhas medidas do DXF. `cai` = pedaços de URL
    que respondem com erro de rede."""
    import urllib.request
    pedidos = []

    def _abre(req, **k):
        url = req.full_url
        pedidos.append((req.get_method(), url, req.data))
        if any(p in url for p in cai):
            raise OSError("sem rede")
        if "/rest/v1/projects?" in url:
            corpo = [] if file_types is None else [{"file_types": file_types}]
        elif "/storage/v1/object/list/" in url:
            corpo = [{"name": n, "id": None if "." not in n else "x"} for n in objetos]
        elif "/rest/v1/project_items?" in url:
            corpo = [{"item_num": "1.%d" % i} for i in range(linhas_dxf)]
        else:
            raise AssertionError("URL fora do roteiro: " + url)
        return io.BytesIO(json.dumps(corpo).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", _abre)
    return pedidos


_SO_PDF = {"dwg": 0, "dxf": 0, "pdf": 1}


def test_a_leitura_dos_tipos_devolve_o_dict_do_banco_e_None_na_falha(monkeypatch):
    import agent
    pedidos = _supabase_de_mentira(monkeypatch, _SO_PDF,
                                   objetos=["prancha_ele.pdf", "prancha_ele_p1.png", "checkpoint"])
    assert agent.tipos_de_arquivo_do_projeto("ele01") == _SO_PDF
    urls = [u for _, u, _ in pedidos]
    assert "job_id=eq.ele01" in urls[0] and "select=file_types" in urls[0], urls
    (lista,) = [p for p in pedidos if "/storage/v1/object/list/" in p[1]]
    assert lista[0] == "POST" and json.loads(lista[2])["prefix"] == "ele01/", lista
    assert any("origem=eq.dxf_geom" in u and "job_id=eq.ele01" in u for u in urls), urls

    _supabase_de_mentira(monkeypatch, _SO_PDF, cai=["/rest/v1/projects?"])
    assert agent.tipos_de_arquivo_do_projeto("ele01") is None
    _supabase_de_mentira(monkeypatch, None)
    assert agent.tipos_de_arquivo_do_projeto("ele01") is None


def test_file_types_VELHO_com_DWG_no_storage_nao_vira_so_PDF(monkeypatch):
    """🩸 Revisão de 22/09: 2 projetos de cliente têm file_types {pdf:n} e DWG no
    Storage (resto do /add-file que descartava file_types, consertado em 03/09).
    O chat esconderia read_dxf_summary e juraria "aqui não existe layer"."""
    import agent
    _supabase_de_mentira(monkeypatch, {"pdf": 2, "dxf": 0, "dwg": 0},
                         objetos=["planta.pdf", "planta.DWG", "corte.pdf"])
    assert agent.tipos_de_arquivo_do_projeto("velho01") is None


def test_file_types_velho_com_linha_medida_do_DXF_nao_vira_so_PDF(monkeypatch):
    import agent
    _supabase_de_mentira(monkeypatch, {"pdf": 1}, objetos=["planta.pdf"], linhas_dxf=1)
    assert agent.tipos_de_arquivo_do_projeto("velho02") is None


@pytest.mark.parametrize("cai", ["/storage/v1/object/list/", "/rest/v1/project_items?"])
def test_so_PDF_sem_a_confirmacao_nao_vira_so_PDF(monkeypatch, cai):
    """Falta de resposta não é "não há CAD": sem confirmar, o ramo neutro."""
    import agent
    _supabase_de_mentira(monkeypatch, _SO_PDF, objetos=["planta.pdf"], cai=[cai])
    assert agent.tipos_de_arquivo_do_projeto("ele01") is None


def test_projeto_com_CAD_no_file_types_nao_precisa_do_storage(monkeypatch):
    import agent
    pedidos = _supabase_de_mentira(monkeypatch, {"pdf": 1, "dxf": 1, "dwg": 0},
                                   cai=["/storage/", "/project_items"])
    assert agent.tipos_de_arquivo_do_projeto("cad01") == {"pdf": 1, "dxf": 1, "dwg": 0}
    assert len(pedidos) == 1, pedidos


def test_o_bucket_que_o_agente_lista_e_o_das_pranchas():
    import agent
    import main
    assert agent._BUCKET_DAS_PRANCHAS == main.PRANCHAS_BUCKET


@pytest.mark.parametrize("objetos,so_pdf", [
    (["planta.pdf", "planta.dwg"], False),   # o caso: file_types velho, DWG guardado
    (["planta.pdf"], True),                  # CONTROLE: só PDF de verdade
])
def test_o_chat_do_projeto_com_file_types_velho_mantem_a_ferramenta_de_DXF(monkeypatch, objetos, so_pdf):
    """A cadeia inteira: a leitura real dos tipos (rede em roteiro) entregue ao
    ask real (modelo em roteiro). Com DWG guardado, nada de "NENHUM DWG"."""
    import agent
    _supabase_de_mentira(monkeypatch, {"pdf": 1, "dxf": 0, "dwg": 0}, objetos=objetos)
    tipos = agent.tipos_de_arquivo_do_projeto("ele01")
    system, ferramentas = _rodar_ask(monkeypatch, tipos)
    assert ("NENHUM DWG ou DXF" in system) is so_pdf, system[-700:]
    assert ("read_dxf_summary" in ferramentas) is (not so_pdf), ferramentas
    if not so_pdf:
        assert "não consegui confirmar" in system, system[-700:]


class _Req:
    def __init__(self, corpo=b""):
        self._corpo = corpo
        self.state = type("_S", (), {})()

    async def body(self):
        return self._corpo


def test_a_rota_do_chat_ENTREGA_os_tipos_de_arquivo_ao_agente(monkeypatch):
    """Sem isto, todo o contexto acima é código morto em produção: a rota é quem
    sabe o job, e só ela lê os tipos do banco."""
    import threading
    import agent
    import main
    lidos, recebido = [], {}
    monkeypatch.setattr(main, "_require_project_owner", lambda *a, **k: "dono")

    def _tipos(job_id, **k):
        lidos.append((job_id, threading.get_ident()))
        return {"pdf": 1, "dxf": 0, "dwg": 0}

    def _ask(**k):
        recebido.update(k)
        return {"answer": "ok", "tool_calls": [], "iterations": 1}

    monkeypatch.setattr(agent, "tipos_de_arquivo_do_projeto", _tipos)
    monkeypatch.setattr(agent, "ask", _ask)
    resp = asyncio.run(main.agent_ask(_Req(), job_id="ele01", question="tem tomada de piso?"))
    assert resp["answer"] == "ok", resp
    assert [j for j, _ in lidos] == ["ele01"], lidos
    assert recebido.get("tipos_de_arquivo") == {"pdf": 1, "dxf": 0, "dwg": 0}, recebido
    # 🧊 a leitura é rede (até 8 s): no laço de eventos ela congela o site (03/09).
    # asyncio.run roda o laço NESTA thread — a leitura tem que ter ido pra outra.
    assert lidos[0][1] != threading.get_ident(), (
        "a leitura dos tipos de arquivo rodou no laço de eventos")
