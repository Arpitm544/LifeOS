begin;
alter table routines add column anchor_date varchar(10) not null default '2026-01-01';
alter table routines add column overrides jsonb not null default '{}';
alter table events add column cancelled boolean not null default false;
alter table action_log add column batch_id uuid;
create index action_log_batch on action_log(user_id,batch_id);
commit;
