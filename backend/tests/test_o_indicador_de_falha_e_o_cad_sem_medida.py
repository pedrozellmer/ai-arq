# -*- coding: utf-8 -*-
"""O indicador de falha que importa: CAD que concluiu sem UMA linha medida.

🩸 18/09/2026 — item 10 da fila. Medido antes de escrever:

  · "deu erro" (status=error) é ~5% — e era o único "indicador de falha";
  · CAD concluído sem nenhuma linha medida: **23 de 79 em 60 dias (29,1%)**,
    17 contas na vida toda — e não aparecia como falha em lugar nenhum;
  · PDF sem medida é REGRA (não carrega geometria), por isso o recorte é CAD;
  · dos 23, 7 ganharam filhote, 6 filhotes mediram, mas só **3 foram
    LIBERADOS** ao cliente — só esses descontam: filhote que mediu e ficou
    guardado não mudou o que o cliente recebeu.

E uma frase FALSA no mesmo bloco: "o reserva lê texto mas não mede". Medido:
o libredwg mediu em **40 de 56** projetos (71%, igual ao conversor principal).
A nota agora lê os números da RPC (`plano_b`), pra nunca mais envelhecer
calada — a mesma lição de [[feedback_numero_velho_de_documento_mente]].

A RPC `admin_qualidade_semanal` ganhou `cad_60d` e `plano_b` (aplicada no
banco; cópia comentada em `migrations_pendentes/`). Aqui se cobra a TELA,
rodando o JavaScript real no dukpy: com os campos novos ela diz o número; sem
eles (RPC velha) ela diz que não tem dado — nunca inventa e nunca some.

🚫 Não cobre: a SQL da RPC (a bancada não roda SQL — conferida contra o banco
no dia: cad_60d = 84/26/3/23, plano_b = 43/61 na definição da RPC, que não
exclui as contas de trial como a minha medição fazia).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _jsbancada import funcao_js, motor  # noqa: E402

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ADMIN = os.path.join(_RAIZ, "admin.html")


def _js():
    js = motor("true;")
    for nome in ("linhaCad60d", "notaPlanoB", "renderQualidadeSemanal"):
        js.evaljs(funcao_js(nome, _ADMIN))
    return js


def _semana(**kw):
    base = {"semana": "2026-09-14", "finalizados": 4, "mediu": 2, "sem_medir": 1, "erro": 1,
            "itens": 40, "itens_medidos": 10, "itens_zerados": 5, "resgatados": 0,
            "min_mediana": 3.5, "nm_pdf": 0, "nm_cad_planob": 1, "nm_cad_outro": 0,
            "clientes": 3, "clientes_novos": 1, "clientes_voltaram": 2}
    base.update(kw)
    return base


def _dados(**extra):
    d = {"semanas": [_semana(semana="2026-09-07"), _semana()],
         "por_formato": [{"formato": "DXF", "total": 10, "concluiu": 9, "mediu": 7}],
         "retencao": {"clientes": 5, "voltaram_outra_sem": 2, "so_um_projeto": 3,
                      "media_projetos": 1.4, "voltaram_outro_dia": 2}}
    d.update(extra)
    return d


# ── o indicador ─────────────────────────────────────────────────────────────

def test_o_indicador_diz_o_liquido_e_o_bruto_e_o_refeito_liberado():
    js = _js()
    out = js.evaljs("linhaCad60d(%s)" % json.dumps(
        {"dias": 60, "finalizados": 79, "sem_medir": 23, "refeito_mediu": 3, "sem_medir_liquido": 20}))
    assert "20 de 79" in out and "25%" in out, out
    assert "<b>3</b>" in out and "liberado" in out, out
    assert "bruto: 23 de 79" in out and "29%" in out, out


def test_sem_refeito_liberado_o_indicador_nao_inventa_desconto():
    js = _js()
    out = js.evaljs("linhaCad60d(%s)" % json.dumps(
        {"dias": 60, "finalizados": 10, "sem_medir": 4, "refeito_mediu": 0, "sem_medir_liquido": 4}))
    assert "4 de 10" in out and "40%" in out, out
    assert "liberado" not in out or "nenhum refeito liberado" in out, out


def test_CONTROLE_sem_o_campo_a_tela_diz_que_NAO_tem_dado_e_nao_some():
    """🪤 RPC velha (sem `cad_60d`) não pode virar '0 de 0' nem sumir calada."""
    js = _js()
    for vazio in ("null", "undefined", "{}", '{"finalizados": 0}'):
        out = js.evaljs("linhaCad60d(%s)" % vazio)
        assert "sem dado" in out, (vazio, out)
        assert "de 0" not in out, (vazio, out)


def test_a_cor_acompanha_a_gravidade():
    js = _js()
    ruim = js.evaljs("linhaCad60d(%s)" % json.dumps({"finalizados": 100, "sem_medir": 30, "refeito_mediu": 0, "sem_medir_liquido": 30}))
    ok = js.evaljs("linhaCad60d(%s)" % json.dumps({"finalizados": 100, "sem_medir": 5, "refeito_mediu": 0, "sem_medir_liquido": 5}))
    assert "text-red-700" in ruim and "text-emerald-700" in ok, (ruim[:200], ok[:200])


# ── a frase do leitor reserva ───────────────────────────────────────────────

def test_a_nota_do_plano_B_le_o_numero_da_RPC():
    js = _js()
    out = js.evaljs("notaPlanoB(%s)" % json.dumps({"total": 56, "mediu": 40}))
    assert "40 de 56" in out and "71%" in out and "mede" in out, out


def test_CONTROLE_sem_numero_a_nota_NAO_afirma_que_nao_mede():
    """A frase velha afirmava 'lê texto mas não mede' — falsa em 40 de 56."""
    js = _js()
    for vazio in ("null", "{}", '{"total": 0}'):
        out = js.evaljs("notaPlanoB(%s)" % vazio)
        assert "não mede" not in out and "nao mede" not in out, (vazio, out)
        assert "leu" in out, out


# ── a tela inteira, com e sem os campos novos ───────────────────────────────

def test_a_tela_inteira_mostra_o_indicador_e_a_nota_viva():
    js = _js()
    html = js.evaljs("renderQualidadeSemanal(%s)" % json.dumps(_dados(
        cad_60d={"dias": 60, "finalizados": 79, "sem_medir": 23, "refeito_mediu": 3, "sem_medir_liquido": 20},
        plano_b={"total": 56, "mediu": 40})))
    assert "CAD sem medida" in html and "20 de 79" in html, html[:300]
    assert "40 de 56" in html, "a nota do plano B não leu a RPC"
    assert "lê texto mas não mede" not in html, "a frase falsa voltou"


def test_CONTROLE_a_tela_inteira_com_a_RPC_velha_continua_de_pe():
    js = _js()
    html = js.evaljs("renderQualidadeSemanal(%s)" % json.dumps(_dados()))
    assert "Qualidade por semana" in html
    assert "sem dado" in html, "sem cad_60d a tela tem que DIZER, não sumir"
    assert "lê texto mas não mede" not in html
