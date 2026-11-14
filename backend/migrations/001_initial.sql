create extension if not exists pg_trgm;

create table if not exists tasks (
  id uuid primary key default gen_random_uuid(), user_id uuid not null,
  title varchar(120) not null, notes text, category varchar(20) not null default 'other',
  deadline_at timestamptz, effort_est_min integer not null default 30,
  effort_actual_min integer, importance integer not null default 3,
  status varchar(16) not null default 'open', priority_score double precision not null default 0,
  priority_band varchar(2) not null default 'P3', pinned boolean not null default false,
  recurrence_rrule varchar(512), created_at timestamptz not null default now(), completed_at timestamptz
);
create index if not exists tasks_user_status_deadline_idx on tasks(user_id, status, deadline_at);
create index if not exists tasks_title_trgm_idx on tasks using gin (title gin_trgm_ops);

create table if not exists action_log (
  id uuid primary key default gen_random_uuid(), user_id uuid not null,
  action_type varchar(32) not null, entity varchar(32) not null, entity_id uuid not null,
  before jsonb, after jsonb, created_at timestamptz not null default now(), undone_at timestamptz
);

alter table tasks enable row level security;
alter table action_log enable row level security;
create policy tasks_user_policy on tasks using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy action_log_user_policy on action_log using (user_id = auth.uid()) with check (user_id = auth.uid());

create table if not exists reminders (
  id uuid primary key default gen_random_uuid(), user_id uuid not null,
  item_type varchar(16) not null, item_id uuid not null, kind varchar(20) not null,
  fire_at timestamptz not null, status varchar(16) not null default 'pending',
  action_taken varchar(20), message text not null default '', sent_at timestamptz
);
create index if not exists reminders_due_idx on reminders(status, fire_at);
alter table reminders enable row level security;
create policy reminders_user_policy on reminders using (user_id = auth.uid()) with check (user_id = auth.uid());

create table if not exists activity_events (
  id uuid primary key default gen_random_uuid(), user_id uuid not null,
  type varchar(32) not null, entity_id uuid, payload jsonb,
  occurred_at timestamptz not null default now()
);
create index if not exists activity_events_user_time_idx on activity_events(user_id, occurred_at);
alter table activity_events enable row level security;
create policy activity_events_user_policy on activity_events using (user_id = auth.uid()) with check (user_id = auth.uid());

create table if not exists idempotency_records (
  key varchar(128) primary key, user_id uuid not null, response jsonb not null,
  created_at timestamptz not null default now()
);
create index if not exists idempotency_user_idx on idempotency_records(user_id, created_at);
alter table idempotency_records enable row level security;
create policy idempotency_user_policy on idempotency_records using (user_id = auth.uid()) with check (user_id = auth.uid());

create table if not exists events (
  id uuid primary key default gen_random_uuid(), user_id uuid not null,
  title varchar(120) not null, start_at timestamptz not null, end_at timestamptz not null,
  location varchar(200), rrule varchar(512), source varchar(16) not null default 'manual', external_id varchar(200)
);
create index if not exists events_user_time_idx on events(user_id, start_at, end_at);
alter table events enable row level security;
create policy events_user_policy on events using (user_id = auth.uid()) with check (user_id = auth.uid());

create table if not exists preferences (
  id uuid primary key default gen_random_uuid(), user_id uuid not null,
  key varchar(80) not null, value jsonb not null, source varchar(16) not null default 'stated',
  confidence double precision not null default 1.0, status varchar(16) not null default 'active',
  unique(user_id, key)
);
alter table preferences enable row level security;
create policy preferences_user_policy on preferences using (user_id = auth.uid()) with check (user_id = auth.uid());

create table if not exists routines (
  id uuid primary key default gen_random_uuid(), user_id uuid not null,
  title varchar(120) not null, rrule varchar(512) not null, start_time varchar(8) not null,
  duration_min integer not null, movable boolean not null default true
);
create index if not exists routines_user_idx on routines(user_id);
alter table routines enable row level security;
create policy routines_user_policy on routines using (user_id = auth.uid()) with check (user_id = auth.uid());

create table if not exists plan_blocks (
  id uuid primary key default gen_random_uuid(), user_id uuid not null, task_id uuid not null,
  start_at timestamptz not null, end_at timestamptz not null, status varchar(16) not null default 'planned',
  plan_date timestamptz not null
);
create index if not exists plan_blocks_user_date_idx on plan_blocks(user_id, plan_date, start_at);
alter table plan_blocks enable row level security;
create policy plan_blocks_user_policy on plan_blocks using (user_id = auth.uid()) with check (user_id = auth.uid());

create table if not exists conflicts (
  id uuid primary key default gen_random_uuid(), user_id uuid not null,
  deadline_at timestamptz not null, needed_min integer not null, free_min integer not null,
  task_ids jsonb not null default '[]', options jsonb not null default '[]', status varchar(16) not null default 'open'
);
create index if not exists conflicts_user_status_idx on conflicts(user_id, status, deadline_at);
alter table conflicts enable row level security;
create policy conflicts_user_policy on conflicts using (user_id = auth.uid()) with check (user_id = auth.uid());

