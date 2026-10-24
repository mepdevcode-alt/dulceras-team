#!/bin/sh
set -e

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

echo "==> Running migrations..."
python manage.py migrate --noinput

# El seed carga pedidos y clientes de demo: apagarlo en producción con RUN_SEED=false
if [ "${RUN_SEED:-true}" = "true" ]; then
    echo "==> Seeding data..."
    python manage.py seed_dulceras || echo "Seed skipped (already applied or error)."
fi

echo "==> Starting gunicorn on port ${PORT:-8000}..."
exec gunicorn dulceras_team.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 2 \
    --timeout 120 \
    --log-level info
