# -*- coding: utf-8 -*-
"""O layer que diz SÓ o estado da reforma ("a construir", "DEMOLIR") é parede.

🩸 06/10/2026 — reforma de escritório: "demolir" e "a construir" eram a parede a
demolir e a nova, em duas faces, e o nome não dizia "parede": a correção
face → eixo não rodava. "Demolição de paredes = 91,95 ml" contra ~48 pelo eixo.

🔑 Por TOKEN: todo pedaço do nome é o estado da obra ou um prefixo genérico.
🪤 Com objeto no nome não é parede: o Archicad põe "Novo_" em TODO layer.

🪤 Nomes FICTÍCIOS ou de convenção (repositório público, regra nº6).
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
from engine_rules import layer_e_parede  # noqa: E402


@pytest.mark.parametrize("nome", [
    "a construir", "A CONSTRUIR", "construir", "construção", "DEMOLIR", "demolir", "ARQ-DEMOLIR",
    "PDF_Arq Construir", "PDF2_Arq Demolir", "ARQ_À REMOVER", "ARQ_remover", "LB_DEMOLIR", "REFORMA",
    "EXECUTAR", "RETIRAR", "NOVO", "novo",
])
def test_o_nome_que_e_so_o_estado_da_reforma_e_parede(nome):
    assert layer_e_parede(nome) is True


@pytest.mark.parametrize("nome", [
    "Novo_Portas_Caneta_No__7",           # o Archicad: "Novo_" em todo layer
    "Novo_ARQ - Pergolado_Caneta_No__3",
    "Novo_EST - Laje_Caneta_No__5",
    "Demolido_EST - Pilar_Caneta_No__9",
    "BRISE_EXECUTAR",
    "MOBILIÁRIO NOVO",
    "HACHURA A CONSTRUIR",
    "ESQUADRIAS REMOVIDAS",
    "PISO A DEMOLIR",
    "FORRO A DEMOLIR",
    "DEMOLIR PISO",
    "ELE-ELETROCALHA-NOVO",
    "Novo_0",                                       # número solto não é prefixo
    "EXISTENTE",                                    # sem caso medido: fica de fora
    "COTA DEMOLIR",
    "ARQ",                                          # só prefixo, sem o estado
    "PDF_Arq",
])
def test_CONTROLE_com_objeto_no_nome_nao_e_parede(nome):
    assert layer_e_parede(nome) is False


@pytest.mark.parametrize("nome", ["PAREDE A CONSTRUIR", "ALVENARIA NOVA", "DRYWALL NOVO", "A-WALL"])
def test_CONTROLE_o_que_ja_era_parede_continua(nome):
    assert layer_e_parede(nome) is True


def _ler(tmp_path, desenha):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    desenha(doc.modelspace())
    p = str(tmp_path / "reforma.dxf")
    doc.saveas(p)
    return dx.extract_dxf(p)


def _linhas(msp, layer, x0, x1, ys):
    for y in ys:
        msp.add_line((x0, y), (x1, y), dxfattribs={"layer": layer})


def test_o_caso_a_parede_a_demolir_mede_pelo_eixo(tmp_path):
    """Paredes a demolir de 15 cm, nas duas faces: 4 × 10 m de parede, 80 m de linha."""
    ex = _ler(tmp_path, lambda m: [_linhas(m, "demolir", 0, 10, (3.0 * i, 3.0 * i + 0.15)) for i in range(4)])
    assert ex.get_walls_by_layer()["demolir"] == pytest.approx(40.0, abs=0.1)


def test_a_demolir_em_parte_em_duas_linhas_fica_sem_selo(tmp_path):
    """O layer de demolição com ~1/3 em duas faces (o resto, linha única): a soma
    pode contar as duas faces — zona cinza, sem selo de comprimento."""
    def d(m):
        _linhas(m, "ARQ-DEMOLIR", 0, 10, (0.0, 0.15))
        for i in range(4):
            _linhas(m, "ARQ-DEMOLIR", 0, 10, (5.0 + 3.0 * i,))
    ex = _ler(tmp_path, d)
    assert "ARQ-DEMOLIR" in (ex.metadata.get("parede_zona_cinza") or {}), ex.metadata.get("parede_zona_cinza")


def test_CONTROLE_o_brise_em_duas_linhas_fica(tmp_path):
    ex = _ler(tmp_path, lambda m: [_linhas(m, "BRISE_EXECUTAR", 0, 10, (3.0 * i, 3.0 * i + 0.15)) for i in range(4)])
    assert ex.get_walls_by_layer()["BRISE_EXECUTAR"] == pytest.approx(80.0, abs=0.1)
