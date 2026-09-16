# -*- coding: utf-8 -*-
"""O chat do projeto não pode negar item que está na planilha do cliente.

🩸 16/09/2026. O contexto do chat da página corta em 40 itens POR DISCIPLINA, e
o corte era calado: o cabeçalho dizia "[Elétrica] (314 itens)" e só 40 linhas
iam junto. Como a regra 5 do prompt manda dizer "não consta" quando o dado não
está na lista, o assistente **negava item que existe** — na planilha do próprio
cliente, que ele tem aberta na outra aba.

📏 Medido hoje na base: **22 de 170 jobs** têm alguma disciplina acima de 40
itens; **1.488 linhas** ficavam fora do que o modelo enxerga; a maior disciplina
tem 314 itens. E a busca de itens parava em 400 por job (2 jobs passam disso).

Duas mudanças, as duas pequenas:
  · o corte APARECE, dizendo que os itens de fora EXISTEM (e o prompt ganhou a
    exceção correspondente na regra 5);
  · a seleção olha a PERGUNTA do cliente: o item que ele citou vem primeiro,
    mesmo que seja o 300º da disciplina.

🪤 O que estes guardas NÃO provam: que o modelo obedece. Isso é texto de prompt,
e prompt não se testa com asserção — o que se testa é o CONTEXTO que ele recebe.
"""
import asyncio
import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


def _item(desc, disc="Elétrica", qty=1, unit="un", conf="estimado", origem="ia_texto"):
    return {"description": desc, "discipline": disc, "quantity": qty, "unit": unit,
            "confidence": conf, "origem": origem}


def _eletrica(n=100):
    return [_item("Tomada 2P+T tipo T%d" % i) for i in range(n)]


# ── o corte passa a aparecer ───────────────────────────────────────────────
def test_o_corte_por_disciplina_APARECE_e_diz_que_os_itens_existem():
    linhas = main._linhas_de_itens_do_chat(_eletrica(100))
    _texto = "\n".join(linhas)
    assert "(100 itens)" in _texto, _texto[:200]
    assert sum(1 for l in linhas if l.lstrip().startswith("- ")) == 40, _texto[:400]
    assert "+60 item(ns) desta disciplina não couberam" in _texto, _texto[-400:]
    assert "EXISTEM na planilha" in _texto, _texto[-400:]
    assert "NÃO diga que não constam" in _texto, _texto[-400:]


def test_CONTROLE_disciplina_pequena_nao_ganha_aviso_de_corte():
    _texto = "\n".join(main._linhas_de_itens_do_chat(_eletrica(12)))
    assert "não couberam" not in _texto, _texto
    assert _texto.count("  - ") == 12, _texto


def test_CONTROLE_o_corte_conta_por_DISCIPLINA_e_nao_no_total():
    itens = _eletrica(45) + [_item("Ponto de água fria", disc="Hidráulica") for _ in range(45)]
    _texto = "\n".join(main._linhas_de_itens_do_chat(itens))
    assert _texto.count("+5 item(ns)") == 2, _texto[-600:]


# ── a pergunta do cliente ordena quem entra ────────────────────────────────
def test_o_item_que_o_cliente_CITOU_entra_mesmo_sendo_o_ultimo_da_lista():
    itens = _eletrica(80) + [_item("Eletroduto PVC corrugado 3/4\" — alimentação do quadro",
                                   qty=120, unit="m")]
    sem = "\n".join(main._linhas_de_itens_do_chat(itens))
    assert "Eletroduto" not in sem, "o arranjo só prova algo se ele ficasse de fora: %r" % sem[-300:]

    com = "\n".join(main._linhas_de_itens_do_chat(
        itens, pergunta="quantos metros de eletroduto tem no projeto?"))
    assert "Eletroduto PVC corrugado" in com, com[:600]
    assert "+41 item(ns)" in com, com[-300:]


def test_CONTROLE_pergunta_generica_nao_reordena_nada():
    """'quantos itens tem a planilha?' não pode bagunçar a ordem da planilha."""
    itens = _eletrica(80)
    igual = main._linhas_de_itens_do_chat(itens)
    com = main._linhas_de_itens_do_chat(itens, pergunta="quantos itens tem essa planilha?")
    assert igual == com, "palavra genérica não pode reordenar"


def test_CONTROLE_pergunta_sem_palavra_util_nao_quebra():
    for p in ("", None, "??", "oi", "e aí", "1 2 3"):
        assert main._linhas_de_itens_do_chat(_eletrica(50), pergunta=p)


def test_as_palavras_da_pergunta_ignoram_as_genericas():
    assert main._palavras_da_pergunta("quantos metros de eletroduto?") == ["metros", "eletroduto"]
    assert main._palavras_da_pergunta("qual o total de itens da planilha?") == []
    assert len(main._palavras_da_pergunta("a " * 400)) <= 12


# ── a marca MEDIDO/estimativa continua sendo a mesma regra da planilha ─────
def test_CONTROLE_a_marca_do_selo_nao_mudou():
    linhas = main._linhas_de_itens_do_chat([
        _item("Piso medido", conf="confirmado", origem="dxf_geom"),
        _item("Piso lido de PDF", conf="confirmado", origem="vision_pdf"),
        _item("Piso estimado", conf="estimado", origem="ia_texto")])
    _texto = "\n".join(linhas)
    assert "Piso medido: 1 un (MEDIDO)" in _texto, _texto
    assert "Piso lido de PDF: 1 un (estimativa)" in _texto, _texto
    assert "Piso estimado: 1 un (estimativa)" in _texto, _texto


# ── a ROTA leva a pergunta até a seleção ──────────────────────────────────
def _rodar_a_rota(monkeypatch, itens, pergunta):
    """Chama `main.project_chat` de verdade, com banco e modelo dublês, e
    devolve o system que chegou ao modelo mais as URLs consultadas."""
    import urllib.request

    import llm_retry

    class _Resp:
        def __init__(self, dados):
            self._b = json.dumps(dados).encode("utf-8")

        def read(self):
            return self._b

    urls = []

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
            # 🪤 a conversa tem DUAS perguntas: a que vale é a última. Sem a
            # primeira (genérica), a sabotagem "pega a primeira" sobrevive.
            return {"messages": [{"role": "user", "content": "quantos itens tem a planilha?"},
                                 {"role": "assistant", "content": "tem bastante"},
                                 {"role": "user", "content": pergunta}]}

    monkeypatch.setattr(urllib.request, "urlopen", _abrir)
    monkeypatch.setattr(main, "_require_project_owner", lambda request, job_id: None)
    monkeypatch.setattr(main, "_PROJECT_CHAT_HITS", {})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "teste-sem-rede")
    monkeypatch.setitem(sys.modules, "anthropic",
                        types.SimpleNamespace(Anthropic=lambda **kw: object()))
    monkeypatch.setattr(llm_retry, "call_with_retry", _falso)
    asyncio.run(main.project_chat("pagina01", _Pedido()))
    return capturado.get("system", ""), urls


def test_a_ROTA_usa_a_pergunta_do_cliente_pra_escolher_os_itens(monkeypatch):
    """🚨 Guarda de CALL SITE: a seleção pode estar certa e a rota não passar a
    pergunta — foi assim que o guarda do selo falhou em 15/09."""
    itens = ([_item("Tomada 2P+T tipo T%d" % i) for i in range(80)]
             + [_item("Eletroduto PVC corrugado 3/4\"", qty=120, unit="m")])
    system, urls = _rodar_a_rota(monkeypatch, itens, "quantos metros de eletroduto?")
    assert "Eletroduto PVC corrugado" in system, system[-900:]
    assert "+41 item(ns)" in system, system[-500:]
    assert any("limit=1000" in u for u in urls), urls


def test_a_ROTA_pega_a_ULTIMA_pergunta_e_nao_a_primeira(monkeypatch):
    itens = ([_item("Tomada 2P+T tipo T%d" % i) for i in range(80)]
             + [_item("Eletroduto PVC corrugado 3/4\"", qty=120, unit="m")])
    system, _ = _rodar_a_rota(monkeypatch, itens, "e o eletroduto, quantos metros?")
    assert "Eletroduto PVC corrugado" in system, system[-900:]


def test_o_prompt_TEM_a_excecao_da_regra_5():
    """🪤 Guarda de COPY, não de comportamento: prova que a exceção está no
    texto que vai pro modelo. Se alguém reescrever a regra 5 e esquecer dela, o
    chat volta a dizer 'não consta' pra item que existe."""
    assert "não couberam" in main.PROJECT_CHAT_SYSTEM, "a regra 5 perdeu a exceção do corte"
    assert "NUNCA responda \"não consta\"" in main.PROJECT_CHAT_SYSTEM
