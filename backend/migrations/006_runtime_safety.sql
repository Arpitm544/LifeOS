begin;
-- Recheck installations that applied the earlier, weaker 003 role validation.
do $$
declare role_id oid := 'lifeos_api'::regrole;
  domain_tables text[] := array['users','tasks','events','preferences','routines','plan_blocks',
    'conflicts','reminders','messages','push_subscriptions','activity_events','action_log',
    'idempotency_records','task_dependencies','worker_heartbeats'];
begin
  if exists(select 1 from pg_roles where oid=role_id and
       (rolsuper or rolbypassrls or rolcreaterole or rolcreatedb or rolcanlogin or rolreplication or rolinherit))
    or exists(select 1 from pg_auth_members where member=role_id)
    or exists(select 1 from pg_shdepend where refclassid='pg_authid'::regclass
       and refobjid=role_id and deptype='o')
    or exists(select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace,
       lateral aclexplode(c.relacl) a where a.grantee=role_id and
       (n.nspname<>'public' or c.relname<>all(domain_tables)
        or a.privilege_type<>all(array['SELECT','INSERT','UPDATE','DELETE']) or a.is_grantable))
    or exists(select 1 from pg_namespace n, lateral aclexplode(n.nspacl) a
       where a.grantee=role_id and
       (n.nspname not in ('public','auth') or a.privilege_type<>'USAGE' or a.is_grantable))
    or exists(select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace,
       lateral aclexplode(p.proacl) a where a.grantee=role_id and
       (n.nspname<>'auth' or p.proname<>'uid' or p.pronargs<>0 or a.is_grantable))
    or exists(select 1 from pg_shdepend where refclassid='pg_authid'::regclass
       and refobjid=role_id and deptype='a'
       and classid not in ('pg_class'::regclass,'pg_namespace'::regclass,'pg_proc'::regclass)) then
    raise exception 'lifeos_api has unexpected privileges; provision a restricted role before rollout';
  end if;
end $$;
alter table routines alter column anchor_date set default (current_date::text);
create table rate_limit_events (
  user_id text not null,
  bucket text not null,
  occurred_at timestamptz not null default clock_timestamp()
);
create index rate_limit_owner_time on rate_limit_events(user_id,bucket,occurred_at);
create index rate_limit_expiry on rate_limit_events(occurred_at);
alter table rate_limit_events enable row level security;
create policy rate_limit_owner on rate_limit_events
 using (user_id = nullif(current_setting('request.jwt.claim.sub', true), ''))
 with check (user_id = nullif(current_setting('request.jwt.claim.sub', true), ''));
grant select,insert,delete on rate_limit_events to lifeos_api;
create function public.prune_rate_limit_events() returns void
language sql security definer set search_path = pg_catalog as $$
  delete from public.rate_limit_events where occurred_at <= clock_timestamp() - interval '60 seconds';
$$;
revoke all on function public.prune_rate_limit_events() from public;
grant execute on function public.prune_rate_limit_events() to lifeos_api;
commit;
