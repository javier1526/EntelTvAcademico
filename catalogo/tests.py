import base64
import uuid
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from online.models import Preguntas, Respuesta, Usuario

from .forms import FormularioContenido
from .models import Contenido, Resena


class PruebasCatalogo(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cliente = Usuario.objects.create_user(
            'cliente@example.com', 'cliente', 'clave-segura-123'
        )
        cls.tecnico = Usuario.objects.create_user(
            'tecnico@example.com', 'tecnico', 'clave-segura-123', tecnico=True
        )
        cls.administrador = Usuario.objects.create_user(
            'admin@example.com', 'administrador', 'clave-segura-123',
            admin=True,
        )
        cls.administrador_tecnico = Usuario.objects.create_user(
            'ambos@example.com', 'ambos', 'clave-segura-123',
            admin=True, tecnico=True,
        )
        cls.pelicula = Contenido.objects.create(
            titulo='Alfa', tipo='pelicula', genero='aventura',
            anio=2000, sinopsis='Una aventura de demostración.',
        )
        cls.serie = Contenido.objects.create(
            titulo='beta', tipo='serie', genero='drama',
            anio=2020, sinopsis='Una serie de demostración.',
        )

    def setUp(self):
        self.client.force_login(self.cliente)
        self.carpeta_medios = TemporaryDirectory(prefix='enteltv-catalogo-')
        self.addCleanup(self.carpeta_medios.cleanup)
        configuracion = override_settings(MEDIA_ROOT=self.carpeta_medios.name)
        configuracion.enable()
        self.addCleanup(configuracion.disable)

    def datos_contenido(self, **cambios):
        datos = {
            'titulo': 'Contenido nuevo', 'tipo': 'pelicula',
            'genero': 'comedia', 'anio': 2005,
            'sinopsis': 'Sinopsis escrita para esta prueba.', 'activo': 'on',
        }
        datos.update(cambios)
        return datos

    def test_visitante_necesita_sesion_en_todas_las_rutas(self):
        self.client.logout()
        rutas = [
            reverse('catalogo:' + nombre)
            for nombre in ('inicio', 'listado', 'peliculas', 'series',
                           'gestion', 'agregar')
        ]
        rutas += [
            reverse('catalogo:' + nombre, args=[self.pelicula.pk])
            for nombre in ('detalle', 'editar', 'desactivar', 'reactivar')
        ]
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)
                self.assertEqual(respuesta.status_code, 302)
                self.assertTrue(respuesta.url.startswith(reverse('Login')))

    def test_inicio_muestra_destacado_y_carruseles(self):
        respuesta = self.client.get(reverse('catalogo:inicio'))
        self.assertContains(respuesta, 'carrusel-peliculas')
        self.assertContains(respuesta, 'carrusel-series')
        self.assertEqual(respuesta.context['destacado'], self.serie)
        self.assertIn(self.pelicula, respuesta.context['peliculas'])
        self.assertIn(self.serie, respuesta.context['series'])
        self.assertContains(respuesta, 'Prototipo académico')
        self.assertNotContains(respuesta, 'Solicitar ayuda')

    def test_catalogos_separan_peliculas_y_series(self):
        for nombre, esperado in (
            ('peliculas', self.pelicula), ('series', self.serie),
        ):
            with self.subTest(listado=nombre):
                respuesta = self.client.get(reverse('catalogo:' + nombre))
                self.assertEqual(
                    list(respuesta.context['contenidos']), [esperado]
                )

    def test_busqueda_por_titulo_no_distingue_mayusculas(self):
        respuesta = self.client.get(
            reverse('catalogo:listado'), {'q': 'BETA'}
        )
        self.assertEqual(list(respuesta.context['contenidos']), [self.serie])

    def test_filtros_se_combinan(self):
        respuesta = self.client.get(reverse('catalogo:listado'), {
            'q': 'al', 'tipo': 'pelicula', 'genero': 'aventura', 'anio': 2000,
        })
        self.assertEqual(
            list(respuesta.context['contenidos']), [self.pelicula]
        )
        respuesta = self.client.get(reverse('catalogo:listado'), {
            'tipo': 'pelicula', 'genero': 'drama', 'anio': 2000,
        })
        self.assertEqual(list(respuesta.context['contenidos']), [])

    def test_tipo_fijo_no_se_manipula_desde_la_url(self):
        respuesta = self.client.get(
            reverse('catalogo:peliculas'), {'tipo': 'serie'}
        )
        self.assertEqual(
            list(respuesta.context['contenidos']), [self.pelicula]
        )

    def test_ordenes_alfabeticos_y_por_anio(self):
        for orden, esperados in (
            ('titulo', [self.pelicula, self.serie]),
            ('-titulo', [self.serie, self.pelicula]),
            ('anio', [self.pelicula, self.serie]),
            ('-anio', [self.serie, self.pelicula]),
        ):
            with self.subTest(orden=orden):
                respuesta = self.client.get(
                    reverse('catalogo:listado'), {'orden': orden}
                )
                self.assertEqual(
                    list(respuesta.context['contenidos']), esperados
                )

    def test_filtros_invalidos_muestran_errores_sin_fallar(self):
        for datos in (
            {'anio': 'abc'}, {'anio': 1800},
            {'anio': timezone.now().year + 1}, {'genero': 'inventado'},
            {'tipo': 'video'}, {'orden': 'titulo; DROP TABLE catalogo'},
        ):
            with self.subTest(filtros=datos):
                respuesta = self.client.get(reverse('catalogo:listado'), datos)
                self.assertEqual(respuesta.status_code, 200)
                self.assertTrue(respuesta.context['formulario'].errors)
                self.assertEqual(list(respuesta.context['contenidos']), [])
        self.assertEqual(Contenido.objects.count(), 2)

    def test_sin_resultados_muestra_mensaje(self):
        respuesta = self.client.get(
            reverse('catalogo:listado'), {'q': 'No existe este título'}
        )
        self.assertContains(respuesta, 'No encontramos resultados')

    def test_ficha_muestra_datos_de_contenido_activo(self):
        respuesta = self.client.get(
            reverse('catalogo:detalle', args=[self.pelicula.pk])
        )
        self.assertContains(respuesta, 'Alfa')
        self.assertContains(respuesta, 'Una aventura de demostración.')
        self.assertContains(respuesta, 'Aventura')
        self.assertContains(respuesta, '2000')
        self.assertNotContains(respuesta, 'Editar contenido')

    def test_inactivos_no_aparecen_en_inicio_listados_busquedas_ni_ficha(self):
        self.pelicula.activo = False
        self.pelicula.save(update_fields=['activo'])
        for nombre in ('inicio', 'listado', 'peliculas', 'series'):
            with self.subTest(ruta=nombre):
                respuesta = self.client.get(
                    reverse('catalogo:' + nombre), {'q': 'Alfa'}
                )
                self.assertNotContains(
                    respuesta,
                    reverse('catalogo:detalle', args=[self.pelicula.pk]),
                )
                if nombre != 'inicio':
                    self.assertNotIn(
                        self.pelicula, respuesta.context['contenidos']
                    )
        for usuario in (self.cliente, self.tecnico, self.administrador):
            self.client.force_login(usuario)
            respuesta = self.client.get(
                reverse('catalogo:detalle', args=[self.pelicula.pk])
            )
            self.assertEqual(respuesta.status_code, 404)

    def test_visitar_catalogo_vacio_no_precarga_registros(self):
        Contenido.objects.update(activo=False)
        respuesta = self.client.get(reverse('catalogo:inicio'))
        self.assertContains(respuesta, 'todavía no tiene contenidos activos')
        self.assertEqual(Contenido.objects.count(), 2)

    def test_portada_faltante_utiliza_reemplazo(self):
        self.assertIn('portada-no-disponible.svg', self.pelicula.url_imagen)
        self.pelicula.imagen = 'archivo-inexistente.png'
        self.assertIn('portada-no-disponible.svg', self.pelicula.url_imagen)

    def test_cliente_y_tecnico_no_gestionan_contenidos(self):
        for usuario in (self.cliente, self.tecnico):
            self.client.force_login(usuario)
            rutas = [reverse('catalogo:gestion'), reverse('catalogo:agregar')]
            rutas += [
                reverse('catalogo:' + nombre, args=[self.pelicula.pk])
                for nombre in ('editar', 'desactivar', 'reactivar')
            ]
            for ruta in rutas:
                with self.subTest(usuario=usuario.usuario, ruta=ruta):
                    respuesta = self.client.post(ruta, self.datos_contenido())
                    self.assertEqual(respuesta.status_code, 403)
            for ruta in rutas[:3]:
                self.assertEqual(self.client.get(ruta).status_code, 403)
        self.pelicula.refresh_from_db()
        self.assertTrue(self.pelicula.activo)
        self.assertEqual(self.pelicula.titulo, 'Alfa')
        self.assertEqual(Contenido.objects.count(), 2)

    def test_admin_solo_o_con_permiso_tecnico_puede_gestionar(self):
        for usuario in (self.administrador, self.administrador_tecnico):
            self.client.force_login(usuario)
            self.assertEqual(
                self.client.get(reverse('catalogo:gestion')).status_code, 200
            )

    def test_cuenta_desactivada_con_sesion_previa_no_gestiona(self):
        self.client.force_login(self.administrador)
        Usuario.objects.filter(pk=self.administrador.pk).update(activo=False)
        respuesta = self.client.post(
            reverse('catalogo:agregar'), self.datos_contenido()
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.url.startswith(reverse('Login')))
        self.assertEqual(Contenido.objects.count(), 2)

    def test_admin_crea_contenido_con_portada_local(self):
        imagen = SimpleUploadedFile(
            'portada.png', base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ'
                'AAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg=='
            ), content_type='image/png',
        )
        self.client.force_login(self.administrador)
        respuesta = self.client.post(
            reverse('catalogo:agregar'), self.datos_contenido(imagen=imagen)
        )
        self.assertRedirects(respuesta, reverse('catalogo:gestion'))
        contenido = Contenido.objects.get(titulo='Contenido nuevo')
        self.assertTrue(contenido.imagen.storage.exists(contenido.imagen.name))
        self.assertTrue(contenido.activo)

    def test_admin_edita_datos_conservando_identificador(self):
        self.client.force_login(self.administrador)
        respuesta = self.client.post(
            reverse('catalogo:editar', args=[self.pelicula.pk]),
            self.datos_contenido(titulo='Título editado', tipo='serie'),
        )
        self.assertRedirects(respuesta, reverse('catalogo:gestion'))
        self.pelicula.refresh_from_db()
        self.assertEqual(self.pelicula.titulo, 'Título editado')
        self.assertEqual(self.pelicula.tipo, 'serie')
        self.assertEqual(Contenido.objects.count(), 2)

    def test_desactivar_y_reactivar_solo_por_post_sin_borrar(self):
        self.client.force_login(self.administrador)
        for nombre, estado in (('desactivar', False), ('reactivar', True)):
            ruta = reverse('catalogo:' + nombre, args=[self.pelicula.pk])
            self.assertEqual(self.client.get(ruta).status_code, 405)
            respuesta = self.client.post(ruta)
            self.assertRedirects(respuesta, reverse('catalogo:gestion'))
            self.pelicula.refresh_from_db()
            self.assertEqual(self.pelicula.activo, estado)
            self.assertEqual(self.pelicula.titulo, 'Alfa')
            self.assertEqual(Contenido.objects.count(), 2)

    def test_gestion_identifica_y_filtra_inactivos(self):
        self.pelicula.activo = False
        self.pelicula.save(update_fields=['activo'])
        self.client.force_login(self.administrador)
        respuesta = self.client.get(reverse('catalogo:gestion'))
        self.assertContains(respuesta, 'Inactivo')
        self.assertContains(respuesta, 'Reactivar')
        respuesta = self.client.get(
            reverse('catalogo:gestion'), {'estado': 'inactivo'}
        )
        self.assertEqual(
            list(respuesta.context['contenidos']), [self.pelicula]
        )

    def test_operaciones_exigen_csrf(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.administrador)
        ruta = reverse('catalogo:agregar')
        self.assertEqual(
            cliente.post(ruta, self.datos_contenido()).status_code, 403
        )
        cliente.get(ruta)
        token = cliente.cookies['csrftoken'].value
        datos = self.datos_contenido(csrfmiddlewaretoken=token)
        self.assertEqual(cliente.post(ruta, datos).status_code, 302)

    def test_modelo_y_formulario_validan_campos_minimos(self):
        for cambios in (
            {'titulo': '   '}, {'sinopsis': '   '}, {'tipo': 'video'},
            {'genero': 'inventado'}, {'anio': 1800},
            {'anio': timezone.now().year + 1},
        ):
            with self.subTest(cambios=cambios):
                formulario = FormularioContenido(
                    self.datos_contenido(**cambios)
                )
                self.assertFalse(formulario.is_valid())
        self.pelicula.anio = timezone.now().year + 1
        with self.assertRaises(ValidationError):
            self.pelicula.full_clean()

    def test_archivo_no_imagen_y_svg_subido_se_rechazan(self):
        for nombre, datos in (
            ('portada.txt', b'No es una imagen'),
            ('portada.svg', b'<svg xmlns="http://www.w3.org/2000/svg"/>'),
        ):
            with self.subTest(nombre=nombre):
                formulario = FormularioContenido(
                    self.datos_contenido(),
                    {'imagen': SimpleUploadedFile(nombre, datos)},
                )
                self.assertFalse(formulario.is_valid())
                self.assertIn('imagen', formulario.errors)

    def test_django_admin_no_permite_eliminar_contenidos(self):
        solicitud = RequestFactory().get('/admin/')
        solicitud.user = self.administrador
        configuracion = admin.site._registry[Contenido]
        self.assertFalse(
            configuracion.has_delete_permission(solicitud, self.pelicula)
        )
        self.assertNotIn(
            'delete_selected', configuracion.get_actions(solicitud)
        )
        self.client.force_login(self.administrador)
        respuesta = self.client.post(
            reverse(
                'admin:catalogo_contenido_delete', args=[self.pelicula.pk]
            ),
            {'post': 'yes'},
        )
        self.assertEqual(respuesta.status_code, 403)
        self.assertTrue(Contenido.objects.filter(pk=self.pelicula.pk).exists())

    def test_identificador_inexistente_devuelve_404(self):
        respuesta = self.client.get(
            reverse('catalogo:detalle', args=[uuid.uuid4()])
        )
        self.assertEqual(respuesta.status_code, 404)


class PruebasResenasEHistorial(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.autor = Usuario.objects.create_user(
            'autor@example.com', 'autor', 'clave-segura-123'
        )
        cls.otra_persona = Usuario.objects.create_user(
            'otra@example.com', 'otra', 'clave-segura-123'
        )
        cls.tecnico = Usuario.objects.create_user(
            'ejecutivo@example.com', 'ejecutivo', 'clave-segura-123',
            tecnico=True,
        )
        cls.administrador = Usuario.objects.create_user(
            'gestion@example.com', 'gestion', 'clave-segura-123', admin=True
        )
        cls.contenido = Contenido.objects.create(
            titulo='Obra para reseñar', tipo='pelicula', genero='drama',
            anio=2001, sinopsis='Una historia para verificar la integración.',
        )
        cls.ticket = Preguntas.objects.create(
            Titulo='Ayuda con esta obra', Pregunta='Consulta inicial privada',
            Usuario=cls.autor, Fecha_creacion=timezone.now(),
            contenido=cls.contenido,
        )

    def setUp(self):
        self.client.force_login(self.autor)
        self.ruta_ficha = reverse('catalogo:detalle', args=[self.contenido.pk])
        self.ruta_creacion = reverse(
            'catalogo:crear_resena', args=[self.contenido.pk]
        )
        self.ruta_historica = reverse(
            'catalogo:ficha_desde_ticket', args=[self.ticket.pk]
        )

    def crear_resena(self, usuario=None, calificacion=4):
        return Resena.objects.create(
            contenido=self.contenido, usuario=usuario or self.autor,
            calificacion=calificacion, comentario='Comentario original.',
        )

    def desactivar(self):
        self.contenido.activo = False
        self.contenido.save(update_fields=['activo'])

    def test_ficha_ofrece_ayuda_y_formulario_de_resena(self):
        respuesta = self.client.get(self.ruta_ficha)
        self.assertContains(respuesta, 'Solicitar ayuda')
        self.assertContains(respuesta, 'Publicar reseña')
        self.assertContains(respuesta, 'Sin valoraciones')
        self.assertEqual(respuesta.context['cantidad_resenas'], 0)

    def test_crear_resena_guarda_autor_y_contenido_del_servidor(self):
        respuesta = self.client.post(self.ruta_creacion, {
            'calificacion': '5', 'comentario': '  Muy recomendable.  ',
            'usuario': self.otra_persona.pk, 'contenido': 'inexistente',
        })
        self.assertRedirects(respuesta, self.ruta_ficha)
        resena = Resena.objects.get()
        self.assertEqual(resena.usuario, self.autor)
        self.assertEqual(resena.contenido, self.contenido)
        ficha = self.client.get(self.ruta_ficha)
        self.assertEqual(ficha.context['promedio'], 5)
        self.assertEqual(resena.calificacion, 5)
        self.assertEqual(resena.comentario, 'Muy recomendable.')

    def test_calificacion_rechaza_valores_invalidos(self):
        for calificacion in ('0', '6', '-1', '2.5', 'texto', ''):
            with self.subTest(calificacion=calificacion):
                respuesta = self.client.post(self.ruta_creacion, {
                    'calificacion': calificacion, 'comentario': 'Comentario.',
                })
                self.assertIn(
                    'calificacion',
                    respuesta.context['formulario_resena'].errors,
                )
        self.assertFalse(Resena.objects.exists())

    def test_comentario_es_obligatorio_y_acotado(self):
        for comentario in ('', '   ', 'a' * 1001):
            with self.subTest(longitud=len(comentario)):
                respuesta = self.client.post(self.ruta_creacion, {
                    'calificacion': 3, 'comentario': comentario,
                })
                self.assertIn(
                    'comentario', respuesta.context['formulario_resena'].errors
                )
        self.assertFalse(Resena.objects.exists())

    def test_duplicado_muestra_error_y_conserva_original(self):
        resena = self.crear_resena()
        respuesta = self.client.post(self.ruta_creacion, {
            'calificacion': 1, 'comentario': 'Segundo envío.',
        })
        self.assertContains(respuesta, 'Ya publicaste una reseña')
        self.assertEqual(Resena.objects.count(), 1)
        resena.refresh_from_db()
        self.assertEqual(resena.calificacion, 4)

    def test_base_impide_duplicados(self):
        self.crear_resena()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.crear_resena()

    def test_base_impide_calificacion_fuera_de_rango(self):
        for calificacion in (0, 6):
            with self.subTest(calificacion=calificacion):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.crear_resena(calificacion=calificacion)

    def test_autor_puede_editar_su_resena(self):
        resena = self.crear_resena()
        ruta = reverse('catalogo:editar_resena', args=[resena.pk])
        self.assertEqual(self.client.get(ruta).status_code, 200)
        respuesta = self.client.post(ruta, {
            'calificacion': 2, 'comentario': 'Opinión actualizada.',
            'usuario': self.otra_persona.pk, 'contenido': 'otro',
        })
        self.assertRedirects(respuesta, self.ruta_ficha)
        resena.refresh_from_db()
        self.assertEqual(resena.calificacion, 2)
        self.assertEqual(resena.comentario, 'Opinión actualizada.')
        self.assertEqual(resena.usuario, self.autor)
        self.assertEqual(resena.contenido, self.contenido)
        ficha = self.client.get(self.ruta_ficha)
        self.assertEqual(ficha.context['promedio'], 2)

    def test_autor_puede_eliminar_su_resena_por_post(self):
        resena = self.crear_resena()
        ruta = reverse('catalogo:eliminar_resena', args=[resena.pk])
        self.assertEqual(self.client.get(ruta).status_code, 405)
        self.assertTrue(Resena.objects.exists())
        self.assertRedirects(self.client.post(ruta), self.ruta_ficha)
        self.assertFalse(Resena.objects.exists())
        ficha = self.client.get(self.ruta_ficha)
        self.assertEqual(ficha.context['cantidad_resenas'], 0)
        self.assertIsNone(ficha.context['promedio'])

    def test_otros_incluso_personal_no_modifican_resena_ajena(self):
        resena = self.crear_resena()
        for usuario in (
            self.otra_persona, self.tecnico, self.administrador
        ):
            self.client.force_login(usuario)
            for accion in ('editar_resena', 'eliminar_resena'):
                with self.subTest(usuario=usuario.usuario, accion=accion):
                    ruta = reverse('catalogo:' + accion, args=[resena.pk])
                    respuesta = self.client.post(ruta, {
                        'calificacion': 1, 'comentario': 'Cambio ajeno.',
                    })
                    self.assertEqual(respuesta.status_code, 404)
        resena.refresh_from_db()
        self.assertEqual(resena.calificacion, 4)

    def test_visitante_no_accede_a_resenas_ni_historial(self):
        resena = self.crear_resena()
        self.client.logout()
        for ruta in (
            self.ruta_creacion, self.ruta_historica,
            reverse('catalogo:editar_resena', args=[resena.pk]),
            reverse('catalogo:eliminar_resena', args=[resena.pk]),
        ):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.post(ruta).status_code, 302)

    def test_mutaciones_de_resenas_exigen_csrf(self):
        navegador = Client(enforce_csrf_checks=True)
        navegador.force_login(self.autor)
        resena = self.crear_resena()
        for ruta in (
            self.ruta_creacion,
            reverse('catalogo:editar_resena', args=[resena.pk]),
            reverse('catalogo:eliminar_resena', args=[resena.pk]),
        ):
            self.assertEqual(navegador.post(ruta).status_code, 403)

    def test_crear_resena_exige_post(self):
        self.assertEqual(self.client.get(self.ruta_creacion).status_code, 405)

    def test_promedio_y_cantidad_incluyen_todas_las_resenas(self):
        self.crear_resena(calificacion=5)
        self.crear_resena(usuario=self.otra_persona, calificacion=2)
        respuesta = self.client.get(self.ruta_ficha)
        self.assertEqual(respuesta.context['promedio'], 3.5)
        self.assertEqual(respuesta.context['cantidad_resenas'], 2)
        self.assertContains(respuesta, 'Comentario original.', count=2)
        self.assertNotContains(respuesta, 'Publicar reseña')
        self.assertContains(respuesta, 'Editar mi reseña', count=1)

    def test_comentario_se_muestra_escapado(self):
        self.client.post(self.ruta_creacion, {
            'calificacion': 3, 'comentario': '<script>alert(1)</script>',
        })
        respuesta = self.client.get(self.ruta_ficha)
        self.assertContains(respuesta, '&lt;script&gt;')
        self.assertNotContains(respuesta, '<script>alert(1)</script>')

    def test_propietario_y_personal_abren_ficha_inactiva_desde_ticket(self):
        self.desactivar()
        for usuario in (self.autor, self.tecnico, self.administrador):
            self.client.force_login(usuario)
            respuesta = self.client.get(self.ruta_historica)
            self.assertContains(respuesta, 'Contenido no disponible')
            self.assertNotContains(respuesta, 'Publicar reseña')
            self.assertNotContains(respuesta, 'Solicitar ayuda')
            self.assertNotContains(respuesta, 'Editar contenido')

    def test_cliente_ajeno_no_abre_historial_con_identificadores(self):
        self.desactivar()
        self.client.force_login(self.otra_persona)
        self.assertEqual(self.client.get(self.ruta_historica).status_code, 403)
        self.assertEqual(self.client.get(self.ruta_ficha).status_code, 404)

    def test_ticket_general_no_abre_ficha_historica(self):
        self.ticket.contenido = None
        self.ticket.save(update_fields=['contenido'])
        self.assertEqual(self.client.get(self.ruta_historica).status_code, 404)

    def test_ticket_inexistente_no_abre_ficha(self):
        ruta = reverse('catalogo:ficha_desde_ticket', args=[999999])
        self.assertEqual(self.client.get(ruta).status_code, 404)

    def test_ficha_normal_inactiva_no_admite_ticket_como_atajo(self):
        self.desactivar()
        respuesta = self.client.get(
            self.ruta_ficha, {'ticket': self.ticket.pk}
        )
        self.assertEqual(respuesta.status_code, 404)

    def test_inactivo_rechaza_creacion_edicion_y_eliminacion_de_resena(self):
        resena = self.crear_resena()
        self.desactivar()
        for ruta in (
            self.ruta_creacion,
            reverse('catalogo:editar_resena', args=[resena.pk]),
            reverse('catalogo:eliminar_resena', args=[resena.pk]),
        ):
            with self.subTest(ruta=ruta):
                respuesta = self.client.post(ruta, {
                    'calificacion': 1, 'comentario': 'No debe guardarse.',
                })
                self.assertEqual(respuesta.status_code, 404)
        resena.refresh_from_db()
        self.assertEqual(resena.calificacion, 4)
        respuesta = self.client.get(self.ruta_historica)
        self.assertContains(respuesta, 'Comentario original.')
        self.assertNotContains(respuesta, 'Editar mi reseña')

    def test_baja_y_reactivacion_conservan_todo_el_historial(self):
        resena = self.crear_resena()
        mensaje = Respuesta.objects.create(
            id_Pregunta=self.ticket, Usuario=self.tecnico,
            FechaHora=timezone.now(), Respuesta='Respuesta conservada.',
        )
        self.client.force_login(self.administrador)
        for accion in ('desactivar', 'reactivar'):
            self.client.post(reverse('catalogo:' + accion, args=[
                self.contenido.pk
            ]))
            self.ticket.refresh_from_db()
            resena.refresh_from_db()
            mensaje.refresh_from_db()
            self.assertEqual(self.ticket.contenido_id, self.contenido.pk)
            self.assertEqual(mensaje.id_Pregunta, self.ticket)
            self.assertEqual(resena.comentario, 'Comentario original.')
        self.assertContains(
            self.client.get(self.ruta_ficha), 'Obra para reseñar'
        )

    def test_contenido_relacionado_tiene_proteccion_contra_borrado(self):
        with self.assertRaises(ProtectedError):
            self.contenido.delete()
        self.assertTrue(Preguntas.objects.filter(pk=self.ticket.pk).exists())

    def test_resenas_protegen_contenido_y_autor(self):
        self.crear_resena()
        self.ticket.contenido = None
        self.ticket.save(update_fields=['contenido'])
        with self.assertRaises(ProtectedError):
            self.contenido.delete()
        with self.assertRaises(ProtectedError):
            self.autor.delete()

    def test_cuenta_desactivada_no_consulta_historial_ni_publica(self):
        Usuario.objects.filter(pk=self.autor.pk).update(activo=False)
        self.assertEqual(self.client.get(self.ruta_historica).status_code, 302)
        self.assertEqual(self.client.post(self.ruta_creacion, {
            'calificacion': 5, 'comentario': 'No permitido.',
        }).status_code, 302)
        self.assertFalse(Resena.objects.exists())

    def test_django_admin_no_permite_mutar_resenas_ajenas(self):
        resena = self.crear_resena()
        self.client.force_login(self.administrador)
        for accion in ('change', 'delete'):
            ruta = reverse(f'admin:catalogo_resena_{accion}', args=[resena.pk])
            self.assertEqual(self.client.post(ruta, {
                'calificacion': 1, 'comentario': 'Cambio administrativo.',
            }).status_code, 403)
        self.assertEqual(
            self.client.post(reverse('admin:catalogo_resena_add')).status_code,
            403,
        )


class PruebasPrecarga(TestCase):
    def setUp(self):
        self.carpeta_medios = TemporaryDirectory(prefix='enteltv-precarga-')
        self.addCleanup(self.carpeta_medios.cleanup)
        configuracion = override_settings(MEDIA_ROOT=self.carpeta_medios.name)
        configuracion.enable()
        self.addCleanup(configuracion.disable)

    def cargar(self):
        salida = StringIO()
        call_command('precargar_catalogo', stdout=salida)
        return salida.getvalue()

    def test_carga_exactamente_20_peliculas_y_10_series_con_portadas(self):
        self.cargar()
        self.assertEqual(Contenido.objects.count(), 30)
        self.assertEqual(Contenido.objects.filter(tipo='pelicula').count(), 20)
        self.assertEqual(Contenido.objects.filter(tipo='serie').count(), 10)
        for contenido in Contenido.objects.all():
            with self.subTest(titulo=contenido.titulo):
                contenido.full_clean()
                self.assertTrue(contenido.activo)
                self.assertTrue(
                    contenido.imagen.storage.exists(contenido.imagen.name)
                )

    def test_repetir_precarga_no_duplica_ni_sobrescribe_ediciones(self):
        self.cargar()
        contenido = Contenido.objects.get(titulo='Toy Story')
        contenido.titulo = 'Título personalizado'
        contenido.tipo = 'serie'
        contenido.genero = 'drama'
        contenido.anio = 2000
        contenido.sinopsis = 'Sinopsis personalizada por el administrador.'
        contenido.imagen = ''
        contenido.activo = False
        contenido.save()
        antes = list(Contenido.objects.order_by('id').values())
        archivos_antes = {
            archivo.relative_to(self.carpeta_medios.name).as_posix():
                archivo.read_bytes()
            for archivo in Path(self.carpeta_medios.name).rglob('*')
            if archivo.is_file()
        }
        salida = self.cargar()
        self.assertIn('Creados: 0', salida)
        self.assertEqual(
            antes, list(Contenido.objects.order_by('id').values())
        )
        archivos_despues = {
            archivo.relative_to(self.carpeta_medios.name).as_posix():
                archivo.read_bytes()
            for archivo in Path(self.carpeta_medios.name).rglob('*')
            if archivo.is_file()
        }
        self.assertEqual(archivos_antes, archivos_despues)

    def test_precarga_conserva_contenidos_creados_manualmente(self):
        contenido = Contenido.objects.create(
            titulo='Manual', tipo='pelicula', genero='drama', anio=2000,
            sinopsis='Contenido creado por el administrador.', activo=False,
        )
        self.cargar()
        contenido.refresh_from_db()
        self.assertEqual(Contenido.objects.count(), 31)
        self.assertFalse(contenido.activo)
        self.assertEqual(contenido.titulo, 'Manual')
