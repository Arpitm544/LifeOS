-- Run once as the migration administrator, after 001 and 002.
-- Atomic: invalid existing rows abort the migration; no user data is deleted.
begin;

do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'lifeos_api') then
    create role lifeos_api nologin noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls;
  end if;
  if exists (select 1 from pg_roles where rolname='lifeos_api' and
      (rolsuper or rolbypassrls or rolcreaterole or rolcreatedb or rolcanlogin or rolreplication or rolinherit)) then
    raise exception 'Existing lifeos_api role is not sufficiently restricted';
  end if;
  if exists(select 1 from pg_auth_members where member = 'lifeos_api'::regrole)
     or exists(select 1 from pg_shdepend where refobjid = 'lifeos_api'::regrole
       and refclassid = 'pg_authid'::regclass and deptype in ('o','a')) then
    raise exception 'Existing lifeos_api has memberships, ownership or explicit grants; provision a clean role';
  end if;
end $$;
grant usage on schema public, auth to lifeos_api;
grant execute on function auth.uid() to lifeos_api;
-- Local development may use the existing administrator login. In production
-- provision a separate login, grant it only lifeos_api membership, and configure
-- DATABASE_URL for that login. Never grant lifeos_api membership to frontend roles.
grant lifeos_api to postgres;

create table users (
  id uuid primary key references auth.users(id) on delete cascade,
  email text, name text, timezone text not null default 'UTC',
  created_at timestamptz not null default now()
);
alter table users enable row level security;
create policy users_owner on users using (id=auth.uid()) with check (id=auth.uid());

alter table tasks add constraint tasks_owner_id unique (user_id,id);
alter table events add constraint events_owner_id unique (user_id,id);
alter table tasks add constraint tasks_values check (
 length(btrim(title)) between 1 and 120 and effort_est_min between 5 and 600 and
 (effort_actual_min is null or effort_actual_min >= 0) and importance between 1 and 5 and
 status in ('open','blocked','done','dropped') and priority_score between 0 and 100 and
 priority_band in ('P1','P2','P3') and
 category in ('study','work','errand','health','social','finance','home','other'));
alter table events add constraint events_valid_range check (end_at>start_at);
alter table preferences add constraint preferences_valid check (
 confidence between 0 and 1 and source in ('stated','inferred','default') and
 status in ('active','suggested'));
alter table routines add constraint routines_duration check (duration_min between 5 and 600);
alter table plan_blocks add constraint blocks_valid check (
 end_at>start_at and status in ('planned','done','missed','moved'));
alter table plan_blocks add constraint blocks_owned_task foreign key (user_id,task_id)
 references tasks(user_id,id) on delete cascade;
alter table conflicts add constraint conflicts_valid check (
 needed_min>=0 and free_min>=0 and status in ('open','resolved','ignored') and
 jsonb_typeof(task_ids)='array' and jsonb_typeof(options)='array');
alter table reminders add constraint reminders_valid check (
 item_type in ('task','event') and status in ('pending','sent','cancelled','acted','missed'));
-- Generated nullable references enforce ownership for both item types.
alter table reminders add column task_item_id uuid generated always as
 (case when item_type='task' then item_id end) stored;
alter table reminders add column event_item_id uuid generated always as
 (case when item_type='event' then item_id end) stored;
alter table reminders add constraint reminder_owned_task foreign key (user_id,task_item_id)
 references tasks(user_id,id) on delete cascade;
alter table reminders add constraint reminder_owned_event foreign key (user_id,event_item_id)
 references events(user_id,id) on delete cascade;

create table task_dependencies (
 user_id uuid not null, task_id uuid not null, depends_on_task_id uuid not null,
 primary key(user_id,task_id,depends_on_task_id),
 check(task_id<>depends_on_task_id),
 foreign key(user_id,task_id) references tasks(user_id,id) on delete cascade,
 foreign key(user_id,depends_on_task_id) references tasks(user_id,id) on delete cascade
);
create table messages (
 id uuid primary key default gen_random_uuid(), user_id uuid not null,
 role text not null check(role in ('user','assistant')), text text not null,
 tool_calls jsonb, latency_ms integer check(latency_ms>=0),
 input_tokens integer check(input_tokens>=0), output_tokens integer check(output_tokens>=0),
 created_at timestamptz not null default now()
);
create index messages_owner_time on messages(user_id,created_at);
create table push_subscriptions (
 id uuid primary key default gen_random_uuid(), user_id uuid not null,
 endpoint text not null, p256dh text not null, auth text not null,
 created_at timestamptz not null default now(), unique(user_id,endpoint)
);
create table worker_heartbeats (
 id uuid primary key default gen_random_uuid(), user_id uuid not null,
 worker_name text not null, last_seen_at timestamptz not null default now(),
 unique(user_id,worker_name)
);

do $$ declare t text; begin
 foreach t in array array['tasks','events','preferences','routines','plan_blocks',
 'conflicts','reminders','messages','push_subscriptions','activity_events',
 'action_log','idempotency_records','task_dependencies','worker_heartbeats'] loop
   execute format('alter table public.%I add constraint %I foreign key(user_id) references auth.users(id) on delete cascade',t,t||'_auth_owner');
   execute format('alter table public.%I enable row level security',t);
 end loop;
 foreach t in array array['messages','push_subscriptions','task_dependencies','worker_heartbeats'] loop
   execute format('create policy %I on public.%I using (user_id=auth.uid()) with check (user_id=auth.uid())',t||'_owner',t);
 end loop;
end $$;

grant select,insert,update,delete on users,tasks,events,preferences,routines,plan_blocks,
 conflicts,reminders,messages,push_subscriptions,activity_events,action_log,
 idempotency_records,task_dependencies,worker_heartbeats to lifeos_api;
commit;
