# -*- coding: utf-8 -*-
"""O teto de DWG recusou um arquivo que a gente lê — por causa de extrapolação.

🩸 03/09/2026, FÁBIO SHIRAISHI (job `75dab573`, "BRB Estadio"), primeiro projeto
dele. DWG de 44,5 MB recusado por um teto de 40 MB, com o log dizendo:

    "converter pediria ~2227 MB de RAM e derrubaria o servidor; nem tentei"

Baixei o arquivo dele do nosso Storage e medi as três etapas:

    conversão: pico   836 MB (18,8×) em 27 s     ← o previsto era 2.227 MB
    DXF gerado:       248,3 MB                    ← abaixo do teto interno (250)
    extração:  pico 1.964 MB (7,9× o DXF) em 87 s, exit 0

Cabia folgado nas três. E ele reagiu subindo um **PDF** — o caminho que só
estima. Recusa errada não devolve o cliente pro lugar certo; empurra ele pro
pior caminho disponível.

🔑 POR QUE A PREVISÃO ERRAVA. As quatro medidas que fixaram o teto de 40 MB
eram todas de arquivo PEQUENO (3,1 a 24,6 MB), onde o fator é 43–53×. Parte do
custo da conversão é FIXA, então o fator CAI conforme o arquivo cresce. Medido
nos grandes, no mesmo dia:

    11,7 MB → ~29×   (produção, Render)
    44,5 MB →  18,8×
    53,2 MB →  26×

Extrapolar 53× de um arquivo de 3 MB para um de 44 MB errou por 2,7 vezes — e
o preço foi um cliente novo recusado no primeiro projeto.

🪤 Este teto protege só a CONVERSÃO, que roda no processo do servidor sem trava
nenhuma. A extração tem o próprio juiz: a trava de 2,5 GB do processo filho.
Confundir os dois foi o que produziu três tetos discordando entre si.
"""
import io
import os
import sys
import textwrap

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from dwg_extractor import _MAX_DWG_BYTES

MB = 1024 * 1024

# Os três casos reais medidos em 03/09/2026: (nome, MB do DWG, fator medido).
_MEDIDOS = [("cliente-40 (produção)", 11.7, 29.0),
            ("Fábio 75dab573", 44.5, 18.8),
            ("Patrick dbd0d97e", 53.2, 26.0)]

# Quanto o pico da conversão pode chegar sem ameaçar o container de 4 GiB.
# O processo do servidor fica em ~100–230 MB medidos; 2,2 GB deixa ~1,6 GB.
_ORCAMENTO_MB = 2200
# Pior fator plausível nos grandes — pessimista contra os 18,8–29 medidos.
_FATOR_PESSIMISTA = 35


# ══════════════════════════════════════════════════════════════════════════
#  A PORTA DE VERDADE — a fatia real do process_job, executada
# ══════════════════════════════════════════════════════════════════════════
# 🪤 Recorte por ÂNCORA (`if _tam_dwg > _TETO_DWG:`), nunca por janela de
# tamanho fixo, e a fatia vai do `try:` do import da constante até a linha da
# conversão — é ali que a decisão acontece.
def _fatia_da_trava_do_dwg():
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    ancora = "                        if _tam_dwg > _TETO_DWG:\n"
    assert src.count(ancora) == 1, (
        "a âncora da trava do DWG deixou de ser única — reveja o recorte "
        "antes de confiar neste guarda")
    i_anc = src.index(ancora)
    inicio = ("                        try:\n"
              "                            from dwg_extractor import "
              "_MAX_DWG_BYTES as _TETO_DWG\n")
    assert src.count(inicio) == 1
    i = src.index(inicio)
    fim = "                            dxf_path = convert_dwg_to_dxf(cad_path)\n"
    assert src.count(fim) == 1
    j = src.index(fim, i_anc) + len(fim)
    assert i < i_anc < j, "as âncoras saíram de ordem"
    fatia = textwrap.dedent(src[i:j])
    assert "convert_dwg_to_dxf(cad_path)" in fatia and "_TETO_DWG" in fatia
    return fatia


def _dwg_de(tmp_path, nome, mb):
    """Cria um arquivo com o TAMANHO do caso real (esparso: não escreve 44 MB)."""
    p = os.path.join(str(tmp_path), nome)
    with io.open(p, "wb") as f:
        f.truncate(int(mb * MB))
    return p


def _porta_do_dwg(caminho):
    """EXECUTA a trava anti-OOM real e devolve o que ela decidiu."""
    visto = {"converteu": False, "recusou": False, "log": [],
             "aviso_pro_cliente": "", "teto_mb": None}

    def _converte(p):
        visto["converteu"] = True
        return p + ".dxf"

    class _JobsFalso:
        def update_field(self, job_id, **kw):
            visto.setdefault("passos", []).append(kw.get("current_step", ""))

    msgs = []
    ns = {
        "os": os, "io": io,
        "cad_path": caminho, "job_id": "job-de-teste",
        "_descartou_por_tamanho": False, "dxf_path": None,
        "_dxf_grandes_msgs": msgs, "jobs": _JobsFalso(),
        "convert_dwg_to_dxf": _converte,
        "_log_error": lambda *a, **k: visto["log"].append(
            " | ".join(str(x) for x in a)),
    }
    exec(compile(_fatia_da_trava_do_dwg(), "<main:trava-dwg>", "exec"), ns, ns)
    visto["recusou"] = bool(ns.get("_descartou_por_tamanho"))
    visto["aviso_pro_cliente"] = "\n".join(msgs)
    visto["teto_mb"] = ns["_TETO_DWG"] / MB
    return visto


def test_o_arquivo_de_44MB_do_job_75dab573_passa(tmp_path):
    """44,5 MB: convertia com 836 MB de pico e extraía com 1.964 MB."""
    r = _porta_do_dwg(_dwg_de(tmp_path, "BRB_Estadio.dwg", 44.5))
    assert r["converteu"] and not r["recusou"], (
        "o DWG de 44,5 MB do job 75dab573 voltou a ser recusado (teto em vigor "
        "no process_job: %.0f MB) — medido, ele cabe nas três etapas. "
        "Aviso que iria pra ele: %r" % (r["teto_mb"], r["aviso_pro_cliente"]))
    assert not r["aviso_pro_cliente"], r["aviso_pro_cliente"]


def test_o_teto_que_a_porta_USA_e_o_da_medicao(tmp_path):
    """🪤 A constante certa não vale nada se o `process_job` não a enxergar:
    o `except` dele fixa 40 MB, o número velho, e a queda é silenciosa."""
    r = _porta_do_dwg(_dwg_de(tmp_path, "qualquer.dwg", 1))
    assert r["teto_mb"] * MB == _MAX_DWG_BYTES, (
        "o process_job está julgando por %.0f MB e a medição fixou %.0f MB — "
        "o import da constante quebrou e o except assumiu calado"
        % (r["teto_mb"], _MAX_DWG_BYTES / MB))


def test_CONTROLE_uma_prancha_ENORME_continua_sendo_recusada(tmp_path):
    """A trava existe pra alguma coisa: sem este controle, um teto infinito
    passaria no teste do job 75dab573 e derrubaria o container."""
    r = _porta_do_dwg(_dwg_de(tmp_path, "gigante.dwg", 150))
    assert r["recusou"] and not r["converteu"], (
        "DWG de 150 MB entrou na conversão — pediria ~5 GB num container de 4")
    assert "grande demais" in r["aviso_pro_cliente"], r["aviso_pro_cliente"]
    assert "não tem defeito" in r["aviso_pro_cliente"], (
        "o aviso culpa o arquivo do cliente: %r" % r["aviso_pro_cliente"])


def test_NOTA_o_teto_antigo_era_40MB_e_o_arquivo_tinha_44():
    """📌 NOTA DE CALIBRAÇÃO — não é controle positivo.

    🩸 03/09, 2ª revisão: isto se chamava `test_CONTROLE_...` e a docstring
    dizia "sem isto o teste acima poderia estar medindo nada". Era aritmética
    pura (`44.5 * MB > 40 * MB`): não exercita nenhuma função do produto, e
    passaria com o código inteiro quebrado. Controle que não exercita nada
    **infla a contagem de guardas** e dá a sensação de cobertura.

    🔑 O que ela é de verdade: o registro dos dois números do caso, pra que a
    próxima pessoa saiba de onde veio o teto — e reprove se alguém "arredondar"
    a história. Renomeada pra dizer isso.
    """
    TETO_ANTIGO_MB, ARQUIVO_DO_FABIO_MB = 40, 44.5
    assert ARQUIVO_DO_FABIO_MB > TETO_ANTIGO_MB, (
        "os números do caso mudaram: o arquivo do Fábio tinha 44,5 MB e o teto "
        "de então era 40 MB — se isso não é mais verdade, a história escrita "
        "nesta docstring precisa ser refeita")


def test_o_teto_novo_cabe_no_orcamento_de_memoria():
    """O teto não pode ser um número escolhido por gosto.

    No pior fator plausível pros arquivos grandes, o pico da conversão tem que
    caber no orçamento — senão a gente troca uma recusa errada por uma queda.
    """
    pico_mb = (_MAX_DWG_BYTES / MB) * _FATOR_PESSIMISTA
    assert pico_mb <= _ORCAMENTO_MB, (
        "com o teto em %.0f MB e o fator pessimista de %d×, a conversão pediria "
        "%.0f MB — acima do orçamento de %d MB"
        % (_MAX_DWG_BYTES / MB, _FATOR_PESSIMISTA, pico_mb, _ORCAMENTO_MB))


def test_CONTROLE_um_teto_grande_demais_REPROVA_neste_criterio():
    """O critério acima precisa saber dizer não."""
    absurdo = 150 * MB
    assert (absurdo / MB) * _FATOR_PESSIMISTA > _ORCAMENTO_MB, (
        "o critério de orçamento aceita qualquer teto — ele não protege nada")


def test_nenhum_caso_medido_desmente_o_fator_pessimista():
    """Se um arquivo real medir acima do fator pessimista, o teto está errado.

    🪤 03/09, 2ª revisão: a docstring prometia "avisa quando a PRÓXIMA medição
    derrubar a conta", e isso não é automático — este teste só enxerga o que
    estiver escrito em `_MEDIDOS`, que é uma lista à mão. Ele não vai buscar
    medição nova em lugar nenhum.

    🔑 A promessa honesta é: **mediu um arquivo grande? acrescente aqui.** É a
    lista que faz o teste valer, e a única coisa que a impede de envelhecer é
    esta frase. Se um dia houver telemetria do fator real por conversão, aí sim
    dá pra automatizar — hoje não há.
    """
    piores = [(nome, f) for nome, _mb, f in _MEDIDOS if f > _FATOR_PESSIMISTA]
    assert not piores, (
        "medição real acima do fator pessimista, o orçamento precisa ser "
        "refeito: " + ", ".join("%s = %.1f×" % p for p in piores))


def test_o_log_nao_promete_um_numero_que_a_medicao_ja_desmentiu():
    """O log dizia "pediria ~{tam * 50} MB" — 2,7× acima do medido.

    Número inventado dentro de um log é pior que log nenhum: ele vira a
    justificativa de quem for reavaliar o teto depois.
    """
    import io
    import os
    fonte = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()
    assert "_tam_dwg * 50 /" not in fonte, (
        "o log voltou a estimar a RAM da conversão com o fator 50×, que só "
        "vale pra arquivo pequeno")
    assert "_tam_dwg * 30 /" in fonte, (
        "sumiu a estimativa da RAM no log da recusa — ela é o que permite "
        "auditar a decisão depois")
