-- Clerk subjects are text values (for example user_2Rf...). Record ids stay UUID.
-- Apply only after 001–004. Existing UUID identities cannot be mapped to Clerk
-- identities automatically; migrate or remove non-production fixture rows first.
begin;

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
