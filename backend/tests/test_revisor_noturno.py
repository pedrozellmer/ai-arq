# -*- coding: utf-8 -*-
"""O revisor noturno (19/10/2026): a ficha de cada projeto, a nota de suspeita e os padrões.

Cada motivo tem o caso que DISPARA e o vizinho que NÃO dispara — guarda que só passa não prova nada
([[feedback_teste_com_controle_positivo]]). Os dados são sintéticos, com a forma medida no banco em
19/10 (reject com item_id nulo, `_antes.confidence = 'confirmado'` no selo branco, file_types como
{"dwg": n, "dxf": n, "pdf": n}).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import revisor_noturno as rn  # noqa: E402
from main import recado_digitado, _RECADO_AUTOMATICO  # noqa: E402


def _proj(jid="aaaa0001", **kw):
    p = {"job_id": jid, "created_at": "2026-10-10T12:00:00+00:00", "status": "done",
         "file_types": {"dwg": 1, "dxf": 0, "pdf": 0}, "reprocess_count": 0, "revisao_aberturas": 1}
    p.update(kw)
    return p


def _ficha(proj=None, extra=None, ultima_rodada=None, **fontes):
    proj = proj or _proj()
    extra = extra if extra is not None else {proj["job_id"]: {"linhas_medidas": 10, "linhas_total": 20}}
    fs = rn.montar_fichas(
        [proj], extra, fontes.get("revisoes", []), fontes.get("lotes", []),
        fontes.get("conversas", []), fontes.get("nps", []), fontes.get("erros", []),
        fontes.get("entregaveis", {}), fontes.get("emails", []), recado_digitado,
        ultima_rodada=ultima_rodada)
    assert len(fs) == 1
    return fs[0]


def _codigos(f):
    return {m["codigo"] for m in f["motivos"]}


def _rev(action, item_id=None, conf=None, comment="", quando="2026-10-12T10:00:00+00:00", jid="aaaa0001"):
    edits = {"_antes": {"confidence": conf, "quantity": 0}} if conf else None
    return {"job_id": jid, "item_id": item_id, "action": action, "edits": edits,
            "comment": comment, "reviewed_at": quando}


# ── projeto sem nada: nota zero ───────────────────────────────────────────────────────────────
def test_projeto_que_mediu_e_ninguem_mexeu_tem_nota_zero():
    f = _ficha()
    assert f["nota"] == 0 and f["motivos"] == []
    assert f["novidade"] is False and f["ultimo_sinal_do_cliente"] is None


# ── medido_mexido ─────────────────────────────────────────────────────────────────────────────
def test_mexer_em_item_com_selo_de_medido_pesa_3():
    f = _ficha(revisoes=[_rev("reject", conf="confirmado")])
    assert "medido_mexido" in _codigos(f) and f["nota"] >= 3


def test_mexer_em_item_estimado_nao_e_medido_mexido():
    f = _ficha(revisoes=[_rev("reject", conf="estimado"), _rev("edit", "i1", conf="estimado")])
    assert "medido_mexido" not in _codigos(f)


def test_aprovar_item_medido_nao_e_medido_mexido():
    f = _ficha(revisoes=[_rev("approve", "i1", conf="confirmado")])
    assert "medido_mexido" not in _codigos(f)


# ── recado ────────────────────────────────────────────────────────────────────────────────────
def test_recado_digitado_pelo_cliente_conta():
    f = _ficha(revisoes=[_rev("approve", "i1", comment="separar por tipo, um para cada item")])
    assert "recado" in _codigos(f)


def test_frase_que_a_nossa_tela_escreve_nao_e_recado():
    automatico = next(iter(_RECADO_AUTOMATICO))
    f = _ficha(revisoes=[_rev("approve", "i1", comment=automatico)])
    assert "recado" not in _codigos(f)


def test_recado_antigo_nao_some_quando_o_cliente_aprova_depois():
    f = _ficha(revisoes=[
        _rev("edit", "i1", comment="falta o rodapé", quando="2026-10-12T10:00:00+00:00"),
        _rev("approve", "i1", quando="2026-10-13T10:00:00+00:00"),
    ])
    assert "recado" in _codigos(f)


# ── faltou ────────────────────────────────────────────────────────────────────────────────────
def test_faltou_conta_e_aprovar_nao():
    assert "faltou" in _codigos(_ficha(revisoes=[_rev("faltou")]))
    assert "faltou" not in _codigos(_ficha(revisoes=[_rev("approve", "i1")]))


# ── recusou: mínimo E fração ──────────────────────────────────────────────────────────────────
def test_recusou_muito_e_proporcionalmente_dispara():
    revs = [_rev("reject") for _ in range(rn.RECUSOU_MIN)]
    revs += [_rev("approve", "a%d" % i) for i in range(5)]
    assert "recusou" in _codigos(_ficha(revisoes=revs))


def test_recusou_abaixo_do_minimo_nao_dispara():
    revs = [_rev("reject") for _ in range(rn.RECUSOU_MIN - 1)]
    assert "recusou" not in _codigos(_ficha(revisoes=revs))


def test_recusou_pouco_perto_do_que_aprovou_nao_dispara():
    revs = [_rev("reject") for _ in range(rn.RECUSOU_MIN)]
    revs += [_rev("approve", "a%d" % i) for i in range(30)]   # 5 de 35 = 14%
    assert "recusou" not in _codigos(_ficha(revisoes=revs))


# ── editou: a última de cada item ─────────────────────────────────────────────────────────────
def test_editou_varias_quantidades_dispara():
    revs = [_rev("edit", "i%d" % i) for i in range(rn.EDITOU_MIN)]
    assert "editou" in _codigos(_ficha(revisoes=revs))


def test_mudar_de_ideia_no_mesmo_item_conta_uma_vez():
    revs = [_rev("edit", "i1", quando="2026-10-12T1%d:00:00+00:00" % h) for h in range(5)]
    f = _ficha(revisoes=revs)
    assert f["sinais"]["revisao"]["editou"] == 1
    assert "editou" not in _codigos(f)


def test_editou_e_depois_aprovou_vale_a_ultima():
    f = _ficha(revisoes=[
        _rev("edit", "i1", quando="2026-10-12T10:00:00+00:00"),
        _rev("approve", "i1", quando="2026-10-12T11:00:00+00:00"),
    ])
    assert f["sinais"]["revisao"] == dict(f["sinais"]["revisao"], editou=0, aprovou=1)


# ── revisão em lote ───────────────────────────────────────────────────────────────────────────
def _lote(orig, alt, rem, quando="2026-10-12T10:00:00+00:00"):
    return {"job_id": "aaaa0001", "created_at": quando, "n_originais": orig, "n_mantidos": orig - alt - rem,
            "n_alterados": alt, "n_removidos": rem, "n_adicionados": 0}


def test_planilha_revisada_que_cortou_metade_dispara():
    assert "lote_cortou" in _codigos(_ficha(lotes=[_lote(20, 4, 6)]))


def test_planilha_revisada_que_manteve_quase_tudo_nao_dispara():
    assert "lote_cortou" not in _codigos(_ficha(lotes=[_lote(20, 2, 2)]))


def test_planilha_pequena_demais_nao_diz_nada():
    assert "lote_cortou" not in _codigos(_ficha(lotes=[_lote(rn.LOTE_MIN_ORIGINAIS - 1, 4, 0)]))


def test_vale_a_planilha_revisada_mais_recente():
    f = _ficha(lotes=[_lote(20, 10, 5, "2026-10-12T10:00:00+00:00"),
                      _lote(20, 1, 0, "2026-10-14T10:00:00+00:00")])
    assert "lote_cortou" not in _codigos(f)
    assert f["sinais"]["lote"]["planilhas"] == 2


# ── NPS ───────────────────────────────────────────────────────────────────────────────────────
def test_nps_ate_6_dispara_e_7_nao():
    assert "nps_baixo" in _codigos(_ficha(nps=[{"job_id": "aaaa0001", "score": 6, "created_at": "2026-10-12"}]))
    assert "nps_baixo" not in _codigos(_ficha(nps=[{"job_id": "aaaa0001", "score": 7, "created_at": "2026-10-12"}]))


def test_vale_a_nota_mais_recente():
    f = _ficha(nps=[{"job_id": "aaaa0001", "score": 3, "created_at": "2026-10-11T00:00:00+00:00"},
                    {"job_id": "aaaa0001", "score": 9, "created_at": "2026-10-13T00:00:00+00:00"}])
    assert f["sinais"]["nps"] == 9 and "nps_baixo" not in _codigos(f)


# ── motor ─────────────────────────────────────────────────────────────────────────────────────
def test_cad_que_nao_mediu_nada_dispara():
    f = _ficha(extra={"aaaa0001": {"linhas_medidas": 0, "linhas_total": 30}})
    assert "cad_sem_medida" in _codigos(f)


def test_pdf_que_nao_mediu_nada_e_o_esperado():
    f = _ficha(proj=_proj(file_types={"dwg": 0, "dxf": 0, "pdf": 2}),
               extra={"aaaa0001": {"linhas_medidas": 0, "linhas_total": 30}})
    assert "cad_sem_medida" not in _codigos(f)


def test_cad_com_pdf_junto_nao_entra_em_cad_sem_medida():
    f = _ficha(proj=_proj(file_types={"dwg": 1, "dxf": 0, "pdf": 1}),
               extra={"aaaa0001": {"linhas_medidas": 0, "linhas_total": 30}})
    assert "cad_sem_medida" not in _codigos(f)


def test_projeto_em_erro_dispara_falhou():
    assert "falhou" in _codigos(_ficha(proj=_proj(status="error"), extra={}))
    assert "falhou" not in _codigos(_ficha())


def test_severity_do_error_log_nao_entra_na_nota():
    """71 de 121 projetos tinham linha 'error' em 19/10, inclusive `nps:promoter-alerta`."""
    erros = [{"job_id": "aaaa0001", "stage": "nps:promoter-alerta", "severity": "error"},
             {"job_id": "aaaa0001", "stage": "motor:spline", "severity": "error"}]
    f = _ficha(erros=erros)
    assert f["nota"] == 0
    assert f["sinais"]["motor"]["etapas"] == ["motor:spline", "nps:promoter-alerta"]


def test_perguntou_e_reprocessou_pesam_pouco():
    f = _ficha(proj=_proj(reprocess_count=1),
               conversas=[{"job_id": "aaaa0001", "created_at": "2026-10-12T10:00:00+00:00"}])
    assert _codigos(f) == {"perguntou", "reprocessou"} and f["nota"] == 2


# ── novidade ──────────────────────────────────────────────────────────────────────────────────
def test_novidade_e_sinal_do_cliente_depois_da_rodada_anterior():
    revs = [_rev("approve", "i1", quando="2026-10-15T10:00:00+00:00")]
    assert _ficha(revisoes=revs, ultima_rodada="2026-10-15T06:00:00+00:00")["novidade"] is True
    assert _ficha(revisoes=revs, ultima_rodada="2026-10-16T06:00:00+00:00")["novidade"] is False


def test_entregavel_mexido_depois_da_rodada_e_novidade():
    ent = {"cronograma": [{"job_id": "aaaa0001", "quando": "2026-10-16T09:00:00+00:00"}]}
    f = _ficha(entregaveis=ent, ultima_rodada="2026-10-16T06:00:00+00:00")
    assert f["novidade"] is True and f["sinais"]["entregaveis"]["cronograma"] is True
    assert f["sinais"]["entregaveis"]["memorial"] is False


def test_primeira_rodada_marca_novidade_so_onde_o_cliente_fez_algo():
    assert _ficha(revisoes=[_rev("approve", "i1")])["novidade"] is True
    assert _ficha()["novidade"] is False


# ── a ficha não leva texto do cliente ─────────────────────────────────────────────────────────
def test_a_ficha_guarda_contagem_e_nao_o_texto_do_recado():
    texto = "texto único do cliente 7f3a"
    f = _ficha(revisoes=[_rev("edit", "i1", comment=texto)],
               conversas=[{"job_id": "aaaa0001", "question": texto, "created_at": "2026-10-12"}])
    assert texto not in repr(f)


# ── ordem da fila ─────────────────────────────────────────────────────────────────────────────
def test_a_fila_vem_da_maior_nota_e_novidade_desempata():
    projs = [_proj("j1"), _proj("j2"), _proj("j3")]
    extra = {j: {"linhas_medidas": 5, "linhas_total": 5} for j in ("j1", "j2", "j3")}
    revs = [_rev("faltou", jid="j2", quando="2026-10-16T10:00:00+00:00"),
            _rev("faltou", jid="j3", quando="2026-10-14T10:00:00+00:00")]
    fs = rn.montar_fichas(projs, extra, revs, [], [], [], [], {}, [], recado_digitado,
                          ultima_rodada="2026-10-15T06:00:00+00:00")
    assert [f["job_id"] for f in fs] == ["j2", "j3", "j1"]


# ── padrões ───────────────────────────────────────────────────────────────────────────────────
def test_padrao_separa_etapa_que_doi_de_etapa_que_so_aparece():
    projs = [_proj("p%d" % i) for i in range(6)]
    extra = {p["job_id"]: {"linhas_medidas": 5, "linhas_total": 5} for p in projs}
    erros = [{"job_id": p["job_id"], "stage": "motor:ruido"} for p in projs]
    erros += [{"job_id": j, "stage": "motor:doi"} for j in ("p0", "p1")]
    revs = [_rev("faltou", jid=j) for j in ("p0", "p1")]
    revs += [_rev("approve", "x", jid="p2")]
    fs = rn.montar_fichas(projs, extra, revs, [], [], [], erros, {}, [], recado_digitado)
    pd = {d["etapa"]: d for d in rn.padroes(fs)}
    assert pd["motor:doi"] == dict(pd["motor:doi"], projetos=2, com_retorno=2, com_reacao=2)
    assert pd["motor:ruido"] == dict(pd["motor:ruido"], projetos=6, com_retorno=3, com_reacao=2)
    assert sorted(pd["motor:doi"]["exemplos"]) == ["p0", "p1"]


def test_pergunta_e_retorno_mas_nao_reacao():
    projs = [_proj("q1")]
    fs = rn.montar_fichas(projs, {"q1": {"linhas_medidas": 1, "linhas_total": 1}}, [], [],
                          [{"job_id": "q1", "created_at": "2026-10-12"}], [],
                          [{"job_id": "q1", "stage": "motor:x"}], {}, [], recado_digitado)
    pd = rn.padroes(fs)[0]
    assert (pd["com_retorno"], pd["com_reacao"]) == (1, 0)


def test_carimbo_sem_fuso_misturado_com_fuso_nao_derruba_a_ficha():
    f = _ficha(revisoes=[_rev("approve", "i1", quando="2026-10-12T10:00:00+00:00")],
               nps=[{"job_id": "aaaa0001", "score": 8, "created_at": "2026-10-13"}])
    assert f["ultimo_sinal_do_cliente"].startswith("2026-10-13")


def test_formato():
    assert rn.formato({"dwg": 2, "dxf": 0, "pdf": 0}) == "CAD"
    assert rn.formato({"dwg": 0, "dxf": 1, "pdf": 3}) == "CAD+PDF"
    assert rn.formato({"pdf": 1}) == "PDF"
    assert rn.formato(None) == ""
