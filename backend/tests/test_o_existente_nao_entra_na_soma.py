# -*- coding: utf-8 -*-
"""Item marcado [EXISTENTE ...] não sai com quantidade na planilha.

🩸 14/09/2026 — a planilha de um cliente do dia (coordenador de orçamento,
prancha de elétrica em DWG+PDF) trouxe duas linhas assim:

    "[EXISTENTE — manter] Eletrocalha galvanizada 300×50mm ... existente
     conforme legenda"   →  414,16 ml, selo CONFIRMADO
    "[EXISTENTE — manter] Eletrocalha ... (elétrica)"  →  341,48 ml, CONFIRMADO

Numa planilha de orçamento, linha com quantidade entra na soma: o total linear
do projeto saltou de 207 m para 970 m, e 755 m eram material que já está
instalado e não será comprado.

🔑 O MESMO arquivo, na leitura anterior, tinha saído com quantidade ZERO e
unidade `vb`, com a medição só na observação — o certo. Quem decidia era a IA, e
ela decidiu diferente nas duas passadas. Esta regra tira a decisão da IA.

📏 Medido na base: 68 linhas com o marcador em 39 jobs; 26 delas (15 jobs) com
quantidade, 11 com selo branco.

🪤 O gatilho é o PREFIXO `[EXISTENTE`, nunca a palavra "existente" no meio do
texto — medido antes de escrever: "Demolição de parede existente", "Pintura em
forro existente", "Restauro de piso existente" e "Proteção de áreas existentes"
são SERVIÇOS a orçar, e casar pela palavra zeraria todos eles.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


class _It:
    def __init__(self, desc, unit, qty, obs="", conf="confirmado"):
        self.description, self.unit, self.quantity = desc, unit, qty
        self.observations, self.confidence = obs, conf


def _conf(it):
    c = getattr(it, "confidence", "")
    return getattr(c, "value", c)


# ── o caso real ──────────────────────────────────────────────────────────
def test_o_existente_com_quantidade_SAI_da_soma():
    it = _It("[EXISTENTE — manter] Eletrocalha galvanizada lisa 300×50mm (dados/voz)",
             "ml", 414.16, "Fonte: comprimento do layer 'W-ELETROCALHA DADOS' = 414,16 m.")
    assert main.existente_nao_leva_quantidade([it]) == 1
    assert float(it.quantity) == 0, "continua somando no orçamento"
    assert it.unit == "vb"
    assert _conf(it) == "estimado", "selo branco em linha sem número a orçar"


def test_o_numero_levantado_NAO_se_perde():
    """Zerar não é apagar: quem for remanejar precisa do levantamento."""
    it = _It("[EXISTENTE - manter] Eletrocalha (elétrica)", "ml", 341.48,
             "Fonte: layer 'W-ELETROCALHA ELÉTRICA' = 341,48 m.")
    main.existente_nao_leva_quantidade([it])
    obs = it.observations or ""
    assert "341.48" in obs or "341,48" in obs, obs
    assert "fora da soma" in obs, obs
    assert "W-ELETROCALHA" in obs, "a observação que a IA escreveu foi jogada fora"


def test_as_DUAS_formas_do_marcador_valem():
    """Travessão e hífen aparecem os dois na base, e a caixa pode variar."""
    for desc in ("[EXISTENTE — manter] Quadro elétrico",
                 "[EXISTENTE - manter] Luminária de emergência",
                 "  [existente - manter] Porta corta-fogo",
                 "[EXISTENTE (várias variantes)] Piso elevado"):
        it = _It(desc, "un", 12)
        assert main.existente_nao_leva_quantidade([it]) == 1, desc
        assert float(it.quantity) == 0, desc


# ── controles: o que NÃO pode ser tocado ─────────────────────────────────
def test_CONTROLE_servico_com_a_palavra_existente_CONTINUA_no_orcamento():
    """🪤 O maior risco deste conserto. Estes quatro são serviços a executar —
    zerar qualquer um deles tira dinheiro real da planilha do cliente."""
    servicos = [
        _It("Demolição de paredes de alvenaria existentes", "m²", 48.5),
        _It("Pintura PVA branca neve em forro existente", "m²", 120.0),
        _It("Lixamento, tratamento e restauro de piso existente em madeira", "m²", 76.3),
        _It("Proteção de áreas existentes durante a obra", "m²", 300.0),
        _It("Retirada de porta existente — remoção e descarte", "un", 8),
    ]
    assert main.existente_nao_leva_quantidade(servicos) == 0
    for it in servicos:
        assert float(it.quantity) > 0, it.description
        assert it.unit != "vb", it.description
        assert _conf(it) == "confirmado", "o selo do serviço foi mexido: %s" % it.description


def test_CONTROLE_existente_que_ja_veio_certo_nao_e_mexido():
    """Quando a IA já acertou (qtd 0 + vb), a regra não tem o que fazer —
    e não pode sujar a observação com uma nota repetida a cada leitura."""
    it = _It("[EXISTENTE — manter] Eletrocalha 300×50mm", "vb", 0,
             "Fonte: layer W-ELETROCALHA DADOS (414.16 m medidos no DXF).",
             conf="estimado")
    antes = it.observations
    assert main.existente_nao_leva_quantidade([it]) == 0
    assert it.observations == antes, "escreveu nota numa linha que já estava certa"


def test_CONTROLE_lista_vazia_e_item_torto_nao_explodem():
    assert main.existente_nao_leva_quantidade([]) == 0
    assert main.existente_nao_leva_quantidade(None) == 0

    class _Torto:
        description = "[EXISTENTE — manter] Sem quantidade nenhuma"
        unit = "un"
        quantity = "não é número"
        observations = None
        confidence = "estimado"
    assert main.existente_nao_leva_quantidade([_Torto()]) == 0


# ── o motor CHAMA a regra (senão ela nasce morta) ────────────────────────
def test_o_process_job_CHAMA_a_regra_antes_de_recontar_o_selo():
    """🪤 Guarda de ponto de chamada: a regra pode existir e ninguém rodar.
    Tem que vir ANTES da recontagem do aviso, senão o aviso conta selo que a
    regra ainda vai rebaixar."""
    import ast
    import io as _io
    caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    arv = ast.parse(_io.open(caminho, encoding="utf-8").read())
    fn = next((n for n in ast.walk(arv)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "process_job"), None)
    assert fn is not None
    chama = [d.lineno for d in ast.walk(fn)
             if isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
             and d.func.id == "existente_nao_leva_quantidade"]
    reconta = [d.lineno for d in ast.walk(fn)
               if isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
               and d.func.id == "_recontar_aviso_planob"]
    assert chama, ("o `process_job` não chama `existente_nao_leva_quantidade` — "
                   "a regra nasceu morta e o existente volta a somar")
    assert reconta, "não achei a recontagem do aviso — a âncora da ordem mudou"
    assert min(chama) < max(reconta), (
        "a regra roda DEPOIS da recontagem final do aviso: o aviso conta um selo "
        "que ela ainda vai rebaixar")
