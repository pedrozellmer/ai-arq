# -*- coding: utf-8 -*-
"""Cache por conteúdo: o carimbo tem que mudar quando a RESPOSTA mudaria.

🎯 28/08/2026. Toda leitura de prancha custa uma chamada de IA, e a mesma
prancha é lida de novo em três situações: o cliente reprocessa, o job cai e
retoma sozinho, e a bancada roda o mesmo arquivo dezenas de vezes. Além do
custo, o motor não é determinístico — a mesma prancha já deu 22 e 34 itens.

🔑 O DESENHO: carimbar o PAYLOAD que vai pra API, não uma lista de ingredientes
mantida à mão. Mexeu no SYSTEM_PROMPT, na diretiva de pé-direito, na env do
modelo ou na temperatura → a chave muda sozinha.

🪤 A ARMADILHA JÁ EXISTE NO REPO, e é ela que este arquivo existe pra impedir
de se repetir: `pdfvec_carimbo.py:220` cacheia por
`sha256(arquivo):página:_PROMPT_VERSION`, com `_PROMPT_VERSION = "v3"` bumpado
NA MÃO e **sem o modelo na chave**. Trocar Haiku por Sonnet ali serve a
resposta do modelo velho, calada. A própria skill do projeto
(`content-hash-cache-pattern`) avisa disso em "when NOT to use".

📌 A pergunta que cada teste abaixo responde é sempre a mesma: **se a resposta
da IA mudaria, a chave muda?** Guarda que só testa "mesmo payload dá hit" é
inútil — o dano mora do outro lado.

✅ Payload estável foi MEDIDO antes de construir: 4 extrações do mesmo DXF de
24 MB, em subprocessos separados (`PYTHONHASHSEED` diferente em cada), deram
sha256 idêntico. Sem isso o cache nasceria com 0% de acerto.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import llm_cache  # noqa: E402


def _payload(**mudanca):
    """Um payload representativo do caminho DXF, com um campo trocável."""
    base = {
        "tag": "dxf:prancha.dxf",
        "model": "claude-sonnet-4-6",
        "max_tokens": 32000,
        "temperature": 0.7,
        "cache_system": True,
        "system": "Você lê pranchas de arquitetura e devolve JSON.",
        "messages": [{"role": "user", "content": "PÉ-DIREITO: 2.80 m\nLAYERS: ..."}],
    }
    base.update(mudanca)
    return base


# ───────────────────────── o lado que importa: MUDOU → MISS ──────────────────

def test_mudar_UM_CARACTERE_do_system_muda_a_chave():
    """🚨 O teste da armadilha. É esta a diferença entre o cache novo e o
    `pdfvec_carimbo`: lá o prompt só invalida se alguém lembrar de bumpar uma
    string à mão. Aqui é mecânico."""
    a = llm_cache.carimbo(_payload())
    b = llm_cache.carimbo(_payload(
        system="Você lê pranchas de arquitetura e devolve JSON!"))
    assert a != b, (
        "mudei o SYSTEM_PROMPT e a chave ficou igual — todo conserto de prompt "
        "passaria a servir a resposta ANTERIOR, e a gente pararia de ver o "
        "conserto funcionar")


def test_mudar_o_MODELO_muda_a_chave():
    """🪤 Exatamente o buraco do `pdfvec_carimbo`, que não tem o modelo na
    chave. `DXF_EXTRACT_MODEL` é env do Render e troca SEM deploy — carimbo
    baseado em git sha não pegaria."""
    assert llm_cache.carimbo(_payload()) != llm_cache.carimbo(
        _payload(model="claude-opus-4-8")), "trocar de modelo não invalidou"


def test_mudar_a_TEMPERATURA_muda_a_chave():
    """`DXF_EXTRACT_TEMP` também é env do Render (default 0,7). Foi ela que
    custou a prancha da Amanda em 26/08 quando estava em 0."""
    assert llm_cache.carimbo(_payload()) != llm_cache.carimbo(
        _payload(temperature=0.0)), "trocar a temperatura não invalidou"


def test_mudar_o_PE_DIREITO_do_cliente_muda_a_chave():
    """O pé-direito informado entra no prompt (`_pd_directive`). Se ele não
    invalidasse, o cliente informaria a altura e receberia de volta a leitura
    feita SEM ela — e concluiria que informar não adianta nada."""
    outro = _payload()
    outro["messages"] = [{"role": "user", "content": "PÉ-DIREITO: 3.50 m\nLAYERS: ..."}]
    assert llm_cache.carimbo(_payload()) != llm_cache.carimbo(outro)


def test_kwarg_DESCONHECIDO_entra_no_hash_por_padrao():
    """🔒 LISTA NEGRA, nunca lista branca. Parâmetro novo que alguém acrescentar
    amanhã tem que invalidar por padrão.

    Foi lista BRANCA que matou o instrumento do cadastro em 27/08: a chave
    `campo` era descartada calada porque não estava numa lista. Aqui o custo de
    errar pra esse lado é servir resposta velha — pior."""
    a = llm_cache.carimbo(_payload())
    b = llm_cache.carimbo(_payload(parametro_que_ninguem_previu="x"))
    assert a != b, (
        "kwarg desconhecido NÃO entrou no hash — o carimbo virou lista branca "
        "e passa a ignorar tudo que for inventado depois")


# ───────────────────── o outro lado: NÃO-semântico → mesma chave ─────────────

def test_cache_system_NAO_muda_a_chave():
    """`cache_system` liga o prompt caching da Anthropic: muda o CUSTO, não a
    resposta. Se invalidasse, o cache nunca acertaria entre uma chamada com e
    outra sem — que é o que acontece quando `LLM_PROMPT_CACHE=0`."""
    assert llm_cache.carimbo(_payload(cache_system=True)) == \
           llm_cache.carimbo(_payload(cache_system=False))


def test_a_TAG_e_a_politica_de_retry_NAO_mudam_a_chave():
    """`tag` é rótulo de log e traz o NOME DO ARQUIVO. Se entrasse na chave,
    dois arquivos de conteúdo idêntico com nomes diferentes nunca se
    aproveitariam — e renomear um arquivo invalidaria o cache dele."""
    assert llm_cache.carimbo(_payload(tag="dxf:outro-nome.dxf")) == \
           llm_cache.carimbo(_payload())
    assert llm_cache.carimbo(_payload(max_retries=3)) == \
           llm_cache.carimbo(_payload())


def test_a_ORDEM_das_chaves_nao_muda_a_chave():
    """Dicionário reordenado é o mesmo payload. Sem `sort_keys` o cache
    acertaria por acaso."""
    a = _payload()
    b = {k: a[k] for k in reversed(list(a.keys()))}
    assert llm_cache.carimbo(a) == llm_cache.carimbo(b)


# ─────────────────────────── o que NÃO pode ser gravado ──────────────────────

class _Resp:
    class _B:
        def __init__(self, t):
            self.text = t
    def __init__(self, texto, stop="end_turn"):
        self.content = [self._B(texto)]
        self.stop_reason = stop


def test_resposta_CORTADA_no_teto_nao_pode_ser_gravada():
    """🚨 A trava que mais importa. Medido em 24/08: `stop_reason='max_tokens'`
    acontece em ~22% das leituras de DXF. Gravar uma dessas congelaria a leitura
    MUTILADA e ela voltaria pra sempre — inclusive depois de a gente consertar o
    corte. É o pior estrago possível aqui: bug antigo servido como resposta boa.
    """
    pode, motivo = llm_cache.pode_gravar(_Resp('{"items": [', stop="max_tokens"))
    assert not pode, "resposta cortada no teto seria gravada e servida pra sempre"
    assert "max_tokens" in motivo


def test_resposta_VAZIA_nao_pode_ser_gravada():
    """Planilha vazia é sempre falha (armadilha nº10 do CLAUDE.md). Cachear
    uma transformaria uma falha momentânea em falha permanente."""
    assert not llm_cache.pode_gravar(_Resp(""))[0]
    assert not llm_cache.pode_gravar(_Resp("   \n  "))[0]


def test_resposta_COMPLETA_pode():
    """🧪 Controle positivo: sem isto, `pode_gravar` retornando sempre False
    passaria nos dois testes acima e o cache nunca gravaria nada."""
    pode, motivo = llm_cache.pode_gravar(_Resp('{"items": [{"d": "parede"}]}'))
    assert pode, "resposta boa foi recusada: %s" % motivo


# ─────────────────────────────── o modo de operação ──────────────────────────

def test_o_default_e_SOMBRA(monkeypatch):
    """🪤 O default NÃO serve do cache. Calcula a chave e loga acerto/erro, e é
    isso — pra medir a taxa real antes de mudar a leitura de um cliente sequer.

    O único jeito de pegar cedo o caso "payload instável = 0% de acerto" sem
    estragar a leitura de ninguém. Provei estabilidade em UM arquivo; sombra é
    o que cobre os outros."""
    monkeypatch.delenv("LLM_CACHE", raising=False)
    assert llm_cache._modo() == "sombra"


def test_o_kill_switch_funciona(monkeypatch):
    """`LLM_CACHE=off` desliga sem deploy — rede de segurança pro caminho que
    gera a planilha."""
    monkeypatch.setenv("LLM_CACHE", "off")
    assert llm_cache._modo() == "off"
    assert llm_cache.ler("qualquer") is None
    assert llm_cache.gravar("qualquer", _Resp("x"), {}) is False


def test_valor_invalido_na_env_cai_pra_SOMBRA(monkeypatch):
    """Errar o valor da env não pode LIGAR o cache por acidente."""
    monkeypatch.setenv("LLM_CACHE", "sim")
    assert llm_cache._modo() == "sombra"


# ────────────────────────── a lista negra é decisão de gente ─────────────────

def test_a_LISTA_NEGRA_nao_cresce_sozinha():
    """🚨 Cada nome aqui é um parâmetro que o carimbo IGNORA. Acrescentar um por
    engano faz o cache servir resposta velha quando não devia — e isso é
    silencioso. Se este teste falhar, a pergunta é: esse parâmetro realmente
    não muda a RESPOSTA da IA?"""
    assert llm_cache._NAO_SEMANTICO == frozenset({
        "tag", "max_retries", "base_delay", "max_delay",
        "cache_system", "cache", "extra_headers", "stream", "timeout",
    }), ("a lista do que o carimbo ignora mudou: %s. Justifique cada nome novo "
         "— o custo de errar aqui é servir leitura velha, calado."
         % sorted(llm_cache._NAO_SEMANTICO))


def test_o_reprocesso_do_cliente_NAO_le_do_cache():
    """🪤 Quem clica "reprocessar" quer leitura NOVA. Com temperatura 0,7 uma
    rodada nova é justamente a chance de consertar a prancha — servir o cache
    ali mataria a saída de emergência dele.

    Guarda do CALL SITE: já passei verde duas vezes testando a função e não
    quem chama."""
    import io
    src = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()
    linhas = [l for l in src.split("\n")
              if "cache=" in l and "cache_system" not in l
              and not l.strip().startswith("#")]
    assert any("_reproc_atual == 0" in l for l in linhas), (
        "o caminho DXF deixou de desligar o cache no reprocesso: %s" % linhas[:5])


def test_o_cache_DA_SINAL_DE_VIDA_no_boot():
    """🩺 Sem isto o cache pode estar MORTO e o log fica idêntico ao de um cache
    que só não acertou ainda — porque tudo aqui é best-effort e silencioso.

    Foi assim que o `signup_saiu_da_tela` viveu um dia inteiro sem gravar o
    `campo` em 27/08: o instrumento existia, chegava ao banco, e perdia a única
    informação pra qual foi feito. Uma linha no boot responde antes de qualquer
    cliente chegar.
    """
    import io
    src = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()
    i = src.find('@app.on_event("startup")')
    assert i > 0, "sumiu o hook de startup"
    j = src.find("\n@app.", i + 10)
    bloco = src[i:j if j > 0 else i + 20000]
    assert "boot:llm-cache" in bloco, (
        "o cache não deixa mais sinal de vida no boot — se ele morrer, a "
        "medição de sombra dá ZERO por motivo errado e ninguém saberia")
    # 🪤 E o sinal tem que provar a GRAVAÇÃO, não só a leitura. A 1ª versão só
    # lia; descobri o furo tentando gravar da minha máquina e levando 42501 do
    # RLS. Em modo sombra nada grava até um cliente processar um projeto, então
    # sem isto um cache que não escreve passaria semanas parecendo um cache que
    # só não acertou ainda.
    assert "checar_no_boot" in bloco, (
        "o sinal de boot voltou a testar só a leitura — gravação continuaria "
        "sem prova nenhuma")
    # e o sinal tem que distinguir vivo de morto, não só 'passei por aqui'
    assert "MORTO" in bloco and "VIVO" in bloco, (
        "o sinal de boot não separa vivo de morto")
    assert 'severity="error"' in bloco, (
        "a falha do cache no boot entra como info — ela some no meio do log")


def test_a_sentinela_do_boot_prova_a_IDA_E_A_VOLTA():
    """🚨 O que faltava. Gravar e não conseguir ler de volta, ou ler valor
    VELHO, tem que reprovar — não basta a chamada não estourar."""
    import io
    src = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "llm_cache.py"), encoding="utf-8").read()
    i = src.find("def checar_no_boot")
    j = src.find("\ndef ", i + 10)
    corpo = "\n".join(l for l in src[i:j].split("\n")
                      if not l.strip().startswith("#"))
    assert "merge-duplicates" in corpo, (
        "voltou a usar ignore-duplicates: aí a gravação só seria exercitada no "
        "PRIMEIRO boot da vida e nunca mais")
    assert "ler(" in corpo, "grava e não confere se conseguiu ler de volta"
    assert "VELHO" in corpo or "!=" in corpo, (
        "não compara o que leu com o que escreveu — leria a linha do boot "
        "anterior e daria tudo certo com a gravação quebrada")
