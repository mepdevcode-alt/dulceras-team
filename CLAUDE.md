# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Contexto del proyecto
SaaS multi-tenant para gestión de pedidos, catálogo y pagos de negocios gastronómicos. **Dulceras Team** es el cliente semilla/referencia visual — cada decisión de diseño debe preguntarse "¿esto sirve solo para Dulceras o también para el próximo cliente gastronómico?" (ver `docs/kit/.../02_REGLAS_DE_DESARROLLO.md`).

## Documentación del kit
Toda la arquitectura, módulos y agentes están documentados en `docs/kit/dulceras_saas_claude_kit/`:
- `00_contexto/` — Contexto general del negocio
- `01_documentacion/` — Stack, arquitectura, multi-tenant, DB, API, auth, roles, roadmap
- `02_modulos/` — Especificación de cada módulo (landing, dashboard, catálogo, pedidos, pagos, etc.)
- `03_agentes/` — Roles y responsabilidades de cada agente Claude
- `04_checklists/` — MVP checklist y release readiness
- `05_prompts/` — Master prompt y template de tareas
- `06_templates/` — ADR y feature spec templates

**Antes de implementar cualquier módulo, leer el archivo correspondiente en `02_modulos/`.**

Nota: el kit describe el frontend objetivo como React + Vite + TypeScript, pero el estado real del código hoy es server-rendered (ver "Frontend actual" abajo). El directorio `frontend/` solo contiene un `node_modules/` residual, sin `package.json` — no hay build de React corriendo.

## Comandos

```powershell
# Activar entorno virtual (Windows)
.\env\Scripts\Activate.ps1

# Servidor de desarrollo
python manage.py runserver

# Migraciones
python manage.py makemigrations
python manage.py migrate

# Seed de datos de referencia (tenant "dulceras-team", categorías, productos, variantes)
python manage.py seed_dulceras

# Tests (Django test runner, no pytest configurado)
python manage.py test
python manage.py test catalog            # una app
python manage.py test orders.tests.NombreDeClase.test_metodo  # un test puntual

# Superusuario (para /admin/ de Django)
python manage.py createsuperuser
```

No hay linter/formatter configurado en el repo (sin `.flake8`, `pyproject.toml`, etc.).

## Arquitectura

### Apps Django
| App | Responsabilidad |
|-----|----------------|
| `core` | Modelos abstractos (`TimeStampedModel`, `TenantModel`), comando `seed_dulceras` |
| `tenants` | `Tenant`, `Plan`, `BusinessProfile`, `Subscription`, `DeliveryZone`; vistas de registro, settings de negocio y superadmin |
| `users` | `User` (AbstractUser) con `role` y `tenant`; auth JWT |
| `catalog` | `Category`, `Product`, `ProductVariant` (stock, precio) |
| `orders` | `Order`, `OrderItem`, `OrderStatusHistory`, `Coupon` — máquina de estados del pedido |
| `payments` | `PaymentIntent`, `WebhookEvent`; integración Mercado Pago (`payments/services.py`) |
| `notifications` | `Notification` (bell in-app), `WhatsAppLog` |
| `customers` | `Customer`, `CustomerAddress`, `Review` |
| `audit` | `AuditLog` genérico por tenant |

### Multi-tenancy: sin middleware, resuelto por vista
A pesar de lo que sugiere la documentación del kit, **no hay middleware multi-tenant**. El tenant se resuelve explícitamente en cada vista según el tipo de endpoint:
- **API pública** (`/api/public/...`): el tenant se resuelve desde `tenant_slug` en la URL (`get_object_or_404(Tenant, slug=tenant_slug, is_active=True)`).
- **API admin** (`/api/admin/...`, requiere JWT): el tenant es `request.user.tenant`.
- **API superadmin** (`/api/superadmin/...`): requiere `request.user.is_platform_owner` (permission class `IsPlatformOwner` en `tenants/views.py`). Un `platform_owner` puede impersonar/consultar un tenant específico pasando `?tenant=<slug>` en query params (patrón usado en `AdminDeliveryZoneViewSet`, `TenantSettingsView`, etc.).

Toda query sobre modelos `TenantModel` debe filtrar explícitamente por `tenant` — no hay un `TenantManager` automático que lo haga.

### Roles (`users.User.role`)
`platform_owner` (dueño de la plataforma SaaS) > `tenant_admin` > `staff_ventas` / `staff_produccion` / `staff_caja` > `customer`. Propiedades helper: `user.is_platform_owner`, `user.is_tenant_admin`.

### Frontend actual: server-rendered, no SPA
El frontend implementado hoy **no es React** — son templates Django en `templates/` servidos desde `dulceras_team/pages.py` (vistas simples que resuelven el tenant `dulceras-team` hardcodeado como `TENANT_SLUG` y pasan contexto al template). El stack de cliente es:
- **Tailwind CSS** vía CDN (`cdn.tailwindcss.com`, configurado inline en `templates/base.html`)
- **Alpine.js** para interactividad declarativa (stores en `static/js/app.js`, cargado antes del CDN de Alpine)
- **HTMX** para fetch/swap de fragmentos
- Las páginas llaman a la API REST same-origin vía `window.DULCERAS.apiBase` (ver `base.html`)

Secciones de páginas: públicas (landing, catálogo, checkout, registro de tenant), cuenta de cliente (`cuenta/...`), panel admin (`admin/...`), superadmin (`superadmin/...`). El panel admin y superadmin tienen su propio `base.html` (`templates/admin_panel/base.html`, `templates/superadmin/base.html`).

### Base de datos: dos rutas según entorno
`dulceras_team/settings.py` elige el engine según si existe `DATABASE_URL`:
- **Sin `DATABASE_URL`** (dev local sin Docker, Windows): SQL Server vía `mssql-django`, requiere ODBC Driver 17 instalado.
- **Con `DATABASE_URL`** (Docker Compose, Render): Postgres vía `dj_database_url` (`dj-database-url` solo está en `requirements-prod.txt`, no en `requirements.txt`).

`docker-compose.yml` levanta Postgres + el servicio web; la variable `MERCADOPAGO_ACCESS_TOKEN` y demás config se inyectan por entorno (ver `.env.example`).

### Pedidos: máquina de estados
`Order.status` recorre: `draft → pending_deposit → deposit_paid → confirmed → in_production → ready → out_for_delivery → delivered` (o `cancelled` / `refunded`). Cada transición queda registrada en `OrderStatusHistory`. Las listas `ACTIVE_STATUSES` / `PAID_STATUSES` en `orders/views.py` se usan para disponibilidad de fechas y reportes — mantenerlas sincronizadas si se agregan estados.

### Pagos: Mercado Pago + webhooks idempotentes
`payments/services.py` aísla el SDK de Mercado Pago (`get_mp_sdk`, `build_mp_preference`) para que las vistas no dependan de él directamente. `WebhookEvent` guarda cada notificación entrante (`mp_id`, `topic`, `payload`, `processed`) para idempotencia — antes de procesar un webhook hay que chequear si ya existe un `WebhookEvent` procesado con ese `mp_id`. El paquete `mercadopago` solo está en `requirements-prod.txt`; para probar pagos localmente sin Docker hay que instalarlo a mano en el venv.

## Reglas clave
- Nunca hardcodear "Dulceras" en config donde deba existir configuración por tenant — el seed (`seed_dulceras`) sí puede usar datos reales de Dulceras Team como demo.
- Toda query debe filtrar por tenant explícitamente (no hay enforcement automático).
- Lógica de negocio (precios, stock, calendario, depósitos, cupones) se valida en backend, nunca solo en Alpine/HTMX.
- Webhooks idempotentes con log de integración (`WebhookEvent`).
- No usar `.gitignore`d `.env`; actualizar `.env.example` al agregar nuevas variables de configuración.
