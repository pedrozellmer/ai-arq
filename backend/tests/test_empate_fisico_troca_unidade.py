# -*- coding: utf-8 -*-
"""DWG em CENTÍMETRO que declara METRO: a física já escolheu, a trava calava.

🩸 09/11/2026. 3 jobs de 2 clientes saíram com 0 linha medida (parede de 2,5
milhões de m). As cotas automáticas ("<>") qualificam metro E cm; a física
(`correcao_e_absurda`) derruba o metro — medido nos arquivos reais:

    job A (casa):   187 cotas | metro: mediana 80 m, 65% > 30 m | cm: 0,90 m, 0%
    job B (escola): 2.360     | metro: mediana 70 m, 69% > 30 m | cm: 0,79 m, 0%
    desenho no declarado: 8.950 m e 4.857 m

e a trava 2 do empate (26/08) só CONFIRMA o detectado. `_unidade_pelo_empate_fisico`
troca, como PLAUSIBILIDADE (nada sai 'confirmado'), e só com a chave
EMPATE_FISICO_TROCA_UNIDADE=1. Com 0 o motor só registra (`empate_fisico`).

🚨 O controle que importa é a IMPLANTAÇÃO em metro de verdade: a mesma forma
(cotas de 40–120 m, a física derruba o metro, sobra o cm). Ela NÃO pode virar
centímetro — é o erro de 100×.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ezdxf  # noqa: E402

import dwg_extractor as dx  # noqa: E402

_INSUNITS_M = 6
_CHAVE = "EMPATE_FISICO_TROCA_UNIDADE"
_AVISO_9KM = ("Unidade suspeita: maior elemento mede 8950m (>500m) — escala pode "
              "estar errada; tratar quantidades como estimado.")


def _cotas(**kw):
    """O que a régua das cotas devolveu no job A (casa), com ajustes."""
    base = {"status": "ambigua", "detectado": 1.0, "fisicos": [0.01],
            "medianas_m": {1.0: 80.0, 0.01: 0.90}, "cotas_utilizaveis": 187,
            "motivo": "empate entre os fatores 1, 0.01 (187 cotas utilizáveis, "
                      "0 com número digitado)"}
    base.update(kw)
    return base


# ── a função sozinha ──────────────────────────────────────────────────────────

def test_o_caso_real_troca_pra_centimetro():
    r = dx._unidade_pelo_empate_fisico(_cotas(), 1.0, [_AVISO_9KM])
    assert r.get("status") == "corrigida_plausibilidade", r
    assert abs(r["fator_corrigido"] - 0.01) < 1e-12, r
    m = r["mensagem"]
    assert "NÃO é prova" in m and "estimado" in m, m
    # número em português, que é o que o cliente lê
    assert "8.950 m" in m and "0,90 m" in m, m


@pytest.mark.parametrize("ajuste, motivo", [
    ({"status": "validada"}, "não empatou"),
    ({"status": None}, "não empatou"),
    ({"fisicos": [1.0, 0.01]}, "dois físicos (um é o detectado)"),
    # 🧬 o mutante `len(fis) < 1` sobrevivia: com [1.0, 0.01] o 1º é o detectado
    # e a outra trava recusa por acaso. Dois físicos MENORES isolam a trava.
    ({"fisicos": [0.01, 0.001], "medianas_m": {1.0: 80.0, 0.01: 0.90, 0.001: 0.09}},
     "dois físicos menores"),
    ({"fisicos": []}, "nenhum físico"),
    ({"fisicos": [1.0]}, "o físico é o próprio detectado"),
    ({"detectado": 0.01, "fisicos": [1.0], "medianas_m": {1.0: 2.0, 0.01: 80.0}},
     "o que sobra AUMENTA o desenho"),
    ({"medianas_m": {1.0: 80.0, 0.01: 0.20}}, "cota do meio pequena demais sob cm"),
    ({"medianas_m": {1.0: 80.0, 0.01: 20.0}}, "cota do meio grande demais sob cm"),
    ({"medianas_m": {1.0: 25.0, 0.01: 0.90}}, "no declarado a cota do meio cabe"),
    ({"detectado": 0.001}, "o detectado não é o fator em uso"),
])
def test_recusa(ajuste, motivo):
    r = dx._unidade_pelo_empate_fisico(_cotas(**ajuste), 1.0, [_AVISO_9KM])
    assert r.get("status") is None, "trocou com %s: %r" % (motivo, r)
    assert r.get("motivo"), "recusou sem dizer por quê"


@pytest.mark.parametrize("avisos, motivo", [
    ([], "sem o aviso de extensão"),
    (["Unidade suspeita: maior elemento mede 1200m (>500m) — escala pode estar "
      "errada; tratar quantidades como estimado."], "terreno de 1,2 km — implantação"),
    (["Unidade suspeita: maior elemento mede 90000m (>500m) — escala pode estar "
      "errada; tratar quantidades como estimado."], "sob cm ainda mede 900 m"),
    (["Unidade suspeita: maior elemento mede 3mm (<5cm) — escala pode estar errada"],
     "o aviso é do lado PEQUENO"),
])
def test_recusa_pela_extensao(avisos, motivo):
    r = dx._unidade_pelo_empate_fisico(_cotas(), 1.0, avisos)
    assert r.get("status") is None, "trocou com %s: %r" % (motivo, r)


def test_nunca_lanca():
    assert dx._unidade_pelo_empate_fisico(None, 1.0, None).get("status") is None
    assert dx._unidade_pelo_empate_fisico(
        _cotas(medianas_m="lixo"), 1.0, [_AVISO_9KM]).get("status") is None


# ── a extração inteira (a régua das cotas → a cascata → o metadata) ───────────

def _prancha_m(cotas, maior):
    """Declara METRO; cotas automáticas de `cotas` unidades e uma linha de
    `maior` unidades (o "maior elemento" da heurística de extensão)."""
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = _INSUNITS_M
    msp = doc.modelspace()
    y = 0.0
    for c in cotas:
        msp.add_line((0, y), (c, y))
        # 🪤 o dimstyle padrão do setup=True tem DIMLFAC=100 (ver
        # test_regua_desempate_por_fisica): sem o override a cota mede outra coisa
        msp.add_linear_dim(base=(0, y + max(c * 0.2, 1.0)), p1=(0, y), p2=(c, y),
                           text="<>", override={"dimlfac": 1.0}).render()
        y += max(c * 1.5, 2.0)
    msp.add_line((0, -10), (maior, -10))
    return doc


def _extrair(doc):
    d = tempfile.mkdtemp(prefix="_empfis_")
    p = os.path.join(d, "p.dxf")
    doc.saveas(p)
    return dx.extract_dxf(p)


# portas e vãos em cm: 0,60–0,90 m sob cm, 60–90 m sob metro
_PORTAS_CM = [60, 65, 70, 75, 80, 85, 90, 62, 78, 88]
# implantação em metro: 40–120 m (a mesma forma — ver o docstring)
_IMPLANTACAO_M = [40, 55, 60, 72, 80, 95, 110, 120, 48, 66]


def test_chave_em_0_so_registra(monkeypatch):
    monkeypatch.setenv(_CHAVE, "0")
    r = _extrair(_prancha_m(_PORTAS_CM, 3000))
    md = r.metadata
    assert abs(float(md["fator_para_metros"]) - 1.0) < 1e-12, "mudou com a chave em 0"
    assert md.get("empate_fisico") == "fator=0.01 liga=0", md.get("empate_fisico")
    assert md.get("escala_ambigua"), "a ressalva de antes sumiu com a chave em 0"
    assert "PLAUSIBILIDADE (cotas)" not in str(md.get("alerta_unidade"))
    assert "empate_fisico" not in r.to_structured_prompt(), (
        "registro do log foi pro prompt (ver _METADADOS_FORA_DO_PROMPT)")


def test_chave_ausente_e_desligada(monkeypatch):
    monkeypatch.delenv(_CHAVE, raising=False)
    r = _extrair(_prancha_m(_PORTAS_CM, 3000))
    assert abs(float(r.metadata["fator_para_metros"]) - 1.0) < 1e-12, (
        "a regra nasceu LIGADA — sem a chave tem de ficar como era")


def test_chave_em_1_troca_como_plausibilidade(monkeypatch):
    monkeypatch.setenv(_CHAVE, "1")
    r = _extrair(_prancha_m(_PORTAS_CM, 3000))
    md = r.metadata
    assert abs(float(md["fator_para_metros"]) - 0.01) < 1e-12, md.get("fator_para_metros")
    assert md.get("empate_fisico") == "fator=0.01 liga=1"
    assert "PLAUSIBILIDADE (cotas)" in str(md.get("alerta_unidade")), (
        "trocou sem a ressalva — sairia 'confirmado' sem prova")
    assert str(md.get("regua_cotas_antes", "")).startswith("ambigua|"), (
        "o log perdeu o que as cotas disseram")
    assert "empate_fisico" not in r.to_structured_prompt()


def test_implantacao_em_metro_NAO_vira_centimetro(monkeypatch):
    """🚨 O CONTROLE. Terreno de 1,5 km em metro, cotas de 40–120 m."""
    monkeypatch.setenv(_CHAVE, "1")
    r = _extrair(_prancha_m(_IMPLANTACAO_M, 1500))
    md = r.metadata
    assert abs(float(md["fator_para_metros"]) - 1.0) < 1e-12, (
        "a implantação em metro virou %r — erro de 100×" % md.get("fator_para_metros"))
    assert not md.get("empate_fisico"), md.get("empate_fisico")


def test_o_aviso_de_extensao_ainda_tem_a_forma_que_a_regra_le():
    """A regra lê o "maior elemento" no texto do aviso. Se o texto mudar, este
    teste cai — em vez de a regra se calar sem ninguém ver."""
    doc = _prancha_m(_PORTAS_CM, 3000)
    _, avisos = dx._validate_unit_factor(doc, 1.0)
    achados = [dx._RE_MAIOR_ELEMENTO_GRANDE.search(a) for a in avisos]
    assert any(achados), avisos
    assert float(next(a for a in achados if a).group(1)) >= 3000


def test_a_chave_e_avaliavel_e_o_log_mostra():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "main.py"), encoding="utf-8").read()
    ini = src.index("_CHAVES_AVALIAVEIS = frozenset({")
    assert '"EMPATE_FISICO_TROCA_UNIDADE"' in src[ini:src.index("})", ini)], (
        "sem a chave em _CHAVES_AVALIAVEIS a avaliação não consegue ligar só pra si")
    assert "empate_fisico={_md_u.get('empate_fisico')" in src, (
        "o log motor:unidade não mostra a régua — com a chave em 0 fica invisível")
