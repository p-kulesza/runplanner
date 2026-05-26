create extension if not exists pgcrypto;

create table if not exists public.routes (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  filename text not null,
  author text not null default '',
  distance_km double precision not null default 0,
  scheduled_dates jsonb not null default '[]'::jsonb,
  groups jsonb not null default '[]'::jsonb,
  gpx_xml text not null,
  gpx_path text,
  created_at date not null default current_date
);

alter table public.routes enable row level security;

drop policy if exists "service_role_manage_routes" on public.routes;
create policy "service_role_manage_routes"
on public.routes
for all
to service_role
using (true)
with check (true);

drop policy if exists "anon_no_access_routes" on public.routes;
create policy "anon_no_access_routes"
on public.routes
for all
to anon
using (false)
with check (false);
