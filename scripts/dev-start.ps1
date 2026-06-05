# DataVerse local development startup reference.
#
# Option A: one-command full stack launcher from repo root:
#   npm run dev
#
# Option B: run services in two terminals:
#
# Terminal 1:
#   cd dataverse_backend
#   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
#
# Terminal 2:
#   cd frontend
#   npm run dev:next

Write-Host "DataVerse development startup"
Write-Host ""
Write-Host "One command from repo root:"
Write-Host "  npm run dev"
Write-Host ""
Write-Host "Or run two terminals:"
Write-Host "  Terminal 1: cd dataverse_backend; python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
Write-Host "  Terminal 2: cd frontend; npm run dev:next"
