# -*- coding: utf-8 -*-
"""A prancha com 376 cotas era tratada PIOR que a prancha com 3.

🚨 26/08/2026. A "régua da prancha" só valida a escala quando UM fator métrico
se prova. Se dois qualificam, ela se cala — e a prancha inteira sai pro cliente
como "escala não conferida por cota".

Medido no acervo (join `motor:geometria` × `motor:unidade`, 60 dias):

    a) desenho sem cota nenhuma           97 pranchas · 16 projetos ·      0 cotas
    c) régua VALIDOU                      30 pranchas · 12 projetos ·  4.618 cotas
    b) TEM cota e a régua não usou        27 pranchas · 21 projetos ·  8.370 cotas
    c) régua CORRIGIU                      8 pranchas ·  8 projetos · 15.501 cotas
    d) calou deixando alerta               2 pranchas ·  2 projetos ·    614 cotas

O balde (b) são 8.370 cotas lidas e jogadas fora, em 21 clientes diferentes.

🔍 O empate costuma ser FALSO. A faixa de plausibilidade da MEDIANA vai até
100 m — larga o bastante pra um desenho em centímetro também "qualificar" como
METRO. Medido nos arquivos reais:

    0326.CGR.14.600.PISO (376 cotas, $INSUNITS=cm)
        fator 1,0   → mediana 100,00 m | 218 de 311 cotas acima de 30 m (70,1%)
        fator 0,01  → mediana   1,48 m |   4 de 369 cotas acima de 30 m ( 1,1%)
    0326.CGR.14.700.FORRO (16 cotas)
        fator 1,0   → mediana  82,24 m | 75,0%
        fator 0,01  → mediana   0,82 m |  0,0%

Prancha cuja cota MEDIANA tem 100 metros não existe em edificação.

O desempate usa `correcao_e_absurda` — o MESMO guarda que já governa o ramo
"corrigida" desde 05/08. Não é critério novo; é o critério existente aplicado
de forma consistente.

🪤 O NÍVEL DE PROVA NÃO BAIXOU. "validada" já sai hoje com cota de texto
automático: o AFP-AQ-LO-229 tem ZERO cotas digitadas e valida. O que mudou é a
prancha de 376 cotas parar de ser punida porque um fator IMPOSSÍVEL também
passou pela peneira larga.

🚨 O TESTE QUE MAIS IMPORTA AQUI É O DE RECUSA (`test_implantacao_...`), não o
de aceitação. Uma implantação legítima em METROS tem a mesma forma do empate
falso — e ali a física derrubaria o fator CERTO. O desempate tem que se calar
nesse caso, nunca converter a implantação em centímetros. Foi assim que a
consolidação matou a bitola em 17/08: acertar o caso comum e destruir o raro.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ezdxf  # noqa: E402

from dwg_extractor import (  # noqa: E402
    _detect_unit_factor,
    _validate_unit_factor,
    _validate_unit_by_dimensions,
)

_INSUNITS_M, _INSUNITS_CM, _INSUNITS_MM = 6, 5, 4


def _prancha(insunits, comprimentos):
    """DXF com cotas lineares de texto AUTOMÁTICO ("<>") — o caso real.

    `comprimentos` são unidades de desenho, que é como o CAD guarda.

    🪤 `ezdxf.new(setup=True)` cria o dimstyle padrão com DIMLFAC = 100. Sem o
    override abaixo, uma cota de 60 unidades EXIBE "6000" e o desenho sintético
    passa a medir outra coisa que não a que o teste diz medir. Custou as três
    primeiras rodadas deste arquivo.
    """
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = insunits
    msp = doc.modelspace()
    y = 0.0
    for c in comprimentos:
        msp.add_line((0, y), (c, y))
        msp.add_linear_dim(base=(0, y + max(c * 0.2, 1.0)),
                           p1=(0, y), p2=(c, y), text="<>",
                           override={"dimlfac": 1.0}).render()
        y += max(c * 1.5, 2.0)
    return doc


def _regua(doc):
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "p.dxf")
        doc.saveas(p)
        d = ezdxf.readfile(p)
    uf, _ = _validate_unit_factor(d, _detect_unit_factor(d))
    return uf, _validate_unit_by_dimensions(d, uf)


# ── cotas de 60 a 90 unidades: sob METRO viram 60-90 m (impossível numa
#    prancha de marcenaria); sob CENTÍMETRO viram 0,60-0,90 m (normal).
_MARCENARIA = [60, 65, 70, 75, 80, 85, 90, 62, 78, 88]
# ── cotas de 40 a 120 unidades: sob METRO viram 40-120 m — que é exatamente o
#    que uma IMPLANTAÇÃO tem. A forma é a MESMA do caso acima.
_IMPLANTACAO = [40, 55, 60, 72, 80, 95, 110, 120, 48, 66]


def test_empate_falso_com_cm_agora_valida():
    """O caso que motivou tudo: cm×metro, e o metro é fisicamente impossível."""
    uf, d = _regua(_prancha(_INSUNITS_CM, _MARCENARIA))
    assert abs(uf - 0.01) < 1e-9, "o desenho declara centímetro: %r" % uf
    assert d["status"] == "validada", (
        "a prancha em cm continua sem prova de escala; a régua devolveu %r (%s)"
        % (d.get("status"), d.get("motivo")))
    assert abs(d["fator"] - 0.01) < 1e-9, (
        "validou no fator errado: %r — isto MUDARIA quantidade" % d.get("fator"))
    assert d.get("desempatada_por_fisica"), (
        "validou por outro caminho que não o desempate — o teste não está "
        "medindo o que diz medir")


def test_implantacao_em_metros_NAO_e_convertida_em_centimetros():
    """🚨 O CONTROLE QUE IMPORTA. Mesma forma, conclusão oposta.

    Numa implantação legítima em metros, a física derruba o fator CERTO (cota
    de 40 a 120 m é o normal ali, mas passa de 30 m). O que sobra é o
    centímetro — que está ERRADO. A régua tem que se CALAR, nunca promover o
    sobrevivente só porque ficou sozinho.

    Sem esta trava, a planilha desta prancha sairia 100× menor e com selo de
    'medido' — o erro mais caro que este motor sabe cometer.
    """
    uf, d = _regua(_prancha(_INSUNITS_M, _IMPLANTACAO))
    assert abs(uf - 1.0) < 1e-9, "o desenho declara metro: %r" % uf
    assert d.get("status") != "corrigida", (
        "a régua CORRIGIU uma implantação legítima — erro de 100×")
    if d.get("status") == "validada":
        assert abs(d["fator"] - 1.0) < 1e-9, (
            "validou a implantação no fator %r em vez de metro — a planilha "
            "sairia 100×%s" % (d.get("fator"),
                               " menor" if d.get("fator", 1) < 1 else " maior"))
    else:
        assert d.get("status") == "ambigua", (
            "esperava a régua se calando, veio %r" % d.get("status"))
        assert d.get("motivo"), "calou sem dizer por quê — volta a ser invisível"


def test_candidato_unico_NAO_e_tocado():
    """Regressão: prancha que valida hoje tem que validar igual.

    Trava nº1 do desenho: o desempate só roda quando há EMPATE. Cotas de 1,5 a
    3,0 m em cm não empatam (sob metro dariam mediana de 225 m, fora da faixa).
    """
    uf, d = _regua(_prancha(_INSUNITS_CM, [150, 180, 200, 220, 250, 300]))
    assert d["status"] == "validada", d
    assert abs(d["fator"] - 0.01) < 1e-9, d
    assert not d.get("desempatada_por_fisica"), (
        "o desempate rodou onde não havia empate — a trava nº1 furou")


def test_desenho_sem_cota_DIZ_que_nao_tem_cota():
    """`cotas=-` juntava cinco desfechos. Agora cada um diz o seu nome."""
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = _INSUNITS_CM
    doc.modelspace().add_line((0, 0), (500, 0))
    _, d = _regua(doc)
    assert d.get("status") is None
    assert "cota" in (d.get("motivo") or "").lower(), (
        "não disse por que se calou: %r" % d.get("motivo"))
    assert d.get("cotas_utilizaveis") == 0


def test_controle_positivo_o_guarda_de_fisica_REPROVA_mesmo():
    """Prova que `correcao_e_absurda` separa os dois conjuntos de verdade.

    Sem isto, os testes acima poderiam estar passando por acaso.
    """
    from dwg_extractor import correcao_e_absurda
    # comprimentos REAIS em metros sob cada leitura da mesma prancha
    assert correcao_e_absurda([60.0, 65.0, 70.0, 75.0, 80.0]) is True, (
        "controle positivo furado: cotas de 60-80 m deviam ser absurdas")
    assert correcao_e_absurda([0.60, 0.65, 0.70, 0.75, 0.80]) is False, (
        "controle negativo furado: cotas de 60-80 cm são normais")


def test_ambigua_deixou_de_ser_beco_sem_saida():
    """🪤 Guarda de CALL SITE: prancha com cota ganhava MENOS tentativa.

    `ambigua` ficava de fora da cascata, então uma prancha com 376 cotas não
    recebia as réguas de reserva (DIMLFAC e plausibilidade) que uma prancha SEM
    cota nenhuma recebe. Ler a função não pega isso — só o chamador.
    """
    import io as _io
    _here = os.path.dirname(os.path.abspath(__file__))
    fonte = _io.open(os.path.join(_here, "..", "dwg_extractor.py"),
                     encoding="utf-8").read()
    corpo = chr(10).join(l for l in fonte.split(chr(10))
                         if not l.strip().startswith("#"))
    assert 'dim_check.get("status") in (None, "ambigua")' in corpo, (
        "'ambigua' voltou a ficar fora da cascata das réguas de reserva")
    # 🪤 `_unidade_por_dimlfac` também aparece na DEFINIÇÃO dela, muito antes
    # do chamador — procurar a 1ª ocorrência compara com o lugar errado.
    i_casc = corpo.find('dim_check.get("status") in (None, "ambigua")')
    i_lfac = corpo.find("_unidade_por_dimlfac(doc", i_casc)
    assert i_casc > 0 and i_lfac > i_casc, (
        "a cascata não chega mais no DIMLFAC depois da régua das cotas")


def test_o_log_conta_POR_QUE_a_regua_se_calou():
    """Sem isto, 27 pranchas de 21 clientes seguem sendo mistério no acervo."""
    import io as _io
    _here = os.path.dirname(os.path.abspath(__file__))
    ext = _io.open(os.path.join(_here, "..", "dwg_extractor.py"),
                   encoding="utf-8").read()
    main = _io.open(os.path.join(_here, "..", "main.py"), encoding="utf-8").read()
    ext_corpo = chr(10).join(l for l in ext.split(chr(10))
                             if not l.strip().startswith("#"))
    main_corpo = chr(10).join(l for l in main.split(chr(10))
                              if not l.strip().startswith("#"))
    assert '"regua_cotas_status"' in ext_corpo, (
        "o extrator parou de registrar o desfecho da régua")
    assert '"regua_cotas_motivo"' in ext_corpo
    assert "regua={" in main_corpo and "porque={" in main_corpo, (
        "o motivo é calculado e nunca vira linha de log — continua invisível, "
        "que foi exatamente o problema do `perdidos=0`")
