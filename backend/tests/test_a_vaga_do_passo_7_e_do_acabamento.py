# -*- coding: utf-8 -*-
"""A vaga do passo 7: só OUTRO ACABAMENTO ocupa — camada não (16/09/2026).

🩸 O passo 7 do `_apply_area_honesty` dá a área medida da prancha pra uma linha
ZERADA de piso/forro. Ele disputava a vaga só entre linhas zeradas: linha COM
número, da mesma prancha e da mesma família, não contava. Então "Piso vinílico
45 m²" (com número) convivia com "Piso porcelanato" recebendo os 102 m² da
prancha inteira — a mesma área falada duas vezes. Medido em 15/09: 4 linhas em
4 jobs de cliente, todas estimadas, todas na planilha entregue.

✅ DECISÃO DO PEDRO (15/09), depois do estudo derrubar o conserto óbvio:
  · CAMADA NÃO OCUPA. Contrapiso, impermeabilização, regularização, pintura de
    forro — com número — continuam convivendo com o acabamento vazio, que segue
    recebendo a área da prancha como estimativa. Camada é a forma MAIS COMUM no
    banco (desde 01/08: piso 16 grupos em 11 jobs, forro 8 em 6). Zerar isso
    apagaria preenchimento legítimo.
  · SÓ OUTRO ACABAMENTO DO MESMO TIPO ocupa (dois pisos de acabamento, dois
    forros). Aí a linha vazia fica EM BRANCO com aviso próprio e verdadeiro.

🪤 O passo da vaga roda DEPOIS do laço (caso S3 do estudo): um número que o
próprio laço zera não pode ocupar vaga nenhuma, senão a prancha fica sem número.

Estes guardas CHAMAM `_apply_area_honesty` e a régua `e_acabamento_de_superficie`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
from engine_rules import e_acabamento_de_superficie  # noqa: E402

_PRANCHA = "ARQ-EXECUTIVO-TERREO.pdf (p1)"


class _Item:
    def __init__(self, desc, qty=0, obs="", ref="", origem="", unit="m²"):
        self.description = desc
        self.unit = unit
        self.quantity = qty
        self.observations = obs
        self.ref_sheet = ref or _PRANCHA
        self.origem = origem
        self.confidence = "estimado"


_OUTRA = "ARQ-PAVIMENTO-TIPO.pdf (p1)"


def _prancha(rooms_m2=102.6):
    """Duas pranchas MEDIDAS: sem a segunda medida, o controle de 'outra
    prancha' passaria pelo motivo errado — a linha seria descartada por não
    casar com prancha nenhuma, e a comparação de chave nem aconteceria
    (medido 16/09: a sabotagem que ignora a prancha sobreviveu por isso)."""
    return {("arq-executivo-terreo.pdf", 0): {
        "arquivo": "ARQ-EXECUTIVO-TERREO.pdf", "pagina": 0,
        "rooms_m2": rooms_m2, "walls_m": 140.0, "scale": 50,
        "escala_validada": True},
        ("arq-pavimento-tipo.pdf", 0): {
        "arquivo": "ARQ-PAVIMENTO-TIPO.pdf", "pagina": 0,
        "rooms_m2": 98.0, "walls_m": 130.0, "scale": 50,
        "escala_validada": True}}


def _rodar(itens, rooms_m2=102.6):
    main._apply_area_honesty(itens, pdfvec_m2=rooms_m2,
                             pdfvec_por_prancha=_prancha(rooms_m2))
    return itens


# ── a régua camada × acabamento ────────────────────────────────────────────
def test_a_regua_separa_camada_de_acabamento():
    for acabamento in ("Piso em porcelanato 60x60", "Piso vinílico em régua",
                       "Forro de gesso acartonado", "Forro mineral removível",
                       "Piso laminado de madeira", "Revestimento de piso cerâmico"):
        assert e_acabamento_de_superficie(acabamento), acabamento
    for camada in ("Contrapiso em argamassa", "Regularização de base para piso",
                   "Impermeabilização de laje", "Pintura do forro em látex",
                   "Massa corrida no teto", "Lastro de concreto magro",
                   "Manta asfáltica sobre laje", "Nivelamento de piso",
                   "Verniz sobre piso de madeira", "Textura no forro",
                   "Selador acrílico em laje", "Emassamento de teto",
                   # 🩸 os quatro que a revisão de 16/09 pegou passando como
                   # acabamento: laje é a BASE, e os nomes de mercado das
                   # camadas não estavam na lista
                   "Laje de cobertura em concreto armado",
                   "Laje pré-moldada treliçada",
                   "Argamassa colante AC-III para assentamento de piso",
                   "Manta acústica sob piso laminado",
                   "Piso tátil direcional em placas"):
        assert not e_acabamento_de_superficie(camada), camada
    # o ato parcial nunca foi acabamento, e continua fora.
    # 🪤 "Rasgo em LAJE" não serve de prova desde que 'laje' virou camada: ele
    # é barrado antes de chegar nessa trava. Estes falam de piso/forro e só
    # saem pela peneira do ato parcial.
    for parcial in ("Demolição de piso cerâmico existente",
                    "Remoção de forro de gesso danificado",
                    "Recorte de piso para shaft hidráulico",
                    "Vão de escada em piso laminado"):
        assert not e_acabamento_de_superficie(parcial), parcial


# ── camada NÃO ocupa: o acabamento vazio continua recebendo ────────────────
def test_CONTROLE_contrapiso_com_numero_nao_tira_a_area_do_piso_vazio():
    contrapiso = _Item("Contrapiso em argamassa desempenada", qty=98.0)
    piso = _Item("Piso em porcelanato 60x60")
    _rodar([contrapiso, piso])
    assert piso.quantity == 102.6, (piso.quantity, piso.observations)
    assert "Área dos ambientes MEDIDOS" in (piso.observations or "")
    assert contrapiso.quantity == 98.0, "camada com número não pode ser mexida"


def test_CONTROLE_pintura_de_forro_com_numero_nao_tira_a_area_do_forro():
    pintura = _Item("Pintura do forro em látex acrílico", qty=80.0)
    forro = _Item("Forro de gesso acartonado")
    _rodar([pintura, forro])
    assert pintura.quantity == 80.0, "o arranjo só prova algo se a camada SOBREVIVER"
    assert forro.quantity == 102.6, (forro.quantity, forro.observations)


def test_CONTROLE_a_laje_e_a_base_e_nao_ocupa_a_vaga_do_piso():
    """🩸 Achado da revisão de 16/09: 'laje' caía como acabamento e a linha de
    laje com número tomava a vaga do piso vazio — camada ocupando, que é
    exatamente o que a decisão do dono proíbe."""
    laje = _Item("Laje de cobertura em concreto armado", qty=120.0)
    piso = _Item("Piso em porcelanato 60x60")
    _rodar([laje, piso])
    assert laje.quantity == 120.0, "o arranjo só prova algo se a laje SOBREVIVER"
    assert piso.quantity == 102.6, (piso.quantity, piso.observations)


def test_CONTROLE_argamassa_colante_e_manta_acustica_tambem_sao_camada():
    """Os nomes que a obra usa de verdade: 'argamassa colante AC-III' e
    'manta acústica' — a 1ª lista só previa 'de assentamento' e 'asfáltica'."""
    for camada in (_Item("Argamassa colante AC-III para assentamento", qty=100.0),
                   _Item("Manta acústica sob piso laminado", qty=95.0)):
        piso = _Item("Piso em porcelanato 60x60")
        _rodar([camada, piso])
        assert piso.quantity == 102.6, (camada.description, piso.observations)


def test_o_aviso_NAO_deixa_de_pe_uma_afirmacao_de_medida_da_IA():
    """🪤 A linha zera, e o texto da IA dizia 'Medido do desenho: 85,00 m²'.
    Zerar deixando a afirmação é o defeito de 14/09 entrando por outra porta."""
    alvo = _Item("Piso em porcelanato 60x60",
                 obs="Medido do desenho com escala 1:50: 85,00 m².")
    _rodar([_Item("Piso vinílico em régua", qty=45.0), alvo])
    assert alvo.quantity == 0, alvo.observations
    assert "Medido do desenho" not in (alvo.observations or ""), alvo.observations
    assert "EM BRANCO de propósito" in (alvo.observations or "")


# ── dois acabamentos: a linha vazia fica em branco COM aviso ───────────────
def test_dois_pisos_de_acabamento_deixam_a_linha_vazia_em_branco():
    vinilico = _Item("Piso vinílico em régua", qty=45.0)
    porcelanato = _Item("Piso em porcelanato 60x60")
    _rodar([vinilico, porcelanato])
    assert porcelanato.quantity == 0, porcelanato.observations
    _o = porcelanato.observations or ""
    assert "EM BRANCO de propósito" in _o, _o
    assert "contar a mesma área duas vezes" in _o, _o
    assert "Piso vinílico" in _o, "o aviso tem que dizer QUEM ocupou a vaga: %r" % _o
    assert vinilico.quantity == 45.0, "a linha que tinha número não se toca"
    assert main._apply_area_honesty.ultimo_p7_desfeitos == 1


def test_dois_forros_tambem():
    mineral = _Item("Forro mineral removível", qty=60.0)
    gesso = _Item("Forro de gesso acartonado")
    _rodar([mineral, gesso])
    assert mineral.quantity == 60.0, "quem ocupa a vaga tem que ter sobrevivido"
    assert gesso.quantity == 0, gesso.observations
    assert "EM BRANCO de propósito" in (gesso.observations or "")


def test_o_aviso_diz_a_area_que_deixou_de_ser_escrita():
    """Sem o número, o aviso vira conversa: o cliente precisa saber o que ele
    teria recebido pra decidir se preenche."""
    _rodar([_Item("Piso vinílico em régua", qty=45.0),
            (_alvo := _Item("Piso em porcelanato 60x60"))])
    assert "102.60 m²" in (_alvo.observations or ""), _alvo.observations


# ── família e prancha continuam separando ──────────────────────────────────
def test_CONTROLE_forro_com_numero_nao_ocupa_a_vaga_do_piso():
    forro = _Item("Forro de gesso acartonado", qty=60.0)
    piso = _Item("Piso em porcelanato 60x60")
    _rodar([forro, piso])
    assert forro.quantity == 60.0, "o arranjo só prova algo se o forro SOBREVIVER"
    assert piso.quantity == 102.6, (piso.quantity, piso.observations)


def test_CONTROLE_acabamento_de_OUTRA_prancha_nao_ocupa_a_vaga():
    outro = _Item("Piso vinílico em régua", qty=45.0, ref=_OUTRA)
    piso = _Item("Piso em porcelanato 60x60")
    _rodar([outro, piso])
    assert outro.quantity == 45.0, (
        "o arranjo não serve se a linha de fora for zerada: ela precisa "
        "SOBREVIVER pra poder (não) ocupar a vaga — %r" % outro.observations)
    assert piso.quantity == 102.6, (piso.quantity, piso.observations)


def test_CONTROLE_linha_sem_prancha_declarada_nao_acusa():
    """Trava 3: sem saber de qual prancha veio, não se atribui nem se acusa."""
    sem_ref = _Item("Piso vinílico em régua", qty=45.0, ref=" ")
    piso = _Item("Piso em porcelanato 60x60")
    _rodar([sem_ref, piso])
    assert sem_ref.quantity == 45.0, "o arranjo só prova algo se ela SOBREVIVER"
    assert piso.quantity == 102.6, (piso.quantity, piso.observations)


def test_CONTROLE_ocupante_em_outra_unidade_nao_ocupa():
    """Rodapé em metro não disputa vaga de área — unidade fora de m² fica fora."""
    rodape = _Item("Rodapé em porcelanato", qty=48.0, unit="ml")
    piso = _Item("Piso em porcelanato 60x60")
    _rodar([rodape, piso])
    assert piso.quantity == 102.6, (piso.quantity, piso.observations)


# ── o caso S3 do estudo ────────────────────────────────────────────────────
def test_S3_numero_que_o_proprio_laco_zera_NAO_ocupa_a_vaga():
    """🪤 Um piso com 5.000 m² numa prancha de 102,6 m² é zerado pelo próprio
    laço. Se ele ocupasse a vaga, a prancha inteira ficaria sem número nenhum —
    o motor teria medido e não entregado nada."""
    implausivel = _Item("Piso vinílico em régua", qty=5000.0)
    porcelanato = _Item("Piso em porcelanato 60x60")
    _rodar([implausivel, porcelanato])
    assert implausivel.quantity == 0, "o laço tinha que zerar este"
    assert porcelanato.quantity == 102.6, (
        "a vaga estava livre: quem a ocuparia foi zerado no mesmo laço — %r"
        % porcelanato.observations)


def test_CONTROLE_sem_o_passo_7_nada_disso_acontece():
    """Sem medição por prancha não há passo 7, e ninguém desfaz nada."""
    piso = _Item("Piso em porcelanato 60x60")
    main._apply_area_honesty([_Item("Piso vinílico em régua", qty=45.0), piso])
    assert piso.quantity == 0
    assert main._apply_area_honesty.ultimo_p7_desfeitos == 0


def test_a_telemetria_conta_os_desfeitos():
    _rodar([_Item("Piso vinílico em régua", qty=45.0),
            _Item("Piso em porcelanato 60x60"),
            _Item("Forro mineral removível", qty=60.0),
            _Item("Forro de gesso acartonado")])
    assert main._apply_area_honesty.ultimo_p7_desfeitos == 2
    assert main._apply_area_honesty.ultimo_criados_prancha == 0
