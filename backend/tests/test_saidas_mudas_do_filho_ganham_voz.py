# -*- coding: utf-8 -*-
"""As duas saídas MUDAS do filho da medição de PDF passam a deixar rastro.

🔬 05/09/2026 (estudo do teto, passo 6 + o custo da A08 do William).

1. **MemoryError engolido por etapa.** Cada etapa de `_measure_page` está num
   try/except. Quando a falta de memória cai em Python/GEOS (não no C que
   aborta), a etapa devolve `err_*='MemoryError...'`, o filho sai com rc=0 e
   um JSON parcial, e nenhum ramo do pai roda: `_pdfvec_falhas` não recebe
   nada e o cliente NÃO é avisado — o oposto do que o comentário do teto
   promete ("MemoryError vira parcial"). Medido local no estudo: FORRO com
   teto de 1,5 GB → rc=0 + err_views/err_rooms 'MemoryError'.

2. **"Sem escala".** O filho pula (viewport, carimbo e cota falharam) e sai
   rc=0 sem `n_rooms` — a promoção não grava NENHUMA linha; só a sombra anota.
   Custou duas tentativas na A08 do William pra achar o cache do carimbo.

Agora: `_saida_do_filho_pdfvec(rc, vm)` classifica; o chamador grava
`pdfvec:filho-morreu` (motivo "memoria", entra no aviso ao cliente com frase
própria) ou `pdfvec:sem-escala` (warning, com viewport/carimbo/cotas).

🧪 Controles: rc≠0 e sucesso normal continuam None; erro que NÃO é memória
não vira "memoria"; os guardas de fonte reprovam a versão antiga.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main  # noqa: E402
from _corpo import fonte, sem_comentarios  # noqa: E402

_SRC = sem_comentarios(fonte("main.py"))


# ── o classificador ────────────────────────────────────────────────────────
def test_memoryerror_engolido_vira_memoria():
    vm = {"file": "x.pdf", "page": 0, "scale": 100.0,
          "err_views": "MemoryError: ", "err_rooms": "MemoryError: bad allocation",
          "err_layers": "MemoryError: bad allocation", "secs": 88.0}
    tipo, det = main._saida_do_filho_pdfvec(0, vm)
    assert tipo == "memoria"
    assert "err_rooms" in det and "err_views" in det and "MemoryError" in det


def test_sem_escala_vira_sem_escala_com_o_motivo_de_cada_fonte():
    vm = {"file": "HNSC.pdf", "page": 0, "skip": "sem escala (viewport, carimbo nem cota)",
          "n_viewports": 0, "indicadas": True, "declared": [],
          "cotas_derivacao": {"votos": 14, "confianca": 0.29}, "secs": 11.2}
    tipo, det = main._saida_do_filho_pdfvec(0, vm)
    assert tipo == "sem_escala"
    assert "carimbo=indicadas" in det, det
    assert "confianca" in det and "secs=11.2" in det


def test_sem_escala_mostra_o_erro_do_carimbo_quando_houve():
    vm = {"skip": "sem escala (viewport, carimbo nem cota)",
          "err_carimbo": "AuthenticationError: 401", "err_viewport": "KeyError: VP"}
    tipo, det = main._saida_do_filho_pdfvec(0, vm)
    assert tipo == "sem_escala" and "AuthenticationError" in det and "KeyError" in det


def test_memoria_tem_prioridade_sobre_sem_escala():
    """Faltou memória ANTES da escala: o motivo real é memória, não 'sem escala'."""
    vm = {"skip": "sem escala (viewport, carimbo nem cota)", "err_carimbo": "MemoryError: ..."}
    assert main._saida_do_filho_pdfvec(0, vm)[0] == "memoria"


# ── controles ─────────────────────────────────────────────────────────────
def test_CONTROLE_sucesso_normal_e_None():
    vm = {"scale": 75.0, "n_rooms": 40, "rooms_m2": 581.7, "walls_m": 1716.9, "secs": 46.0}
    assert main._saida_do_filho_pdfvec(0, vm) == (None, "")


def test_CONTROLE_rc_diferente_de_zero_NAO_e_daqui():
    """Filho morto (rc≠0) já tem ramo próprio (filho-morreu com stderr) — aqui é None."""
    assert main._saida_do_filho_pdfvec(-6, {})[0] is None
    assert main._saida_do_filho_pdfvec(1, {"skip": "x"})[0] is None


def test_CONTROLE_erro_que_NAO_e_memoria_nao_vira_memoria():
    vm = {"scale": 100.0, "n_rooms": 3, "err_walls": "ValueError: eixo vazio", "err_layers": "KeyError: OCG"}
    assert main._saida_do_filho_pdfvec(0, vm) == (None, "")


def test_CONTROLE_vm_vazio_ou_lixo_nao_levanta():
    assert main._saida_do_filho_pdfvec(0, {}) == (None, "")
    assert main._saida_do_filho_pdfvec(0, None) == (None, "")
    assert main._saida_do_filho_pdfvec(0, "texto") == (None, "")


# ── o chamador USA o classificador e avisa o cliente ───────────────────────
def test_o_pai_chama_o_classificador_logo_depois_de_ler_o_json():
    i = _SRC.find("_vm = _jv.loads(_pr.stdout.strip().splitlines()[-1])")
    assert i > 0
    trecho = _SRC[i:i + 1400]
    assert "_saida_do_filho_pdfvec(_pr.returncode, _vm)" in trecho, (
        "o classificador não é chamado depois de ler o JSON do filho — as saídas voltam a ser mudas")
    assert '"motivo": "memoria"' in trecho, "memória engolida tem que entrar em _pdfvec_falhas"
    assert '_log_error("pdfvec:sem-escala"' in trecho


def test_o_aviso_ao_cliente_inclui_memoria_com_frase_propria():
    i = _SRC.find('if f.get("motivo") in ("tempo", "processo", "memoria")]')
    assert i > 0, "o filtro do aviso voltou a ignorar o motivo 'memoria' — cliente sem aviso"
    trecho = _SRC[i:i + 900]
    assert "densas demais" in trecho and "limite nosso" in trecho, (
        "faltou a frase própria: 'densa demais' não é 'não havia o que medir'")


def test_CONTROLE_guarda_de_fonte_reprova_a_versao_antiga():
    antigo = '_falhou = [f for f in _pdfvec_falhas\n                       if f.get("motivo") in ("tempo", "processo")]'
    assert '"memoria"' not in antigo
