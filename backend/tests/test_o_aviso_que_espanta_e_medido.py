# -*- coding: utf-8 -*-
"""Os avisos que a tela dispara sozinha ao escolher o arquivo têm que ser MEDIDOS.

🚨 14/09/2026 — MEDIDO nos **18 cadastros completos (todos com WhatsApp) que
nunca subiram um projeto**:

  · 12 chegaram ao painel,
  ·  4 ESCOLHERAM o arquivo (3 PDF, 1 DWG),
  ·  0 clicaram em processar.

E três deles **reabriram o seletor de arquivo 8 s e 27 s depois de já ter
escolhido** — gesto de quem foi trocar de arquivo, não de quem desistiu do
produto.

🔑 O `processar_bloqueado` (o envelope de 25/08) registrou **2 cliques em 20
dias**, nenhum dessas pessoas. Então elas nem chegaram ao botão: a desistência
acontece ANTES dele. E o que existe nesse intervalo são dois avisos que a tela
dispara sozinha ao escolher o arquivo — e que nunca foram medidos:

  · o do PDF diz "o quantitativo sai com itens identificados mas com quantidade
    em branco" e fica aberto até a pessoa fechar;
  · o do DWG manda voltar ao CAD e rodar EXPORTTOAUTOCAD antes de continuar.

🪤 Este guarda protege o INSTRUMENTO, não o texto. Nenhum dos dois avisos muda
de redação aqui: primeiro o número diz se é isso, depois se decide. Foi assim
que o envelope de 25/08 nasceu — e é a mesma lição do `poly_layers_recusados`,
que passou 5 dias sendo coletado sem ninguém ler.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _corpo import corpo_js, fonte, sem_comentarios_js  # noqa: E402


def _dash():
    return fonte("dashboard.html")


# ── cada aviso registra, no lugar certo ──────────────────────────────────
def test_o_aviso_do_PDF_registra():
    corpo = corpo_js("checkPdfTextAndWarn", "dashboard.html")
    assert "aviso_pdf_sem_texto" in corpo, (
        "o aviso mais pesado da tela — o que diz que a quantidade sai em branco "
        "— voltou a ser invisível: sem evento, não dá pra saber se é ele que "
        "espanta quem escolheu um PDF")
    assert "chars" in corpo, (
        "sem o número de caracteres lidos não dá pra separar 'PDF escaneado' de "
        "'PDF com pouco texto' — e a decisão sobre o texto depende disso")


def test_o_aviso_do_DWG_registra():
    corpo = corpo_js("checkDwgAecAndWarn", "dashboard.html")
    assert "aviso_dwg_aec" in corpo, (
        "o aviso que manda o cliente voltar pro CAD rodar EXPORTTOAUTOCAD é o "
        "pedido mais caro da tela e continua sem medição")


def test_tirar_um_arquivo_da_lista_registra():
    """Entre `arquivo_escolhido` e `clique:processar-projeto` não havia NADA no
    rastro. Remover um arquivo já escolhido é o gesto de quem mudou de ideia.

    🪤 A 1ª versão deste guarda procurava só o NOME do evento e SOBREVIVEU ao
    mutante que trocava `trackEvent(` por outra função: o nome continuava
    escrito, e nada era registrado. Tem que exigir a CHAMADA.
    """
    corpo = corpo_js("renderFiles", "dashboard.html")
    assert re.search(r"trackEvent\s*\(\s*['\"]arquivo_removido['\"]", corpo), (
        "remover arquivo continua invisível — é o único gesto observável entre "
        "escolher e processar, e o nome do evento sem a chamada não registra nada")
    assert "restam" in corpo, (
        "sem `restam` não dá pra separar 'trocou de arquivo' de 'desistiu de tudo'")


# ── o evento tem que CHEGAR: allowlist do /api/track ─────────────────────
def test_os_tres_eventos_passam_pela_allowlist_do_backend():
    """🪤 A armadilha que o próprio código documenta: `/api/track` DESCARTA em
    silêncio evento que não está em `_TRACK_ALLOWED`. Instrumentar sem liberar
    é o mesmo que não instrumentar — com a desvantagem de parecer feito."""
    main_src = fonte("main.py")
    ini = main_src.index("_TRACK_ALLOWED = {")
    fim = main_src.index("}", main_src.index("instagram", ini)) \
        if "instagram" in main_src[ini:ini + 20000] else ini + 20000
    lista = main_src[ini:fim]
    faltando = [e for e in ("aviso_pdf_sem_texto", "aviso_dwg_aec", "arquivo_removido")
                if '"%s"' % e not in lista]
    assert not faltando, (
        "evento(s) instrumentado(s) no front mas NÃO liberado(s) no /api/track: "
        "%r — seriam descartados em silêncio" % faltando)


# ── controle: o que já existia continua de pé ────────────────────────────
def test_CONTROLE_o_envelope_de_25_08_continua_registrando():
    """O `processar_bloqueado` mede o passo SEGUINTE ao que este arquivo mede.
    Os dois juntos cobrem o intervalo inteiro; perder um cega metade."""
    src = _dash()
    assert "processar_bloqueado" in src
    assert "'sem-arquivo'" in src and "'termos'" in src, (
        "o motivo do bloqueio sumiu — sem ele o evento não diz o que fazer")


def test_CONTROLE_o_evento_de_escolher_arquivo_continua():
    assert "arquivo_escolhido" in corpo_js("addFiles", "dashboard.html"), (
        "sem `arquivo_escolhido` o funil perde o denominador de todos os outros")


def test_CONTROLE_o_texto_dos_avisos_NAO_mudou():
    """🪤 Este commit é só instrumento. Se alguém aproveitar pra suavizar o
    aviso, o número que vier depois mede outra coisa e a decisão nasce torta —
    e ninguém vai lembrar que o texto mudou junto.

    🪤 DUAS versões deste guarda sobreviveram à mutação antes desta:
    1. procurava a frase no ARQUIVO INTEIRO — a mesma frase existe em outro
       ponto da tela, então apagar o aviso não reprovava;
    2. procurava no corpo da função, mas o COMENTÁRIO que eu escrevi logo
       acima do aviso CITA a frase — o guarda lia a minha própria anotação e
       passava. É a armadilha do "comentário que planta o defeito", e eu
       reincidi nela hoje. E `sem_comentarios` só conhece `#`, de Python:
       num recorte de JS ela nao tira nada. Por isso `sem_comentarios_js`.
    """
    pdf = sem_comentarios_js(corpo_js("checkPdfTextAndWarn", "dashboard.html"))
    assert "quantidade em branco" in pdf, (
        "o texto do aviso do PDF foi alterado no commit do instrumento — o "
        "número que vier depois vai medir outro aviso")
    dwg = sem_comentarios_js(corpo_js("checkDwgAecAndWarn", "dashboard.html"))
    assert "EXPORTTOAUTOCAD" in dwg, (
        "o texto do aviso do DWG foi alterado no commit do instrumento")
