#!/usr/bin/env fish
# One-shot setup for CachyOS/Arch + fish. Run from the repo root: ./scripts/setup.fish
set root (dirname (dirname (status filename)))
cd $root

for t in git uv node pnpm docker
    command -q $t; or echo "MISSING: $t  (sudo pacman -S --needed git uv nodejs pnpm docker docker-compose)"
end

cp -n .env.example .env; and echo "created .env"

echo "== backend"
cd backend
uv python install 3.12
uv sync --python 3.12
uv run pytest -q
cd ..

if not test -d frontend
    echo "== frontend (Next.js + Tailwind + shadcn + charts + maps)"
    pnpm create next-app@latest frontend --ts --tailwind --eslint --app --src-dir --import-alias "@/*" --use-pnpm --yes
    cd frontend
    pnpm dlx shadcn@latest init -d
    pnpm add recharts leaflet react-leaflet
    pnpm add -D @types/leaflet
    mkdir -p src/lib
    cp ../frontend_starter/lib/api.ts src/lib/api.ts
    echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
    cd ..
end

echo "== done. Run: (1) cd backend; uv run uvicorn app.main:app --reload   (2) cd frontend; pnpm dev"
