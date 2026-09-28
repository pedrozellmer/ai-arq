-- ✅ APLICADA em 28/09/2026 ~08h50 BRT (migração `telemetria_24_meses_e_junto_com_a_conta`), ANTES da Política de
-- Privacidade que promete isso ir ao ar. Pedro (28/09, decisões do parecer jurídico): telemetria guardada por 24 meses.
--
-- A política passa a dizer "Telemetria de uso: guardada por até 24 meses e apagada junto com a conta". Antes desta
-- migração nenhuma das duas coisas era verdade: `usage_events.user_id` é TEXTO e não tem FK — excluir a conta no
-- Supabase não apagava nenhum evento, e nada apagava evento velho.
-- Ensaiado num DO-block desfeito: 2 eventos de uma conta de mentira → 0 depois do DELETE; os outros 5.488 intactos;
-- 0 eventos com mais de 24 meses hoje (o mais antigo é de 30/06/2026). Conferido: 0 eventos de conta já apagada.

create or replace function public._apaga_telemetria_da_conta() returns trigger
language plpgsql security definer set search_path = public, pg_temp as $b$
begin
  delete from public.usage_events where user_id = old.id::text;
  return old;
end $b$;
revoke all on function public._apaga_telemetria_da_conta() from public, anon, authenticated;

create trigger apaga_telemetria_da_conta after delete on auth.users
  for each row execute function public._apaga_telemetria_da_conta();

select cron.schedule('usage-events-24-meses', '40 6 * * *',
  $c$delete from public.usage_events where created_at < now() - interval '24 months'$c$);
