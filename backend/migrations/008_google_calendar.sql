-- Apply once after 007. Additive only. Google Calendar sync (read-only): one connection per user.
-- refresh_token_enc is Fernet-encrypted by the API; the plaintext token never reaches the database.
begin;

create table google_connections (
  id uuid primary key default gen_random_uuid(),
  user_id text not null unique references public.users(id) on delete cascade,
  refresh_token_enc text not null check (length(refresh_token_enc) > 0),
  connected_at timestamptz not null default now(),
  last_synced_at timestamptz,
  last_error varchar(200)
);
alter table google_connections enable row level security;
create policy google_connections_clerk_owner on google_connections
  using (user_id = nullif(current_setting('request.jwt.claim.sub', true), ''))
  with check (user_id = nullif(current_setting('request.jwt.claim.sub', true), ''));
grant select, insert, update, delete on google_connections to lifeos_api;

commit;
