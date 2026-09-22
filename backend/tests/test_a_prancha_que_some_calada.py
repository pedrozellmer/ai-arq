# -*- coding: utf-8 -*-
"""A prancha que a IA leu e que sumiu da planilha sem ninguém saber.

🩸 22/09/2026 — job ee801b82 (estrutura, 7 PDFs de uma página). A IA devolveu
69 itens e o banco guardou 63. Duas pranchas sumiram, e o error_log não tem
uma linha sobre nenhuma delas:

  · a do poço de sucção voltou `{"project_data": {"kept_elements": [...],
    "items": [6 itens]}}`. Os dois laços do main leem `result["items"]` no
    TOPO e o normalize só tratava lista × dict: os 6 itens — 785,7 kg de aço
    calculados da lista da prancha — foram descartados;
  · a de fundação voltou SÓ `project_data.kept_elements`, sem "items" em
    lugar nenhum. Sem erro, o aviso de cobertura não a contou (ele só conhece
    `result["error"]`), e o cliente nunca soube que ela não entrou.

🔑 Os consertos:
  (2) o normalize sobe a lista de UM nível abaixo quando o topo não tem item,
      mantém o project_data e deixa a marca `_items_aninhados` pro log;
  (3) resposta sem "items" em lugar nenhum ganha UMA releitura com texto
      diferente (o payload muda, então o llm_cache não devolve a mesma
      resposta); continuando sem item, vira `motor:prancha-sem-item` no
      error_log e uma frase própria no aviso — que NÃO promete que
      reprocessar resolve.

📊 Alcance medido em 22/09 no llm_cache (respostas do analyzer, 31/08–22/09,
451 no total): aninhado em project_data 1 (este caso). Sem item e sem erro
32 em setembro: 27 com "items": [] explícito (a IA respondeu que não há o
que quantificar — capa, documento) e 5 sem "items" nenhum, 4 delas em projeto
de estrutura. Só as 5 são relidas: ~7/mês × US$ 0,049 ≈ US$ 0,35/mês.

🧪 Tudo aqui CHAMA o código real: `normalize_items_payload`,
`analyze_sheet` com um cliente falso, e as instruções do `process_job`
recortadas pela árvore sintática e EXECUTADAS.
"""
import ast
import io
import json
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import analyzer  # noqa: E402
import engine_rules  # noqa: E402
import llm_cache  # noqa: E402
from models import SheetType  # noqa: E402


# ── os números do caso, com nomes neutros ─────────────────────────────────
_SEIS_ITENS = [
    {"item_num": "1", "description": "Concreto C30 — parede do poço",
     "unit": "m³", "quantity": 8.0, "confidence": "estimado"},
    {"item_num": "2", "description": "Concreto C30 — laje de cobertura",
     "unit": "m³", "quantity": 1.35, "confidence": "estimado"},
    {"item_num": "3", "description": "Fôrma — parede do poço",
     "unit": "m²", "quantity": 79.6, "confidence": "estimado"},
    {"item_num": "4", "description": "Fôrma — laje de cobertura",
     "unit": "m²", "quantity": 9.6, "confidence": "estimado"},
    {"item_num": "5", "description": "Aço CA-50 ø10 — lista de ferros",
     "unit": "kg", "quantity": 784.45, "confidence": "estimado"},
    {"item_num": "6", "description": "Aço CA-50 ø6,3 — lista de ferros",
     "unit": "kg", "quantity": 1.27, "confidence": "estimado"},
]
_KEPT = ["Poço circular — parede 10 cm", "Laje de cobertura h=25 cm"]
_ANINHADO = {"project_data": {"kept_elements": _KEPT, "items": _SEIS_ITENS}}
_SO_KEPT = {"project_data": {"kept_elements": ["4 sapatas S1 120×120",
                                               "pilares P1–P4 20×20"]}}


def _texto(obj, raciocinio="Raciocínio da leitura."):
    return "%s\n```json\n%s\n```" % (raciocinio, json.dumps(obj, ensure_ascii=False))


class _Resp:
    def __init__(self, texto, stop_reason="end_turn"):
        class _C:
            pass
        _c = _C()
        _c.text = texto
        self.content = [_c]
        self.stop_reason = stop_reason


class _Sheet:
    def __init__(self, sheet_type=SheetType.ARQUITETURA, nome="prancha-F.pdf"):
        self.text_content = ""
        self.crops = []
        self.sheet_type = sheet_type
        self.filename = nome


def _roda(monkeypatch, respostas, sheet=None, **kw):
    """`analyze_sheet` de verdade; a IA é uma fila de respostas prontas.
    Devolve (resultado, lista dos kwargs de cada chamada)."""
    fila = list(respostas)
    capt = []

    def _fake_stream(*a, **k):
        capt.append(k)
        r = fila.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(analyzer, "call_with_retry_stream", _fake_stream)
    kw.setdefault("is_structural", True)
    out = analyzer.analyze_sheet(None, sheet or _Sheet(), **kw)
    return out, capt


# ══════════════════════════════════════════════════════════════════════════
#  (2) item aninhado sobe um nível — sem perder o project_data, sem calar
# ══════════════════════════════════════════════════════════════════════════
def test_o_normalize_sobe_os_6_itens_do_project_data():
    out = engine_rules.normalize_items_payload(json.loads(json.dumps(_ANINHADO)))
    assert len(out["items"]) == 6, "os itens aninhados continuam perdidos"
    kg = sum(i["quantity"] for i in out["items"] if i["unit"] == "kg")
    assert abs(kg - 785.72) < 0.01, "o aço da lista (785,7 kg) não voltou"
    assert out["project_data"]["kept_elements"] == _KEPT, "perdeu o project_data"
    assert out["_items_aninhados"] == {"de": "project_data", "n": 6}, (
        "subiu calado — sem a marca o main não registra que o formato variou")


def test_o_normalize_nao_mexe_no_que_ja_vem_no_topo():
    entrada = {"items": [{"description": "Concreto"}], "project_data": {"items": [{"x": 1}]}}
    out = engine_rules.normalize_items_payload(entrada)
    assert out is entrada and "_items_aninhados" not in out
    # e os casos antigos continuam
    assert engine_rules.normalize_items_payload([{"a": 1}]) == {"items": [{"a": 1}]}
    assert engine_rules.normalize_items_payload(None) == {"items": []}


def test_o_normalize_nao_sobe_lista_de_texto():
    """Lista de string não é item — subir faria o laço do main descartar cada
    uma no except, calado de novo."""
    out = engine_rules.normalize_items_payload(
        {"project_data": {"items": ["poço", "caixa"]}})
    assert not out.get("items") and "_items_aninhados" not in out


def test_o_analyze_sheet_entrega_os_6_numa_chamada_so(monkeypatch):
    out, capt = _roda(monkeypatch, [_Resp(_texto(_ANINHADO))])
    assert len(capt) == 1, "item aninhado não é prancha vazia: não pode reler"
    assert len(out["items"]) == 6 and out["_items_aninhados"]["n"] == 6
    assert "_sem_item" not in out and "error" not in out
    assert out["project_data"]["kept_elements"] == _KEPT


def test_o_registro_do_aninhado_vai_pro_error_log():
    out = engine_rules.normalize_items_payload(json.loads(json.dumps(_ANINHADO)))
    regs = engine_rules.registros_da_leitura(out, "prancha-D.pdf")
    assert [s for s, _ in regs] == ["motor:items-aninhados"]
    assert "prancha-D.pdf" in regs[0][1] and "6 item" in regs[0][1]


def test_CONTROLE_o_normalize_antigo_perdia_os_6():
    """🧪 O comportamento de ANTES, reproduzido: devolvia o dict como veio, e o
    laço do main (`result.get("items", [])`) não via item nenhum."""
    def _antigo(parsed):
        if isinstance(parsed, list):
            return {"items": parsed}
        if not isinstance(parsed, dict):
            return {"items": []}
        return parsed
    assert _antigo(json.loads(json.dumps(_ANINHADO))).get("items", []) == []


# ══════════════════════════════════════════════════════════════════════════
#  (3) sem item e sem erro: UMA releitura com texto diferente, e registro
# ══════════════════════════════════════════════════════════════════════════
def test_a_prancha_so_com_kept_elements_e_relida_com_outro_payload(monkeypatch):
    """🩸 A prancha de fundação do caso. A 1ª resposta não traz 'items'; a
    releitura traz. A 2ª chamada tem de ser OUTRO payload — com o mesmo, o
    llm_cache (modo 'on') devolveria a mesma resposta vazia."""
    out, capt = _roda(monkeypatch, [_Resp(_texto(_SO_KEPT)),
                                    _Resp(_texto({"items": _SEIS_ITENS[:2]}))])
    assert len(capt) == 2, "a prancha sem 'items' não foi relida"
    c1, c2 = capt[0]["messages"][0]["content"], capt[1]["messages"][0]["content"]
    assert c2[:-1] == c1, "a releitura tem de mandar a MESMA prancha"
    assert c2[-1]["text"] == analyzer.RELEITURA_SEM_ITEMS
    assert llm_cache.carimbo(capt[0]) != llm_cache.carimbo(capt[1]), (
        "mesma chave de cache — a releitura receberia a resposta vazia de novo")
    for k in ("model", "system", "temperature", "max_tokens"):
        assert capt[0][k] == capt[1][k], "a releitura mudou %r" % k
    assert len(out["items"]) == 2
    assert out["_releitura"] == {"motivo": "sem-chave-items", "itens": 2}
    assert "_sem_item" not in out


def test_se_a_releitura_tambem_vem_vazia_so_uma_vez_e_fica_registrado(monkeypatch):
    out, capt = _roda(monkeypatch, [_Resp(_texto(_SO_KEPT)), _Resp(_texto(_SO_KEPT))])
    assert len(capt) == 2, "UMA releitura, nunca um laço"
    assert not out.get("items") and "error" not in out
    assert out["_sem_item"] == {"motivo": "sem-chave-items", "releu": True}
    regs = dict(engine_rules.registros_da_leitura(out, "prancha-F.pdf"))
    assert "motor:prancha-sem-item" in regs and "motor:prancha-releitura" in regs


def test_items_vazio_explicito_nao_e_relido_mas_e_registrado(monkeypatch):
    """"items": [] é a IA RESPONDENDO que não há o que quantificar (capa,
    lista de documentos). Insistir empurra a inventar — regra nº1."""
    out, capt = _roda(monkeypatch, [_Resp(_texto({"items": [], "project_data": {}}))])
    assert len(capt) == 1
    assert out["_sem_item"] == {"motivo": "items-vazio", "releu": False}


def test_layout_atual_em_arquitetura_nao_e_relido(monkeypatch):
    """O prompt do layout atual pede só kept_elements: reler pediria item de
    ambiente EXISTENTE, que viraria serviço novo na planilha."""
    out, capt = _roda(monkeypatch, [_Resp(_texto(_SO_KEPT))],
                      sheet=_Sheet(SheetType.LAYOUT_ATUAL), is_structural=False)
    assert len(capt) == 1
    assert out["_sem_item"]["motivo"] == "layout-atual"


def test_a_releitura_que_falha_nao_vira_erro_da_prancha(monkeypatch):
    out, capt = _roda(monkeypatch, [_Resp(_texto(_SO_KEPT)), RuntimeError("caiu")])
    assert len(capt) == 2
    assert "error" not in out, "a 1ª leitura foi boa; a releitura não pode derrubá-la"
    assert "RuntimeError" in out["_releitura"]["falhou"]
    assert out["_sem_item"]["releu"] is True


def test_corte_no_teto_nao_e_relido(monkeypatch):
    """Resposta cortada tem aviso próprio, e reler corta no mesmo lugar."""
    out, capt = _roda(monkeypatch, [_Resp(_texto(_SO_KEPT), stop_reason="max_tokens")])
    assert len(capt) == 1 and out.get("_truncated") and "_sem_item" not in out


def test_prancha_com_item_nao_ganha_marca_nenhuma(monkeypatch):
    out, capt = _roda(monkeypatch, [_Resp(_texto({"items": _SEIS_ITENS}))])
    assert len(capt) == 1
    assert not [k for k in out if k.startswith("_")]
    assert engine_rules.registros_da_leitura(out, "x") == []


def test_o_aviso_diz_o_que_aconteceu_e_nao_promete_reprocesso():
    um = engine_rules.aviso_de_prancha_sem_item(["prancha-F.pdf"])
    assert "prancha-F.pdf" in um and "1 prancha foi lida e não gerou nenhum item" in um
    varios = engine_rules.aviso_de_prancha_sem_item(["prancha-F.pdf", "prancha-G.pdf"])
    assert varios.startswith("ℹ 2 pranchas foram lidas e não geraram")
    for t in (um, varios):
        assert "eprocess" not in t, "o aviso prometeu reprocesso — ninguém mediu que resolve"
    assert engine_rules.aviso_de_prancha_sem_item([]) == ""
    longo = engine_rules.aviso_de_prancha_sem_item(["prancha-%03d.pdf" % i for i in range(60)])
    assert len(longo) < 520, "a lista de nomes não tem teto"


# ══════════════════════════════════════════════════════════════════════════
#  O main REGISTRA e AVISA — as instruções reais do process_job, executadas
# ══════════════════════════════════════════════════════════════════════════
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _process_job():
    achados = [n for n in ast.walk(ast.parse(_FONTE))
               if isinstance(n, ast.FunctionDef) and n.name == "process_job"]
    assert len(achados) == 1, "process_job sumiu ou virou duas definições"
    return achados[0]


def _blocos_com_filhos(no):
    for n in ast.walk(no):
        for campo in ("body", "orelse", "finalbody"):
            corpo = getattr(n, campo, None)
            if isinstance(corpo, list):
                yield corpo


def _chama(no, nome):
    return any(isinstance(x, ast.Call) and getattr(x.func, "id", "") == nome
               for x in ast.walk(no))


def _executa(nos, ns):
    exec(compile(ast.Module(body=list(nos), type_ignores=[]), "main.py", "exec"), ns)


def _laços_de_registro():
    """(laço, instrução seguinte) de cada `for … in _registros_da_leitura(…)`."""
    achados = []
    for corpo in _blocos_com_filhos(_process_job()):
        for k, st in enumerate(corpo):
            if isinstance(st, ast.For) and _chama(st.iter, "_registros_da_leitura"):
                achados.append((st, corpo[k + 1] if k + 1 < len(corpo) else None))
    return achados


class _Log:
    def __init__(self):
        self.linhas = []

    def __call__(self, stage, message, job_id=None, severity="error", **k):
        self.linhas.append((stage, message, job_id, severity))


def test_os_dois_lacos_do_main_registram_a_leitura():
    """PDF e DXF: os dois leem `result["items"]` e os dois perdiam o aninhado."""
    assert len(_laços_de_registro()) == 2, (
        "esperava o registro da leitura nos laços de PDF e de DXF")


def test_o_laco_de_PDF_registra_e_guarda_a_prancha_sem_item():
    pdf = [(f, prox) for f, prox in _laços_de_registro()
           if "_disp" in ast.dump(f.iter)]
    assert len(pdf) == 1, "o registro do laço de PDF sumiu"
    laco, prox = pdf[0]
    assert prox is not None and "_pranchas_sem_item" in ast.dump(prox), (
        "a prancha sem item não é mais guardada pro aviso de cobertura")
    log, lista = _Log(), []
    ns = {"_registros_da_leitura": engine_rules.registros_da_leitura,
          "_log_error": log, "_pranchas_sem_item": lista, "job_id": "ee801b82",
          "_disp": "prancha-F.pdf",
          "result": {"items": [], "_sem_item": {"motivo": "sem-chave-items",
                                                "releu": True},
                     "_releitura": {"motivo": "sem-chave-items", "itens": 0}}}
    _executa([laco, prox], ns)
    assert [l[0] for l in log.linhas] == ["motor:prancha-releitura",
                                          "motor:prancha-sem-item"]
    assert all(l[2] == "ee801b82" and l[3] == "warning" for l in log.linhas)
    assert lista == ["prancha-F.pdf"]
    # e a prancha que deu item não entra na lista
    ns["result"], log.linhas[:] = {"items": [{"description": "x"}]}, []
    _executa([laco, prox], ns)
    assert lista == ["prancha-F.pdf"] and log.linhas == []


def test_o_laco_de_DXF_registra_o_aninhado():
    dxf = [f for f, _ in _laços_de_registro() if "dxf_path" in ast.dump(f.iter)]
    assert len(dxf) == 1, "o registro do laço de DXF sumiu"
    log = _Log()
    out = engine_rules.normalize_items_payload(json.loads(json.dumps(_ANINHADO)))
    _executa([dxf[0]], {"_registros_da_leitura": engine_rules.registros_da_leitura,
                        "_log_error": log, "job_id": "ee801b82", "result": out,
                        "_nome_prancha_bonito": os.path.basename,
                        "dxf_path": "/tmp/prancha-D.dxf"})
    assert [l[0] for l in log.linhas] == ["motor:items-aninhados"]


def _if_do_aviso():
    """(bloco, índice) do `if _pranchas_sem_item:` do fim do process_job."""
    achados = [(corpo, k) for corpo in _blocos_com_filhos(_process_job())
               for k, st in enumerate(corpo)
               if isinstance(st, ast.If) and isinstance(st.test, ast.Name)
               and st.test.id == "_pranchas_sem_item"]
    assert len(achados) == 1, "o aviso da prancha sem item sumiu do process_job"
    return achados[0]


def test_o_aviso_de_cobertura_conta_a_prancha_sem_item():
    corpo, k = _if_do_aviso()
    ifs = [corpo[k]]

    class _PD:
        warnings = ["aviso que já estava"]
    pd = _PD()
    _executa(ifs, {"_pranchas_sem_item": ["prancha-F.pdf"], "project_data": pd,
                   "_aviso_de_prancha_sem_item": engine_rules.aviso_de_prancha_sem_item})
    assert pd.warnings[0] == "aviso que já estava"
    assert len(pd.warnings) == 2 and "prancha-F.pdf" in pd.warnings[1]
    assert "não gerou nenhum item" in pd.warnings[1]


def test_a_lista_nasce_no_mesmo_bloco_antes_do_aviso():
    """Nascer DENTRO de um ramo faria o aviso estourar NameError no job que
    não passa por ele."""
    corpo, k_usa = _if_do_aviso()
    nasce = [k for k, st in enumerate(corpo[:k_usa])
             if isinstance(st, (ast.Assign, ast.AnnAssign))
             and "'_pranchas_sem_item'" in ast.dump(st)]
    assert nasce, "a lista _pranchas_sem_item não nasce no mesmo bloco do aviso"


@pytest.mark.parametrize("resposta, motivo", [
    ({"items": [{"a": 1}]}, None),
    (_ANINHADO, None),
    ({"items": []}, "items-vazio"),
    ([], "items-vazio"),
    ({"project_data": {"items": []}}, "items-vazio"),
    (_SO_KEPT, "sem-chave-items"),
    ({}, "sem-chave-items"),
])
def test_o_motivo_separa_resposta_vazia_de_pergunta_nao_respondida(resposta, motivo):
    assert engine_rules.motivo_da_prancha_sem_item(json.loads(json.dumps(resposta))) == motivo
