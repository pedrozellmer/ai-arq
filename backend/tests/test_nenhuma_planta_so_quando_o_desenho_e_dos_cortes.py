# -*- coding: utf-8 -*-
""""Esta prancha tem corte e NENHUMA planta" só quando o desenho é dos cortes.

🩸 28/09/2026 (job dd52081b): a leitura por folha reconheceu 1 corte e deixou
15 desenhos sem tipo — as 4 plantas baixas do prédio. O texto da IA disse
"NENHUMA planta", ela repetiu isso ao cliente e deixou alvenaria, pintura e
forro em branco. A folha de cortes de verdade (p0003/p0004, 25/09) não tem
nada fora das vistas; a do prédio (dd52081b) tinha 22.450 m e 560 blocos fora delas.
"""
import os
import sys

import ezdxf

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402


def _folhas(neutro, vista, sem_tipo=15):
    return {"aplicada": True,
            "desenhos_lista": [{"tipo": "vista", "titulo": "CORTE BB"}]
            + [{"tipo": "", "titulo": ""} for _ in range(sem_tipo)],
            "medida": {"vista": vista, "neutro": neutro,
                       "sem_folha": {"m": 0, "m2": 0, "blocos": 0}}}


class _Ex:
    def __init__(self, folhas):
        self.folhas = folhas


PREDIO = ({"m": 22450.8, "m2": 7545.2, "blocos": 560}, {"m": 73.4, "m2": 3.4, "blocos": 4})
CORTES = ({"m": 0.0, "m2": 0.0, "blocos": 0}, {"m": 693.8, "m2": 31.3, "blocos": 3})
FORRO = ({"m": 573.4, "m2": 148.3, "blocos": 41}, {"m": 294.0, "m2": 9.4, "blocos": 14})


def test_o_predio_com_plantas_sem_titulo_nao_e_folha_de_cortes():
    assert not dx.prancha_so_de_vista(_Ex(_folhas(*PREDIO)))


def test_a_planta_de_forro_nao_e_folha_de_cortes():
    assert not dx.prancha_so_de_vista(_Ex(_folhas(*FORRO, sem_tipo=9)))


def test_CONTROLE_a_folha_de_cortes_de_verdade_segue():
    assert dx.prancha_so_de_vista(_Ex(_folhas(*CORTES, sem_tipo=0)))


def test_CONTROLE_sem_medida_por_folha_fica_como_era():
    f = _folhas(*PREDIO)
    f.pop("medida")
    assert dx.prancha_so_de_vista(_Ex(f))


def test_menos_linha_mas_mais_blocos_fora_dos_cortes_tambem_nao():
    neutro = {"m": 100.0, "m2": 5.0, "blocos": 41}
    assert not dx.prancha_so_de_vista(_Ex(_folhas(neutro, CORTES[1])))


def _prompt(tmp_path, folhas):
    doc = ezdxf.new("R2018")
    doc.modelspace().add_line((0, 0), (5, 0))
    p = str(tmp_path / "x.dxf")
    doc.saveas(p)
    ex = dx.extract_dxf(p)
    ex.folhas = folhas
    return ex.to_structured_prompt()


def test_o_texto_da_ia_nao_afirma_nenhuma_planta_no_predio(tmp_path, monkeypatch):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    assert "NENHUMA planta" not in _prompt(tmp_path, _folhas(*PREDIO))


def test_CONTROLE_o_texto_da_ia_avisa_na_folha_de_cortes(tmp_path, monkeypatch):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    assert "NENHUMA planta" in _prompt(tmp_path, _folhas(*CORTES, sem_tipo=0))
