# Entel TV

Proyecto académico de la Evaluación Sumativa N.º 3, Parte 2, de Programación
Back End. Docente: Boris Astorga Parraguez.

Integra catálogo de películas y series, reseñas y atención al cliente con
tickets, conversaciones y un asistente virtual. Es un prototipo inspirado en
Entel TV Chile; no es un servicio oficial ni reproduce películas o series.

## Requisitos

- Windows y PowerShell.
- Python 3.11 de 64 bits.
- MySQL 8.4; versión utilizada en la comprobación integrada: 8.4.13.
- Acceso a una cuenta de MySQL que permita preparar una base para el proyecto.
- Clave propia de Gemini si se desea utilizar el asistente real. El catálogo
  y la atención mediante tickets funcionan sin esa clave.

Las dependencias directas son Django 5.2.17, mysqlclient 2.3.0 y Pillow 12.3.0.
Bootstrap 5.3.3 y los recursos de presentación están incluidos localmente.
No se necesitan Node.js, OpenAI ni django-environ para ejecutar la aplicación.

## 1. Preparar el entorno virtual

Después de clonar el repositorio o extraer el ZIP, abrir PowerShell en la
carpeta que contiene `manage.py`. Si se usa Visual Studio Code, abrir esa
misma carpeta y utilizar su terminal integrada.

```powershell
py -3.11 --version
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip check
```

Si PowerShell no permite activar el entorno, se puede utilizar
`.\.venv\Scripts\python.exe` en lugar de `python` en todos los comandos
siguientes, sin cambiar la política del sistema.

La instalación de mysqlclient requiere una distribución compatible con
Python y Windows. Si pip informa que necesita compilarlo, revisar ese error
y los requisitos de compilación de la versión indicada antes de continuar.

## 2. Preparar MySQL

Estos pasos corresponden a una instalación nueva. Ejecutar las instrucciones
SQL en MySQL Workbench o en el cliente de MySQL con una cuenta administradora.
No ejecutarlas sobre una base existente que se quiera conservar sin revisar
su respaldo y configuración.

```sql
CREATE DATABASE enteltv
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

CREATE USER 'enteltv_app'@'localhost'
    IDENTIFIED BY 'REEMPLAZAR_POR_UNA_CLAVE_LOCAL';

GRANT ALL PRIVILEGES ON enteltv.* TO 'enteltv_app'@'localhost';
```

El texto `REEMPLAZAR_POR_UNA_CLAVE_LOCAL` es un marcador: debe sustituirse por
una contraseña elegida localmente. Los permisos se limitan a la base del
proyecto. Si ya existe una base o cuenta preparada, utilizar sus datos en
las variables de entorno y omitir su creación.

## 3. Configurar las variables de entorno

En la misma terminal de PowerShell que ejecutará Django:

```powershell
$env:DB_NAME = 'enteltv'
$env:DB_USER = 'enteltv_app'
$env:DB_HOST = 'localhost'
$env:DB_PORT = '3306'
$env:DJANGO_DEBUG = 'True'
$env:DJANGO_ALLOWED_HOSTS = 'localhost,127.0.0.1'

$claveMySQL = Read-Host 'Contraseña local de MySQL' -AsSecureString
$env:DB_PASSWORD = [System.Net.NetworkCredential]::new('', $claveMySQL).Password
$claveMySQL.Dispose()
Remove-Variable claveMySQL

$env:DJANGO_SECRET_KEY = (& python -c "import secrets; print(secrets.token_urlsafe(50))")
```

`DJANGO_SECRET_KEY` es obligatoria en la configuración normal. Para conservar
las sesiones entre reinicios, reutilizar de forma privada la misma clave
en lugar de generar otra cada vez. No publicar esta clave ni las contraseñas.

El proyecto obtiene la configuración con `os.environ` y **no carga
automáticamente archivos `.env`**. Las variables de este ejemplo pertenecen
a la terminal actual y a los procesos que se inicien desde ella.

`DJANGO_DEBUG=True` corresponde a la demostración local por HTTP y permite
servir estáticos y medios mediante Django. El servidor de desarrollo no se
presenta como una instalación de producción.

## 4. Comprobar la conexión y aplicar migraciones

Con el entorno activado y las variables configuradas:

```powershell
python -B manage.py check --database default
python -B manage.py migrate --plan
python -B manage.py migrate
python -B manage.py showmigrations
```

En una base existente, respaldar previamente sus datos y la carpeta `media`.
Las migraciones incluidas son el historial necesario para reconstruir el
esquema; no se deben borrar ni sustituir por tablas creadas manualmente.

## 5. Precargar el catálogo y crear el administrador

```powershell
python -B manage.py precargar_catalogo
python -B manage.py createsuperuser
```

La precarga crea 20 películas y 10 series de demostración. Se puede repetir:
reconoce los registros mediante identificadores estables y no duplica ni
sobrescribe cambios del administrador. No se ejecuta al visitar la página.

El superusuario se crea con datos elegidos durante el comando. La entrega no
incluye cuentas ni contraseñas para ingresar a una base privada.
El registro web permite crear clientes sin privilegios de personal.

Las portadas originales están en `catalogo/static/catalogo/portadas/`.
La precarga copia las imágenes de registros nuevos a `media`. El almacenamiento
puede ajustar el nombre si ya existe un archivo; el comando conserva el
nombre resultante en el registro. Las ejecuciones posteriores no vuelven a
copiar imágenes de contenidos existentes.

## 6. Configurar Gemini

El asistente real requiere una clave existente de Gemini. Introducirla
localmente sin enviarla por chat ni guardarla en el proyecto:

```powershell
$claveAsistente = Read-Host 'Clave de Gemini' -AsSecureString
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new('', $claveAsistente).Password
$claveAsistente.Dispose()
Remove-Variable claveAsistente

python -B manage.py shell -c "from django.conf import settings; print('Asistente configurado:', bool(settings.GEMINI_API_KEY))"
```

La clave debe establecerse **antes de iniciar el servidor y desde la misma
terminal**. Si Django ya está abierto en otra terminal o proceso, detenerlo
y reiniciarlo desde la terminal configurada. Una variable nueva no cambia el
entorno de un proceso que ya está iniciado.

El modelo configurado es `gemini-3.5-flash-lite` y el límite de espera del
servidor es de 20 segundos. No se requiere una clave de OpenAI.
Sin `GEMINI_API_KEY`, el asistente informa que no está configurado; los tickets
y la atención humana continúan disponibles.

## 7. Iniciar y utilizar la plataforma

```powershell
python -B manage.py runserver 127.0.0.1:8000
```

Abrir [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

| Perfil | Uso |
|---|---|
| Cliente | Registrarse, entrar al catálogo, buscar, valorar contenidos y consultar sus tickets. |
| Técnico activo | Atender la bandeja compartida y responder dentro de los tickets. |
| Administrador activo | Gestionar el catálogo y las herramientas administrativas. |

El superusuario puede gestionar las casillas `admin`, `tecnico` y `activo`
desde [Django Admin](http://127.0.0.1:8000/admin/). Son independientes:
una cuenta puede ser administradora y técnica simultáneamente.
El catálogo se administra desde el panel propio disponible en la navegación.

El cliente accede al asistente mediante la burbuja inferior derecha.
Desde la ficha de un contenido activo puede solicitar ayuda y crear un ticket
vinculado. También puede crear una consulta general desde el centro de ayuda.
El ejecutivo abre el contenido desde el ticket y la conversación conserva
autores y fechas.

Para detener Django, presionar `Ctrl+C` en la terminal. Al terminar la sesión
de trabajo se pueden quitar las variables sensibles:

```powershell
Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:DB_PASSWORD -ErrorAction SilentlyContinue
Remove-Item Env:DJANGO_SECRET_KEY -ErrorAction SilentlyContinue
```

## 8. Ejecutar las pruebas sin MySQL

Las pruebas usan un perfil que no importa la configuración normal, una base
SQLite en memoria y medios temporales. No requieren configurar credenciales
de MySQL, `DJANGO_SECRET_KEY` ni una clave del asistente.

```powershell
python -B manage.py test online administracion catalogo --settings=CallCenterGamer.settings_pruebas --verbosity=2
python -B manage.py check --settings=CallCenterGamer.settings_pruebas
python -B manage.py makemigrations --check --dry-run --settings=CallCenterGamer.settings_pruebas
```

La suite contiene 142 pruebas. Las consultas a Gemini se simulan; su aprobación
no equivale a realizar llamadas al proveedor real.
No usar el perfil de pruebas como configuración de la demostración en MySQL.

## Arquitectura y documentación

Se utiliza un proyecto Django con tres aplicaciones y una autenticación común:

- `online`: usuarios, acceso, tickets, mensajes y asistente.
- `catalogo`: películas, series, reseñas, filtros y precarga.
- `administracion`: paneles, usuarios, estadísticas y bandeja técnica.

La integración utiliza relaciones entre modelos y consultas del ORM, sin
una API REST propia ni JWT entre las aplicaciones.

- [Documentación técnica de la integración](documentacion/Documentacion_Tecnica_Integracion.md).
- [Informe de modificaciones](documentacion/Informe_Modificaciones.md).
- [Evidencias y verificaciones](documentacion/Evidencias.md).
- [Fuentes y licencias](documentacion/Fuentes_y_Licencias.md).

La comprobación integrada registró 142 pruebas aprobadas en SQLite, 49
comprobaciones satisfactorias en MySQL 8.4.13 y 26 migraciones aplicadas en
la base utilizada. Gemini real fue comprobado manualmente por la responsable
del proyecto. Las nuevas verificaciones de la copia de entrega se distinguen
en el documento de evidencias.

Las ilustraciones de las portadas son referenciales y no oficiales.
Los títulos no constituyen una afirmación de disponibilidad comercial en Entel TV.
El alcance no incluye reproducción, pagos, suscripciones, temporadas ni capítulos.
