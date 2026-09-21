# -*- coding: utf-8 -*-
"""A régua do recorte de ambientes: o log tem que guardar o que COMPARA.

🚨 20/09/2026, passo 1 da inversão do motor. A inversão (medir primeiro, listar
depois) estava travada por um pré-requisito reprovado em 19/09: "o recorte de
ambientes não corresponde ao projeto real — o quadro do autor lista 115
ambientes com maiores 525/285/35,6 e a geometria recortou 142 com maiores
204/181/167/163; nenhum valor coincide".

🩸 A COMPARAÇÃO ERA INVÁLIDA. O campo `primeiros=` do log são os 8 PRIMEIROS EM
ORDEM DE LEITURA, não os maiores — está escrito `_ar[:8]` no código, e o
comentário vizinho registra um dia inteiro perdido pela MESMA armadilha em
agosto. Os "maiores do autor" eram os maiores de uma amostra de 8; os da
geometria, os maiores de 142. Duas listas diferentes.

📏 No agregado, o mesmo job BATE: a geometria somou 2.429,1 m² contra 2.350
declarados pelo cliente — 3,4%. O segundo caso com área do cliente bate a 8%.
Os casos que erram feio (0,14× / 3,5× / 24×) têm a área de referência vinda de
fonte desconhecida ou da própria IA, nunca do cliente.

🔑 Por isso este commit NÃO inverte nada e NÃO mexe no recorte. Ele conserta a
RÉGUA: o log passa a guardar quantos ambientes o autor lista, quanto somam, os
MAIORES em ordem, e quantos passam do teto de 500 m² — o mesmo teto que faz a
geometria descartar o ambiente de 525,05 m² do autor por 25 m² de margem.

Alcance medido ANTES de escrever: 22 jobs/mês registram o quadro do autor,
contra 14 que informam área no upload (9% dos 262 jobs com CAD).
"""
import io
import os
import re
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import main  # noqa: E402
import dxf_rooms_shadow as sombra  # noqa: E402

_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()

# O caso real de 19/09, na ordem em que o log o registrou. ⏭️ Não se sabe o
# rótulo de cada um: o log de 19/09 não guardava. Por isso o 525,05 NÃO pode
# ser chamado de ambiente — pode ser subtotal de pavimento.
QUADRO_DO_CASO_REAL = [525.05, 19.63, 284.55, 35.57, 2.0, 2.88, 3.42, 3.42]
SO_AMBIENTES = [""] * len(QUADRO_DO_CASO_REAL)


# ══════════════════════════════════════════════════════════════════════════
#  🩸 O PAI NÃO PODE SER IRMÃO DO FILHO — o que a revisão derrubou
# ══════════════════════════════════════════════════════════════════════════
# A primeira versão desta régua repetiu a doença que ela veio matar. O regex do
# quadro (`engine_rules._RE_AREA_QUADRO`) captura DE PROPÓSITO os rótulos
# `total`, `construída`, `útil` e `privativa` — só o terreno é descartado. A
# lista chamada "quadro de AMBIENTES" vinha com as linhas de TOTAL dentro, e a
# régua somava tudo. Num quadro comum o log dizia `soma=4442` para 56 m² de
# ambientes, e os dois "maiores ambientes do autor" eram o total e a área útil.
def test_o_TOTAL_do_quadro_nao_entra_como_ambiente(tmp_path):
    """🧪 CONTROLE POSITIVO, executando o PRODUTOR da lista, não um fixture.

    É este teste que reprova a versão anterior: com ela, `soma` dava 4.442,0 e
    `acima_de_500` dava 2 — e os dois "ambientes acima do teto" eram a linha de
    total e a de área útil do próprio quadro.
    """
    from engine_rules import areas_do_texto_da_prancha_rotuladas as _rot
    from engine_rules import areas_do_texto_da_prancha as _vals

    # 🔒 Quadro inventado, no formato que o CAD escreve. Nada de cliente.
    quadro = ["A = 25,40 m2", "A = 18,60 m2", "A = 12,00 m2",
              "AREA CONSTRUIDA 56,00 m2", "AREA TOTAL 2.350,00 m2",
              "AREA UTIL 1.980,00 m2", "AREA DO TERRENO 5.000,00 m2"]
    pares = _rot(quadro)
    assert [v for _r, v in pares] == _vals(quadro), (
        "a versão rotulada divergiu da antiga — o consenso de área depende de "
        "a lista de valores continuar idêntica")

    linha = main.linha_do_quadro_de_areas(
        "planta.dxf", _vals(quadro), [r for r, _v in pares])
    assert "AMBIENTES: n=3 soma=56.0" in linha, (
        "as linhas de TOTAL do quadro entraram como ambiente: %r" % linha)
    assert "acima_de_500=0" in linha, (
        "um somatório do quadro virou 'ambiente acima do teto' — é exatamente "
        "o número que decidiria sobre o teto de 500: %r" % linha)
    assert "SOMATORIOS do quadro: n=3" in linha, (
        "os totais sumiram do log; eles é que são candidatos a área total: %r"
        % linha)
    # 🪤 O terreno continua fora, como sempre foi.
    assert "5000" not in linha, linha


def test_CONTROLE_ambiente_grande_de_verdade_AINDA_e_acusado():
    """🧪 O separador não pode "resolver" o problema devolvendo sempre zero:
    um ambiente SEM rótulo acima de 500 m² tem que continuar aparecendo."""
    linha = main.linha_do_quadro_de_areas(
        "planta.dxf", [900.0, 25.0, 2350.0], ["", "", "total"])
    assert "acima_de_500=1" in linha, (
        "o salão de 900 m² sumiu junto com os somatórios: %r" % linha)
    assert "AMBIENTES: n=2 soma=925.0" in linha, linha


def test_SEM_rotulo_a_regua_NAO_soma_nada():
    """🪤 Falta de estado não é neutra. Job antigo não tem a chave nova na
    metadata; somar ali seria publicar um número com cara de medida do autor —
    o mesmo erro, de novo."""
    linha = main.linha_do_quadro_de_areas("planta.dxf", QUADRO_DO_CASO_REAL)
    assert "rotulos=ausentes" in linha, linha
    for proibido in ("soma=", "maiores=", "acima_de_500="):
        assert proibido not in linha, (
            "somou sem saber o que é ambiente e o que é total: %r" % linha)
    # e com rótulo de tamanho diferente (metadata inconsistente) idem
    linha2 = main.linha_do_quadro_de_areas("planta.dxf", [1.0, 2.0], [""])
    assert "rotulos=ausentes" in linha2, linha2


# ══════════════════════════════════════════════════════════════════════════
#  O LADO DO AUTOR — a régua EXECUTA, não é lida do fonte
# ══════════════════════════════════════════════════════════════════════════
def test_a_regua_guarda_os_MAIORES_e_nao_so_os_primeiros():
    """🩸 Sem isto a linha segue comparável a nada — foi o que sustentou, por
    um dia inteiro, um veredito mal fundamentado sobre o motor."""
    linha = main.linha_do_quadro_de_areas("planta.dxf", QUADRO_DO_CASO_REAL,
                                          SO_AMBIENTES)
    assert "maiores=" in linha, (
        "o log voltou a guardar só os primeiros lidos: %r" % linha)
    m = re.search(r"maiores=\[([^\]]*)\]", linha)
    assert m, linha
    valores = [float(x) for x in m.group(1).split(",") if x.strip()]
    assert valores == sorted(valores, reverse=True), (
        "a lista de maiores não está em ordem decrescente: %r" % valores)
    assert valores[0] == pytest.approx(525.05, abs=0.1), valores
    assert valores[1] == pytest.approx(284.55, abs=0.1), valores


def test_a_regua_guarda_a_SOMA_e_a_CONTAGEM_inteiras():
    """🪤 O `[:8]` é corte de EXIBIÇÃO. Sem soma e contagem do conjunto todo,
    não dá pra comparar com o `rooms_m2_total` da geometria."""
    areas = [10.0] * 100 + [500.0]
    linha = main.linha_do_quadro_de_areas("planta.dxf", areas, [""] * 101)
    assert "n=101 candidatos" in linha, linha
    assert "soma=1500.0" in linha, (
        "a soma não cobre o quadro inteiro, só a amostra exibida: %r" % linha)


def test_a_regua_conta_quantos_passam_do_teto_da_geometria():
    """🔑 A hipótese que só isto permite testar: o teto de 500 m² da geometria
    descarta ambiente LEGÍTIMO?"""
    linha = main.linha_do_quadro_de_areas("planta.dxf", QUADRO_DO_CASO_REAL,
                                          SO_AMBIENTES)
    assert "acima_de_500=1" in linha, (
        "não dá pra saber se o autor tem ambiente acima do teto: %r" % linha)


def test_CONTROLE_quadro_sem_ambiente_grande_nao_acusa_nada():
    """🧪 Sem este controle, um contador que devolvesse sempre 1 passaria no
    teste acima e toda planta pareceria ter ambiente cortado pelo teto."""
    linha = main.linha_do_quadro_de_areas("planta.dxf", [12.0, 30.0, 8.5],
                                          ["", "", ""])
    assert "acima_de_500=0" in linha, linha
    assert "n=3 candidatos" in linha and "soma=50.5" in linha, linha


def test_a_regua_nao_quebra_com_lixo_no_quadro():
    """A leitura do quadro vem de texto de CAD: vem vazio, vem None, vem str."""
    for entrada, rot in (([], []), ([None, "x", 10.0], ["", "", ""]),
                         (None, None)):
        linha = main.linha_do_quadro_de_areas("planta.dxf", entrada, rot)
        assert "n=" in linha, (entrada, linha)


def test_so_NUMERO_entra_na_conta_nem_que_o_texto_pareca_numero():
    """🩸 A sabotagem que sobreviveu à primeira rodada: trocar
    `isinstance(x, (int, float))` por um teste de "parece número" passava
    verde, porque nenhum caso distinguia os dois.

    `areas_do_texto_da_prancha` entrega FLOAT — o parser pt-BR já rodou lá
    (onde "1.234" vale mil). Se um dia chegar string aqui, somá-la em silêncio
    esconderia a quebra do parser e um erro de 1000× entraria na régua.
    """
    linha = main.linha_do_quadro_de_areas("planta.dxf", [10.0, "20.0", 30.0],
                                          ["", "", ""])
    assert "soma=40.0" in linha, (
        "uma string que parece número entrou na conta — se o parser pt-BR "
        "quebrar, o erro passa por aqui sem ninguém ver: %r" % linha)
    m = re.search(r"maiores=\[([^\]]*)\]", linha)
    assert m and "20.0" not in m.group(1), linha


def test_a_regua_nao_leva_nome_de_ambiente_pro_log():
    """🔒 Regra dura nº6 — o repositório é público e o log é lido no admin:
    vai NÚMERO e rótulo curto, nunca o texto que o autor escreveu."""
    linha = main.linha_do_quadro_de_areas(
        "planta.dxf", [10.0, "SALA DE REUNIAO", 20.0], ["", "", ""])
    m = re.search(r"maiores=\[([^\]]*)\]", linha)
    assert m and "SALA" not in m.group(1).upper(), (
        "texto do quadro do cliente vazou pra lista de maiores: %r" % linha)
    assert "soma=30.0" in linha, (
        "o texto entrou na conta em vez de ser ignorado: %r" % linha)


def test_o_rotulo_que_vai_pro_log_e_curto_e_normalizado():
    """🔒 O rótulo vem do texto do autor. Só passam as quatro palavras da
    régua, normalizadas — nunca a frase que ele escreveu."""
    from engine_rules import areas_do_texto_da_prancha_rotuladas as _rot
    # 🪤 O regex exige o número logo depois do rótulo: "ÁREA CONSTRUÍDA DO
    # PAVIMENTO TÉRREO 56 m²" não casa, e isso é comportamento existente — o
    # teste usa as formas que a régua realmente lê.
    pares = _rot(["AREA CONSTRUIDA 56,00 m2", "Área Útil 1.980,00 m2",
                  "AREA TOTAL 2.350,00 m2", "A = 12,00 m2"])
    rotulos = sorted({r for r, _v in pares})
    assert rotulos == ["", "construida", "total", "util"], rotulos
    assert all(len(r) <= 12 for r, _v in pares), (
        "rótulo longo demais para ser normalizado — cheira a texto do autor: "
        "%r" % pares)


def test_o_motor_CHAMA_a_regua_em_vez_de_remontar_a_linha():
    """🪤 Não reimplemente a régua: se o `process_job` voltar a montar a string
    na mão, as duas divergem em silêncio e os guardas acima deixam de valer."""
    assert "def linha_do_quadro_de_areas(" in _FONTE
    # 🪤 Duas âncoras falsas aqui: o nome do stage aparece antes na lista
    # `_STAGES_DIAGNOSTICO`, e a PRIMEIRA chamada do stage é o outro ramo (o
    # `n=1 candidato ÚNICO`, que entra no consenso e não usa esta régua). O que
    # interessa é o ramo do QUADRO — o `elif _ar:`.
    m = re.search(r"\n\s*elif _ar:\n(.{0,900})", _FONTE, re.S)
    assert m, "o ramo do quadro de ambientes sumiu do process_job"
    assert "linha_do_quadro_de_areas(" in m.group(1), (
        "o log do quadro de áreas parou de usar a régua e voltou a montar a "
        "linha na mão: %r" % m.group(1)[:220])


# ══════════════════════════════════════════════════════════════════════════
#  O LADO DA GEOMETRIA — o recorte roda de verdade, num DXF montado aqui
# ══════════════════════════════════════════════════════════════════════════
def _dxf_com_salas(tmp_path, lados_m, nome="planta.dxf"):
    """DXF real com uma sala quadrada por lado pedido, lado a lado.

    🪤 Cada parede vai em 3 segmentos. O motor descarta a prancha inteira
    abaixo de 20 segmentos ("geometria insuficiente"), e um quadrado por sala
    daria 4 — a bancada mediria o vazio e passaria verde.
    """
    ezdxf = pytest.importorskip("ezdxf")
    doc = ezdxf.new()
    msp = doc.modelspace()
    x = 0.0
    for lado in lados_m:
        p = [(x, 0.0), (x + lado, 0.0), (x + lado, lado), (x, lado), (x, 0.0)]
        for i in range(len(p) - 1):
            (ax, ay), (bx, by) = p[i], p[i + 1]
            for k in range(3):     # parede em 3 pedaços colineares
                t0, t1 = k / 3.0, (k + 1) / 3.0
                msp.add_line((ax + (bx - ax) * t0, ay + (by - ay) * t0),
                             (ax + (bx - ax) * t1, ay + (by - ay) * t1))
        x += lado + 5.0          # espaço entre salas: não se colam
    caminho = str(tmp_path / nome)
    doc.saveas(caminho)
    return caminho


def test_CONTROLE_o_dxf_de_teste_tem_geometria_suficiente(tmp_path):
    """🧪 O motor recusa prancha com menos de 20 segmentos. Sem este controle,
    todo teste de geometria abaixo passaria medindo um dicionário vazio."""
    out = sombra.medir_um(_dxf_com_salas(tmp_path, [6.0, 8.0]), 1.0)
    assert "skip" not in out, (
        "o DXF de teste foi recusado pelo motor: %r" % out)
    assert out.get("n_segs", 0) >= 20, out


def test_CONTROLE_a_geometria_recorta_as_salas_que_desenhei(tmp_path):
    """🧪 Prova que a bancada mede o recorte REAL. Se este falhar, todo teste
    de geometria abaixo está medindo o vazio."""
    caminho = _dxf_com_salas(tmp_path, [6.0, 8.0, 10.0])     # 36 · 64 · 100 m²
    out = sombra.medir_um(caminho, 1.0)
    assert out.get("n_rooms") == 3, out
    assert out.get("rooms_m2") == pytest.approx(200.0, abs=1.0), out
    assert out.get("acima_do_teto_n") == 0, out


def test_a_sombra_registra_o_que_o_teto_de_500_jogou_fora(tmp_path):
    """🔑 O achado que este commit existe pra poder medir: hoje o log não
    distingue "não existe ambiente grande" de "existe e eu descartei".

    Um salão de 900 m² é ambiente de verdade em fórum, ginásio ou pátio
    coberto — e cai fora do recorte por causa de `MAX_ROOM_M2 = 500`.
    """
    caminho = _dxf_com_salas(tmp_path, [6.0, 30.0])           # 36 m² · 900 m²
    out = sombra.medir_um(caminho, 1.0)

    assert out.get("n_rooms") == 1, (
        "o salão de 900 m² entrou no recorte — o teto mudou sem este guarda "
        "saber: %r" % out)
    assert out.get("acima_do_teto_n") == 1, (
        "o que o teto descartou continua invisível: %r" % out)
    assert out["acima_do_teto_top"][0] == pytest.approx(900.0, abs=5.0), out
    assert out.get("acima_do_teto_m2") == pytest.approx(900.0, abs=5.0), out
    assert out.get("teto_m2") == sombra.MAX_ROOM_M2, (
        "o log não diz contra qual teto a conta foi feita — daqui a um mês "
        "ninguém sabe se o número saiu de 500 ou de outro valor: %r" % out)


def test_o_recorte_NAO_muda_por_causa_desta_instrumentacao(tmp_path):
    """🪤 Este commit é SÓ LEITURA. O que a sombra entrega como ambiente tem
    que ser exatamente o mesmo de antes — senão a régua passa a medir o
    conserto em vez do problema."""
    caminho = _dxf_com_salas(tmp_path, [6.0, 8.0, 30.0, 40.0])
    out = sombra.medir_um(caminho, 1.0)
    assert out["n_rooms"] == 2, out                    # 36 e 64
    assert out["rooms_m2"] == pytest.approx(100.0, abs=1.0), out
    assert out["top"][0] == pytest.approx(64.0, abs=1.0), out
    assert out["acima_do_teto_n"] == 2, out            # 900 e 1600
