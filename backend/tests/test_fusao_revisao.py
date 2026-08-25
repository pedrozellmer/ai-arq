# -*- coding: utf-8 -*-
"""A fusão das revisões do cliente — regra dura nº7.

Pedro, 08/08/2026: *"o cliente que mudou os itens na tela, os itens que ele
mediu são a verdade mais pura, mesmo que a gente tenha revisado o motor"*.

🚨 Esta função nunca rodou em produção: até 23/08 morria no bug da leitura da
tupla, dentro de um try/except que engolia o erro. Foi escrita, revisada e
liberada sem NUNCA ter sido exercida. Cada rodada de auditoria achou defeitos
que estavam esperando o primeiro cliente:

  23/08 — a linha acrescentada era `deepcopy(items[0])`: herdava selo
          'confirmado', item_num, prancha, disciplina e SINAPI de outro serviço.
  24/08 — os VALORES vinham de `item_reviews.edits`, o payload CRU do navegador
          na PRIMEIRA edição. Isso desfazia três consertos que o endpoint de
          revisão já tinha feito: unidade apagada pelo dropdown, selo rebaixado
          e a versão mais nova do número. Além disso, o casamento por 9 palavras
          jogava a correção na linha ERRADA quando havia linhas irmãs.

🪤 O harness antigo TROCAVA o `_norm_desc` por um stub bobo — então o casamento
de verdade (que tira acento, tira [marcadores] e corta em 9 palavras) nunca era
exercido, e a colisão passou batido. Aqui a fatia carrega o `_norm_desc` REAL.
"""
import io
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)


def _carrega(revs, itens_do_pai=None, status_rev=200, status_itens=200):
    """Executa a fatia REAL (do `_norm_desc` até a fusão) com o banco injetado.

    `revs`         -> o que `item_reviews` devolve
    `itens_do_pai` -> o que `project_items` do PAI devolve (a fonte dos valores)
    """
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("def _norm_desc(")
    j = src.index("\n_CAMPOS_ITEM_VERSAO", i)
    chamadas = []

    def _fake(method, path, **kw):
        chamadas.append((method, path))
        if path == "item_reviews":
            return status_rev, revs
        if path == "project_items":
            return status_itens, (itens_do_pai or [])
        return 200, []

    import re as _re
    ns = {"__name__": "fusao_ns", "_re": _re, "re": _re,
          "_supa_rest_service": _fake, "_log_error": lambda *a, **k: None,
          "_SUPA_TETO_POR_PAGINA": 1000}
    # 🪤 25/08: a fusão passou a ler o pai pelo paginador (o PostgREST corta em
    # 1000 e não avisa). Aqui entra o paginador REAL, não um stub — stub de
    # paginação esconderia justamente o que ele existe pra provar.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _corpo import corpo_de
    exec(compile(corpo_de("_supa_rest_tudo"), "paginador", "exec"), ns)
    exec(compile(src[i:j], "main_slice", "exec"), ns)
    return ns["_fundir_revisoes_do_cliente"], chamadas, ns


def _rev(item_id, desc="", unit="", qtd=None):
    """Uma linha de item_reviews. O que importa agora é o item_id."""
    return {"item_id": item_id, "reviewed_at": "2026-08-23T10:00:00Z",
            "edits": {"description": desc, "unit": unit, "quantity": qtd}}


def _linha_pai(item_id, desc, unit, qtd, conf="estimado", obs=""):
    """Uma linha de project_items do PAI — já corrigida e já rebaixada."""
    return {"id": item_id, "description": desc, "unit": unit, "quantity": qtd,
            "confidence": conf, "observations": obs}


def _itens_da_leitura():
    """Primeiro item MEDIDO — era ele que o deepcopy antigo clonava."""
    from models import BudgetItem, Confidence
    return [
        BudgetItem(item_num="1.1", description="Laje maciça h=12cm", unit="m²",
                   quantity=210.0, confidence=Confidence.CONFIRMADO,
                   origem="dxf_geom", ref_sheet="ARQ-01", discipline="Estrutura",
                   sinapi_matches=[{"cod": "92873", "sim": 91}]),
        BudgetItem(item_num="1.2", description="Piso porcelanato", unit="m²",
                   quantity=118.5, confidence=Confidence.ESTIMADO),
    ]


def _selo(it):
    return str(getattr(it.confidence, "value", it.confidence))


# ══════════════════════════════════════════════════════════════════════════
#  A FONTE DOS VALORES (achados 7, 2 e 1 na raiz)
# ══════════════════════════════════════════════════════════════════════════
def test_o_valor_vem_da_linha_do_pai_e_nao_do_payload_antigo():
    """🚨 #7: o endpoint deduplica e NÃO atualiza `edits`. O cliente digita 100
    por engano, corrige pra 250 e sai: `project_items` fica 250 (o que ele vê),
    `item_reviews` continua 100. A fusão trazia o 100 de volta e ainda carimbava
    "este número é o que você corrigiu"."""
    f, _, _ = _carrega(
        revs=[_rev("id-1", "Piso porcelanato", "m²", 100.0)],          # 1ª edição
        itens_do_pai=[_linha_pai("id-1", "Piso porcelanato", "m²", 250.0)])
    itens, resumo = f(_itens_da_leitura(), "pai123")
    piso = [i for i in itens if "porcelanato" in i.description.lower()][0]
    assert piso.quantity == 250.0, (
        "voltou %s — a fusão ressuscitou a 1ª edição em vez da correção final"
        % piso.quantity)


def test_unidade_vazia_do_payload_nunca_chega_na_planilha():
    """🚨 #2: 8 linhas reais no banco têm unit='' em item_reviews (7 de armadura
    CA-50 em kg). O endpoint conserta antes de gravar em project_items; a fusão
    lia item_reviews e contornava a trava de 18/08."""
    f, _, _ = _carrega(
        revs=[_rev("id-9", "Pilares — armadura CA-50", "", 1500.0)],
        itens_do_pai=[_linha_pai("id-9", "Pilares — armadura CA-50", "kg", 1500.0)])
    from models import BudgetItem, Confidence
    alvo = BudgetItem(item_num="3.1", description="Pilares — armadura CA-50",
                      unit="kg", quantity=18168.0, confidence=Confidence.CONFIRMADO,
                      origem="dxf_geom")
    f([alvo], "pai123")
    assert alvo.unit == "kg", "a unidade foi apagada (%r)" % alvo.unit
    assert alvo.quantity == 1500.0


def test_o_selo_vem_do_pai_ja_rebaixado():
    """🚨 #1: número digitado à mão não é medição do CAD. O endpoint já rebaixa;
    a fusão devolvia 'confirmado'."""
    f, _, _ = _carrega(
        revs=[_rev("id-2")],
        itens_do_pai=[_linha_pai("id-2", "Piso porcelanato", "m²", 130.0,
                                 conf="estimado")])
    itens, _ = f(_itens_da_leitura(), "pai123")
    piso = [i for i in itens if "porcelanato" in i.description.lower()][0]
    assert piso.quantity == 130.0
    assert _selo(piso) == "estimado", "saiu como '%s'" % _selo(piso)
    assert piso.origem == "revisao_cliente"
    assert "não é medida do CAD" in piso.observations


def test_correcao_so_de_texto_preserva_o_selo_da_medicao():
    """Controle do outro lado: se o cliente só arrumou o NOME, a medição
    continua sendo medição — o pai guarda 'confirmado' e isso tem que passar."""
    f, _, _ = _carrega(
        revs=[_rev("id-3")],
        itens_do_pai=[_linha_pai("id-3", "Laje maciça h=12cm", "m²", 210.0,
                                 conf="confirmado")])
    itens, _ = f(_itens_da_leitura(), "pai123")
    laje = [i for i in itens if "laje" in i.description.lower()][0]
    assert _selo(laje) == "confirmado", "rebaixou uma medição que não mudou de número"


# ══════════════════════════════════════════════════════════════════════════
#  O CASAMENTO (achados 8 e 9)
# ══════════════════════════════════════════════════════════════════════════
def _porta(sufixo, qtd):
    from models import BudgetItem, Confidence
    return BudgetItem(item_num="4.1",
                      description="Porta de madeira 80x210 cm folha lisa branca " + sufixo,
                      unit="un", quantity=qtd, confidence=Confidence.ESTIMADO)


def test_linhas_irmas_nao_recebem_a_correcao_no_lugar_errado():
    """🚨 #8: a chave corta em 9 palavras, e o que distingue "SUITE 1/2/3" mora
    justamente no fim. A correção da SUITE 2 caía na SUITE 1 e ainda reescrevia
    a descrição dela — o cliente ficava com duas "SUITE 2" e nenhuma "SUITE 1"."""
    f, _, _ = _carrega(
        revs=[_rev("id-4")],
        itens_do_pai=[_linha_pai(
            "id-4", "Porta de madeira 80x210 cm folha lisa branca SUITE 2", "un", 3.0)])
    itens, _ = f([_porta("SUITE 1", 1.0), _porta("SUITE 2", 1.0), _porta("SUITE 3", 1.0)],
                 "pai123")
    s1 = [i for i in itens if i.description.endswith("SUITE 1")]
    s2 = [i for i in itens if i.description.endswith("SUITE 2")]
    assert len(s1) == 1, "a SUITE 1 foi renomeada — a correção caiu na linha errada"
    assert len(s2) == 1 and s2[0].quantity == 3.0, "a correção não chegou na SUITE 2"


def test_ambiguidade_nao_e_resolvida_no_escuro():
    """Quando a leitura nova tem DUAS linhas idênticas, escolher é adivinhar.
    Não escolhe: acrescenta e registra."""
    f, _, _ = _carrega(
        revs=[_rev("id-5")],
        itens_do_pai=[_linha_pai("id-5", "Ponto de tomada 220V", "un", 40.0)])
    from models import BudgetItem, Confidence
    a = BudgetItem(item_num="5.1", description="Ponto de tomada 220V", unit="un",
                   quantity=10.0, confidence=Confidence.ESTIMADO)
    b = BudgetItem(item_num="5.2", description="Ponto de tomada 220V", unit="un",
                   quantity=12.0, confidence=Confidence.ESTIMADO)
    itens, resumo = f([a, b], "pai123")
    assert resumo["ambiguas"] == 1
    assert a.quantity == 10.0 and b.quantity == 12.0, "sobrescreveu no escuro"
    assert resumo["acrescentadas"] == 1, "a correção do cliente se perdeu"
    assert itens[-1].quantity == 40.0


def test_duas_correcoes_nao_colapsam_uma_na_outra():
    """🚨 #9: com a chave cortada, duas correções de linhas irmãs viravam UMA —
    a outra sumia em silêncio, e o contador dizia revisoes=1."""
    f, _, _ = _carrega(
        revs=[_rev("id-6"), _rev("id-7")],
        itens_do_pai=[
            _linha_pai("id-6", "Porta de madeira 80x210 cm folha lisa branca SUITE 1", "un", 2.0),
            _linha_pai("id-7", "Porta de madeira 80x210 cm folha lisa branca SUITE 2", "un", 3.0),
        ])
    itens, resumo = f([_porta("SUITE 1", 1.0), _porta("SUITE 2", 1.0)], "pai123")
    assert resumo["revisoes"] == 2, "uma das duas correções sumiu do contador"
    q = {i.description[-7:]: i.quantity for i in itens}
    assert q.get("SUITE 1") == 2.0 and q.get("SUITE 2") == 3.0, q


# ══════════════════════════════════════════════════════════════════════════
#  A linha acrescentada (achado de 23/08) — não pode herdar nada
# ══════════════════════════════════════════════════════════════════════════
def test_linha_acrescentada_nasce_limpa():
    f, _, _ = _carrega(
        revs=[_rev("id-8")],
        itens_do_pai=[_linha_pai("id-8", "Alvenaria de bloco 14 cm", "m²", 96.0)])
    itens, resumo = f(_itens_da_leitura(), "pai123")
    assert resumo["acrescentadas"] == 1
    nova = itens[-1]
    assert _selo(nova) == "estimado", "número digitado saiu como MEDIDO do CAD"
    assert nova.ref_sheet == "" and nova.item_num != "1.1"
    assert nova.discipline != "Estrutura" and not nova.sinapi_matches
    assert nova.origem == "revisao_cliente"
    assert nova.quantity == 96.0


# ══════════════════════════════════════════════════════════════════════════
#  Falha de leitura NUNCA pode passar por "o cliente não revisou"
# ══════════════════════════════════════════════════════════════════════════
def test_falha_ao_ler_as_revisoes_deixa_rastro():
    f, _, _ = _carrega(revs=None, status_rev=500)
    _, resumo = f(_itens_da_leitura(), "pai123")
    assert resumo.get("erro_leitura")


def test_falha_ao_ler_os_itens_do_pai_tambem_deixa_rastro():
    """Sem os itens do pai não dá pra saber o valor CORRETO — e continuar
    seria voltar a usar o payload velho, que é o bug que este redesenho fecha."""
    f, _, _ = _carrega(revs=[_rev("id-1")], itens_do_pai=None, status_itens=503)
    _, resumo = f(_itens_da_leitura(), "pai123")
    assert resumo.get("erro_leitura")
    assert resumo["casadas"] == 0 and resumo["acrescentadas"] == 0


def test_sem_revisao_nao_mexe_em_nada():
    f, _, _ = _carrega(revs=[])
    antes = _itens_da_leitura()
    itens, resumo = f(list(antes), "pai123")
    assert resumo["revisoes"] == 0 and resumo["casadas"] == 0
    assert len(itens) == len(antes)


def test_sem_pai_nao_toca_o_banco():
    f, chamadas, _ = _carrega(revs=[_rev("id-1")])
    f(_itens_da_leitura(), "")
    assert not chamadas


# ══════════════════════════════════════════════════════════════════════════
#  ORDEM no process_job: a planilha entregue é a de DEPOIS da fusão
# ══════════════════════════════════════════════════════════════════════════
def test_a_planilha_entregue_e_a_ULTIMA_versao():
    """A ordem no process_job é o que garante que o arquivo baixado bate com a tela.

    Duas coisas nascem DEPOIS da primeira planilha: a fusão das revisões (regra
    nº7) e o aviso "esta releitura mediu MENOS que a versão anterior". As duas
    precisam estar no .xlsx, e o carimbo de coerência é calculado sobre o banco —
    então se o arquivo for o antigo, o detector jura que está tudo em dia.
    """
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i_fusao = src.index("all_items, _fusao = _fundir_revisoes_do_cliente(")
    i_cmp = src.index("_cmp_v = _comparar_com_versao_anterior(", i_fusao)
    i_regen = src.index("generate_spreadsheet(project_data, all_items, output_path", i_cmp)
    i_carimbo = src.index("_carimbar_planilha(job_id)", i_fusao)
    i_upload = src.index("_supabase_storage_upload(output_path", i_fusao)
    assert i_fusao < i_cmp < i_regen < i_carimbo < i_upload, (
        "a planilha tem que ser refeita DEPOIS da fusão E do aviso de versão, e "
        "antes do carimbo e do upload")


def test_o_aviso_de_mediu_menos_entra_no_arquivo():
    """🚨 24/08: o aviso ia pra tela e nunca pro .xlsx — o cliente encaminhava o
    arquivo pro orçamentista sem a ressalva, justo no caso em que a ressalva É o
    produto (caso Amanda, 10/08: 47 medidos viraram 28 e o e-mail dizia
    'planilha atualizada')."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("_cmp_v = _comparar_com_versao_anterior(")
    trecho = src[i:i + 1200]
    assert "_refazer_planilha.append" in trecho, (
        "o aviso de 'mediu menos' não marca a planilha pra ser refeita — ele "
        "nasce depois do arquivo e morre na tela")


def test_o_regen_nao_roda_a_toa():
    """Refazer a planilha custa tempo em todo job. Só quando há motivo."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("_cmp_v = _comparar_com_versao_anterior(")
    i_regen = src.index("generate_spreadsheet(project_data, all_items, output_path", i)
    trecho = src[i:i_regen]
    assert "if _refazer_planilha:" in trecho, (
        "a refação virou incondicional — passa a rodar em todo job sem motivo")


def test_a_fusao_ainda_marca_a_planilha_pra_refazer():
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("all_items, _fusao = _fundir_revisoes_do_cliente(")
    trecho = src[i:src.index("_persist_items_to_supabase(job_id, all_items)", i)]
    assert 'if (_fusao.get("casadas") or 0) or (_fusao.get("acrescentadas") or 0):' in trecho
    assert "_refazer_planilha.append" in trecho


def test_o_aviso_ao_cliente_conta_as_linhas_NOVAS():
    """🚨 #10: o aviso garantia que 'o motor corrigiu apenas as outras linhas'
    mesmo quando a correção entrou como linha NOVA convivendo com a do motor —
    quem somasse a coluna contava duas vezes, com o aviso dizendo que estava
    tudo certo."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("MANTEVE as {_fusao['revisoes']}")
    trecho = src[max(0, i - 800):i + 1500]
    assert "LINHA NOVA" in trecho, "o aviso não distingue sobrescrita de linha acrescentada"
    assert "antes de somar a coluna" in trecho, "não alerta sobre a soma em dobro"
    assert "ambiguas={_amb}" in trecho or "ambiguas=" in trecho, (
        "o contador de ambíguas continua sem chegar ao log")


# ══════════════════════════════════════════════════════════════════════════
#  Controle positivo do casamento: o _norm_desc REAL colide mesmo?
# ══════════════════════════════════════════════════════════════════════════
def test_o_corte_de_9_palavras_realmente_colide():
    """Se este teste parar de valer, o das linhas irmãs virou decorativo."""
    _, _, ns = _carrega(revs=[])
    n = ns["_norm_desc"]
    a = "Porta de madeira 80x210 cm folha lisa branca SUITE 1"
    b = "Porta de madeira 80x210 cm folha lisa branca SUITE 2"
    assert n(a) == n(b), "o corte não colide mais — reveja o teste das irmãs"
    assert n(a, cortar=False) != n(b, cortar=False), (
        "a chave cheia também colide — aí o casamento não tem como distinguir")


# ══════════════════════════════════════════════════════════════════════════
#  2ª VALIDAÇÃO (24/08) — o que a reescrita de uma hora antes quebrou
# ══════════════════════════════════════════════════════════════════════════
def _rev_antes(item_id, desc, unit_antes, qtd_antes, unit_ed="", qtd_ed=None):
    """Revisão COM `_antes` — a foto do item antes da edição (86 das 88 têm)."""
    return {"item_id": item_id, "reviewed_at": "2026-08-23T10:00:00Z",
            "edits": {"description": desc, "unit": unit_ed, "quantity": qtd_ed,
                      "_antes": {"description": desc, "unit": unit_antes,
                                 "quantity": qtd_antes}}}


def test_corrigir_a_UNIDADE_nao_pode_virar_linha_duplicada():
    """🚨 #1, medido em 6 correções reais de 5 clientes. A unidade estava DENTRO
    da chave de casamento — e trocar a unidade é justamente uma das coisas que o
    cliente edita. A correção nunca casava, virava REV.1, e a linha do motor
    sobrevivia intacta com '✓ MEDIDO do CAD'.

    Caso real (job df4f00ca): o cliente marcou a luminária de emergência como
    "já existe, não comprar" (un→vb, 15→0). A releitura devolvia as 15 unidades
    prontas pra comprar."""
    desc = "[EXISTENTE - manter] Luminária de emergência autônoma 30 LED"
    f, _, _ = _carrega(
        revs=[_rev_antes("id-lum", desc, "un", 15.0, unit_ed="vb", qtd_ed=0.0)],
        itens_do_pai=[_linha_pai("id-lum", desc, "vb", 0.0, conf="estimado")])
    from models import BudgetItem, Confidence
    motor = BudgetItem(item_num="7.3", description=desc, unit="un", quantity=15.0,
                       confidence=Confidence.CONFIRMADO, origem="dxf_geom")
    itens, resumo = f([motor], "pai123")
    assert resumo["casadas"] == 1 and resumo["acrescentadas"] == 0, (
        "a correção de unidade virou linha nova: %s" % resumo)
    assert len(itens) == 1, "o mesmo serviço saiu em duas linhas"
    assert motor.unit == "vb" and motor.quantity == 0.0, (
        "a decisão do cliente ('já existe, não comprar') foi desfeita")
    assert _selo(motor) == "estimado"


def test_arrumar_so_a_grafia_nao_carimba_QUANTIDADE_CORRIGIDA():
    """🚨 #2: `_mudou` comparava o pai com a LEITURA NOVA. Como o motor não é
    determinístico elas quase nunca batem, então a linha saía com selo
    'confirmado' (herdado do pai, correto) E com "QUANTIDADE CORRIGIDA POR
    VOCÊ" — a mesma célula do .xlsx dizia '✓ MEDIDO do CAD' e 'não é medida do
    CAD'. A pergunta certa é se o CLIENTE digitou o número, e quem responde é
    o `_antes`."""
    desc = "Forro de gesso acartonado liso (área)"
    f, _, _ = _carrega(
        # o cliente só arrumou o TEXTO: a quantidade do _antes é a mesma do pai
        revs=[_rev_antes("id-forro", desc, "m²", 118.5, unit_ed="m²", qtd_ed=118.5)],
        itens_do_pai=[_linha_pai("id-forro", desc, "m²", 118.5, conf="confirmado")])
    from models import BudgetItem, Confidence
    # a leitura nova mediu OUTRO valor — é isso que enganava o critério antigo
    novo = BudgetItem(item_num="6.1", description=desc, unit="m²", quantity=300.0,
                      confidence=Confidence.CONFIRMADO, origem="dxf_geom")
    f([novo], "pai123")
    assert _selo(novo) == "confirmado", "rebaixou uma medição que o cliente não tocou"
    obs = novo.observations
    assert "QUANTIDADE CORRIGIDA" not in obs, (
        "carimbou 'você corrigiu o número' num item em que ele só arrumou a "
        "grafia:\n" + obs)


def test_quando_o_cliente_digitou_mesmo_o_selo_cai():
    """Controle do outro lado: `_antes` diferente do pai = ele digitou."""
    desc = "Piso porcelanato 60x60"
    f, _, _ = _carrega(
        revs=[_rev_antes("id-p", desc, "m²", 210.0, unit_ed="m²", qtd_ed=130.0)],
        itens_do_pai=[_linha_pai("id-p", desc, "m²", 130.0, conf="estimado")])
    from models import BudgetItem, Confidence
    novo = BudgetItem(item_num="2.1", description=desc, unit="m²", quantity=305.0,
                      confidence=Confidence.CONFIRMADO, origem="dxf_geom")
    f([novo], "pai123")
    assert novo.quantity == 130.0 and _selo(novo) == "estimado"
    assert "QUANTIDADE CORRIGIDA" in novo.observations
    assert novo.origem == "revisao_cliente"


def test_se_a_gravacao_no_pai_falhou_vale_o_numero_da_revisao():
    """🚨 #6: o PATCH que grava a correção engole exceção num log mudo, e a tela
    já mostrou 'Salvo'. Se o pai continua IGUAL ao `_antes` mas a revisão
    registrou outro número, a gravação não pegou — a única cópia do que o
    cliente digitou está no `edits`. A reescrita devolvia o número do MOTOR
    chamando de 'sua revisão'."""
    desc = "Piso porcelanato 60x60"
    f, _, _ = _carrega(
        revs=[_rev_antes("id-x", desc, "m²", 118.5, unit_ed="m²", qtd_ed=130.0)],
        itens_do_pai=[_linha_pai("id-x", desc, "m²", 118.5, conf="confirmado")])
    from models import BudgetItem, Confidence
    novo = BudgetItem(item_num="2.1", description=desc, unit="m²", quantity=305.0,
                      confidence=Confidence.CONFIRMADO, origem="dxf_geom")
    f([novo], "pai123")
    assert novo.quantity == 130.0, (
        "entregou %s — o número do motor foi devolvido como se fosse a revisão "
        "do cliente" % novo.quantity)
    assert _selo(novo) == "estimado"


def test_linha_ressuscitada_nao_perde_a_unidade():
    """🚨 #7, payload REAL do job 2933cc30: unit='' no edits, 'kg' no `_antes`.
    Sem a cascata, o persist inventa 'vb' e 1.850 kg viram 1.850 verbas."""
    desc = "Muro de arrimo — armadura CA-50/CA-60 (peso total)"
    f, _, _ = _carrega(
        revs=[_rev_antes("id-sumiu", desc, "kg", 100.0, unit_ed="", qtd_ed=1850.0)],
        itens_do_pai=[])          # o item foi apagado do pai
    itens, resumo = f(_itens_da_leitura(), "pai123")
    assert resumo["acrescentadas"] == 1
    nova = itens[-1]
    assert nova.unit == "kg", (
        "unidade %r — 1.850 de nada; quem cota devolve a planilha" % nova.unit)
    assert nova.quantity == 1850.0
