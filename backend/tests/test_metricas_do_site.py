# -*- coding: utf-8 -*-
"""O painel que responde "isso é normal?" sem eu ter que medir na mão.

🎯 29/08/2026, pedido do Pedro. Ele perguntou TRÊS vezes na mesma semana se o
site tinha caído do Google. Cada resposta custou meia hora de consulta — e nas
duas primeiras **eu respondi errado**:

  1ª  "a visita está normal, 211 únicos na quinta" — aquele dia foi **76% ROBÔ**
      (1.129 de 1.475 requisições, vindas de 16 endereços). O contador de
      "únicos" do Cloudflare conta robô.
  2ª  "21 downloads do memorial hoje, tem gente usando" — eram 5 endereços, e um
      sozinho fez 16 (faixa da Azure, com user-agent de Edge).

🔑 O problema nunca foi falta de dado. Era eu reinventando o critério de "quem é
gente" a cada pergunta — o mesmo erro que a rota `/api/admin/selo-historico` já
documenta: *"critério à mão diverge; reimplementar cria a quarta versão"*.

🪤 E o Cloudflare só guarda o detalhe (IP, navegador) por **7 DIAS**. Sem gravar
diariamente, "isso é normal?" é impossível de responder olhando pra trás — a
comparação que faltava.
"""
import io
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import metricas_site as ms  # noqa: E402

_MAIN = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _dias(pares):
    """[(data, ips_gente)] → série no formato que o veredito espera."""
    return [{"dia": d, "ips_gente": n} for d, n in pares]


# ───────────────────── o veredito compara DIA COM DIA IGUAL ──────────────────

def test_compara_sabado_com_sabado_e_nao_com_a_media():
    """🚨 O erro que eu quase cometi ao vivo: olhei a sexta (50 endereços)
    contra a quinta (97) e quase disse "caiu pela metade". A sexta ANTERIOR
    tinha dado 51 — não tinha caído nada.

    Fim de semana cai sempre. Comparar com a média geral inventa uma queda.
    """
    # 4 sábados entre 51 e 72; o 5º sábado com 62 é normal
    sabados = _dias([("2026-08-01", 60), ("2026-08-08", 72),
                     ("2026-08-15", 55), ("2026-08-22", 51),
                     ("2026-08-29", 62)])
    v = ms.veredito(sabados)
    assert v["status"] == "normal", v
    # o MESMO 62 seria baixo entre quintas de 88 a 95
    quintas = _dias([("2026-08-06", 90), ("2026-08-13", 88),
                     ("2026-08-20", 95), ("2026-08-27", 62)])
    assert ms.veredito(quintas)["status"] == "abaixo", (
        "62 numa quinta de 88–95 tem que acender a luz; num sábado de 51–72 não")


def test_diz_NAO_SEI_quando_nao_tem_com_o_que_comparar():
    """🪤 Veredito com 1 ponto de comparação é chute com cara de medida — e
    chute com cara de medida foi o que fez o Pedro perder a manhã três vezes.
    Preciso de 3 dias iguais antes de opinar."""
    v = ms.veredito(_dias([("2026-08-22", 51), ("2026-08-29", 29)]))
    assert v["status"] == "nao_sei", v
    assert "preciso de 3" in v["frase"]


def test_acende_a_luz_quando_cai_de_verdade():
    sabados = _dias([("2026-08-01", 60), ("2026-08-08", 72),
                     ("2026-08-15", 55), ("2026-08-29", 12)])
    v = ms.veredito(sabados)
    assert v["status"] == "abaixo" and "Vale olhar" in v["frase"], v


def test_as_frases_saem_em_portugues_correto():
    """🪤 Errei a concordância TRÊS vezes montando a frase por pedaços: "a menor
    sábado", "acima DA MAIS CHEIO", "acima D MAIS CHEIO". Frase torta faz o
    painel parecer descuidado, e painel descuidado não é lido."""
    sab = _dias([("2026-08-01", 60), ("2026-08-08", 72), ("2026-08-15", 55)])
    qui = _dias([("2026-08-06", 90), ("2026-08-13", 88), ("2026-08-20", 95)])
    frases = [ms.veredito(sab + _dias([("2026-08-29", n)]))["frase"] for n in (12, 62, 99)]
    frases += [ms.veredito(qui + _dias([("2026-08-27", n)]))["frase"] for n in (12, 92, 200)]
    for f in frases:
        for torto in ("a menor sábado", "as outras sábados", "acima d mais",
                      "da mais cheio", "do mais cheia", "a mais fraco",
                      "o mais fraca", "d mais"):
            assert torto not in f, "frase torta: %r em %r" % (torto, f)


# ─────────────────── a separação de quem é robô, nós e o resto ───────────────

def test_o_IP_da_nossa_maquina_nao_conta_como_movimento():
    """🚨 Pergunta literal do Pedro: "verifica se essas visitas não são de fato
    a gente entrando". Sem isto, um dia de trabalho pesado no site vira
    'movimento' e a série mente pro lado otimista.

    📌 A lista de VERDADE mora no banco (`ips_da_casa`) e se enche sozinha. O
    que se testa aqui é a rede de segurança: se o banco não responder, o
    coletor não pode voltar a contar a gente como público.
    """
    assert "189.62.150.142" in ms._IPS_DE_EMERGENCIA, (
        "a rede de segurança ficou vazia — se o banco falhar, nossas visitas "
        "voltam a contar como público")


def test_a_lista_do_BANCO_manda_e_a_de_emergencia_so_complementa():
    """🔑 O desenho: banco primeiro, código como rede. Se alguém inverter, um
    IP novo do Pedro (celular, ou o residencial depois de rotacionar) deixaria
    de ser excluído — que é exatamente o que ele pediu pra não acontecer."""
    fonte = io.open(os.path.join(_BACKEND, "metricas_site.py"), encoding="utf-8").read()
    i = fonte.find("def coletar")
    corpo = fonte[i:i + 1600]
    assert "ips_da_casa or ()" in corpo and "_IPS_DE_EMERGENCIA" in corpo, (
        "o coletor parou de juntar a lista do banco com a de emergência")


def test_navegador_desconhecido_e_robo():
    for nav in ("Unknown", "BingBot", "python-requests", "curl/8.0", "GPTBot"):
        assert ms._e_robo(nav), "%r devia contar como robô" % nav


def test_CONTROLE_navegador_de_verdade_NAO_e_robo():
    """🧪 O outro lado. Sem isto, um classificador que devolve True sempre
    passaria no teste de cima e a série mostraria zero movimento pra sempre."""
    for nav in ("Chrome", "Safari", "MobileSafari", "Edge", "Firefox", "Opera"):
        assert not ms._e_robo(nav), "%r é navegador de gente" % nav


def test_o_nome_da_coluna_NAO_promete_pessoa():
    """🪤 `req_gente` é TETO, não medida: robô disfarçado de navegador cai nele
    (o endereço da Azure que baixou o memorial 16× com user-agent Edge conta
    aqui). Chamar de `pessoas` convidaria a próxima leitura preguiçosa — que foi
    exatamente o meu erro do "21 downloads"."""
    fonte = io.open(os.path.join(_BACKEND, "metricas_site.py"), encoding="utf-8").read()
    assert "req_gente" in fonte
    assert "TETO, não medida" in fonte, (
        "sumiu o aviso de que esse número é teto e não contagem de pessoas")


# ────────────────── o instrumento tem que DIZER quando está morto ────────────

def test_sem_token_o_tick_GRITA_em_vez_de_gravar_zero():
    """🚨 A lição que mais se repetiu esta semana: instrumento que não mede tem
    que dizer que não mediu. Série vazia e site sem movimento têm a mesma cara.
    """
    i = _MAIN.find('@app.post("/api/metricas/tick")')
    assert i > 0, "sumiu o tick das métricas"
    bloco = _MAIN[i:i + 2200]
    assert "sem_token" in bloco, "não distingue 'sem token' de 'sem movimento'"
    assert 'severity="error"' in bloco, (
        "a falta do token entra como info e some no meio do log")


def test_o_painel_avisa_quando_a_coleta_esta_desligada():
    i = _MAIN.find('@app.get("/api/admin/metricas")')
    assert i > 0, "sumiu a rota do painel"
    bloco = _MAIN[i:i + 1800]
    assert "token_configurado" in bloco and "aviso" in bloco, (
        "o painel não diz se a coleta está viva — série parada passaria por "
        "site sem movimento")


def test_o_tick_reescreve_os_ultimos_dias_e_nao_so_ontem():
    """🪤 O Cloudflare só guarda o detalhe por ~7 dias. Se o tick falhar um dia,
    aquele pedaço some PRA SEMPRE — a menos que a próxima rodada reescreva."""
    i = _MAIN.find('@app.post("/api/metricas/tick")')
    bloco = _MAIN[i:i + 2200]
    assert "for atras in (1, 2, 3)" in bloco, (
        "o tick voltou a gravar só um dia — uma falha de 24h vira buraco "
        "permanente na série")


def test_falha_ao_contar_projetos_vira_NULO_e_nao_zero():
    """🪤 Zero é uma AFIRMAÇÃO ("não teve projeto"); falha de rede não pode
    virar afirmação. Mesmo erro do smoke que dizia "0 projetos" com o servidor
    respondendo 502."""
    i = _MAIN.find("def _contar_do_dia")
    bloco = _MAIN[i:i + 1500]
    assert "return None" in bloco, "falha de contagem volta a virar zero"
    assert "and=" in bloco, (
        "o filtro de faixa de data saiu do formato do PostgREST — com duas "
        "chaves `created_at` a segunda apaga a primeira e conta o histórico todo")


# ────────── "tira sempre o meu acesso e o seu" (Pedro, 29/08) ────────────────

def test_a_lista_de_IPS_da_casa_vem_do_BANCO_e_nao_do_codigo():
    """🚨 Pedido literal do Pedro. A 1ª versão era uma lista FIXA com um IP só —
    e isso envelhece calado: IP residencial rotaciona e o celular dele é outro
    endereço. Em um mês a lista estaria errada e a estatística voltaria a contar
    a gente como público, sem ninguém perceber."""
    assert "_ips_da_casa" in _MAIN, "sumiu a leitura da lista do banco"
    i = _MAIN.find("def _ips_da_casa")
    corpo = _MAIN[i:i + 1400]
    assert "ips_da_casa" in corpo, "não consulta a tabela"
    assert "days=90" in corpo, (
        "sumiu o esquecimento por tempo — IP devolvido pro pool da operadora "
        "ficaria excluído pra sempre e apagaria visita de cliente")


def test_o_tick_USA_a_lista_ao_coletar():
    """🪤 Guarda do CALL SITE: a função existir não adianta se o tick não passar
    a lista adiante. Já passei verde duas vezes testando função e não chamador."""
    i = _MAIN.find('@app.post("/api/metricas/tick")')
    bloco = _MAIN[i:i + 2400]
    assert "_ips_da_casa()" in bloco, "o tick não lê a lista"
    assert "ips_da_casa=" in bloco, "lê a lista mas não repassa pro coletor"


def test_o_IP_real_vem_do_cabecalho_do_cloudflare():
    """🪤 Atrás do Cloudflare, `request.client.host` é o IP da BORDA, igual pra
    todo mundo. Registrar ele excluiria o Cloudflare inteiro da estatística —
    ou seja, zeraria a contagem."""
    i = _MAIN.find("def admin_marcar_meu_ip")
    corpo = _MAIN[i:i + 1400]
    assert "cf-connecting-ip" in corpo, (
        "não lê o cabeçalho do Cloudflare — registraria o IP da borda")


def test_a_rota_de_marcar_IP_exige_admin():
    """🔒 Sem isso, qualquer visitante poderia se auto-excluir da contagem."""
    i = _MAIN.find("def admin_marcar_meu_ip")
    assert "_require_admin(request)" in _MAIN[i:i + 700]


def test_o_coletor_aceita_a_lista_e_nao_so_a_constante():
    """🧪 Controle: a assinatura tem que receber a lista, senão o parâmetro do
    tick cai no vazio e a exclusão volta a ser o IP fixo."""
    import inspect
    assert "ips_da_casa" in str(inspect.signature(ms.coletar)), (
        "coletar() não recebe mais a lista — o tick passa e ela é ignorada")


# ──────────────────── a tela existe e está ligada de verdade ─────────────────

def test_a_tela_do_painel_tem_TODOS_os_campos_que_o_JS_procura():
    """🪤 A memória do projeto guarda um caso de aba que existia no HTML e não
    tinha botão no menu — código vivo, tela morta. Aqui o risco é o irmão dele:
    o JS escrever num id que o HTML não tem, e o painel ficar em branco sem
    erro nenhum no console."""
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    html = io.open(os.path.join(raiz, "admin.html"), encoding="utf-8").read()
    assert "carregarMovimentoDoSite" in html, "a função do painel sumiu"
    assert html.count("carregarMovimentoDoSite") >= 2, (
        "a função existe mas ninguém CHAMA ela — painel morto")
    for campo in ("mov-frase", "mov-farol", "mov-barras", "mov-alerta",
                  "mov-saude", "mov-cadastros", "mov-projetos"):
        assert ('id="%s"' % campo) in html, "o JS escreve em #%s e o HTML não tem" % campo
        assert ("'%s'" % campo) in html, "#%s existe no HTML e ninguém preenche" % campo


def test_a_tela_avisa_quando_a_coleta_esta_desligada():
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    html = io.open(os.path.join(raiz, "admin.html"), encoding="utf-8").read()
    i = html.find("carregarMovimentoDoSite")
    bloco = html[i:i + 3000]
    assert "coleta" in bloco and "aviso" in bloco, (
        "a tela não mostra o aviso de coleta desligada — série parada ficaria "
        "igual a site sem movimento")


def test_a_tela_diz_que_o_numero_e_TETO_e_nao_pessoas():
    """🪤 Foi lendo um número desses como 'pessoas' que eu errei duas vezes hoje.
    O rodapé da tela tem que desarmar isso pra quem olha."""
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    html = io.open(os.path.join(raiz, "admin.html"), encoding="utf-8").read()
    i = html.find('id="mov-barras"')
    assert "teto" in html[i:i + 900].lower(), (
        "sumiu o aviso de que a barra é teto e não contagem de pessoas")
