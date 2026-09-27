# -*- coding: utf-8 -*-
"""O quadro de consumo do Eberick (Formas | Superfície | Volume) é lido por
POSIÇÃO: coluna pelo X da linha de unidades, linha pelo Y.

🩸 26/09/2026 — job 32a27efc (muro de arrimo, 7 DXF do Eberick). O quadro
chegava à IA só pela lista TEXTOS/LEGENDAS — sem posição, sem o "-", ordenado
por repetição e ordem alfabética — e ela casou célula com coluna pela ORDEM:
17 linhas trocadas (o Índice em m³/m² virou volume de pilar, a Superfície
virou fôrma, o Total virou volume de viga).

Tudo aqui é SINTÉTICO: a geometria imita o quadro do Eberick (rótulo bem à
esquerda, unidades logo abaixo do cabeçalho e um pouco à direita, "-"
deslocado em relação aos números); os números são genéricos.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from structural_extractor import (  # noqa: E402
    extract_structural_measurements,
    parse_quadro_consumo,
    structural_prompt_section,
)


class _T:
    """TextAnnotation fake (duck-typed)."""
    def __init__(self, text, x, y, h, layer="TABELAS"):
        self.text = text
        self.position = (x, y)
        self.height = h
        self.layer = layer


class _NS:
    def __init__(self, **kw):
        self.__dict__.update(kw)


# Deslocamentos em relação ao texto "Formas", para altura de texto 3.
X_ROT, X_TOTAL, X_IND = -51.2, -11.3, -32.5
X_CAB = (0.0, 14.5, 34.0)
X_UNID = (3.1, 20.1, 37.4)
X_NUM = (1.8, 18.8, 36.2)
X_TRACO = (6.3, 23.2, 40.6)
PASSO = 5.9

VIGAS = ("Vigas", X_ROT, ("20.00", "8.00", "2.500"))
PILARES = ("Pilares", X_ROT, ("10.00", "-", "0.700"))
TOTAL = ("Total", X_TOTAL, ("-", "8.00", "3.200"))
INDICE = ("Índices (por m2)", X_IND, ("-", "-", "0.256"))      # 3.200 / 12.50
SUP_TOTAL = "Superfície total: 12.50 m2"


def _quadro(linhas=(VIGAS, PILARES, TOTAL, INDICE), x0=0.0, y0=0.0, esc=1.0,
            pav="PAV. TIPO", cab=("Formas", "Superfície", "Volume"), sup_total=SUP_TOTAL,
            x_cab=X_CAB, dy_rot=0.0):
    h = 3.0 * esc
    t = []

    def add(s, dx, dy):
        t.append(_T(s, x0 + dx * esc, y0 + dy * esc, h))

    add(pav, -2.8, 5.3)
    for s, dx in zip(cab, x_cab):
        add(s, dx, 0.0)
    add("Elemento", -35.5, -2.4)
    for s, dx in zip(("(m2)", "(m2)", "(m3)"), X_UNID):
        add(s, dx, -4.5)
    y = -10.2
    for rot, x_rot, cels in linhas:
        add(rot, x_rot, y + dy_rot)
        for k, v in enumerate(cels):
            if v is not None:
                add(v, (X_TRACO if v == "-" else X_NUM)[k], y)
        y -= PASSO
    if sup_total:
        add(sup_total, X_ROT, y)
    return t


def _um(textos):
    qs = parse_quadro_consumo(textos)
    assert len(qs) == 1, qs
    return qs[0]


def _linhas_de_item(txt):
    return [ln for ln in txt.splitlines() if ln.startswith("  [TABELA]") or ln.startswith("  [REFERÊNCIA] pavimento")]


# ─────────────────────────── controle POSITIVO ────────────────────────────
def test_POSITIVO_le_cada_celula_na_sua_coluna_e_as_provas_fecham():
    q = _um(_quadro())
    assert q["pavimento"] == "PAV. TIPO"
    assert q["layer"] == "TABELAS"
    assert q["elementos"] == {
        "Vigas": {"formas": 20.0, "superficie": 8.0, "volume": 2.5},
        "Pilares": {"formas": 10.0, "superficie": "-", "volume": 0.7},
    }
    assert q["total"] == {"formas": "-", "superficie": 8.0, "volume": 3.2}
    assert q["indice"] == 0.256 and q["area_pavimento"] == 12.5
    assert {k: p["ok"] for k, p in q["provas"].items()} == {
        "soma_superficie": True, "soma_volume": True, "indice": True}
    assert q["confiavel"] is True and q["motivos"] == []


def test_a_leitura_nao_depende_da_ORDEM_dos_textos():
    """Prova que lê por posição: embaralhar a lista não muda nada."""
    base = parse_quadro_consumo(_quadro())
    for semente in range(8):
        tx = _quadro()
        random.Random(semente).shuffle(tx)
        assert parse_quadro_consumo(tx) == base, semente
    tx = _quadro()
    tx.reverse()
    assert parse_quadro_consumo(tx) == base


def test_a_tolerancia_e_relativa_a_altura_do_texto():
    """O mesmo quadro desenhado 100× maior (outra unidade) lê igual."""
    q1, q100 = _um(_quadro()), _um(_quadro(esc=100.0))
    assert q100["elementos"] == q1["elementos"] and q100["confiavel"] is True


def test_a_coluna_vem_da_linha_de_unidades_e_nao_do_cabecalho():
    """Cabeçalho escrito mais à esquerda que a coluna (outro alinhamento de
    texto): pelo X do cabeçalho o "-" de Superfície cairia em Volume."""
    q = _um(_quadro(x_cab=(0.0, 11.0, 28.0)))
    assert q["elementos"] == _um(_quadro())["elementos"] and q["confiavel"] is True


def test_rotulo_com_a_base_um_pouco_fora_dos_numeros_e_a_mesma_linha():
    q = _um(_quadro(dy_rot=0.5))
    assert q["elementos"] == _um(_quadro())["elementos"] and q["confiavel"] is True


def test_texto_solto_bem_abaixo_do_quadro_nao_vira_linha():
    """Sem "Superfície total" (o quadro fecha no Total), uma linha de outra
    coisa lá embaixo, na mesma faixa de X, não entra no quadro."""
    tx = _quadro(linhas=(VIGAS, PILARES, TOTAL), sup_total=None)
    y_longe = -10.2 - 12 * PASSO
    tx += [_T("Lajes", X_ROT, y_longe, 3.0), _T("5.00", X_NUM[0], y_longe, 3.0),
           _T("1.000", X_NUM[2], y_longe, 3.0)]
    q = _um(tx)
    assert list(q["elementos"]) == ["Vigas", "Pilares"] and q["confiavel"] is True


def test_duas_celulas_na_mesma_coluna_nao_e_confiavel_mesmo_com_as_provas_fechando():
    tx = _quadro()
    tx.append(_T("9.999", 35.0, -10.2 - PASSO, 3.0))   # texto a mais na coluna Volume de Pilares
    q = _um(tx)
    assert all(p["ok"] for p in q["provas"].values()), "o último da linha é o certo"
    assert q["confiavel"] is False and any("duas células" in m for m in q["motivos"])


def test_dois_quadros_na_mesma_folha_nao_se_misturam():
    """Duas plantas (dois níveis) na mesma folha: um quadro para cada."""
    outro = (("Vigas", X_ROT, ("5.00", "2.00", "0.600")),
             ("Pilares", X_ROT, ("4.00", "-", "0.300")),
             ("Total", X_TOTAL, ("-", "2.00", "0.900")))
    # o de BAIXO vem primeiro na lista: a saída segue a folha (de cima pra baixo)
    tx = _quadro(linhas=outro, y0=-300.0, pav="NIVEL B", sup_total=None) + _quadro(pav="NIVEL A")
    qs = parse_quadro_consumo(tx)
    assert [q["pavimento"] for q in qs] == ["NIVEL A", "NIVEL B"]
    assert qs[1]["elementos"]["Vigas"] == {"formas": 5.0, "superficie": 2.0, "volume": 0.6}
    assert all(q["confiavel"] for q in qs)
    assert "indice" not in qs[1]["provas"], "sem Índice/Superfície total a prova não existe"


# ───────────────────── NEGATIVOS: leitura errada reprova ──────────────────
def test_A_formas_e_superficie_trocadas_reprovam_na_soma_da_superficie():
    q = _um(_quadro(linhas=(("Vigas", X_ROT, ("8.00", "20.00", "2.500")), PILARES, TOTAL, INDICE)))
    assert q["provas"]["soma_superficie"]["ok"] is False and q["confiavel"] is False


def test_B_indice_no_lugar_do_volume_de_pilar_reprova():
    q = _um(_quadro(linhas=(VIGAS, ("Pilares", X_ROT, ("10.00", "-", "0.256")), TOTAL,
                            ("Índices (por m2)", X_IND, ("-", "-", "0.700")))))
    assert q["provas"]["soma_volume"]["ok"] is False
    assert q["provas"]["indice"]["ok"] is False
    assert q["confiavel"] is False


def test_C_forma_no_lugar_do_volume_reprova_na_soma_do_volume():
    q = _um(_quadro(linhas=(("Vigas", X_ROT, ("2.500", "8.00", "20.00")), PILARES, TOTAL, INDICE)))
    assert q["provas"]["soma_volume"]["ok"] is False and q["confiavel"] is False


def test_D_sem_linha_Total_nao_ha_prova_e_nao_e_confiavel():
    q = _um(_quadro(linhas=(VIGAS, PILARES, INDICE)))
    assert "soma_volume" not in q["provas"] and q["confiavel"] is False
    assert any("Total" in m for m in q["motivos"])
    txt = structural_prompt_section({"consumo": [q]})
    assert "[REFERÊNCIA] pavimento 'PAV. TIPO' · Vigas: fôrma 20.00 m² · volume 2.500 m³" in txt
    assert not any(ln.startswith("  [TABELA]") for ln in txt.splitlines())
    assert "SEM prova" in txt


def test_E_ponto_lido_como_milhar_reprova_no_indice():
    q = _um(_quadro(linhas=(("Vigas", X_ROT, ("20.00", "8.00", "2500")),
                            ("Pilares", X_ROT, ("10.00", "-", "700")),
                            ("Total", X_TOTAL, ("-", "8.00", "3200")), INDICE)))
    assert q["provas"]["soma_volume"]["ok"] is True, "a soma não vê a escala"
    assert q["provas"]["indice"]["ok"] is False and q["confiavel"] is False


def test_F_sem_os_tracos_continua_confiavel():
    """Robustez: a coluna vem da posição, não da contagem de células."""
    def sem_traco(ln):
        return (ln[0], ln[1], tuple(None if v == "-" else v for v in ln[2]))
    q = _um(_quadro(linhas=tuple(sem_traco(ln) for ln in (VIGAS, PILARES, TOTAL, INDICE))))
    assert q["confiavel"] is True
    assert q["elementos"]["Pilares"] == {"formas": 10.0, "superficie": None, "volume": 0.7}


def test_G_ler_por_ORDEM_sem_o_traco_como_o_prompt_fazia_reprova():
    """O que a IA fazia: sem o "-", o 1º número vira Formas, o 2º Superfície…"""
    q = _um(_quadro(linhas=(VIGAS,
                            ("Pilares", X_ROT, ("10.00", "0.700", None)),
                            ("Total", X_TOTAL, ("8.00", "3.200", None)),
                            ("Índices (por m2)", X_IND, ("0.256", None, None)))))
    assert q["confiavel"] is False
    assert "soma_volume" not in q["provas"]
    assert q["provas"]["soma_superficie"]["ok"] is False


def test_H_LIMITE_trocar_dois_elementos_na_MESMA_coluna_passa_nas_provas():
    """🪤 Limite documentado: soma não vê permutação. Se o CAD tiver o volume
    de Vigas escrito na linha de Pilares, a leitura segue a POSIÇÃO — e as
    provas não têm como acusar. Só a posição protege aqui."""
    q = _um(_quadro(linhas=(("Vigas", X_ROT, ("20.00", "8.00", "0.700")),
                            ("Pilares", X_ROT, ("10.00", "-", "2.500")), TOTAL, INDICE)))
    assert q["confiavel"] is True
    assert q["elementos"]["Vigas"]["volume"] == 0.7 and q["elementos"]["Pilares"]["volume"] == 2.5


def test_I_cabecalho_sem_Volume_nao_e_quadro():
    assert parse_quadro_consumo(_quadro(cab=("Formas", "Superfície", "Peso"))) == []


def test_negativos_sem_quadro_nada_e_lido():
    assert parse_quadro_consumo([]) == []
    assert parse_quadro_consumo([_T("Formas de madeira", 0, 0, 3), _T("12.00", 10, -6, 3)]) == []
    # cabeçalho fora de ordem (Volume antes de Superfície) é outra tabela: não lê
    for x_cab in (X_CAB, (0.0, 22.0, 34.0)):
        assert parse_quadro_consumo(_quadro(cab=("Formas", "Volume", "Superfície"), x_cab=x_cab)) == []
    # quadro de aço não é quadro de consumo
    aco = [_T("BITOLA (mm)", 0, 100, 5), _T("PESO (kg)", 100, 100, 5),
           _T("Ø 8.0", 0, 90, 5), _T("97,00", 100, 90, 5)]
    assert parse_quadro_consumo(aco) == []
    assert "consumo" not in extract_structural_measurements(_NS(texts=aco))


# ─────────────────────────── o que a IA recebe ────────────────────────────
def test_prompt_uma_linha_por_elemento_com_a_coluna_certa_e_sempre_estimado():
    struct = extract_structural_measurements(_NS(texts=_quadro()))
    assert [q["pavimento"] for q in struct["consumo"]] == ["PAV. TIPO"]
    txt = structural_prompt_section(struct)
    assert "QUADRO DE CONSUMO DO PROJETISTA" in txt
    itens = _linhas_de_item(txt)
    assert itens == [
        "  [TABELA] pavimento 'PAV. TIPO' · Vigas: fôrma 20.00 m² · volume 2.500 m³",
        "  [TABELA] pavimento 'PAV. TIPO' · Pilares: fôrma 10.00 m² · volume 0.700 m³",
    ], itens
    # Superfície (8.00), Total (3.200), Índice (0.256) e área (12.50) não viram item
    for proibido in ("8.00", "3.200", "0.256", "12.50"):
        assert not any(proibido in ln for ln in itens), proibido
    ini = txt.index("QUADRO DE CONSUMO DO PROJETISTA")
    bloco = txt[ini:]
    assert "[MEDIDO]" not in bloco and 'SEMPRE confidence="estimado"' in bloco
    assert "NÃO use como quantidade: a coluna Superfície" in bloco
    assert "'Índices (por m2)'" in bloco and "'Superfície total'" in bloco
    assert "Total (soma das linhas: dupla contagem)" in bloco
    assert "NUNCA some entre pranchas" in bloco
    assert "layer TABELAS" in bloco


def test_prompt_leitura_reprovada_vira_REFERENCIA():
    q = _um(_quadro(linhas=(("Vigas", X_ROT, ("2.500", "8.00", "20.00")), PILARES, TOTAL, INDICE)))
    itens = _linhas_de_item(structural_prompt_section({"consumo": [q]}))
    assert itens and all(ln.startswith("  [REFERÊNCIA] pavimento") for ln in itens), itens


def test_o_quadro_chega_ao_prompt_pelo_extrator_de_DXF(tmp_path):
    """Fluxo real: ezdxf → extract_dxf → to_structured_prompt (altura e
    posição do TEXT preenchidas pelo extrator de produção)."""
    import ezdxf
    from dwg_extractor import extract_dxf

    doc = ezdxf.new("R2018", setup=False)
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()
    for t in _quadro(x0=1000.0, y0=500.0):
        msp.add_text(t.text, dxfattribs={"layer": "TABELAS", "height": t.height,
                                         "insert": t.position})
    p = tmp_path / "quadro_consumo.dxf"
    doc.saveas(str(p))
    prompt = extract_dxf(str(p)).to_structured_prompt()
    assert "QUADRO DE CONSUMO DO PROJETISTA" in prompt
    assert "[TABELA] pavimento 'PAV. TIPO' · Pilares: fôrma 10.00 m² · volume 0.700 m³" in prompt
