# -*- coding: utf-8 -*-
"""A medição geométrica da prancha tem que CHEGAR na IA (31/08/2026).

🩸 O motor mede a geometria do PDF, monta a seção "=== MEDIÇÕES VETORIAIS DA
PRANCHA ===" com quantos m² foram medidos, cola no fim do texto da prancha
(`main.py`: `text_content = text[:5000] + _vet_secao`) — e o analyzer cortava
tudo em `[:3000]`. Numa prancha com 3000+ caracteres de texto extraível, a
medição sumia INTEIRA antes de chegar ao modelo.

🪤 A CORRELAÇÃO É ADVERSA, e é o que torna isso pior do que parece: a seção só
existe quando o PDF é VETORIAL — e PDF vetorial é justamente o que tem muito
texto extraível. O corte tendia a apagar a medição exatamente onde ela existia.
(Nas 13 pranchas de teste locais o texto não passa de 1.190 caracteres, mas elas
são raster: 0 a 44 caracteres na maioria, e prancha raster não tem medição
vetorial pra perder. Não consegui medir a frequência real — o conserto vale
porque o modo de falha é real e não custa nada quando o texto é curto.)

🔑 O corte agora vale só pro TEXTO da prancha; a medição vai inteira, sempre.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analyzer  # noqa: E402


class _Sheet:
    def __init__(self, texto):
        self.text_content = texto
        self.crops = []
        self.sheet_type = None
        self.filename = "prancha.pdf"


_MEDICAO = (
    "\n=== MEDIÇÕES VETORIAIS DA PRANCHA (validadas por cota) ===\n"
    "Escala 1:50 confirmada por 29 cota(s) da própria prancha.\n"
    "Ambientes MEDIDOS geometricamente: 12 somando 107.7 m².\n"
    "Paredes/divisórias MEDIDAS: 74.6 m (42 segmentos).")


class _Resp:
    class _C:
        text = '{"items": []}'
    content = [_C()]


def _texto_enviado(sheet, monkeypatch):
    """O que de fato vai no bloco de texto do prompt.

    🚨 31/08: a 1ª versão disto REIMPLEMENTAVA o recorte do analyzer quando não
    achava uma função `_monta_conteudo` — que eu inventei e nunca existiu. Ou
    seja: o teste passava verde conferindo a MINHA CÓPIA da lógica, não o
    código. Guarda tautológico, exatamente o vício que este dia inteiro está
    auditando. Agora chama `analyze_sheet` de verdade e intercepta o que ela
    manda pro modelo."""
    capturado = {}

    def _fake_stream(client, **kw):
        capturado["messages"] = kw.get("messages")
        return _Resp()
    monkeypatch.setattr(analyzer, "call_with_retry_stream", _fake_stream)
    analyzer.analyze_sheet(None, sheet)
    assert capturado.get("messages"), "analyze_sheet não chegou a chamar o modelo"
    blocos = capturado["messages"][0]["content"]
    textos = [b["text"] for b in blocos if b.get("type") == "text"]
    assert textos, "nenhum bloco de texto foi enviado"
    return textos[0]


def test_prancha_LONGA_nao_perde_a_medicao(monkeypatch):
    """🧪 O teste que importa: 4.000 caracteres de texto + a medição no fim."""
    enviado = _texto_enviado(_Sheet("A" * 4000 + _MEDICAO), monkeypatch)
    assert "MEDIÇÕES VETORIAIS DA PRANCHA" in enviado, (
        "a medição foi cortada — a IA não vai saber que a gente mediu a planta")
    assert "107.7 m²" in enviado, "sumiu o número medido"
    assert "74.6 m" in enviado, "sumiu o comprimento medido"


def test_o_texto_da_prancha_CONTINUA_limitado(monkeypatch):
    """O corte existe por um motivo (custo e janela do modelo). Preservar a
    medição não pode virar mandar a prancha inteira."""
    import analyzer as _a
    enviado = _texto_enviado(_Sheet("A" * 40000 + _MEDICAO), monkeypatch)
    # 🪤 contar "A" no texto INTEIRO conta as maiúsculas da própria medição
    # ("PRANCHA", "MEDIÇÕES"...) — erro meu na 1ª versão deste teste. O que
    # importa é o tamanho do CORPO, antes da marca.
    corpo = enviado.split(_a.MARCA_MEDICAO_VETORIAL)[0]
    # 🪤 o bloco vai com um prefixo ("Texto extraído do PDF:") — a 1ª versão
    # deste teste não sabia disso porque reimplementava o analyzer em vez de
    # chamá-lo. Conta só os "A" do corpo.
    assert corpo.count("A") == 3000, (
        "o corte do texto da prancha sumiu (A=%d) — vai mandar tudo pro modelo"
        % corpo.count("A"))
    assert "MEDIÇÕES VETORIAIS" in enviado, "e a medição tem que continuar lá"


def test_prancha_CURTA_continua_igual(monkeypatch):
    """Sem medição e com texto curto, nada muda."""
    enviado = _texto_enviado(_Sheet("planta baixa, sala, quarto"), monkeypatch)
    assert enviado.endswith("planta baixa, sala, quarto")
    assert "Texto extraído do PDF" in enviado


def test_prancha_SEM_medicao_nao_ganha_nada(monkeypatch):
    enviado = _texto_enviado(_Sheet("B" * 5000), monkeypatch)
    assert enviado.count("B") == 3000, "o corte do texto deixou de valer"
    assert "MEDIÇÕES" not in enviado


def test_CONTROLE_a_MARCA_e_a_MESMA_nos_dois_arquivos():
    """🪤 `main.py` ESCREVE a marca e `analyzer.py` PROCURA. Se as duas strings
    divergirem — alguém troca um acento, muda o texto do cabeçalho — o find()
    devolve -1, a medição volta a ser cortada e NINGUÉM percebe: nenhum teste
    quebra, nenhum log grita, a planilha só fica pior. Por isso a marca mora numa
    constante e este guarda confere que o main ainda a escreve literalmente."""
    import io
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    main_src = io.open(os.path.join(base, "main.py"), encoding="utf-8").read()
    marca = analyzer.MARCA_MEDICAO_VETORIAL
    assert marca in main_src, (
        "o main.py não escreve mais a marca %r que o analyzer procura — a "
        "medição está sendo cortada em silêncio de novo" % marca)
    # e escreve nos DOIS ramos (escala validada e não validada)
    assert main_src.count(marca) >= 2, (
        "só um dos dois ramos de medição escreve a marca (validada × não "
        "validada) — um deles perde a medição")


def test_CONTROLE_o_guarda_REPROVA_se_o_corte_voltar():
    """🧪 Guarda que nunca reprova é pior que guarda nenhum: reproduz o corte
    antigo e confere que ele MATA a medição."""
    antigo = ("A" * 4000 + _MEDICAO)[:3000]
    assert "MEDIÇÕES VETORIAIS" not in antigo, (
        "o corte antigo não perdia a medição — então este arquivo inteiro está "
        "guardando um problema que não existe")
