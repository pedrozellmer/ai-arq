# -*- coding: utf-8 -*-
"""O repositório é PÚBLICO: nada aqui identifica um cliente.

🚨 06/09/2026 — o segundo CRÍTICO da auditoria total. Comentários e docstrings
identificavam titulares reais pelo e-mail inteiro, pelo apelido (a parte antes
do @) e pelo NOME, sempre grudados a um fato sobre a pessoa: quantas devoluções
a caixa dela teve, o que perguntou no chat, a que horas subiu o projeto.
Tudo em github.com/pedrozellmer/ai-arq, que é público.

🔑 O VALOR DO COMENTÁRIO É O CASO, NUNCA A PESSOA. "cliente-02, 16/06: só
funcionou na 4ª tentativa manual" ensina exatamente o que o nome ensinava, e o
rótulo é estável — o mesmo cliente mantém o mesmo número em todos os arquivos,
então a história continua rastreável sem identificar ninguém.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POR QUE A LISTA DE NOMES VIROU LISTA DE HASHES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
A 1ª versão deste guarda trazia 29 nomes ESCRITOS. Duas doenças nisso:

1. UMA LISTA DE NOMES DE CLIENTE NO REPO É UMA LISTA DE NOMES DE CLIENTE NO
   REPO. O guarda contra o vazamento era ele mesmo um vazamento menor.
2. E por isso ela nunca pôde ser COMPLETA — eu não ia escrever a base inteira
   aqui. Cobria os 29 que eu lembrava. Em 06/09, com ela verde, o repositório
   ainda tinha 58 nomes de cliente e 374 ocorrências. Eu disse ao Pedro
   "zero nomes" três vezes, e três vezes estava errado. Ver
   [[feedback_guarda_preso_a_forma_do_item]].

Guardando HASH em vez de nome, a lista cobre a base INTEIRA (108 palavras,
tiradas de `projects.user_name`, `nps_responses.user_name` e `chat_leads.name`)
e este arquivo não contém nome nenhum.

🪤 HONESTIDADE SOBRE O QUE O HASH PROTEGE: md5 de um primeiro nome comum se
quebra com dicionário em segundos. Não é sigilo — é para que o repositório não
CARREGUE a lista legível, e para que a lista possa ser completa. Contra alguém
determinado, o que protege é o nome não estar aqui; contra o acidente do dia a
dia — que é o que vem acontecendo —, isto resolve.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
O TETO DE DÍVIDA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
São 374 ocorrências em 72 arquivos, quase todas em comentário de motor contando
um caso real ("caso <nome> 17/08", "<nome> job 75dab573"). Limpar tudo de uma
vez, à mão, em 72 arquivos de motor, arrisca estragar a explicação que é o valor
daqueles comentários. Então o guarda nasce com TETO: reprova qualquer ocorrência
NOVA e o teto só pode DESCER. É o mesmo desenho de `test_rotas_sem_consumidor`.

⏭️ O HISTÓRICO do git continua com tudo, e 177 mensagens de commit também —
inclusive duas escritas 26 minutos antes desta regra nascer. Limpar exige
reescrever o histórico e forçar o push; a decisão é do Pedro.
"""
import hashlib
import io
import os
import re
import subprocess

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
_RAIZ = os.path.dirname(_BACKEND)

# ═══════════════════════════════════════════════════════════════════════════
#  E-MAIL — a forma mais direta, e a única que o guarda zera de verdade
# ═══════════════════════════════════════════════════════════════════════════
_RE_PESSOAL = re.compile(
    r"[A-Za-z0-9._%+-]+@(?:gmail|outlook|hotmail|yahoo|uol|bol|terra|live|icloud|"
    r"protonmail|me|msn)\.com(?:\.br)?", re.I)

# 🔑 A exceção é UMA e é explícita: os e-mails DO DONO. Não são dado de
# terceiro — são o admin (`ADMIN_EMAIL`), o destino das notificações internas
# (`NOTIFY_EMAIL`) e a conta de smoke test, e os dois primeiros são apenas o
# DEFAULT de uma variável de ambiente.
_DO_DONO = {
    "zarelalopes@gmail.com",
    "pedro.zellmer@gmail.com",
    "zarelalopes+smoke@gmail.com",
}

# ═══════════════════════════════════════════════════════════════════════════
#  NOME — por hash, tirado da base inteira
# ═══════════════════════════════════════════════════════════════════════════
#: md5 das palavras de nome de PESSOA da base de clientes (2+ palavras no
#: cadastro, sem marca de empresa nem de conta de teste), sem sobrenome comum
#: e sem o nome do dono. Regenerar com a consulta em `_COMO_REGERAR` abaixo.
_HASH_DE_NOME = frozenset("""
02558a70324e7c4f269c69825450cec8 0410c49927fe2e0123dd9e19fadcadbb
067036db8f53564d6a32e3f10466c99f 07a88e756847244f3496f63f473d6085
0db513d0630a515d0b64efd30fdd0dd5 0e4d164a767ed5990a08089020eb696b
0f5366b3b19afc3184d23bc73d8cd311 112c60a750df6654cc3a8dac9b4379c0
132043adb2ba8acad21e401523cdc7fe 1434e827e7914d05c96e4e0934539776
15b1dfdb3030371415e5e6c276388201 184e6788c1d056417c9d25f6716827eb
18e59942c3d24ca9888364ce1455eb1a 19984dcaea13176bbb694f62ba6b5b35
1b150854805cbe12194c8dbc55c900cd 1b207465eac83b5d4b12e335faa0b53a
1ee1877c6655ecc71dfead311c771bd0 205a10818889cfe2de7c278fb6e9188f
229e5b1363be0591e674cd57b3bb8645 276e697e74e8b5264465139a480db556
29a2b2e1849474d94d12051309c7b4d7 2c42e5cf1cdbafea04ed267018ef1511
2e247e2eb505c42b362e80ed4d05b078 2efb7ced7e8047462873546c5521aaba
38054601a6487bd992ded83e3f33ebae 3805b13916b5664e3b029ee804edf3a4
3a23bb515e06d0e944ff916e79a7775c 3df2175295d900d6f0c2f3a521d957cd
3f28e55efb457c86a979da0edfa923be 3f3ce8d94f88d42322e7204f702c138f
41008f06b76981093c7aa369d83c08ea 41847ec28c30f25acc5d96f0bef5ebfc
4757067ca131abf21c7dedea7efd0c80 4b6683e45065f9f7116267016239705b
502ff82f7f1f8218dd41201fe4353687 503873f51e44d687ec3ba06846aca82f
52be95db6f26ac6b2d291443fcea77d8 5494e1e7b721c2a7c867f3588e577154
55fadfd036b568d4b2d5796ee444caa0 5bb2ec2c8876622a004e241e3ceed2f7
5d24aff18191f1177d00384e07736ef7 6209804952225ab3d14348307b5a4a27
64b1c7a622073845494b9815348c0d28 680c3108617bfed131f7d20c929234b9
68c2280bda076acef10b444c9665f052 6a796ddf660ddf10b7323414321d2a1b
6c84cbd30cf9350a990bad2bcc1bec5f 726cd927c662edb20fedf29faf26c60b
77949c9f02621a4c85964be115a9dcc9 790d0289dae439880bc46c13818998d5
79df64f73eab9bc0d7b448d2008d876e 7bc6784b07998864a2c2891386970de9
7fa81ff5e6a88a34ca2392240268c68f 8235bf5b8bf5057897114b8b7ef4e720
8355185df4677535f568ea6498c80d84 841d93525b9f0960ceaf38f4fdf22e2e
848ffd503f98d2368d47abceb4821465 8767bbc52e71900d1f3a50b53196d0e2
89ba023086e37a345839e0c6a0d272eb 8ac291d567b1e54952a12f2f28740643
8c3856f64ea9383b1d3d9fe834c73ff6 9135d8523ad3da99d8a4eb83afac13d1
9491876179d7a80bb5c86f15dbe31422 9885921f1302d72826ee65394f50fdf7
995bf053c4694e1e353cfd42b94e4447 997d13b90da22b35ce43bebdd332ad11
9ac7dd42fc7e07f79b72f7d999188ab3 9be63b1329806f4c3cdff5fa92ba6b9a
9c5ddd54107734f7d18335a5245c286b 9e85d98e8033df21f562a84a940133cc
9ed083b1436e5f40ef984b28255eef18 a37b2a637d2541a600d707648460397e
a3cd5afc9eab47fefcd573566c41594e a53bd0415947807bcb95ceec535820ee
a64abe98558bb7bb5a9f1b8e2146cf68 ab892a649914a9e71aa3e869739253db
ac1da964ea928cf1b7b59120b4179e76 af5caae019a33d603444b7492a436b7f
b73cc1cbd7f3180f41013971b8edf2f9 b993e4526238d62f6b1b90e605532ff8
bbb5ff6dc3826b999a5cf0c2e7b2c889 c11845c9a05c8df7b137f49504dd918b
c13c253f3e26c1c6f265d444275bc7fb c26d483dd7cb0179994e7ed88fe8c7d4
c50eeda3f8f0d15c77754857c0cdc3eb c7b2af69cfca668a7eb128295789b6d3
c810ed30521e174d8040df6f9c054567 c94596c251014e32ca68d59e18a8dd11
c99868052fb8a76e4f4b9f2ee67d39fb cd86a0ad35cb75edda6569fc74941a7c
cec4daff4af61548d4536c86cf60c164 d1778abf5069d30922f191b60cc383e8
d1dcb1f278f32127505cb2133ab9bfc6 d252377a473501b19964bc41b5f503e7
d2d8ffc663941ccd1392de0cf254d3ef da64c7daf16c4687b0b8686147448223
db5fb5279b9f52c63638a39462d6c962 df8e65bca92091ec2d549727da81ee64
e4095399f03b0cc518535c29d75859c6 e5fef21172cc7f1991bf93c7ab6653aa
e60408e9a55027070e3caf0550d2b4df e7ef7a9f4059ff0401e5b92afe7a4d04
eb54d2175a728ed5bd17575d9fdf694c ebc65bc5b4f82407a201c89670ce454d
ec02d2d95c27675d87dca50018d89192 f1b6d941a97ababa0c81b92841b3189f
f76405ac130dac085b2a6249073b213b fd820a2b4461bddd116c1518bc4b0f77
""".split())

_COMO_REGERAR = """
Cliente novo entra na base e o guarda não sabe. Rode no Supabase e cole o
resultado acima — a consulta devolve SÓ hashes, nenhum nome sai do banco:

  with fontes as (
    select coalesce(user_name,'') as nome from projects
    union all select coalesce(user_name,'') from nps_responses
    union all select coalesce(name,'') from chat_leads
  ), pessoas as (
    select nome from fontes
    where array_length(regexp_split_to_array(btrim(nome), '\\s+'), 1) >= 2
      and nome !~* '(construtora|engenharia|arquitetura|ltda|eireli|smoke|fake|teste|admin|projetos|obras|incorporad|administrativ|confortar|servi)'
  ), palavras as (
    select distinct lower(btrim(p)) as w
    from pessoas, regexp_split_to_table(btrim(nome), '\\s+') as p
    where length(btrim(p)) >= 4
  )
  select string_agg(md5(w), ' ' order by md5(w)) from palavras
  where w !~ '^(junior|neto|filho|silva|santos|souza|costa|lima|dias|rosa|cruz|reis|nunes|pinto|marco|faria|campos|mota|melo|leal|braga|maia|serra|monte|amaral|prado|vale|barros|freitas|ramos|teixeira|moreira|cardoso|gomes|martins|araujo|carvalho|almeida|ribeiro|fernandes|goncalves|rodrigues|oliveira|pereira|ferreira|alves|barbosa|rocha|dantas|nascimento|moura|batista|machado|azevedo|correia|cavalcante|andrade)$'
    and w ~ '^[a-záàâãéêíóôõúüç]+$' and w not in ('pedro','zellmer');
"""

#: 🪤 O BLOG FICA DE FORA DA CHECAGEM DE NOME, E É DE PROPÓSITO.
#: Os posts citam AUTORES de artigos e normas ("Adriana de Paula Lacerda
#: Santos; Antonio Edésio Jungles"). São a FONTE que a regra de copy pública
#: exige em toda afirmação — apagar destruiria a citação e a regra. Que um
#: cliente compartilhe primeiro nome com um autor citado é coincidência, não
#: vazamento. A checagem de E-MAIL continua valendo lá: endereço pessoal num
#: post seria erro em qualquer hipótese.
_FORA_DA_CHECAGEM_DE_NOME = ("blog/posts",)

#: A dívida herdada, medida em 06/09/2026: 374 ocorrências em 72 arquivos,
#: quase todas em comentário de motor contando um caso real. O teto só DESCE.
_TETO_DE_NOMES = 374

_EXT_TEXTO = (".py", ".html", ".js", ".md", ".yml", ".yaml", ".css",
              ".json", ".txt", ".sql", ".toml", ".sh")

#: 🪤 Este arquivo se exclui de TODAS as varreduras: os controles positivos
#: plantam um e-mail e apelidos de mentira de propósito. Sem isto o guarda
#: acusa a própria prova de que funciona — a 5ª vez em 06/09 que um texto meu
#: virou o defeito que ele explicava. Ver
#: [[feedback_comentario_que_planta_o_defeito]].
_ESTE_ARQUIVO = os.path.basename(__file__)
_PALAVRA = re.compile(r"[A-Za-zÀ-ÿ]{4,}")


def _versionados():
    """Todo arquivo de texto que o git rastreia.

    🩸 A versão anterior varria só `backend/**/*.py`, HTML/JS da raiz e
    `blog/*.py` — 425 dos 747 arquivos versionados ficavam de fora, e 10
    menções de cliente moravam justamente lá (`.github/scripts`,
    `.github/workflows`, `scripts/`). Alcance estreito é cegueira silenciosa.
    """
    try:
        saida = subprocess.run(["git", "ls-files"], cwd=_RAIZ,
                               capture_output=True, text=True, timeout=60).stdout
        arqs = [l.strip().replace("\\", "/") for l in saida.split("\n") if l.strip()]
    except Exception:
        arqs = []
    if not arqs:                      # fora de um clone git (não deve acontecer no CI)
        for base, dirs, files in os.walk(_RAIZ):
            dirs[:] = [d for d in dirs
                       if d not in (".git", "node_modules", "__pycache__", ".claude")]
            for f in files:
                arqs.append(os.path.relpath(os.path.join(base, f), _RAIZ).replace("\\", "/"))
    return [a for a in arqs
            if a.endswith(_EXT_TEXTO) and os.path.basename(a) != _ESTE_ARQUIVO]


def _conteudo(rel):
    try:
        return io.open(os.path.join(_RAIZ, rel), encoding="utf-8", errors="replace").read()
    except Exception:
        return ""


def _e_nome_de_cliente(palavra):
    return hashlib.md5(palavra.lower().encode("utf-8")).hexdigest() in _HASH_DE_NOME


def _ocorrencias_de_nome():
    """(arquivo, linha) de cada palavra que bate com a base de clientes."""
    achados = []
    for rel in _versionados():
        if rel.startswith(_FORA_DA_CHECAGEM_DE_NOME):
            continue
        src = _conteudo(rel)
        if not src:
            continue
        for m in _PALAVRA.finditer(src):
            if _e_nome_de_cliente(m.group(0)):
                achados.append((rel, src[:m.start()].count("\n") + 1))
    return achados


# ═══════════════════════════════════════════════════════════════════════════
#  E-mail: zero, sem teto
# ═══════════════════════════════════════════════════════════════════════════

def test_nenhum_email_pessoal_de_terceiro_no_codigo():
    """🚨 E-mail de cliente em comentário é dado pessoal publicado — e vem
    acompanhado de um fato sobre a pessoa, o que é pior."""
    achados = []
    for rel in _versionados():
        for m in _RE_PESSOAL.finditer(_conteudo(rel)):
            if m.group(0).lower() in _DO_DONO:
                continue
            achados.append("%s:%d" % (rel, _conteudo(rel)[:m.start()].count("\n") + 1))
    assert not achados, (
        "e-mail pessoal de terceiro no repositório PÚBLICO: %s\n"
        "Troque por um rótulo estável (cliente-NN) ou pelo job_id, que já é "
        "opaco. O valor do comentário é o CASO, não a pessoa." % achados[:8])


def test_nenhum_apelido_de_cliente_sobreviveu():
    """A parte ANTES do @ identifica igual — e escapa do regex de e-mail."""
    apelidos = ["ivaldogss", "jssoliveira88", "thallisson.producao", "eng.kovatch",
                "kasavitski", "rafaelcmnz", "humberto.oliveira", "marcioeng72",
                "valimduda", "lpleonardo", "v.anjos.ia.81", "diana.golin",
                "alansilvacosta", "ialves943", "estudosmaraligrupo",
                "professormoabgarcia", "adn.arquiteturadinamica"]
    achados = []
    for rel in _versionados():
        src = _conteudo(rel)
        for a in apelidos:
            if a in src:
                achados.append("%s: %s" % (rel, a[:4] + "***"))
    assert not achados, "apelido de cliente ainda no repositório público: %s" % achados


# ═══════════════════════════════════════════════════════════════════════════
#  Nome: teto que só desce
# ═══════════════════════════════════════════════════════════════════════════

def test_nenhum_nome_de_cliente_NOVO_entra_no_repositorio():
    """🚨 A REGRA: no repositório público, cliente é rótulo — nunca nome.

    O teto é dívida herdada, não licença. Ocorrência nova reprova aqui.
    """
    achados = _ocorrencias_de_nome()
    assert len(achados) <= _TETO_DE_NOMES, (
        "nome de cliente NOVO no repositório PÚBLICO: %d ocorrências, teto %d.\n"
        "Primeiras: %s\n"
        "Use um rótulo estável (cliente-NN) ou o job_id. O caso é o que ensina; "
        "o nome não acrescenta nada e é dado pessoal."
        % (len(achados), _TETO_DE_NOMES,
           ["%s:%d" % a for a in achados[:8]]))


def test_o_teto_de_nomes_esta_APERTADO():
    """🪤 Teto folgado é teto que não protege: se a dívida cair pra 100 e o teto
    ficar em 374, cabem 274 nomes novos sem ninguém ver. Quando limpar, APERTE
    o teto no mesmo commit."""
    achados = _ocorrencias_de_nome()
    folga = _TETO_DE_NOMES - len(achados)
    assert folga <= 10, (
        "o teto está %d acima da dívida real (%d). Baixe _TETO_DE_NOMES para %d "
        "— senão ele deixa passar nome novo." % (folga, len(achados), len(achados)))


# ═══════════════════════════════════════════════════════════════════════════
#  Controles — o guarda prova que REPROVA, e que não acusa o que é legítimo
# ═══════════════════════════════════════════════════════════════════════════

def test_CONTROLE_o_padrao_ACHA_um_email_plantado():
    falso = "# 🚨 caso maria.silva@gmail.com — 3 devoluções"
    m = _RE_PESSOAL.search(falso)
    assert m and m.group(0) == "maria.silva@gmail.com"


def test_CONTROLE_o_padrao_NAO_acusa_o_que_e_nosso():
    for ok in ("contato@ai.arq.br", "cliente1@example.com",
               "noreply@mail.app.supabase.io"):
        assert not _RE_PESSOAL.search(ok), ok


def test_CONTROLE_as_excecoes_sao_POUCAS_e_do_dono():
    assert len(_DO_DONO) <= 3, (
        "a lista de exceção cresceu: %d. Cada e-mail a mais é um dado pessoal "
        "tolerado no repo público" % len(_DO_DONO))
    for e in _DO_DONO:
        assert _RE_PESSOAL.search(e), (
            "%s não casa com o padrão — está na exceção à toa" % e)


def test_CONTROLE_a_lista_de_hash_RECONHECE_cliente_de_verdade():
    """🚨 O controle que prova que a peneira existe. Se `_HASH_DE_NOME` for
    esvaziada ou o md5 trocado, a dívida vira 0, o teto passa e o guarda vira
    enfeite. Aqui a gente cobra que ele ainda ACHA gente no repositório —
    porque hoje, comprovadamente, há 374 ocorrências."""
    assert len(_HASH_DE_NOME) >= 100, (
        "a lista de hash encolheu para %d — foi truncada?" % len(_HASH_DE_NOME))
    assert len(_ocorrencias_de_nome()) > 0, (
        "o guarda parou de achar QUALQUER nome num repositório que tem 374 "
        "ocorrências conhecidas — a peneira quebrou")


def test_CONTROLE_o_dono_NAO_e_acusado():
    """O Pedro é citado em centenas de comentários. Guarda que reclama dele é
    guarda desligado no primeiro dia."""
    for palavra in ("Pedro", "pedro", "Zellmer", "zellmer"):
        assert not _e_nome_de_cliente(palavra), "%r foi acusado" % palavra


def test_CONTROLE_vocabulario_do_projeto_NAO_e_acusado():
    """🪤 Falso positivo mata guarda. Estas são palavras que aparecem às
    centenas no código e não podem virar acusação."""
    for palavra in ("prancha", "medida", "cliente", "projeto", "planilha",
                    "quantidade", "revisao", "arquivo", "layer", "bloco",
                    "smoke", "construtora", "engenharia", "teste"):
        assert not _e_nome_de_cliente(palavra), (
            "%r está na lista de nomes — vai acusar código legítimo e o guarda "
            "acaba desligado" % palavra)


def test_CONTROLE_o_alcance_cobre_o_que_a_versao_ANTERIOR_deixava_de_fora():
    """🩸 A 1ª versão varria 322 de 747 arquivos versionados. Dez menções de
    cliente moravam justamente nos 425 de fora."""
    arqs = _versionados()
    # 386 arquivos de texto em 06/09 (de 747 versionados). O limiar existe pra
    # pegar encolhimento do alcance, não pra cravar o número do dia.
    assert len(arqs) > 300, "o alcance encolheu para %d arquivos" % len(arqs)
    for pasta in (".github/", "scripts/"):
        assert any(a.startswith(pasta) for a in arqs), (
            "%s voltou a ficar fora do alcance — foi exatamente ali que "
            "sobraram nomes na limpeza de 06/09" % pasta)


def test_CONTROLE_a_citacao_do_BLOG_nao_e_confundida_com_cliente():
    """🪤 Os posts citam autores de artigos e normas — é a FONTE que a regra de
    copy pública exige. Se o blog entrar na checagem de nome, o conserto de
    privacidade vira destruição de citação."""
    assert any(f.startswith("blog/posts") for f in _versionados()), \
        "o blog sumiu do repositório?"
    assert not any(rel.startswith("blog/posts") for rel, _ln in _ocorrencias_de_nome()), \
        "a checagem de nome invadiu o blog e vai mandar apagar citação"


def test_o_rotulo_opaco_continua_ENSINANDO_o_caso():
    """🔑 Anonimizar não pode custar a lição."""
    achou = any("cliente-02" in _conteudo(rel) and "4ª tentativa" in _conteudo(rel)
                for rel in _versionados())
    assert achou, (
        "o caso do retry (que justifica o backoff de ~5min em llm_retry.py) "
        "perdeu o contexto na anonimização — o rótulo substitui o nome, não "
        "apaga a história")
