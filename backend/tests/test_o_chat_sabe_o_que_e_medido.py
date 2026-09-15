# -*- coding: utf-8 -*-
"""O chat tem que saber o que é MEDIDO — e dizer igual à planilha.

🩸 15/09/2026, job ba869938. O cliente (orçamentista) clicou no atalho
"Resumo por disciplina" e o chat da planilha respondeu com ✓ em ~20 linhas
ESTIMADAS: "Alvenaria — ✓ 2.986,82 ml medidos do CAD", "✓ 7.314,03 m²",
"✓ 144 vagas". Só 7 das 37 linhas eram medidas. O prompt manda dizer medido ×
estimado, e a ferramenta `list_items` devolvia número, descrição, unidade e
quantidade — o modelo chutou. Precisou de e-mail de correção pro cliente.

🪤 SÃO DOIS CHATS — o do painel (`agent.py`) e o da página do projeto
(`main.py:project_chat`) — e a pergunta "é medido?" tinha QUATRO respostas
escritas à mão nos lugares que MOSTRAM o selo. O da página esquecia o
`vision_pdf` (latente: 0 linhas confirmadas de vision_pdf em 15/09): a mesma
receita divergindo. Agora esses lugares perguntam a `models.e_medido`.

🔬 A revisão de 3 lentes (15/09) derrubou dois guardas meus: o do chat da
página conferia o NOME da constante no fonte da rota (a rota podia voltar ao
laço antigo com tudo verde), e o de "cópia escrita à mão" só via cópia que
cita `vision_pdf` — exatamente as que estavam certas. O primeiro agora chama a
rota; o segundo diz o que realmente vê.

🚨 Este teste GERA a planilha de verdade e chama as ferramentas e as rotas em
cima dela: o selo nasce num arquivo e é lido em outro, e o par só existe se os
dois lados rodarem juntos.
"""
import asyncio
import io
import json
import os
import re
import sys
import types

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

openpyxl = pytest.importorskip("openpyxl")

_MAPEADA = "Revestimentos"          # cai no 1º laço da planilha
_SEM_MAPA = "Zeta Fora do Mapa"     # cai no 2º laço (disciplina não mapeada)

# descrição → (confidence, origem, disciplina, observação, selo esperado)
_CASOS = {
    "Porta contada por bloco": (
        "confirmado", "dxf_geom", _MAPEADA, "Fonte: 18 INSERTs do bloco 'porta'.", "medido"),
    "Linha antiga confirmada sem origem": (
        "confirmado", "", _MAPEADA, "Fonte: layer A-PISO.", "medido"),
    "Confirmada sem observação": (
        "confirmado", "dxf_geom", _MAPEADA, "", "medido"),
    "Piso lido na imagem do PDF": (
        "confirmado", "vision_pdf", _MAPEADA, "Fonte: leitura da prancha.", "estimado"),
    # sem "Fonte:" a coluna ORIGEM DA MEDIÇÃO cai no ramo que também decide medido
    "Bancada lida na imagem sem fonte": (
        "confirmado", "vision_pdf", _MAPEADA, "", "estimado"),
    "Alvenaria que cita outra linha": (
        "estimado", "dxf_geom", _MAPEADA,
        "Fonte: comprimento do layer AR-ALV. A porta ao lado saiu ✓ MEDIDO do CAD.", "estimado"),
    "Forro a verificar": (
        "verificar", "dxf_geom", _MAPEADA, "Fonte: texto da prancha.", "estimado"),
    "Tomada fora do mapa contada": (
        "confirmado", "dxf_geom", _SEM_MAPA, "Fonte: 12 INSERTs do bloco 'tomada'.", "medido"),
    "Luminária fora do mapa lida no PDF": (
        "confirmado", "vision_pdf", _SEM_MAPA, "Fonte: imagem da prancha.", "estimado"),
    "Eletroduto fora do mapa estimado": (
        "estimado", "", _SEM_MAPA, "Fonte: estimativa.", "estimado"),
}


def _gerar(caminho, itens):
    from models import ProjectData
    from spreadsheet import generate_spreadsheet
    generate_spreadsheet(ProjectData(name="t"), itens, caminho, typology="office")
    return caminho


@pytest.fixture
def planilha(tmp_path, monkeypatch):
    from models import BudgetItem, Confidence
    import agent
    itens = [BudgetItem(item_num=str(i), description=desc, unit="un", quantity=3.0,
                        observations=obs, confidence=Confidence(conf), origem=org,
                        discipline=disc)
             for i, (desc, (conf, org, disc, obs, _)) in enumerate(_CASOS.items(), 1)]
    caminho = _gerar(str(tmp_path / "orcamento_chat01.xlsx"), itens)
    monkeypatch.setattr(agent, "_planilha_path", lambda job_id: caminho)
    return caminho


def _planilha_grande(tmp_path, n=150):
    from models import BudgetItem, Confidence
    itens = [BudgetItem(item_num=str(i),
                        description="Serviço de teste número %03d com descrição comprida" % i,
                        unit="m²", quantity=float(i), observations="Fonte: layer de teste.",
                        confidence=Confidence.CONFIRMADO if i % 3 == 0 else Confidence.ESTIMADO,
                        origem="dxf_geom", discipline=_MAPEADA)
             for i in range(1, n + 1)]
    return _gerar(str(tmp_path / "orcamento_grande01.xlsx"), itens)


def _por_descricao(itens):
    return {i["description"]: i for i in itens}


def _linha(ws, texto):
    for r in range(1, ws.max_row + 1):
        if str(ws.cell(row=r, column=2).value or "") == texto:
            return r
    raise AssertionError("não achei a linha de %r na planilha" % texto)


# ── O chat do painel (agent.py) ────────────────────────────────────────────
def test_list_items_entrega_o_selo_de_CADA_linha(planilha):
    import agent
    r = agent.tool_list_items("chat01")
    assert "error" not in r, r
    achados = _por_descricao(r["items"])
    for desc, (_, _, _, _, esperado) in _CASOS.items():
        assert desc in achados, "a linha %r sumiu da lista do agente" % desc
        assert achados[desc].get("selo") == esperado, (
            "%r: o agente leu selo=%r e a planilha diz %r"
            % (desc, achados[desc].get("selo"), esperado))


def test_linha_da_capa_e_metadado_nem_medida_nem_estimativa(planilha):
    import agent
    capa = [i for i in agent.tool_list_items("chat01")["items"]
            if i["item_num"].startswith("0.")]
    assert capa, "a planilha de teste devia ter as linhas 0.x da capa"
    assert {i["selo"] for i in capa} == {"metadado"}, capa


def test_MEDIDO_escrito_no_meio_da_observacao_nao_vira_medido(planilha):
    """O motor escreve observação livre; só o COMEÇO dela é o selo."""
    import agent
    ws = openpyxl.load_workbook(planilha)["Orçamento"]
    obs = str(ws.cell(row=_linha(ws, "Alvenaria que cita outra linha"), column=8).value or "")
    # controle: a armadilha está armada — o texto contém o selo de medido
    assert "✓ MEDIDO do CAD" in obs and obs.startswith("⚠ ESTIMADO"), obs
    achados = _por_descricao(agent.tool_list_items("chat01")["items"])
    assert achados["Alvenaria que cita outra linha"]["selo"] == "estimado"


def test_search_e_detalhe_levam_o_selo_e_nao_outra_confianca(planilha, monkeypatch):
    import agent
    # o detalhe chama um classificador por LLM; aqui ele responde com a
    # confiança DELE (0 a 1), que não pode sair com cara de confiança da medição
    monkeypatch.setitem(sys.modules, "classifier", types.SimpleNamespace(
        classify_item=lambda d, u: {"confidence": 0.95, "familia_code": "fam_teste"}))
    hits = _por_descricao(agent.tool_search_items("chat01", "PDF")["items"])
    assert set(hits) == {"Piso lido na imagem do PDF",
                         "Luminária fora do mapa lida no PDF"}, hits
    assert {h["selo"] for h in hits.values()} == {"estimado"}, hits
    num = _por_descricao(agent.tool_list_items("chat01")["items"])[
        "Piso lido na imagem do PDF"]["item_num"]
    det = agent.tool_get_item_details("chat01", num)
    assert det.get("selo") == "estimado", det
    assert "confidence" not in det["categoria"], det["categoria"]
    assert det["categoria"].get("confianca_da_classificacao") == 0.95, det["categoria"]


def test_o_selo_que_o_chat_le_bate_com_a_COR_nos_dois_lacos(planilha):
    """Cor e texto são o MESMO veredito. O 2º laço pintava pela confiança crua
    e deixaria branca (medida) uma linha confirmada lida no PDF."""
    import agent
    ws = openpyxl.load_workbook(planilha)["Orçamento"]
    selo_por_num = {i["item_num"]: i["selo"]
                    for i in agent.tool_list_items("chat01")["items"]}
    vistos = 0
    for r in range(1, ws.max_row + 1):
        num = str(ws.cell(row=r, column=1).value or "").strip()
        if not re.match(r"^[1-9]\d*\.\d+$", num):
            continue
        laranja = str(ws.cell(row=r, column=1).fill.fgColor.rgb or "").upper().endswith("FFE1B3")
        assert laranja == (selo_por_num[num] == "estimado"), (
            "linha %s (%s): laranja=%s, selo=%s"
            % (num, ws.cell(row=r, column=2).value, laranja, selo_por_num[num]))
        vistos += 1
    assert vistos == len(_CASOS), vistos


def test_a_coluna_ORIGEM_DA_MEDICAO_segue_a_mesma_regra(planilha):
    """Sem "Fonte:", a coluna 9 decide sozinha entre "sem procedência" (linha
    medida sem fonte) e "não medido". Ela também olhava a confiança crua."""
    ws = openpyxl.load_workbook(planilha)["Orçamento"]
    medida = str(ws.cell(row=_linha(ws, "Confirmada sem observação"), column=9).value or "")
    do_pdf = str(ws.cell(row=_linha(ws, "Bancada lida na imagem sem fonte"), column=9).value or "")
    assert "sem procedência registrada" in medida, medida
    assert do_pdf.startswith("não medido"), do_pdf


def test_CONTROLE_planilha_antiga_sem_selo_nao_vira_medida(tmp_path, monkeypatch):
    """FAIL-SAFE da nº1: planilha de antes do selo (ou mexida à mão) não tem o
    prefixo — e aí nada é medido, nunca o contrário."""
    import agent
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Orçamento"
    ws.append(["ITEM", "DESCRIÇÃO", "UN", "QTDE", None, None, None, "OBSERVAÇÕES", "ORIGEM"])
    ws.append(["1.1", "Porta sem selo", "un", 18, None, None, None,
               "Fonte: 18 INSERTs do bloco 'porta'.", ""])
    caminho = str(tmp_path / "antiga.xlsx")
    wb.save(caminho)
    monkeypatch.setattr(agent, "_planilha_path", lambda job_id: caminho)
    (linha,) = agent.tool_list_items("antiga")["items"]
    assert linha["selo"] == "estimado", linha


def _rodar_agente(monkeypatch, caminho):
    """Roda `agent.ask` DE VERDADE com o modelo trocado por um roteiro: 1ª volta
    pede list_items, 2ª responde. Devolve o que a ferramenta entregou ao modelo."""
    import agent
    import llm_retry
    monkeypatch.setattr(agent, "_planilha_path", lambda job_id: caminho)
    monkeypatch.setattr(agent, "_log_conversation", lambda *a, **k: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "teste-sem-rede")
    monkeypatch.setitem(sys.modules, "anthropic",
                        types.SimpleNamespace(Anthropic=lambda **kw: object()))
    chamadas = []

    def _falso(client, **kw):
        chamadas.append(kw)
        if len(chamadas) == 1:
            pede = types.SimpleNamespace(type="tool_use", id="t1", name="list_items", input={})
            return types.SimpleNamespace(content=[pede], stop_reason="tool_use")
        fim = types.SimpleNamespace(type="text", text="resumo pronto")
        return types.SimpleNamespace(content=[fim], stop_reason="end_turn")

    monkeypatch.setattr(llm_retry, "call_with_retry", _falso)
    r = agent.ask("agente01", "Me dá um resumo dos itens da planilha por disciplina")
    assert r["answer"] == "resumo pronto", r
    assert len(chamadas) == 2, chamadas
    return chamadas[1]["messages"][-1]["content"][0]["content"]


def test_o_agente_AVISA_quando_o_resultado_da_ferramenta_e_cortado(tmp_path, monkeypatch):
    """🩸 O corte em 8.000 caracteres era calado: planilha grande, resumo de ~50
    linhas apresentado como a planilha inteira."""
    entregue = _rodar_agente(monkeypatch, _planilha_grande(tmp_path))
    assert "RESULTADO CORTADO" in entregue, entregue[-400:]


def test_CONTROLE_resultado_pequeno_vai_inteiro_e_com_selo(planilha, monkeypatch):
    entregue = _rodar_agente(monkeypatch, planilha)
    assert "RESULTADO CORTADO" not in entregue
    itens = _por_descricao(json.loads(entregue)["items"])
    assert itens["Piso lido na imagem do PDF"]["selo"] == "estimado"
    assert itens["Porta contada por bloco"]["selo"] == "medido"


def test_a_ferramenta_e_o_prompt_apontam_pro_selo():
    """Ingrediente, não prato — o prato são os testes acima. Mas o modelo só usa
    o campo que a descrição da ferramenta anuncia e o prompt manda usar."""
    import agent
    import main
    desc = {t["name"]: t["description"] for t in agent.TOOLS}
    assert "selo" in desc["list_items"] and "selo" in desc["search_items"], desc
    pronto = agent.SYSTEM_PROMPT.format(job_id="chat01")
    # 🪤 "selo" sozinho não basta: o prompt antigo dizia "observação/selo do
    # item" e mandava o modelo procurar o que a ferramenta não entregava.
    assert 'selo = "medido"' in pronto and "Ter número NÃO é ter medição" in pronto, pronto[:900]
    # a resposta errada de 15/09 continua no histórico que a tela recarrega
    assert "Nunca repita um ✓ do histórico" in pronto
    assert "RESULTADO CORTADO" in pronto
    assert "(MEDIDO) ou (estimativa)" in main.PROJECT_CHAT_SYSTEM


# ── A regra única ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("conf,origem,esperado", [
    ("confirmado", "dxf_geom", True),
    ("confirmado", "", True),
    ("CONFIRMADO", None, True),
    ("confirmado", "vision_pdf", False),
    ("confirmado", "VISION_PDF", False),
    ("confirmado", " vision_pdf ", False),
    ("estimado", "dxf_geom", False),
    ("verificar", "", False),
    (None, "", False),
    ("", "dxf_geom", False),
])
def test_a_regra_unica(conf, origem, esperado):
    from models import Confidence, e_medido
    assert e_medido(conf, origem) is esperado
    if conf and conf.lower() in ("confirmado", "estimado", "verificar"):
        # 🪤 `str(Confidence.CONFIRMADO)` dá "Confidence.CONFIRMADO": o enum e o
        # texto cru do banco têm que dar o mesmo veredito.
        assert e_medido(Confidence(conf.lower()), origem) is esperado


# ── O chat da página do projeto (a ROTA, não um pedaço dela) ───────────────
def _rodar_chat_da_pagina(monkeypatch, itens):
    """Chama `main.project_chat` com o banco e o modelo trocados por dublês.
    Devolve (resposta, system que chegou ao modelo, URLs consultadas)."""
    import urllib.request
    import llm_retry
    import main
    urls = []

    class _Resp:
        def __init__(self, dados):
            self._b = json.dumps(dados).encode("utf-8")

        def read(self):
            return self._b

    def _abrir(req, timeout=None):
        url = getattr(req, "full_url", str(req))
        urls.append(url)
        if "/project_items?" in url:
            return _Resp(itens)
        return _Resp([{"total_area": None, "typology": "office"}])

    capturado = {}

    def _falso(client, **kw):
        capturado.update(kw)
        return types.SimpleNamespace(content=[types.SimpleNamespace(text="ok")],
                                     stop_reason="end_turn")

    class _Pedido:
        async def json(self):
            return {"messages": [{"role": "user", "content": "resumo"}]}

    monkeypatch.setattr(urllib.request, "urlopen", _abrir)
    monkeypatch.setattr(main, "_require_project_owner", lambda request, job_id: None)
    monkeypatch.setattr(main, "_PROJECT_CHAT_HITS", {})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "teste-sem-rede")
    monkeypatch.setitem(sys.modules, "anthropic",
                        types.SimpleNamespace(Anthropic=lambda **kw: object()))
    monkeypatch.setattr(llm_retry, "call_with_retry", _falso)
    resp = asyncio.run(main.project_chat("pagina01", _Pedido()))
    return resp, capturado.get("system", ""), urls


_ITENS_DA_PAGINA = [
    {"description": "Porta contada", "unit": "un", "quantity": 18,
     "confidence": "confirmado", "origem": "dxf_geom", "discipline": "Portas"},
    {"description": "Piso lido no PDF", "unit": "m²", "quantity": 90,
     "confidence": "confirmado", "origem": "vision_pdf", "discipline": "Pisos"},
    {"description": "Vaga estimada", "unit": "un", "quantity": 144,
     "confidence": "estimado", "origem": "", "discipline": "Complementares"},
]


def test_o_chat_da_pagina_marca_pela_MESMA_regra(monkeypatch):
    resp, system, _ = _rodar_chat_da_pagina(monkeypatch, _ITENS_DA_PAGINA)
    assert resp.get("reply") == "ok", resp
    assert "Porta contada: 18 un (MEDIDO)" in system, system[-800:]
    assert "Piso lido no PDF: 90 m² (estimativa)" in system, system[-800:]
    assert "Vaga estimada: 144 un (estimativa)" in system, system[-800:]


def test_o_chat_da_pagina_BUSCA_a_origem_que_a_regra_le(monkeypatch):
    """🪤 Sem `origem` no SELECT a regra recebe vazio e volta a chamar de MEDIDO
    o que veio do PDF — calada."""
    _, _, urls = _rodar_chat_da_pagina(monkeypatch, _ITENS_DA_PAGINA)
    (url_itens,) = [u for u in urls if "/project_items?" in u]
    campos = re.search(r"select=([^&]+)", url_itens).group(1).split(",")
    assert "origem" in campos and "confidence" in campos, url_itens


def test_o_teto_do_agente_e_inclusivo_na_borda():
    """Exatamente no teto vai inteiro; um caractere a mais, corta e avisa."""
    import agent
    teto = agent._TETO_RESULTADO_FERRAMENTA
    base = len(json.dumps({"a": ""}, ensure_ascii=False))
    cabe = {"a": "x" * (teto - base)}
    assert len(json.dumps(cabe, ensure_ascii=False)) == teto
    inteiro = agent._conteudo_da_ferramenta(cabe)
    assert "RESULTADO CORTADO" not in inteiro and json.loads(inteiro) == cabe
    passa = {"a": "x" * (teto - base + 1)}
    assert agent._conteudo_da_ferramenta(passa).rstrip().endswith("restante.]")


def test_o_contexto_do_chat_da_pagina_nao_corta_linha_no_meio(monkeypatch):
    """O `[:9000]` cortava a última linha antes da marca: número sem selo."""
    itens = [{"description": "Item longo de teste número %03d com descrição comprida" % i,
              "unit": "m²", "quantity": i, "confidence": "estimado", "origem": "",
              "discipline": "Disciplina %d" % (i % 8)} for i in range(320)]
    _, system, _ = _rodar_chat_da_pagina(monkeypatch, itens)
    dados = system.split("DADOS DO PROJETO:", 1)[1]
    aviso = re.search(r"\(lista cortada por tamanho: (\d+) item", dados)
    assert aviso, dados[-300:]
    linhas_de_item = [l for l in dados.splitlines() if l.lstrip().startswith("- ")]
    assert linhas_de_item, dados[:300]
    for l in linhas_de_item:
        assert l.rstrip().endswith(("(MEDIDO)", "(estimativa)")), "linha cortada no meio: %r" % l
    # 8 disciplinas × 40 = 320 itens cabem no teto por disciplina: o que não
    # apareceu tem que estar no número do aviso, não sumir calado
    assert int(aviso.group(1)) == 320 - len(linhas_de_item), (aviso.group(0), len(linhas_de_item))


# ── O e-mail ───────────────────────────────────────────────────────────────
def test_o_placar_do_email_conta_pela_mesma_regra():
    import main
    from models import BudgetItem, Confidence, ProjectData
    itens = [
        BudgetItem(item_num="1", description="a", unit="un", quantity=1,
                   confidence=Confidence.CONFIRMADO, origem="dxf_geom"),
        BudgetItem(item_num="2", description="b", unit="un", quantity=1,
                   confidence=Confidence.CONFIRMADO, origem="vision_pdf"),
        BudgetItem(item_num="3", description="c", unit="un", quantity=1,
                   confidence=Confidence.ESTIMADO),
    ]
    html = main._build_reading_diagnostic(itens, 1, 1, "arquitetura", ProjectData(name="t"))
    assert "1 medido(s)" in html and "2 pra você confirmar" in html, html[:500]


# ── Cópia que cita vision_pdf ──────────────────────────────────────────────
# 🪤 O QUE ESTE GUARDA NÃO VÊ (a revisão provou): a cópia que ESQUECE o
# vision_pdf — `confidence == "confirmado"` e pronto — não cita a palavra, e
# essa é justamente a que diverge. Os lugares que MOSTRAM o selo (planilha,
# os dois chats, o e-mail) estão amarrados pelos testes de comportamento acima.
# As cópias latentes que sobraram (financeiro, memorial, cronograma de
# produtividade, contagens do motor e o front) estão listadas na fila de 15/09.
_RX_CITA_VISION = re.compile(r"""(?:!=|==)\s*["']vision_pdf["']""")


def _copias_que_citam_vision_pdf(diretorio):
    achadas = []
    for nome in sorted(os.listdir(diretorio)):
        if not nome.endswith(".py") or nome == "models.py":
            continue
        txt = io.open(os.path.join(diretorio, nome), encoding="utf-8").read()
        achadas += ["%s:%d" % (nome, txt.count("\n", 0, m.start()) + 1)
                    for m in _RX_CITA_VISION.finditer(txt)]
    return achadas


def test_nenhuma_copia_da_regra_que_cita_vision_pdf_fora_de_models():
    copias = _copias_que_citam_vision_pdf(_BACKEND)
    assert not copias, (
        "a regra 'é medido?' foi reescrita à mão em %s — use models.e_medido" % copias)


def test_CONTROLE_o_varredor_acha_a_copia_num_arquivo_de_verdade(tmp_path):
    (tmp_path / "models.py").write_text('x = o != "vision_pdf"\n', encoding="utf-8")
    (tmp_path / "limpo.py").write_text('origem="vision_pdf"  # atribuição, não regra\n',
                                       encoding="utf-8")
    (tmp_path / "mutante.py").write_text(
        "a = 1\nmedido = c == 'confirmado' and getattr(it, 'origem', '') != 'vision_pdf'\n",
        encoding="utf-8")
    assert _copias_que_citam_vision_pdf(str(tmp_path)) == ["mutante.py:2"]
