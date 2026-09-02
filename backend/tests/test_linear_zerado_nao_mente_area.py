# -*- coding: utf-8 -*-
"""Item em METRO que sai zerado não pode dizer "Área NÃO medida".

🩸 MEDIDO em 01/09/2026, job 144c1f04 (flavio anderson, 20 PDFs — o maior
caderno da base). A planilha saiu com 161 itens:

    contagem (un)   73 itens · 73 com número
    área (m²)       50 itens ·  8 com número
    LINEAR (ml, m)  25 itens ·  0 com número   ← todos zerados

E os 25 lineares levaram, um por um, a frase:

    "Área NÃO medida (lida de PDF por IA, não da geometria) — preencha a
     metragem, informe a área no upload ou envie o DXF pra medir."

Três coisas erradas numa frase só:
  1. rodapé, soleira, tubulação frigorígena, dreno e perfil de LED não são
     ÁREA — são COMPRIMENTO. O substantivo mente sobre o que a linha é;
  2. "informe a área no upload" não preenche metro nenhum: aquele campo
     alimenta piso/forro/laje (`FLOOR_M2_UNITS`) e nunca toca em `ml`;
  3. a frase sugere que não conseguimos ler a prancha — e nesse mesmo job
     medimos 17 pranchas (`pdfvec:promo` no error_log, soma 1.183,6 m²).

🪤 O QUE ESTE CONSERTO **NÃO** FAZ: preencher. A tentação óbvia é jogar o
`walls_m` medido na linha de rodapé, e isso é proibido por medição nossa —
em 31/08 o `walls_m` de PDF errou até 4,6×, e comprimento de parede não é
perímetro de rodapé nem percurso de tubulação. Zerar continua certo (regra
dura nº1). O que muda é a honestidade do texto.

🔑 Quem resgata linear MEDIDO de verdade é `_quantidade_medida_pelo_pdf`
(passo 6), que exige o número escrito na observação bater ±1% com a nossa
medição daquela prancha. No job real deu `resgate_pdf=0`: a IA escreveu
estimativa visual ("~4 barras × 3 m = 12ml"), não a nossa medição. Este ramo
é o que sobra depois dele — e por isso ele precisa falar a verdade.
"""
import io
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import main  # noqa: E402


class _Item:
    def __init__(self, desc, unit, qty, obs="", origem="", conf="estimado"):
        self.description = desc
        self.unit = unit
        self.quantity = qty
        self.ref_sheet = ""
        self.observations = obs
        self.origem = origem
        self.confidence = conf


# itens reais do job 144c1f04, com a unidade que eles têm no banco
RODAPE = ("Rodapé em porcelanato acetinado 90×90cm — BIANCOGRES — H=10cm", "ml")
FRIGO = ("Tubulação frigorífica em cobre (linha líquido + linha gás)", "ml")
SOLEIRA = ("Soleira de piso em granito Cinza Andorinha escovado", "ml")
PISO = ("Piso porcelanato acetinado 90×90cm — BIANCOGRES", "m²")


def _zera(desc, unit, qty=50.0, **kw):
    it = _Item(desc, unit, qty)
    main._apply_area_honesty([it], **kw)
    return it


# ── A frase ────────────────────────────────────────────────────────────────
def test_item_LINEAR_zerado_NAO_diz_que_e_area():
    """🩸 Os 25 itens do flavio."""
    it = _zera(*RODAPE)
    assert it.quantity == 0, "o teste não está exercitando o ramo que zera"
    obs = (it.observations or "").lower()
    assert "área não medida" not in obs, (
        "rodapé em metro linear recebeu 'Área NÃO medida' — a frase mente "
        "sobre o que a linha é")
    assert "comprimento" in obs, (
        "a frase não diz que o que falta é COMPRIMENTO")


def test_item_LINEAR_nao_recebe_conselho_que_nao_resolve():
    """🪤 'Informe a área no upload' não preenche metro nenhum: aquele campo
    só alimenta piso/forro/laje. Mandar o cliente fazer isso é fazer ele
    perder tempo e voltar com a mesma linha vazia."""
    it = _zera(*FRIGO)
    obs = (it.observations or "").lower()
    assert "informe a área no upload" not in obs, (
        "conselho de área num item de comprimento — não resolve e frustra")
    assert "dxf" in obs, "sumiu o único caminho que realmente mede (DXF)"


def test_a_frase_diz_que_a_GENTE_MEDIU_a_prancha():
    """🔑 A linha vazia sem contexto se lê como 'não conseguiram abrir meu
    arquivo'. Medimos 17 pranchas nesse job — a frase tem que dizer isso."""
    it = _zera(*RODAPE)
    assert "medimos a planta" in (it.observations or "").lower(), (
        "a frase não distingue 'não medimos' de 'medimos e não dá pra "
        "publicar esse número'")


def test_CONTROLE_item_de_AREA_continua_com_a_frase_de_area():
    """🧪 O conserto não pode vazar pro caminho que estava certo."""
    it = _zera(*PISO)
    obs = (it.observations or "").lower()
    assert "área não medida" in obs, (
        "o item de m² perdeu a frase certa — o conserto vazou")
    assert "comprimento não medido" not in obs


def test_CONTROLE_a_frase_LINEAR_nao_aparece_em_item_de_area():
    it = _zera(*PISO)
    assert "comprimento não medido" not in (it.observations or "").lower()


# ── O que o conserto NÃO faz ───────────────────────────────────────────────
def test_NAO_inventa_numero_no_item_linear():
    """🚨 Regra dura nº1, e uma medição nossa: `walls_m` de PDF erra até 4,6×.
    O conserto é de TEXTO. Se algum dia alguém preencher aqui, este teste cai
    e a pessoa vai ter que ler o porquê."""
    it = _zera(*RODAPE)
    assert it.quantity == 0, (
        "alguém passou a preencher item linear — `walls_m` de PDF erra até "
        "4,6× e não é perímetro de rodapé; ver o cabeçalho deste arquivo")


def test_o_selo_continua_ESTIMADO():
    it = _zera(*RODAPE)
    assert str(getattr(it.confidence, "value", it.confidence)) == "estimado"


def test_observacao_que_a_IA_escreveu_e_PRESERVADA():
    """A conta da IA ('~4 barras × 3 m') é o rastro que o cliente usa pra
    preencher. Zerar o número não pode apagar o raciocínio."""
    it = _Item(RODAPE[0], "ml", 12.0,
               obs="Contagem visual: ~4 barras de perfil, 3 m cada = ~12ml")
    main._apply_area_honesty([it])
    assert "~4 barras" in (it.observations or ""), (
        "o conserto apagou o raciocínio da IA junto com o número")


# ── O contador e o aviso do projeto ────────────────────────────────────────
def test_conta_quantos_lineares_zerou():
    itens = [_Item(RODAPE[0], "ml", 50.0), _Item(FRIGO[0], "m", 30.0),
             _Item(PISO[0], "m²", 900.0)]
    main._apply_area_honesty(itens)
    assert getattr(main._apply_area_honesty, "ultimo_lineares_zerados", 0) == 2, (
        "o contador de linear zerado não separa linear de área")


def test_CONTROLE_linear_que_NAO_foi_zerado_nao_conta():
    """🧪 Item linear com quantidade 0 desde o começo não passa pelo ramo —
    não é o motor que zerou, e não pode inflar o contador."""
    it = _Item(RODAPE[0], "ml", 0.0)
    main._apply_area_honesty([it])
    assert getattr(main._apply_area_honesty, "ultimo_lineares_zerados", 0) == 0, (
        "o contador conta linha que já nasceu vazia")


def _fonte():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def test_o_projeto_AVISA_quando_muita_linha_linear_fica_vazia():
    """🩸 25 de 25 vazias. A observação por linha existe, mas quem abre a
    planilha vê a coluna inteira em branco antes de ler observação nenhuma."""
    limpo = "\n".join(l for l in _fonte().splitlines()
                      if not l.lstrip().startswith("#"))
    assert "ultimo_lineares_zerados" in limpo, (
        "o caller não lê o contador — o aviso não existe")
    assert "ficaram sem quantidade" in limpo, "o cliente não é avisado"
    assert "motor:linear-zerado" in limpo, "não vira linha em error_log"


def test_CONTROLE_a_checagem_de_chamada_sabe_REPROVAR():
    """🧪 Sem isto o teste acima passaria com o aviso desligado."""
    falso = "\n".join(["        # ultimo_lineares_zerados (comentado)", "        pass"])
    limpo = "\n".join(l for l in falso.splitlines()
                      if not l.lstrip().startswith("#"))
    assert "ultimo_lineares_zerados" not in limpo, (
        "a checagem aceita a linha COMENTADA — não guarda nada")


def test_o_conjunto_local_NAO_pode_divergir_do_engine_rules():
    """🪤 O conjunto de unidades vive LOCAL dentro de `_apply_area_honesty`
    (três testes dão exec numa fatia da função e um global novo vira NameError
    neles — foi como eu deixei 9 testes vermelhos hoje). O preço de ser local é
    poder divergir da fonte canônica; este teste é quem cobra esse preço."""
    import re
    import engine_rules
    src = _fonte()
    m = re.search(r'_u_compr = (\{[^}]*\})', src)
    assert m, "o conjunto local sumiu ou mudou de nome"
    local = eval(m.group(1))          # noqa: S307 — literal do próprio fonte
    assert local == set(engine_rules.UNIDADES_SO_COMPRIMENTO), (
        "o conjunto local de main.py divergiu de "
        "engine_rules.UNIDADES_SO_COMPRIMENTO: %s != %s"
        % (local, engine_rules.UNIDADES_SO_COMPRIMENTO))
