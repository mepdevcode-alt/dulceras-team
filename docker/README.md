# Deploy en el VPS con Docker

`docker-compose.prod.yml` levanta Django (`web`) y n8n (`n8n`) en la misma red.
Los puertos solo escuchan en `127.0.0.1`:

| Servicio | Host | Uso |
|---|---|---|
| `web` | `127.0.0.1:8001` | nginx de CloudPanel hace proxy acá (TLS lo maneja CloudPanel) |
| `n8n` | `127.0.0.1:5678` | editor por túnel SSH; Django le habla en `http://n8n:5678` |
| `sqlserver` | `127.0.0.1:1433` | SQL Server 2022 Express; Django le habla en `sqlserver:1433` |

Datos persistentes (fuera de la imagen):
- volumen `sqlserver_data` — base SQL Server (activa con `DB_ENGINE=mssql` en `.env`)
- `./data/db.sqlite3` — base SQLite (fallback: el compose fija `DATABASE_URL` a esta ruta y se usa si `.env` no tiene `DB_ENGINE=mssql`)
- `./media/` — imágenes subidas
- volumen `n8n_data` — workflows y credenciales de n8n

El resto de la config sale del `.env` del directorio (ver `.env.example`).
El seed no corre en producción (`RUN_SEED=false`).

## Redeploy

```bash
cd /home/dulceras/htdocs/vps-5881993-x.dattaweb.com/app
cp data/db.sqlite3 data/db.sqlite3.bak-$(date +%F)   # backup antes de migrar
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f web   # migraciones + gunicorn
```

`migrate` y `collectstatic` corren solos al arrancar el contenedor (`entrypoint.sh`).

## Comandos útiles

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
docker compose -f docker-compose.prod.yml restart web
```

n8n: ver `n8n/README.md`.

## SQL Server

Requiere el VPS con 4 GB de RAM o más (SQL Server no arranca con menos de 2 GB).

Alta inicial (una sola vez):

```bash
# 1. Password de sa (no versionado). Mínimo 8 caracteres con mayúsculas, minúsculas, números y símbolos.
echo 'MSSQL_SA_PASSWORD=...' > .env.sqlserver && chmod 600 .env.sqlserver

# 2. Levantar solo SQL Server y esperar a que quede healthy
docker compose -f docker-compose.prod.yml up -d sqlserver
docker compose -f docker-compose.prod.yml ps sqlserver

# 3. Base y login propios de la app (no usar sa desde Django)
docker compose -f docker-compose.prod.yml exec sqlserver bash -c '/opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD"'
#   CREATE DATABASE dulceras_db;
#   GO
#   CREATE LOGIN dulceras_app WITH PASSWORD = '...';
#   GO
#   USE dulceras_db; CREATE USER dulceras_app FOR LOGIN dulceras_app; ALTER ROLE db_owner ADD MEMBER dulceras_app;
#   GO
```

Migrar los datos de SQLite (con la web todavía en SQLite):

```bash
cp data/db.sqlite3 /root/backups/dulceras/db-$(date +%Y%m%d-%H%M)-antes-sqlserver.sqlite3
docker compose -f docker-compose.prod.yml exec web python manage.py dumpdata \
  --natural-foreign --natural-primary -e contenttypes -e auth.permission -e admin.logentry \
  -e sessions --indent 2 -o /app/data/dump.json
# Agregar al .env: DB_ENGINE=mssql, DB_HOST=sqlserver, DB_PORT=1433, DB_NAME, DB_USER, DB_PASSWORD
docker compose -f docker-compose.prod.yml up -d web          # migrate corre solo sobre SQL Server
docker compose -f docker-compose.prod.yml exec web python manage.py loaddata /app/data/dump.json
```

Rollback: sacar `DB_ENGINE=mssql` del `.env` y `docker compose -f docker-compose.prod.yml up -d web`
(vuelve al `db.sqlite3`, que la migración no toca).
