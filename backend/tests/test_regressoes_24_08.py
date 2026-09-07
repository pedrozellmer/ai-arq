# -*- coding: utf-8 -*-
"""Os 4 críticos que a validação de 24/08 achou nos consertos de 23/08.

Contexto: em 23/08 uma auditoria achou 57 problemas no trabalho do próprio dia,
e eu fechei as 26 pendências trabalhando até 02:30. Na manhã seguinte, antes de
qualquer cliente rodar, 5 frentes independentes atacaram esse código. Acharam
16 problemas confirmados — DOIS deles regressões que eu mesmo tinha acabado de
introduzir, e que deixavam o sistema PIOR do que antes do conserto.

Este arquivo guarda os quatro. Cada teste tem controle: prova que o
comportamento errado seria reprovado.

  #1 fusão devolvia selo 'confirmado' ao número que o cliente digitou (regra nº1)
  #2 fusão reinjetava a unidade VAZIA que o endpoint já tinha consertado
  #4 /inform-area zerava e GRAVAVA a área com procedência (regressão minha)
  #5 pintura/fôrma zeradas apostando numa derivação que muitas vezes não repõe
"""
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 🪤 Janela de tamanho fixo mede o vizinho (ou um pedaço) e passa verde por
# engano — a auditoria de 25/08 achou 17 assim, e a mutação de 06/09 provou
# que nem o recorte certo salva um guarda que só LÊ o fonte. O que sobrou de
# leitura aqui é complemento; o julgamento é sobre o que a função DEVOLVE.

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import main as m  # noqa: E402


def _fatia_motor():
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.rindex("\n", 0, src.index("_RX_SECAO_PILAR")) + 1
    j = src.index("\ndef _dedupe_revisoes", i)
    from engine_rules import (AREA_UNITS_HONESTY as _A, FLOOR_M2_UNITS as _F,
                              is_floor_surface as _isf,
                              is_floor_surface_para_criar as _isfc)
    from models import Confidence
    import re as _re
    ns = {"__name__": "motor_ns", "_AREA_UNITS_HONESTY": _A, "_FLOOR_M2_UNITS": _F,
          "_is_floor_surface": _isf, "_is_floor_surface_criar": _isfc, "Confidence": Confidence,
          "_re_honesty": _re, "_re": _re, "re": _re}
    exec(compile(src[i:j], "main_slice", "exec"), ns)
    return ns


def _fatia_fusao(revs, status=200):
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("def _fundir_revisoes_do_cliente")
    j = src.index("\n_CAMPOS_ITEM_VERSAO", i)
    ns = {"__name__": "fusao_ns",
          "_supa_rest_service": lambda m, p, **k: (status, revs),
          "_log_error": lambda *a, **k: None,
          "_norm_desc": lambda d: " ".join(str(d or "").lower().split())}
    exec(compile(src[i:j], "main_slice", "exec"), ns)
    return ns["_fundir_revisoes_do_cliente"]


class _Item:
    def __init__(self, description, unit, quantity, observations="", origem="",
                 confidence=None):
        self.description = description
        self.unit = unit
        self.quantity = quantity
        self.observations = observations
        self.origem = origem
        self.confidence = confidence


def _selo(it):
    return str(getattr(it.confidence, "value", it.confidence))


# ══════════════════════════════════════════════════════════════════════════
#  #4 — /inform-area PREENCHE, nunca zera
# ══════════════════════════════════════════════════════════════════════════
def test_inform_area_nao_zera_area_com_procedencia():
    """🚨 Regressão: o conserto da manhã de 23/08 (passar o pé-direito) foi
    desfeito pelo da noite (travas por origem), porque `project_items` nunca
    guardou a origem — na reidratação tudo volta com origem='' e as duas travas
    falham juntas. Caso cliente-25: pintura 1.641 m² e massa corrida 817 m²
    iam pra 0 e eram GRAVADAS assim."""
    f = _fatia_motor()["_apply_area_honesty"]
    pintura = _Item("Pintura latex acrilica em parede", "m²", 1641.4,
                    "⚠ ESTIMADO — 303.9 m de parede × pé-direito 2.70 m informado por você × 2 faces")
    massa = _Item("Massa corrida sobre paredes internas", "m²", 817.0,
                  "A-WALL = 303.96 ml × 2,70 m (pé-direito informado)")
    piso = _Item("Piso vinílico", "m²", 0, "Área NÃO medida — informe a área no upload")
    itens = [pintura, massa, piso]

    filled, blanked = f(itens, 118.5, "informado", pe_direito=2.7, apenas_preencher=True)

    assert pintura.quantity == 1641.4, "a rota zerou pintura com procedência"
    assert massa.quantity == 817.0, "a rota zerou massa corrida com procedência"
    assert blanked == 0, "esta rota NUNCA pode zerar — ela só preenche"
    assert piso.quantity == 118.5 and filled == 1, "parou de preencher o que estava em branco"


def test_o_controle_prova_que_sem_a_flag_o_estrago_acontece():
    """Controle positivo: sem `apenas_preencher`, e com a origem perdida (que é
    exatamente o estado da linha reidratada do banco antes de 24/08), os dois
    itens são zerados. É a prova de que a flag está segurando alguma coisa."""
    f = _fatia_motor()["_apply_area_honesty"]
    pintura = _Item("Massa corrida sobre paredes internas", "m²", 817.0,
                    "A-WALL = 303.96 ml × 2,70 m (pé-direito informado)")
    f([pintura], 118.5, "informado", pe_direito=2.7)      # sem a flag
    assert pintura.quantity == 0, (
        "o cenário do bug não reproduz mais — reveja este teste antes de confiar "
        "no de cima")


def _linhas_que_o_persist_manda(monkeypatch, itens, job_id="job-teste"):
    """Roda `_persist_items_to_supabase` de verdade e devolve o JSON que ele
    POSTA no PostgREST — as linhas como o banco vai recebê-las.

    🚨 06/09/2026 — a versão anterior deste guarda procurava `"origem"` no
    CORPO da função. Um `for _r in rows: _r.pop("origem", None)` depois de
    montar as linhas mantém a chave escrita no dicionário logo acima: o guarda
    ficava verde e a origem voltava a nunca chegar ao banco — que é o defeito
    original de 24/08, inteiro.
    """
    import json as _json
    import urllib.request as _ur
    postados = []

    class _Resp:
        def read(self):
            return b"[]"

    def _fake_urlopen(req, timeout=None):
        dados = getattr(req, "data", None)
        if dados and req.get_method() == "POST":
            postados.append(_json.loads(dados.decode("utf-8")))
        return _Resp()

    monkeypatch.setattr(_ur, "urlopen", _fake_urlopen)
    monkeypatch.setattr(m, "_supa_log", lambda *a, **k: None)
    monkeypatch.setattr(m, "_arquivar_versao_anterior", lambda *a, **k: None)
    monkeypatch.setattr(m, "_spec_do_cliente_antes_do_swap", lambda *a, **k: {})
    # 🪤 07/09: o terceiro resgate do swap. Sem neutralizar, o PATCH dele falha
    # neste ambiente, o `_log_error` grava — e o POST do log entra na contagem
    # de "inserts em lote" deste teste, que passa a ver 2 onde espera 1.
    # Os dois irmãos acima já estavam aqui pelo mesmo motivo.
    monkeypatch.setattr(m, "_soltar_revisoes_do_cascade", lambda *a, **k: 0)
    monkeypatch.setattr(m, "_contar_itens_no_banco", lambda *a, **k: len(itens))
    n = m._persist_items_to_supabase(job_id, itens)
    assert n == len(itens), "o persist devolveu %r pra %d itens" % (n, len(itens))
    assert len(postados) == 1, "esperava UM insert em lote, vi %d" % len(postados)
    return postados[0]


def _itens_que_a_planilha_recebe(monkeypatch, tmp_path, linhas, rota):
    """Executa UM dos DOIS caminhos que remontam a planilha a partir do banco e
    devolve os `BudgetItem` que chegaram ao `generate_spreadsheet`.

    🪤 06/09/2026 — SÃO DOIS, e o guarda executava um só. O guarda cego que ele
    substituiu contava `src.count('origem=r.get("origem") or ""') == 2`; a
    conversão pra execução exercitou só `/api/items/{job}/finalize` e largou a
    contagem. `/api/project/{job}/inform-area` — a rota em que o cliente informa
    a metragem e a planilha é REFEITA em cima dos itens do banco — podia voltar
    a perder a origem sem ninguém ver. E é justo ela que chama
    `_apply_area_honesty`, cuja trava de "não zerar o que tem procedência"
    depende dessa origem: perdê-la ali apaga pintura e massa corrida do cliente.
    """
    import json as _json
    import urllib.request as _ur
    import spreadsheet as _sp
    import sinapi_matcher as _sm
    import tcpo_matcher as _tm
    capturado = {}

    def _fake_generate(pd, items, output_path, **kw):
        capturado["items"] = list(items)
        open(output_path, "wb").write(b"x")

    class _R2:
        def __init__(self, c):
            self._c = c

        def read(self):
            return self._c

    monkeypatch.setattr(_sp, "generate_spreadsheet", _fake_generate)
    monkeypatch.setattr(m, "_require_project_owner", lambda *a, **k: None)
    monkeypatch.setattr(m, "_supa_rest_as_user",
                        lambda *a, **k: (200, [{"job_id": "job-teste",
                                                "project_name": "Casa",
                                                "total_area": 0,
                                                "warnings": []}]))
    monkeypatch.setattr(_ur, "urlopen",
                        lambda *a, **k: _R2(_json.dumps(linhas).encode("utf-8")))
    monkeypatch.setattr(m, "_supabase_storage_upload", lambda *a, **k: True)
    monkeypatch.setattr(m, "_carimbar_planilha", lambda *a, **k: None)
    monkeypatch.setattr(m, "WORK_DIR", str(tmp_path))
    monkeypatch.setattr(_sm, "candidates_for", lambda *a, **k: [])
    monkeypatch.setattr(_sm, "apply_llm_pick", lambda *a, **k: 0)
    monkeypatch.setattr(_tm, "match_item", lambda *a, **k: [])
    if rota == "finalize":
        import asyncio
        asyncio.run(m.rebuild_planilha_from_review("job-teste", object()))
    else:
        monkeypatch.setattr(m, "_log_error", lambda *a, **k: None)
        monkeypatch.setattr(m, "_supabase_update", lambda *a, **k: True)
        monkeypatch.setattr(m, "_projeto_patch", lambda *a, **k: True)
        monkeypatch.setattr(m, "_persist_items_to_supabase", lambda *a, **k: 0)
        m.inform_project_area("job-teste", m.InformAreaPayload(area=100.0),
                              object())
    assert capturado.get("items") is not None, (
        "a rota %r nem chegou a montar a planilha" % rota)
    return capturado["items"]


@pytest.mark.parametrize("rota", ["finalize", "inform-area"])
def test_a_origem_e_gravada_e_relida(monkeypatch, tmp_path, rota):
    """Sem isto, a reidratação volta a decidir no escuro.

    Duas metades, as duas EXECUTADAS: o persist manda a origem pro banco, e
    CADA UM dos dois caminhos que remontam a planilha devolve ela no objeto.

    🪤 As três origens que atravessam o banco aqui são de famílias diferentes de
    propósito: uma linha MEDIDA do CAD (`dxf_geom`, com número), uma DERIVADA
    pela nossa conta (`deriv_pd`) e uma que veio da mão do cliente
    (`revisao_cliente`, zerada — "já existe, não comprar"). Gravar a origem só
    de uma das famílias deixaria as outras duas passarem batido.
    """
    from models import BudgetItem, Confidence
    itens = [BudgetItem(item_num="1.1", description="Piso porcelanato", unit="m²",
                        quantity=118.5, confidence=Confidence.CONFIRMADO,
                        origem="dxf_geom", discipline="Acabamentos"),
             BudgetItem(item_num="1.2", description="Pintura látex", unit="m²",
                        quantity=540.0, confidence=Confidence.ESTIMADO,
                        origem="deriv_pd", discipline="Acabamentos"),
             BudgetItem(item_num="1.3", description="Luminária de emergência",
                        unit="un", quantity=0.0, confidence=Confidence.ESTIMADO,
                        origem="revisao_cliente", discipline="Elétrica")]
    _ESPERADO = ["dxf_geom", "deriv_pd", "revisao_cliente"]
    linhas = _linhas_que_o_persist_manda(monkeypatch, itens)
    assert [l.get("origem") for l in linhas] == _ESPERADO, (
        "_persist_items_to_supabase parou de mandar a origem pro banco: %r"
        % [sorted(l) for l in linhas])

    # ── e a volta: o que o banco guardou tem que virar objeto de novo ──
    relidos = _itens_que_a_planilha_recebe(monkeypatch, tmp_path, linhas, rota)
    assert [i.origem for i in relidos] == _ESPERADO, (
        "a reidratação de %s perdeu a origem — a honestidade de área volta a "
        "decidir com menos informação do que o motor tinha: %r"
        % (rota, [i.origem for i in relidos]))


def test_CONTROLE_o_persist_manda_mesmo_as_linhas(monkeypatch):
    """🧪 Se o dublê engolisse o POST, o teste acima seria verde por não olhar
    nada."""
    from models import BudgetItem, Confidence
    linhas = _linhas_que_o_persist_manda(
        monkeypatch,
        [BudgetItem(item_num="9.9", description="Item de controle", unit="un",
                    quantity=3, confidence=Confidence.ESTIMADO, origem="")])
    assert len(linhas) == 1 and linhas[0]["description"] == "Item de controle"
    assert linhas[0].get("origem", "AUSENTE") is None, (
        "origem vazia tem que virar NULL, não string vazia nem chave ausente: %r"
        % linhas[0].get("origem", "AUSENTE"))


# ══════════════════════════════════════════════════════════════════════════
#  #5 — só zera quando a nossa conta REALMENTE vai repor
# ══════════════════════════════════════════════════════════════════════════
def _pintura_ia():
    return _Item("Pintura latex em paredes internas", "m²", 540.0,
                 "300 m × pé-direito 1,80 m informado por você — conta do modelo")


def test_pintura_sobrevive_quando_outra_pintura_bloqueia_a_derivacao():
    """Cenário A: existe "Pintura em teto" medida do CAD. `_derive_pintura_pe_direito`
    desiste (`if any(_e_pintura(i) and _qtd(i) > 0)`), então zerar aqui apaga a
    linha e ninguém repõe."""
    ns = _fatia_motor()
    p = _pintura_ia()
    itens = [
        _Item("Alvenaria de vedação", "m", 300.0, "", origem="dxf_geom"),
        _Item("Pintura latex em teto", "m²", 80.0, "", origem="dxf_geom"),
        p,
    ]
    ns["_apply_area_honesty"](itens, 0, "", pe_direito=1.8)
    ns["_derive_pintura_pe_direito"](itens, 1.8)
    assert p.quantity > 0, "linha zerada e a derivação não repôs — dado perdido"


def test_pintura_sobrevive_quando_o_linear_medido_nao_e_parede():
    """Cenário B: o único linear do CAD é eletroduto. A derivação só soma
    m/ml cuja descrição tenha parede/alvenaria/drywall — então desiste."""
    ns = _fatia_motor()
    p = _pintura_ia()
    itens = [_Item("Eletroduto PVC 25mm", "m", 200.0, "", origem="dxf_geom"), p]
    ns["_apply_area_honesty"](itens, 0, "", pe_direito=1.8)
    ns["_derive_pintura_pe_direito"](itens, 1.8)
    assert p.quantity > 0, "linha zerada e a derivação não repôs — dado perdido"


def test_quando_a_derivacao_VAI_repor_a_conta_nossa_vence():
    """O contrário também tem que continuar valendo: havendo parede medida e
    nenhuma outra pintura, a linha do modelo É zerada de propósito pra a nossa
    conta (2 faces) entrar no lugar."""
    ns = _fatia_motor()
    p = _pintura_ia()
    itens = [_Item("Alvenaria de vedação", "m", 300.0, "", origem="dxf_geom"), p]
    ns["_apply_area_honesty"](itens, 0, "", pe_direito=1.8)
    assert p.quantity == 0, "a honestidade tem que limpar pra a nossa conta entrar"
    ns["_derive_pintura_pe_direito"](itens, 1.8)
    assert abs(p.quantity - round(300.0 * 1.8 * 2, 1)) < 0.11, (
        "a nossa conta determinística não entrou: %s" % p.quantity)
    assert p.origem == "deriv_pd"


def test_derivacao_vai_repor_responde_certo_nos_dois_sentidos():
    f = _fatia_motor()["_derivacao_vai_repor"]
    parede = _Item("Alvenaria de vedação", "m", 300.0, "", origem="dxf_geom")
    alvo = "Pintura latex em paredes internas"
    assert f([parede, _pintura_ia()], alvo, 2.7) is True
    assert f([_Item("Eletroduto", "m", 200.0)], alvo, 2.7) is False
    assert f([parede], alvo, 0) is False        # sem pé-direito não deriva nada
    # fôrma de pilar precisa da seção "AxB cm" num item contado em `un`
    forma = "Fôrma de pilar em chapa compensada"
    assert f([_Item("Pilar P1 20x40 cm", "un", 12)], forma, 2.7) is True
    assert f([_Item("Pilar P1", "un", 12)], forma, 2.7) is False


# ══════════════════════════════════════════════════════════════════════════
#  #1 e #2 — resolvidos na RAIZ, e testados em test_fusao_revisao.py
# ══════════════════════════════════════════════════════════════════════════
# O primeiro conserto (24/08 de manhã) remendou o ramo "casou": ignorar campo
# vazio e rebaixar o selo quando a quantidade mudasse. Funcionava, mas atacava o
# sintoma — a fusão continuava lendo `item_reviews.edits`, que é o payload CRU
# da PRIMEIRA edição do navegador.
#
# O conserto de raiz veio junto: `item_reviews` passou a responder só QUAIS
# itens o cliente tocou (`item_id`), e os VALORES saem da linha do pai em
# `project_items` — que já está com a unidade consertada, o selo rebaixado e a
# ÚLTIMA versão do número. Isso mata #1, #2 e #7 de uma vez.
#
# Os testes desse comportamento moram em test_fusao_revisao.py. Aqui fica só o
# controle que prova que o jeito ANTIGO seria reprovado.


def test_o_controle_prova_que_o_ramo_casado_antigo_seria_reprovado():
    """Reprodução do ramo 'casou' como era até 24/08: escrevia os 4 campos
    direto do payload, sem olhar vazio nem selo."""
    from models import BudgetItem, Confidence

    def _velho(alvo, ed):
        alvo.description = ed.get("description", alvo.description)
        alvo.unit = ed.get("unit", alvo.unit)
        alvo.quantity = ed.get("quantity", alvo.quantity)

    it = BudgetItem(item_num="3.1", description="Pilares — armadura CA-50",
                    unit="kg", quantity=18168.0,
                    confidence=Confidence.CONFIRMADO, origem="dxf_geom")
    _velho(it, {"description": "Pilares — armadura CA-50", "unit": "",
                "quantity": 1500.0})
    assert it.unit == "", "o cenário do bug não reproduz mais"
    assert it.confidence == Confidence.CONFIRMADO, "o cenário do bug não reproduz mais"


def _fusao_de_verdade(monkeypatch, revs, linhas_do_pai):
    """A fusão REAL do main.py, com o banco injetado."""
    monkeypatch.setattr(m, "_supa_rest_service",
                        lambda metodo, tabela, **kw:
                        (200, revs) if tabela == "item_reviews" else (200, []))
    monkeypatch.setattr(m, "_supa_rest_tudo",
                        lambda tabela, **kw:
                        (200, linhas_do_pai) if tabela == "project_items" else (200, []))
    monkeypatch.setattr(m, "_log_error", lambda *a, **k: None)
    return m._fundir_revisoes_do_cliente


def test_a_fusao_le_os_valores_do_project_items_do_pai(monkeypatch):
    """🚨 De onde vêm os valores da correção do cliente: da linha ATUAL do pai
    (`project_items`) e não do payload cru do navegador (`item_reviews.edits`).

    🚨 06/09/2026 — a versão anterior era um guarda ESTRUTURAL: conferia que os
    nomes dos campos apareciam no `select` de `project_items`. Trocar
    `linha.get("unit")` por `ed.get("unit")` e `linha.get("quantity")` por
    `ed.get("quantity")` na montagem deixava o `select` intacto — o guarda
    ficava verde e os bugs #1, #2 e #7 voltavam juntos.

    O cenário abaixo é o real de 24/08: 7 linhas de armadura CA-50 em que o
    dropdown apagou a unidade no payload, e a quantidade foi corrigida DUAS
    vezes (o `edits` guarda a primeira, o pai guarda a última).

    🪤 06/09/2026 — ELE SÓ PROVAVA `unit` E `quantity`. O assert de `confidence`
    era satisfeito pela regra nº1 (quem digitou vira 'estimado'), não por LER o
    selo do pai; e `observations`/`description` não eram olhados de jeito nenhum
    — `observations` podia voltar a sair do `edits` (a foto do navegador na 1ª
    edição) e a anotação ATUAL do cliente, guardada no pai, seria sobrescrita
    calada. Perda de trabalho humano, regra nº7, com a bancada verde.
    Agora entram DUAS revisões: uma em que o cliente digitou outro número, e
    outra em que ele NÃO mexeu na quantidade — nesta o selo só pode vir do pai.
    """
    from models import BudgetItem, Confidence
    # a anotação que o cliente tem HOJE, guardada no pai...
    _OBS_DO_PAI = "conferido em obra: bitola 12,5 mm conforme prancha EST-02"
    # ...e a foto velha do navegador, que o `edits` congelou na 1ª edição
    _OBS_DO_NAVEGADOR = "rascunho ANTIGO da primeira edicao, ja substituido"
    # o cliente também arrumou o TEXTO da linha; o pai tem a versão dele
    _DESC_PAI = ("Pilares — armadura CA-50 conforme prancha EST-02 do bloco A "
                 "(bitola conferida por mim)")
    _DESC_LEITURA_NOVA = "Pilares — armadura CA-50 conforme prancha EST-02 do bloco A"
    f = _fusao_de_verdade(
        monkeypatch,
        revs=[{"item_id": "id-9", "reviewed_at": "2026-08-23T10:00:00Z",
               "edits": {"description": "Pilares — armadura CA-60 (grafia da 1ª edição)",
                         "unit": "",              # o dropdown apagou
                         "quantity": 100.0,       # a PRIMEIRA edição
                         "observations": _OBS_DO_NAVEGADOR,
                         "_antes": {"unit": "kg", "quantity": 18168.0}}},
              # 2ª revisão: o cliente só arrumou a GRAFIA — a quantidade é a
              # mesma de antes, então quem responde pelo selo é o pai.
              {"item_id": "id-12", "reviewed_at": "2026-08-23T10:05:00Z",
               "edits": {"description": "Piso porcelanato 60x60 - hall",
                         "unit": "m²", "quantity": 88.0,
                         "_antes": {"unit": "m²", "quantity": 88.0}}}],
        linhas_do_pai=[{"id": "id-9", "description": _DESC_PAI,
                        "unit": "kg",             # o endpoint já consertou
                        "quantity": 1500.0,       # a ÚLTIMA correção
                        "confidence": "estimado",
                        "observations": _OBS_DO_PAI},
                       {"id": "id-12", "description": "Piso porcelanato 60x60 - hall",
                        "unit": "m²", "quantity": 88.0,
                        "confidence": "confirmado", "observations": ""}])
    # a leitura nova trouxe a unidade que o persist inventa quando falta
    alvo = BudgetItem(item_num="3.1", description=_DESC_LEITURA_NOVA,
                      unit="vb", quantity=18168.0,
                      confidence=Confidence.CONFIRMADO, origem="dxf_geom")
    piso = BudgetItem(item_num="4.1", description="Piso porcelanato 60x60 - hall",
                      unit="m²", quantity=88.0,
                      confidence=Confidence.CONFIRMADO, origem="dxf_geom")
    f([alvo, piso], "pai123")
    assert alvo.unit == "kg", (
        "a fusão voltou a tirar a unidade do payload cru do navegador — "
        "1.850 kg viram '1850 verbas'. Veio: %r" % alvo.unit)
    assert alvo.quantity == 1500.0, (
        "a fusão ressuscitou a 1ª edição (%s) em vez da correção final do "
        "cliente (1500)" % alvo.quantity)
    assert str(getattr(alvo.confidence, "value", alvo.confidence)) == "estimado", (
        "número digitado à mão saiu carimbado como medição do CAD")
    # 🔑 observations: a anotação do cliente mora no PAI, não no `edits`
    assert _OBS_DO_PAI in alvo.observations, (
        "a fusão perdeu a anotação ATUAL do cliente (regra nº7) — veio %r"
        % alvo.observations)
    assert "ANTIGO" not in alvo.observations, (
        "a fusão voltou a copiar a observação CONGELADA na 1ª edição do "
        "navegador por cima da anotação de hoje: %r" % alvo.observations)
    # 🔑 description: idem — o texto que vale é o que o cliente vê na tela
    assert "bitola conferida por mim" in alvo.description, (
        "a descrição não veio da linha do pai: %r" % alvo.description)
    assert "CA-60" not in alvo.description, (
        "a fusão ressuscitou a grafia errada da 1ª edição: %r" % alvo.description)
    # 🔑 confidence: aqui o cliente NÃO digitou número nenhum, então a regra nº1
    # não decide — o selo só pode ter vindo da linha do pai.
    assert str(getattr(piso.confidence, "value", piso.confidence)) == "confirmado", (
        "o selo do pai não foi lido: a linha que o CAD mediu e o cliente só "
        "corrigiu na grafia foi rebaixada sem motivo (%r)" % piso.confidence)
    assert piso.quantity == 88.0, "mexeu no número que o cliente não tocou"


def test_CONTROLE_a_fusao_reprova_quando_o_pai_nao_responde(monkeypatch):
    """🧪 Sem isto o teste acima passaria com a fusão desligada: se ela não
    fundir nada, o item fica com os valores da leitura nova — e é justamente
    isso que o teste acima chama de defeito."""
    from models import BudgetItem, Confidence
    f = _fusao_de_verdade(monkeypatch, revs=[], linhas_do_pai=[])
    alvo = BudgetItem(item_num="3.1", description="Pilares — armadura CA-50",
                      unit="vb", quantity=18168.0,
                      confidence=Confidence.CONFIRMADO, origem="dxf_geom")
    f([alvo], "pai123")
    assert alvo.unit == "vb" and alvo.quantity == 18168.0, (
        "sem revisão nenhuma a fusão mexeu no item — o cenário do teste acima "
        "não prova nada")


def test_a_fusao_continua_lendo_os_campos_do_pai_no_select(monkeypatch):
    """Complemento estrutural do teste acima: campo que sai do `select` chega
    vazio na fusão sem quebrar nada — o `.get()` devolve None e ninguém grita."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("def _fundir_revisoes_do_cliente")
    corpo = src[i:src.index("_CAMPOS_ITEM_VERSAO", i)]
    # 🪤 25/08: aqui a asserção era a STRING EXATA do select. Ela quebrou no dia
    # em que a fusão passou a ler TAMBÉM marca/codigo/cor/spec_origem — ou
    # seja, quebrou porque melhorou. O que o guarda quer dizer é "a fusão lê os
    # VALORES do pai em vez de confiar no payload do navegador"; então é isso
    # que ele confere, e campo novo no select não derruba mais nada.
    # 🪤 O primeiro `"select"` da função é o de `item_reviews` — ancorar nele
    # mediria a leitura errada. O que interessa é a de `project_items`.
    # 🪤 E a janela de N caracteres me pegou DE NOVO aqui: 400 chars não
    # alcançavam o fim do select depois que um comentário entrou no meio do
    # dicionário. A janela certa é a que termina onde a CHAMADA termina.
    _i_sel = corpo.index('"project_items"')
    _texto_sel = corpo[_i_sel:corpo.index("})", _i_sel)]
    for _campo in ("quantity", "unit", "confidence", "observations"):
        assert _campo in _texto_sel, (
            "a fusão parou de ler `%s` do pai — voltou a confiar no payload "
            "cru do navegador" % _campo)
    assert '_atuais = {str((l or {}).get("id")): l' in corpo, (
        "a fusão parou de indexar os itens do pai por id")
    assert '"_antes"' in corpo, (
        "a fusão parou de olhar o `_antes` — é ele que responde se o CLIENTE "
        "digitou o número e qual era a unidade do motor")


# ══════════════════════════════════════════════════════════════════════════
#  2ª VALIDAÇÃO (24/08): "preencher" só pode preencher o que está EM BRANCO
# ══════════════════════════════════════════════════════════════════════════
def test_inform_area_nao_sobrescreve_o_numero_que_o_cliente_digitou():
    """🚨 O `apenas_preencher=True` que eu criei de manhã não protegia o ramo
    que PREENCHE — ele vem ANTES no encadeamento. Medido: piso vinílico que o
    cliente tinha corrigido pra 45,30 m² virava 310,00 (a área total informada)
    e era GRAVADO. A linha zerada é a pergunta do cliente; a linha que ele
    preencheu é a resposta dele."""
    f = _fatia_motor()["_apply_area_honesty"]
    cliente = _Item("Piso vinílico em manta - áreas administrativas", "m²", 45.30,
                    "corrigido na tela", origem="revisao_cliente")
    cad = _Item("Piso porcelanato - hall", "m²", 88.0, "", origem="dxf_geom")
    branco = _Item("Forro de gesso", "m²", 0, "Área NÃO medida")
    f([cliente, cad, branco], 310.0, "informado", pe_direito=2.7,
      apenas_preencher=True)
    assert cliente.quantity == 45.30, (
        "virou %s — o cliente perdeu o número dele por ter informado a metragem"
        % cliente.quantity)
    assert cad.quantity == 88.0, "encostou no que foi medido do CAD"
    assert branco.quantity == 310.0, "parou de preencher o que estava em branco"


def test_revisao_do_cliente_e_intocavel_tambem_no_caminho_normal():
    """Regra dura nº7 não depende de qual rota chamou."""
    f = _fatia_motor()["_apply_area_honesty"]
    cliente = _Item("Piso vinílico", "m²", 45.30, "", origem="revisao_cliente")
    f([cliente], 310.0, "informado", pe_direito=2.7)      # sem a flag
    assert cliente.quantity == 45.30


# ══════════════════════════════════════════════════════════════════════════
#  2ª VALIDAÇÃO (24/08): o dedup da planilha apagava a linha do cliente
# ══════════════════════════════════════════════════════════════════════════
def test_o_dedup_da_planilha_nao_apaga_a_linha_vinda_da_revisao():
    """🚨 Duas réguas diferentes pra "o mesmo item": a fusão casa por 9 palavras,
    o dedup da planilha corta em 50 caracteres. Par REAL de produção (job
    1a2f9f03): "Escavação ... tipo S1 (160×160×60cm)" e "... tipo S2
    (100×100×40cm)" NÃO casam na fusão — a linha do cliente é acrescentada,
    certo — e DEPOIS colidem aqui e somem do .xlsx, com o log dizendo
    "planilha REFEITA com as correções do cliente"."""
    import os as _os
    import tempfile
    import openpyxl
    from models import BudgetItem, Confidence, ProjectData
    from spreadsheet import generate_spreadsheet

    S1 = ("Escavação manual/mecânica de cavas para sapatas tipo S1 "
          "(160×160×60cm) — solo em condições a confirmar por sondagem SPT")
    S2 = ("Escavação manual/mecânica de cavas para sapatas tipo S2 "
          "(100×100×40cm) — solo em condições a confirmar por sondagem SPT")
    assert S1.lower().strip()[:50] == S2.lower().strip()[:50], (
        "o par de controle parou de colidir em 50 chars — reveja este teste")

    itens = [
        BudgetItem(item_num="1.1", description=S1, unit="m³", quantity=12.0,
                   confidence=Confidence.CONFIRMADO, origem="dxf_geom",
                   discipline="Estrutura"),
        BudgetItem(item_num="REV.1", description=S2, unit="m³", quantity=4.5,
                   confidence=Confidence.ESTIMADO, origem="revisao_cliente",
                   discipline="Estrutura"),
    ]
    d = tempfile.mkdtemp(prefix="xlsx_dedup_")
    saida = _os.path.join(d, "t.xlsx")
    generate_spreadsheet(ProjectData(project_name="teste"), itens, saida)
    wb = openpyxl.load_workbook(saida)
    texto = []
    for ws in wb.worksheets:
        for linha in ws.iter_rows(values_only=True):
            texto.append(" | ".join("" if c is None else str(c) for c in linha))
    tudo = "\n".join(texto)
    assert "tipo S1" in tudo, "sumiu a linha do motor"
    assert "tipo S2" in tudo, (
        "a linha vinda da revisão do cliente foi DELETADA pelo dedup de 50 "
        "caracteres — regra dura nº7 quebrada no arquivo que ele baixa")
