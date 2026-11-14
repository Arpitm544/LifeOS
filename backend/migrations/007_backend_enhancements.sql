-- Apply once after 006. Additive only: no existing column, policy or row is rewritten.
-- Supports priority explanations, insight suggestions, the reminder worker and retention.
begin;

-- Priority "why" line and score breakdown shown on tap (PRD F2, F2.2).
alter table tasks add column priority_why text;
alter table tasks add column priority_breakdown jsonb;
alter table tasks add constraint tasks_breakdown_object check (
  priority_breakdown is null or jsonb_typeof(priority_breakdown) = 'object');

-- 'sending' = claimed by a worker while the push is in flight (no row lock held
-- during network calls); 'missed' was already allowed.
alter table reminders drop constraint reminders_valid;
alter table reminders add constraint reminders_valid check (
 item_type in ('task','event') and status in ('pending','sending','sent','cancelled','acted','missed'));
-- Reminder kinds written by the rules, plan blocks, user requests and the daily plan.
alter table reminders add constraint reminders_kind_valid check (
  kind in ('start_now','due_soon','overdue','event','plan_block','custom','daily_plan'));
-- Notification centre and per-user rate limiting read recent sends per user.
create index reminders_user_sent_idx on reminders(user_id, sent_at desc) where sent_at is not null;
create index reminders_item_pending_idx on reminders(user_id, item_type, item_id) where status = 'pending';

-- Insight suggestions with Apply / Dismiss (PRD F4, 4.6).
create table suggestions (
  id uuid primary key default gen_random_uuid(),
  user_id text not null references public.users(id) on delete cascade,
  type varchar(32) not null check (type in ('pad_estimates','move_focus_window','adjust_reminder_lead','protect_routine')),
  text text not null check (length(btrim(text)) between 1 and 500),
  payload jsonb not null default '{}' check (jsonb_typeof(payload) = 'object'),
  status varchar(16) not null default 'active' check (status in ('active','applied','dismissed')),
  created_at timestamptz not null default now()
);
create index suggestions_owner_time on suggestions(user_id, created_at desc);
alter table suggestions enable row level security;
create policy suggestions_clerk_owner on suggestions
  using (user_id = nullif(current_setting('request.jwt.claim.sub', true), ''))
  with check (user_id = nullif(current_setting('request.jwt.claim.sub', true), ''));
grant select, insert, update, delete on suggestions to lifeos_api;

-- Worker liveness (NFR-R5). Not tenant data: RLS on with no policy and no grant
-- to lifeos_api, so only the administrative worker/health connection can use it.
create table worker_status (
  worker_name text primary key,
  last_seen_at timestamptz not null default now(),
  last_jobs jsonb not null default '{}'
);
alter table worker_status enable row level security;
-- Health check reads only the latest heartbeat time through this function.
create function public.lifeos_worker_last_seen() returns timestamptz
language sql stable security definer set search_path = pg_catalog as $$
  select max(last_seen_at) from public.worker_status;
$$;
revoke all on function public.lifeos_worker_last_seen() from public;
grant execute on function public.lifeos_worker_last_seen() to lifeos_api;

-- One browser endpoint belongs to one user: subscribing from a shared browser
-- removes the previous user's row so their reminders stop reaching this device.
-- RLS hides other users' rows from lifeos_api, hence the definer function.
create function public.claim_push_endpoint(p_endpoint text) returns void
language sql security definer set search_path = pg_catalog as $$
  delete from public.push_subscriptions
  where endpoint = p_endpoint
    and user_id <> nullif(current_setting('request.jwt.claim.sub', true), '')
    and nullif(current_setting('request.jwt.claim.sub', true), '') is not null;
$$;
revoke all on function public.claim_push_endpoint(text) from public;
grant execute on function public.claim_push_endpoint(text) to lifeos_api;

-- Read paths used by analytics, Today and retention.
create index if not exists tasks_owner_completed_idx on tasks(user_id, completed_at) where status = 'done';
create index if not exists plan_blocks_owner_start_idx on plan_blocks(user_id, start_at);
create index if not exists activity_events_type_idx on activity_events(user_id, type, occurred_at);
create index if not exists idempotency_created_idx on idempotency_records(created_at);

-- Retention (PRD 9): messages 90 days, activity 180 days, idempotency keys 2 days.
create function public.prune_lifeos_history() returns void
language sql security definer set search_path = pg_catalog as $$
  delete from public.messages where created_at < now() - interval '90 days';
  delete from public.activity_events where occurred_at < now() - interval '180 days';
  delete from public.idempotency_records where created_at < now() - interval '2 days';
$$;
revoke all on function public.prune_lifeos_history() from public;

-- The worker also runs retention nightly. When pg_cron is installed (Supabase:
-- Database > Extensions), schedule it in the database as well.
do $$ begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.schedule('lifeos-retention', '15 3 * * *', 'select public.prune_lifeos_history()');
  end if;
end $$;

commit;
