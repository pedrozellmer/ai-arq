# -*- coding: utf-8 -*-
"""Número de área preservado que nem confessa nem cita base — EM SOMBRA.

🔬 25/10/2026 — Medido em 120 dias (preservadas pelo "cabe na geometria",
clientes): depois das réguas que pegam o chute CONFESSADO, sobram linhas como
"Confirmar ambientes com indicação ⑤" com 25 m² e "Item 12 identificado com
setas em diversas áreas" com 120 m². Mas a base também vem escrita de mil
jeitos ("Somatório das áreas: 9,61 + 9,25 …", "Área extraída do texto da
prancha: 'OFICINA 493.85m²'"); testada em linhas que eu não tinha lido, a 1ª
versão acertou 73%. Por isso nasce EM SOMBRA: com AREA_SEM_BASE_NAO_PRESERVA=0
o motor só anota (`ultimo_sombra_sem_base` → `motor:sombra-area-sem-base`).

Roda a `_apply_area_honesty` REAL pela fatia de `test_area_medida_do_pdf_nao_e_apagada`.
🪤 Frases reescritas sem nome de cliente (o repositório é público).
"""
import io
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)
sys.path.insert(0, os.path.dirname(_AQUI))

from engine_rules import area_sem_base_citada  # noqa: E402
import test_area_medida_do_pdf_nao_e_apagada as _base  # noqa: E402

_CHAVE = "AREA_SEM_BASE_NAO_PRESERVA"
_IRMAS = ("AREA_A_OLHO_NAO_PRESERVA", "AREA_ESTIMADA_SEM_BASE_NAO_PRESERVA")
#: o nosso aviso de prancha repetida — fala em "somam", e não é base da linha
_AVISO_PRANCHAS = (" | ⚠ Este serviço aparece em 4 pranchas do projeto (a.pdf, b.pdf). "
                   "Esta linha vem da prancha dela — confira se são trechos diferentes "
                   "da obra (pavimentos, fases, blocos), que somam, ou o mesmo trecho "
                   "desenhado mais de uma vez, que não soma.")

_SEM_BASE = [
    "Confirmar ambientes com indicação ⑤ e especificação completa na legenda.",
    "Item 12 identificado com setas em diversas áreas. Confirmar especificação completa.",
    "Estimativa: 2 lavabos × ~3m² de piso. Confirmar com planta baixa do térreo.",
    "Brinquedoteca identificada com tag ②." + _AVISO_PRANCHAS,
    "Piso tipo PI-A indicado em múltiplas áreas da planta. | Estimativa: lido de PDF, "
    "não medido em geometria — envie DWG/DXF pra medir",
    "Estimativa: cozinhas de ~7,69 m² × ~7 unidades visíveis.",
    "Legenda item 2: bloco intertravado. | Fundido de 2 entradas com a mesma quantidade (10,00 m²)",
    # 🔬 26/10: a palavra de base só no PEDIDO de conferência
    "Área estimada. Confirmar com quadro de áreas completo.",
    "Estimativa baseada nos ambientes identificados. Confirmar com planta cotada do térreo.",
    "Piso do salão; verificar a área medida no levantamento.",
    "",
    None,
]

_COM_BASE = [
    "Somatório das áreas de salas: Sala 9,61 + 9,25 + 6,96 = ~25,8 m².",
    "Prismas identificados: 4,72 + 3,30 + 4,76 (parcial).",
    "Área extraída do texto da prancha: 'OFICINA 493.85m²'.",
    "Área extraída do Quadro de Quantitativo | Revestimento Piso (RE01) constante na prancha.",
    "Área declarada na planta: HALL 8,00 m². Tipo de piso não especificado.",
    "Área lida diretamente da anotação na planta: 'LAVANDERIA 16,80m²'.",
    "Calculado pela soma das áreas declaradas: sala (16,00) + caixa (5,85).",
    "Área total do pavimento: 306,8 m². Tipo de forro não especificado.",
    "Área igual ao piso do ambiente (A=42,65m²).",
    "Área de escoramento = área de laje.",
    "VESTIR A: 4,40 m². Tipo de piso inferido.",
    # cada uma só tem UMA forma de base (pega o mutante que a apagar)
    "Somatório das áreas dos ambientes com este código na legenda.",
    "Ambiente 'OFICINA 493.85m²' identificado na planta.",
    # a base ANTES do pedido de conferência continua valendo
    "Área conforme rótulo da planta (12,50 m²); confirmar acabamento com o memorial.",
    "Medição validada por cotas na escala 1:50.",   # "validada" não é o verbo do pedido
    # o corte do pedido para no fim da frase: a base da frase seguinte fica
    "Confirmar acabamento com o memorial. Área conforme rótulo da planta (12,50 m²).",
    "⚠ NÃO SOME COM AS DE BAIXO: esta linha parece ser o TOTAL de 6 linha(s) "
    "da mesma disciplina, que somam 423.65 m².",
]


@pytest.mark.parametrize("obs", _SEM_BASE)
def test_sem_base_citada_e_reconhecida(obs):
    assert area_sem_base_citada(obs), obs


@pytest.mark.parametrize("obs", _COM_BASE)
def test_CONTROLE_base_escrita_de_varios_jeitos_e_base(obs):
    assert not area_sem_base_citada(obs), obs


def _caso(monkeypatch, obs, ligada):
    for k in _IRMAS:
        monkeypatch.delenv(k, raising=False)
    if ligada:
        monkeypatch.setenv(_CHAVE, "1")
    else:
        monkeypatch.delenv(_CHAVE, raising=False)
    piso = _base._Item("Piso em porcelanato 120×120 cm — legenda 3", "m²", 25.0, obs)
    h = _base._fatia()["_apply_area_honesty"]
    h([piso], total_area=0, total_area_source="", pe_direito=0, pdfvec_m2=667.0)
    return piso, h


def test_CONTROLE_desligada_o_numero_fica_e_a_sombra_anota(monkeypatch):
    piso, h = _caso(monkeypatch, _SEM_BASE[0], ligada=False)
    assert _base._valor(piso) == 25.0, "a sombra mudou número"
    assert getattr(h, "ultimo_sombra_sem_base", None) == [
        (25.0, "Piso em porcelanato 120×120 cm — legenda 3")]
    assert getattr(h, "ultimo_sem_base_larga", None) == 0


def test_CONTROLE_desligada_linha_com_base_nao_entra_na_sombra(monkeypatch):
    piso, h = _caso(monkeypatch, _COM_BASE[0], ligada=False)
    assert _base._valor(piso) == 25.0
    assert getattr(h, "ultimo_sombra_sem_base", None) == []


def test_ligada_o_numero_sem_base_nao_e_preservado(monkeypatch):
    piso, h = _caso(monkeypatch, _SEM_BASE[0], ligada=True)
    assert _base._valor(piso) == 0
    assert getattr(h, "ultimo_sem_base_larga", None) == 1


def test_CONTROLE_ligada_com_base_segue_preservado(monkeypatch):
    piso, h = _caso(monkeypatch, _COM_BASE[2], ligada=True)
    assert _base._valor(piso) == 25.0
    assert getattr(h, "ultimo_sem_base_larga", None) == 0


def test_ligada_a_frase_que_o_ramo_apaga_nao_salva(monkeypatch):
    """A IA escreve "Medido do desenho com escala 1:X lida do carimbo" e o ramo
    apaga logo depois — não pode contar como base (mesma lição de 25/10)."""
    obs = "Confirmar ambientes com indicação ⑧. Medido do desenho com escala 1:50 lida do carimbo."
    piso, h = _caso(monkeypatch, obs, ligada=True)
    assert _base._valor(piso) == 0


def test_a_avaliacao_liga_so_para_ela(monkeypatch):
    import main
    for k in _IRMAS + (_CHAVE,):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setitem(main._CHAVES_DA_AVALIACAO, "evsomb01", {_CHAVE: "1"})

    def _roda(job):
        piso = _base._Item("Piso em porcelanato 120×120 cm — legenda 3", "m²", 25.0, _SEM_BASE[1])
        main._apply_area_honesty([piso], total_area=0, total_area_source="",
                                 pe_direito=0, pdfvec_m2=667.0, job_id=job)
        return _base._valor(piso)

    assert _roda("evsomb01") == 0
    assert _roda("abc12345") == 25.0


def test_a_chave_e_avaliavel_lida_pelo_job_e_a_sombra_vai_pro_log():
    src = io.open(os.path.join(_base._BACKEND, "main.py"), encoding="utf-8").read()
    assert '_chave_do_job(job_id, "%s")' % _CHAVE in src
    assert '"%s"' % _CHAVE in src[src.index("_CHAVES_AVALIAVEIS = frozenset"):][:4000]
    assert '_log_error("motor:sombra-area-sem-base"' in src


def test_a_sombra_e_diagnostico_e_nao_entope_o_painel_de_erros():
    """🪤 Sem estar na lista de diagnóstico, cada job com sombra viraria uma linha
    no painel "Erros do motor" — como o `llm:cache` em 24/08."""
    src = io.open(os.path.join(_base._BACKEND, "main.py"), encoding="utf-8").read()
    _lista = src[:src.index('"motor:passo7-ambiguo"')]
    assert '    "motor:sombra-area-sem-base",\n' in _lista.replace("\r\n", "\n")
    assert "sem_base_larga={getattr(_apply_area_honesty, 'ultimo_sem_base_larga', 0)}" in src
