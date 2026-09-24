# -*- coding: utf-8 -*-
"""As verbas gerais de obra saem numa linha só, a definir (decisão do Pedro, 24/09).

📊 90 dias: 25 das 440 rejeições de cliente eram administração local,
mobilização, limpeza final, proteção… sugeridas como "1 vb" em várias
pranchas; dois clientes em dois dias apagaram as MESMAS quatro, uma a uma.
"""
import ast
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import main  # noqa: E402
from engine_rules import e_verba_preliminar as e_verba  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402


def _it(desc, unit="vb", q=1.0, conf="estimado", obs="", disc="Serviços Preliminares"):
    return BudgetItem(item_num="1", description=desc, unit=unit, quantity=q, observations=obs,
                      ref_sheet="p.dxf", confidence=Confidence(conf), discipline=disc)


@pytest.mark.parametrize("desc", [
    "Administração local de obra — mobilização, desmobilização e gerenciamento",
    "Limpeza final de obra (várias variantes)",
    "Mobilização e desmobilização de obra — transporte de equipe",
    "Serviços Preliminares — Mobilização, proteção de áreas e canteiro",
    "Proteção de áreas existentes durante a obra — pisos, paredes",
    "Canteiro de obras — tapumes e barracão",
    "Placa de obra — chapa galvanizada",
])
def test_verba_geral_de_obra_e_reconhecida(desc):
    assert e_verba(desc, "vb")


@pytest.mark.parametrize("desc, unit, conf, obs", [
    ("Placa de obra — chapa galvanizada", "un", "estimado", ""),          # não é verba
    ("Demolição e remoção de elementos existentes", "vb", "estimado", ""),  # sai do desenho
    ("Instalações provisórias — incluindo sprinkler provisório", "vb", "estimado", ""),  # embala incêndio
    ("Pintura de proteção de esquadrias", "vb", "estimado", ""),           # é pintura
    ("Remoção e descarte de bancada — limpeza final", "vb", "estimado", ""),  # nome = remoção
    ("Administração local de obra", "vb", "confirmado", ""),               # medido: não toca
    ("Administração local de obra", "vb", "estimado", "✏️ REVISADO POR VOCÊ"),  # do cliente
    # a palavra de verba só na CAUDA não faz a linha ser verba geral
    ("Bancada de granito — com limpeza final inclusa", "vb", "estimado", ""),
])
def test_CONTROLE_o_que_nunca_entra_na_linha_unica(desc, unit, conf, obs):
    assert not e_verba(desc, unit, conf, obs)


def test_quatro_verbas_viram_UMA_linha_sem_quantidade(monkeypatch):
    monkeypatch.delenv("VERBAS_NUMA_LINHA", raising=False)
    itens = [_it("Porcelanato — sala", unit="m²", q=24.92, disc="Pisos e Rodapés"),
             _it("Administração local de obra — equipe"),
             _it("Limpeza final de obra (várias variantes)", q=5),
             _it("Mobilização e desmobilização de obra — transporte", q=3),
             _it("Tomada baixa", unit="un", q=16, disc="Instalações Elétricas e Dados"),
             _it("Proteção de áreas existentes durante a obra")]
    n = main._juntar_verbas_preliminares(itens)
    assert n == 4
    assert len(itens) == 3
    unica = [i for i in itens if "verba a definir" in i.description]
    assert len(unica) == 1 and unica[0].quantity == 0 and unica[0].unit == "vb"
    assert "Administração local" in unica[0].observations
    assert itens[1] is unica[0], "a linha única fica no lugar da 1ª verba"
    assert [i.description for i in itens][0].startswith("Porcelanato")


def test_CONTROLE_sem_verba_nada_muda():
    itens = [_it("Porcelanato — sala", unit="m²", q=24.92)]
    assert main._juntar_verbas_preliminares(itens) == 0 and len(itens) == 1


def test_a_chave_desliga_sem_deploy(monkeypatch):
    monkeypatch.setenv("VERBAS_NUMA_LINHA", "0")
    itens = [_it("Administração local de obra"), _it("Limpeza final de obra")]
    assert main._juntar_verbas_preliminares(itens) == 0 and len(itens) == 2


def test_o_motor_chama_depois_da_administracao_local():
    fonte = open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8").read()
    fn = next(n for n in ast.walk(ast.parse(fonte))
              if isinstance(n, ast.FunctionDef) and n.name == "process_job")
    def _l(nome):
        return [c.lineno for c in ast.walk(fn) if isinstance(c, ast.Call)
                and (getattr(c.func, "id", None) or getattr(c.func, "attr", None)) == nome]
    al, vp = _l("_juntar_admin_local"), _l("_juntar_verbas_preliminares")
    assert al and vp and min(al) < min(vp), (al, vp)
