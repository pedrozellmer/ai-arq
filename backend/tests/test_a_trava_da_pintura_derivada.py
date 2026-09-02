# -*- coding: utf-8 -*-
"""A pintura derivada somava CEGO e daria 58× o imóvel.

🩸 02/09/2026. `_derive_pintura_pe_direito` fecha a pintura de parede quando só
temos o COMPRIMENTO: área = Σ(comprimento) × pé-direito × 2 faces. A soma pegava
tudo que tinha unidade de metro e a palavra parede/alvenaria/drywall.

Medido no acervo, com a área do imóvel ao lado:

    razão pintura/área .... 0,6× … 7,6×   (17 projetos, o normal)
    job 43b26b58 .......... 58×    (1.324 m² de imóvel → 77.153 m² de pintura)
    job b82a72ed .......... 155×   (474 m² de imóvel → 13.134 m de parede)

Entre 7,6 e 58 não existe NADA na base. Os dois de cima não são "alto", são
impossíveis — e os quatro defeitos que os produzem estão escritos no próprio
item:

  1. ACESSÓRIO com a palavra: "Batente/marco para parede drywall" (30 ml) e
     "Perfis de drywall — montantes/guias" (22,4 ml) entravam na soma.
  2. O ITEM CONTRADIZ A PRÓPRIA FONTE: gravou 12.496,67 ml e a observação dele,
     na mesma linha, diz "layer A-WALL = 975,53 m" — 12,8× o que ele declara.
  3. DUAS FACES EM DOBRO: a observação avisa "pode incluir ambas as faces
     (duplicidade)" e a conta multiplicava por 2 outra vez.
  4. O MESMO LAYER DUAS VEZES: em b82a72ed dois itens medem o layer A-WALL,
     um diz 8.626 m e o outro 2.275 m. Cada um coerente consigo; juntos, a
     mesma parede contada duas vezes.

🔑 A trava RECUSA, não corrige. Comprimento que mente sobre si mesmo não vira
número melhor sendo ajustado — vira chute com cara de conta (regra dura nº1).

🪤 O ERRO QUE ESTE ARQUIVO QUASE DEIXOU PASSAR: a 1ª versão da lista de
acessórios procurava a palavra no texto INTEIRO. "Parede drywall tipo DRY 01 —
espessura 82,5 mm, **montante** 70 mm" é parede de verdade, e teria sido
descartada em silêncio — 12.496 m sumindo sem aviso. A palavra tem que estar no
NOME do item, antes do travessão. Ver [[feedback_procurei_a_palavra_nao_o_comportamento]].
"""
import os
import re
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main                                            # noqa: E402
from _corpo import corpo_de, fonte                     # noqa: E402


def _so_codigo(nome):
    """O que EXECUTA — sem comentário e sem docstring NENHUMA, nem as internas.

    🪤 `so_o_que_roda` tira só a docstring de fora. As helpers aninhadas têm as
    suas, e é justamente nelas que esta casa escreve a frase que está
    proibindo — pra explicar por que ela saiu. Guarda que lê a própria
    documentação acusa a explicação e me empurra a apagá-la pra calar o
    alarme. Já aconteceu três vezes aqui; a primeira versão deste arquivo foi
    a terceira.
    """
    corpo = re.sub(r'""".*?"""', "", corpo_de(nome), flags=re.S)
    return "\n".join(l for l in corpo.splitlines()
                     if not l.strip().startswith("#"))


class _It:
    def __init__(self, desc, unit, qty, obs=""):
        self.description, self.unit, self.quantity = desc, unit, qty
        self.observations, self.ref_sheet = obs, "planta.dxf"
        self.origem, self.confidence = "", "estimado"


def _alvo():
    """A linha de pintura de parede zerada que a derivação preenche."""
    return _It("Pintura látex em paredes internas", "m²", 0,
               "Requer pé-direito para fechar a área.")


def _derivar(itens, pd=2.8, area=0.0):
    alvo = _alvo()
    lista = list(itens) + [alvo]
    n = main._derive_pintura_pe_direito(lista, pd, area)
    return n, alvo, getattr(main._derive_pintura_pe_direito, "ultimo_motivo", "")


# ── Defeito 2: o item mente sobre si mesmo ─────────────────────────────────
def test_o_caso_REAL_da_thamiry_e_RECUSADO():
    """🩸 job 43b26b58. Sem a trava: 77.153 m² num imóvel de 1.324."""
    n, alvo, motivo = _derivar([
        _It("Parede drywall tipo DRY 01 — espessura total 82,5 mm, montante "
            "70 mm, espaçamento 400 mm, chapa simples ST 12,5 mm", "ml", 12496.67,
            "Fonte: comprimento total do layer A-WALL = 975,53 m. ATENÇÃO: "
            "este valor representa o comprimento LINEAR total de TODAS as "
            "paredes drywall do pavimento mezanino."),
    ], pd=2.8, area=1324.0)
    assert n == 0, "derivou em cima de um item que contradiz a própria fonte"
    assert alvo.quantity == 0, "escreveu %r na planilha do cliente" % alvo.quantity
    assert "declara fonte" in motivo, motivo


def test_CONTROLE_POSITIVO_sem_a_contradicao_a_derivacao_ACONTECE():
    """🧪 Se este teste parar de derivar, a trava virou "recusa sempre" — que
    é tão inútil quanto somar cego, só que na direção covarde."""
    n, alvo, motivo = _derivar([
        _It("Parede drywall tipo DRY 01 — espessura total 82,5 mm, montante "
            "70 mm, espaçamento 400 mm", "ml", 975.53,
            "Fonte: comprimento total do layer A-WALL = 975,53 m."),
    ], pd=2.8, area=1324.0)
    assert n == 1, "recusou o caso BOM (motivo: %s)" % motivo
    assert alvo.quantity == round(975.53 * 2.8 * 2, 1), alvo.quantity
    assert motivo == "", motivo


def test_a_margem_de_15pct_nao_reprova_arredondamento():
    """Declarar 100 m e gravar 110 é arredondamento/rateio, não invenção."""
    n, _, motivo = _derivar([
        _It("Parede de alvenaria", "ml", 110.0,
            "Fonte: comprimento do layer ALV = 100,00 m."),
    ], pd=2.8, area=500.0)
    assert n == 1, motivo


# ── Defeito 1: acessório não é parede ──────────────────────────────────────
def test_acessorio_com_a_palavra_parede_NAO_entra_na_soma():
    n, alvo, _ = _derivar([
        _It("Parede de alvenaria — bloco cerâmico", "ml", 100.0),
        _It("Batente/marco para parede drywall — perfil metálico", "ml", 30.0),
        _It("Perfis de drywall — montantes/guias (layer A-DETL-MEDM)", "ml", 22.4),
        _It("Guia (trilho) de aço galvanizado 70mm para paredes drywall", "ml", 40.0),
    ], pd=3.0, area=500.0)
    assert n == 1
    assert alvo.quantity == round(100.0 * 3.0 * 2, 1), (
        "acessório entrou na soma: esperava 600.0, veio %r" % alvo.quantity)


def test_CONTROLE_parede_de_verdade_com_montante_na_ESPECIFICACAO_ENTRA():
    """🪤 O erro que a 1ª versão desta trava cometeu. A palavra "montante"
    aparece na especificação de uma parede REAL. Procurar no texto inteiro
    descartava 12.496 m de parede em silêncio."""
    n, alvo, motivo = _derivar([
        _It("Parede drywall tipo DRY 01 — espessura total 82,5 mm, montante "
            "70 mm, espaçamento 400 mm, chapa ST 12,5 mm em ambas as faces",
            "ml", 200.0),
    ], pd=3.0, area=500.0)
    assert n == 1, "recusou tudo (motivo: %s)" % motivo
    assert alvo.quantity > 0, (
        "a parede real foi descartada porque a ESPECIFICAÇÃO dela cita "
        "'montante' — guarda que joga fora medição calado")


# ── Defeito 4: o mesmo layer duas vezes ────────────────────────────────────
def test_o_caso_REAL_do_b82a72ed_e_RECUSADO():
    """🩸 Dois itens medem o layer A-WALL: 8.626 m e 2.275 m. 155× o imóvel."""
    n, alvo, motivo = _derivar([
        _It("Alvenaria estrutural em blocos cerâmicos 14x19x29cm", "ml", 8626.04,
            "Fonte: comprimento total do layer A-WALL = 8626.04 m"),
        _It("Divisória em drywall com chapa standard", "ml", 2275.27,
            "Fonte: comprimento do layer 'A-WALL' = 2275.27 m"),
    ], pd=2.8, area=474.0)
    assert n == 0, "somou a mesma parede duas vezes"
    assert alvo.quantity == 0
    assert "dois itens" in motivo, motivo


def test_CONTROLE_layers_DIFERENTES_somam_normalmente():
    """🧪 Duas paredes de layers distintos é o caso legítimo — e é o do
    Flávio (ALVENARIA + ALVV). Recusar aqui mataria a feature."""
    n, alvo, motivo = _derivar([
        _It("Alvenaria de vedação", "ml", 255.06,
            "Fonte: comprimento do layer ALVENARIA = 255,06 m"),
        _It("Alvenaria de vedação fina", "ml", 15.48,
            "Fonte: comprimento do layer ALVV = 15,48 m"),
    ], pd=3.0, area=188.0)
    assert n == 1, "recusou dois layers diferentes (motivo: %s)" % motivo
    assert alvo.quantity == round((255.06 + 15.48) * 3.0 * 2, 1), alvo.quantity


# ── Defeito 3: as duas faces em dobro ──────────────────────────────────────
def test_quando_o_layer_JA_traz_as_duas_faces_nao_dobra():
    n, alvo, _ = _derivar([
        _It("Comprimento total de paredes drywall — layer A-WALL", "ml", 300.0,
            "ATENÇÃO: este valor representa a soma de TODAS as linhas do layer "
            "A-WALL, que pode incluir ambas as faces das paredes (duplicidade)."),
    ], pd=3.0, area=500.0)
    assert n == 1
    assert alvo.quantity == round(300.0 * 3.0, 1), (
        "dobrou faces que o próprio layer já contava: %r" % alvo.quantity)
    assert "já traz as 2 faces" in alvo.observations, alvo.observations


def test_CONTROLE_sem_o_aviso_de_duplicidade_dobra_normalmente():
    n, alvo, _ = _derivar([
        _It("Parede de alvenaria", "ml", 300.0, "Fonte: layer ALV."),
    ], pd=3.0, area=500.0)
    assert alvo.quantity == round(300.0 * 3.0 * 2, 1), alvo.quantity
    assert "× 2 faces" in alvo.observations


# ── O teto de sanidade ─────────────────────────────────────────────────────
def test_o_teto_recusa_o_impossivel():
    """900 m de parede num imóvel de 50 m² = 108×. Não existe."""
    n, alvo, motivo = _derivar([
        _It("Parede de alvenaria", "ml", 900.0),
    ], pd=3.0, area=50.0)
    assert n == 0 and alvo.quantity == 0
    assert "imovel" in motivo, motivo


def test_CONTROLE_o_maior_caso_REAL_da_base_passa_no_teto():
    """🧪 7,6× é o topo medido em 19 projetos reais (job d5e073cf). Se o teto
    reprovar aqui, ele está calibrado contra a realidade e vai calar projeto
    legítimo — que é o defeito que a gente está consertando, ao contrário."""
    n, _, motivo = _derivar([
        _It("Parede de alvenaria", "ml", 255.0,
            "Fonte: comprimento do layer ALVENARIA = 255,0 m"),
    ], pd=2.8, area=188.0)
    assert n == 1, "o teto reprovou o maior caso REAL da base: %s" % motivo


def test_sem_area_conhecida_o_teto_nao_opina():
    """Sem área não há contra o que comparar — e inventar comparação é pior."""
    n, _, motivo = _derivar([_It("Parede de alvenaria", "ml", 900.0)],
                            pd=3.0, area=0.0)
    assert n == 1, motivo


# ── O motivo tem que chegar ────────────────────────────────────────────────
def test_toda_recusa_deixa_MOTIVO():
    """🚨 Trava que recusa em silêncio é indistinguível de trava que não
    existe. Foi assim que a feature passou 33 dias com 0 derivados sem
    ninguém saber se era falta de uso ou defeito."""
    for itens, area in (
            ([_It("Parede de alvenaria", "ml", 900.0)], 50.0),
            ([_It("Parede X", "ml", 500.0, "Fonte: layer A = 10,00 m")], 0.0),
            ([], 100.0)):
        _, _, motivo = _derivar(itens, pd=3.0, area=area)
        assert motivo, "recusou calado com %r" % (itens,)


def test_o_chamador_REGISTRA_o_motivo_no_log():
    src = fonte("main.py")
    assert "motivo={getattr(_derive_pintura_pe_direito, 'ultimo_motivo', '')!r}" in src, (
        "o log do motor voltou a registrar só a contagem — 'derivados=0' sem "
        "motivo não diz se foi falta de parede ou recusa da trava")


# ── Guardas de forma ───────────────────────────────────────────────────────
def test_os_DOIS_chamadores_passam_a_area():
    """🪤 Sem a área o teto de sanidade nunca opina — guarda que sempre passa
    é pior que guarda nenhum."""
    src = fonte("main.py")
    assert "_derive_pintura_pe_direito(all_items, _pd_inf," in src, (
        "o fluxo do motor voltou a chamar sem a área")
    assert "_derive_pintura_pe_direito(items, _pd_efetivo," in src, (
        "a rota /inform-area voltou a chamar sem a área")


def test_a_funcao_NAO_usa_re_solto():
    """🚨 O topo do main.py NÃO importa `re`, só apelidos. `re.` direto passa
    no editor e mata a partida — foi o deploy 8d597a6."""
    corpo = _so_codigo("_derive_pintura_pe_direito")
    assert not re.search(r"(?<![_\w.])re\.", corpo), (
        "voltou a usar `re.` solto numa função de um módulo que não importa `re`")
    assert "import re as" in corpo, "o import local sumiu"


def test_CONTROLE_o_guarda_do_re_REPROVA_de_verdade():
    """🧪 Um guarda que lê texto tem que provar que enxerga o defeito. Se a
    regex não pegar isto, ela não pegaria o `re.sub` que matou o deploy."""
    assert re.search(r"(?<![_\w.])re\.", "x = re.sub(a, b)")
    assert not re.search(r"(?<![_\w.])re\.", "x = _re_pd.sub(a, b)")


def test_a_trava_nao_cria_global_novo():
    """🪤 Três arquivos de teste executam uma FATIA do main.py. Nome de módulo
    que a fatia não contém quebra os três (aprendido em 01/09)."""
    corpo = corpo_de("_derive_pintura_pe_direito")
    for nome in ("_NAO_E_PAREDE", "_FACES_JA_INCLUSAS"):
        assert ("    %s = (" % nome) in corpo, (
            "%s saiu de dentro da função e virou global de módulo" % nome)
