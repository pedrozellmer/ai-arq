# -*- coding: utf-8 -*-
"""Página que não é prancha técnica não vira levantamento.

🩸 22/09/2026 — job 1d0751b8 (cliente de 1 dia, primeiro envio). Um caderno de
APRESENTAÇÃO de 35 páginas: 2 pranchas técnicas (uma planta baixa e um
corte/elevação) e 33 páginas de render, fotografia, moodboard, capa e brochura
de conceito. A planilha saiu com **537 linhas**, 316 zeradas, 0 medidas.
**91,8% delas (493) nasceram das páginas que não são prancha**: a fotografia de
uma loja JÁ CONSTRUÍDA devolveu "Demolição e remoção de revestimentos
existentes — 8 vb", outra foto devolveu "Mobilização e instalação de canteiro
de obras — 3 vb", e a página de brochura devolveu a planilha inteira de uma
loja de ~80 m² que ninguém desenhou.

🔑 A IA não escondeu nada: em 18 das 35 páginas ela ESCREVEU, em prosa, que não
havia prancha técnica ("Impossível gerar quantitativos sem prancha técnica").
Quem ignorou fomos nós — o PROMPT_ESTRUTURA é o único que oferece a saída
`"items": []`, e o de arquitetura ainda empurrava pro outro lado.

O conserto tem três partes, e este arquivo guarda as três:
  (a) todo prompt que não é de estrutura passa a oferecer `"items": []` e a
      pedir o que a página É num CAMPO (`tipo_de_pagina`);
  (b) o motor usa o campo: linha nascida de render/foto/moodboard/capa vira
      ESCOPO — o serviço fica, o número some, a observação diz de que página
      veio;
  (c) o cliente lê quantas páginas do envio dele eram prancha técnica.

📊 ALCANCE, E O QUE ELE É (22/09, 90 dias, sem is_eval, testemunha `now()`):
13.176 linhas em 168 jobs. Pelo `ref_sheet` que a própria leitura escreve, 3
jobs têm linha nascida de página de render/foto/capa — 1d0751b8 (400 linhas,
74,5% da entrega), c378477f (47 de 500) e aec7cac2 (1 de 1.044). É POUCO JOB e
MUITA LINHA: quando acontece, decide a planilha inteira.
🪤 Isso é PROXY, não a medida desta régua: `ref_sheet` é texto livre, e o campo
`tipo_de_pagina` que a régua lê não existe em leitura nenhuma do acervo — ele
começa a ser pedido neste commit. O proxy SUBCONTA: na única entrega conferida
linha a linha (1d0751b8) ele acha 400 das 493 (91,8%). O tamanho de verdade sai
do log `motor:pagina-sem-prancha` em 2-4 semanas.

🚫 POR QUE ESCOPO E NÃO APAGAR A LINHA — medido nos 4 casos de hoje:
  · 1d0751b8: apagar deixaria a entrega com 44 linhas (as 2 páginas técnicas),
    e essas 44 também saíram zeradas — 35/35 páginas sem escala. O cliente
    trocaria 537 linhas erradas por uma planilha praticamente vazia;
  · c378477f (19/09): 47 das 500 linhas vêm de página de foto/capa num envio
    que ENTREGOU. Barrar por conta própria come entrega de verdade — é o
    "o número que eu medi pode ser o meu próprio corte";
  · ee801b82/f8d8e6d8, 844603fb e 95bab8ba (os outros 3 casos de hoje):
    ZERO linha PELO PROXY. 🪤 esse zero não prova dano colateral nenhum: em
    22/09 nenhuma linha do banco PODE estar classificada, porque o
    classificador nasce aqui — é a tautologia irmã do "0 de 117" de 18/09.

🧪 Os guardas EXECUTAM: o prompt sai de `analyze_sheet` de verdade (com um
cliente falso no lugar da IA) e a fiação do motor é recortada do `main.py` pela
árvore sintática e executada (tests/_executa.py) — nunca `assert "..." in src`.

🔁 22/09/2026, DEPOIS DA REVISÃO — quatro coisas a mais, guardadas aqui:
  · o recado não pede o DWG a quem mandou o DWG no mesmo envio (18 dos 167
    jobs entregues em 90 dias, 10,8%, trazem PDF e DWG/DXF juntos), e a
    primeira frase diz que o denominador é só das páginas dos PDFs;
  · o número de linhas do recado é o da planilha ENTREGUE, contado depois da
    consolidação — 19,2% dos itens montados somem depois do laço de páginas;
  · a página cuja LEITURA FALHOU sai do censo: "não classificada" é diferente
    de "não foi lida";
  · a página que voltou sem item E sem se classificar é CONTADA no log, e só —
    agir sobre "não sei" é o que esta régua inteira se proíbe de fazer.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analyzer  # noqa: E402
import engine_rules as R  # noqa: E402
from models import SheetType  # noqa: E402

from _executa import roda  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
#  (a) O PROMPT OFERECE A SAÍDA HONESTA E PEDE O CAMPO
# ══════════════════════════════════════════════════════════════════════════
class _Sheet:
    def __init__(self, sheet_type=SheetType.ARQUITETURA, nome="prancha-A.pdf"):
        self.text_content = ""
        self.crops = []
        self.sheet_type = sheet_type
        self.filename = nome


class _Resp:
    stop_reason = "end_turn"

    def __init__(self, texto):
        class _C:
            pass
        _c = _C()
        _c.text = texto
        self.content = [_c]


_COM_ITEM = ('ok\n```json\n{"tipo_de_pagina": "planta", "items": [{"item_num": '
             '"1", "description": "Piso vinílico", "unit": "m2", '
             '"quantity": 12, "confidence": "estimado"}]}\n```')


def _chamadas(monkeypatch, sheet, resposta=_COM_ITEM, **kw):
    """Roda `analyze_sheet` de verdade e devolve o que ela mandou pra IA."""
    capt = []

    def _fake_stream(*a, **k):
        capt.append(k)
        return _Resp(resposta)
    monkeypatch.setattr(analyzer, "call_with_retry_stream", _fake_stream)
    out = analyzer.analyze_sheet(None, sheet, **kw)
    assert capt, "analyze_sheet não chegou a chamar o modelo"
    return capt, out


def _prompt(chamada):
    blocos = chamada["messages"][0]["content"]
    return [b["text"] for b in blocos if b.get("type") == "text"][-1]


#: Tipos que a tela oferece — todos passam pelo prompt de arquitetura & cia.
_TIPOS_NAO_ESTRUTURAIS = [t for t in SheetType if t != SheetType.ESTRUTURA]


@pytest.mark.parametrize("tipo", _TIPOS_NAO_ESTRUTURAIS)
def test_todo_prompt_que_nao_e_de_estrutura_oferece_items_vazio(monkeypatch, tipo):
    """🩸 Era só o PROMPT_ESTRUTURA que dizia "devolva items: []". A página de
    render lia um prompt que só sabia pedir item."""
    ch, _ = _chamadas(monkeypatch, _Sheet(tipo), is_structural=False)
    p = _prompt(ch[0])
    assert '"items": []' in p, (
        "o prompt do tipo %s não oferece a saída vazia — é o defeito de "
        "1d0751b8" % tipo.value)
    assert "não é prancha técnica" in p.lower()


@pytest.mark.parametrize("tipo", _TIPOS_NAO_ESTRUTURAIS)
def test_todo_prompt_pede_o_tipo_de_pagina_com_as_palavras_fechadas(monkeypatch, tipo):
    ch, _ = _chamadas(monkeypatch, _Sheet(tipo), is_structural=False)
    p = _prompt(ch[0])
    assert '"tipo_de_pagina"' in p
    for palavra in R.PAGINA_TECNICA + R.PAGINA_SEM_PRANCHA:
        assert '"%s"' % palavra in p, (
            "o prompt do tipo %s não oferece o valor %r — a IA não tem como "
            "responder o que o motor lê" % (tipo.value, palavra))


def test_a_secao_vai_no_FIM_do_prompt(monkeypatch):
    """Vale acima das regras de contagem de cada prompt ("se viu 1 ocorrência
    → vira item"), e pra isso precisa ser a última coisa lida."""
    ch, _ = _chamadas(monkeypatch, _Sheet(SheetType.ARQUITETURA))
    assert _prompt(ch[0]).endswith(analyzer.SAIDA_DE_PAGINA_SEM_PRANCHA)


def test_o_prompt_proibe_estimar_de_render_e_de_foto(monkeypatch):
    ch, _ = _chamadas(monkeypatch, _Sheet(SheetType.ARQUITETURA))
    p = _prompt(ch[0])
    assert "NÃO estime quantidade a partir de render" in p
    assert "demolição" in p.lower() and "canteiro" in p.lower(), (
        "as duas linhas que a fotografia de outra loja gerou têm que estar "
        "nomeadas no prompt")


def test_o_campo_da_leitura_chega_inteiro_no_resultado(monkeypatch):
    """Sem isto o conserto (b) não tem o que ler: o campo tem que atravessar o
    parser e o normalizador."""
    _, out = _chamadas(monkeypatch, _Sheet(SheetType.ARQUITETURA))
    assert out.get("tipo_de_pagina") == "planta"
    # e com a resposta honesta de uma página de render (items vazio)
    vazio = ('não há prancha técnica aqui\n```json\n{"tipo_de_pagina": '
             '"render", "items": [], "project_data": {"warnings": ["render"]}}\n```')
    _, out2 = _chamadas(monkeypatch, _Sheet(SheetType.ARQUITETURA),
                        resposta=vazio)
    assert out2.get("items") == [] and out2.get("tipo_de_pagina") == "render"


# ── 🧪 CONTROLE POSITIVO: estrutura não muda um byte ──────────────────────
def test_CONTROLE_o_prompt_de_estrutura_fica_exatamente_como_estava(monkeypatch):
    """Se a seção nova vazasse pra estrutura, este reprova — e ele prova que a
    marca procurada acima existe de verdade (guarda que não enxerga nada
    passaria verde nos dois lados)."""
    ch, _ = _chamadas(monkeypatch, _Sheet(SheetType.ARQUITETURA),
                      is_structural=True)
    p = _prompt(ch[0])
    assert p == analyzer.PROMPT_ESTRUTURA
    assert '"tipo_de_pagina"' not in p
    assert analyzer.SAIDA_DE_PAGINA_SEM_PRANCHA not in p


def test_CONTROLE_o_prompt_do_tipo_continua_inteiro_antes_da_secao(monkeypatch):
    ch, _ = _chamadas(monkeypatch, _Sheet(SheetType.ARQUITETURA),
                      typology="office")
    p = _prompt(ch[0])
    assert analyzer.PROMPT_ARQUITETURA in p
    assert "TIPOLOGIA DO PROJETO: ESCRITÓRIO CORPORATIVO" in p
    assert "## PERSIANAS" in p


# ══════════════════════════════════════════════════════════════════════════
#  (b) A RÉGUA: render/foto/moodboard/capa viram ESCOPO
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("bruto,esperado", [
    ("planta", "planta"), ("Planta Baixa Geral", "planta"), ("PLANTA", "planta"),
    ("corte", "corte"), ("elevação", "corte"), ("Corte/Elevação", "corte"),
    ("detalhe", "detalhe"), ("legenda", "legenda"), ("quadro", "legenda"),
    ("render", "render"), ("Render conceitual", "render"),
    ("perspectiva 3D", "render"), ("renderização", "render"),
    ("foto", "foto"), ("Fotografia de referência", "foto"),
    ("moodboard", "moodboard"), ("amostra de materiais", "moodboard"),
    ("capa", "capa"), ("índice", "capa"), ("brochura", "capa"),
    ("outro", ""), ("", ""), (None, ""), ("sei lá", ""),
])
def test_o_campo_da_ia_vira_um_valor_conhecido(bruto, esperado):
    assert R.tipo_de_pagina(bruto) == esperado


def test_quem_nao_disse_nao_e_acusado():
    """🪤 Falta de estado NÃO é neutra: o default do e-mail de falha já acusou
    cliente inocente (19/09). Aqui o silêncio devolve None, e None não mexe."""
    for mudo in (None, "", "outro", "qualquer coisa", 7, [] ):
        assert R.pagina_e_prancha_tecnica(mudo) is None, mudo
        q, o, z = R.escopo_de_pagina_sem_prancha(8, "obs original", mudo)
        assert (q, o, z) == (8, "obs original", False), mudo


def test_a_foto_de_outra_loja_nao_entrega_demolicao_com_numero():
    """🩸 A linha do caso: "Demolição e remoção de revestimentos existentes",
    8 vb, lida de uma FOTOGRAFIA de uma loja já construída."""
    q, obs, zerou = R.escopo_de_pagina_sem_prancha(
        8, "Contagem visual da fotografia", "foto")
    assert q == 0 and zerou is True
    assert obs.startswith(R.MARCA_DE_ESCOPO)
    assert "fotografia" in obs and "não é prancha técnica" in obs
    assert "Contagem visual da fotografia" in obs, (
        "a observação da IA não pode ser jogada fora — o cliente perde a "
        "procedência do número que sumiu")


@pytest.mark.parametrize("tipo", list(R.PAGINA_SEM_PRANCHA))
def test_toda_pagina_de_apresentacao_zera_a_quantidade(tipo):
    q, obs, _ = R.escopo_de_pagina_sem_prancha(153, "", tipo)
    assert q == 0
    assert R.MARCA_DE_ESCOPO in obs and "em branco" in obs


@pytest.mark.parametrize("tipo", list(R.PAGINA_TECNICA))
def test_CONTROLE_prancha_tecnica_sai_intacta(tipo):
    """A régua tem que REPROVAR o render e APROVAR a planta. Sem este, um
    `return quantidade, obs, False` fixo passaria verde nos testes de cima."""
    assert R.pagina_e_prancha_tecnica(tipo) is True
    assert R.escopo_de_pagina_sem_prancha(30, "medido", tipo) == (30, "medido", False)


def test_rodar_duas_vezes_nao_empilha_a_marca():
    """A retomada relê o mesmo item do checkpoint."""
    q1, o1, _ = R.escopo_de_pagina_sem_prancha(4, "obs", "render")
    q2, o2, z2 = R.escopo_de_pagina_sem_prancha(q1, o1, "render")
    assert (q2, o2) == (0, o1) and z2 is False
    assert o2.count(R.MARCA_DE_ESCOPO) == 1


def test_quantidade_que_ja_era_zero_ganha_a_explicacao_e_nao_conta_como_zerada():
    q, obs, zerou = R.escopo_de_pagina_sem_prancha(0, "", "capa")
    assert q == 0 and zerou is False and R.MARCA_DE_ESCOPO in obs


def test_quantidade_ilegivel_nao_derruba_a_regua():
    q, obs, zerou = R.escopo_de_pagina_sem_prancha("mais ou menos", "", "render")
    assert q == 0 and zerou is False and R.MARCA_DE_ESCOPO in obs


# ══════════════════════════════════════════════════════════════════════════
#  (b) A FIAÇÃO — o código REAL do process_job, recortado e executado
# ══════════════════════════════════════════════════════════════════════════
#: Os marcadores dos statements reais que decidem a linha, na ordem em que o
#: `process_job` os executa.
_MARCA_IMPORT = "escopo_de_pagina_sem_prancha as _escopo_pg"
_MARCA_TIPO = '_tipo_pg = result.get("tipo_de_pagina")'
_MARCA_VEREDITO = "_pg_e_escopo = (_pg_tecnica("
_MARCA_REGUA = "_escopo_pg(qty, obs_raw, _tipo_pg)"
_MARCA_CONTA = "_n_escopo += 1"


def _ns_do_item(tipo_de_pagina, qty, obs=""):
    """Executa os statements REAIS do process_job que decidem a linha."""
    ns = {"result": {"tipo_de_pagina": tipo_de_pagina},
          "qty": qty, "obs_raw": obs, "_n_escopo": 0, "_n_escopo_zerado": 0}
    roda("process_job", _MARCA_IMPORT, ns)
    roda("process_job", _MARCA_TIPO, ns)
    roda("process_job", _MARCA_VEREDITO, ns)
    roda("process_job", _MARCA_REGUA, ns)
    roda("process_job", _MARCA_CONTA, ns, tamanho=1)
    return ns


def test_a_fiacao_zera_a_linha_da_foto_no_motor_de_verdade():
    ns = _ns_do_item("foto", 8, "Contagem visual")
    assert ns["qty"] == 0
    assert ns["obs_raw"].startswith(R.MARCA_DE_ESCOPO)
    assert ns["_n_escopo"] == 1 and ns["_n_escopo_zerado"] == 1


def test_CONTROLE_a_fiacao_nao_toca_na_linha_da_planta():
    ns = _ns_do_item("planta", 30, "medido")
    assert (ns["qty"], ns["obs_raw"]) == (30, "medido")
    assert ns["_n_escopo"] == 0 and ns["_n_escopo_zerado"] == 0


def test_CONTROLE_a_fiacao_nao_toca_em_quem_nao_declarou():
    ns = _ns_do_item(None, 30, "obs")
    assert (ns["qty"], ns["obs_raw"], ns["_n_escopo"]) == (30, "obs", 0)


#: Marcadores dos statements reais do censo, no fim do laço de páginas.
_MARCA_CENSO = '_tipos_de_pagina.append(str(result.get("tipo_de_pagina")'
_MARCA_SEM_TIPO = "_n_sem_item_sem_tipo += 1"


def _ns_censo(result):
    """Executa os statements REAIS do fim do laço de páginas do process_job."""
    ns = {"result": result, "_tipos_de_pagina": [],
          "_pranchas_nao_tecnicas": [], "_disp": "pagina 17",
          "_n_sem_item_sem_tipo": 0}
    roda("process_job", _MARCA_IMPORT, ns)      # liga _pg_tecnica de verdade
    roda("process_job", _MARCA_TIPO, ns)
    roda("process_job", _MARCA_VEREDITO, ns)
    roda("process_job", _MARCA_CENSO, ns, tamanho=1)
    roda("process_job", _MARCA_SEM_TIPO, ns, tamanho=1)
    roda("process_job", "_pranchas_nao_tecnicas.append(_disp)", ns, tamanho=1)
    return ns


def test_o_censo_recolhe_o_veredito_de_cada_pagina():
    ns = _ns_censo({"tipo_de_pagina": "render"})
    assert ns["_tipos_de_pagina"] == ["render"]
    assert ns["_pranchas_nao_tecnicas"] == ["pagina 17"]


def test_a_pagina_cuja_LEITURA_FALHOU_nao_entra_no_censo():
    """🩸 22/09 (revisão) — a página que a IA nunca respondeu não tem
    `continue` neste laço: ela caía no censo como "" e virava, pro cliente,
    "(Outras N página(s) a leitura não soube classificar.)". São 11 páginas em
    3 jobs em 90 dias (error_log stage='pdf:analyze'), e o comentário do
    próprio conserto já dizia a regra que o código não cumpria."""
    ns = _ns_censo({"items": [], "error": "[status=529] overloaded"})
    assert ns["_tipos_de_pagina"] == [], (
        '"não classificada" tem que continuar diferente de "não foi lida"')


def test_CONTROLE_a_pagina_LIDA_que_nao_se_classificou_entra_no_censo():
    """O controle do controle: é ela que faz a frase das não classificadas —
    se o filtro de cima comesse as duas, o denominador voltaria a mentir."""
    ns = _ns_censo({"tipo_de_pagina": "outro", "items": []})
    assert ns["_tipos_de_pagina"] == ["outro"], (
        "o censo guarda o BRUTO da leitura; quem normaliza e censo_de_paginas")
    assert R.censo_de_paginas(ns["_tipos_de_pagina"]) == {
        "tecnicas": 0, "sem_prancha": 0, "nao_disse": 1, "total": 1,
        "por_tipo": {}}


def test_conta_a_pagina_que_voltou_sem_item_e_sem_dizer_o_que_e():
    """🪤 22/09 (revisão) — o prompt novo oferece `"items": []` a TODO prompt
    não estrutural e oferece "outro" a quem não souber classificar. A página
    que responde a lista vazia sem se classificar escapa da poda e chega ao
    cliente pelo aviso de "prancha lida que não gerou item". Tirar o "outro"
    do prompt trocaria "não sei" por palpite — e palpite de "render" ZERA a
    quantidade de prancha de verdade. Então aqui a gente MEDE, e não age."""
    ns = _ns_censo({"tipo_de_pagina": "outro", "items": [],
                    "_sem_item": {"motivo": "items-vazio"}})
    assert ns["_n_sem_item_sem_tipo"] == 1
    assert ns["_pranchas_nao_tecnicas"] == [], (
        "medir não é agir: sem classificação a página NÃO pode sair do aviso "
        "da outra frente")


@pytest.mark.parametrize("tipo", ["render", "planta"])
def test_CONTROLE_quem_se_classificou_nao_conta_como_sem_tipo(tipo):
    ns = _ns_censo({"tipo_de_pagina": tipo, "items": [],
                    "_sem_item": {"motivo": "items-vazio"}})
    assert ns["_n_sem_item_sem_tipo"] == 0


def test_CONTROLE_pagina_que_gerou_item_nao_conta_como_sem_tipo():
    ns = _ns_censo({"tipo_de_pagina": "outro",
                    "items": [{"description": "Piso vinílico"}]})
    assert ns["_n_sem_item_sem_tipo"] == 0


def test_a_pagina_de_render_sai_do_aviso_de_prancha_sem_item():
    """🪤 INTERAÇÃO com o conserto de ee801b82: agora que o prompt OFERECE
    "items": [], as 33 páginas de apresentação cairiam no aviso "33 pranchas
    foram lidas e não geraram item — confira antes de fechar". Elas não são
    pranchas e não há o que conferir."""
    ns = {"_pranchas_sem_item": ["pagina 17", "pagina 31", "planta que sumiu"],
          "_pranchas_nao_tecnicas": ["pagina 17", "pagina 31"]}
    roda("process_job", "if _n not in _pranchas_nao_tecnicas", ns, tamanho=1)
    assert ns["_pranchas_sem_item"] == ["planta que sumiu"], (
        "a prancha TÉCNICA que sumiu calada tem que continuar no aviso")


def test_CONTROLE_sem_pagina_de_apresentacao_a_lista_fica_inteira():
    ns = {"_pranchas_sem_item": ["planta que sumiu"], "_pranchas_nao_tecnicas": []}
    roda("process_job", "if _n not in _pranchas_nao_tecnicas", ns, tamanho=1)
    assert ns["_pranchas_sem_item"] == ["planta que sumiu"]


# ══════════════════════════════════════════════════════════════════════════
#  (c) O RECADO: quantas páginas do envio eram prancha técnica
# ══════════════════════════════════════════════════════════════════════════
#: O caderno do caso, com o veredito por página (2 técnicas, 33 de apresentação).
_CADERNO_DO_CASO = (["planta", "corte"]
                    + ["render"] * 18 + ["foto"] * 7 + ["moodboard"] * 2
                    + ["capa"] * 6)


def test_o_censo_do_caderno_do_caso():
    c = R.censo_de_paginas(_CADERNO_DO_CASO)
    assert c["total"] == 35
    assert c["tecnicas"] == 2 and c["sem_prancha"] == 33 and c["nao_disse"] == 0
    assert c["por_tipo"]["render"] == 18


def test_o_aviso_diz_o_numero_que_o_cliente_nunca_leu():
    aviso = R.aviso_das_paginas_sem_prancha(
        R.censo_de_paginas(_CADERNO_DO_CASO), n_linhas_escopo=493)
    assert "2 de 35" in aviso and "33" in aviso
    assert "493" in aviso and "ESCOPO" in aviso
    assert "prancha técnica" in aviso


def test_o_denominador_nao_e_inventado():
    """🪤 Dizer "2 de 35" quando 10 páginas não foram classificadas seria
    inventar o denominador — o defeito que a auditoria de hoje mais achou."""
    censo = R.censo_de_paginas(["planta"] + ["render"] * 4 + [""] * 10)
    aviso = R.aviso_das_paginas_sem_prancha(censo)
    assert "1 de 5" in aviso, aviso
    assert "10" in aviso and "não soube classificar" in aviso


def test_quando_nenhuma_pagina_e_prancha_o_recado_pede_a_planta():
    aviso = R.aviso_das_paginas_sem_prancha(
        R.censo_de_paginas(["render", "foto"]), n_linhas_escopo=12)
    assert "Nenhuma página deste envio é prancha técnica" in aviso
    assert "DWG/DXF" in aviso


def test_o_recado_nao_pede_o_DWG_a_quem_mandou_o_DWG():
    """🩸 22/09 (revisão) — O CENSO SÓ ENXERGA PÁGINA DE PDF. Num envio que
    também trouxe DWG/DXF (18 dos 167 jobs entregues em 90 dias, 10,8%), o
    cliente lia "mande a planta baixa (de preferência em DWG/DXF)" sobre o DWG
    que ele acabara de mandar."""
    censo = R.censo_de_paginas(["render", "foto"])
    com_cad = R.aviso_das_paginas_sem_prancha(censo, 12, leu_cad=True)
    assert "mande a planta baixa" not in com_cad, com_cad
    assert "foi lido à parte" in com_cad


def test_CONTROLE_sem_CAD_no_envio_o_recado_continua_pedindo_a_planta():
    """O controle positivo do caminho COMUM: quem mandou só PDF de
    apresentação precisa continuar ouvindo que falta a planta."""
    censo = R.censo_de_paginas(["render", "foto"])
    sem_cad = R.aviso_das_paginas_sem_prancha(censo, 12, leu_cad=False)
    assert "Nenhuma página deste envio é prancha técnica" in sem_cad
    assert "mande a planta baixa" in sem_cad
    assert "foi lido à parte" not in sem_cad


def test_a_primeira_frase_diz_que_o_denominador_e_so_das_paginas_de_PDF():
    """🪤 O denominador excluía, calado, todas as pranchas de CAD lidas — o
    mesmo defeito de denominador que a função guarda uma frase acima."""
    aviso = R.aviso_das_paginas_sem_prancha(
        R.censo_de_paginas(["planta", "render"]))
    assert aviso.startswith("📄 Das páginas dos PDFs deste envio, 1 de 2")


def test_CONTROLE_envio_normal_nao_ganha_aviso_nenhum():
    """O recado não existe pra quem mandou prancha — senão vira ruído em toda
    entrega, que é como a nota "aparece em N pranchas" ocupou 76% da
    observação de 343 linhas deste mesmo job."""
    for tipos in ([], ["planta"], ["planta", "corte", "detalhe"], ["", ""]):
        assert R.aviso_das_paginas_sem_prancha(R.censo_de_paginas(tipos)) is None


class _ItemDaPlanilha:
    """O que a planilha entregue tem: um item com observação."""

    def __init__(self, observations=""):
        self.observations = observations


class _PDVazio:
    warnings = []


class _LogLista:
    def __init__(self):
        self.linhas = []

    def __call__(self, stage, message, job_id=None, severity="error", **k):
        self.linhas.append((stage, message, job_id, severity))


def _ns_recado(**kw):
    ns = {"_tipos_de_pagina": _CADERNO_DO_CASO, "_n_escopo": 0,
          "_n_escopo_zerado": 0, "all_items": [], "_cad_analisou": False,
          "_n_sem_item_sem_tipo": 0, "job_id": "1d0751b8"}
    ns.update(kw)
    ns.setdefault("project_data", _PDVazio())
    ns.setdefault("_log_error", _LogLista())
    roda("process_job", "aviso_das_paginas_sem_prancha as _aviso_pg", ns,
         tamanho=1)
    return ns


def test_a_fiacao_do_recado_escreve_no_warnings_e_no_log():
    class _PD:
        warnings = ["aviso que já estava"]

    pd, log = _PD(), _LogLista()
    # 🩸 22/09 (revisão) — O LAÇO MONTOU 493 LINHAS DE ESCOPO; A PLANILHA QUE O
    # CLIENTE RECEBE TEM 3. `_consolidate_items`, `_dedupe_by_block` e
    # `_drop_nonsense_items` rodam DEPOIS do laço e comem 19,2% dos itens em
    # 90 dias (44 jobs, 7.616 -> 6.151; no job do caso, 743 -> 542, 27%). O
    # recado tem que dizer o número da planilha dele.
    entregues = [_ItemDaPlanilha(R.MARCA_DE_ESCOPO + " — veio de render"),
                 _ItemDaPlanilha(R.MARCA_DE_ESCOPO + " — veio de foto"),
                 _ItemDaPlanilha(R.MARCA_DE_ESCOPO + " — veio de capa"),
                 _ItemDaPlanilha("medido do desenho")]
    ns = _ns_recado(project_data=pd, _log_error=log, _n_escopo=493,
                    _n_escopo_zerado=192, all_items=entregues)
    assert pd.warnings[0] == "aviso que já estava", "aviso alheio foi atropelado"
    assert "2 de 35" in pd.warnings[-1]
    assert "3 linha(s)" in pd.warnings[-1], (
        "o recado conta a planilha ENTREGUE, não o laço: %s" % pd.warnings[-1])
    assert "493" not in pd.warnings[-1], (
        "493 é o número do laço — ele não existe na planilha do cliente")
    assert [l[0] for l in log.linhas] == ["motor:pagina-sem-prancha"]
    assert log.linhas[0][2] == "1d0751b8" and log.linhas[0][3] == "info"
    assert "linhas em ESCOPO=3" in log.linhas[0][1]
    assert "no laco=493" in log.linhas[0][1], (
        "os dois números juntos são o que mede quanto a consolidação comeu")
    assert "tinham numero=192" in log.linhas[0][1]
    assert ns["_n_escopo_entregue"] == 3


def test_CONTROLE_a_linha_que_nao_e_escopo_nao_entra_na_conta():
    """Sem este, um `len(all_items)` passaria verde no teste de cima."""
    ns = _ns_recado(all_items=[_ItemDaPlanilha("medido do desenho"),
                               _ItemDaPlanilha("")])
    assert ns["_n_escopo_entregue"] == 0
    assert "saíram como ESCOPO" not in ns["project_data"].warnings[-1]


def test_a_fiacao_do_recado_nao_pede_o_DWG_a_quem_mandou_o_DWG():
    """🩸 R1 no motor: `_cad_analisou` (bool(dxf_paths)) é o estado que diz se
    sobrou CAD pra analisar neste envio. Sem ele chegar à régua, o recado
    mandava o cliente mandar o desenho que ele já tinha mandado."""
    ns = _ns_recado(_tipos_de_pagina=["render", "foto"], _cad_analisou=True)
    texto = ns["project_data"].warnings[-1]
    assert "mande a planta baixa" not in texto, texto
    assert "foi lido à parte" in texto
    assert "leu_cad=True" in ns["_log_error"].linhas[0][1]


def test_CONTROLE_a_fiacao_sem_CAD_continua_pedindo_a_planta():
    ns = _ns_recado(_tipos_de_pagina=["render", "foto"], _cad_analisou=False)
    texto = ns["project_data"].warnings[-1]
    assert "Nenhuma página deste envio é prancha técnica" in texto
    assert "mande a planta baixa" in texto
    assert "leu_cad=False" in ns["_log_error"].linhas[0][1]


def test_a_pagina_sem_item_e_sem_tipo_vai_pro_LOG_e_nao_pro_CLIENTE():
    """🪤 R4: a medida serve pra DECIDIR em 2-4 semanas, com a frente do aviso
    de prancha sem item. Ela não vira texto pro cliente hoje."""
    ns = _ns_recado(_tipos_de_pagina=["planta", "corte"],
                    _n_sem_item_sem_tipo=2)
    assert ns["project_data"].warnings == [], "medida não vira recado"
    log = ns["_log_error"]
    assert [l[0] for l in log.linhas] == ["motor:pagina-sem-prancha"]
    assert "sem item e sem tipo=2" in log.linhas[0][1]


def test_CONTROLE_a_fiacao_do_recado_cala_em_envio_normal():
    ns = _ns_recado(_tipos_de_pagina=["planta", "corte"])
    assert ns["project_data"].warnings == []
    assert ns["_log_error"].linhas == []
