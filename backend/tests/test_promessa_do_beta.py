# -*- coding: utf-8 -*-
"""A promessa do beta não pode voltar pelas FONTES que geram copy nova.

🕰️ 31/08/2026 — O PEDRO PERGUNTOU A COISA CERTA. Eu tinha encontrado 17 posts
publicados com "1º projeto grátis" e ia sair editando. Ele: *"faz sentido ficar
alterando o post antigo dado que a gente mudou a regra depois?"* Não faz — a
oferta mudou em **22/07/2026** e post de maio refletindo a oferta de maio é
conteúdo datado, não promessa falsa. Os 17 foram TODOS escritos antes da
mudança (os mais recentes em 15/07, publicados depois só porque ficaram na fila).

🎯 O ALVO É O FUTURO. O que importa não é o arquivo histórico, é **quem ainda
gera copy nova**. E procurando por isso apareceu o que a auditoria de 09/08
tinha deixado passar:
  • `.claude/skills/seo-pt-br/SKILL.md` ensinava o CTA errado como padrão;
  • `backend/instagram_image.py` DESENHAVA a promessa dentro do PNG em 3 lugares
    (o CTA de rodapé, o subtítulo do post promo e o destaque de preço).
🪤 A promessa mora em DOIS lugares: legenda e ARTE. Em 10/08 eu limpei 4 legendas
no banco e duas artes continuaram mentindo. Legenda limpa não conserta imagem.

🚫 O que este guarda NÃO faz: não olha post publicado. Publicado é passado.
"""
import inspect
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import instagram_image  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# variações da oferta ANTIGA (valeu até 22/07/2026)
# 🚨 31/08, 2ª auditoria: faltava a forma SEM ACENTO. Meio repositório escreve
# sem acento (o próprio instagram_agent.py tem "gratis" em várias linhas), então
# o guarda tinha um furo do tamanho da própria regra.
PROIBIDO = ("1º projeto grátis", "1o projeto grátis", "primeiro projeto grátis",
            "1º projeto gratis", "1o projeto gratis", "primeiro projeto gratis",
            "primeiro projeto é grátis", "primeiro projeto e gratis",
            "primeiro projeto é gratis", "primeiro projeto e grátis")

# a frase aparece legitimamente quando o texto ENSINA a não usá-la
NEGACAO = ("nunca", "não escrever", "nao escrever", "proibid", "jamais",
           "oferta antiga", "regra dura de copy", "não pode", "nao pode",
           # 🪤 "pós-beta" é o qualificador que TORNA a frase verdadeira. O
           # termos.html diz "No modelo pós-beta, o primeiro projeto de cada
           # usuário será gratuito" — e isso está CERTO (decisão de 22/07
           # manteve a tabela como preço pós-beta). Uma auditoria marcou essa
           # linha como violação por ler só a substring; sem esta exceção o
           # guarda repetiria o mesmo alarme falso.
           "pós-beta", "pos-beta", "após o beta", "apos o beta", "depois do beta")


def _tem_promessa_antiga(texto: str) -> list:
    """Devolve as linhas que ENSINAM a promessa antiga (ignora a negativa)."""
    achados = []
    for n, linha in enumerate(texto.splitlines(), 1):
        baixa = linha.lower()
        if any(p in baixa for p in PROIBIDO) and not any(x in baixa for x in NEGACAO):
            achados.append((n, linha.strip()[:110]))
    return achados


def test_o_subtitulo_padrao_do_post_promo_nao_promete_o_1o_gratis():
    """EXECUTA: lê o valor real do parâmetro no módulo importado, não o arquivo."""
    padrao = inspect.signature(
        instagram_image.generate_promo_post).parameters["subtitle"].default
    assert not _tem_promessa_antiga(padrao), (
        "o subtítulo padrão do post promo promete o 1º projeto grátis: %r" % padrao)


def test_NENHUMA_fonte_do_backend_ensina_a_promessa_antiga():
    """🚨 31/08, 2ª auditoria: a 1ª versão deste guarda olhava UM arquivo
    (`instagram_image.py`) e a pasta `.claude/`. Passou verde enquanto
    `backend/instagram_agent.py:46` — o prompt do agente que responde DM de
    Instagram — mandava dizer "PRIMEIRO PROJETO É GRÁTIS (até 5 pranchas)".
    Guarda que olha um arquivo não guarda uma regra: varre o backend inteiro."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    problemas = []
    vistos = 0
    for raiz, dirs, arqs in os.walk(base):
        dirs[:] = [d for d in dirs
                   if d not in ("__pycache__", "tests", "sinapi", "tcpo", "assets",
                                "node_modules", ".git")]
        for a in arqs:
            if not a.endswith(".py"):
                continue
            cam = os.path.join(raiz, a)
            try:
                txt = io.open(cam, encoding="utf-8").read()
            except (OSError, UnicodeDecodeError):
                continue
            vistos += 1
            for n, linha in _tem_promessa_antiga(txt):
                problemas.append("%s:%d %s" % (a, n, linha))
    assert vistos > 5, "varri só %d arquivo(s) — guarda inerte" % vistos
    assert not problemas, (
        "fonte do backend ainda ensina a oferta antiga: " + " | ".join(problemas))


def test_o_gerador_de_ARTE_nao_desenha_a_promessa_antiga():
    """🪤 Aqui o guarda LÊ O FONTE, e isso é proposital: a frase que vai pro PNG
    é um literal dentro de `draw.text(...)`. Não dá pra pegar em tempo de
    execução sem renderizar a imagem e fazer OCR. Quando a regra vigia um
    LITERAL, o fonte é o artefato — diferente de vigiar comportamento, onde ler
    fonte é guarda fraco."""
    caminho = os.path.join(RAIZ, "projeto_arq", "backend", "instagram_image.py")
    if not os.path.exists(caminho):
        caminho = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "instagram_image.py")
    fonte = io.open(caminho, encoding="utf-8").read()
    achados = _tem_promessa_antiga(fonte)
    assert not achados, (
        "o gerador de arte desenha a promessa antiga dentro do PNG: %s" % achados)


def test_as_FONTES_que_geram_copy_nova_ensinam_a_promessa_certa():
    """Agentes, skills e a grade do Instagram geram post NOVO. Se a promessa
    velha continuar escrita ali, ela volta na próxima geração — foi assim que a
    skill de SEO seguiu ensinando o CTA errado por 22 dias depois do conserto."""
    base = os.path.join(RAIZ, "projeto_arq", ".claude")
    if not os.path.isdir(base):
        base = os.path.join(RAIZ, ".claude")
    alvos = []
    for pasta in ("agents", "skills"):
        p = os.path.join(base, pasta)
        for raiz, _dirs, arqs in os.walk(p) if os.path.isdir(p) else []:
            if "worktrees" in raiz:      # cópias temporárias de agente
                continue
            alvos += [os.path.join(raiz, a) for a in arqs if a.endswith(".md")]
    grade = os.path.join(base, "GRADE_INSTAGRAM.md")
    if os.path.exists(grade):
        alvos.append(grade)
    if not alvos:
        # 🪤 `.claude/` é gitignored (o repo é PÚBLICO), então em CI a pasta não
        # existe. Sem esta saída o guarda quebraria o build por AUSÊNCIA de
        # arquivo, que não é violação nenhuma. Ele vigia de verdade na máquina
        # onde os agentes e skills realmente rodam — que é onde a copy nasce.
        import pytest
        pytest.skip("sem .claude/ neste checkout (gitignored): nada a vigiar aqui")
    problemas = []
    for a in alvos:
        try:
            txt = io.open(a, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            continue
        for n, linha in _tem_promessa_antiga(txt):
            problemas.append("%s:%d %s" % (os.path.basename(a), n, linha))
    assert not problemas, (
        "fonte que gera copy NOVA ainda ensina a oferta antiga:\n  " +
        "\n  ".join(problemas))


def test_CONTROLE_o_guarda_REPROVA_mesmo():
    """🧪 Guarda que nunca reprova é pior que guarda nenhum."""
    assert _tem_promessa_antiga('cta = "Primeiro projeto grátis · ai.arq.br"')
    assert _tem_promessa_antiga("CTA padrão: 1º projeto grátis")


def test_CONTROLE_a_regra_escrita_na_NEGATIVA_nao_e_achado():
    """🪤 7 dos 8 arquivos que a busca apontou eram a REGRA, não a violação:
    'NUNCA escrever "1º projeto grátis"'. Sem esta trava o guarda acusaria o
    próprio conserto de 09/08 e viraria alarme que ninguém olha."""
    assert not _tem_promessa_antiga(
        '> 🚨 REGRA DURA DE COPY. NUNCA escrever "1º projeto grátis", "primeiro...')
    assert not _tem_promessa_antiga(
        '# a oferta antiga ("primeiro projeto grátis") valeu até 22/07/2026')
