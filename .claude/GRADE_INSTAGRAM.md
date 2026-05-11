# 📅 Grade Editorial Instagram AI.arq

> **Documento canônico.** Toda postagem segue essa grade. Se algo aqui for violado, sessão deve perguntar antes de postar.
> Última revisão: 2026-05-10

---

## 🚨 Regras de ouro

1. **JAMAIS mencionar dia da semana na legenda** sem o post estar travado nesse dia. Ex: "Pergunta da quinta" só pode sair se `publish_at` cai numa quinta.
2. **AIrnaldo posta SOMENTE quarta.** Qualquer outro dia é violação de marca.
3. **Horário fixo por dia** (ver tabela abaixo). Não improvisar.
4. **Validação no `slot_key`**: o `<dia>` do slot tem que casar com o `dow` (day-of-week) do `publish_at`. Scheduler tem que rejeitar antes de publicar se não bater.

---

## 🗓️ Grade fixa (uma rubrica por dia)

| Dia    | Rubrica            | Horário BRT | Formato       | Tema                                                                 |
|--------|--------------------|-------------|---------------|----------------------------------------------------------------------|
| SEG    | **Bastidor**       | 19:00       | Feed single   | Número da semana, melhoria nova, prova de progresso                  |
| TER    | **Erro caro**      | 19:00       | Carrossel 4-6 | 1 erro comum de orçamento c/ gancho TCU/SINAPI                       |
| QUA    | **Quarta do AIrnaldo** | **19:00** | Feed single   | Personagem fala BDI / SINAPI / prancha — voz funcional, sem biografia |
| QUI    | **Pergunta da semana** | 19:00   | Carrossel/single | FAQ respondida c/ CTA pro chat ou login                            |
| SEX    | **Real da sexta**  | 17:00       | Feed          | Opinião direta, descontração, "o que NÃO fazemos"                    |
| SÁB    | **Comparativo**    | 11:00       | Carrossel     | AI.arq vs Excel/X, antes-depois — leitura tranquila                  |
| DOM    | **Convite**        | 20:00       | Feed single   | CTA suave, testemunho, 1º projeto grátis                             |

**Stories (todo dia):** 12:00 e 20:00 — sem rubrica fixa, mais flexível (bastidor, repost, behind-the-scenes, número rápido). Padrão emergente que funcionou na semana 1.

---

## 🏷️ Convenção de slot_key

Formato: `<tipo>_<dia>_<semana_iso>`

- `feed_seg_w2` → feed de segunda-feira, semana 2 do calendário ISO
- `feed_qua_w2` (= AIrnaldo) — alternativa: `airnaldo_w2`
- `feed_ter_w2_p1` (se tiver mais de um na mesma semana)
- `story_seg_12_w2` / `story_seg_20_w2`
- `reel_seg_w2`

**Por que:** o scheduler valida que `dow(publish_at) == dia(slot_key)`. Se não bater, falha o agendamento ANTES de postar — Pedro vê o alerta e corrige.

---

## 📝 Sobre o AIrnaldo

- **Não é pessoa real, não é personagem-romance.** É mascote funcional.
- Fala de **temas técnicos** (BDI, SINAPI, BIM, prancha) com tom **AIrnaldo** — mais velho, experiente, sem firula.
- **Sem biografia inventada.** Sem datas, lugares, hábitos pessoais. Tom funcional sobre assuntos técnicos, não personagem com história.
- Só posta **quarta**. Frequência semanal, expectativa criada.

---

## ✅ Checklist antes de agendar cada post

- [ ] `publish_at` cai no dia certo da rubrica
- [ ] `slot_key` segue convenção e dia bate com `publish_at`
- [ ] Horário fixo da rubrica respeitado (19:00 seg/ter/qua/qui, 17:00 sex, 11:00 sáb, 20:00 dom)
- [ ] Legenda não menciona dia da semana sem ele estar travado
- [ ] Se for AIrnaldo: é quarta, tom funcional, sem biografia
- [ ] Imagem segue identidade (Montserrat, indigo/cyan, mascote consistente)
- [ ] Hashtags revisadas (8-12 hashtags, mix de nicho + amplo)

---

## 🔄 O que fazer com o post AIrnaldo de 07/05 (já publicado quinta com "toda quarta")

- **NÃO deletar.** Já tem engajamento, deletar perde tudo.
- Adicionar **comentário fixado** com tom de persona, transformando o erro em piada:
  > "📌 Atualização do AIrnaldo: a partir da próxima, toda QUARTA. Essa apresentação saiu na quinta porque eu tava encurralado em obra (cliente esquecendo de pagar a sondagem 🤷)."
- Próximo AIrnaldo: **quarta 13/05/2026 às 19:00**. Tema sugerido: "BDI por dentro — 4 coisas que precisam entrar e ninguém calcula direito"

---

## 📊 Métricas a acompanhar (já existem em `instagram_post_insights`)

- **Reach por rubrica** — qual dia da semana funciona melhor?
- **Saves por post** — saves > likes pra B2B (significa "vou usar isso depois")
- **Profile visits → follows** — funil de conversão
- **Comments** — engajamento real (vs likes que viraram inflação)

Sincronizar via `POST /api/instagram/insights/sync` semanalmente (segunda às 09:00 — adicionar ao pg_cron).

---

## 🚫 O que NÃO fazer

- Postar sem horário fixo da rubrica
- Mencionar dia da semana na legenda sem o post estar nesse dia
- Botar AIrnaldo em outro dia que não quarta
- Dar biografia ao AIrnaldo (sem "nasceu em", "trabalhou em")
- Postar 2 feeds no mesmo dia (story sim, feed não — uma voz por dia)
- Hashtags spam (#construcaocivil#obras#engenharia#arquitetura — máximo 12)
