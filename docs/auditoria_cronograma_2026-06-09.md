# Auditoria do módulo CRONOGRAMA — 2026-06-09

Auditoria sênior das 3 ondas (paleta slate + editor live · drag-and-drop · dependências FS + marcos + grupos).
Arquivos: `cronograma.html` (frontend), `backend/cronograma.py` (motor), `backend/cronograma_export.py` (PDF/PPT).
Método: leitura linha-a-linha + execução de 13 testes diretos no motor Python (ciclos, cascade, grupos aninhados, marcos, datas invertidas, vazio, export). Sem commit.

## Resumo

O motor é robusto contra crash (div-por-zero, datas invertidas, cronograma vazio — todos protegidos). Os bugs reais são de **correção lógica**, não de quebra: o cascade FS não faz ordenação topológica (sucessora listada antes da predecessora usa data velha), índices de `depends_on`/`parent_ordem` quebram porque o backend re-ordena as fases depois que o frontend os gravou, e grupos aninhados não propagam datas. No export, a **capa do PDF e do PPT desenha os 4 números-chave em branco sobre fundo branco (invisíveis) + texto duplicado** — bug visual P0 que some justamente os dados de resumo.

| Área | Status | Nota |
|---|---|---|
| Dependências FS (ciclo) | 🟡 não trava, mas ignora silenciosamente | DFS funciona contra crash; cascade some sem avisar |
| Dependências FS (cascade / ordem) | 🔴 P0 | sem topo-sort: sucessora antes da predecessora usa data velha |
| Índices depends_on/parent_ordem vs sort | 🔴 P0 | `fases.sort` re-ordena DEPOIS de gravar índices → apontam pra fase errada |
| Grupos aninhados | 🔴 P1 | grupo-de-grupo não propaga datas (1 passada só) |
| Marcos (dur=0) | 🟢 | div protegida por `max(1,f_dur)` em toda parte |
| Drag-and-drop | 🟡 P1 | reorder + resize mexem em índices; sem snap; sem teclado |
| Acessibilidade Gantt | 🟡 P1 | sem aria-live, sem teclado pra mover/redimensionar (já flagado 02/06) |
| Render live 250ms | 🟡 P1 | debounce OK, mas race com drag + reentrância |
| Export PDF/PPT capa | 🔴 P0 | meta cards brancos sobre branco (invisíveis) + título duplicado |
| Curva S | 🟢 | sigmoidal correta; PPC coerente |
| Persistência | 🟢 | save/autosave mandam os 3 campos novos; restaura tudo |
| Cores slate | 🟡 | motor 100% slate; export tem lavanda/âmbar residual |

---

## 🟢 Acertos

- **Proteção contra div-por-zero é consistente.** Matriz usa `max(1, f_dur)` (`cronograma.py:192, 353`), curva S usa `max(1, duracao_dias_real)` (`:373`) e `max(1, soma_dur)` no PPC (`:641`). Testei marco isolado, todos-marcos-no-mesmo-dia e cronograma vazio: nenhum crash.
- **Datas invertidas (fim < início) tratadas** — `cronograma.py:113-115` força `dur=7`. Confirmado no teste 10.
- **Cronograma vazio não quebra export** — `gerar_gantt_png`/`gerar_curva_s_png` têm early-return com placeholder (`cronograma_export.py:52-60, 120-128`). PDF vazio gerou 73KB sem erro.
- **Múltiplas predecessoras pegam `max(fim)` corretamente** (`cronograma.py:820`). Confirmado no teste 3.
- **DFS de ciclo não estoura recursão** — teste 1 com A↔B não travou (sem `RecursionError`).
- **`parent_ordem` inválido é ignorado com segurança** — validação `isinstance(p,int) and 0<=p<n and p!=i` em `_agregar_grupos` (`:858`). Teste 7 (parent=99, parent=self) passou limpo.
- **Persistência completa** — `save`/autosave enviam `depends_on`, `is_milestone`, `parent_ordem` (`cronograma.html:798-800, 955-957`); `/full` reconstrói via `gerar_cronograma_de_fases_custom`. Recarregar restaura config + fases.
- **Curva S sigmoidal correta** com guarda de `OverflowError` (`:208-210`) e clamp em t_norm≥0.99.
- **Export é resiliente a I/O** — download de logo, limpeza de tempfiles e branding têm try/except por bloco.

---

## 🔴 Bugs (P0) — quebra real

### P0-1 · Cascade FS sem ordenação topológica (datas erradas)
`cronograma.py:766-836` (`_aplicar_dependencias_fs`)
O cascade percorre `fases` na ordem da lista e aplica `inicio = max(predecessoras.fim)+1`. Mas **não faz topo-sort**: se uma sucessora aparece na lista ANTES da predecessora (ou antes de a predecessora ter sido recalculada), ela lê a data **velha**.

Teste 2b (lista `[C→B, B→A, A]`):
```
C 2026-06-07 -> 2026-06-11     # ERRADO — devia começar depois de B (06-27)
B 2026-06-21 -> 2026-06-26     # B recalculado DEPOIS de C já ter lido B.fim antigo
A 2026-06-01 -> 2026-06-20
```
C deveria sair em 06-27 (após B), mas saiu em 06-07 porque foi processada antes de B mover. **O cliente arrasta/edita e o cronograma mostra datas que violam as próprias dependências que ele definiu.** Numa fase 2 cuja venda é "cronograma confiável", isso é grave.
**Fix:** ordenar por Kahn (topological sort) antes de aplicar o cascade, ou iterar até estabilizar (fixpoint, com cap de N iterações).

### P0-2 · `fases.sort` quebra os índices de `depends_on`/`parent_ordem`
`cronograma.py:150` (`fases.sort(key=lambda x: (x.get('ordem') or 0, x['inicio']))`) roda **antes** de `_aplicar_dependencias_fs` e `_agregar_grupos`.
O frontend grava `depends_on`/`parent_ordem` como **índice posicional do DOM** (`cronograma.html:707, 710, 717-719`). Quando duas fases têm o mesmo `ordem` (ex.: ambas `null` → `0`), o desempate por `inicio` **reordena a lista**, mas os índices já gravados **não são remapeados**.

Teste 8b (duas fases sem `ordem`, a 2ª depende da 1ª via `[0]`):
```
idx0 Segunda-mas-comeca-antes  deps=[0]   # aponta pra ELA MESMA após o sort
idx1 Primeira-na-lista         deps=[]
```
A dependência passou a apontar pra própria fase. `_aplicar_dependencias_fs` tem guarda `d == i` (`:810`) que descarta auto-referência, então aqui vira "sem dependência" silenciosamente — mas com 3+ fases o índice cai numa fase **diferente da pretendida**, criando dependência fantasma.
**Fix:** ou (a) parar de re-ordenar e confiar na ordem do editor, ou (b) remapear `depends_on`/`parent_ordem` pelo mapa `idx_antigo → idx_novo` logo após o sort. Recomendo (b) com um dict de remap construído antes do `sort`.

### P0-3 · Capa do PDF/PPT: meta cards brancos sobre fundo branco (invisíveis) + título duplicado
PDF: `cronograma_export.py:469-519` · PPT: `:872-892`
A capa minimal desenha **fundo branco** (`capa_canvas`, comentário `:360`). Mas o conteúdo Platypus da página 1 desenha os 4 números-chave com `COLOR_WHITE` (#FFFFFF) e rótulos em lavanda `#A5B4FC`/`#C7D2FE` — sobras do design fullbleed antigo:
```python
meta_html = f'<font color="{COLOR_WHITE}" size="22">...'   # branco no branco
... f'<font color="#A5B4FC" size="10">INÍCIO PREVISTO</font>'
```
Extraí o texto da página 1 (teste com nome longo): o conteúdo aparece **duplicado** — `capa_canvas` desenha título + cliente em slate-escuro (visível), e o `story` redesenha "CRONOGRAMA / DA OBRA" + nome + cliente + os 4 cards por cima. Resultado:
- Os 4 números (início/término/duração/fases) ficam **brancos sobre branco = invisíveis**. Como só aparecem na capa, esse resumo **some** do PDF/PPT.
- Título e cliente aparecem **2×** sobrepostos (canvas em escuro + story branco). O texto extrai mas o leitor vê duplicação fantasma / borra.
- 🎨 Daltonismo à parte, lavanda claro sobre branco também reprova contraste.
**Fix:** remover do `story` da página 1 os blocos que `capa_canvas` já desenha (título, cliente), e recolorir os 4 meta cards pra slate escuro (`COLOR_DARK` valor / `COLOR_GRAY_MID` rótulo). No PPT, trocar `rgb_white`/`#A5B4FC` por `rgb_dark`/`rgb_gray_mid` nas linhas 881-892.

---

## 🟡 Edge cases (P1)

### P1-1 · Grupo aninhado (grupo dentro de grupo) não propaga datas
`cronograma.py:839-874` (`_agregar_grupos`)
`_agregar_grupos` faz **uma passada só**. Teste 6 (Raiz ⊃ SubGrupo ⊃ Folha):
```
Raiz     is_group=True  2026-06-01 -> 2026-06-02   # ERRADO: agregou SubGrupo ANTES dele absorver a Folha
SubGrupo is_group=True  2026-07-01 -> 2026-07-20   # correto (absorveu Folha)
Folha                   2026-07-01 -> 2026-07-20
```
A Raiz refletiu as datas **originais** do SubGrupo, não as agregadas. Aninhamento de 2+ níveis dá datas erradas no pai-de-cima.
**Fix:** processar grupos das folhas pra raiz (ordenar por profundidade) ou iterar até fixpoint.

### P1-2 · Cascade FS é silenciosamente ignorado em ciclo
`cronograma.py:813-815` — ao detectar ciclo, a dependência é descartada (`continue`) sem nenhuma flag no retorno. O frontend desenha as setas FS a partir de `f.depends_on` (`cronograma.html:1102-1119`); como `_aplicar_dependencias_fs` reescreve `depends_on` só com os válidos (`:834`), a seta some — mas o usuário não recebe aviso de "dependência circular removida". Some sem rastro.
**Fix:** devolver `warnings: ['dependência circular entre X e Y ignorada']` no JSON e mostrar toast no front.

### P1-3 · Resize não respeita snap-a-dia nem duração mínima visível
`cronograma.html:1235-1244` — `resize-left/right` bloqueia só `< 1 dia` (`diffDays < 1`). Mas a barra visual tem largura mínima de 20px (`:1053, 1295`), então arrastar pra duração de 1-2 dias mostra uma barra que não encolhe proporcionalmente (descola do dado real). Não há snap explícito: `deltaDias = Math.round(dx / pxPorDia)` arredonda, o que é um snap implícito ok, mas o handle de 8px (`HANDLE_W`) em barras de w<20px **não é renderizado** (`:1093 if w >= 20`), então fases curtas não têm como redimensionar pela borda.

### P1-4 · Reorder via drag confia em índices que o cascade vai reler errado
`cronograma.html:1302-1316, 1275` — após reordenar por drag, o `_onDragEnd` grava nos inputs do editor pela posição final, dispara `scheduleLiveApply` → `aplicarEdits` → re-render local. Mas `aplicarEdits` recalcula só localmente (não chama backend), então `depends_on` por índice **não é reavaliado** contra a nova ordem. Reordenar uma fase com dependência cria a mesma quebra de índice do P0-2 — agora no caminho de drag.

### P1-5 · `aplicarEdits` local não aplica cascade FS nem agrega grupos
`cronograma.html:741-772` — o render live recalcula `dur_dias`, PPC e `data_fim` no cliente, mas **não** roda `_aplicar_dependencias_fs`/`_agregar_grupos` (isso só existe no backend). Então, enquanto edita, o Gantt mostra as datas SEM cascade; só depois de Salvar + recarregar via `/full` o cascade aparece. Comportamento inconsistente entre "o que vejo editando" e "o que sai salvo".

### P1-6 · Race entre drag e debounce de 250ms
`cronograma.html:658-665, 1286` — `scheduleLiveApply` tem debounce de 250ms e re-renderiza o SVG inteiro (`renderGantt` recria todos os nós). Se o usuário começa um novo drag dentro da janela de 250ms após soltar o anterior, o `setTimeout` pode disparar `aplicarEdits`→`renderGantt` **no meio do novo `pointerdown`**, recriando o `rectEl` que `_dragState` referencia → o drag em curso passa a mexer num nó órfão. `_dragState` não é invalidado no re-render.
**Fix:** cancelar `_liveApplyTimer` em `iniciarDrag`, ou ignorar re-render enquanto `_dragState != null`.

### P1-7 · Marco arrastável mas sem handles e sem clamp de área
`cronograma.html:1063-1072` — diamante tem `data-drag-mode="move"`. Arrastar pra fora da área (x negativo / além do último mês) não é clampado: `addDays` aceita qualquer delta, então dá pra empurrar a fase pra antes de `data_inicio` (offset negativo) — no `_onDragEnd` `diasOffset` vira negativo e `addDays(data_inicio, negativo)` gera data anterior ao início do projeto. O Gantt então recalcula `total_dias` e a escala toda "pula".

---

## ♿ Acessibilidade do Gantt

Contexto: Pedro é daltônico (regra dura cor+ícone+texto) e a auditoria a11y de 02/06 (`docs/auditoria_a11y_2026-06-02.md`, itens 9, 11, 19) já pegou parte disto.

- **Sem alternativa de teclado pro drag-and-drop (P1).** Mover/redimensionar barra só por ponteiro (`pointerdown`). WCAG 2.5.7 (Dragging Movements) e 2.1.1 (Keyboard). Há mitigação parcial: o editor tem setas ↑↓ (`btn-up`/`btn-down`, `cronograma.html:510-515`) pra reordenar e inputs `date`/`number` pra ajustar datas/% por teclado — ou seja, **toda ação do drag tem equivalente por formulário**. Mas mover/redimensionar a barra em si é ponteiro-só.
- **Reorder não anuncia (P1).** `moverRow` (`:640-654`) e `reordenarFaseDuranteDrag` (`:1302`) só dão flash visual (`ring-2`). Sem `aria-live` → leitor de tela não percebe. Já flagado (item 9 da auditoria 02/06). Fix barato: 1 `<div class="sr-only" aria-live="polite">` + update "Fase X movida pra posição Y de N".
- **Cor das barras NÃO é o único diferenciador (✓ regra cumprida).** Cada barra tem o label da fase à esquerda sempre visível (`:1061`) e o `<title>` com nome+datas. A matriz mostra `%` em texto dentro da célula colorida (`:1433`). PPC e status usam ícone+texto (`✓`, "em andamento", "não iniciada(s)" `:994-996`).
- **MAS: paleta slate tem dois tons de luminância idêntica.** `instalacoes` #64748B e `complementares` #71717A têm luminância ~114 (medido) — indistinguíveis num degradê. A barra estreita (w≤40) **não mostra o texto de dias** (`:1089 if w > 40`), restando só a cor; salva-se pelo label lateral. Recomendo dar a `complementares` um tom claramente mais claro/escuro pra não colidir com `instalacoes`.
- **`<input type="color">` sem hex visível (P1).** `:517` — daltônico não lê a cor escolhida. Item 11/213 da auditoria 02/06. Mostrar o hex ao lado.
- **`multiple select` de "Depende de" (P1).** `:538` exige Ctrl/Cmd+clique — difícil no teclado/mobile e instrução só textual. Item 14 (`:92`) da auditoria 02/06.

---

## 🛠️ Top fixes (ordem de impacto)

1. **(P0-3) Capa PDF/PPT**: remover do `story` pág. 1 o que `capa_canvas` já desenha e recolorir os 4 meta cards pra slate escuro. Os números do resumo estão invisíveis hoje. *Impacto: todo PDF/PPT exportado sai com capa quebrada.*
2. **(P0-2) Remapear índices após `cronograma.py:150` sort** (ou remover o sort). `depends_on`/`parent_ordem` apontam pra fase errada quando `ordem` empata.
3. **(P0-1) Topo-sort no cascade FS** (`_aplicar_dependencias_fs`) — Kahn ou fixpoint. Hoje sucessora antes da predecessora usa data velha.
4. **(P1-1) `_agregar_grupos` folha→raiz** (multi-passada) pra grupo aninhado propagar datas.
5. **(P1-6) Cancelar `_liveApplyTimer` em `iniciarDrag`** + invalidar `_dragState` no re-render, pra matar a race do drag.
6. **(P1-7) Clampar drag** a `[data_inicio, fim_do_grid]` e dar handles de resize a barras curtas.
7. **(a11y) `aria-live` announcer no reorder** + hex visível no color picker (ambos triviais, já na fila da auditoria 02/06).
8. **(cores) Remover lavanda/âmbar residual do export** (`cronograma_export.py:482, 491-506, 730, 884, 889-892, 997, 1002`) e separar luminância de `complementares` vs `instalacoes` no `CATEGORIA_COR`.
9. **(P1-2) Devolver `warnings[]`** quando ciclo/dependência for descartado, com toast no front.

---

## ❓ Decisão pra Pedro

**O render live e o drag-and-drop mostram datas SEM aplicar dependências/grupos** (isso só roda quando salva e recarrega). Ou seja: enquanto você edita, o Gantt na tela pode estar "mentindo" sobre as datas reais — o cronograma "de verdade" (com cascade FS e grupos) só aparece depois de Salvar.

Duas saídas:
- **(A)** Recalcular tudo no servidor a cada edição (chamar `/save`+`/full` no debounce) — fica 100% fiel, mas mais lento e gasta mais request.
- **(B)** Portar a lógica de cascade/grupos pro JavaScript pra o preview bater com o salvo — rápido, mas duplica regra em 2 lugares (Python + JS) e precisa manter os dois sincronizados.

Recomendo **(B)** só pro cascade FS (que é o que o usuário enxerga arrastar), e deixar grupos aninhados (uso raro) pro servidor. Mas é decisão de produto: você quer o preview perfeito (mais código) ou aceita "salvou, recarregou, ajustou"? Me diz qual e eu implemento junto com os P0.
