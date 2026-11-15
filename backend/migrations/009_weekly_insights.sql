-- Apply once after 008. Additive only.
-- The Sunday insight job (worker `weekly_insights`) retires last week's open suggestions as 'expired'.
-- Learned preference proposals (PRD F6) use rows keyed `inferred.<key>` in `preferences`; no schema change.
begin;

alter table suggestions drop constraint if exists suggestions_status_check;
alter table suggestions add constraint suggestions_status_check
  check (status in ('active','applied','dismissed','expired'));

-- Inference rules and the check-in read recent activity by type.
create index if not exists activity_events_owner_type_time on activity_events(user_id, type, occurred_at desc);

commit;
