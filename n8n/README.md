# n8n — notificaciones de pedidos

Django es la fuente de verdad (pedidos, stock, pagos). Cuando pasa algo con un
pedido, Django le envía un evento a n8n por un webhook **local**, y n8n manda
los emails al cliente (y opcionalmente un aviso por Telegram al equipo).
Cada email queda registrado en Django (`MessageDelivery`) y n8n le informa el
resultado, así el panel admin muestra el estado de cada envío.

```
Django ──POST http://127.0.0.1:5678/webhook/pedidos (X-Webhook-Secret)──▶ n8n ──▶ SMTP / Telegram
   ▲                                                                       │
   └──── POST {callback_url} {status: sent|failed} (X-Webhook-Secret) ─────┘
```

- n8n escucha solo en `127.0.0.1`; no tiene vhost en nginx ni es accesible desde internet.
- Si `N8N_WEBHOOK_URL` está vacío en Django, todo funciona como antes (emails enviados por Django),
  pero igual queda el registro de cada envío.
- Si n8n está caído o responde error, Django manda su propio email como fallback.

## Panel admin

En **Pedidos → detalle**, la tarjeta *Mensajes al cliente* muestra cada envío con su estado
(Pendiente → En n8n → Enviado / Falló), permite **Reenviar** y **Enviar mensaje**
(una plantilla o un mensaje libre con asunto y texto).

API: `GET/POST /api/admin/orders/<id>/messages/` con `{template}`, `{template: "custom", subject, message}`
o `{resend_of: <id>}`.

## Eventos

| `event` | Cuándo | `delivery.template` |
|---|---|---|
| `order_created` | Checkout crea el pedido | `order_created` |
| `payment_received` | Webhook de MP aprueba la seña | `payment_received` |
| `order_status_changed` | Admin cambia el estado (`from_status`, `to_status`) | `order_ready` / `order_cancelled` / sin email |
| `message_requested` | Envío manual desde el panel | cualquiera, incluido `custom` |

`delivery` es `null` cuando el evento no lleva email al cliente (o el cliente no tiene email).
Payload completo: `build_order_payload` en `notifications/n8n.py`.
El aviso por Telegram al equipo solo se dispara con `order_created` y `payment_received` (no con envíos manuales).

## Instalación en el VPS

En producción n8n corre junto a Django en `docker-compose.prod.yml` (ver `docker/README.md`),
así que ya queda levantado con el resto. Para configurarlo:

```bash
# 1. Abrir el editor desde tu PC por túnel SSH
ssh -L 5678:127.0.0.1:5678 root@<ip-del-vps>
# y entrar a http://localhost:5678 (crear el usuario owner la primera vez)
```

2. En n8n: **Import from file** → `n8n/workflows/notificaciones_pedidos.json`.
3. Crear credenciales:
   - **Header Auth**: Name `X-Webhook-Secret`, Value = un secreto largo
     (ej. `python -c "import secrets; print(secrets.token_urlsafe(32))"`).
     Usarla en *Webhook Django*, *Informar enviado* e *Informar error*.
   - **SMTP** (nodo *Email al cliente*) y cambiar `CONFIGURAR_REMITENTE@example.com` por el remitente real.
   - Opcional: **Telegram**, poner el `chatId` y activar el nodo *Telegram al equipo*.
4. Activar el workflow.
5. En el `.env` de Django (Django le habla a n8n por la red interna de Docker):
   ```
   N8N_WEBHOOK_URL=http://n8n:5678/webhook/pedidos
   N8N_WEBHOOK_SECRET=<el mismo secreto del paso 3>
   # opcional, por defecto usa FRONTEND_URL (el dominio público)
   N8N_CALLBACK_BASE_URL=
   ```
   y `docker compose -f docker-compose.prod.yml up -d web`.

Para apagar la integración: dejar `N8N_WEBHOOK_URL=` vacío y recrear el contenedor `web`.

## Desarrollo local

- Con el workflow en modo test (botón *Execute workflow*), la URL es `/webhook-test/pedidos`;
  activado, es `/webhook/pedidos`.
- Si n8n corre en **Docker** y Django en tu PC, n8n no llega a `localhost:8000`. Usar
  `N8N_CALLBACK_BASE_URL=http://host.docker.internal:8000` y agregar `host.docker.internal`
  a `ALLOWED_HOSTS`. Si n8n corre con `npx n8n`, alcanza con `http://localhost:8000`.

## Archivos

- `workflows/notificaciones_pedidos.json` — workflow actual (sin credenciales ni datos personales).
- `workflows/pedidos_y_stock.json` — workflow original basado en Google Sheets, como referencia.
  Contiene un email personal, el ID del Sheet y el chat de Telegram: **no commitearlo** (está en `.gitignore`).
