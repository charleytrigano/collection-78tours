create extension if not exists pgcrypto;
create table if not exists public.disques (
 id uuid primary key default gen_random_uuid(),
 created_at timestamptz not null default now(),
 titre_face_a text, titre_face_b text,
 interprete_face_a text, interprete_face_b text,
 orchestre text, auteurs text, label_marque text, reference_disque text, annee text,
 etat text default 'Très bon état', pochette text default 'À confirmer',
 estimation_basse_eur text, estimation_haute_eur text, notes text, identification_ia text,
 photo_etiquette text, photo_face_b text, photo_pochette text
);
alter table public.disques enable row level security;
insert into storage.buckets (id,name,public) values ('disques-photos','disques-photos',false) on conflict (id) do nothing;

alter table public.disques add column if not exists photo_face_b text;
