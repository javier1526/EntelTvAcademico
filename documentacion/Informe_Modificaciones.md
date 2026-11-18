# Informe de modificaciones del proyecto Entel TV

Evaluación Sumativa N.º 3, Parte 2 — Programación Back End  
Docente: Boris Astorga Parraguez  
Fecha: 17 de noviembre de 2026

## Introducción

El proyecto integra el sistema CallCenterGamer desarrollado por el equipo
con un catálogo adaptado a la temática Entel TV Chile. El punto de partida
del catálogo fue `backendeva3`, material entregado por el docente con un modelo
de películas orientado a exhibiciones de cine.

Se conservó el Call Center como base del sistema. El catálogo se incorporó
como una aplicación interna, compartiendo autenticación, servidor y base
MySQL. Este informe describe los cambios por aplicación y su resultado.

## Funcionalidades conservadas de CallCenterGamer

El sistema original ya disponía de registro, inicio de sesión, modelo
personalizado de usuario, tickets, categorías y estados, conversación entre
usuarios y técnicos, actualización de mensajes, bandeja técnica, estadísticas
y herramientas administrativas.

Se conservaron los modelos `Usuario`, `Preguntas` y `Respuesta`, las casillas
independientes `admin`, `tecnico` y `activo`, el comportamiento del superusuario,
las rutas útiles y las cinco migraciones originales del Call Center.
También se mantuvo la integración con Gemini como base del asistente.

Los cambios se concentraron en adaptar esas funciones al catálogo y a la
atención de Entel TV, protegiendo sus permisos y el historial.

## Modificaciones en online

| Situación original | Modificación | Resultado |
|---|---|---|
| Registro y autenticación propios del Call Center. | El registro público fuerza permisos de cliente; se revisó el rechazo de cuentas inactivas y las redirecciones. | El cliente ingresa al catálogo sin obtener privilegios mediante campos manipulados. |
| Tickets generales sin referencia a una obra. | Se añadió `Preguntas.contenido` como relación opcional con `Contenido` y protección frente a borrado. | Se admiten tickets generales y consultas vinculadas a películas o series. |
| Edición con campos sensibles del ticket. | Propietario y fecha se controlan en el servidor. | La edición administrativa conserva autoría y fecha de creación. |
| Categorías de videojuegos y soporte informático. | Se incorporaron Cuenta y acceso, Películas y series, Problemas técnicos y Otros. | Las solicitudes nuevas utilizan categorías de Entel TV y los valores anteriores permanecen consultables. |
| Historial expuesto a acciones de eliminación. | Se bloqueó la eliminación física desde las interfaces administrativas y se incorporó la desactivación de cuentas. | Tickets y mensajes se conservan al desactivar usuarios. |
| Interfaz original de videojuegos. | Se adaptaron acceso, ayuda, tickets y conversaciones a la presentación compartida. | Catálogo y atención mantienen una navegación coherente. |

Se conservaron exactamente los estados Abierto, En proceso y Cerrada.
La conversación continúa dentro del ticket mediante `Respuesta` y la
actualización automática de mensajes. No se creó un chat humano paralelo.

El centro de ayuda permite crear tickets directamente. Cuando se accede
desde una ficha, el servidor valida el contenido y establece la relación;
no acepta referencias adicionales manipuladas en el formulario.

### Asistente virtual

El backend de `online/gemini_chat.py` se adaptó al uso de la plataforma y a los
datos públicos del catálogo activo. La consulta contextual utiliza el contenido
validado por el servidor, sin incorporar perfiles ni conversaciones privadas.

La presentación recupera la burbuja flotante del sistema original mediante
un componente compartido. Se utiliza el nombre Asistente virtual en la
interfaz y se conserva Gemini como proveedor interno. El centro de ayuda
puede abrir la burbuja y no mantiene otro formulario independiente de IA.

Se conservaron el modelo configurado, la clave mediante variable de entorno,
los límites de espera y el manejo de errores. La atención humana sigue
disponible sin requerir una consulta previa al asistente.

## Adaptación del catálogo del docente

El proyecto de referencia disponía de listados, ficha de película, formularios,
carga de imágenes y operaciones de gestión. Su modelo incluía conceptos
de cine, como sala, sucursal, exhibición y valor de entradas.

Se aprovecharon sus patrones de vistas, `ModelForm`, mensajes, archivos subidos
y redirección después de POST. Se adaptaron dentro de la aplicación `catalogo`,
sin trasladar la configuración independiente, su base de datos, usuarios ni
migraciones.

| Elemento de referencia | Adaptación realizada |
|---|---|
| Modelo `Pelicula` orientado a cine. | Modelo común `Contenido` para películas y series con título, tipo, género principal, año, sinopsis, imagen y estado. |
| Listado y ficha de películas. | Inicio con destacados, carruseles, listados por tipo y fichas con reseñas y ayuda. |
| Gestión básica. | Panel propio para administrador activo, con altas, edición, desactivación y reactivación. |
| Eliminación física. | Baja lógica para conservar referencias e historial. |
| Carga de ejemplos durante la navegación. | Comando explícito de precarga reproducible con 20 películas y 10 series. |
| Enlaces entre sistemas separados. | Rutas internas y relaciones entre modelos del mismo proyecto Django. |

La búsqueda por título se complementó con filtros combinables de tipo, género
y año, y ordenamiento alfabético y por año en ambas direcciones.

### Funcionalidades nuevas del catálogo

Se incorporó el modelo `Resena` con calificación de 1 a 5 y comentario.
El autor puede editar o eliminar su valoración en un contenido activo.
La ficha muestra promedio y cantidad de reseñas. La unicidad por autor y
contenido se valida en el servidor y en la base de datos.

Se incorporó también la ficha de consulta histórica desde tickets. Un contenido
inactivo deja de aparecer en el catálogo, pero su registro y reseñas permanecen.
El propietario del ticket o el personal autorizado puede consultarlo con el
aviso «Contenido no disponible», sin crear nuevas solicitudes ni reseñas
sobre esa ficha.

El catálogo inicial conserva los 30 títulos de demostración y sus ilustraciones
locales. La carga repetida no duplica contenidos ni reemplaza ediciones del
administrador. No se afirma que los títulos estén disponibles comercialmente
en Entel TV.

## Modificaciones en administracion

Se conservaron el panel administrativo, las estadísticas, la gestión de usuarios
y el escritorio técnico. La bandeja continúa siendo compartida, sin asignación
individual de un ejecutivo a cada ticket.

Se revisaron los permisos para separar el acceso del cliente, del técnico y
del administrador. La gestión del catálogo exige `admin`, mientras que el
personal técnico mantiene las funciones de atención.

La baja de usuarios se realiza por desactivación y protege el historial.
La edición de tickets funciona sin llamadas a OpenAI. Las estadísticas siguen
obteniéndose de los datos del proyecto y no requieren una clave de IA.

Django Admin mantiene la administración de perfiles y registros, con sus
controles de conservación. La plantilla administrativa de estadísticas
`analytics_ia.html` permanece activa, aunque su nombre técnico provenga
del proyecto original.

## Integración de modelos, formularios y migraciones

La relación central añadida es `Preguntas.contenido`, opcional para mantener
compatibilidad con tickets generales y anteriores. El catálogo y las reseñas
utilizan el usuario personalizado existente.

Los formularios validan los campos propios del catálogo, la calificación,
el comentario y las referencias permitidas. Las vistas verifican permisos,
asignan los datos controlados por el servidor y devuelven las pantallas
correspondientes mediante rutas del mismo proyecto.

| Migración incorporada | Cambio |
|---|---|
| `catalogo.0001_initial` | Creación de `Contenido`. |
| `catalogo.0002_resena` | Creación de `Resena`, relaciones y restricciones. |
| `online.0006_preguntas_contenido_alter_preguntas_categoria` | Relación opcional del ticket y adaptación de categorías. |

Las migraciones anteriores se conservaron. La base utilizada en la verificación
integrada tiene 26 migraciones aplicadas, contando las propias y las de Django.

## Presentación y organización de la entrega

La identidad visual utiliza fondos oscuros, texto claro, tarjetas de contenido
y acentos rosados. Se unificaron login, registro, catálogo, reseñas, ayuda,
conversaciones y paneles mediante plantillas y estilos compartidos.

Los recursos de Bootstrap, CSS, JavaScript y portadas son locales. El diseño
es propio e inspirado en referencias públicas de Entel TV Chile; no es una
reproducción de sus hojas CSS. Se conserva el aviso de prototipo académico
no oficial.

La entrega conserva las tres aplicaciones, sus archivos convencionales,
modelos, migraciones, pruebas, medios y precarga. Se excluyeron recursos
antiguos sin uso y materiales internos de seguimiento. Las dependencias directas
son Django, mysqlclient y Pillow; se retiraron OpenAI y django-environ al no
tener consumidores activos. La configuración utiliza variables de entorno y
no distribuye credenciales personales.

## Resultados

La comprobación integrada registró 142 pruebas automatizadas aprobadas en
SQLite aislado y 49 comprobaciones funcionales satisfactorias sobre MySQL
8.4.13. El catálogo inicial contiene 20 películas y 10 series.
El funcionamiento con Gemini real fue comprobado manualmente por la responsable
del proyecto y se distingue de las respuestas simuladas utilizadas en las pruebas.

La verificación específica de la copia de entrega se documenta por separado
en [Evidencias](Evidencias.md). Las fuentes y condiciones de los recursos se
conservan en [Fuentes y licencias](Fuentes_y_Licencias.md).

## Conclusión

El resultado conserva la atención al cliente de CallCenterGamer y adapta el
catálogo del docente a un sistema conjunto de películas y series. La relación
entre contenido y ticket conecta ambos componentes: el cliente solicita ayuda
desde una ficha y el ejecutivo consulta la obra y responde dentro del mismo
historial.

Las reseñas, la baja lógica, las fichas históricas y la presentación compartida
completan la personalización temática. La integración funciona dentro de un
único proyecto Django y mantiene el alcance académico solicitado.
