-- Clerk subjects are text values (for example user_2Rf...). Record ids stay UUID.
-- Apply only after 001–004. Existing UUID identities cannot be mapped to Clerk
-- identities automatically; supply lifeos_identity_map as documented in README.md.
begin;

-- Operators populate this temporary table in the same session before running 005.
create temporary table if not exists lifeos_identity_map (
  legacy_id uuid primary key,
  clerk_id text not null unique check (clerk_id like 'user\_%' escape '\')
) on commit drop;


do $$
declare t text; r record;
begin
  foreach t in array array['tasks','action_log','reminders','activity_events','idempotency_records','events','preferences','routines','plan_blocks','conflicts','task_dependencies','messages','push_subscriptions','worker_heartbeats','users'] loop
    execute format('drop policy if exists %I on public.%I', t || '_user_policy', t);
    execute format('drop policy if exists %I on public.%I', t || '_owner', t);
    execute format('alter table public.%I drop constraint if exists %I', t, t || '_auth_owner');
  end loop;
  -- Drop every existing FK which contains user_id, including composite owner
  -- FKs. They are re-created after the type conversion below.
  for r in select c.conname, cls.relname
    from pg_constraint c join pg_class cls on cls.oid = c.conrelid
    join pg_namespace ns on ns.oid = cls.relnamespace
    where c.contype = 'f' and ns.nspname = 'public'
      and cls.relname = any(array['tasks','action_log','reminders','activity_events','idempotency_records','events','preferences','routines','plan_blocks','conflicts','task_dependencies','messages','push_subscriptions','worker_heartbeats','users'])
      and pg_get_constraintdef(c.oid) like 'FOREIGN KEY (user_id%'
  loop
    execute format('alter table public.%I drop constraint %I', r.relname, r.conname);
  end loop;
end $$;

drop policy if exists idempotency_user_policy on public.idempotency_records;
alter table users drop constraint if exists users_id_fkey;
alter table users alter column id type text using id::text;
alter table tasks alter column user_id type text using user_id::text;
alter table action_log alter column user_id type text using user_id::text;
alter table reminders alter column user_id type text using user_id::text;
alter table activity_events alter column user_id type text using user_id::text;
alter table idempotency_records alter column user_id type text using user_id::text;
alter table events alter column user_id type text using user_id::text;
alter table preferences alter column user_id type text using user_id::text;
alter table routines alter column user_id type text using user_id::text;
alter table plan_blocks alter column user_id type text using user_id::text;
alter table conflicts alter column user_id type text using user_id::text;
alter table task_dependencies alter column user_id type text using user_id::text;
alter table messages alter column user_id type text using user_id::text;
alter table push_subscriptions alter column user_id type text using user_id::text;
alter table worker_heartbeats alter column user_id type text using user_id::text;

-- Fail atomically if any historical owner lacks an explicit Clerk mapping.
do $$ declare t text; missing boolean; begin
  select exists(select 1 from public.users u left join lifeos_identity_map m
    on u.id = m.legacy_id::text where m.legacy_id is null) into missing;
  if missing then raise exception 'Missing legacy-to-Clerk mapping for public.users'; end if;
  foreach t in array array['tasks','action_log','reminders','activity_events','idempotency_records','events','preferences','routines','plan_blocks','conflicts','task_dependencies','messages','push_subscriptions','worker_heartbeats'] loop
    execute format('select exists(select 1 from public.%I x left join lifeos_identity_map m on x.user_id=m.legacy_id::text where m.legacy_id is null)', t) into missing;
    if missing then raise exception 'Missing legacy-to-Clerk mapping for %', t; end if;
    execute format('update public.%I x set user_id=m.clerk_id from lifeos_identity_map m where x.user_id=m.legacy_id::text', t);
  end loop;
  update public.users u set id=m.clerk_id from lifeos_identity_map m where u.id=m.legacy_id::text;
  insert into public.users(id) select clerk_id from lifeos_identity_map on conflict(id) do nothing;
end $$;

do $$
declare t text;
begin
  foreach t in array array['tasks','action_log','reminders','activity_events','idempotency_records','events','preferences','routines','plan_blocks','conflicts','task_dependencies','messages','push_subscriptions','worker_heartbeats'] loop
    execute format('alter table public.%I add constraint %I foreign key(user_id) references public.users(id) on delete cascade', t, t || '_clerk_owner');
    execute format('alter table public.%I enable row level security', t);
    execute format('create policy %I on public.%I using (user_id = nullif(current_setting(''request.jwt.claim.sub'', true), '''')) with check (user_id = nullif(current_setting(''request.jwt.claim.sub'', true), ''''))', t || '_clerk_owner', t);
  end loop;
  alter table public.users enable row level security;
  create policy users_clerk_owner on public.users using (id = nullif(current_setting('request.jwt.claim.sub', true), '')) with check (id = nullif(current_setting('request.jwt.claim.sub', true), ''));
end $$;

alter table plan_blocks add constraint blocks_owned_task foreign key(user_id,task_id)
  references tasks(user_id,id) on delete cascade;
alter table reminders add constraint reminder_owned_task foreign key(user_id,task_item_id)
  references tasks(user_id,id) on delete cascade;
alter table reminders add constraint reminder_owned_event foreign key(user_id,event_item_id)
  references events(user_id,id) on delete cascade;
alter table task_dependencies add constraint dependencies_owned_task foreign key(user_id,task_id)
  references tasks(user_id,id) on delete cascade;
alter table task_dependencies add constraint dependencies_owned_parent foreign key(user_id,depends_on_task_id)
  references tasks(user_id,id) on delete cascade;

commit;
