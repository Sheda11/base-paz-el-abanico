#!/bin/sh
set -e

echo "Esperando que PostgreSQL este listo..."
while ! nc -z db 5432; do
  sleep 0.5
done
echo "PostgreSQL iniciado correctamente."

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"
