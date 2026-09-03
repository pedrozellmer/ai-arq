# -*- coding: utf-8 -*-
"""A planilha refeita nascia mais limpa e MENOS honesta — e apagava a boa.

🩸 03/09/2026. Dois caminhos refazem o .xlsx a partir do banco: finalizar a
revisão e informar a área. Os dois montavam o `ProjectData` com três campos —
nome, área, layout — e o arquivo refeito **sobrescreve o original no Storage**.
Sumiam do arquivo entregue: `warnings`, `address`, `phase`.

📏 Medido: **9 projetos de cliente, 24 avisos apagados**.

🚨 E o pior é de regra dura. Sem `total_area_source`, `spreadsheet.py:419`
escreve na capa "Área construída — perímetro externo da laje" — uma afirmação
de que NÓS medimos. Dois clientes receberam isso em cima de um número que eles
mesmos digitaram (conferido no banco em 03/09):

    29e2cfc4  luizchirigatti478@  total_area 290,00 = user_total_area 290,00
    f271473f  flaviohermolin@     total_area 400,00 = user_total_area 400,00

Os dois tinham 3 avisos no banco. Regra dura nº1 violada no arquivo que já está
na mão do cliente, e a versão honesta apagada por cima.

🪤 A reconstrução existia em DOIS lugares fazendo a mesma coisa pela metade.
Agora mora em `_project_data_do_banco` — cópia velha ao lado da nova é a
próxima pessoa consertando a errada (a lição de 02/09 com o portão do admin).
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main as m                                    # noqa: E402
from _corpo import fonte, sem_comentarios           # noqa: E402


def _linha(**kw):
    """Uma linha de `projects` como o banco devolve com select=*."""
    base = {"project_name": "Casa Bruna", "total_area": 290.0, "layout_area": 0,
            "warnings": ["Área informada por você", "3 pranchas não lidas"],
            "address": "Rua X, 100", "phase": "Executivo",
            "user_total_area": None, "user_pe_direito": None}
    base.update(kw)
    return base


# ── O que sumia do arquivo ─────────────────────────────────────────────────
def test_a_planilha_refeita_LEVA_os_avisos():
    """🩸 Os 24 avisos de 9 projetos."""
    pd = m._project_data_do_banco(_linha())
    assert pd.warnings == ["Área informada por você", "3 pranchas não lidas"], pd.warnings


def test_leva_endereco_fase_e_pe_direito():
    pd = m._project_data_do_banco(_linha(user_pe_direito=2.8))
    assert pd.address == "Rua X, 100"
    assert pd.phase == "Executivo"
    assert pd.user_pe_direito == 2.8


def test_CONTROLE_projeto_SEM_esses_campos_nao_estoura():
    """Regerar planilha não pode falhar por causa de metadado ausente."""
    pd = m._project_data_do_banco({"project_name": "X"})
    assert pd.warnings == [] and pd.address == "" and pd.total_area == 0


# ── A regra dura nº1, que é o ponto ────────────────────────────────────────
def test_area_DIGITADA_pelo_cliente_nao_sai_como_medida_por_nos():
    """🚨 O caso 29e2cfc4 (290 m²) e f271473f (400 m²). Sem isto a capa diz
    'Área construída — perímetro externo da laje' em cima do número do
    cliente — a planilha afirma uma medição que não existiu."""
    for area in (290.0, 400.0):
        pd = m._project_data_do_banco(_linha(total_area=area, user_total_area=area))
        assert pd.total_area_source == "informado", (
            "área de %s m² que o cliente digitou saiu carimbada como medida" % area)


def test_CONTROLE_area_MEDIDA_continua_medida():
    """🧪 O outro lado, e é essencial: rebaixar medição a 'informado por você'
    sem ninguém pedir é o mesmo erro na direção contrária."""
    pd = m._project_data_do_banco(_linha(total_area=290.0, user_total_area=None))
    assert pd.total_area_source != "informado", (
        "área que a planta mediu passou a se apresentar como informada")


def test_CONTROLE_cliente_informou_numero_DIFERENTE_da_capa():
    """Se a capa tem 290 medido e o cliente informou 150 noutro momento, a capa
    continua sendo a medição — não vira 'informado' por associação."""
    pd = m._project_data_do_banco(_linha(total_area=290.0, user_total_area=150.0))
    assert pd.total_area_source != "informado"


def test_o_chamador_pode_FORCAR_a_procedencia():
    pd = m._project_data_do_banco(_linha(), total_area_source="informado")
    assert pd.total_area_source == "informado"


def test_a_PLANILHA_de_fato_muda_de_texto_com_isso():
    """🪤 Guarda de ponta a ponta: não basta o campo existir, `spreadsheet.py`
    tem que ler ELE. Se a condição lá mudar de nome, este teste cai."""
    src = fonte("spreadsheet.py")
    assert "getattr(project, 'total_area_source', '') == 'informado'" in src, (
        "a planilha parou de decidir a linha de premissa por total_area_source")
    assert "INFORMADA POR VOCÊ (não medida pela planta)" in src


# ── Um lugar só, e os dois chamadores ──────────────────────────────────────
def test_os_DOIS_caminhos_usam_o_MESMO_reconstrutor():
    """🪤 A reconstrução existia duplicada e as duas cópias estavam erradas.
    Se nascer uma terceira sem passar por aqui, o defeito volta."""
    src = sem_comentarios(fonte("main.py"))
    assert src.count("_project_data_do_banco(") >= 3, (
        "sumiu um dos chamadores do reconstrutor (esperado: definição + 2 usos)")
    assert "pd = _project_data_do_banco(proj)" in src, "o caminho da revisão não usa"
    assert "_project_data_do_banco(proj, total_area=(area or _area_ja_tinha))" in src, (
        "o caminho do inform-area não usa")


def test_NENHUM_outro_lugar_remonta_o_ProjectData_na_mao():
    """🚨 O guarda que se cobra sozinho. Só o motor (que lê o CAD) pode criar
    ProjectData do zero; quem REMONTA a partir do banco passa pelo helper."""
    src = sem_comentarios(fonte("main.py"))
    assert src.count("ProjectData(") == 2, (
        "apareceu uma remontagem nova de ProjectData fora do helper — "
        "encontradas %d ocorrências (esperado 2: o motor e o helper)"
        % src.count("ProjectData("))


def test_CONTROLE_a_contagem_sabe_REPROVAR():
    falso = "pd = ProjectData(name='x')\npd2 = ProjectData(name='y')\npd3 = ProjectData()"
    assert falso.count("ProjectData(") == 3
