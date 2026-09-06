# -*- coding: utf-8 -*-
"""O nosso próprio agente mandava o cliente pelo caminho caro.

🩸 02/09/2026. A investigação do "por que ninguém clica" achou o canal onde a
queixa REALMENTE chega — e não é o formulário de contato (1 linha em toda a
história, e é teste interno) nem o chat público (0 linhas). É o chat do agente,
dentro do produto. As frases textuais dos clientes:

    cliente-04  29/07 17:53  "qual a metragem de laje"
    cliente-04  29/07 18:12  "qual a metragem da laje do segundo pavijmento"
    cliente-05   02/09 16:25  "preciso do levantamento de paredes internas e
                               externas para calcular a quantitdade de tinta"

🔑 Nenhum deles diz "veio vazio" ou "faltou". Eles pedem O NÚMERO — não percebem
um defeito nosso a reportar, percebem uma pergunta que ainda precisam responder.

🩸 E o agente respondeu confirmando o vazio e oferecendo os DOIS caminhos caros:
"Quer que eu verifique os DXFs?" e "Informar a área manualmente → editando os
itens 3.3 e 3.7". O produto tem um campo que refaz a planilha inteira na hora,
sem IA e sem custo, a partir de UM número — e o agente nunca o mencionou.

📏 Toda a base tem **30 linhas** de texto escrito por cliente desde abril. Este
canal é praticamente o único que existe; desperdiçá-lo custa caro.

🪤 SÃO DOIS PROMPTS que falam com o cliente sobre a planilha dele
(`agent.py:SYSTEM_PROMPT` e `main.py:PROJECT_CHAT_SYSTEM`) — consertar um só é o
mesmo erro do portão do admin em 02/09, que ficou verde cobrindo metade das
páginas. O guarda abaixo se cobra sozinho: qualquer prompt novo com `{job_id}`
ou `{context}` entra na varredura automaticamente.

🚫 E a regra tem um NÃO tão importante quanto o SIM: a área total NÃO preenche
pintura de parede nem nada que dependa de altura. Oferecer ali seria mandar o
cliente informar um número que não completa a linha dele — o defeito que a
gente vive consertando, do outro lado.
"""
import io
import os
import re
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

_RX_PROMPT = re.compile(
    r'^([A-Z][A-Z0-9_]*(?:SYSTEM|PROMPT)[A-Z0-9_]*)\s*=\s*"""', re.M)

# Prompts que falam com o cliente sobre UM projeto. A marca é o placeholder:
# `{job_id}` (agent.py) ou `{context}` (o chat da página). O chat público e os
# do Instagram não têm nenhum dos dois — separação conferida em 02/09.
_ARQUIVOS = ("main.py", "agent.py", "instagram_agent.py")


def _prompts():
    """Todos os prompts do backend: (arquivo, nome, corpo)."""
    for arq in _ARQUIVOS:
        txt = io.open(os.path.join(_BACKEND, arq), encoding="utf-8").read()
        for m in _RX_PROMPT.finditer(txt):
            fim = txt.find('"""', m.end())
            yield arq, m.group(1), txt[m.end():fim]


def _de_projeto():
    return [(a, n, c) for a, n, c in _prompts()
            if "{job_id}" in c or "{context}" in c]


# ── O guarda que se cobra sozinho ──────────────────────────────────────────
def test_a_varredura_ACHA_os_dois_prompts_conhecidos():
    """🧪 Controle do próprio detector: se ele parar de achar, os testes
    abaixo passam VERDE varrendo lista vazia — o pior modo de falha."""
    achados = {(a, n) for a, n, _ in _de_projeto()}
    assert ("agent.py", "SYSTEM_PROMPT") in achados, achados
    assert ("main.py", "PROJECT_CHAT_SYSTEM") in achados, achados
    assert len(achados) >= 2, "a varredura encolheu"


def test_CONTROLE_o_detector_NAO_pega_os_prompts_sem_projeto():
    """O chat público e os do Instagram não falam de planilha de ninguém —
    incluir eles seria ruído, e ruído acaba desligado."""
    nomes = {n for _, n, _ in _de_projeto()}
    for fora in ("PUBLIC_CHAT_SYSTEM_PROMPT", "SYSTEM_PROMPT_DM",
                 "SYSTEM_PROMPT_CONTENT"):
        assert fora not in nomes, (
            "%s entrou na varredura de prompts de projeto" % fora)


# ── A regra, nos DOIS ───────────────────────────────────────────────────────
def test_TODO_prompt_de_projeto_aponta_o_convite():
    """🩸 O conserto. Vale pros dois de hoje e pro terceiro que nascer."""
    faltando = []
    for arq, nome, corpo in _de_projeto():
        if "Área total" not in corpo or "refeita NA HORA" not in corpo:
            faltando.append("%s:%s" % (arq, nome))
    assert not faltando, (
        "estes prompts falam com o cliente sobre a planilha dele e NÃO "
        "mencionam o campo que resolve a linha vazia na hora: %s" % faltando)


def test_TODO_prompt_de_projeto_oferece_o_convite_ANTES_do_caminho_caro():
    """🪤 Não basta mencionar: o agente citou 'informar manualmente' e
    'reprocessar o DXF' e o cliente foi pelo caro. A ordem é a regra."""
    for arq, nome, corpo in _de_projeto():
        assert "ANTES de qualquer outra saída" in corpo, (
            "%s:%s menciona o campo mas não manda oferecê-lo PRIMEIRO — foi "
            "assim que o agente empurrou o DXF pro kovatch" % (arq, nome))


def test_TODO_prompt_de_projeto_diz_o_que_o_campo_NAO_resolve():
    """🚫 Pintura de parede e qualquer coisa que dependa de altura NÃO são
    preenchidas pela área total. Sem este NÃO, a regra vira promessa falsa —
    o caso cliente-09: ela mexeu num item que precisava de ALTURA, a quantidade
    continuou 0, e 11 minutos depois deu nota 2."""
    for arq, nome, corpo in _de_projeto():
        assert "pintura de PAREDE" in corpo, (
            "%s:%s não exclui pintura de parede" % (arq, nome))
        assert "ALTURA" in corpo and "pé-direito" in corpo, (
            "%s:%s não explica que ali o que falta é o pé-direito" % (arq, nome))


def test_TODO_prompt_de_projeto_proibe_prometer_quantas_linhas():
    """🪤 Quem decide item a item é `_apply_area_honesty`. Prometer número que
    o agente não controla é o aviso que a cliente-31 leu e não se cumpriu."""
    for arq, nome, corpo in _de_projeto():
        assert "NUNCA prometa QUANTAS linhas" in corpo, (
            "%s:%s pode prometer quantas linhas serão preenchidas" % (arq, nome))


def test_TODO_prompt_de_projeto_PROIBE_inventar_campo():
    """🩸 ACHADO RODANDO O AGENTE DE VERDADE, não lendo o prompt.

    Com a 1ª versão desta regra, o Haiku respondeu à pergunta da cliente-05:
    *"Tem um campo 'Altura' logo acima da lista de itens na tela — preencha
    lá"*. **Esse campo não existe.** Eu dei ao modelo a FORMA da frase ("campo
    X logo acima da lista") e ele generalizou pra um controle inventado —
    mandaria o cliente procurar o que não está lá.

    🔑 Guarda de texto nenhum pegaria isso: o prompt estava correto. Só
    chamar o modelo mostrou. Ver [[feedback_arquivo_correto_nao_e_tela_correta]].
    """
    for arq, nome, corpo in _de_projeto():
        assert "NÃO INVENTE CAMPO" in corpo, (
            "%s:%s pode inventar campo/botão que não existe" % (arq, nome))
        assert "NÃO existe campo de altura" in corpo, (
            "%s:%s não diz que a tela de revisão NÃO tem campo de pé-direito — "
            "foi exatamente o campo que o modelo inventou" % (arq, nome))


def test_CONTROLE_a_checagem_sabe_REPROVAR():
    """🧪 Um prompt sem a regra tem que falhar em todas as quatro checagens."""
    falso = "Você é o assistente. Contexto: {context}. Seja gentil."
    assert "Área total" not in falso
    assert "ANTES de qualquer outra saída" not in falso
    assert "pintura de PAREDE" not in falso
    assert "NUNCA prometa QUANTAS linhas" not in falso


# ── E o prompt tem que continuar FUNCIONANDO ───────────────────────────────
def test_os_prompts_continuam_FORMATAVEIS():
    """🚨 Isto é comportamento, não leitura. Estes prompts passam por
    `.format()`: uma chave solta no texto novo levanta KeyError/IndexError e
    derruba o chat inteiro em produção — e nenhum guarda de texto pegaria.
    O `agent.py` já escapa `{{"error": ...}}` justamente por isso."""
    import agent as _ag
    import main as _m
    assert "{job_id}" in _ag.SYSTEM_PROMPT
    pronto = _ag.SYSTEM_PROMPT.format(job_id="abc123")
    assert "abc123" in pronto and "Área total" in pronto

    assert "{context}" in _m.PROJECT_CHAT_SYSTEM
    pronto2 = _m.PROJECT_CHAT_SYSTEM.format(context="itens de teste")
    assert "itens de teste" in pronto2 and "Área total" in pronto2


def test_CONTROLE_uma_chave_solta_REALMENTE_quebraria():
    """🧪 Prova que o teste acima sabe reprovar: sem isto ele passaria mesmo
    que `.format()` nunca pudesse falhar."""
    ruim = "Contexto: {context}. E uma chave solta: {piso}"
    try:
        ruim.format(context="x")
    except (KeyError, IndexError):
        return
    raise AssertionError("o .format() aceitou chave desconhecida — o guarda "
                         "de formatação deixou de provar alguma coisa")
