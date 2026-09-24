# -*- coding: utf-8 -*-
"""A releitura NÃO traz de volta o que o cliente rejeitou (regra dura nº7).

🩸 24/09/2026, job b6df4f3d: 4 linhas rejeitadas às 17:23 voltaram no filhote
das 17:35 — a fusão só lia `action=edit`. 90 dias: 104 releituras, 6 com
rejeição no pai, 19 linhas que voltariam.

🪤 Aqui o erro é APAGAR (invisível pro cliente); duplicar ele vê e rejeita de
novo. Cada controle abaixo é uma forma de apagar a linha ERRADA.
"""
import ast
import os
import sys
from types import SimpleNamespace as NS

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import main  # noqa: E402
from engine_rules import par_da_linha_rejeitada as par  # noqa: E402


def _nova(desc, unit="vb", q=1.0, obs=""):
    return NS(description=desc, unit=unit, quantity=q, observations=obs)


def _rej(desc, unit="vb", q=1.0):
    return {"description": desc, "unit": unit, "quantity": q}


LEITURA_NOVA = [
    _nova("Administração local de obra — mobilização, desmobilização e gerenciamento do canteiro"),
    _nova("Limpeza final de obra (várias variantes)", q=5),
    _nova("Mobilização e desmobilização de obra — transporte de equipe, ferramentas e materiais", q=3),
    _nova("Serviços Preliminares — Mobilização, proteção de áreas e instalação de canteiro de obras"),
    _nova("Porcelanato Portobello Posto 12 — sala, cozinha e quarto", unit="m²", q=24.92),
]


# ── o caso real: a IA reescreveu a cauda, o nome do serviço é o mesmo ──────
def test_administracao_local_casa_pelo_nome_do_servico():
    r = _rej("Administração local de obra — equipe de gestão, segurança e apoio")
    assert par(r, LEITURA_NOVA) == 0


def test_limpeza_final_casa_mesmo_com_outra_quantidade_de_verba():
    assert par(_rej("Limpeza final de obra (várias variantes)", q=3), LEITURA_NOVA) == 1


def test_mobilizacao_casa_pela_maioria_das_palavras():
    r = _rej("Mobilização e instalação de canteiro de obras — proteção de áreas existentes")
    assert par(r, LEITURA_NOVA) == 3


def test_CONTROLE_sem_par_seguro_a_linha_FICA():
    r = _rej("Proteção de áreas existentes durante a obra — proteção de pisos, paredes e mobiliário")
    assert par(r, LEITURA_NOVA) is None


# ── controles: cada um é um jeito de apagar a linha errada ────────────────
def test_CONTROLE_codigo_diferente_nao_casa():
    novas = [_nova("Porta de madeira PM2 — semi-oca", unit="un", q=4)]
    assert par(_rej("Porta de madeira PM1 — semi-oca", unit="un", q=4), novas) is None


def test_CONTROLE_quantidade_diferente_nao_casa_fora_de_verba():
    """Piso da sala rejeitado não pode apagar o piso da cozinha."""
    novas = [_nova("Piso porcelanato — cozinha", unit="m²", q=7.1)]
    assert par(_rej("Piso porcelanato — sala", unit="m²", q=7.8), novas) is None


def test_mesma_quantidade_fora_de_verba_casa():
    novas = [_nova("Piso porcelanato Portobello — sala", unit="m²", q=7.8)]
    assert par(_rej("Piso porcelanato Portobello — sala de estar", unit="m²", q=7.8), novas) == 0


def test_CONTROLE_unidade_diferente_nao_casa():
    novas = [_nova("Administração local de obra — gestão", unit="mês", q=1)]
    assert par(_rej("Administração local de obra — gestão"), novas) is None


def test_CONTROLE_linha_que_o_cliente_EDITOU_nunca_sai():
    novas = [_nova("Administração local de obra — gestão", obs="✏️ REVISADO POR VOCÊ — …")]
    assert par(_rej("Administração local de obra — gestão"), novas) is None


def test_CONTROLE_empate_nao_adivinha():
    novas = [_nova("Limpeza final de obra — interna"), _nova("Limpeza final de obra — externa")]
    assert par(_rej("Limpeza final de obra — geral"), novas) is None


def test_CONTROLE_uma_linha_nova_so_serve_a_uma_rejeicao():
    assert par(_rej("Limpeza final de obra (várias variantes)"), LEITURA_NOVA, usados={1}) is None


# ── o caminho do motor, com o banco de dublê ───────────────────────────────
def _banco(monkeypatch, rejeicoes, vivos=(), status=200):
    def _svc(metodo, tabela, params=None, **k):
        return status, rejeicoes
    def _tudo(tabela, params=None, **k):
        return 200, [{"id": v} for v in vivos]
    monkeypatch.setattr(main, "_supa_rest_service", _svc)
    monkeypatch.setattr(main, "_supa_rest_tudo", _tudo)


def _r(iid, desc, unit="vb", q=1.0):
    return {"item_id": iid, "edits": {"_antes": {"description": desc, "unit": unit, "quantity": q}}}


def test_o_motor_tira_as_rejeitadas(monkeypatch):
    _banco(monkeypatch, [_r("a", "Administração local de obra — equipe de gestão"),
                         _r("b", "Limpeza final de obra (várias variantes)", q=3)])
    itens, res = main._tirar_rejeitadas_pelo_cliente(list(LEITURA_NOVA), "pai1")
    assert res["tiradas"] == 2 and len(itens) == 3, res
    assert not any("Administração" in i.description for i in itens)


def test_CONTROLE_rejeicao_DESFEITA_nao_tira(monkeypatch):
    """O item ainda existe no pai: o cliente voltou atrás."""
    _banco(monkeypatch, [_r("a", "Administração local de obra — equipe de gestão")], vivos=("a",))
    itens, res = main._tirar_rejeitadas_pelo_cliente(list(LEITURA_NOVA), "pai1")
    assert res["tiradas"] == 0 and res["desfeitas"] == 1 and len(itens) == 5


def test_CONTROLE_banco_fora_do_ar_nao_tira_nada(monkeypatch):
    _banco(monkeypatch, None, status=503)
    itens, res = main._tirar_rejeitadas_pelo_cliente(list(LEITURA_NOVA), "pai1")
    assert len(itens) == 5 and res.get("erro_leitura") == "HTTP 503"


def test_a_chave_desliga_sem_deploy(monkeypatch):
    monkeypatch.setenv("RELEITURA_RESPEITA_REJEICAO", "0")
    _banco(monkeypatch, [_r("a", "Administração local de obra — equipe de gestão")])
    itens, res = main._tirar_rejeitadas_pelo_cliente(list(LEITURA_NOVA), "pai1")
    assert len(itens) == 5 and res["rejeicoes"] == 0


# ── call site: roda DEPOIS das edições e refaz a planilha ─────────────────
def test_o_motor_chama_depois_da_fusao_e_refaz_a_planilha():
    fonte = open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8").read()
    fn = next(n for n in ast.walk(ast.parse(fonte))
              if isinstance(n, ast.FunctionDef) and n.name == "process_job")
    def _l(nome):
        return [c.lineno for c in ast.walk(fn) if isinstance(c, ast.Call)
                and (getattr(c.func, "id", None) or getattr(c.func, "attr", None)) == nome]
    fus, rej = _l("_fundir_revisoes_do_cliente"), _l("_tirar_rejeitadas_pelo_cliente")
    assert fus and rej and min(fus) < min(rej), (fus, rej)
    assert '_fusao.get("rejeitadas_tiradas")' in fonte
