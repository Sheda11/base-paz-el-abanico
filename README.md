# Reingeniería del Sistema Web para la Gestión Financiera y Auditoría Centralizada de la Gran Base de Paz "El Abanico" y sus Sedes Anexas

> **Proyecto Socio-Tecnológico (PST)**  
> **Área:** Ingeniería de Software y Gestión de Sistemas de Información Contable  

---

## 👥 Equipo de Desarrollo e Investigadores

* **Carlos Alvarez**
* **Williams Rios**
* **Emanuel Velásquez**

---

## 📖 Descripción General del Proyecto

El presente proyecto socio-tecnológico constituye una solución integral de reingeniería de software diseñada para optimizar, centralizar y transparentar la administración de los recursos financieros de la **Gran Base de Paz "El Abanico" (Sede Matriz)** y sus diferentes sedes anexas.

El sistema reemplaza los registros manuales y descentralizados mediante una plataforma web robusta capaz de operar con **aislamiento territorial por sede**, **procesamiento atómico de movimientos contables**, **flujos de aprobación de compras jerarquizados** y un **módulo de auditoría inmutable** que registra de forma inalterable quién, qué, cuándo y desde qué dirección IP se realiza cada transacción.

### 🎯 Objetivos Principales
1. **Control de Acceso Territorial Basado en Roles (RBAC):** Garantizar que cajeros, supervisores y analistas operen estrictamente en la sede asignada, manteniendo vistas consolidadas reservadas para la Dirección General y Auditoría.
2. **Gestión de Tesorería Atómica y Validada:** Procesar ingresos y egresos diarios con validación estricta de saldos disponibles, impidiendo montos negativos y actualizando el balance en tiempo real sin condiciones de carrera (*race conditions*).
3. **Workflow Digital de Órdenes de Pago:** Automatizar la aprobación de compras con escalamiento jerárquico según el monto económico (revisión de supervisor vs. escalamiento al Director General para montos $\ge \$1,000.00\text{ USD}$).
4. **Auditoría Forense e Inmutable:** Bloquear intentos de modificación (`UPDATE`) o eliminación (`DELETE`) sobre los logs de auditoría contable mediante triggers directos en el motor de base de datos.
5. **Automatización Asíncrona de Cartera Morosa:** Ejecución nocturna desatendida a las 00:00 hrs (vía Celery Beat y Redis) para evaluar vencimientos, reclasificar obligaciones a *Moroso* y emitir notificaciones sin congelar el servidor web.
6. **Dashboard Gerencial Interactivo:** Visualización de métricas en tiempo real, comparativas territoriales y recuento de cartera morosa.

---

## 🛠️ Stack Tecnológico

| Componente | Tecnología | Justificación Técnica |
| :--- | :--- | :--- |
| **Lenguaje Backend** | Python 3.12+ | Tipado estático moderno, alto rendimiento y legibilidad. |
| **Framework Web** | Django 5.x / 6.x | Robustez para arquitecturas empresariales, ORM seguro y protección CSRF/XSS. |
| **Base de Datos Principal** | PostgreSQL 16 | Soporte para transacciones ACID, integridad referencial y triggers en PL/pgSQL. |
| **Base de Datos de Desarrollo** | SQLite 3 | Base de datos ligera embebida con triggers nativos para pruebas locales inmediatas. |
| **Cola de Mensajes / Broker** | Redis 7 | Almacenamiento en memoria ultrarrápido para el encolamiento de tareas Celery. |
| **Procesamiento Asíncrono** | Celery & Celery Beat | Desacoplamiento de I/O y tareas programadas (cron a las 00:00 hrs). |
| **Contenedores y Despliegue** | Docker & Docker Compose | Entorno autocontenido y reproducible en cualquier servidor. |
| **Servidor Web y Proxy** | Nginx & Gunicorn | Proxy inverso de alta concurrencia y servidor WSGI para producción. |
| **Front-End / UI** | Bootstrap 5, Bootstrap Icons, Chart.js | Interfaz responsiva, dashboards visuales dinámicos y experiencia interactiva. |

---

## 🚀 Guía de Instalación y Ejecución Local (Paso a Paso)

Esta guía permite al jurado evaluador o tutor técnico poner en marcha el proyecto en su máquina local en menos de 5 minutos.

### Prerrequisitos
* Python 3.10 o superior instalado.
* Git instalado.

---

### Paso 1: Clonar el Repositorio
```bash
git clone https://github.com/tu-usuario/base-paz-el-abanico.git
cd base-paz-el-abanico
```

### Paso 2: Crear y Activar el Entorno Virtual

* **En Linux / macOS:**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```
* **En Windows (PowerShell):**
  ```powershell
  python -m venv venv
  .\venv\Scripts\Activate.ps1
  ```

### Paso 3: Instalar las Dependencias
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Paso 4: Configurar Variables de Entorno
Copia la plantilla de variables de entorno:
* **En Linux / macOS:** `cp .env.example .env`
* **En Windows:** `copy .env.example .env`

*(El sistema viene configurado por defecto con SQLite para que no sea obligatorio levantar PostgreSQL para evaluarlo).*

### Paso 5: Aplicar Migraciones de Base de Datos
Aplica el esquema relacional y los triggers de auditoría inmutable:
```bash
python manage.py migrate
```

### Paso 6: Cargar Datos Maestros de Demostración
Hemos preparado un comando de inicialización que crea automáticamente las sedes, categorías contables, usuarios y obligaciones morosas de prueba:
```bash
python manage.py seed_data
```

### Paso 7: Iniciar el Servidor de Desarrollo
```bash
python manage.py runserver
```

El sistema estará accesible en: **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)**

---

## 🔑 Credenciales de Acceso para Evaluación

El script de semillas (`seed_data`) provee los siguientes perfiles para que los evaluadores puedan verificar el comportamiento de los roles y el RBAC:

| Rol | Usuario | Contraseña | Alcance Territorial y Permisos |
| :--- | :--- | :--- | :--- |
| **Director General** *(Superusuario)* | `director` | `admin` | Acceso global consolidado, aprobación de órdenes $\ge \$1,000$, panel de auditoría y administración total. |
| **Cajero de Sede** | `cajero_matriz` | `password` | Operación restringida exclusivamente a la Gran Base de Paz "El Abanico". Registro de ingresos y egresos diarios. |

---

## 🧪 Ejecución de la Suite de Pruebas Automatizadas

El proyecto cuenta con una batería de pruebas unitarias y de integración que certifican los requerimientos críticos (inmutabilidad, saldos atómicos, workflow de órdenes y tarea de morosidad):

```bash
python manage.py test apps.finanzas
```

**Resultado esperado:**
```text
Creating test database for alias 'default'...
Found 5 test(s).
.....
----------------------------------------------------------------------
Ran 5 tests in 3.9s

OK
Destroying test database for alias 'default'...
```

---

## ⏰ Ejecución de Tareas Asíncronas (Celery y Redis)

En caso de evaluar el funcionamiento concurrente de Celery:

1. **Asegurar que Redis esté corriendo:**
   ```bash
   redis-server
   ```
2. **Iniciar el Worker de Celery:**
   ```bash
   celery -A config worker --loglevel=info -Q cron_queue,notifications_queue,celery
   ```
3. **Iniciar el Planificador Beat (Medianoche 00:00 hrs):**
   ```bash
   celery -A config beat --loglevel=info
   ```

*Nota: Para probar la tarea de medianoche de inmediato sin esperar al cron, se puede invocar desde la consola:*
```python
python manage.py shell
>>> from apps.finanzas.tasks import evaluar_cuentas_morosas_medianoche
>>> res = evaluar_cuentas_morosas_medianoche.delay()
>>> res.get()
```

---

## 🐳 Despliegue con Docker Compose (Producción)

Si el evaluador dispone de Docker, puede levantar la arquitectura completa (PostgreSQL 16, Redis 7, Django, Celery Worker, Celery Beat y Nginx) con un solo comando:

```bash
docker compose up -d --build
```

El servidor web de producción quedará disponible en el puerto `80`: **[http://localhost/](http://localhost/)**

---

## 📁 Estructura del Repositorio

```text
base_paz_el_abanico/
├── apps/
│   ├── auditoria/          # Modelo inmutable y triggers SQL (PL/pgSQL y SQLite)
│   ├── dashboard/          # Servicios analíticos, endpoints agregados y vistas
│   └── finanzas/           # Sedes, RBAC, transacciones atómicas, órdenes de pago y tareas Celery
│       ├── management/commands/seed_data.py   # Script de carga inicial de prueba
│       ├── forms.py        # Formularios tipificados y validados
│       ├── tasks.py        # Tareas periódicas Celery (00:00 hrs)
│       └── tests.py        # Suite de pruebas automatizadas
├── config/                 # Configuración central de Django (settings, urls, celery, wsgi)
├── nginx/                  # Archivos de configuración para proxy inverso Nginx
├── templates/              # Plantillas HTML responsivas (Dashboard, Formularios, Auth)
├── .env.example            # Plantilla de variables de entorno segura
├── .gitignore              # Reglas de exclusión de archivos sensibles
├── docker-compose.yml      # Orquestación de contenedores
├── Dockerfile              # Construcción multi-stage de la aplicación
├── manage.py               # Punto de entrada de comandos de gestión
├── README.md               # Documentación académica del proyecto
└── requirements.txt        # Especificación de dependencias del proyecto
```

---

## 📄 Licencia y Marco Académico

Desarrollado bajo el marco del **Proyecto Socio-Tecnológico**, con fines de impacto comunitario, modernización de la gestión pública y soberanía tecnológica.
