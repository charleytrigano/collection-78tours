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
alter table public.disques add column if not exists presentation_face_a text;
alter table public.disques add column if not exists presentation_face_b text;
alter table public.disques add column if not exists ecoute_face_a text;
alter table public.disques add column if not exists ecoute_face_b text;

-- CDthèque
create table if not exists public.cds (
 id uuid primary key default gen_random_uuid(),
 created_at timestamptz not null default now(),
 artiste text, titre text, label text, annee text, genre text, format text, reference text, code_barres text,
 nb_disques text, pistes text, etat text, emplacement text, notes text, presentation text,
 estimation_basse_eur text, estimation_haute_eur text, identification_ia text,
 photo_recto text, photo_verso text, ecoutes text
);
alter table public.cds enable row level security;

-- Bibliothèque
create table if not exists public.livres (
 id uuid primary key default gen_random_uuid(),
 created_at timestamptz not null default now(),
 titre text, auteur text, editeur text, collection text, annee text, isbn text, langue text, genre text,
 format text, pages text, edition text, etat text, emplacement text, lu text, pret text, notes text, resume text,
 estimation_basse_eur text, estimation_haute_eur text, identification_ia text,
 photo_couverture text, photo_dos text
);
alter table public.livres enable row level security;
