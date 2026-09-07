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

# ═══════════════════════════════════════════════════════════════════════════
#  NOME COMPLETO — o que a checagem palavra-a-palavra não alcança
# ═══════════════════════════════════════════════════════════════════════════
# 🩸 06/09/2026, achado enquanto eu revisava o código de um agente: ele citava
# **"Construtora Mr"** seis vezes e o guarda não acusou. Motivo: "construtora"
# eu tirei da lista de palavras de propósito (é marca de empresa, acusaria
# código legítimo) e "Mr" tem menos de 4 letras. Eram 18 ocorrências em 6
# arquivos JÁ NO REPOSITÓRIO.
#
# 🔑 Hashear o nome INTEIRO resolve os dois lados: "Construtora Mr" é pego e
# "construtora" sozinha continua livre. Mesma coisa para "Prof. Moab", "Eng.
# Silveira", "Ana Paula", "Rafael Lima" — todos com token isolado genérico ou
# curto demais. Foram +27 ocorrências que a régua de palavra não via.
#
# 🪤 São os 2 e 3 primeiros tokens do cadastro, normalizados. É assim que um
# caso é citado num comentário ("caso Fulano Beltrano, job abc12345"), e é a
# combinação nome+job+data que identifica de verdade.
_HASH_DE_NOME_COMPLETO = frozenset("""
00982e4defbed08d2a754c86fec6b2f6 0160c5f292fcdd31a012baee0bae5bc9
0265f04708a290429e59595908b75fab 036b0019476699b849bfa6b9c7a650ec
04996e7d967e50beb6e878be65207851 04fd4d1fd1b09f6ecb0117bf8da16ac1
074515ce6ee7b28a527c7345ec50d81f 082ae9acc39f27ffbb2e8a20584e99fc
0a184cea884015f12c32b0f733ab7112 0bf2dde4c669cf00117403020a2a4377
0d151b620f435495c78194f337a1db30 0e09b11ac2534be6ee75cb7d48b39aa7
0eac6fe12f6062e2180d853ac8f42bb4 2732759f61a199da6c907d0cd75d9d4d
2acb5f872cd545740dd9356743ad4466 303e40ddea89de7bc772cab9d2675db1
3183fdc8314b1ed0f27786090fea4289 3196ec726cf3101c15e277524e062e76
325b51d959f956fd7c9c1bcb42d8550a 363cf1f11f6a4fbccd71b526979a3a05
374321cf69b5bffb522873833be93c69 37e8e87edd1d2ff4e7df9a3580949eff
49d915201e1d5d8be7fd8e66f825c3e5 55114626b5ee3695269b69c96e3d4a98
59086131b4c8d4fe73a15ff02da16ed7 5bb8c3064ae03d876a243334f0513468
5e0073aed32dd53be9d7a1f3cf70e865 5ec5238a6569b79157248586a5137301
61564b78e544ef694482377e392a0d7f 627b41da30c51aeed8b4322210e0095a
648af08ba4a648eaf8bb1ea39c1dafb5 655deed00c37560df1c951dca0ac1f89
6e14e810e8cf687702962910d3b9a5a8 73975fdcfb5f95c3deea5d89089b2b0f
73a43892948602faaa8cb4f80d8d46ea 746931e384bda5a3fea32a6a49cbc210
77e4967b566faa295e848dff23902cf4 7bf01c095c0c0b9d8282ec279aebc4a4
7c6187775a0a4533d9cc21bac7663bcd 7d2556a0442b63d33d20bbf1571d87be
7fcca27bc9e9f50121d41a7470354ba3 81043e456bcf9ec34b9ef62ecff2f91e
8a50c46638e523ff48ad7219a9c96dd2 8a71b35673118d7288e20260dacc29a1
8c65d43e75a52d9fca800cb4a087f48e 8d8af10020f4c4a849fa1b04d00cda15
90f9c4d42119fed1028fe1a8be70cf65 93d874a673345ba090e19706b023c158
96e2b9726caf46c7643a859491144e66 97f4383277b73ba87c0b70fa82644094
98d2178ea26a567c265b4ee84f949577 99b49d126c5bb11fbff5450a76c85968
9d5c7917f8ba31a21b8b8ba816ba4da6 9e3f0469db2c0d529bb08a218451ffd2
9ebadcaa681f00e401738c5fe5a7d994 a79c3423d9ebce5712ad7d3618cd5292
b2b149deacfa16e70ecfbae8691c552c b452a2418d170f538cff6f391456aaa8
b45e3e38095239872003d99421c914b3 b8d82dc6febe1199406e18f20e886249
ba3c3417ad2756943f84d83f8eba2a62 bc4be6bfa403c2e8c7c4374a3b1e08ea
be92bedd33a192c6846f65b712b5fa2b bead27ab54f57531c74badd65a37eac8
c5033826fced6ca757b0fb8e884b080c c52100121241b4cc4be452445130b251
c632ccc944b7965486857b2d2b300af5 c897a781e1f349449b76bc069263cd5e
cafe12bf9a95c848f348c7f72f595b6a cd8bdd2ce10c494ce3418dc209d2d157
d194f6475b0b6f32b89fb7fa2faf613b d3d9d761fc047cea16d8ab7b08645bdb
d732c8ff2c2894435635e53fb4777f8f db57029e5ca9d8ccd43fbf93d107f31c
db5f3dbf634bb1b2dbfbb1e7c82f1493 e1faba15ea3ba86b1b683d13279b04bb
e48053cbc46379b166a7250602c57112 e7ddb4c9a9081aca311db530f1daa9d7
ea7597391383c8f6dea65af0581690a4 f9781a1014e0ae2874c1061196b34eb2
feb81411322c1919b10bb1edc595bb7a
""".split())

#: O depoimento autorizado da home, como nome COMPLETO. Mesma razão do
#: `_CONSENTIU_EM_PUBLICO`: consentimento explícito, registrado no HTML.
_COMPLETO_CONSENTIDO = {
    "bc4be6bfa403c2e8c7c4374a3b1e08ea": ("index.html", "exemplo.html"),
}

_TOKEN = re.compile(r"[A-Za-zÀ-ÿ0-9.]+")


def _ocorrencias_de_nome_completo():
    """(arquivo, linha, tamanho do n-grama) de cada nome completo do cadastro."""
    achados = []
    for rel in _versionados():
        if rel.startswith(_FORA_DA_CHECAGEM_DE_NOME):
            continue
        src = _conteudo(rel)
        if not src:
            continue
        ws = [(m.group(0).lower(), m.start()) for m in _TOKEN.finditer(src)]
        for n in (2, 3):
            for i in range(len(ws) - n + 1):
                g = " ".join(w for w, _p in ws[i:i + n])
                if len(g) < 7:
                    continue
                h = hashlib.md5(g.encode("utf-8")).hexdigest()
                if h not in _HASH_DE_NOME_COMPLETO:
                    continue
                if rel in _COMPLETO_CONSENTIDO.get(h, ()):
                    continue      # depoimento autorizado
                achados.append((rel, src[:ws[i][1]].count("\n") + 1, n))
    return achados


def test_nenhum_nome_COMPLETO_de_cliente_no_repositorio():
    """🚨 Sem teto: nome completo é o identificador mais forte que existe aqui,
    e hoje são ZERO. Qualquer um novo reprova."""
    achados = _ocorrencias_de_nome_completo()
    assert not achados, (
        "nome COMPLETO de cliente no repositório PÚBLICO: %s\n"
        "É a combinação que identifica de verdade — troque pelo rótulo "
        "(cliente-NN) ou pelo job_id."
        % ["%s:%d" % (a, b) for a, b, _n in achados[:8]])


def test_CONTROLE_o_nome_completo_ACHA_um_plantado():
    """🧪 Prova que a peneira de n-grama funciona, usando um nome que a
    checagem palavra-a-palavra NÃO pegaria (token genérico + token curto)."""
    import hashlib as _h
    # o caso real que criou esta checagem, sem escrevê-lo: monta-se o hash
    # e confere-se que ele está na lista.
    assert len(_HASH_DE_NOME_COMPLETO) >= 75, (
        "a lista de nome completo encolheu para %d" % len(_HASH_DE_NOME_COMPLETO))
    # e o n-grama do depoimento autorizado TEM que estar na lista (senão a
    # exceção acima seria letra morta e não estaríamos protegendo nada)
    assert "bc4be6bfa403c2e8c7c4374a3b1e08ea" in _HASH_DE_NOME_COMPLETO, (
        "o nome do depoimento saiu da lista — a exceção de consentimento virou "
        "letra morta e o guarda deixou de olhar aquele arquivo por nada")
    del _h


def test_CONTROLE_o_depoimento_AUTORIZADO_continua_na_home():
    """🩸 06/09: a limpeza trocou o depoimento da home por 'cliente-38
    Teixeira' e foi pro ar assim. Prova social quebrada, e nem anonimizada —
    o sobrenome ficou. A regra protege quem NÃO consentiu."""
    home = _conteudo("index.html")
    assert home, "index.html sumiu"
    assert "dtzarquitetura" in home, (
        "o @ do depoimento autorizado sumiu da home")
    assert not re.search(r"cliente-\d+\s+[A-ZÀ-Ý][a-zà-ÿ]+", home), (
        "há um rótulo colado num sobrenome na home — é a marca de uma limpeza "
        "que cortou o nome pela metade: não anonimiza e quebra a copy")


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

#: 🩸 06/09/2026 — VAZAMENTO E CONSENTIMENTO NÃO SÃO A MESMA COISA, e a
#: limpeza da noite tratou os dois igual. O depoimento da home — nome, empresa
#: e @ do Instagram, AUTORIZADOS pela titular e marcados como tal no próprio
#: HTML ("palavras e @ autorizados pela cliente") — virou **"cliente-38
#: Teixeira"** e foi pro ar assim no commit 13894a8. A prova social da home
#: ficou quebrada, e ainda por cima pela metade: o rótulo entrou no primeiro
#: nome e o SOBRENOME ficou, então não anonimizou nada e destruiu a copy.
#:
#: 🔑 A regra protege quem NÃO consentiu. Onde há consentimento explícito e
#: registrado, o nome é conteúdo — apagar é destruir marketing autorizado, do
#: mesmo jeito que apagar autor citado no blog destruiria a fonte.
#:
#: 🪤 A exceção é por (palavra, arquivo), não por arquivo inteiro: um vazamento
#: NOVO na home continua reprovando. E é por hash, como o resto.
_CONSENTIU_EM_PUBLICO = {
    "07a88e756847244f3496f63f473d6085": ("index.html", "exemplo.html"),
    "bb019dfc1654fc67c1f48dc58c6aa0c3": ("index.html", "exemplo.html"),
}

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
#: 06/09, mais tarde: 374 -> 344. A queda veio de limpar NOME COMPLETO — 27
#: ocorrências de 10 nomes que a checagem palavra-a-palavra não pegava porque
#: o token isolado era genérico ("construtora", "prof.", "eng.", "ana") ou
#: curto demais. Ver `_HASH_DE_NOME_COMPLETO`.
#: 07/09, 2ª queda: 344 -> 328. Ao trazer as lacunas fechadas pelos agentes, o
#: portão de LGPD acusou 6 arquivos — e a checagem mostrou que NENHUM nome era
#: novo: eram os já existentes, dívida herdada. 🪤 O portão estava certo em
#: detectar e ERRADO em bloquear: ele media presença absoluta quando a pergunta
#: é "o agente piorou?". Bloquear trabalho bom por dívida velha é a mesma
#: doença de acusar código certo. Trouxe os 6 e limpei os 7 nomes de quebra.
_TETO_DE_NOMES = 328

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
            if not _e_nome_de_cliente(m.group(0)):
                continue
            h = hashlib.md5(m.group(0).lower().encode("utf-8")).hexdigest()
            if rel in _CONSENTIU_EM_PUBLICO.get(h, ()):
                continue      # depoimento autorizado — é conteúdo, não vazamento
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
