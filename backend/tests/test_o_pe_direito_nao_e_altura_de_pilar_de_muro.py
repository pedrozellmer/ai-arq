# -*- coding: utf-8 -*-
"""Em estrutura de CONTENÇÃO o pé-direito informado não é altura de pilar.

🩸 26/09/2026 — job 32a27efc (muro de arrimo, 7 DXF de estrutura). O cliente
informou pé-direito 7,32 m: a altura TOTAL do muro no ponto mais fundo. O muro
tem 32 pilares 19×30 com altura desenhada de 1,00 a 6,77 m (média 3,84). A
conta seção × 7,32 × 32 deu 13,35 m³ e 229,6 m² de fôrma, contra ≈ 7,0 m³ e
≈ 120 m² desenhados — e usaram o 7,32 os dois caminhos:
  · `_derive_estrutura_pe_direito` (a nossa conta, depois da IA);
  · o prompt estrutural, que mandava "Use este valor como ALTURA nos
    elementos verticais".
🔑 Em contenção cada pilar tem a altura do muro NAQUELE ponto. A pergunta é do
JOB (3 das 7 pranchas não citam o muro nos itens) e só de itens de Estrutura.

📏 Acervo de cliente em 26/09: 6 jobs com item de Estrutura que casa a régua;
só o 32a27efc informou pé-direito. `motor:pd-estrutura` disparou em 2 jobs: este
e o b073d13b (galpão pré-moldado) — o CONTROLE, que tem de continuar derivando.
"""
import os
import sys
import textwrap
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import main  # noqa: E402
from _corpo import fonte  # noqa: E402
from engine_rules import estrutura_de_contencao  # noqa: E402

_deriva = main._derive_estrutura_pe_direito


class _It:
    def __init__(self, descricao, unidade, qtd, folha="0001", disciplina="Estrutura"):
        self.description = descricao
        self.unit = unidade
        self.quantity = qtd
        self.confidence = "estimado"
        self.observations = ""
        self.discipline = disciplina
        self.origem = None
        self.ref_sheet = folha


# ── a régua ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("texto", [
    "RAMPA - MURO DE ARRIMO",                                   # o carimbo das 7 pranchas
    "Pilar de concreto armado — seção 19×30 cm — muro de arrimo",
    "Fôrma para muro de arrimo/contenção h≈300cm",
    "CONTENÇÃO DO SUBSOLO",
    "contencao lateral",                                        # sem acento
    "Cortina de concreto armado e=20 cm",
    "cortina de estacas justapostas",
    "Parede diafragma e=40 cm",
])
def test_a_regua_reconhece_contencao(texto):
    assert estrutura_de_contencao([texto]), texto


@pytest.mark.parametrize("texto", [
    "Muro de divisa em alvenaria de bloco",                     # "muro" sozinho é arquitetura
    "Gradil metálico sobre muros",
    "Cortina de vidro temperado 10 mm",                         # esquadria
    "Cortina do poço do elevador",
    "Pilar de concreto pré-fabricado — seção 40×50 cm",
    "",
    None,
])
def test_a_regua_nao_pega_o_que_nao_e_contencao(texto):
    assert not estrutura_de_contencao([texto]), texto


def test_a_regua_ignora_o_acento_DECOMPOSTO():
    """🪤 A régua já aceita 'ç'/'ã' compostos; o acento DECOMPOSTO (NFD: 'c' +
    cedilha combinante, comum em texto vindo de Mac) só casa porque o texto
    passa pelo helper que tira o acento."""
    assert estrutura_de_contencao([unicodedata.normalize("NFD", "CONTENÇÃO DO TALUDE")])


def test_a_regua_aceita_um_texto_solto():
    """🪤 str também é iterável: sem o cuidado, 'MURO DE ARRIMO' seria lido letra
    por letra e nunca casaria."""
    assert estrutura_de_contencao("RAMPA - MURO DE ARRIMO")
    assert not estrutura_de_contencao("Muro de divisa")


# ── a derivação ──────────────────────────────────────────────────────────
def _o_caso(com_muro=True):
    """O job como estava: a prancha 0001 NÃO cita o muro nos itens; a 0004 cita."""
    pilar = _It("Pilar de concreto armado — seção 30×19 cm", "un", 32, "0001")
    conc = _It("Concreto armado — pilares 30×19 cm", "m³", 0, "0001")
    forma = _It("Fôrma de madeira — pilares 30×19 cm", "m²", 0, "0001")
    ja = _It("Fôrma de madeira — pilares seção 19×30 cm", "m²", 120.0, "0004")
    muro = _It("Pilar de concreto armado — seção 19×30 cm — muro de arrimo"
               if com_muro else "Pilar de concreto armado — seção 19×30 cm",
               "un", 32, "0004")
    return [pilar, conc, forma, ja, muro]


def test_o_caso_contencao_nao_deriva_nem_confere():
    itens = _o_caso()
    _, conc, forma, ja, _ = itens
    assert _deriva(itens, 7.32) == 0
    assert conc.quantity == 0 and forma.quantity == 0, (
        "a prancha que não cita o muro recebeu seção × 7,32 — a pergunta é do JOB")
    assert conc.observations == "" and forma.observations == ""
    assert ja.quantity == 120.0
    assert "Conferência" not in ja.observations, (
        "a conferência com 7,32 põe o número errado ao lado do certo")


def test_o_caso_o_motivo_diz_por_que():
    _deriva(_o_caso(), 7.32)
    m = _deriva.ultimo_motivo
    assert m.startswith("estrutura de contenção/muro de arrimo: cada pilar tem a "
                        "altura do muro naquele ponto; o pé-direito informado não "
                        "é altura de pilar"), m
    assert "muro de arrimo" in m.split("(item:")[1], "o motivo não diz qual item casou: %s" % m


def test_CONTROLE_o_mesmo_job_sem_o_muro_deriva():
    """Controle POSITIVO: tirando só a palavra do item da 0004, a conta volta —
    a trava é a única coisa segurando o 7,32."""
    itens = _o_caso(com_muro=False)
    assert _deriva(itens, 7.32) > 0
    assert itens[1].quantity == round(0.057 * 7.32 * 32, 2), itens[1].quantity
    assert _deriva.ultimo_motivo == ""


def test_CONTROLE_galpao_pre_moldado_continua_derivando():
    """O b073d13b (galpão pré-moldado, pé-direito 2,70) é o outro job em que a
    conta disparou — e lá o pé-direito É a altura do pilar."""
    itens = [_It("Pilar de concreto pré-fabricado — seção 40×50 cm", "un", 10),
             _It("Concreto armado — pilares seção 40×50 cm", "m³", 0),
             _It("Fôrma de madeira — pilares seção 40×50 cm", "m²", 0)]
    assert _deriva(itens, 2.7) == 2
    assert itens[1].quantity == round(0.2 * 2.7 * 10, 2), itens[1].quantity
    assert itens[2].quantity == round(1.8 * 2.7 * 10, 2), itens[2].quantity


def test_CONTROLE_muro_de_arrimo_de_ARQUITETURA_nao_trava():
    """Só item de Estrutura decide: "muro de arrimo" citado como referência da
    arquitetura não diz nada sobre os pilares."""
    itens = _o_caso(com_muro=False) + [
        _It("Muro de arrimo — referência arquitetônica", "m", 40, "A01", disciplina="Arquitetura")]
    assert _deriva(itens, 7.32) > 0
    assert itens[1].quantity > 0


def test_CONTROLE_muro_de_divisa_na_estrutura_nao_trava():
    itens = _o_caso(com_muro=False) + [
        _It("Muro de divisa — viga baldrame", "m", 40, "0004")]
    assert _deriva(itens, 7.32) > 0


# ── a honestidade não aposta numa reposição que não vem ──────────────────
def test_derivacao_vai_repor_diz_NAO_em_contencao():
    alvo = "Fôrma de madeira — pilares 30×19 cm"
    assert main._derivacao_vai_repor(_o_caso(), alvo, 7.32) is False


def test_CONTROLE_derivacao_vai_repor_sem_contencao_segue_SIM():
    alvo = "Fôrma de madeira — pilares 30×19 cm"
    assert main._derivacao_vai_repor(_o_caso(com_muro=False), alvo, 7.32) is True


# ── o motivo chega ao log (fatia REAL do process_job) ────────────────────
_ABRE_LOG = "# Pintura derivada do pé-direito informado (01/08/2026)"
_FECHA_LOG = '_log_error("motor:pe-direito", f"FALHOU: {_epd}", job_id)'


def _roda_o_bloco_do_log(itens, pd):
    src = fonte("main.py")
    i = src.index(_ABRE_LOG)
    i = src.rindex("\n", 0, i) + 1
    j = src.index(_FECHA_LOG, i) + len(_FECHA_LOG)
    logs = []

    class _Proj:
        user_pe_direito = pd
        total_area = 0

    ns = {"project_data": _Proj(), "all_items": itens, "job_id": "job-teste",
          "_log_error": lambda st, msg, jid=None, **k: logs.append((st, msg)),
          "_derive_pintura_pe_direito": main._derive_pintura_pe_direito,
          "_derive_estrutura_pe_direito": main._derive_estrutura_pe_direito,
          "_anotar_area_parede_pe_direito": main._anotar_area_parede_pe_direito}
    exec(compile(textwrap.dedent(src[i:j]), "<bloco_pe_direito>", "exec"), ns)
    return logs


def test_o_motivo_da_contencao_chega_ao_log_do_pe_direito():
    logs = _roda_o_bloco_do_log(_o_caso(), 7.32)
    pe = [m for st, m in logs if st == "motor:pe-direito"]
    assert len(pe) == 1, logs
    assert "estrutura: tocados=0" in pe[0], pe[0]
    assert "o pé-direito informado não é altura de pilar" in pe[0], pe[0]
    assert not [st for st, _ in logs if st == "motor:pd-estrutura"], logs


def test_CONTROLE_sem_contencao_o_log_registra_a_derivacao():
    logs = _roda_o_bloco_do_log(_o_caso(com_muro=False), 7.32)
    assert [st for st, _ in logs if st == "motor:pd-estrutura"], logs


# ── o prompt (fatia REAL da montagem, por prancha) ───────────────────────
_ABRE_PD = '_pd_directive = ""'
_FECHA_PD = 'dxf_prompt = f"""Analise os dados extraídos'
_TEXTO_DO_CASO = ("TEXTOS:\n    RAMPA - MURO DE ARRIMO\n    P1 19x30\n"
                  "COMPRIMENTOS POR LAYER: Rampa 90,85 m")


def _diretiva(texto, pd=7.32, estrutural=True):
    src = fonte("main.py")
    i = src.index(_ABRE_PD)
    i = src.rindex("\n", 0, i) + 1
    j = src.index(_FECHA_PD, i)
    j = src.rindex("\n", 0, j) + 1
    ns = {"user_pe_direito": pd, "is_structural": estrutural, "structured_text": texto}
    exec(compile(textwrap.dedent(src[i:j]), "<pd_directive>", "exec"), ns)
    return ns["_pd_directive"]


def test_o_prompt_de_contencao_nao_manda_usar_o_pe_direito_como_altura():
    d = _diretiva(_TEXTO_DO_CASO)
    assert "Use este valor como ALTURA" not in d, d
    assert "× 7.32 × quantidade" not in d, d
    assert "NÃO vale como altura de pilar de muro/contenção" in d, d
    assert "corte/elevação" in d and "quantidade 0" in d, d


def test_CONTROLE_o_prompt_sem_contencao_segue_como_era():
    d = _diretiva("TEXTOS:\n    P1 40x50\n    GALPÃO PRÉ-MOLDADO")
    assert "Use este valor como ALTURA nos elementos verticais" in d, d
    assert "CONTENÇÃO" not in d, d


def test_CONTROLE_arquitetura_com_muro_de_arrimo_segue_a_diretiva_de_pintura():
    """A trava é do ramo ESTRUTURAL: em arquitetura o pé-direito serve à pintura."""
    d = _diretiva(_TEXTO_DO_CASO, estrutural=False)
    assert "pintura" in d.lower() and "CONTENÇÃO" not in d, d


def test_CONTROLE_sem_pe_direito_nao_ha_diretiva():
    assert _diretiva(_TEXTO_DO_CASO, pd=0) == ""
