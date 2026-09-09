# -*- coding: utf-8 -*-
"""O aviso que a IA escreve tem que CHEGAR no projeto — os dois laços colhiam mal.

🩸 09/09/2026. A mesma mesclagem do `project_data` existia em DOIS laços vivos
do `main.py` e eles DIVERGIRAM:

    campo                        DXF/DWG    PDF
    áreas, name, new_rooms...    colhe      colhe
    workstations, departments    DESCARTA   colhe
    warnings                     DESCARTA   DESCARTA

🚨 O `warnings` é o que doía. A IA DETECTA que o cliente mandou só a prancha de
elevações e não a planta baixa com o quadro de especificações, e escreve o aviso
pedindo o arquivo que falta — e os dois laços jogavam fora.

🪤 E o aparato existia dos DOIS lados do buraco: o prompt PEDE o aviso
(`analyzer.py`, PROMPT_DETALHE_AMBIENTE), o `models.py` tem o campo, o
`spreadsheet.py` tem o bloco "⚠ AVISOS DO MOTOR — REVISAR" na capa, o painel
acende "precisa de complemento" e o e-mail tem linha pra ele. **Só o meio
faltava.** Quem colhia era a `analyze_all_sheets` — que era MORTA, e foi apagada
hoje.

🪤 `workstations`/`departments`: o prompt do DXF PEDE os dois, o laço
descartava, e a capa da planilha tem campo. O MESMO projeto saía COM em PDF e
SEM em DWG.

🔑 Por que o guarda antigo não pegou: `test_avisos_chegam_ao_cliente.py` monta
`ProjetoFalso(warnings=[...])` e mede só a ENTREGA (e-mail, planilha) a partir
de avisos JÁ INJETADOS. Nenhum teste exercitava quem deveria COLHÊ-LOS.
Ver [[project_guardas_cegos_medidos_20260906]].
"""
import ast
import io
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from engine_rules import mesclar_project_data  # noqa: E402


class _Projeto:
    """O mínimo que a mesclagem toca — espelha o `ProjectData`."""

    def __init__(self):
        self.name = ""
        self.address = ""
        self.architect = ""
        self.workstations = 0
        self.departments = []
        self.demolition_notes = []
        self.new_rooms = []
        self.kept_elements = []
        self.warnings = []


def _sf(v):
    return float(str(v).replace(",", ".").replace("m²", "").strip())


# ══════════════════════════════════════════════════════════════════════════
#  O que estava sendo jogado fora
# ══════════════════════════════════════════════════════════════════════════
def test_o_AVISO_da_IA_chega_no_projeto():
    """🩸 O defeito em pessoa: este aviso morria nos dois laços."""
    p = _Projeto()
    mesclar_project_data(p, {"warnings": [
        "Pr X: códigos numéricos visíveis sem o quadro de especificações. "
        "Recomendamos subir também a PLANTA BAIXA"]}, sf=_sf)
    assert len(p.warnings) == 1, p.warnings
    assert "PLANTA BAIXA" in p.warnings[0]


def test_avisos_de_PRANCHAS_diferentes_ACUMULAM():
    """🪤 Uma prancha por chamada. Sobrescrever perderia o aviso da anterior —
    e é justamente o cliente que manda várias pranchas quem mais precisa."""
    p = _Projeto()
    mesclar_project_data(p, {"warnings": ["aviso da prancha 1"]}, sf=_sf)
    mesclar_project_data(p, {"warnings": ["aviso da prancha 2"]}, sf=_sf)
    assert p.warnings == ["aviso da prancha 1", "aviso da prancha 2"]


def test_workstations_e_departments_chegam():
    """🪤 O prompt do DXF PEDE os dois e o laço descartava. A capa da planilha
    tem campo pra eles — o mesmo projeto saía com em PDF e sem em DWG."""
    p = _Projeto()
    mesclar_project_data(p, {"workstations": "12 un",
                             "departments": [{"nome": "Marketing", "n": 8}]},
                         sf=_sf)
    assert p.workstations == 12
    assert p.departments == [{"nome": "Marketing", "n": 8}]


def test_CONTROLE_campo_ausente_NAO_zera_o_que_ja_havia():
    """🧪 O outro lado: uma mesclagem que sobrescrevesse com vazio apagaria o
    que a prancha anterior trouxe, e passaria em todos os testes acima."""
    p = _Projeto()
    mesclar_project_data(p, {"workstations": "12", "name": "Obra A",
                             "warnings": ["a"]}, sf=_sf)
    mesclar_project_data(p, {}, sf=_sf)                      # prancha sem nada
    mesclar_project_data(p, {"warnings": []}, sf=_sf)        # lista vazia
    assert p.workstations == 12
    assert p.name == "Obra A"
    assert p.warnings == ["a"]


def test_o_PRIMEIRO_nome_manda_e_os_seguintes_nao_atropelam():
    p = _Projeto()
    mesclar_project_data(p, {"name": "Obra A"}, sf=_sf)
    mesclar_project_data(p, {"name": "Detalhe de banheiro"}, sf=_sf)
    assert p.name == "Obra A"


def test_as_areas_ENTRAM_na_votacao_e_nao_sobrescrevem():
    """🔑 A área vai pro consenso (moda), não pro campo — a prancha de detalhe
    com valor errado não pode apagar a leitura boa de outra."""
    p = _Projeto()
    leituras, registrado = {}, []
    for v in ("135,4", "270", "135,4"):
        mesclar_project_data(p, {"total_area": v}, leituras,
                             lambda o, c: registrado.append((o, c)),
                             "ia-dxf", _sf)
    assert leituras["total_area"] == [135.4, 270.0, 135.4]
    assert registrado == [("ia-dxf", "total_area")] * 3


@pytest.mark.parametrize("lixo", [None, [], "texto", 42])
def test_resposta_torta_da_IA_nao_derruba_o_projeto(lixo):
    """🪤 Isto roda DENTRO do processamento do cliente: estourar aqui mata a
    prancha inteira por um campo mal formado."""
    p = _Projeto()
    mesclar_project_data(p, lixo, sf=_sf)
    assert p.warnings == [] and p.workstations == 0


def test_area_ilegivel_nao_entra_na_votacao():
    p = _Projeto()
    leituras = {}
    mesclar_project_data(p, {"total_area": "sem medida"}, leituras, sf=_sf)
    mesclar_project_data(p, {"total_area": 0}, leituras, sf=_sf)
    assert leituras.get("total_area", []) == []


# ══════════════════════════════════════════════════════════════════════════
#  🔑 Os DOIS laços têm que chamar — senão volta a divergir
# ══════════════════════════════════════════════════════════════════════════
def test_os_DOIS_lacos_vivos_chamam_a_MESMA_mesclagem():
    """🪤 Foi a divergência entre eles que matou o aviso. Ancorado na AST:
    comentário citando a função não pode fazer isto passar."""
    arvore = ast.parse(io.open(os.path.join(_BACKEND, "main.py"),
                               encoding="utf-8").read())
    chamadas = [n for n in ast.walk(arvore)
                if isinstance(n, ast.Call)
                and (getattr(n.func, "id", None) or getattr(n.func, "attr", None))
                in ("mesclar_project_data", "_mescla_pd")]
    assert len(chamadas) >= 2, (
        "o main.py mescla o project_data em %d lugar(es); são DOIS laços de "
        "prancha (DXF/DWG e PDF) e os dois precisam chamar a mesma função — "
        "a divergência entre eles descartou o aviso da IA por meses"
        % len(chamadas))


def test_NENHUM_laco_monta_a_mesclagem_a_mao():
    """🩸 O sintoma exato do defeito: `project_data.warnings` sendo montado à
    mão dentro de um laço de prancha. Se voltar, voltou a cópia."""
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    arvore = ast.parse(fonte)
    # 🪤 A 1ª versão deste guarda era LARGA DEMAIS e acusou o caminho de
    # RETOMADA POR CHECKPOINT (main.py ~9426), que restaura estado já mesclado
    # do disco (`pd_warnings`, não `warnings`) — coisa legítima e diferente.
    # 🔑 O defeito real tem uma assinatura estreita: mesclar no `project_data`
    # a partir do `pd` que a IA acabou de devolver. É nisso que ancoro; guarda
    # que acusa o inocente acaba desligado.
    culpados = []
    for n in ast.walk(arvore):
        if not isinstance(n, ast.Call):
            continue
        if getattr(n.func, "attr", None) != "extend":
            continue
        alvo = getattr(n.func, "value", None)
        if not (isinstance(alvo, ast.Attribute)
                and getattr(alvo.value, "id", None) == "project_data"
                and alvo.attr in ("kept_elements", "new_rooms",
                                  "demolition_notes", "warnings")):
            continue
        # a fonte é o `pd` da IA? (`pd.get(...)` ou `pd[...]`)
        veio_do_pd = any(
            getattr(getattr(x, "value", None), "id", None) == "pd"
            for x in ast.walk(n) if isinstance(x, (ast.Attribute, ast.Subscript)))
        if veio_do_pd:
            culpados.append(n.lineno)
    assert not culpados, (
        "o main.py voltou a mesclar %s à mão (linhas %s) — use "
        "`mesclar_project_data`, senão os dois laços divergem de novo"
        % ("project_data", culpados))
