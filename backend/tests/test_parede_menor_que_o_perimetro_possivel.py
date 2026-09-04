# -*- coding: utf-8 -*-
"""O motor mediu MENOS parede do que a geometria permite — e não disse nada.

🩸 04/09/2026, no PRIMEIRO projeto da Caroline (Bolognesi, "Parque Aurora").
O motor apurou **17,18 m** de parede numa casa de **46,79 m²**, e daí saíram a
alvenaria (44,67 m² = 17,18 × 2,60), o chapisco, o reboco e o rodapé dela.

🔑 Entre todos os retângulos de mesma área, o QUADRADO tem o menor perímetro.
Logo nenhuma edificação pode ter menos parede que `4·√área`:

        4 · √46,79  =  27,36 m        contra        17,18 m medidos

Faltam **59%** — e isso IGNORANDO as paredes internas, que só aumentam o
mínimo. Não é regra de bolso nem benchmark de obra (que a regra dura nº3
proíbe usar pra corrigir): é geometria. O limite é uma impossibilidade, não uma
expectativa.

🔑 MEDIDO na base antes de escrever: dos **19** projetos de cliente em que a
gente mede parede em metro, **3 (16%)** estão abaixo do mínimo —
`humberto.oliveira@` 88% abaixo (25/06), `marcioeng72@` 42% (30/08) e a
Caroline 59% (hoje). **Onze itens BRANCOS** saíram desses três.

🪤 SÓ APONTA e REBAIXA. Não corrige o número: inventar a parede que falta seria
exatamente o que a regra nº3 proíbe. O que muda é o selo — número que não pode
estar certo não é "✓ MEDIDO" — e o aviso ao cliente.

🚫 **UMA AFIRMAÇÃO MINHA QUE MORREU NO MESMO DIA.** A 1ª versão deste arquivo
(e do aviso ao cliente) dizia que "a parede quase sempre está num layer que o
motor não reconheceu". Fui MEDIR os layers do arquivo da Caroline pra provar
isso, e o dado derrubou:

    ARQ_HAT=57,9 · ARQ_VISTA01=22,3 · Camada 1=22,1 · PAREDES=17,2
    ARQ_VISTA02=16,5 · ARQ_ESTRUTURA=14,0 · ARQ_VISTA00=11,2 · ARQ_ESQUADRIA=11,0

Dos 251 m, os outros 234 são hachura, as três FACHADAS (elevação, não planta),
caixilho e o layer padrão do AutoCAD. **A escolha de `PAREDES` estava CERTA** —
a parede dela tem 17,18 m mesmo. E 2.408 segmentos somando 251 m dá 10 cm por
segmento: é linha de detalhe, não corrida de parede.

🔑 Eu inventei uma causa — o mesmo pecado que passei o dia inteiro tirando do
motor. O aviso agora diz o que a gente SABE (falta parede) e oferece as duas
hipóteses sem escolher nenhuma.
"""
import ast
import io
import os

import pytest

from engine_rules import parede_abaixo_do_minimo as _abaixo

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()

# Os TRÊS casos reais medidos no banco em 04/09/2026.
_REAIS = [
    ("caroline.passos (Parque Aurora)", 17.18, 46.79),
    ("humberto.oliveira", 34.65, 264.54),
    ("marcioeng72", 49.51, 309.75),
]


@pytest.mark.parametrize("quem,parede,area", _REAIS)
def test_os_casos_REAIS_sao_pegos(quem, parede, area):
    impossivel, minimo = _abaixo(parede, area)
    assert impossivel, (
        "%s deixou de ser acusado: %.2f m de parede numa área de %.2f m² "
        "(mínimo %.2f m)" % (quem, parede, area, minimo))
    assert minimo > parede


def test_projeto_com_parede_farta_NAO_e_acusado():
    """CONTROLE: acusar quem está certo é pior que não acusar ninguém."""
    for parede, area in ((60.0, 46.79), (120.0, 264.54), (200.0, 309.75)):
        impossivel, _ = _abaixo(parede, area)
        assert not impossivel, (
            "%.1f m de parede em %.1f m² é folgado e foi acusado" % (parede, area))


def test_o_minimo_e_o_perimetro_do_quadrado():
    """A conta tem que ser essa, e não um palpite calibrado."""
    _, minimo = _abaixo(1.0, 100.0)
    assert abs(minimo - 40.0) < 0.01, (
        "o mínimo de uma área de 100 m² é 4×√100 = 40 m; veio %.2f" % minimo)
    _, m2 = _abaixo(1.0, 46.79)
    assert abs(m2 - 27.36) < 0.01


def test_a_folga_existe_e_e_pequena():
    """🪤 O limite é exato só pro quadrado perfeito SEM parede interna, e
    medição tem ruído. Sem folga, planta quase quadrada viraria alarme falso."""
    area = 46.79
    _, minimo = _abaixo(1.0, area)
    assert not _abaixo(minimo, area)[0], "no mínimo exato não pode acusar"
    assert not _abaixo(minimo * 0.96, area)[0], "4% abaixo ainda é ruído"
    assert _abaixo(minimo * 0.90, area)[0], "10% abaixo TEM que acusar"
    # e a folga não salva nenhum dos casos reais
    for _quem, parede, ar in _REAIS:
        assert _abaixo(parede, ar)[0]


def test_nao_avalia_o_que_nao_da_pra_avaliar():
    for parede, area in ((0, 46.79), (17.18, 0), (None, None), ("x", "y"),
                         (-5, 46.79), (17.18, -1)):
        assert _abaixo(parede, area) == (False, 0.0) or not _abaixo(parede, area)[0]


# ══════════════════════════════════════════════════════════════════════════
#  O motor tem que APLICAR — e só rebaixar
# ══════════════════════════════════════════════════════════════════════════
def _bloco():
    """Do import até o `except` que fecha o bloco.

    🪤 04/09: era `_FONTE[i:i + 3800]` — janela de tamanho fixo. Bastou eu
    acrescentar o comentário do conserto seguinte pra o aviso e o log saírem
    da janela e DOIS testes reprovarem código correto. Janela de N caracteres
    envelhece a cada linha; âncora nos dois extremos, não.
    """
    i = _FONTE.index("from engine_rules import (parede_abaixo_do_minimo")
    j = _FONTE.index("print(f\"[parede-minimo] nao-fatal:", i)
    return _FONTE[i:j]


def test_o_motor_consulta_a_regra():
    chamou = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "_par_min"
                 for n in ast.walk(ast.parse(_FONTE)))
    assert chamou, "o motor parou de conferir o mínimo de parede"


def test_o_motor_REBAIXA_o_selo():
    b = _bloco()
    assert "_CfP.ESTIMADO" in b, (
        "item derivado de parede impossível voltou a poder sair com ✓ MEDIDO")
    assert 'if _cfp == "confirmado":' in b


def test_o_motor_NUNCA_corrige_o_numero():
    """🚨 Regra nº3: ratio/benchmark só ALERTA. Inventar a parede que falta
    seria o defeito que esta regra existe pra denunciar."""
    b = _bloco()
    for proibido in (".quantity =", ".quantity=", "quantity = _min_per",
                     "quantity = _maior"):
        assert proibido not in b, (
            "o bloco passou a ESCREVER quantidade (%r) — ele só pode apontar"
            % proibido)


def test_o_cliente_e_avisado_na_LINHA_e_no_projeto():
    b = _bloco()
    assert "menos parede do que o mínimo" in b, (
        "sumiu o aviso na linha — é onde o cliente lê o número")
    assert "PAREDE INCOMPLETA" in b, "sumiu o aviso de topo do projeto"
    assert "layer" in b, (
        "o aviso parou de dizer ONDE procurar; sem isso ele é só má notícia")


def test_o_alarme_e_CRITICO():
    b = _bloco()
    assert 'severity="critical"' in b, (
        "parede impossível virou log comum — some no meio do bookkeeping")


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — antes não havia julgamento nenhum
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_sem_a_regra_os_tres_casos_passavam():
    def _regra_ANTIGA(_parede, _area):
        return False, 0.0        # não existia conferência

    passavam = [q for q, p, a in _REAIS if not _regra_ANTIGA(p, a)[0]]
    assert len(passavam) == 3, "controle mal montado"
    pega = [q for q, p, a in _REAIS if _abaixo(p, a)[0]]
    assert len(pega) == 3, (
        "a regra de hoje não cobre os três casos reais que a motivaram — "
        "escapariam %s" % [q for q, p, a in _REAIS if not _abaixo(p, a)[0]])


# ══════════════════════════════════════════════════════════════════════════
#  O guarda não pode depender da FORMA do item
# ══════════════════════════════════════════════════════════════════════════
from engine_rules import comprimento_de_parede_na_observacao as _compr  # noqa: E402

# A observação REAL do filhote `ev6edc7e` (Caroline), 04/09/2026.
_OBS_REAL = ("Estimativa: comprimento total do layer PAREDES = 17,18 m "
             "(confirmado) × pé-direito estimado 2,60 m = 44,67 m². Descontar "
             "vãos de esquadrias > 2 m² na revisão. Confirmar pé-direito em corte.")


def test_o_comprimento_e_lido_da_OBSERVACAO():
    """🩸 O furo que só apareceu RODANDO num arquivo real.

    O conserto foi escrito olhando a 1ª rodada da Caroline, onde a parede saiu
    como "17,18 ml". Rodei o filhote do MESMO arquivo e o guarda ficou mudo: o
    motor não é determinístico e naquela rodada a parede saiu só em **m²**.

    🔑 O comprimento não se perde — fica escrito na observação. Ler dali é
    exato e cobre as duas formas.
    """
    assert _compr(_OBS_REAL) == 17.18, (
        "parou de ler o comprimento da observação — o guarda volta a depender "
        "da forma do item e some nas rodadas em que a parede sai em m²")


def test_o_caso_da_Caroline_e_pego_pelas_DUAS_formas():
    area = 46.79
    por_ml = _abaixo(17.18, area)[0]                 # rodada 1: item em ml
    por_obs = _abaixo(_compr(_OBS_REAL), area)[0]    # rodada 2: item em m²
    assert por_ml and por_obs, (
        "a mesma casa tem que ser acusada nas duas formas: ml=%s obs=%s"
        % (por_ml, por_obs))


def test_a_leitura_da_observacao_nao_inventa():
    for obs in ("área do layer PAREDES = 44,67 m²", "", None,
                "comprimento total do layer PAREDES = m",
                "pé-direito estimado 2,60 m"):
        assert _compr(obs) is None, (
            "extraiu comprimento de onde não há: %r" % (obs,))


def test_o_motor_junta_as_DUAS_fontes():
    b = _FONTE[_FONTE.index("_paredes_ml = ["):]
    b = b[:b.index("_impossivel, _min_per")]
    assert "_compr_obs(" in b, (
        "o motor voltou a olhar só a unidade do item — perde a rodada em que "
        "a parede sai em m² com o comprimento na observação")
    assert "_paredes_ml.append" in b


def test_pega_o_MAIOR_comprimento_das_fontes():
    """🪤 Maior = violação menos provável. O erro do guarda tem que cair pro
    lado de CALAR, nunca pro de acusar quem está certo.

    🩸 04/09, teste de mutação DESTE teste: a 1ª versão procurava
    `"max(_paredes_ml" in _FONTE[i:i+160]` — e passou VERDE com a mutação
    aplicada, porque existe um SEGUNDO `max(_paredes_ml)` poucas linhas abaixo
    (o `_maior` do bloco de rebaixamento) que cai dentro da janela. Guarda
    satisfeito por texto vizinho e sem relação é a família que eu passei o dia
    inteiro consertando — e reapareceu no meu próprio teste. Âncora na CHAMADA
    inteira, não numa janela.
    """
    assert "_par_min(max(_paredes_ml" in _FONTE, (
        "parou de usar o maior comprimento na conferência — passa a acusar por "
        "causa de um trecho curto de parede")
    assert "_par_min(min(_paredes_ml" not in _FONTE


def test_a_soma_da_EXTRACAO_nao_entra_na_comparacao():
    """🚨 Conserto de um erro meu, no mesmo dia em que o cometi.

    Eu tinha acrescentado `sum(_compr_paredes)` (a soma de TODOS os layers de
    parede da extração) como "terceira fonte", achando que era a medida
    robusta. Medi no arquivo da Caroline e o número desmentiu:

        layers_de_parede=31   soma=251,23 m   maior=ARQ_HAT(57,94 m)

    251 m contra um mínimo de 27,36 m. Como a comparação usa `max`, entrar com
    a soma **desligava o alarme em todo projeto** — eu anulei o guarda que
    estava consertando, e só descobri porque RODEI e li o número.

    🔑 E o maior "layer de parede" é `ARQ_HAT` — hachura. A soma mede "quanta
    linha existe no desenho", não "quanta parede tem o edifício".
    """
    i = _FONTE.index("_impossivel, _min_per = _par_min(")
    trecho = _FONTE[max(0, i - 2500):i]
    assert "_paredes_ml.append(sum(_compr_paredes))" not in trecho, (
        "a soma da extração voltou pra dentro da comparação — com `max` ela "
        "desliga o alarme em todo projeto (251 m contra um mínimo de 27 m)")
    assert "_paredes_ml.append(sum(" not in _FONTE, (
        "alguma soma de layers voltou pra lista comparada")


def test_a_MEDICAO_da_extracao_continua_sendo_gravada():
    """Ela não serve de piso, mas é o dado que explicou o caso da Caroline:
    a parede ESTÁ no desenho (251 m) e o item usou 17,18 m de um layer só."""
    assert "motor:parede-medida" in _FONTE, (
        "sumiu o log que mede quanta parede a extração acha — sem ele a gente "
        "não teria descoberto que o problema é escolha de layer, não leitura")
    assert "layers_de_parede=%d" in _FONTE


def test_o_aviso_NAO_inventa_a_causa():
    """🩸 04/09, mesmo dia: a 1ª redação dizia "provavelmente está num layer que
    o motor não reconheceu". Fui MEDIR os layers do arquivo da Caroline pra
    provar a frase, e o dado derrubou:

        ARQ_HAT=57,9 · ARQ_VISTA01=22,3 · Camada 1=22,1 · PAREDES=17,2
        ARQ_VISTA02=16,5 · ARQ_ESTRUTURA=14,0 · ARQ_VISTA00=11,2 · ARQ_ESQUADRIA=11,0

    Os outros 234 m são hachura, as três FACHADAS (elevação, não planta),
    caixilho e o layer padrão do AutoCAD. A escolha de `PAREDES` estava CERTA;
    a parede dela tem 17,18 m mesmo.

    🔑 Ou seja: eu inventei uma causa — exatamente o pecado que passei o dia
    tirando do motor (`project_selo_zero_nao_prova_origem`). O aviso tem que
    dizer o que a gente SABE e oferecer as hipóteses sem escolher uma.
    """
    import re as _re
    b = _bloco()
    i = b.index("PAREDE INCOMPLETA")
    # 🪤 A frase que o cliente lê NÃO existe inteira no fonte: ela é montada de
    # literais adjacentes quebrados por linha ("...não sabe qual é a " + "sua:
    # as paredes..."). Procurar no fonte cru devolve zero e o guarda acusa o
    # texto CERTO — mesmo tropeço de `test_email_nao_afirma_medicao`. Cola os
    # literais antes de procurar.
    frase = _re.sub(r'"\s*\n\s*"', "", b[i:i + 1600])
    assert "provavelmente está num layer" not in frase, (
        "o aviso voltou a AFIRMAR a causa; medido no arquivo real, ela estava "
        "errada — os outros layers eram fachada e hachura, não parede")
    assert "hachura ou sólido" in frase, (
        "sumiu a 1ª hipótese (parede desenhada como hachura/sólido) — é a que "
        "o dado da Caroline torna mais provável")
    assert "não sabe qual é a sua" in frase, (
        "o aviso parou de admitir que não sabe qual das causas é — voltou a "
        "vender palpite como diagnóstico")
