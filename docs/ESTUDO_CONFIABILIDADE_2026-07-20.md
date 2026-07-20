# 🛡️ Estudo de Confiabilidade do Motor — 2026-07-20

> Por que cliente novo bate em erro no processamento — e o plano pra blindar.  
> Estudo multi-agente: 6 frentes + verificação adversarial + síntese (13 agentes, 0 erros).  
> Gatilho: incidente Rodrigo (projeto estrutural, 6 falhas por rótulo de erro mascarado).

## Resumo pro Pedro

Pedro, descobrimos por que cliente novo bate em erro e às vezes fica "processando" pra sempre. A causa raiz da maioria dos casos NÃO é "IA sobrecarregada" — o sistema estava colando esse rótulo errado em erros que são definitivos (foi exatamente isso que prendeu o Rodrigo em loop: ele reprocessava, dava o mesmo erro, reprocessava de novo). O plano ataca cinco frentes, em ordem do que dá mais alívio com menos risco: (1) parar de chamar de "sobrecarga temporária" o que na verdade é erro definitivo — só usar esse rótulo quando for REALMENTE o provedor de IA fora do ar; (2) garantir que nenhum projeto fique rodando eternamente — se travar, vira erro honesto com botão de reprocessar; (3) reprocessar SEMPRE funcionar e nunca gastar seu "1 grátis" quando a tentativa falha; (4) você ser avisado NA HORA quando um cliente novo bate em erro, já com a causa de verdade (não o rótulo mascarado); (5) avisar o cliente ANTES de pagar quando o arquivo claramente não vai medir. Começamos hoje pelos seis consertos rápidos e seguros (baixo risco), e deixamos os refactors pesados e os que mexem na medição pra depois, sempre com teste antes de ligar. Regra nº1 intacta: nada de fingir sucesso com planilha vazia.

## 📜 Contrato de Confiabilidade

- Nenhum erro permanente e rotulado como transitorio: so dizer 'servidores de IA sobrecarregados / temporario' com PROVA de 429/529/timeout. 404/401/403/413/invalid_request/surrogate/objeto-AEC nunca viram 'reprocesse, e o provedor'.
- 0 itens NUNCA vira 'done' — sempre erro honesto (regra nº1 preservada em todos os fixes).
- Todo job termina em estado terminal observavel (done OU error). Nenhum job fica preso em 'queued'/'processing' pra sempre: heartbeat + watchdog transformam thread morta ou travada em erro recuperavel.
- O semaforo de 1-job nunca fica preso indefinidamente; um job travado libera a fila com erro honesto ao cliente — e sem rodar 2 jobs em paralelo (sem reintroduzir o OOM que o semaforo evita).
- Reprocessar SEMPRE disponivel quando o projeto esta em 'error'; um reprocesso que FALHA nunca consome a cota gratis do no original.
- A acao certa concorda entre TELA, E-MAIL e DASHBOARD: se e reprocessavel diz reprocessar nos tres; se e trocar arquivo diz trocar nos tres. Fim do 'tela manda reprocessar, email manda trocar o arquivo'.
- O texto do card de erro sempre bate com o botao oferecido (transitorio -> Reprocessar gratis; problema do arquivo -> Enviar outro).
- Pedro e avisado no 1º projeto de conta nova que falha, e em falhas seguidas do mesmo cliente, JA com a causa tecnica real (do error_log), nao com o rotulo que o cliente viu.
- Quando o alerta pro Pedro nao e entregue (SMTP fora), fica registrado como erro critico no error_log — nunca some em silencio.
- O tipo/status do erro-raiz e preservado ate a classificacao (nunca mais achatado pra string antes de decidir transitorio vs permanente); a decisao e por tipo, nao por adivinhar substring no texto que nos mesmos escrevemos.

## ⚡ Quick-wins — fazer JÁ (alto impacto, baixo risco)

1. Lock no JobsStore (backend/main.py:1661-1676 e 998-1002): serializa as escritas do JSON de jobs. Mata a escrita-fantasma que sobrescreve 'error' de volta pra 'queued'/'processing' e semeia o job orfao. Risco quase zero, secao critica curtissima.

2. Blacklist de status no bloco ai_errors + preservar categoria do erro-raiz (backend/main.py:4635-4659 + 4122-4123 e 4356-4357 + backend/analyzer.py:1143): guardar (tipo/status, msg) em vez de so str, e so cair em 'sobrecarregada' com 429/529/timeout — 404/401/403/413/invalid_request viram mensagem honesta. Mata o rotulo errado fleet-wide que causou o loop do Rodrigo.

3. Alerta terminal com o erro REAL (backend/main.py:1854-1857 + 1832): fazer o join com error_log por job_id e mostrar a causa tecnica real ao lado do rotulo que o cliente viu. Custo minimo, e o que faz o Pedro parar de investigar as cegas.

4. Escotilha 'Parece travado? Reprocessar' no spinner (projeto.html:1257-1330): oferecer botao acionavel quando o progresso real trava, em vez de texto passivo aos 20min. Cliente nunca mais fica olhando spinner eterno. So UI.

5. estimate-price devolve warnings[] (backend/main.py:8210-8232 + backend/pricing.py:140 + dashboard.html:1938): precheck barato reaproveitando o arquivo ja em disco, avisando ANTES de pagar (inclusive no 1º projeto gratis). Campo novo e opcional, front antigo ignora.

6. _log_error quando o alerta ao Pedro nao e entregue (backend/main.py:1861 no ramo _ok=False): registra alerta critico quando o SMTP esta fora, fechando o unico ponto cego onde o aviso sumiria de vez.

## 📋 Plano priorizado (25 itens)

| # | Fix | Impacto | Esforço | Onde |
|---|-----|---------|---------|------|
| 1 | Lock no JobsStore (threading.Lock em __setitem__/update_field/_save_jobs) pra impedir status-fantasma por escrita concorrente | alto | baixo | backend/main.py:1661-1676, 998-1002 |
| 2 | Preservar a categoria/tipo do erro-raiz no loop DXF/PDF (guardar tupla (categoria,msg) em vez de achatar pra str) | alto | baixo | backend/main.py:4122-4123, 4356-4357; backend/analyzer.py:1143 |
| 3 | Inverter o default do bloco ai_errors: so 'sobrecarregada' com prova de 429/529/timeout; blacklist de status (404/401/403/413/invalid_request) vira mensagem honesta | alto | baixo | backend/main.py:4635-4659; backend/llm_retry.py:89-95 |
| 4 | Alerta terminal existente passa a mostrar a causa REAL do error_log (join por job_id) ao lado do rotulo que o cliente viu | alto | baixo | backend/main.py:1854-1857, 1832 |
| 5 | Escotilha de fuga no spinner: 'Parece travado? Reprocessar' quando o progresso real fica parado (nao so por tempo) | alto | baixo | projeto.html:1257-1330, 1328 |
| 6 | estimate-price devolve warnings[] — precheck barato que avisa ANTES de pagar (reaproveita arquivo ja em disco) | alto | baixo | backend/main.py:8210-8232, 8227, 8235; backend/pricing.py:140; dashboard.html:1938 |
| 7 | Alerta imediato quando o 1º projeto de conta nova falha, e em falhas seguidas do mesmo cliente, ja com a causa real (dedup por email+causa+dia) | alto | medio | backend/main.py:1849-1852, 4967 |
| 8 | Registrar erro critico no error_log quando o alerta ao Pedro NAO e entregue (SMTP persistente fora) | medio | baixo | backend/main.py:1861, 1062 |
| 9 | Card de erro com a acao certa por tipo de falha (transitorio -> Reprocessar gratis; problema do arquivo -> Enviar outro), espelhando a classificacao do backend | alto | medio | projeto.html:144-153, 1334-1399, 764-773 |
| 10 | Alinhar a instrucao do erro 400/permanente-nosso entre tela, e-mail e dashboard (3ª categoria de copy: 'erro tecnico nosso, reprocesse') | medio | medio | backend/main.py:4646-4652, 4989, 1191-1211 |
| 11 | Heartbeat + staleness no skip_local_active (mata o job orfao na raiz) — adicionar campo de tempo ao ProcessingStatus e checar liveness, nao presenca-no-store | alto | medio | backend/main.py:1779-1783, 1978-1983; backend/models.py:66-73 |
| 12 | Timeout no semaforo + watchdog por job (mata o deadlock silencioso que congela a fila) | alto | medio | backend/main.py:3237, 3242 |
| 13 | Retry in-place SEM custo e sem novo arquivo pra falha transitoria (caminho limpo que sempre funciona) | alto | medio | backend/main.py:10474, 10486-10487, 10535-10536, 10584 |
| 14 | So gastar o reprocesso gratis quando o filho CONCLUIR (estornar/nao contar na falha) + guard anti-spam 'ja existe filho queued?' | medio | medio | backend/main.py:10442-10452, 10362-10368; projeto.html:1963-1969 |
| 15 | Tirar o preview de CAD da concorrencia com a extracao (serializar pra DEPOIS, pular por os.path.getsize) | medio | baixo | backend/main.py:3394, 3541 |
| 16 | Cap honesto que avisa cedo por RAM PREVISTA (usar psutil.virtual_memory().available real) e marca o caso como TERMINAL/nao-reprocessavel | medio | medio | backend/dwg_extractor.py:1178-1184, 1169-1173 |
| 17 | Nao convidar a reprocessar arquivo garantido a falhar — desabilitar o reprocess-box SO nas causas detectaveis como irreprocessaveis (PDF escaneado/DWG-AEC), nunca em todo 0-itens | medio | medio | projeto.html:1959-2002, 767 |
| 18 | Persistir error_category em projects e o auto-retry filtrar por ela (aposentar o _TRANSIENT_ERR_RX na fonte; migration nullable com fallback regex enquanto vazia) | medio | medio | backend/main.py:1834, 1800-1802 |
| 19 | Precheck de quantificabilidade server-side compartilhado por upload E reprocess (le so header/counts com cap de tamanho + try/except que degrada) | medio | alto | backend/main.py:5109-5132, 10319-10440; backend/dwg_extractor.py:880, 1178 |
| 20 | Telemetria de RAM por etapa (logar RSS pro error_log que o Pedro le) + tentativa de saida parcial honesta antes do SIGKILL | medio | medio | backend/main.py:4128-4143, 4459 |
| 21 | Painel/endpoint admin 'Clientes com falha nas ultimas 24h' com causa real, agrupado por email e com flag de 1º-projeto (via Python no endpoint, estilo admin_activity) | medio | medio | backend/main.py (endpoint admin estilo admin_activity; RPC admin_ops) |
| 22 | Deteccao deploy-vs-crash duravel + drain no shutdown (handler SIGTERM/atexit marca marcador duravel) | medio | medio | backend/main.py:1872-1893, 2050 |
| 23 | Deteccao de proxy/AEC em DXF como AVISO nao-bloqueante (condicao AND: proxy>0 E mensuravel~0, nunca OR) | baixo | medio | dashboard.html:2101; backend/dwg_extractor.py:1729; backend/main.py:3610-3613 |
| 24 | Gate upfront distinguindo PDF escaneado/imagem de vetorial-sem-cota (limiar conservador, so avisa quando e MUITO claramente imagem) | baixo | baixo | dashboard.html:2186-2204; backend/main.py:4667 |
| 25 | Alinhar a cobertura da varredura AEC do navegador com a do servidor (exibir o aviso autoritativo do servidor em vez de confiar no chunk parcial do browser) | baixo | baixo | dashboard.html:2250-2254; backend/dwg_extractor.py:898-907 |

### Por quê de cada prioridade

**1. Lock no JobsStore (threading.Lock em __setitem__/update_field/_save_jobs) pra impedir status-fantasma por escrita concorrente**  
Recovery, request e processamento escrevem o mesmo JSON sem trava (lost-update): uma entrada 'error' pode ser sobrescrita de volta por 'queued'/'processing' — que e justamente o que semeia o job orfao. Melhor relacao impacto/risco de toda a lista.  
_(backend/main.py:1661-1676, 998-1002)_

**2. Preservar a categoria/tipo do erro-raiz no loop DXF/PDF (guardar tupla (categoria,msg) em vez de achatar pra str)**  
Keystone: hoje type(e)/status_code sao jogados fora antes da decisao, obrigando o guard a re-adivinhar por substring. Sem isso, o fix de classificacao honesta nao tem como decidir por status. analyzer.py tambem precisa propagar o tipo senao o caminho PDF continua cego.  
_(backend/main.py:4122-4123, 4356-4357; backend/analyzer.py:1143)_

**3. Inverter o default do bloco ai_errors: so 'sobrecarregada' com prova de 429/529/timeout; blacklist de status (404/401/403/413/invalid_request) vira mensagem honesta**  
Hoje tudo que nao casa o whitelist de 5 tokens cai em 'IA sobrecarregada, reprocesse' — id de modelo errado numa env-var faria TODO DXF dar 404 e todo cliente ver 'sobrecarregada' + loop. Foi a inversao que prendeu o Rodrigo. O paliativo de blacklist funciona ja com o item 2.  
_(backend/main.py:4635-4659; backend/llm_retry.py:89-95)_

**4. Alerta terminal existente passa a mostrar a causa REAL do error_log (join por job_id) ao lado do rotulo que o cliente viu**  
O email de alerta usa error_message ROTULADO ('sobrecarregado'/'reinicio'); a causa real ('invalid high surrogate', tipo da excecao) ja esta gravada no error_log — falta so o join. Melhor ganho/custo da lane; se a busca falhar, cai no rotulo atual (fallback natural).  
_(backend/main.py:1854-1857, 1832)_

**5. Escotilha de fuga no spinner: 'Parece travado? Reprocessar' quando o progresso real fica parado (nao so por tempo)**  
get_status devolve 200 pra qualquer job no dict; job orfao semeado em 'queued' cuja thread morreu responde 200 pra sempre e a UI so encerra por done/error/404 que nunca chega — aos 20min mostra so texto passivo. Independe do fix de recovery no backend. Botao chama o retry-sem-custo (item 13), nao /reprocess.  
_(projeto.html:1257-1330, 1328)_

**6. estimate-price devolve warnings[] — precheck barato que avisa ANTES de pagar (reaproveita arquivo ja em disco)**  
estimatePriceForFiles roda em TODO upload novo, inclusive o 1º gratis — alcanca exatamente a '1ª impressao do cliente novo', a dor nº1. Arquivos ja estao em disco ali; rodar o precheck dentro do try (antes do finally que apaga). Campo novo/opcional, front antigo ignora, nao altera preco.  
_(backend/main.py:8210-8232, 8227, 8235; backend/pricing.py:140; dashboard.html:1938)_

**7. Alerta imediato quando o 1º projeto de conta nova falha, e em falhas seguidas do mesmo cliente, ja com a causa real (dedup por email+causa+dia)**  
Nao existe deteccao de '1º projeto de conta nova falhou' nem 'N falhas do mesmo email' — o cenario Rodrigo (6 tentativas) so apareceu porque o Pedro reparou. Cobre a DOR nº1 (1ª impressao). Embrulhar em try/except; para transitorios que cicatrizam sozinhos, deixar o streak pro sweep pra nao virar ruido. Subsume o 'agrupar por cliente'.  
_(backend/main.py:1849-1852, 4967)_

**8. Registrar erro critico no error_log quando o alerta ao Pedro NAO e entregue (SMTP persistente fora)**  
_notify_admin e canal unico best-effort; se o SMTP esta fora de vez, o alerta nunca vira registro visivel. Um _log_error(stage='alert:admin', severity='critical') no ramo de falha e barato e garante rastreabilidade via MCP mesmo sem email.  
_(backend/main.py:1861, 1062)_

**9. Card de erro com a acao certa por tipo de falha (transitorio -> Reprocessar gratis; problema do arquivo -> Enviar outro), espelhando a classificacao do backend**  
Hoje o erro-block so tem 'Enviar outro arquivo' + 'Reportar', enquanto a mensagem transitoria manda literalmente 'e so reprocessar — e gratis': texto x acao nao batem. So UI, reusa endpoints existentes. A regex do front tem que espelhar exatamente a do backend — por isso vem depois dos itens 2/3.  
_(projeto.html:144-153, 1334-1399, 764-773)_

**10. Alinhar a instrucao do erro 400/permanente-nosso entre tela, e-mail e dashboard (3ª categoria de copy: 'erro tecnico nosso, reprocesse')**  
A tela levanta 'problema tecnico, reprocesse' mas essa msg nao casa o regex transitorio -> email manda 'seu arquivo esta ruim, troque'. Contradicao verificada. Como o scrub ja limpa o surrogate, reprocessar REALMENTE resolve — o email e que esta errado. Alternativa conservadora: corrigir so a copy/classificacao do email.  
_(backend/main.py:4646-4652, 4989, 1191-1211)_

**11. Heartbeat + staleness no skip_local_active (mata o job orfao na raiz) — adicionar campo de tempo ao ProcessingStatus e checar liveness, nao presenca-no-store**  
O sweep pula qualquer job local em 'queued'/'processing' sem checar se a thread esta viva; se a thread do resume morre (OOM), o job encalha em 'queued' e o sweep nunca o resgata dentro do processo. Precisa de campo novo em models.py + janela folgada (8-10min, acima da prancha mais lenta) reaproveitando o checkpoint por prancha pra nao reprocessar em dobro.  
_(backend/main.py:1779-1783, 1978-1983; backend/models.py:66-73)_

**12. Timeout no semaforo + watchdog por job (mata o deadlock silencioso que congela a fila)**  
Semaphore(1) com 'with' sem timeout: num HANG real (rede sem timeout, ODA travado) o semaforo nunca solta e TODO upload seguinte fica preso em 'queued', sem erro nem botao. Watchdog marca erro honesto + solta a fila. CAVEAT: nao mata a thread-zumbi (Python), entao combinar com timeouts DUROS nas chamadas externas pra o HANG virar excecao e o 'with' soltar sozinho, senao ha risco de 2 jobs em paralelo (OOM).  
_(backend/main.py:3237, 3242)_

**13. Retry in-place SEM custo e sem novo arquivo pra falha transitoria (caminho limpo que sempre funciona)**  
add_file_and_reprocess exige >=1 arquivo em dois pontos; afrouxar isso (mantendo o guard 409 anti-duplo e o guard de storage vazio) da um retry idempotente que re-baixa os mesmos arquivos, limpa error_message e nao toca reprocess_count. Usar flag is_retry dedicada em vez de reciclar is_complement (senao o email diz 'medindo pelo CAD que voce anexou' sem nada anexado).  
_(backend/main.py:10474, 10486-10487, 10535-10536, 10584)_

**14. So gastar o reprocesso gratis quando o filho CONCLUIR (estornar/nao contar na falha) + guard anti-spam 'ja existe filho queued?'**  
increment_reprocess_count roda no disparo, antes da thread do filho, sem depender do sucesso — um reprocesso que falha queima a cota do no original. O beco sem saida e menor do que parecia (ha escotilha via cadeia de filhos), mas contar cota num reprocesso que falhou e errado. Cuidado: tirar o increment do disparo abre janela de spam — precisa do guard de filho ja em andamento.  
_(backend/main.py:10442-10452, 10362-10368; projeto.html:1963-1969)_

**15. Tirar o preview de CAD da concorrencia com a extracao (serializar pra DEPOIS, pular por os.path.getsize)**  
_render_cad_previews_bg dispara como daemon ANTES do loop de extracao; o semaforo serializa jobs, nao as 2 threads do mesmo job -> RAM concorrente no dyno de 2GB. Preview e cosmetico (botao 'Ver prancha'), nao toca medicao; move-lo pra depois so atrasa a imagem em segundos. (O pico de matplotlib ja e barrado por subprocesso+guarda de entidades, entao o ganho e menor que 'causa nº1', mas o fix e barato e correto.)  
_(backend/main.py:3394, 3541)_

**16. Cap honesto que avisa cedo por RAM PREVISTA (usar psutil.virtual_memory().available real) e marca o caso como TERMINAL/nao-reprocessavel**  
O teto de 150MB e por bytes de disco, mas ezdxf infla 5-10x; o buraco que sobra e o DXF heavy-BLOCKS onde o dxf_slim devolve None (caso AFP) e o readfile carrega tudo -> OOM/SIGKILL mascarado de 'servidor reiniciou'. Recusa honesta > SIGKILL cego (regra nº1). Calibrar com DXFs reais e logar previsto x real ANTES de ligar a recusa dura, pra nao recusar cedo demais em dyno ocioso.  
_(backend/dwg_extractor.py:1178-1184, 1169-1173)_

**17. Nao convidar a reprocessar arquivo garantido a falhar — desabilitar o reprocess-box SO nas causas detectaveis como irreprocessaveis (PDF escaneado/DWG-AEC), nunca em todo 0-itens**  
renderReprocess so olha reprocess_count, nunca o tipo do erro; num 0-itens o box aparece habilitado com '1x gratis' e o clique re-roda os MESMOS arquivos -> mesmo 0 itens, queimando o gratis. MAS 0-itens por motor antigo PODE medir com motor novo — por isso restringir so as causas comprovadamente irreprocessaveis (a deteccao de PDF-escaneado ja existe no upload), mantendo 'Enviar outro'.  
_(projeto.html:1959-2002, 767)_

**18. Persistir error_category em projects e o auto-retry filtrar por ela (aposentar o _TRANSIENT_ERR_RX na fonte; migration nullable com fallback regex enquanto vazia)**  
O auto-retry decide transitorio por regex na string que nos mesmos escrevemos — infra transitoria sem keyword PT (Supabase 5xx, 'Connection refused') nunca re-tenta; nossa msg com 'sobrecarregad' sempre re-tenta. Persistir a categoria resolve na fonte, mas depende do classificador (item 2) pra ter o que gravar. Coluna nullable degrada graciosamente. Fazer depois.  
_(backend/main.py:1834, 1800-1802)_

**19. Precheck de quantificabilidade server-side compartilhado por upload E reprocess (le so header/counts com cap de tamanho + try/except que degrada)**  
/api/process so valida assinatura+tamanho de DWG; DXF/PDF passam sem precheck, e o reprocess nao roda precheck nenhum. Curto-circuita a classe 'nao mede sem consertar' detectavel barato (AEC/proxy/scanned) antes de pagar a conversao. NAO cobre o surrogate do Rodrigo (esse ja e tratado pelo scrub). Risco real: abrir ezdxf.readfile no thread do UPLOAD pode OOM o web worker — ler so header/counts com cap e try/except.  
_(backend/main.py:5109-5132, 10319-10440; backend/dwg_extractor.py:880, 1178)_

**20. Telemetria de RAM por etapa (logar RSS pro error_log que o Pedro le) + tentativa de saida parcial honesta antes do SIGKILL**  
Nao ha guarda de RAM dentro do process_job. Como TELEMETRIA (RSS por etapa no error_log) e valioso e barato — da ao Pedro a causa real do OOM. A 'parcial honesta' e best-effort, nao garantia: a guarda so mede nas fronteiras do loop, e o salto ate OOM pode ser rapido demais; tratar como backstop, nao como recuperacao confiavel.  
_(backend/main.py:4128-4143, 4459)_

**21. Painel/endpoint admin 'Clientes com falha nas ultimas 24h' com causa real, agrupado por email e com flag de 1º-projeto (via Python no endpoint, estilo admin_activity)**  
admin_ops ja retorna motor_errors (causa real) e recent_failures (cliente+rotulo) no mesmo payload, cruzaveis por job_id A MAO. Falta o join automatico, o agrupamento por cliente e a flag de 1º-projeto (casa com o item 7). Read-only atras de _require_admin; fazer em Python evita mexer na RPC. Daltonismo: cor+icone+texto no card.  
_(backend/main.py (endpoint admin estilo admin_activity; RPC admin_ops))_

**22. Deteccao deploy-vs-crash duravel + drain no shutdown (handler SIGTERM/atexit marca marcador duravel)**  
_restart_foi_deploy e best-effort e retorna False em qualquer ambiguidade -> deploy classificado como crash gasta auto_resume_count. No caso comum a versao muda e ja acerta; a falha so aparece em ambiguidade (regex/rede). Endurecimento legitimo, nao bug ativo, e o impacto de 'job morto no meio' ja e mitigado pelo checkpoint por prancha. Preferir errar pro lado 'deploy'. Fazer depois dos criticos.  
_(backend/main.py:1872-1893, 2050)_

**23. Deteccao de proxy/AEC em DXF como AVISO nao-bloqueante (condicao AND: proxy>0 E mensuravel~0, nunca OR)**  
O front so checa AEC em .dwg; DXF passa direto. Ja existe rede pos-extracao (extracao_esteril -> aviso honesto), entao o cliente NAO fica preso hoje — o ganho e so antecipar/baratear o aviso. Classe especulativa (nao aparece na taxonomia dos 45 dias). Risco: classificar DXF estrutural legitimo (so LINE/aco) como 'proxy' e assustar a toa — por isso a condicao AND.  
_(dashboard.html:2101; backend/dwg_extractor.py:1729; backend/main.py:3610-3613)_

**24. Gate upfront distinguindo PDF escaneado/imagem de vetorial-sem-cota (limiar conservador, so avisa quando e MUITO claramente imagem)**  
checkPdfTextAndWarn so conta caracteres e sempre diz 'PDF vetorial sem cotas', mesmo pra raster puro. Classe de baixa frequencia (nao esta na taxonomia dos 45 dias) e ja recebe msg honesta pos-IA — ganho marginal. Risco: falso-positivo em PDF vetorial denso -> exige limiar bem conservador.  
_(dashboard.html:2186-2204; backend/main.py:4667)_

**25. Alinhar a cobertura da varredura AEC do navegador com a do servidor (exibir o aviso autoritativo do servidor em vez de confiar no chunk parcial do browser)**  
O browser le so 8MB head + 4MB tail; o servidor varre o arquivo inteiro. Marcador AEC no miolo de DWG grande -> browser da falso 'OK'. Baixissimo valor: e aviso nao-bloqueante e o servidor ja recupera; ninguem trava. Higiene, nao confiabilidade — fazer so quando o resto estiver estavel. Nao re-varrer o arquivo inteiro no browser (trava a UI em DWG de 100MB).  
_(dashboard.html:2250-2254; backend/dwg_extractor.py:898-907)_

## 🕓 Deixar pra depois (com o porquê)

- Classificador central com excecoes TIPADAS em todos os pontos de raise do process_job (~10k linhas) — refactor pesado e a mudanca mais arriscada da lista, e majoritariamente redundante com os fixes de preservar-categoria + inverter-default + persistir-error_category. So encarar se sobrar dor depois do incremental; manter o regex como fallback.
- Slim ciente de BLOCKS / podar blocos orfaos (backend/dxf_slim.py:58 e docstring L17) — risco MEDIO-ALTO a regra nº1: podar um bloco que esta referenciado (INSERT aninhado, msp.query nao-recursivo em dwg_extractor.py:1285-1287) dropa geometria e PERDE medicao silenciosamente. So ligar com golden test novo usando um DXF de blocks pesado real (regression_motor.py + golden_motor.json), e depende do cap de RAM rodar antes. Pra o caso AFP 22MB quem salva e o cap honesto, nao este.
- Segundo canal de alerta (push/WhatsApp) — escopo maior; o _log_error critico ja garante rastreabilidade via MCP mesmo com email fora. Adiar.
- Agrupar alerta por cliente como fix isolado (obs lane #5) — subsumido pelo alerta 1º-projeto/falhas-seguidas (item 7); fazer separado brigaria com o dedup e poderia engolir o 2º projeto do mesmo cliente com causa diferente no mesmo dia. Decidir o modelo de dedup dentro do item 7 (por email+causa+dia, nao so email+dia).
- Deteccao proxy/AEC em DXF, gate de PDF escaneado, e alinhar varredura AEC browser vs servidor — classes raras ou especulativas (nao aparecem na taxonomia de falhas dos 45 dias) e ja cobertas por mensagem honesta pos-extracao (extracao_esteril). So priorizar se aparecerem nas falhas reais. DESCARTADOS por serem REFUTADO: orcamento de paginas do job inteiro (e problema de duracao, nao de OOM; memoria ja e por-pagina) e dica de 'DWG versao nova demais AC1032+' (o ODA le 2018+ nativamente; causa nao demonstrada).

---
_Só entraram fixes CONFIRMADO/PLAUSÍVEL na verificação adversarial._