# -*- coding: utf-8 -*-
"""REGRA DURA Nº1: o selo "✓ MEDIDO do CAD" exige procedência de GEOMETRIA.

🚨 24/08/2026. Medido no acervo de produção: **61 itens, em 19 projetos de 15
clientes**, foram entregues com `confirmado` (branco na planilha, "✓ MEDIDO do
CAD") tendo como única procedência um TEXTO lido da prancha. 23 deles em m²,
somando **33.962 m²** apresentados como medidos.

A rede que existia (`selos_sem_medida`) só pegava `confirmado` com quantidade
ZERO. Para `confirmado` com um número vindo de texto não havia rede nenhuma.

🪤 Esta regra decide olhando TEXTO — e a lição do dia anterior foi justamente
"texto não é prova". A diferença é a DIREÇÃO: ela só REBAIXA, nunca promove.
Errar pro lado de "estimado" custa uma revisão a mais ao cliente; errar pro lado
de "medido" põe um número sem lastro na planilha usando o selo que o produto
reserva pra confiança. Na dúvida, rebaixa.

Todos os casos abaixo são observações REAIS, copiadas de itens que já foram
entregues a clientes.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 🪤 Janela de tamanho fixo mede o vizinho (ou um pedaço) e passa
# verde por engano — a auditoria de 25/08 achou 17 assim. O recorte
# certo mora num lugar só.
from _corpo import corpo_de  # noqa: E402
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from engine_rules import selos_sem_geometria  # noqa: E402


def _it(obs, conf="confirmado", q=10.0, origem="", desc="Item", unit="m²"):
    return {"description": desc, "unit": unit, "quantity": q,
            "confidence": conf, "observations": obs, "origem": origem}


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLE POSITIVO — casos REAIS que estavam com selo de medido
# ══════════════════════════════════════════════════════════════════════════
REAIS_QUE_DEVEM_CAIR = [
    "Fonte: texto layer 'ARQ-TEXTO 1': 'AREA TOTAL CLINICA = 264,54 m²'. "
    "Inclui todas as áreas internas.",
    "Conforme legenda código 04 da primeira tabela — área aproximada explícita",
    "Fonte: texto layer 'txt' — 'A = 48.00 m²'. Identificado como Sala de Aula 02.",
    "Fonte: texto na legenda 'TOTAL DE CADEIRAS NEWNET 16003 EXISTENTES = 151 UNIDADES'",
    "Fonte: texto '30.995,80 m²' explícito no layer 'INC_LIN02' e 'FOLHA'. "
    "Área total construída conforme carimbo do projeto.",
    "LM1 conforme legenda de luminárias",
    "Conforme legenda código 01 — quantidade explícita na tabela",
]


def test_texto_com_selo_de_medido_e_rebaixado():
    itens = [_it(o) for o in REAIS_QUE_DEVEM_CAIR]
    ach = selos_sem_geometria(itens)
    faltaram = [REAIS_QUE_DEVEM_CAIR[i] for i in range(len(itens))
                if i not in {a["indice"] for a in ach}]
    assert not faltaram, (
        "estes já foram entregues como '✓ MEDIDO do CAD' e continuariam:\n  "
        + "\n  ".join(f[:100] for f in faltaram))


def test_o_pior_caso_real_e_pego():
    """O total do PRÉDIO colado numa linha de acabamento de piso, com selo de
    medido. Errado no número e errado no selo."""
    it = _it("Fonte: texto layer 'ARQ-TEXTO 1': 'AREA TOTAL CLINICA = 264,54 m²'.",
             q=264.54, desc="Piso — revestimento de piso interno")
    assert selos_sem_geometria([it])


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLE NEGATIVO — medição de verdade não pode ser rebaixada
# ══════════════════════════════════════════════════════════════════════════
REAIS_QUE_DEVEM_FICAR = [
    "Fonte: 84 INSERTs do bloco '_VAONER025250652500550005500' (CONTAGEM DE BLOCOS).",
    "Fonte: 2 INSERTs do bloco 'LOUÇA - bacia deca unic planta'.",
    "Fonte: comprimento do layer 'ARQ-DEMOLIR' = 93.85 m. Textos no layer indicam: "
    "WC 02, WC 04, PM-01.",
    "Fonte: comprimento total do layer 'PVC' = 75,73 m. Textos associados: Ø100, Ø150.",
    "Fonte: área hachurada do layer 'ARQ-DET-GENF' = 12,33 m² (soma de 12 hachuras).",
    "Fonte: comprimento total do layer ARQ-SOCULO = 409,13 m. Texto 'SÓCULO DE "
    "ALVENARIA' aparece 6× na prancha (layer ARQ-TXT-1_100).",
]


def test_medicao_de_verdade_nao_e_tocada():
    """🪤 Os três últimos citam TEXTO na observação — mas a medida veio da
    geometria. Rebaixá-los seria destruir o trabalho do motor."""
    itens = [_it(o) for o in REAIS_QUE_DEVEM_FICAR]
    ach = selos_sem_geometria(itens)
    assert not ach, (
        "rebaixou medição legítima:\n  " + "\n  ".join(
            REAIS_QUE_DEVEM_FICAR[a["indice"]][:100] for a in ach))


def test_o_rotulo_dxf_geom_sozinho_NAO_absolve_mais():
    """🚨 29/08/2026 — ESTE TESTE GUARDAVA O BUG.

    Ele dizia: "quem tem origem dxf_geom não é julgado por texto nenhum". E o
    `main.py` carimba `origem="dxf_geom"` em TODO item vindo de DXF, sem olhar
    de onde a quantidade saiu. Somando as duas coisas, este guarda pulava o
    caminho DXF inteiro — ele só funcionava de fato para itens de PDF.

    📊 Medido no acervo em 29/08: 492 itens confirmados com esse rótulo, 46
    deles com procedência só de texto — 38 do aço (caso legítimo, tratado à
    parte) e 8 outros em 5 projetos de cliente, que eram vazamento silencioso
    desde que o guarda nasceu.

    🔑 A regra agora: rótulo não é prova. A origem só absolve quando o TEXTO da
    procedência confirma a geometria. A frase que o motor escreve quando mede
    vale mais que um campo preenchido no atacado.
    """
    assert selos_sem_geometria(
        [_it("Conforme legenda código 01 — quantidade explícita", origem="dxf_geom")]), (
        "rótulo 'dxf_geom' voltou a absolver sozinho — o guarda fica cego pro "
        "caminho DXF inteiro de novo")


def test_origem_dxf_geom_COM_prova_no_texto_continua_absolvendo():
    """🧪 O outro lado: quando o rótulo e o texto concordam, não acusa."""
    assert not selos_sem_geometria(
        [_it("Área hachurada do layer PISO-CER: 128,40 m²", origem="dxf_geom")])


def test_o_QUADRO_DE_ACO_e_a_unica_excecao_de_texto():
    """⚖️ Decisão de 29/08, e a razão está escrita em `_QUADRO_DE_ACO`.

    Tabela com COLUNAS ROTULADAS é diferente de texto solto: o desenho diz o
    que cada número é (bitola, comprimento, peso), então não há adivinhação de
    atribuição — que foi exatamente o erro de 24/08 (a área da clínica colada
    na linha do piso). Some-se a isso que o quadro é conferido contra a massa
    linear da NBR e contra o total impresso na prancha.

    E o argumento que fecha: geometria NÃO pesa armadura — a prancha não
    desenha barra por barra. Exigir geometria aqui seria dizer que aço nunca
    pode ser medido, em projeto nenhum.
    """
    assert not selos_sem_geometria([_it(
        "Fonte: Quadro/Resumo de Aço lido da prancha [MEDIDO]. Comprimento 409 m.",
        origem="dxf_geom")])
    # 🔒 e a exceção é ESTREITA: outra tabela qualquer continua sendo acusada
    assert selos_sem_geometria([_it(
        "Fonte: tabela de ambientes da prancha — área 264,54 m²",
        origem="dxf_geom")]), (
        "a exceção vazou pra qualquer tabela — só o quadro de aço, nomeado, "
        "tem as duas conferências que justificam o selo")


def test_nao_acusa_quem_nao_declarou_procedencia():
    """Sem observação, ou com observação que não diz de onde veio, a rede se
    cala. Acusar no escuro seria rebaixar meio acervo por precaução."""
    assert not selos_sem_geometria([_it("")])
    assert not selos_sem_geometria([_it("Item de praxe para obras de reforma.")])
    assert not selos_sem_geometria([_it("Revisar antes de orçar.")])


def test_so_mexe_em_quem_esta_marcado_como_medido():
    assert not selos_sem_geometria([_it("Conforme legenda", conf="estimado")])
    assert not selos_sem_geometria([_it("Fonte: texto na legenda", conf="verificar")])


def test_a_rede_so_REBAIXA_nunca_promove():
    """Guarda de direção: a função devolve índices pra rebaixar. Se algum dia
    ela apontar um item que NÃO está confirmado, virou promoção."""
    itens = [_it("Fonte: texto na legenda", conf="estimado"),
             _it("Fonte: texto na legenda", conf="confirmado")]
    ach = selos_sem_geometria(itens)
    assert [a["indice"] for a in ach] == [1]


def test_a_rede_esta_ligada_no_process_job():
    """🚨 25/08 (auditoria): a versão anterior deste guarda passava VERDE com a
    rede NUNCA sendo chamada. Ela conferia que o import existia e que 4 strings
    apareciam numa janela de 1400 chars — nada disso prova execução.

    É a defesa da REGRA DURA Nº1, a mais importante do produto, e dava pra
    desligá-la sem nenhum teste reclamar. Sabotagem que provou: trocar
    `_ssg(all_items)` por `(lambda *a, **k: [])(all_items)` → 8 testes passaram.

    🪤 Mesmo erro do guarda da ordenação de e-mails, no mesmo dia: conferir que
    a função EXISTE em vez de conferir que ela é CHAMADA e que o resultado é
    USADO."""
    import io
    import re
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    assert "selos_sem_geometria as _ssg" in src, "a rede nem é importada"

    # 1. é CHAMADA, com os itens do projeto
    assert re.search(r"_sem_geo\s*=\s*_ssg\(\s*all_items\s*\)", src), (
        "a rede não é chamada com all_items — foi assim que a sabotagem passou")
    # 2. o resultado é PERCORRIDO pelo laço que REBAIXA — e só ele conta.
    # 🪤 A 1ª versão deste guarda procurava "for X in _sem_geo" em TODO o
    # arquivo, e casava com `for x in _sem_geo[:4]` de DENTRO da mensagem de
    # log. Trocar o laço de verdade por `for _a in []` passava verde, porque o
    # laço do log continuava lá. Guarda tem que olhar o trecho que AGE.
    i = src.index("_sem_geo = _ssg(")
    j = src.index("motor:selo-sem-geometria", i)
    age = src[i:j]                      # só o que roda ANTES do log
    assert re.search(r"for\s+\w+\s+in\s+_sem_geo\s*:", age), (
        "o resultado da rede não é percorrido pelo laço que rebaixa — foi assim "
        "que a sabotagem passou")
    # 3. o que ela aponta é REBAIXADO, nunca promovido.
    # 🪤 Aqui eu me enrolei: usei o MESMO trecho (que vai só até o log) pra
    # depois exigir que o log estivesse dentro dele — impossível por
    # construção, e o guarda reprovava o código CERTO. Duas perguntas
    # diferentes pedem duas janelas diferentes.
    trecho = src[i:i + 1400]
    assert "_CfG.ESTIMADO" in trecho, "não rebaixa o selo"
    assert "_CfG.CONFIRMADO" not in trecho, "🚨 a rede está PROMOVENDO"
    assert "motor:selo-sem-geometria" in trecho, "não deixa rastro no log"
    assert "LIDO de um texto da prancha" in trecho, "não explica ao cliente"


# ══════════════════════════════════════════════════════════════════════════
#  📏 O numero dos itens ANTIGOS tem que reproduzir
# ══════════════════════════════════════════════════════════════════════════
#
# 🚨 25/08 (auditoria): quantos itens historicos seguem com o selo indevido? O
# numero ja saiu TRES vezes diferente — 61 (documentado em 24/08), 82 (a
# auditoria) e 38 (uma query minha de hoje). Nenhum estava "errado": cada um
# escreveu A MAO o proprio criterio de "procedencia so de texto".
#
# A rede E o criterio. Contar com ela e a unica forma de reproduzir; qualquer
# SQL novo seria a quarta versao.
def test_existe_uma_rota_que_conta_com_a_PROPRIA_rede():
    import io as _io
    src = _io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    assert '@app.get("/api/admin/selo-historico")' in src
    corpo = corpo_de("admin_selo_historico")
    assert "selos_sem_geometria as _ssg_h" in corpo, (
        "a rota conta por criterio proprio em vez de usar a rede — e assim que "
        "nasce a quarta versao do numero")


def test_a_rota_de_contagem_NAO_altera_nada():
    """🚫 A rede vale pra leitura NOVA. Mexer no selo de projeto ja entregue e
    decisao do Pedro: o cliente pode ter usado aquela planilha."""
    import io as _io
    src = _io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    # 🪤 28/08: procurava "async def" literal e quebrou quando a rota virou
    # `def` (rota async com corpo bloqueante congelava o servidor). "def X"
    # casa com as duas formas — e essa e a busca certa em qualquer caso.
    i = src.index("def admin_selo_historico")
    j = src.index('@app.post("/api/admin/spec-backfill")', i)
    corpo = src[i:j]
    for escrita in ('"PATCH"', '"POST"', '"DELETE"', "update", "insert"):
        assert escrita not in corpo, (
            "a rota de CONTAGEM faz %s — ela so pode ler" % escrita)


def test_a_rota_e_so_de_admin():
    import io as _io
    src = _io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    assert "_require_admin(request)" in corpo_de("admin_selo_historico")


# ══════════════════════════════════════════════════════════════════════════
#  🚨 Se a rede NAO RODAR, o cliente tem que saber
# ══════════════════════════════════════════════════════════════════════════
#
# Auditoria de 25/08: a rede da REGRA DURA Nº1 vivia dentro de um `except` que
# so escrevia no log. Se ela quebrasse, o cliente recebia selos de "✓ MEDIDO do
# CAD" que NUNCA foram conferidos — e nao tinha como saber.
#
# Falhar FECHADA (rebaixar tudo) arruinaria um projeto bom por um erro
# passageiro. Falhar ABERTA e calada e o que estava. O desfecho honesto entre os
# dois e falhar DECLARADA: os selos ficam, e o cliente e avisado.
def _bloco_da_rede():
    """Só o bloco da rede — do começo ao FIM do seu except.

    🪤 3ª vez hoje que erro a janela de recorte de um guarda. A 1ª versao ia ate
    "motor:escala-aviso", e nesse caminho estava o `project_data.warnings` do
    bloco SEGUINTE (o da escala). Resultado: apaguei o aviso da rede e o teste
    passou verde, porque estava lendo o aviso de outra coisa.

    Janela de guarda tem que terminar onde o assunto termina. Aqui: no `try:`
    do bloco seguinte, no mesmo nivel de indentacao."""
    import io as _io
    src = _io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("_sem_geo = _ssg(all_items)")
    j = src.index(chr(10) + "        try:", src.index("except Exception as _esg", i))
    return src[i:j]


def test_quando_a_rede_QUEBRA_o_cliente_e_avisado():
    corpo = _bloco_da_rede()
    i = corpo.index("except Exception as _esg")
    depois = corpo[i:]
    assert "project_data.warnings" in depois, (
        "a rede da regra nº1 voltou a falhar em silêncio pro cliente — ele "
        "recebe selo de MEDIDO sem conferência e não fica sabendo")
    assert "sem essa segunda" in depois or "não rodou" in depois


def test_o_aviso_de_falha_NAO_promete_o_que_nao_houve():
    """Ele não pode dizer 'conferimos' — a checagem justamente não rodou."""
    corpo = _bloco_da_rede()
    i = corpo.index("except Exception as _esg")
    assert "Não conseguimos rodar a conferência" in corpo[i:]


def test_item_que_NAO_deu_pra_rebaixar_tambem_vira_aviso():
    """🪤 Era um `except: pass` cru: o item ficava com selo de MEDIDO e nem o
    log registrava."""
    corpo = _bloco_da_rede()
    assert "_falhou_rebaixar" in corpo
    assert "except Exception:" in corpo
    assert "_falhou_rebaixar += 1" in corpo
    i = corpo.index("if _falhou_rebaixar:")
    assert "project_data.warnings" in corpo[i:i + 700]


def test_o_caminho_FELIZ_nao_ganhou_aviso_nenhum():
    """Controle negativo: projeto em que a rede roda bem não pode receber aviso
    de falha — alarme que sai sempre ensina a ignorar."""
    corpo = _bloco_da_rede()
    i_ok = corpo.index("if _sem_geo:")
    i_falha = corpo.index("if _falhou_rebaixar:")
    assert i_ok < i_falha, "a ordem mudou; o teste está medindo outra coisa"
    trecho_ok = corpo[i_ok:i_falha]
    assert "project_data.warnings" not in trecho_ok, (
        "o caminho de sucesso passou a acrescentar aviso de falha")


# ── o guarda precisa conhecer o vocabulário do próprio motor ─────────────────

def test_COMPRIMENTO_de_layer_com_valor_e_MEDICAO_nao_texto():
    """🚨 29/08/2026 — falso positivo achado ao conferir os 81 acusados.

    "Condutos no teto — Fonte: layer 'EL-Condutos (Teto)' = 9,92 m" estava na
    lista de rebaixamento. Isso é comprimento de layer: geometria pura.

    🪤 Guarda que acusa errado é ignorado, e aí para de proteger. O custo aqui
    não é teórico: 81 itens de 21 clientes dependem desse número pra virar (ou
    não) uma decisão de rebaixamento retroativo.
    """
    assert not selos_sem_geometria(
        [_it("Fonte: layer 'EL-Condutos (Teto)' = 9.92 m (único significativo)")])
    assert not selos_sem_geometria(
        [_it("Fonte: layer 'F-FURO-PAREDE' = 10,43 m (COMPRIMENTOS POR LAYER)")])


def test_TEXTO_layer_continua_sendo_acusado():
    """🔒 O contraste que decide, e é uma palavra de diferença:
        "layer 'X' = 9,92 m"          → mediu    (absolve)
        "texto layer 'X': 'AREA=...'" → leu      (acusa)
    O segundo é literalmente o caso que criou este guarda em 24/08."""
    assert selos_sem_geometria([_it(
        "Fonte: texto layer 'ARQ-TEXTO 1': 'AREA TOTAL CLINICA = 264,54 m²'")]), (
        "o caso original de 24/08 deixou de ser acusado — a exceção do "
        "comprimento de layer vazou pra leitura de texto")


def test_ATRIBUTO_de_bloco_e_dado_estruturado_do_projetista():
    """Atributo é campo que o projetista preencheu DENTRO do bloco — o arquivo
    diz o que o valor é, como no quadro de aço. Não é frase solta."""
    assert not selos_sem_geometria(
        [_it("Fonte: atributo de bloco EL_IND_QUADRO com TAG=QFAC-OL")])


def test_CONTROLE_POSITIVO_o_guarda_ainda_acusa_o_que_deve():
    """🧪 Depois de alargar a lista de provas três vezes, o risco é ter virado
    peneira. Os quatro casos que TÊM que continuar reprovando."""
    for obs in (
        "Fonte: texto layer 'ARQ-TEXTO 1': 'AREA TOTAL CLINICA = 264,54 m²'",
        "Conforme legenda código 06 — área APROXIMADA explícita",
        "Fonte: texto G-ANNO-TEXT: 'REGULARIZAÇÃO DE LAJE - Á= 1.177,70m²'",
        "Fonte: tabela de ambientes da prancha — área 264,54 m²",
    ):
        assert selos_sem_geometria([_it(obs)]), (
            "deixou de acusar, o guarda virou peneira: %r" % obs[:60])
