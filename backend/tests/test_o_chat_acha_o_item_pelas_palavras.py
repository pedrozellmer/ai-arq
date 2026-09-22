# -*- coding: utf-8 -*-
"""O chat dizia que um item da planilha não existia — e culpava o DWG que não havia.

🩸 22/09/2026, job 844603fb. Prancha de pontos de elétrica, 1 PDF e nenhum CAD.
A cliente colou 3 linhas da legenda no chat do painel e o agente respondeu
"Nenhum dos três itens foi encontrado na planilha". DOIS estavam lá: o conjunto
tomada + interruptor paralelo (8 un) e a tomada para luminária de emergência
(12 un). Na pergunta anterior, "caixa 4x4" também voltou 0 — e a planilha tem
caixa octogonal 4x4 (60 un).

🔑 Duas causas, as duas nossas:
  • `tool_search_items` procurava a FRASE inteira como pedaço da descrição.
    "tomada caixa 4x2" dava 0 com 8 linhas "Tomada ... em caixa 4x2\"". Em 60
    dias as 10 buscas de mais de uma palavra voltaram 0 — 10 de 10.
  • O prompt não dizia o que o cliente ENVIOU. Num projeto só-PDF o modelo
    culpou "os layers do DWG" e ofereceu "listar os arquivos DXF do projeto".

Este arquivo GERA a planilha de verdade (generate_spreadsheet) com as linhas do
caso e chama a ferramenta real em cima dela; o contexto é conferido rodando
`agent.ask` e a rota `/api/agent/ask` com o modelo trocado por um roteiro.
As descrições são as do caso (texto genérico de item, sem dado de ninguém).
"""
import asyncio
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

# As três linhas que a cliente colou (texto de legenda, genérico).
_LEGENDA_CONJUNTO = ("CONJUNTO TOMADA SIMPLES MONOPOLAR HEXAGONAL 2P+T-10A UNIVERSAL COM "
                     "INTERRUPTOR PARALELO, 250VCA EM CAIXA 4x2'' - H=1,20m")
_LEGENDA_LE = ("TOMADA 2P+T-10A EM CAIXA 4x4\", PARA LUMINÁRIA DE EMERGÊNCIA, EMBUTIDO "
               "NO FORRO (CONFORME PROJETO ESPECÍFICO)")
_LEGENDA_PISO = "TOMADA 2P+T-10A EM CAIXA 4x4\" NO PISO"


@pytest.fixture
def planilha(tmp_path, monkeypatch):
    import agent
    from models import BudgetItem, Confidence, ProjectData
    from spreadsheet import generate_spreadsheet
    itens = [BudgetItem(item_num=str(i), description=d, unit=u, quantity=float(q),
                        observations="Contagem visual estimada.",
                        confidence=Confidence.ESTIMADO, origem="vision_pdf",
                        discipline=_ELE)
             for i, (d, u, q) in enumerate(_LINHAS_DO_CASO, 1)]
    caminho = str(tmp_path / "orcamento_ele01.xlsx")
    generate_spreadsheet(ProjectData(name="t"), itens, caminho, typology="residential")
    monkeypatch.setattr(agent, "_planilha_path", lambda job_id, **k: caminho)
    return caminho


def _buscar(q):
    import agent
    r = agent.tool_search_items("ele01", q)
    assert "error" not in r, r
    return r


def _descs(linhas):
    return [x["description"] for x in linhas]


def _tem(linhas, pedaco):
    return any(pedaco in d for d in _descs(linhas))


# ── A busca do caso ───────────────────────────────────────────────────────────
def test_CONTROLE_a_armadilha_do_caso_esta_armada(planilha):
    """As buscas do caso NÃO são pedaço de descrição nenhuma — era por isso que
    a busca antiga (frase inteira) dava 0. Se isto mudar, o cenário não prova mais nada."""
    import agent
    wb = agent._open_planilha("ele01")
    descs = [r["description"].lower() for r in agent._iter_orcamento_rows(wb)]
    wb.close()
    assert len(descs) >= len(_LINHAS_DO_CASO), descs
    for q in ("tomada caixa 4x2", "luminária emergência tomada", "caixa 4x4"):
        assert not any(q in d for d in descs), q


def test_tomada_caixa_4x2_acha_as_duas_linhas_que_o_chat_disse_que_nao_existiam(planilha):
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


def test_caixa_4x4_QUADRADA_nao_inventa_mas_mostra_a_octogonal(planilha):
    """A planilha não tem caixa quadrada. A resposta honesta é "não há quadrada;
    há octogonal 4x4" — nem "não existe", nem fingir que achou."""
    r = _buscar("caixa 4x4 quadrada")
    assert r["count"] == 0, r["items"]
    assert r.get("termos_sem_correspondencia") == ["quadrada"], r
    cands = r.get("candidatos", [])
    oct_ = [c for c in cands if _OCTOGONAL in c["description"]]
    assert oct_ and oct_[0]["falta"] == ["quadrada"], cands
    assert "NÃO prova que o item não existe" in r.get("aviso", ""), r


@pytest.mark.parametrize("legenda,esperada", [
    (_LEGENDA_CONJUNTO, _CONJUNTO),
    (_LEGENDA_LE, _TOMADA_LE),
])
def test_a_linha_de_legenda_colada_acha_a_linha_certa_em_primeiro(planilha, legenda, esperada):
    r = _buscar(legenda)
    primeira = (r["items"] or r.get("candidatos") or [{}])[0]
    assert esperada in primeira.get("description", ""), r


def test_a_divergencia_4x4_da_legenda_x_4x2_da_planilha_aparece(planilha):
    """A legenda diz caixa 4x4; a IA leu 4x2. O modelo só consegue contar isso
    ao cliente se a busca disser o que FALTA na linha que bate."""
    r = _buscar(_LEGENDA_LE)
    alvo = [c for c in r.get("candidatos", []) if _TOMADA_LE in c["description"]]
    assert alvo and "4x4" in alvo[0]["falta"], r


def test_tomada_em_caixa_4x4_mostra_OS_DOIS_lados_do_que_existe(planilha):
    """A resposta honesta a "tomada em caixa 4x4" tem duas metades: as tomadas
    da planilha estão em caixa 4x2, e as caixas 4x4 são octogonais de teto. Se
    os candidatos mostrarem só uma, o modelo conta meia verdade. Por isso a
    palavra rara ("4x4", 3 linhas) pesa mais que a comum ("caixa", 16)."""
    r = _buscar("tomada caixa 4x4")
    assert r["count"] == 0, _descs(r["items"])
    cands = r.get("candidatos", [])
    # a CAIXA 4x4 em si (a 17ª linha) — na ordem da planilha ficaria atrás das
    # tomadas e fora dos 8 candidatos
    assert any(_OCTOGONAL in c["description"] for c in cands), _descs(cands)
    assert any(c["description"].startswith("Tomada") and "4x2" in c["description"]
               for c in cands), _descs(cands)


def test_tomada_de_PISO_nao_existe_e_a_busca_diz_isso(planilha):
    r = _buscar(_LEGENDA_PISO)
    assert r["count"] == 0, r["items"]
    assert "piso" in r.get("termos_sem_correspondencia", []), r


# ── Normalização ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("q,esperada", [
    ("LUMINARIA EMERGENCIA", _LUMINARIA_LE),         # sem acento, maiúscula
    ("tomadas emergência", _TOMADA_LE),              # plural
    ("interruptor paralelo 4 x 2", _CONJUNTO),       # medida com espaço
    ("2P + T 20 A", "2P+T-20A"),                     # 2P+T e amperagem soltos
    ("cx octogonal", _OCTOGONAL),                    # abreviação de caixa
    ("eletroduto rigido roscavel", "Eletroduto PVC rígido roscável Ø25mm"),  # acento no começo
    ("caixa passagem nota geral", "Caixa de passagem PVC 4x2"),    # gerais -> geral
    ("caixa octogonal embutido", _OCTOGONAL),        # embutido x embutida
    ("tomada dupla 1.20", "Tomada dupla monopolar"),  # 1.20 = 1,20m
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
    import agent
    wb = agent._open_planilha("ele01")
    antes = [r["description"][:120] for r in agent._iter_orcamento_rows(wb)
             if q.lower() in r["description"].lower()]
    wb.close()
    r = _buscar(q)
    assert antes and _descs(r["items"]) == antes, (q, antes, _descs(r["items"]))
    assert not r.get("aviso"), r


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
    assert "read_dxf_summary" not in ferramentas, ferramentas
    assert "search_items" in ferramentas, ferramentas


def test_CONTROLE_projeto_COM_DXF_mantem_a_ferramenta(monkeypatch):
    system, ferramentas = _rodar_ask(monkeypatch, {"pdf": 1, "dxf": 2, "dwg": 0})
    assert "read_dxf_summary" in ferramentas, ferramentas
    assert "NENHUM DWG" not in system, system[-700:]
    assert "2 DXF" in system, system[-700:]


def test_CONTROLE_sem_saber_os_arquivos_nao_esconde_nada_nem_afirma_CAD(monkeypatch):
    system, ferramentas = _rodar_ask(monkeypatch, None)
    assert "read_dxf_summary" in ferramentas, ferramentas
    assert "não consegui confirmar" in system, system[-700:]


def test_a_leitura_dos_tipos_devolve_o_dict_do_banco_e_None_na_falha(monkeypatch):
    import io as _io
    import json as _json
    import urllib.request
    import agent
    pedidos = []

    def _abre(req, **k):
        pedidos.append(req.full_url)
        return _io.BytesIO(_json.dumps([{"file_types": {"dwg": 0, "dxf": 0, "pdf": 1}}]).encode())

    monkeypatch.setattr(urllib.request, "urlopen", _abre)
    assert agent.tipos_de_arquivo_do_projeto("ele01") == {"dwg": 0, "dxf": 0, "pdf": 1}
    assert "job_id=eq.ele01" in pedidos[0] and "select=file_types" in pedidos[0], pedidos

    def _cai(req, **k):
        raise OSError("sem rede")

    monkeypatch.setattr(urllib.request, "urlopen", _cai)
    assert agent.tipos_de_arquivo_do_projeto("ele01") is None
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, **k: _io.BytesIO(b"[]"))
    assert agent.tipos_de_arquivo_do_projeto("ele01") is None


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
