-- Apply once after 001_initial.sql. Existing rows without hashes return 409 on replay.
begin;
alter table idempotency_records add column request_hash varchar(64) not null default '';
alter table idempotency_records drop constraint idempotency_records_pkey;
alter table idempotency_records add primary key (user_id, key);
commit;
