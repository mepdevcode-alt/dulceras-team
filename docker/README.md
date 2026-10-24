# Deploy en el VPS con Docker

`docker-compose.prod.yml` levanta Django (`web`) y n8n (`n8n`) en la misma red.
Los puertos solo escuchan en `127.0.0.1`:

| Servicio | Host | Uso |
|---|---|---|
| `web` | `127.0.0.1:8001` | nginx de CloudPanel hace proxy acá (TLS lo maneja CloudPanel) |
| `n8n` | `127.0.0.1:5678` | editor por túnel SSH; Django le habla en `http://n8n:5678` |

Datos persistentes (fuera de la imagen):
- `./data/db.sqlite3` — base SQLite (el compose fuerza `DATABASE_URL` a esta ruta)
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
