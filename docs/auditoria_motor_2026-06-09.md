# Auditoria profunda do motor de extração — AI.arq

**Data:** 2026-06-09
**Lentes:** silent-failure-hunter + python-reviewer
**Escopo:** `backend/analyzer.py`, `backend/processor.py`, `backend/dwg_extractor.py`, `backend/llm_retry.py`, consolidação e orquestração em `backend/main.py` (`process_job`), `backend/spreadsheet.py`, `backend/density_calibration.py`. Cronograma fora de escopo.

---

## Resumo executivo

O motor está **sólido nas regras duras** (0-itens vira erro, default `estimado`, isolamento real, calibração só por ratio). Os problemas reais são de **borda**: uma falha de IA no caminho DXF é engolida (não entra em `sheet_errors`), o caso "qty=0 medido" é indistinguível de "qty=0 não-medido" (a armadilha Granado), e XREF em DWG não é resolvido (geometria some). Nada quebra isolamento nem promove estimativa pra confirmado indevidamente.

| Área | Grade |
|---|---|
| Regra "0 itens = erro" | 🟢 Bom (todos os caminhos cobertos via `process_job`) |
| Default confidence `estimado` | 🟢 Bom |
| Isolamento de projetos | 🟢 Bom |
| Calibração por densidade (só ratio) | 🟢 Bom |
| Silent failures | 🟡 Atenção (1 erro de IA engolido no DXF) |
| Escape hatches nos prompts | 🟡 Atenção (qty=0 fácil demais) |
| qty=0 ("não medido" vs "medido") | 🔴 Crítico de produto (Granado) |
| Classificação de layout | 🟢 Bom (ATUAL antes de NOVO, comentado) |
| ezdxf / XREF / unidades | 🟡 Atenção (XREF não resolvido; INSUNITS=0 só alerta) |
| Custo / performance | 🟢 Bom (retry com backoff+jitter; short-circuit de densidade) |

---

## 🟢 5 acertos

1. **Regra 0-itens implementada e ramificada por causa** — `main.py:2773-2796`. Distingue "IA falhou" (reprocessar grátis) de "nada quantificável" (trocar arquivo). `all_items` começa com `dxf_items` (`main.py:2480`), então o guard cobre PDF, DXF e reprocess (que reentra em `process_job`, `main.py:6452`).
2. **`analyze_sheet` nunca lança — e o caller PDF checa** — `analyzer.py:1056-1062` retorna `{"items":[], "error":...}`; `main.py:2584-2587` faz `result.get("error")` e empilha em `sheet_errors`. Exatamente a armadilha #11 do CLAUDE.md, tratada no caminho PDF.
3. **Isolamento real na calibração** — `density_calibration.py:469-475` (`check_density_anomaly`) só ALERTA, comentário explícito "nunca sobe confidence pra confirmado"; não escreve `item.quantity`. Benchmarks exigem `n_projects >= 2` e comparam ratio qty/área, nunca valor absoluto (`main.py:2743-2765`). Cumpre regra dura #2 e #3.
4. **Default `estimado` à prova de bala** — toda leitura de confidence cai em `estimado` quando inválida (`main.py:2427`, `2627`; `analyzer.py:1165`). `qty==0 & confirmado` é rebaixado pra `estimado` (`main.py:2434-2435`, `2633-2634`; `analyzer.py:1177-1179`). Toda consolidação que funde itens força `Confidence("estimado")` (`main.py:1255,1338,1457,1555`).
5. **Retry centralizado, correto e barato** — `llm_retry.py:84-138`: backoff exponencial 2→60s com jitter, respeita `Retry-After`, só retenta 429/529/5xx/timeout, propaga erro de prompt/API-key. Mais o short-circuit de densidade (`density_calibration.py:499-500`) que evita ~3s de LLM por item quando não há benchmark útil.

---

## 🔴 Críticos (P0)

### P0-1 — Erro de IA no caminho DXF é engolido (silent failure)
`main.py:2464-2466`: quando a interpretação Claude do DXF falha (timeout/sobrecarga/JSON inválido), o `except` só faz `jobs.update_field(... current_step=...)` + `print`. **Não** empilha em `sheet_errors`. Pior: `sheet_errors` só é declarado em `main.py:2489`, DEPOIS do bloco DXF (que termina ~2476) — então nem está em escopo ali.

Consequência real: projeto **só-DXF** (caso comum — DWG é o formato que "resolve" segundo a memória) cuja única chamada de IA falha por sobrecarga → `dxf_items` vazio → cai no guard de 0-itens (`main.py:2773`), mas como `sheet_errors` está vazio, dispara a mensagem ERRADA: "Nenhum item quantificável... troque o arquivo / é PDF escaneado" em vez de "IA sobrecarregada, reprocesse grátis". O usuário troca um arquivo que estava perfeito. É exatamente o espírito da armadilha #11 reaparecendo no caminho DXF.

**Fix:** declarar `dxf_errors: list[str] = []` antes do loop DXF, empilhar no `except` (`main.py:2464`), e no guard de 0-itens considerar `sheet_errors + dxf_errors`.

---

## 🟡 Médios (P1)

### P1-1 — qty=0 "não medido" indistinguível de "medido = não existe" (armadilha Granado)
`spreadsheet.py:367,424`: `value=(item.quantity if item.quantity else None)` → qty=0 vira célula vazia, com selo genérico "⚠ ESTIMADO — revisar" (`spreadsheet.py:374,429`). Não há diferença visível entre:
- "achamos divisória de vidro mas o PDF é vetorial sem texto, não deu pra medir" (Granado, 30 itens qty=0), e
- "pintura externa mencionada por completude, mas não se aplica".

O usuário vê só linha laranja vazia nos dois casos. É o cerne da reclamação Granado (02/06). O prompt até manda anotar ("Contagem visual: ... Confirmar com quadro", `analyzer.py:84`), mas isso depende da IA e não é estruturado.

**Fix de produto (decisão Pedro abaixo):** introduzir um marcador explícito "NÃO MEDIDO" (selo + ícone distinto, respeitando daltonismo: cor+ícone+texto) quando qty=0 vier de item detectado-mas-não-medido, separando-o de "estimado".

### P1-2 — Escape hatches nos prompts que deixam a IA desistir de medir
Cada um vira "saída fácil" pra retornar sem número:
- `analyzer.py:88-90` — "ESTIME pela ordem de grandeza" com exemplos de tubulação (`~50m pra 1 pavimento`, `~80m pra residência de 150m²`). São números genéricos no prompt; embora marcados estimado, encostam na borda da regra "isolamento". Reforço: trocar por "meça o traçado no CAD; só estime se não houver traçado, e declare a base do cálculo".
- `analyzer.py:516-520` — tabela "Estimativa de tubulação típica residencial (20-30m/pavimento...)". Idem: ordem de grandeza fixa no prompt. Aceitável como último recurso, mas é o tipo de número que o usuário pode confundir com medição.
- `PROMPT_LAYOUT_NOVO` (`analyzer.py:680-682`) é o BOM contra-exemplo: "a QUANTIDADE DEVE ser medida de verdade pelas cotas — nunca deixar em branco quando a planta permite medir". Replicar essa firmeza nos prompts de PONTOS e nas seções de tubulação.
- `analyzer.py:95` — "vb=0 melhor que un=0" pode virar fuga pra item mensurável. O system já alerta contra isso (`analyzer.py:68-74`), mas a coexistência das duas regras é ambígua.

### P1-3 — XREF em DWG/DXF não é resolvido → geometria some
`dwg_extractor.py`: `msp.query("INSERT")` é não-recursivo (comentado em `:869`) e o código **filtra** blocos com nome de xref (`:904,911`). Não há `bind`/`explode`/`virtual_entities` de xref. Se o projeto referencia DWG externo (o caso Granado tinha xref), as paredes/hachuras/blocos vivem na definição do xref e **não aparecem no modelspace** → extração quase vazia → erro genérico de 0-itens. É o equivalente-DWG da armadilha Granado, ainda latente.

**Fix:** detectar xrefs (`doc.blocks` com flag de xref / nome com `.dwg`) e, quando presentes, ou (a) tentar resolver via ODA com flag de bind na conversão, ou (b) emitir warning explícito "projeto usa referências externas (XREF) não anexadas — exporte com 'bind/insert' ou mande o PDF". Hoje some silenciosamente.

### P1-4 — INSUNITS=0 assume mm sem corrigir, só alerta
`dwg_extractor.py:241-242`: INSUNITS=0 ("sem unidade") cai no default mm (`:257`, fator 0.001). `_validate_unit_factor` (`:319-356`) detecta linha > 500m ou < 5cm mas **não auto-corrige** (docstring `:343` "Flag but don't auto-fix"). Um desenho realmente em metros com INSUNITS=0 sai 1000× menor; o alerta vai pro prompt via `metadata["alerta_unidade"]` (`:860-861`), mas a IA recebe áreas/comprimentos já errados — e tende a confiar no número "medido".

**Fix:** quando `max_len < 0.05m` com fator mm, auto-tentar fator metros (×1000) e re-validar; logar a correção. Pelo menos rebaixar pra estimado tudo que vier de DXF com `alerta_unidade` presente.

### P1-5 — Item-parse com `except: continue` mudo engole itens individuais
`main.py:2460` e `:2664` (e `analyzer.py:1200`): o loop de itens usa `except: continue` sem log. Um item com formato inesperado (qty não-numérica não-tratada, campo faltando) some sem rastro. Em volume, "5 luminárias viraram 3" sem ninguém saber. `analyzer.py:1200` ao menos faz `print`. Padronizar: logar `item_data` descartado nos três pontos.

---

## ⚪ Baixos (P2)

### P2-1 — `generate_budget_data` (caminho DXF puro, sem IA) hardcoda `confidence:"confirmado"` e nomes de disciplina errados
`dwg_extractor.py:1361,1381,1401` marcam tudo `"confirmado"`; `_CATEGORY_TO_DISCIPLINE` (`:1325-1337`) usa "Prevenção e Combate a Incêndio" e "Instalações Elétricas" — nomes que NÃO existem em `valid_disciplines` (`main.py:2611-2618`, que usa "Incêndio e Segurança" / "Instalações Elétricas e Dados"). **Hoje é inócuo**: a função só roda no `__main__` CLI (`dwg_extractor.py:1452`); produção usa Claude pra interpretar o DXF. Mas é uma bomba-relógio — se alguém religar essa função como fallback, viola a regra dura #1 (confirmado sem medição-via-IA) e gera disciplina órfã. Marcar `verificar`/`estimado` e alinhar os nomes, ou deletar a função.

### P2-2 — Pass 1 da consolidação preserva confidence da descrição mais longa
`main.py:1259-1261`: quando qtys são idênticas, mantém o item de descrição mais longa sem reconciliar confidence. Se um for `confirmado` e outro `estimado` (mesma qty, mesma unidade, vindos de pranchas diferentes), pode manter `confirmado`. Risco baixo (qty idêntica sugere mesma fonte), mas a regra dura pede o oposto: na dúvida, `estimado`. Rebaixar quando o grupo mistura confidences.

### P2-3 — Pass 4 (luminárias) preserva `best.confidence` ao somar cross-prancha
`main.py:1503`: comentário "preserva confirmado se todos eram", mas usa `best.confidence` (do item de descrição mais longa), não um AND de todos. Somar contagens de pranchas diferentes é, por definição, uma operação que deveria virar `estimado` (a soma não é "lida" de lugar nenhum). Forçar `estimado` aqui.

### P2-4 — `verificar` ainda é aceito apesar de "não usar verificar"
O system prompt repete "não use verificar" (`analyzer.py:262,303`), mas `Confidence.VERIFICAR` existe (`models.py:25`) e é aceito em 3 validações (`main.py:2427,2627`; `analyzer.py:1165`) e tratado como laranja na planilha (`spreadsheet.py:374`). Inofensivo (vira laranja), mas é dívida: ou remover o enum ou parar de listá-lo como válido.

---

## 🛠️ Top 10 fixes que Claude aplica sem decisão humana

1. **[P0-1]** Criar `dxf_errors=[]` antes do loop DXF, empilhar no `except` `main.py:2464`, e somar em `sheet_errors + dxf_errors` no guard de 0-itens (`main.py:2774`). Corrige mensagem errada em projeto só-DXF.
2. **[P1-5]** Trocar os 3 `except: continue` mudos (`main.py:2460,2664`; conferir `analyzer.py:1200`) por log do `item_data` descartado.
3. **[P1-4]** Em `_validate_unit_factor`, quando `max_len < 0.05` com fator mm, retornar fator ×1000 (metros) + warning de auto-correção; e rebaixar pra `estimado` itens de DXF com `metadata["alerta_unidade"]`.
4. **[P1-3]** Adicionar detecção de XREF em `extract_dxf` e, se presente e geometria ~vazia, gerar warning explícito ("referências externas não anexadas") em vez de cair no erro genérico.
5. **[P2-3]** Pass 4 luminárias: forçar `Confidence("estimado")` ao somar cross-prancha (`main.py:1503`).
6. **[P2-2]** Pass 1: se o grupo mistura `confirmado`+`estimado`, manter `estimado` (`main.py:1259-1261`).
7. **[P2-1]** Em `generate_budget_data`, trocar `"confirmado"` por `"estimado"` e alinhar `_CATEGORY_TO_DISCIPLINE` aos nomes de `valid_disciplines` (ou marcar a função como dead-code/CLI-only no docstring).
8. **[P1-2]** Reforçar `PROMPT_PONTOS` (`analyzer.py:455`) com a firmeza do `PROMPT_LAYOUT_NOVO` ("meça o traçado; só estime se não houver"), e marcar as tabelas de "tubulação típica" (`analyzer.py:516-520`) explicitamente como "último recurso, declare na observação".
9. **[P2-4]** Decidir o destino de `verificar`: remover de `valid` lists ou do enum. Aplicar a escolha consistentemente.
10. **[P1-1 parcial / preparatório]** Adicionar campo estruturado `measured: bool` (ou flag em `observations`) quando qty=0 vier de item detectado-mas-não-medido, pra a planilha conseguir distinguir — pré-requisito do P1-1 abaixo (a UI da planilha é a parte que precisa do OK do Pedro).

---

## ❓ Decisão pra Pedro

**Como mostrar "encontramos mas não medimos" (qty=0 não-medido) na planilha?** (caso Granado)

Hoje, item que a IA detectou mas não conseguiu medir (PDF vetorial sem texto, ou DWG com xref) vira **célula de quantidade vazia + laranja "estimado"** — igualzinho a um item que simplesmente não se aplica. O arquiteto não sabe se precisa medir aquilo na mão ou se pode ignorar.

Proposta: criar um **3º estado visual** "⊘ NÃO MEDIDO — informar quantidade" (cor + ícone + texto, pra respeitar daltonismo), distinto de "⚠ ESTIMADO — revisar". Isso muda a aparência da planilha que os ~8 usuários já conhecem e mexe na legenda de cores/símbolos.

Preciso do teu OK em: (a) criar mesmo o 3º estado, ou manter só 2 e melhorar o texto da observação? (b) se sim, qual ícone/rótulo prefere? O resto da auditoria (P0-1, P1-3, P1-4, etc.) eu aplico sem precisar de ti.
