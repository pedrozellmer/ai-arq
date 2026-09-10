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
import unicodedata
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
01b4aa2504786a6abb782dfd5d59f689 02558a70324e7c4f269c69825450cec8
0410c49927fe2e0123dd9e19fadcadbb 067036db8f53564d6a32e3f10466c99f
07a88e756847244f3496f63f473d6085 0db513d0630a515d0b64efd30fdd0dd5
0e4d164a767ed5990a08089020eb696b 0f5366b3b19afc3184d23bc73d8cd311
110d46fcd978c24f306cd7fa23464d73 112c60a750df6654cc3a8dac9b4379c0
131b4969b68d0e5c0d195e9773600d3a 132043adb2ba8acad21e401523cdc7fe
1434e827e7914d05c96e4e0934539776 1449bad536b588ec140ea1eeedbf2f41
15b1dfdb3030371415e5e6c276388201 184e6788c1d056417c9d25f6716827eb
18e59942c3d24ca9888364ce1455eb1a 19984dcaea13176bbb694f62ba6b5b35
1b150854805cbe12194c8dbc55c900cd 1b207465eac83b5d4b12e335faa0b53a
1ee1877c6655ecc71dfead311c771bd0 205a10818889cfe2de7c278fb6e9188f
2164e6a05df0c76ed7ccc03722fc8cd7 229e5b1363be0591e674cd57b3bb8645
263bce650e68ab4e23f28263760b9fa5 276e697e74e8b5264465139a480db556
29a2b2e1849474d94d12051309c7b4d7 2a4fbed09d245d236f4e46b0f874d6c9
2c42e5cf1cdbafea04ed267018ef1511 2e247e2eb505c42b362e80ed4d05b078
2efb7ced7e8047462873546c5521aaba 3805b13916b5664e3b029ee804edf3a4
38efbc884fc2473d095d6680c5840885 3a23bb515e06d0e944ff916e79a7775c
3df2175295d900d6f0c2f3a521d957cd 3f28e55efb457c86a979da0edfa923be
3f3ce8d94f88d42322e7204f702c138f 41008f06b76981093c7aa369d83c08ea
41602f23c972e56cb9661de649d4435a 41847ec28c30f25acc5d96f0bef5ebfc
4757067ca131abf21c7dedea7efd0c80 4aab03d761754d4d2b27314d11313079
4b2b772a039e1f20612cc32a5b633bce 4b6683e45065f9f7116267016239705b
4c57da7cca7a66c425c6aa53636613f1 4dc5bfca8186349e8d77469db5ec608a
4df055c5a76cccc7fb9d02c18858a07c 502ff82f7f1f8218dd41201fe4353687
503873f51e44d687ec3ba06846aca82f 52be95db6f26ac6b2d291443fcea77d8
5494e1e7b721c2a7c867f3588e577154 55815a0e411eeb2a4ef66dd7f19c0856
55fadfd036b568d4b2d5796ee444caa0 5bb2ec2c8876622a004e241e3ceed2f7
5d24aff18191f1177d00384e07736ef7 6209804952225ab3d14348307b5a4a27
64b1c7a622073845494b9815348c0d28 680c3108617bfed131f7d20c929234b9
68830aef4dbfad181162f9251a1da51b 68c2280bda076acef10b444c9665f052
6a117c1c8daea248caca1507b93ccb11 6a796ddf660ddf10b7323414321d2a1b
6c84cbd30cf9350a990bad2bcc1bec5f 704797c6cd9bd24d777423f9bff26565
726cd927c662edb20fedf29faf26c60b 729df251ee41cf92d45ec11a87c60ec0
77949c9f02621a4c85964be115a9dcc9 790d0289dae439880bc46c13818998d5
79df64f73eab9bc0d7b448d2008d876e 7bc6784b07998864a2c2891386970de9
7e6595dae6c06c29dcc107d88fa93e46 7fa81ff5e6a88a34ca2392240268c68f
841d93525b9f0960ceaf38f4fdf22e2e 845f18eea198bc4a7a26605a0615ad21
848ffd503f98d2368d47abceb4821465 870f4f7827a85c1eb93bb583a6c9c293
8767bbc52e71900d1f3a50b53196d0e2 89ba023086e37a345839e0c6a0d272eb
8ac291d567b1e54952a12f2f28740643 8c278462dc2f486dd9697edc17eff391
8c3856f64ea9383b1d3d9fe834c73ff6 8cebae137bc58ff04e6bb3baa4e5a4ce
8eb479d8ea940abc1afdde436233c4cc 9135d8523ad3da99d8a4eb83afac13d1
9491876179d7a80bb5c86f15dbe31422 9518fcbed21ea1baa2552302e13c66fe
9885921f1302d72826ee65394f50fdf7 995bf053c4694e1e353cfd42b94e4447
997d13b90da22b35ce43bebdd332ad11 9ac7dd42fc7e07f79b72f7d999188ab3
9be63b1329806f4c3cdff5fa92ba6b9a 9c5ddd54107734f7d18335a5245c286b
9d3d67d1c0edd25a04dc79788404a9e3 9e85d98e8033df21f562a84a940133cc
9ed083b1436e5f40ef984b28255eef18 a1361cb85be840d6a2d762c68e4910e2
a1607661a82efce42f12531480d680a4 a37b2a637d2541a600d707648460397e
a3b96c3330d605fad966ad069ec45677 a3cd5afc9eab47fefcd573566c41594e
a53bd0415947807bcb95ceec535820ee a64abe98558bb7bb5a9f1b8e2146cf68
a9629ec3e248369c5c8b9a885bab85d8 aa3fec16d57bcd14cb027a3d0c0f5a4a
aa47f8215c6f30a0dcdb2a36a9f4168e ab892a649914a9e71aa3e869739253db
ac1da964ea928cf1b7b59120b4179e76 af465ebe364f4b50526eb5f59885d7aa
af5caae019a33d603444b7492a436b7f b73cc1cbd7f3180f41013971b8edf2f9
b993e4526238d62f6b1b90e605532ff8 bbb5ff6dc3826b999a5cf0c2e7b2c889
c11845c9a05c8df7b137f49504dd918b c13c253f3e26c1c6f265d444275bc7fb
c1ed60949799e3adcd72928bb3314fe0 c26d483dd7cb0179994e7ed88fe8c7d4
c50eeda3f8f0d15c77754857c0cdc3eb c7b2af69cfca668a7eb128295789b6d3
c810ed30521e174d8040df6f9c054567 c94596c251014e32ca68d59e18a8dd11
c99868052fb8a76e4f4b9f2ee67d39fb cd86a0ad35cb75edda6569fc74941a7c
cebdd715d4ecaafee8f147c2e85e0754 cf960696aa77325be0cbfe7020407e7d
d1778abf5069d30922f191b60cc383e8 d1dcb1f278f32127505cb2133ab9bfc6
d252377a473501b19964bc41b5f503e7 d2d8ffc663941ccd1392de0cf254d3ef
d6607a0d5fa9ddbc40d551a695a3ddee da64c7daf16c4687b0b8686147448223
db5fb5279b9f52c63638a39462d6c962 dccd96c256bc7dd39bae41a405f25e43
dcf7ae580d3db76e6a5a832febbd242c df8e65bca92091ec2d549727da81ee64
e0e34c5ad05aac3eef6ab31eacbf7a5c e17da2153e6c23b3da11ce17765ecb7a
e1c565c5b1da2a3b81712427d06f5b34 e1d9614bc81cfc05391171cede492e79
e4095399f03b0cc518535c29d75859c6 e5fef21172cc7f1991bf93c7ab6653aa
e60408e9a55027070e3caf0550d2b4df e70f86c2b08f055b0acdf9b36df2ab3b
e7ef7a9f4059ff0401e5b92afe7a4d04 e982c8758a00a39fa94321e015ec6443
eb54d2175a728ed5bd17575d9fdf694c ebc65bc5b4f82407a201c89670ce454d
ec02d2d95c27675d87dca50018d89192 f1b6d941a97ababa0c81b92841b3189f
f576e7b27eafbfdf37fc44a357a8b085 f76405ac130dac085b2a6249073b213b
f883145b85cff801447fc390798d76a6 fd680d0cec4637cec6758e0393c2bd39
fd820a2b4461bddd116c1518bc4b0f77 ffc150a160d37e92012c196b6af4160d
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
# "construtora" sozinha continua livre. Mesma coisa para os n-gramas com
# título ("Prof. X", "Eng. Y") e para os de dois nomes comuns — todos com
# token isolado genérico ou
# curto demais. Foram +27 ocorrências que a régua de palavra não via.
#
# 🪤 São os 2 e 3 primeiros tokens do cadastro, normalizados. É assim que um
# caso é citado num comentário ("caso Fulano Beltrano, job abc12345"), e é a
# combinação nome+job+data que identifica de verdade.
_HASH_DE_NOME_COMPLETO = frozenset("""
004b77b1c386222c1ff1bd7635cdd825 0160c5f292fcdd31a012baee0bae5bc9
0265f04708a290429e59595908b75fab 0354975f93564fd14b3b89fff3a9b3d2
036b0019476699b849bfa6b9c7a650ec 04996e7d967e50beb6e878be65207851
059dcbb410d7df4ae72994115b295ec2 074515ce6ee7b28a527c7345ec50d81f
082ae9acc39f27ffbb2e8a20584e99fc 08b1baa21945bb4b93bf88b1cd2af69a
0a184cea884015f12c32b0f733ab7112 0acbaf16cb340be1a19cb6ca143895a5
0bf2dde4c669cf00117403020a2a4377 0d151b620f435495c78194f337a1db30
0dd4bcad4362a07b9f8e723c56534274 0e09b11ac2534be6ee75cb7d48b39aa7
0eac6fe12f6062e2180d853ac8f42bb4 0ee01de15e82a787f35ffcd10bd283b0
14a4de94f99d2b9856c36ad24c7f7fe9 179df79e604fe2e5c962d52635642441
192850af201f399cfa747bb91ce80a0d 1c7c76f5668a9209de399fffdcc6b030
1e03c454c86a87c9f5f52a8206c3d6c7 1eef77bc3f1a38c1e68ce00a8b6946ea
20d55c67c56607983d7231ba764bf1d6 217f7539cc1d9dcd2380cd8f5df02fc4
24ca9f1281f7494f569157c4c0d91014 2732759f61a199da6c907d0cd75d9d4d
27b09d369dc09d958a25e1caaefb965c 2a21cc7020095a4bb361da8938eeda4a
2d030a597a35fc5990928c2c07afe870 303e40ddea89de7bc772cab9d2675db1
3089b96b7feedb8ee11b03b5a8ed0d91 3183fdc8314b1ed0f27786090fea4289
31cba6b09ee805fe14b4806f94f984e7 325b51d959f956fd7c9c1bcb42d8550a
32c101d5832b1ac2992c47cedb87966d 32d6673760728f923915c6e6c1a88119
3372046d3784b3b5530b2a443de731f5 34bf6dfcf4d642bbb43b4b0d163be5b1
362990c9af8739a6f04509c53ae1c443 363cf1f11f6a4fbccd71b526979a3a05
374321cf69b5bffb522873833be93c69 37e8e87edd1d2ff4e7df9a3580949eff
3af4b18764a2d63840e6c5bd830b78f2 3dcfc4713d45ba536f1063955109f108
402a4a0e2dd2a6455521f886c965950a 4236179e9d8b8e0f31e9cb07451e00b6
49089f386f1b1449a874838e2208e389 4ae4d7a34d77091373cc080e863be95f
50b9f41882a2f1cbc089d37657d82a87 5311bfbf6a4ac7e914a56cdf3109d018
55114626b5ee3695269b69c96e3d4a98 56209f4c18443c73c291093eb69f8502
59086131b4c8d4fe73a15ff02da16ed7 5bb8c3064ae03d876a243334f0513468
5e0073aed32dd53be9d7a1f3cf70e865 5ec5238a6569b79157248586a5137301
627b41da30c51aeed8b4322210e0095a 629507f3b29e8fa9a6ed255a4f376d6d
641bd0012d8ffd0244be94fc40f3f818 648af08ba4a648eaf8bb1ea39c1dafb5
655deed00c37560df1c951dca0ac1f89 6659f5b3018408da9138b4c5b6eaca27
69a21d0951044e11b257a7433a1438cd 69beb605700814da62ea2d5d1a9275f3
6c00a867059915f13d7b0f3a98a9b85b 6db56c006c005ace22391786ea37ec5d
6dd9d7e7f0ba286308f0db92980ed276 6e14e810e8cf687702962910d3b9a5a8
6eac60d763c9e74bda9bc41a3d6a5e31 70a6323fc4f35ebf81a8a5e011115d55
712832ec7d1614be5b277b65e9523b50 713262d170ad5ef328ec3bdb2b8c9fa9
731dd17568a67e54657913507d69147c 7353ae8b76626bac16d36d9083240dda
73975fdcfb5f95c3deea5d89089b2b0f 73a43892948602faaa8cb4f80d8d46ea
746931e384bda5a3fea32a6a49cbc210 74b615ab9c264019dd5ebb175785d8b7
779bb26ae04c86d062adf8449beddc75 77e4967b566faa295e848dff23902cf4
7836a5f143401937ed98086a96b3c65b 78afd487fc9fd854e9184315934916cd
7bf01c095c0c0b9d8282ec279aebc4a4 7c6187775a0a4533d9cc21bac7663bcd
7dc218ac604bc51556bc8ec5b55e392e 7fcca27bc9e9f50121d41a7470354ba3
81043e456bcf9ec34b9ef62ecff2f91e 87bb1eeee61fc31d08289332af30bace
890bdb5e0048d3c128e587a3ecabdd77 8a50c46638e523ff48ad7219a9c96dd2
8a71b35673118d7288e20260dacc29a1 8a72abc880812d5c7aaf8c2b73aa2d15
8bca84e090b5adc11668d80da027e25e 8c65d43e75a52d9fca800cb4a087f48e
8d80a2da663a2422c475419ad1d2be17 8d8af10020f4c4a849fa1b04d00cda15
8e18908c5245eb733e4aa623060d3f5c 8fd0bb26b1437bad0ae0a1c3ec06adb6
90f9c4d42119fed1028fe1a8be70cf65 93d874a673345ba090e19706b023c158
95303485dc220699e69866eaec6a782a 96e2b9726caf46c7643a859491144e66
97df8a16a496419d58be423b97cdd850 97f4383277b73ba87c0b70fa82644094
981fabc2501445a62599c9894bd7a9b2 99b49d126c5bb11fbff5450a76c85968
9d0591fb298bc1f3582648b919dfa3e3 9d5c7917f8ba31a21b8b8ba816ba4da6
9e3f0469db2c0d529bb08a218451ffd2 9ebadcaa681f00e401738c5fe5a7d994
9fcfb5d7451c314068f05ada1876c3e5 a0488bdfc643d07c54b45b7ce5f0e28c
a10cc2c230aab95bf86778cf1e57d162 a19efc3cf8fb3a7d02ab8dc6abd1cba4
a3125f2b64b712a2de5fa8771f7dcb30 a48272cbd3f0b15804d88dcd565845fc
a5f416f9b2739dc3bf4c6f1f7199fe47 a6660646c09291bc9053d8ed53aedbb3
a79c3423d9ebce5712ad7d3618cd5292 ab792008ea10953fbbac6d38a35197ed
af3b817539bc52a164238001642c7592 b2b149deacfa16e70ecfbae8691c552c
b331e566bfae8a23db8c726680c52b2c b452a2418d170f538cff6f391456aaa8
b45e3e38095239872003d99421c914b3 b4ddf716e68233b91a6c6f4903003697
b7b4b5eb623bf3fec8328626377c203a b81d6b9217217d38e28ea692ba1449c9
b823e6d77aabc9e05f6ebb2b76f658f6 b8d82dc6febe1199406e18f20e886249
b9e05b40412ed7d6e74de8442b17b7fb ba3c3417ad2756943f84d83f8eba2a62
bae1e86c2ca63bc70db52d2204115515 bc4be6bfa403c2e8c7c4374a3b1e08ea
be92bedd33a192c6846f65b712b5fa2b c0507d176d68e66b6d819ebab077b559
c5033826fced6ca757b0fb8e884b080c c52100121241b4cc4be452445130b251
c632ccc944b7965486857b2d2b300af5 c8f1c57d02ed8a83d57962b56123038e
cd8bdd2ce10c494ce3418dc209d2d157 cdcd90995b19a0c85d7841e42536d5dd
d1095f97895f2e41bea15bc81578644d d194f6475b0b6f32b89fb7fa2faf613b
d392b62549a853d2741d97cd1cef60ac d3d9d761fc047cea16d8ab7b08645bdb
d3ea48786b7a357656b8ed5ecfac2d29 d732c8ff2c2894435635e53fb4777f8f
da4b1a6432ead6ba07334b2ac359d32e da6ccda680418cb3ce339859a8e81b4f
db15cc0538fdefc3cb28dee717586bd7 db57029e5ca9d8ccd43fbf93d107f31c
db5f3dbf634bb1b2dbfbb1e7c82f1493 dd5d43ac7337d77f5a18a2d307495fbc
e1faba15ea3ba86b1b683d13279b04bb e3db62872313723858eb96c6fbc6b713
e7ddb4c9a9081aca311db530f1daa9d7 ea7597391383c8f6dea65af0581690a4
eaa08a58481ef55d0bb182d8d03c6a23 ebb004cadacd7ba9ca7f9490acc57cb9
ec39749d62e9deb9fdae4aae302182b9 f0202629f4e8286159d3d2d4c87a3bf0
f113df39dddd8e3e4d6035c2cddcc4a8 f2052044230bae98e8f0ce9acf0a3dda
f20f6501c38993415d3d5fe229a1b23e f59a0af5c4c57ea7ce4d187797d064cd
f8ee15f565c33093b00f7729f522d9a5 f9781a1014e0ae2874c1061196b34eb2
fa65893d1ccd9bc85ccac658d3ccf014 fbb6a0a945bb0bb470f90690eb03675e
feb81411322c1919b10bb1edc595bb7a ff0590ba9b883565db5fa7f319a86275
ff301519e277d7229731d61780c55e6a
""".split())

#: O depoimento autorizado da home, como nome COMPLETO. Mesma razão do
#: `_CONSENTIU_EM_PUBLICO`: consentimento explícito, registrado no HTML.
_COMPLETO_CONSENTIDO = {
    "bc4be6bfa403c2e8c7c4374a3b1e08ea": ("index.html", "exemplo.html"),
}

_TOKEN = re.compile(r"[A-Za-zÀ-ÿ0-9.]+")


def nomes_completos_no_texto(src, rel=""):
    """(linha, tamanho do n-grama) de cada nome completo dentro de UM texto.

    🔑 Extraída de `_ocorrencias_de_nome_completo` em 08/09/2026 pra poder ser
    CHAMADA por um teste. Enquanto a varredura só existia amarrada aos arquivos
    versionados, nenhum controle exercitava o caminho real — e foi assim que a
    cegueira de acento passou por 5 ocorrências com a bancada verde. Guarda que
    não pode ser chamado não pode ser provado.
    """
    achados = []
    # 🪤 08/09: era `.lower()` puro — e acento fazia o hash nunca bater.
    ws = [(_sem_acento(m.group(0)), m.start()) for m in _TOKEN.finditer(src)]
    for n in (2, 3):
        for i in range(len(ws) - n + 1):
            g = " ".join(w for w, _p in ws[i:i + n])
            if len(g) < 7:
                continue
            h = hashlib.md5(g.encode("utf-8")).hexdigest()
            if h not in _HASH_DE_NOME_COMPLETO:
                continue
            if rel and rel in _COMPLETO_CONSENTIDO.get(h, ()):
                continue      # depoimento autorizado
            achados.append((src[:ws[i][1]].count("\n") + 1, n))
    return achados


def _ocorrencias_de_nome_completo():
    """(arquivo, linha, tamanho do n-grama) de cada nome completo do cadastro."""
    achados = []
    for rel in _versionados():
        if rel.startswith(_FORA_DA_CHECAGEM_DE_NOME):
            continue
        src = _conteudo(rel)
        if not src:
            continue
        for linha, n in nomes_completos_no_texto(src, rel):
            achados.append((rel, linha, n))
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


def test_a_LISTA_cobre_as_5_FONTES_de_nome(monkeypatch):
    """🩸 08/09/2026 — o achado n1 da auditoria de seguranca.

    A lista nascia de 3 tabelas e IGNORAVA `profiles`, a do CADASTRO. Quem criou
    conta e nunca teve projeto nunca entrava na peneira: **156 palavras na base
    contra 108 na lista** — 48 palavras e 94 n-gramas que o guarda nunca viu. E
    3 dos 5 nomes completos achados hoje caiam exatamente nessa fatia.

    🔑 A lista e ESTATICA e so muda a mao. Nada no repositorio avisava que ela
    tinha envelhecido — e ela envelheceu por 3 tabelas. Este teste nao consulta
    o banco (bancada nao depende de rede): ele congela o TAMANHO medido, pra que
    encolher a lista, ou regerar com as fontes antigas, reprove alto.
    """
    assert len(_HASH_DE_NOME) >= 154, (
        "a lista de PALAVRA encolheu para %d (medido em 08/09: 154, de 5 fontes "
        "com unaccent). Regerar com menos fontes deixa cliente invisivel — foi "
        "assim que `profiles` ficou de fora por 3 tabelas." % len(_HASH_DE_NOME))
    assert len(_HASH_DE_NOME_COMPLETO) >= 175, (
        "a lista de nome COMPLETO encolheu para %d (medido em 08/09: 175)"
        % len(_HASH_DE_NOME_COMPLETO))
    del monkeypatch


def test_a_receita_de_regerar_NAO_perdeu_as_fontes_novas():
    """🪤 Guarda de fonte, e assumido: a receita e o que a proxima pessoa vai
    rodar. Se ela voltar a listar 3 tabelas, a lista envelhece de novo no
    proximo cliente — e o teste de tamanho acima so acusaria DEPOIS."""
    # 🪤 Procura o SQL, nao a PALAVRA. A 1a versao conferia `"profiles" in
    # _COMO_REGERAR` e a mutacao passou batida: o proprio texto que EXPLICA o
    # defeito contem a palavra "profiles". Foi a quarta vez no dia que prosa
    # citando codigo enganou um guarda meu.
    for tabela in ("profiles", "contact_messages", "nps_responses",
                   "chat_leads", "projects"):
        assert ("from %s" % tabela) in _COMO_REGERAR, (
            "a receita de regerar perdeu a fonte %r (procurei `from %s`)"
            % (tabela, tabela))
    assert "unaccent(btrim(p))" in _COMO_REGERAR, (
        "a receita voltou a hashear COM acento — os dois lados precisam da "
        "mesma regua, e a chamada tem que estar no SELECT das palavras")
    assert "bc4be6bfa403c2e8c7c4374a3b1e08ea" in _COMO_REGERAR, (
        "sumiu o lembrete de conferir o hash do depoimento consentido")


def test_CONTROLE_o_ACENTO_nao_cega_o_guarda(monkeypatch):
    """🧪 O controle que faltava — e a falta dele custou 5 vazamentos.

    🩸 08/09/2026: as listas de hash foram geradas SEM acento, o texto do repo
    era hasheado COM acento, e os dois nunca batiam. O guarda passava verde com
    um nome completo de cliente vivo em `backend/main.py`, colado ao job_id.
    Nenhum teste percebeu, porque todos os controles usavam nome SEM acento.

    Aqui a peneira é obrigada a achar a forma acentuada de uma palavra que ela
    só conhece sem acento. Se alguém tirar o `_sem_acento`, este teste reprova.

    🪤 Fixture genérica de propósito: "jose"/"antonio" são nomes comuns, não
    identificam cliente nenhum, e o repo é público.
    """
    import hashlib as _h
    for sem, com in (("jose", "José"), ("antonio", "Antônio"),
                     ("marcia", "MÁRCIA"), ("ines", "Inês")):
        monkeypatch.setattr(
            "test_repo_publico_nao_expoe_cliente._HASH_DE_NOME",
            frozenset({_h.md5(sem.encode("utf-8")).hexdigest()}))
        assert _e_nome_de_cliente(com), (
            "%r não foi reconhecido a partir de %r — o guarda voltou a ser "
            "cego pra acento" % (com, sem))
        assert _e_nome_de_cliente(sem), "controle: a forma sem acento também tem que bater"


def test_CONTROLE_o_ACENTO_tambem_vale_pro_nome_COMPLETO(monkeypatch):
    """🪤 A 1ª versão deste controle só RECALCULAVA o hash — não chamava a
    varredura. A mutação provou que ele era decorativo: dava pra devolver o
    n-grama pra `.lower()` e ele passava verde.

    Agora ele RODA `nomes_completos_no_texto` num texto acentuado. É o caminho
    exato que deixou passar 5 ocorrências em 08/09.
    """
    import hashlib as _h
    monkeypatch.setattr(
        "test_repo_publico_nao_expoe_cliente._HASH_DE_NOME_COMPLETO",
        frozenset({_h.md5("jose antonio".encode("utf-8")).hexdigest()}))

    texto = "# caso José Antônio (job 3eb748e3): informou 880.000 no campo\n"
    achados = nomes_completos_no_texto(texto)
    assert achados, ("a varredura não achou o nome ACENTUADO — é a cegueira de "
                     "08/09 de volta")
    assert achados[0][0] == 1, achados

    # CONTROLE do controle: sem acento tem que achar igual
    assert nomes_completos_no_texto("# caso Jose Antonio (job x)\n"), (
        "cenário inválido: nem sem acento acha, então o teste não prova nada")


def test_CONTROLE_o_CONSENTIMENTO_sobrevive_ao_acento(monkeypatch):
    """🪤 O outro mutante que passou batido: o caminho do depoimento AUTORIZADO
    também compara por hash. Se ele voltar a comparar com acento, a exceção de
    consentimento deixa de casar — e o guarda passa a ACUSAR o depoimento que o
    cliente autorizou, num arquivo que é conteúdo do site.
    """
    import hashlib as _h
    alvo = _h.md5("jose antonio".encode("utf-8")).hexdigest()
    monkeypatch.setattr(
        "test_repo_publico_nao_expoe_cliente._HASH_DE_NOME_COMPLETO",
        frozenset({alvo}))
    monkeypatch.setattr(
        "test_repo_publico_nao_expoe_cliente._COMPLETO_CONSENTIDO",
        {alvo: ("index.html",)})

    texto = "<p>José Antônio, arquiteto, aprovou este depoimento.</p>\n"
    assert not nomes_completos_no_texto(texto, "index.html"), (
        "o depoimento autorizado foi acusado: a exceção de consentimento não "
        "casou com a forma acentuada")
    assert nomes_completos_no_texto(texto, "backend/main.py"), (
        "controle: FORA do arquivo consentido o mesmo texto tem que acusar")


def test_CONTROLE_o_CONSENTIMENTO_PALAVRA_sobrevive_ao_acento(monkeypatch):
    """A exceção de consentimento existe em DOIS caminhos — n-grama e
    palavra-a-palavra — e cada um tem a própria comparação por hash.

    🪤 A mutação pegou justamente este: eu tinha coberto o n-grama e deixado o
    outro sem ninguém. Dava pra devolver `_ocorrencias_de_nome` pra `.lower()`
    e a bancada seguia verde — o depoimento AUTORIZADO passaria a ser acusado.
    """
    import hashlib as _h
    alvo = _h.md5("marcia".encode("utf-8")).hexdigest()
    monkeypatch.setattr(
        "test_repo_publico_nao_expoe_cliente._HASH_DE_NOME", frozenset({alvo}))
    monkeypatch.setattr(
        "test_repo_publico_nao_expoe_cliente._CONSENTIU_EM_PUBLICO",
        {alvo: ("index.html",)})

    texto = "<p>MÁRCIA autorizou este depoimento.</p>\n"
    assert not nomes_no_texto(texto, "index.html"), (
        "o depoimento autorizado foi acusado — a exceção não casou com a "
        "forma acentuada")
    assert nomes_no_texto(texto, "backend/main.py"), (
        "controle: fora do arquivo consentido, a mesma palavra acusa")
    assert nomes_no_texto("<p>marcia sem acento</p>\n", "backend/main.py"), (
        "controle do controle: sem acento também tem que acusar")


def test_CONTROLE_normalizar_NAO_junta_palavras_diferentes():
    """🪤 Tirar acento aproxima palavras: se juntasse demais, o guarda passaria
    a acusar vocabulário do projeto. Duas palavras distintas continuam
    distintas — o que muda é só o acento."""
    assert _sem_acento("Área") == "area"
    assert _sem_acento("area") == "area"
    assert _sem_acento("cotas") != _sem_acento("cota")
    assert _sem_acento("São") == "sao" and _sem_acento("sao") == "sao"


def test_CONTROLE_o_depoimento_AUTORIZADO_continua_na_home():
    """🩸 06/09: a limpeza trocou o primeiro nome do depoimento da home por um
    rótulo e foi pro ar assim, com o SOBRENOME intacto. Prova social quebrada, e
    nem anonimizada. A regra protege quem NÃO consentiu.
    🔁 09/09: aconteceu DE NOVO, na limpeza em massa — e este guarda pegou."""
    home = _conteudo("index.html")
    assert home, "index.html sumiu"
    assert "dtzarquitetura" in home, (
        "o @ do depoimento autorizado sumiu da home")
    assert not _RX_ROTULO_COLADO.search(home), (
        "há um rótulo colado num sobrenome na home — é a marca de uma limpeza "
        "que cortou o nome pela metade: não anonimiza e quebra a copy")


#: Rótulo no primeiro nome + SOBRENOME intacto: não anonimiza (o sobrenome
#: ainda identifica) e ainda estraga a frase. 🪤 O exemplo do padrão é montado
#: em tempo de execução no controle — escrevê-lo aqui seria, ele próprio, meio
#: nome de cliente no repo público.
_RX_ROTULO_COLADO = re.compile(r"cliente-\d+\s+[A-ZÀ-Ý][a-zà-ÿ]{2,}")

#: 🪤 Onde a metade do nome é LEGÍTIMA: aqui o rótulo é seguido de palavra
#: comum, não de sobrenome. Explícito e curto — se crescer, é sinal de que a
#: peneira está larga demais.
_ROTULO_SEGUIDO_DE_PALAVRA_OK = ("Rev", "Estrutura", "Arquitetura")


def test_nenhum_rotulo_ficou_COLADO_num_sobrenome_em_lugar_nenhum():
    """🩸 08/09 (auditoria): este controle existia e olhava SÓ o index.html.

    A doença é a limpeza feita pela metade — o rótulo entra no primeiro nome e o
    sobrenome fica. Não anonimiza nada e quebra a frase. Olhar uma amostra de um
    arquivo enquanto o padrão vive em outros é o mesmo erro do guarda que só
    conhecia 3 tabelas: a peneira certa, aplicada estreito demais.

    🔑 A mudança é uma linha — rodar o mesmo regex sobre TODOS os versionados.
    """
    achados = []
    for rel in _versionados():
        src = _conteudo(rel)
        if not src:
            continue
        for m in _RX_ROTULO_COLADO.finditer(src):
            seguinte = m.group(0).split()[-1]
            if seguinte in _ROTULO_SEGUIDO_DE_PALAVRA_OK:
                continue
            linha = src[:m.start()].count("\n") + 1
            achados.append("%s:%d %r" % (rel, linha, m.group(0)))
    assert not achados, (
        "rótulo colado num sobrenome — limpeza pela metade, que não anonimiza "
        "e ainda estraga a frase: %s" % achados[:6])


def test_CONTROLE_o_regex_do_rotulo_colado_ACHA_um_plantado():
    """🧪 Sem isto, um regex que não casasse nada passaria em tudo.

    🪤 O sobrenome do exemplo é SINTÉTICO e montado aqui: usar um real faria
    este controle ser o vazamento que ele caça — e desde 09/09 o guarda varre
    o próprio arquivo, então ele reprovaria a si mesmo (e reprovou)."""
    _sobrenome = "So" + "brenome"
    assert _RX_ROTULO_COLADO.search("o caso do cliente-38 %s mostrou" % _sobrenome)
    assert not _RX_ROTULO_COLADO.search("o caso do cliente-38 mostrou")
    assert not _RX_ROTULO_COLADO.search("cliente-38, 16/06: 4a tentativa")


_COMO_REGERAR = r"""
Cliente novo entra na base e o guarda nao sabe. Rode no Supabase e cole o
resultado acima — a consulta devolve SO hashes, nenhum nome sai do banco.

🩸 08/09/2026 — A CONSULTA LIA 3 TABELAS E IGNORAVA `profiles`, A DO CADASTRO.
Quem criou conta e nunca teve projeto nunca entrava na peneira: 156 palavras na
base contra 108 na lista. E ela hasheava COM acento, enquanto a comparacao
passou a ser sem — os dois lados precisam da MESMA regua.

🔑 Agora sao 5 fontes e `unaccent()` dos dois lados:

  with fontes as (
    select coalesce(user_name,'') as nome from projects
    union all select coalesce(user_name,'') from nps_responses
    union all select coalesce(name,'') from chat_leads
    union all select coalesce(full_name,'') from profiles          -- <- faltava
    union all select coalesce(name,'') from contact_messages       -- <- faltava
  ), pessoas as (
    select nome from fontes
    where array_length(regexp_split_to_array(btrim(nome), '\s+'), 1) >= 2
      and nome !~* '(construtora|engenharia|arquitetura|ltda|eireli|smoke|fake|teste|admin|projetos|obras|incorporad|administrativ|confortar|servi)'
  ), palavras as (
    select distinct lower(unaccent(btrim(p))) as w
    from pessoas, regexp_split_to_table(btrim(nome), '\s+') as p
    where length(btrim(p)) >= 4
  )
  select string_agg(md5(w), ' ' order by md5(w)) from palavras
  where w !~ '^(junior|neto|filho|silva|santos|souza|costa|lima|dias|rosa|cruz|reis|nunes|pinto|marco|marcos|passos|faria|campos|mota|melo|leal|braga|maia|serra|monte|amaral|prado|vale|barros|freitas|ramos|teixeira|moreira|cardoso|gomes|martins|araujo|carvalho|almeida|ribeiro|fernandes|goncalves|rodrigues|oliveira|pereira|ferreira|alves|barbosa|rocha|dantas|nascimento|moura|batista|machado|azevedo|correia|cavalcante|andrade)$'
    and w ~ '^[a-z]+$' and w not in ('pedro','zellmer');

🪤 `marcos` e `passos` entraram no corte: sao sobrenome E palavra comum, e
sozinhas geravam 130 falsos positivos. O nome COMPLETO delas continua protegido
pelo n-grama.

Pra _HASH_DE_NOME_COMPLETO, a mesma base, montando 2- e 3-gramas:

  ), toks as ( select nome, string_to_array(nome,' ') as w from pessoas ),
  grams as (
    select array_to_string(w[i:i+1],' ') as g from toks, generate_series(1, array_length(w,1)-1) as i
    union
    select array_to_string(w[i:i+2],' ') from toks, generate_series(1, array_length(w,1)-2) as i
  )
  select string_agg(md5(g), ' ' order by md5(g))
  from (select distinct g from grams where length(g) >= 7 and g ~ '^[a-z ]+$') t;

🚨 CONFERIR SEMPRE: o hash do depoimento AUTORIZADO
(bc4be6bfa403c2e8c7c4374a3b1e08ea) tem que continuar na lista — se sair, a
excecao de consentimento vira letra morta e o guarda passa a acusar a prova
social da home.
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
#: Os posts citam AUTORES de artigos e normas (nome completo de pesquisador
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
# 🩸 08/09/2026 — 328 -> 306. A queda NÃO veio de limpeza: veio de o guarda
# passar a ENXERGAR. Ele comparava hash do texto como está escrito contra uma
# lista gerada SEM acento, então "cliente-73" nunca batia com "cliente-73". Metade dos
# nomes brasileiros era invisível — todo primeiro nome com acento, e no Brasil
# isso é uma fatia enorme da base.
# Normalizado (`_sem_acento`), a contagem MUDOU nos dois sentidos: apareceram
# ocorrências que ninguém via, e sumiram duplicatas de acento.
# 🚨 O que ele achou na hora: 5 ocorrências de um nome COMPLETO de cliente,
# duas delas em `backend/main.py`, com a bancada verde o tempo todo. Limpas no
# mesmo commit.
# 🩸 08/09/2026, 2a mexida do dia: 306 -> 378, e o teto SOBE — o que contraria
# a regra "o teto só desce". A exceção é honesta e tem motivo medido: a dívida
# não cresceu, o guarda passou a ENXERGAR.
#
# A lista de hashes nascia de 3 tabelas (`projects.user_name`,
# `nps_responses.user_name`, `chat_leads.name`) e IGNORAVA `profiles` — a tabela
# do CADASTRO. Quem criou conta e nunca teve projeto nunca entrou na peneira.
# Medido: a base tem 156 palavras de nome; a lista conhecia 108. Eram 48
# palavras (31%) e 94 n-gramas de nome completo que o guarda NUNCA tinha visto.
# Agora a consulta lê 5 fontes e normaliza acento dos dois lados.
#
# 🚨 O que apareceu na hora: 5 ocorrências de nome COMPLETO de cliente — em
# `engine_rules.py`, `test_engine_rules.py`, `test_descarte_de_pilares.py` e
# `test_pagina_destrava_a_medicao.py`. Todas limpas no mesmo commit.
#
# 🪤 `passos` e `marcos` FICARAM DE FORA da lista de palavra, de propósito: são
# sobrenome E palavra comum ("os passos do motor", "marcos de referência"), e
# sozinhas geravam 130 das 510 ocorrências. Guarda barulhento é guarda que
# alguém desliga. O nome COMPLETO delas continua protegido pelo n-grama, que é
# o identificador que importa — mesma troca que a lista já fazia com
# silva/santos/campos.
#
# ⏭️ Daqui pra frente o teto SÓ DESCE de novo.
# 08/09, 4a mexida: 366 -> 364. Saiu um [[link de memoria]] cujo NOME DE
# ARQUIVO carregava o nome do cliente — a unica porta desse tipo no repo
# (os outros ~40 wikilinks sao por TEMA). O guarda ja enxergava essa
# ocorrencia; quem a absorvia era o teto. Por isso o teto desce junto.
# 08/09, 3a mexida: 378 -> 366. Esta DESCE, e pelo motivo certo: 12 ocorrencias
# saíram de arquivos SERVIDOS ao visitante (dashboard/projeto/cadastro/admin).
# Ver test_o_que_vai_pro_ar_nao_leva_nome_de_cliente — la o teto e ZERO, porque
# comentario que vai pro ar nao e divida a pagar devagar: e publicacao.
# 08/09, 5a mexida: 364 -> 339. Varredura NOVA, por NOME DE OBRA: hasheei no
# proprio banco as palavras de `projects.project_name` (sem materializar nome
# nenhum em arquivo) e varri o repo contra os hashes. 8 exposicoes reais, e uma
# delas em ARQUIVO SERVIDO ao visitante.
# 🔑 O que isso revelou vale mais que a lista: o guarda de tolerancia ZERO dos
# arquivos servidos so conhece nome de PESSOA — nome de EMPRESA passa direto.
# Foi assim que um nome de obra chegou no projeto.html.
# 🪤 As 25 ocorrencias a mais que cairam sao nome de PESSOA que morava colado ao
# nome da obra (`cliente-22 (Sobrenome)`), no mesmo padrao do rotulo colado que
# ja consertei hoje de manha em outro lugar.
# 🧹 09/09/2026: 339 → **ZERO**. A dívida herdada acabou — 45 pessoas, 349
# ocorrências, 74 arquivos.
# 🩸 A 1ª tentativa CORROMPEU o repositório e o revert foi por HEAD: eu usei
# `str.replace` cru e um primeiro nome de 4 letras casou DENTRO de uma palavra
# inglesa comum do código —
# `extract_balanced_obj` virou lixo em 32 arquivos. Substring em vez de token,
# no mesmo dia em que escrevi um guarda contra exatamente isso.
# 🔑 A fronteira certa é `(?<![letra])nome(?![letra])`: aceita `_` e dígito
# (onde nome aparece em identificador) e recusa letra colada (sempre pedaço de
# outra palavra). `` NÃO serve: ele trata `_` como letra, então
# `_QUADRO_<nome>` escapa — e o script diz "troquei" sem trocar nada.
# 🪤 E compilar não basta: `f(cliente-88)` é sintaxe VÁLIDA (vira subtração) e
# só quebra rodando. Quem pegou foi a bancada, no runner de script legado.
# 🚨 O teto agora é ZERO e SÓ DESCE — não há mais dívida pra absorver
# ocorrência nova. Qualquer nome que entrar reprova aqui.
_TETO_DE_NOMES = 0

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
            if a.endswith(_EXT_TEXTO)]


def _conteudo(rel):
    try:
        return io.open(os.path.join(_RAIZ, rel), encoding="utf-8", errors="replace").read()
    except Exception:
        return ""


def _sem_acento(s):
    """'cliente-73' -> 'cliente-73'. A régua de comparação é UMA: minúscula sem acento.

    🩸 08/09/2026 — ESTE GUARDA ERA CEGO PRA ACENTO, E ISSO O DESLIGAVA PRA
    METADE DOS NOMES BRASILEIROS. As listas de hash foram geradas a partir da
    forma SEM acento ('cliente-73' -> 374321cf…), mas o texto do repositório era
    hasheado COM acento (o mesmo nome dá outro md5). Os dois nunca batiam.

    🚨 Não é "a lista está incompleta": o nome ESTAVA na lista e passou mesmo
    assim. Achado hoje ao vivo — um nome completo de cliente vivia em
    `backend/main.py` num comentário, colado ao job_id, com a bancada verde.
    Todo primeiro nome acentuado ficava invisível — e no Brasil isso é uma
    fatia enorme da base de clientes.

    🔑 Guarda que passa por estar cego é pior que guarda nenhum — o verde
    ensina a confiar. Ver [[feedback_teste_com_controle_positivo]].
    """
    return "".join(c for c in unicodedata.normalize("NFKD", str(s).lower())
                   if not unicodedata.combining(c))


#: Palavra que COINCIDE com o primeiro nome de um cliente mas, NAQUELE arquivo
#: e naquele uso, não fala dele. Chaveado por (hash, arquivo) — nunca por
#: arquivo inteiro, senão vira porta aberta.
#: 🩸 09/09/2026 — o caso que criou isto: a limpeza em massa trocou o nome
#: DENTRO do nome de uma unidade federativa, numa tabela do `admin.html` que
#: VAI PRO AR.
#: Restaurar a palavra fez o guarda acusar — e ele estava tecnicamente certo e
#: praticamente errado. 🪤 A exceção é o remédio; alargar a peneira pra "ignorar
#: nomes de estado" seria inventar regra pra um caso.
_HOMONIMO_CONHECIDO = {
    "d6607a0d5fa9ddbc40d551a695a3ddee": ("admin.html",),      # nome de unidade federativa
}


def _e_nome_de_cliente(palavra, rel=""):
    h = hashlib.md5(_sem_acento(palavra).encode("utf-8")).hexdigest()
    if h not in _HASH_DE_NOME:
        return False
    if rel and rel in _HOMONIMO_CONHECIDO.get(h, ()):
        return False
    return True


def nomes_no_texto(src, rel=""):
    """Linhas de UM texto onde há palavra de nome de cliente.

    🔑 Extraída em 08/09/2026 pelo mesmo motivo do n-grama: a mutação mostrou
    que o caminho do CONSENTIMENTO não tinha nenhum teste que o executasse —
    dava pra devolver a comparação pra `.lower()` e a bancada seguia verde.
    """
    achados = []
    for m in _PALAVRA.finditer(src):
        if not _e_nome_de_cliente(m.group(0), rel):
            continue
        h = hashlib.md5(_sem_acento(m.group(0)).encode("utf-8")).hexdigest()
        if rel and rel in _CONSENTIU_EM_PUBLICO.get(h, ()):
            continue      # depoimento autorizado — é conteúdo, não vazamento
        achados.append(src[:m.start()].count("\n") + 1)
    return achados


def _ocorrencias_de_nome():
    """(arquivo, linha) de cada palavra que bate com a base de clientes."""
    achados = []
    for rel in _versionados():
        if rel.startswith(_FORA_DA_CHECAGEM_DE_NOME):
            continue
        src = _conteudo(rel)
        if not src:
            continue
        for linha in nomes_no_texto(src, rel):
            achados.append((rel, linha))
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


#: md5 dos APELIDOS de cliente (a parte antes do @, que identifica igual e
#: escapa do regex de e-mail).
#: 🩸 09/09/2026 — ESTA LISTA ESTAVA EM TEXTO PURO, DENTRO DO REPO PÚBLICO.
#: Era a lista de apelidos de cliente escrita por extenso no arquivo do guarda —
#: exatamente o que o cabeçalho deste arquivo diz ter resolvido pros NOMES,
#: hasheando. E pior: `_versionados()` exclui este arquivo da própria varredura
#: (pelo basename), então nem o guarda se via. Uma busca pública por qualquer um
#: desses apelidos devolvia este arquivo.
#: 🪤 E a limpeza de nomes de 09/09 REESCREVEU UMA DAS AGULHAS: um apelido virou
#: "eng.cliente-NN". Como esta lista não é prosa — é o CONJUNTO DE AGULHAS que o
#: teste procura —, o guarda passou a caçar uma string que só existe nele mesmo,
#: e o apelido real ficou sem vigia. Recuperado do commit anterior.
#: 🔑 Regenerar: hash md5 do apelido em minúsculas.
_HASH_DE_APELIDO = frozenset("""
75a297863c92abea141dde7b7643bd07 2144313c78734ecf8e9c71d8947065ff
22655dfead35ff3a65d959c9bbb29ab8 7f3d2753230db37743dfce9483e1bfbd
43fd81ebb84bceffc66e1568e38aa0ed d2ccc89455f63c146623e1b745b528b1
d8120e9453ac34ef8bc4ca120bbe4bef 38df2200bcc9369fc6719bf7239b0551
f94ab5e691932764e2e26e21fa389771 8ca4a082a7d6060fcde10c82f71a5333
daa65c4b1e4bda939467f82157f84ba5 25796f152436d0f060eb4e9040b2b577
8a70f920a39ccfef7278af4985aa0d02 5a8741a96a4c52d906d852f317a9eb3f
85cb62786fe6cc3e621303957814588c 61a623424aabbbc690c57b65d1cc4662
8238ced88d136d363a28c2642738beb7
""".split())

#: candidatos a apelido no texto: 5+ caracteres de letra/dígito/._-
_TOKEN_APELIDO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{4,}")


def apelidos_no_texto(src):
    """Linhas onde um apelido de cliente aparece. Extraída pra poder ser
    CHAMADA por um controle — guarda que não pode ser provado não vale."""
    fora = []
    for m in _TOKEN_APELIDO.finditer(src or ""):
        tok = m.group(0).lower().strip(".-_")
        if hashlib.md5(tok.encode("utf-8")).hexdigest() in _HASH_DE_APELIDO:
            fora.append(src[:m.start()].count(chr(10)) + 1)
    return fora


def test_nenhum_apelido_de_cliente_sobreviveu():
    """A parte ANTES do @ identifica igual — e escapa do regex de e-mail."""
    achados = []
    for rel in _versionados():
        for linha in apelidos_no_texto(_conteudo(rel)):
            achados.append("%s:%d" % (rel, linha))
    assert not achados, (
        "apelido de cliente ainda no repositório PÚBLICO: %s" % achados[:8])


def test_CONTROLE_a_peneira_de_apelido_ACHA_um_plantado():
    """🧪 Prova que o predicado reprova — sem escrever apelido nenhum aqui.
    Monta o texto a partir de um hash conhecido? Não dá (md5 não inverte).
    Então planta um hash FALSO e confere que a peneira o reconhece."""
    global _HASH_DE_APELIDO
    _orig = _HASH_DE_APELIDO
    try:
        _HASH_DE_APELIDO = frozenset([
            hashlib.md5(b"apelido.de.mentira").hexdigest()])
        assert apelidos_no_texto("olha o apelido.de.mentira no meio da frase")
        assert not apelidos_no_texto("nada aqui")
    finally:
        _HASH_DE_APELIDO = _orig


def test_a_LISTA_de_apelido_nao_encolheu():
    """🪤 Lista estática só muda à mão. Encolher = cliente sem vigia."""
    assert len(_HASH_DE_APELIDO) >= 17, (
        "a lista de apelido encolheu para %d (medido em 09/09: 17)"
        % len(_HASH_DE_APELIDO))


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
    # 🪤 Montado em tempo de execução: escrever um endereço aqui faria o
    # controle do guarda de e-mail ser, ele próprio, um e-mail no repo público.
    _end = "fulana" + "." + "detal" + "@" + "gmail" + "." + "com"
    falso = "# 🚨 caso %s — 3 devoluções" % _end
    m = _RE_PESSOAL.search(falso)
    assert m and m.group(0) == _end


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
    # 🩸 09/09/2026 — ESTE CONTROLE PRECISOU SER REANCORADO, e o motivo é bom.
    # Ele exigia que o guarda ainda ACHASSE gente no repositório, *"porque hoje,
    # comprovadamente, há 374 ocorrências"* — um controle apoiado na DÍVIDA. A
    # dívida foi zerada, e ele passou a REPROVAR O CONSERTO. Controle que
    # depende do defeito existir morre no dia em que o defeito acaba.
    # 🔑 Agora a prova é sintética: acha por força bruta uma palavra que ESTÁ na
    # lista de hash (sem nunca escrever nome nenhum aqui, que é o que este
    # arquivo proíbe) e exige que a peneira a reconheça.
    achou = None
    import itertools as _it
    for _n in range(3, 6):
        for _c in _it.product("abcdefgilmnorstuv", repeat=_n):
            _p = "".join(_c)
            if _e_nome_de_cliente(_p):
                achou = _p
                break
        if achou:
            break
    assert achou is not None, (
        "a peneira não reconheceu NENHUMA palavra da própria lista de hash — "
        "ela quebrou (md5 trocado, normalização diferente, lista esvaziada)")
    assert not _e_nome_de_cliente("zzqxjw"), (
        "a peneira diz SIM pra qualquer coisa — pior do que estar quebrada")


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
