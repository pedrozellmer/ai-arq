# 🏗️ Estrutural — achados 2026-07-20 (futura feature)

Investigação a fundo do caso **Luciano Zacheo** (`7f7ef56a`, projeto estrutural
de residência: FORMA + PILAR + VIGA + fundação, com ferragem). Testado com os
DXF reais convertidos do DWG. Guarda isso pra quando estrutural virar foco.

## ✅ O que JÁ funciona (aproveitar agora)
- **Aço via DXF:** `parse_steel_table` lê a tabela "Resumo de Aço" dos textos do
  CAD e devolve **kg de aço medido**. No `PILAR.dxf` do Luciano deu **629 kg,
  confiável**. → **Cliente que manda DXF já tira o aço.** (PDF não dá — a tabela
  não é legível; DWG só se converter.)

## 🔧 Corrigido hoje (no ar)
1. `count_pillars` não conta mais blocos de **eixo/hachura** como pilar (era 184
   falso numa casa de ~15-30). — `structural_extractor.py`
2. **Telemetria** `dwg:convert-fail` no `error_log` — falha de conversão DWG→DXF
   agora fica visível (antes sumia no disco efêmero do Render). — `main.py`
3. Aba **"Estrutural"** no guia de exportação do site: orienta mandar **DXF** pra
   ler a tabela de aço. — `dashboard.html`

## 🕓 Pra feature (quando estrutural virar foco)
1. **Conversão DWG→DXF falha no Render** em pranchas estruturais (ODA/libredwg).
   O cliente que manda DWG perde o aço (o extrator nunca roda). Investigar/
   robustecer a conversão, OU tratar estrutural como **DXF-only** com aviso claro.
   (A telemetria nova vai mostrar a frequência.)
2. **Parser de chamadas de ferro (rebar callouts):** a VIGA **não tem tabela** de
   aço (o PILAR tem) — o aço dela está em chamadas soltas por barra
   (`N1 Ø10 C=...`). Somar kg daí é uma extração nova (bitola → comprimento →
   massa linear).
3. **NÃO forçar medição geométrica dos detalhes.** As pranchas usam unidade
   **não-padrão e inconsistente** (`$INSUNITS=inches` errado; fator real ~0,2 no
   detalhe, ~0,1 na planta) e os detalhes **não estão em escala 1:1**. Medir
   geometria daí geraria número FALSO → viola a regra dura nº1. Só a **tabela de
   aço** é confiável em detalhamento; concreto/geometria fica estimado.

## 📌 Regra prática hoje
Projeto estrutural → **oriente DXF**. O aço lê da tabela (medido). O resto
(concreto, geometria) sai estimado, honesto. Nada de fingir medição de detalhe.
