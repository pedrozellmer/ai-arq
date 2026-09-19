# -*- coding: utf-8 -*-
"""A Central de E-mails diz o que VOLTOU, não só o que saiu.

🩸 19/09/2026 — item 12 da fila. A Central mostrava "N e-mails enviados" por
tipo e parava aí. Medido na base antes de escrever uma linha (90 dias, por
pessoa, só com a janela de 7 dias já fechada):

    tipo                pessoas    abriram projeto novo em 7 d
    retorno_30d            39                  0
    newsletter             64                  0
    calibracao             49                  0
    nudge_onboarding       13                  0
    nudge_cadastro         11                  0
    nps_relacional          7                  0

~184 pessoas nos tipos que falam com quem sumiu, ZERO projeto novo — e a casa
seguia mandando, porque a tela não contava essa metade.

🩸 E A REVISÃO DERRUBOU A PRIMEIRA VERSÃO DESTA TELA. O único número positivo
dela era CO-PRESENÇA, não retorno: `boas_vindas` marcava "72 de 95", e os 72
abriram o projeto DENTRO DE 1 HORA do envio (mediana 2,4 min), porque esse
e-mail sai justamente quando a pessoa acabou de entrar no site. O placar
estava certo e respondia outra pergunta. Conserto: a MEDIANA do intervalo vem
impressa e desmente o placar sozinha — sem limiar inventado, sem jogar dado
fora. Medianas reais em 19/09: boas_vindas 0,04 h · erro_trocar 0,03 h ·
complemento_pronto 0,21 h (tudo mesma visita) × proximo_projeto 106,8 h e
leu_sem_medir 144,6 h (retorno de verdade).

O que este arquivo protege, e por quê cada um já mordeu esta casa:

  1. 🪤 VAZIO ≠ FALHOU, e agora em TRÊS estados: a leitura falhou ("não sei"),
     a leitura foi bem e o tipo nunca saiu ("nunca saiu"), ou saiu fora da
     janela. Zero em qualquer um deles seria o defeito do `volume` de 31/08.
  2. 🪤 CAMPO AUSENTE ≠ CAMPO ZERO. `Number(null)||0` afirmaria um zero que
     ninguém mediu, com alarme e tudo.
  3. 🪤 JANELA ABERTA NÃO É FRACASSO: quem recebeu ontem vai em `aguardando`.
  4. 🪤 ZERO NO RASTRO NÃO É DIAGNÓSTICO: o rastro de site é cego pra 50 das
     125 pessoas, por isso o sinal é PROJETO NOVO e os invisíveis aparecem.
  5. 🪤 A TAXA-BASE SAI SEMPRE, inclusive zero — se só aparecesse quando > 0,
     sumiria justo das fichas onde a linha acusa.

🚫 Não cobre a SQL da RPC (a bancada não roda SQL) — cópia em
`migrations_pendentes/`.
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _jsbancada import funcao_js, motor  # noqa: E402

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ADMIN = os.path.join(_RAIZ, "admin.html")


def _fonte():
    return io.open(_ADMIN, encoding="utf-8").read()


def _const_js(nome):
    """A declaração da const, pra carregar no motor junto das funções."""
    src = _fonte()
    m = re.search(r"^const %s = \{.*?^\};" % re.escape(nome), src, re.S | re.M)
    assert m, "não achei a const %s no admin.html" % nome
    return m.group(0)


def _js(com_cartao=False):
    js = motor("true;")
    js.evaljs(_const_js("_EMAIL_PEDE_OUTRA_COISA"))
    for f in ("_numOuNulo", "_intervaloEmPalavra", "linhaRetornoDoEmail"):
        js.evaljs(funcao_js(f, _ADMIN))
    if com_cartao:
        for f in ("esc", "_emailBadge", "_emailCard"):
            js.evaljs(funcao_js(f, _ADMIN))
    return js


def _linha(r, lido="true", dias=90):
    return _js().evaljs("linhaRetornoDoEmail(%s, %s, %s)"
                        % (json.dumps(r), lido, dias))


# Retrato real do `retorno_30d` em 19/09: 39 pessoas, janela fechada, zero.
_SECO = {"kind": "retorno_30d", "volume_total": 39, "enviados": 39, "pessoas": 39,
         "janela_7d_fechada": 39, "aguardando_7d": 0, "projeto_7d": 0,
         "projeto_7d_mesma_visita": 0,
         "janela_14d_fechada": 32, "projeto_14d": 0, "projeto_antes_7d": 0,
         "sem_rastro_de_site": 25, "mediana_horas_ate_o_projeto": None}
# Retrato real do `boas_vindas`: o placar que parecia vitória — 72 de 72 na
# mesma visita.
_COPRESENCA = {"kind": "boas_vindas", "volume_total": 117, "pessoas": 113,
               "janela_7d_fechada": 95, "aguardando_7d": 18, "projeto_7d": 72,
               "projeto_7d_mesma_visita": 72,
               "janela_14d_fechada": 82, "projeto_14d": 61, "projeto_antes_7d": 1,
               "sem_rastro_de_site": 27, "mediana_horas_ate_o_projeto": 0.044}


def test_o_zero_de_verdade_aparece_e_vem_destacado():
    """39 pessoas, ninguém voltou: é ESTE número que decide se o e-mail continua."""
    out = _linha(_SECO)
    assert "0 de 39 abriram projeto novo em 7 dias" in out, out
    assert "text-amber-700" in out, "o zero seco saiu sem destaque: %s" % out
    assert "25 das 39 sem rastro de site" in out, (
        "os invisíveis sumiram, ou saíram sem o denominador — 'não enxergo' "
        "virou 'não voltou': %s" % out)
    assert "&#128200;" not in out, "seta de alta numa linha que marca zero: %s" % out


def test_O_PLACAR_QUE_ERA_CO_PRESENCA_SE_DESMENTE_NA_PROPRIA_LINHA():
    """🩸 O defeito que a revisão pegou: "72 de 95" parecia o melhor e-mail da
    Central. Os 72 abriram o projeto na mesma visita."""
    out = _linha(_COPRESENCA)
    assert "72 de 95 abriram projeto novo em 7 dias" in out, out
    assert "mediana 3 min depois do envio" in out, (
        "o intervalo não saiu: o placar volta a parecer retorno: %s" % out)
    assert "todos na mesma visita" in out and "não é retorno" in out, out
    assert "&#128200;" not in out, (
        "ícone de ALTA num número que é co-presença: %s" % out)


def test_MISTURA_meio_a_meio_nao_apaga_o_aviso_de_mesma_visita():
    """🩸 O segundo passe da revisão derrubou o primeiro conserto: com metade
    do grupo na mesma visita e metade uma semana depois, a MEDIANA cai no vão
    entre as duas populações (60 h) e o aviso sumia — com 36 casos de
    co-presença dentro. Quem decide é a contagem por pessoa."""
    out = _linha(dict(_COPRESENCA, projeto_7d=72, projeto_7d_mesma_visita=36,
                      mediana_horas_ate_o_projeto=60.02))
    assert "72 de 95 abriram projeto novo em 7 dias" in out, out
    assert "36 desses na mesma visita" in out, (
        "a mistura apagou o aviso de co-presença: %s" % out)
    assert "&#9201;" in out, "sem a marca de tempo, a mistura passa por retorno: %s" % out


def test_a_mediana_ausente_nao_leva_embora_o_aviso_de_mesma_visita():
    """O aviso vem da CONTAGEM; pendurá-lo na mediana o faria sumir junto."""
    out = _linha(dict(_COPRESENCA, mediana_horas_ate_o_projeto=None))
    assert "todos na mesma visita" in out, out


def test_retorno_de_verdade_NAO_leva_o_aviso_de_mesma_visita():
    """`proximo_projeto`: 2 de 35, mediana 106,8 h — 4,5 dias depois. Esse é o
    formato do retorno de verdade, e não pode vir marcado como mesma visita."""
    out = _linha(dict(_COPRESENCA, kind="proximo_projeto", janela_7d_fechada=35,
                      projeto_7d=2, projeto_7d_mesma_visita=0, projeto_antes_7d=29,
                      sem_rastro_de_site=12, mediana_horas_ate_o_projeto=106.805))
    assert "2 de 35 abriram projeto novo em 7 dias" in out, out
    assert "mediana 4,5 dias depois do envio" in out, out
    assert "mesma visita" not in out, out
    assert "29 já tinham aberto na semana anterior" in out, (
        "a taxa-base sumiu: 2 viraria prova de causa que ninguém mediu: %s" % out)


def test_a_taxa_base_sai_SEMPRE_inclusive_quando_e_zero():
    """🚨 Se a semana anterior só aparecesse quando > 0, sumiria exatamente das
    fichas onde a linha acusa — e o "0 de 39" perderia o que o inocenta."""
    out = _linha(_SECO)
    assert "nenhum tinha aberto na semana anterior" in out, (
        "com antes=0 a linha calou a taxa-base: %s" % out)


def test_CONTROLE_leitura_FALHADA_e_tipo_que_NUNCA_SAIU_sao_coisas_diferentes():
    """🪤 A feature nasceu da lição "vazio ≠ falhou" e a 1ª versão repetia o
    erro do outro lado: dizia "não sei" pra tipo que nunca teve envio."""
    falhou = _js().evaljs("linhaRetornoDoEmail(null, false, 90)")
    assert "não sei se trouxe alguém" in falhou, falhou
    nunca = _js().evaljs("linhaRetornoDoEmail(null, true, 90)")
    assert "nunca saiu" in nunca, nunca
    assert "não sei" not in nunca, nunca


def test_CONTROLE_campo_ausente_nao_vira_zero_afirmado():
    """🪤 `Number(undefined)||0` transformaria "não medi" em "0 de 0", com
    alarme. Falta um dos dois campos da conta → a ficha diz que não sabe."""
    for parcial in ({"kind": "x"},
                    dict(_SECO, projeto_7d=None),
                    dict(_SECO, janela_7d_fechada="n/d")):
        out = _linha(parcial)
        assert "não sei se trouxe alguém" in out, (parcial, out)
        assert "abriram projeto" not in out and "0 de 0" not in out, (parcial, out)


def test_a_taxa_base_AUSENTE_nao_vira_a_frase_de_que_ninguem_voltou():
    """🪤 O campo que vira FRASE é o mais perigoso de coalescer: sem
    `projeto_antes_7d`, `|| 0` escreveria "nenhum tinha aberto na semana
    anterior" — uma afirmação sobre número que ninguém mediu."""
    out = _linha(dict(_SECO, projeto_antes_7d=None))
    assert "semana anterior: não medida" in out, out
    assert "nenhum tinha aberto" not in out, out


def test_pessoas_AUSENTE_nao_vira_silencio_afirmado():
    """🪤 Com `|| 0`, `pessoas` ausente fazia a linha dizer "nenhum envio nos
    últimos 90 dias" mesmo com a janela cheia de gente."""
    out = _linha(dict(_SECO, pessoas=None))
    assert "nenhum envio nos últimos" not in out, out
    assert "0 de 39 abriram projeto novo" in out, out


def test_janela_ainda_aberta_NAO_conta_como_fracasso():
    """Quem recebeu ontem ainda pode voltar."""
    out = _linha(dict(_SECO, pessoas=6, janela_7d_fechada=0, aguardando_7d=6,
                      projeto_7d=0, sem_rastro_de_site=0))
    assert "janela ainda aberta" in out and "6 pessoas" in out, out
    assert "abriram projeto" not in out and "0 de 0" not in out, out


def test_tipo_sem_envio_na_janela_diz_isso_e_nao_zero():
    """Saiu no passado, nada nos últimos 90 dias: não é fracasso, é silêncio."""
    out = _linha(dict(_SECO, pessoas=0, janela_7d_fechada=0, aguardando_7d=0,
                      projeto_7d=0, sem_rastro_de_site=0))
    assert "nenhum envio nos últimos 90 dias" in out, out


def test_o_alarme_respeita_o_piso_inclusive_NA_BORDA():
    """🪤 Piso é a mínima que resolve. 10 pessoas acende, 9 não — e a borda é
    onde catraca escolhida no olho quebra (7ª vez nesta casa)."""
    dez = _linha(dict(_SECO, janela_7d_fechada=10, projeto_7d=0, sem_rastro_de_site=0))
    nove = _linha(dict(_SECO, janela_7d_fechada=9, projeto_7d=0, sem_rastro_de_site=0))
    assert "text-amber-700" in dez, dez
    assert "text-amber-700" not in nove, nove
    assert "0 de 9 abriram projeto novo" in nove, nove


def test_email_que_pede_OUTRA_COISA_nao_acende_alarme_e_diz_o_motivo():
    """🚨 `calibracao` (49 pessoas, 0 projetos) pede planilha revisada. Medir
    com a régua de projeto novo e acender alarme seria julgar pelo número
    errado — o erro que esta casa cometeu em 18/09 com a régua de cobrança."""
    out = _linha(dict(_SECO, kind="calibracao", janela_7d_fechada=49,
                      projeto_7d=0, sem_rastro_de_site=22))
    assert "0 de 49 abriram projeto novo" in out, out
    assert "text-amber-700" not in out, "alarme na régua errada: %s" % out
    assert "pede planilha revisada" in out, out


def test_concordancia_do_verbo_segue_quem_voltou():
    """Detalhe de português que o Pedro lê todo dia: 1 pessoa ABRIU."""
    um = _linha(dict(_SECO, janela_7d_fechada=12, projeto_7d=1,
                     mediana_horas_ate_o_projeto=30.0))
    assert "1 de 12 abriu projeto novo" in um, um
    assert "mediana 30 h depois do envio" in um, (
        "a faixa do meio de _intervaloEmPalavra nunca foi afirmada: %s" % um)
    umCego = _linha(dict(_SECO, sem_rastro_de_site=1))
    assert "1 das 39 sem rastro de site" in umCego, umCego


def test_o_intervalo_em_palavra_nas_TRES_faixas_e_nas_bordas():
    """🪤 Borda é onde catraca escolhida no olho quebra. 48 h muda de faixa; e
    intervalo menor que um minuto não pode virar "1 min" inventado."""
    js = _js()
    casos = [(0.004, "<1 min"), (0.044, "3 min"), (0.999, "60 min"),
             (1.0, "1 h"), (47.9, "48 h"), (48.0, "2,0 dias"), (144.648, "6,0 dias")]
    for h, esperado in casos:
        assert js.evaljs("_intervaloEmPalavra(%r)" % h) == esperado, (h, esperado)


def test_a_borda_de_UMA_HORA_nao_decide_sozinha_a_mesma_visita():
    """🪤 A decisão saiu de cima do escalar: mediana de 1,0 h com contagem
    zerada não marca mesma visita, e contagem > 0 marca mesmo com mediana alta."""
    alta = _linha(dict(_COPRESENCA, projeto_7d_mesma_visita=0,
                       mediana_horas_ate_o_projeto=1.0))
    assert "mesma visita" not in alta, alta
    baixa = _linha(dict(_COPRESENCA, projeto_7d_mesma_visita=72,
                        mediana_horas_ate_o_projeto=1.0))
    assert "todos na mesma visita" in baixa, baixa


def test_kind_que_bate_no_prototipo_nao_desliga_o_alarme():
    """🪤 Sem `hasOwnProperty`, um tipo chamado `constructor` acharia uma
    função na cadeia de protótipo, desligaria o âmbar e jogaria o código dela
    dentro do HTML."""
    out = _linha(dict(_SECO, kind="constructor"))
    assert "text-amber-700" in out, "o alarme foi desligado por um kind herdado: %s" % out
    assert "function" not in out.lower(), out


def test_CONTROLE_o_cartao_RODANDO_mostra_a_linha_do_retorno():
    """🪤 A 1ª versão deste guarda lia o FONTE atrás da chamada — ficava verde
    com a chamada comentada e vermelho numa refatoração inocente. Aqui o
    cartão é executado de verdade."""
    js = _js(com_cartao=True)
    ficha = {"key": "retorno_30d", "nome": "Volta pra cá", "grupo": "auto",
             "gatilho": "30 dias sem aparecer", "volume": 39, "retorno": _SECO}
    html = js.evaljs("_emailCard(%s, true, 90)" % json.dumps(ficha))
    assert "0 de 39 abriram projeto novo em 7 dias" in html, html[:400]
    sem = js.evaljs("_emailCard(%s, true, 90)"
                    % json.dumps(dict(ficha, retorno=None)))
    assert "nunca saiu" in sem, sem[:400]
    # A outra metade do elo: volume None tem que virar "desconhecido", não 0.
    caido = js.evaljs("_emailCard(%s, false, 90)"
                      % json.dumps(dict(ficha, volume=None, retorno=None)))
    assert "volume desconhecido" in caido, caido[:400]
    assert "0 emails enviados" not in caido, caido[:400]
    assert "não sei se trouxe alguém" in caido, caido[:400]


def test_CONTROLE_o_cartao_nao_pode_ser_passado_direto_pro_map():
    """🪤 `.map(_emailCard)` injeta o ÍNDICE no 2º argumento: o 1º cartão
    receberia lido=0 (falso) e o 2º lido=1. A tela tem que usar arrow.

    🩸 Este guarda reprovou o arquivo CORRETO na 1ª execução: o comentário que
    eu tinha acabado de escrever na tela diz, em português, "nunca
    `.map(_emailCard)`" — e o guarda leu a minha própria anotação. É a quinta
    vez nesta casa; por isso a busca é no código SEM comentário.
    """
    from _corpo import sem_comentarios_js
    src = sem_comentarios_js(_fonte())
    assert ".map(_emailCard)" not in src, (
        "alguém voltou a passar _emailCard direto pro map — o índice vira o "
        "parâmetro `lido` e o 1º cartão passa a mentir")
    assert "_emailCard(i, lido, dias)" in src


# ─────────────────────────────────────────────────────────────────────────────
#  O backend — a leitura que falha não pode virar zero
# ─────────────────────────────────────────────────────────────────────────────

def test_backend_leitura_que_falha_devolve_None_e_nao_dicionario_vazio(monkeypatch):
    """🚨 `{}` seria servido à tela como "nenhum tipo teve retorno"."""
    import main
    # 🪤 `_log_error` real chama `_supabase_insert` com urllib e escreveria no
    # error_log de PRODUÇÃO durante a bancada. Dublê aqui também.
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    for resposta in ((500, None), (200, None), (401, {"erro": "x"}), (200, [])):
        monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: resposta)
        main._AVISOS_COM_TETO.clear()
        assert main._email_retorno_por_tipo(90) is None, resposta


def test_backend_EXCECAO_na_leitura_tambem_vira_None(monkeypatch):
    """🪤 O `except` que ninguém exercita é o que estava inalcançável em 31/08.
    Aqui o dublê LEVANTA — que é o caminho que o comentário promete cobrir."""
    import main

    def _explode(*a, **k):
        raise RuntimeError("timeout no supabase")

    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_rest_service", _explode)
    main._AVISOS_COM_TETO.clear()
    assert main._email_retorno_por_tipo(90) is None


def test_backend_entrega_o_retorno_indexado_por_tipo(monkeypatch):
    import main
    payload = {"dias": 90, "por_tipo": [
        {"kind": "retorno_30d", "janela_7d_fechada": 39, "projeto_7d": 0},
        {"kind": "boas_vindas", "janela_7d_fechada": 95, "projeto_7d": 72}]}
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (200, payload))
    lido = main._email_retorno_por_tipo(90)
    tipos = {t["kind"]: t for t in lido["por_tipo"]}
    assert tipos["retorno_30d"]["projeto_7d"] == 0
    assert tipos["boas_vindas"]["projeto_7d"] == 72


def test_backend_corta_cedo_em_vez_de_pendurar_a_tela(monkeypatch):
    """🪤 Sem `timeout`, esta chamada herdaria os 15 s do padrão e a Central
    ficaria pendurada. A ficha já sabe dizer "não sei": cortar é melhor."""
    import main
    visto = {}

    def _falso(metodo, rota, body=None, *a, **k):
        visto.update(rota=rota, body=body, timeout=k.get("timeout"))
        return (200, {"dias": 90, "por_tipo": []})

    monkeypatch.setattr(main, "_supa_rest_service", _falso)
    main._email_retorno_por_tipo(90)
    assert visto["rota"] == "rpc/admin_email_retorno", visto
    assert visto["timeout"] and visto["timeout"] <= 5, visto
    # 🪤 E manda só `dias`: o `excluir` foi tirado porque mandava UM endereço e
    # não removia nada — quem sabe quem é da casa é a régua do banco.
    assert visto["body"] == {"dias": 90}, visto


def test_backend_o_aviso_de_falha_tem_TETO_e_nao_entope_o_painel(monkeypatch):
    """🪤 Sem teto, cada abertura da tela grava uma linha nova em `error_log` —
    e afoga o painel de 40 linhas que o Pedro usa pra achar erro de verdade."""
    import main
    gravados = []
    monkeypatch.setattr(main, "_log_error",
                        lambda *a, **k: gravados.append(a[1] if len(a) > 1 else "?"))
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (500, None))
    main._AVISOS_COM_TETO.clear()
    for _ in range(5):
        main._email_retorno_por_tipo(90)
    assert len(gravados) == 1, (
        "a falha gravou %d avisos em 5 leituras seguidas" % len(gravados))


def test_backend_o_teto_nao_engole_uma_causa_DIFERENTE(monkeypatch):
    """🪤 Teto só por stage calaria a segunda falha — e a causa nova é
    justamente o que o Pedro precisaria ver."""
    import main
    gravados = []
    monkeypatch.setattr(main, "_log_error",
                        lambda *a, **k: gravados.append(a[1] if len(a) > 1 else "?"))
    main._AVISOS_COM_TETO.clear()
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (500, None))
    main._email_retorno_por_tipo(90)
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (401, None))
    main._email_retorno_por_tipo(90)
    assert len(gravados) == 2, (
        "a segunda causa foi engolida pelo teto: %s" % gravados)


def test_a_rota_entrega_retorno_e_volume_na_MESMA_leitura(monkeypatch):
    """🚨 O elo entre a RPC e a tela não tinha guarda nenhum: se a chave
    `retorno` sumisse da ficha, os outros guardas seguiriam verdes e a Central
    diria "não sei" em TODAS as fichas, para sempre.
    E o volume agora sai da mesma resposta — antes a rota puxava a tabela
    `email_sent_log` inteira pela rede só pra contar."""
    import main
    idas = []

    def _falso(metodo, rota, body=None, *a, **k):
        idas.append(rota)
        return (200, {"dias": 90, "por_tipo": [
            {"kind": "retorno_30d", "volume_total": 39, "pessoas": 39,
             "janela_7d_fechada": 39, "projeto_7d": 0},
            {"kind": "tipo_orfao_do_motor", "volume_total": 7, "pessoas": 7,
             "janela_7d_fechada": 7, "projeto_7d": 1}]})

    monkeypatch.setattr(main, "_require_admin", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_rest_service", _falso)
    saida = main.admin_email_catalog(request=None)
    fichas = {i["key"]: i for i in saida["items"]}
    assert saida["retorno_lido"] is True and saida["volume_lido"] is True
    assert fichas["retorno_30d"]["retorno"]["projeto_7d"] == 0
    assert fichas["retorno_30d"]["volume"] == 39
    assert fichas["tipo_orfao_do_motor"]["orfao"] is True, (
        "tipo que o motor manda e o catálogo não conhece sumiu da Central")
    assert len(idas) == 1, "a rota foi ao banco %d vezes: %s" % (len(idas), idas)


def test_a_rota_com_a_RPC_fora_do_ar_diz_NAO_SEI_em_toda_ficha(monkeypatch):
    """E nunca zero — nem no retorno, nem no volume. E avisa que a lista de
    tipos fora do catálogo pode estar incompleta, em vez de deixar a ausência
    passar por "não existe nenhum"."""
    import main
    monkeypatch.setattr(main, "_require_admin", lambda *a, **k: None)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (503, None))
    main._AVISOS_COM_TETO.clear()
    saida = main.admin_email_catalog(request=None)
    assert saida["retorno_lido"] is False and saida["volume_lido"] is False
    assert saida["orfaos_lidos"] is False, (
        "a lista de órfãos sumiu calada quando a leitura caiu")
    assert saida["items"], "a Central ficou sem fichas quando a RPC caiu"
    for ficha in saida["items"]:
        assert ficha.get("retorno") is None, ficha["key"]
        assert ficha.get("volume") is None, ficha["key"]


def test_a_rota_com_resposta_SEM_por_tipo_nao_finge_que_contou(monkeypatch):
    """🪤 200 com dict sem `por_tipo` faria toda ficha imprimir "0 e-mails
    enviados" — o defeito de 31/08 entrando por outra porta."""
    import main
    monkeypatch.setattr(main, "_require_admin", lambda *a, **k: None)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_rest_service",
                        lambda *a, **k: (200, {"dias": 90}))
    saida = main.admin_email_catalog(request=None)
    assert saida["volume_lido"] is False, "dict sem `por_tipo` passou por leitura boa"
    for ficha in saida["items"]:
        assert ficha.get("volume") is None, ficha["key"]


def test_a_rota_continua_sendo_SO_do_admin(monkeypatch):
    """🚨 Nenhum guarda provava isso: apagar `_require_admin(request)` da rota
    deixava a bancada inteira verde, com a Central aberta pra quem pedisse."""
    import main
    chamou = []

    def _barra(*a, **k):
        chamou.append(True)
        raise main.HTTPException(status_code=403, detail="não é admin")

    monkeypatch.setattr(main, "_require_admin", _barra)
    monkeypatch.setattr(main, "_supa_rest_service",
                        lambda *a, **k: (200, {"dias": 90, "por_tipo": []}))
    try:
        main.admin_email_catalog(request=None)
    except main.HTTPException as e:
        assert e.status_code == 403
    else:
        raise AssertionError("a rota respondeu sem passar pelo porteiro")
    assert chamou, "a rota nem chamou `_require_admin`"
