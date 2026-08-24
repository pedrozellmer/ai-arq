# -*- coding: utf-8 -*-
"""A fusão das revisões do cliente — regra dura nº7.

Pedro, 08/08/2026: *"o cliente que mudou os itens na tela, os itens que ele
mediu são a verdade mais pura, mesmo que a gente tenha revisado o motor"*.

🚨 Esta função NUNCA rodou em produção: até 23/08/2026 ela morria no bug da
leitura da tupla do Supabase, dentro de um try/except que engolia o erro
(`error_log` com stage `motor:fusao-revisao` = 0 linhas). Ou seja, ela foi
escrita, revisada e liberada sem nunca ter sido exercida — e a auditoria do dia
achou dois defeitos que estavam esperando o primeiro cliente:

  23) a linha acrescentada era `deepcopy(items[0])` com 4 campos reescritos.
      Herdava o SELO do primeiro item da leitura — e em 23 de 147 projetos
      (16%) esse primeiro item é 'confirmado'. Resultado: a linha que o cliente
      DIGITOU sairia marcada "✓ MEDIDO do CAD". Herdava também item_num
      (duplicado), ref_sheet (prancha errada), disciplina e código SINAPI de
      outro serviço.

  22) o .xlsx era gerado ANTES da fusão — a tela mostrava as correções, o
      arquivo baixado não, e o carimbo de coerência jurava que estava em dia.
      (Testado aqui pela ORDEM no código, que é o que dá pra afirmar sem subir
      um job inteiro.)

Como a fusão lê o Supabase, os testes injetam a leitura em vez de bater na
rede — o que interessa é a decisão, não o transporte.
"""
import io
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)


def _carrega(revs, status=200):
    """Executa só a função de fusão, com a leitura do banco injetada."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("def _fundir_revisoes_do_cliente")
    j = src.index("\n_CAMPOS_ITEM_VERSAO", i)
    chamadas = []

    def _fake_rest(method, path, **kw):
        chamadas.append((method, path))
        return status, revs

    ns = {
        "__name__": "fusao_ns",
        "_supa_rest_service": _fake_rest,
        "_log_error": lambda *a, **k: None,
        "_norm_desc": lambda d: " ".join(str(d or "").lower().split()),
    }
    exec(compile(src[i:j], "main_slice", "exec"), ns)
    return ns["_fundir_revisoes_do_cliente"], chamadas


def _rev(desc, unit, qtd, obs=""):
    return {"edits": {"description": desc, "unit": unit, "quantity": qtd,
                      "observations": obs},
            "reviewed_at": "2026-08-23T10:00:00Z"}


def _itens_da_leitura():
    """Primeiro item MEDIDO — é justamente ele que o deepcopy clonava."""
    from models import BudgetItem, Confidence
    return [
        BudgetItem(item_num="1.1", description="Laje maciça h=12cm", unit="m²",
                   quantity=210.0, confidence=Confidence.CONFIRMADO,
                   origem="dxf_geom", ref_sheet="ARQ-01", discipline="Estrutura",
                   sinapi_matches=[{"cod": "92873", "sim": 91}]),
        BudgetItem(item_num="1.2", description="Piso porcelanato", unit="m²",
                   quantity=118.5, confidence=Confidence.ESTIMADO),
    ]


# ══════════════════════════════════════════════════════════════════════════
#  ACHADO 23 — a linha do cliente não pode herdar nada do item[0]
# ══════════════════════════════════════════════════════════════════════════
def test_linha_acrescentada_nao_herda_o_selo_medido():
    f, _ = _carrega([_rev("Alvenaria de bloco 14 cm", "m²", 96.0)])
    itens = _itens_da_leitura()
    itens, resumo = f(itens, "pai123")
    assert resumo["acrescentadas"] == 1
    nova = itens[-1]
    selo = str(getattr(nova.confidence, "value", nova.confidence))
    assert selo == "estimado", (
        "número digitado à mão saiu como '%s' — regra dura nº1: só o que veio "
        "da geometria do CAD pode ser 'confirmado'" % selo)


def test_linha_acrescentada_nao_herda_prancha_numero_disciplina_nem_sinapi():
    f, _ = _carrega([_rev("Alvenaria de bloco 14 cm", "m²", 96.0)])
    itens, resumo = f(_itens_da_leitura(), "pai123")
    nova = itens[-1]
    assert nova.ref_sheet == "", "apontava pra prancha de outro serviço"
    assert nova.item_num != "1.1", "item_num duplicado com o primeiro item"
    assert nova.discipline != "Estrutura", "caiu na disciplina do item[0]"
    assert not nova.sinapi_matches, "levou o código SINAPI de outro serviço"
    assert nova.origem == "revisao_cliente"


def test_a_linha_do_cliente_sobrevive_com_os_valores_dele():
    f, _ = _carrega([_rev("Alvenaria de bloco 14 cm", "m²", 96.0, "medi na obra")])
    itens, _ = f(_itens_da_leitura(), "pai123")
    nova = itens[-1]
    assert nova.description == "Alvenaria de bloco 14 cm"
    assert nova.unit == "m²" and nova.quantity == 96.0
    assert "REVISADO POR VOCÊ" in nova.observations
    assert "medi na obra" in nova.observations


def test_duas_linhas_acrescentadas_ganham_numeros_diferentes():
    f, _ = _carrega([_rev("Alvenaria de bloco 14 cm", "m²", 96.0),
                     _rev("Chapisco interno", "m²", 210.0)])
    itens, resumo = f(_itens_da_leitura(), "pai123")
    assert resumo["acrescentadas"] == 2
    nums = [i.item_num for i in itens[-2:]]
    assert len(set(nums)) == 2, "duas linhas com o mesmo item_num: %s" % nums


# ══════════════════════════════════════════════════════════════════════════
#  O que a fusão já fazia certo e não pode regredir
# ══════════════════════════════════════════════════════════════════════════
def test_quando_casa_o_valor_do_cliente_manda():
    f, _ = _carrega([_rev("Piso porcelanato", "m²", 130.0)])
    itens, resumo = f(_itens_da_leitura(), "pai123")
    assert resumo["casadas"] == 1 and resumo["acrescentadas"] == 0
    piso = [i for i in itens if "porcelanato" in i.description.lower()][0]
    assert piso.quantity == 130.0, "a leitura nova sobrescreveu a correção do cliente"
    assert "REVISADO POR VOCÊ" in piso.observations


def test_sem_revisao_nao_mexe_em_nada():
    f, _ = _carrega([])
    antes = _itens_da_leitura()
    itens, resumo = f(list(antes), "pai123")
    assert resumo == {"revisoes": 0, "casadas": 0, "acrescentadas": 0}
    assert len(itens) == len(antes)


def test_falha_de_leitura_nao_pode_passar_por_cliente_sem_revisao():
    """🚨 O erro que fez esta função morrer calada por semanas."""
    f, _ = _carrega(None, status=500)
    itens, resumo = f(_itens_da_leitura(), "pai123")
    assert resumo.get("erro_leitura"), (
        "consulta falhou e o resumo não registrou — 'não deu pra ler' virou "
        "'o cliente não revisou', que é como o bug ficou invisível")


def test_sem_pai_nao_tenta_ler_o_banco():
    f, chamadas = _carrega([_rev("X", "un", 1)])
    f(_itens_da_leitura(), "")
    assert not chamadas, "leu o banco sem ter projeto pai"


# ══════════════════════════════════════════════════════════════════════════
#  ACHADO 22 — a planilha entregue tem que ser a de DEPOIS da fusão
# ══════════════════════════════════════════════════════════════════════════
def test_a_planilha_e_refeita_depois_da_fusao():
    """Sem subir um job, o que dá pra afirmar é a ORDEM no código: a chamada que
    refaz o .xlsx tem que estar entre a fusão e o upload pro Storage."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i_fusao = src.index("all_items, _fusao = _fundir_revisoes_do_cliente(")
    i_regen = src.index("generate_spreadsheet(project_data, all_items, output_path", i_fusao)
    i_carimbo = src.index("_carimbar_planilha(job_id)", i_fusao)
    i_upload = src.index("_supabase_storage_upload(output_path", i_fusao)
    assert i_fusao < i_regen < i_carimbo, (
        "a planilha não é refeita entre a fusão e o carimbo — o cliente baixa "
        "um .xlsx sem as correções dele e o carimbo diz que está em dia")
    assert i_regen < i_upload, "refez o arquivo depois de já ter subido pro Storage"


def test_o_regen_so_roda_quando_a_fusao_mudou_alguma_coisa():
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i_fusao = src.index("all_items, _fusao = _fundir_revisoes_do_cliente(")
    trecho = src[i_fusao:src.index("_persist_items_to_supabase(job_id, all_items)", i_fusao)]
    assert 'if (_fusao.get("casadas") or 0) or (_fusao.get("acrescentadas") or 0):' in trecho, (
        "refazer a planilha em todo job custa tempo à toa — tem que ser "
        "condicionado a a fusão ter mudado alguma coisa")
