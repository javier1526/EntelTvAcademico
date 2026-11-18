import json
import uuid
from html.parser import HTMLParser
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib import admin
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import resolve, reverse
from django.utils import timezone

from catalogo.models import Contenido
from online.forms import PreguntasForm, RegisterForm
from online.models import Preguntas, Respuesta, Usuario


class ConversationAccessTests(TestCase):
    def setUp(self):
        self.owner = self.create_user('owner', 'owner@example.com')
        self.other = self.create_user('other', 'other@example.com')
        self.question = Preguntas.objects.create(
            Titulo='Consulta',
            Pregunta='No inicia el juego',
            Fecha_creacion=timezone.now(),
            Usuario=self.owner,
        )

    def create_user(self, username, email, **fields):
        user = Usuario.objects.create(
            usuario=username,
            correo=email,
            **fields,
        )
        user.set_password('test-password-123')
        user.save()
        return user

    def test_user_cannot_view_another_users_conversation(self):
        self.client.force_login(self.other)

        response = self.client.get(
            reverse('respuestas', args=[self.other.id, self.question.idPregunta])
        )

        self.assertRedirects(response, f'/Inicio/{self.other.id}/')

    def test_user_cannot_read_another_users_messages_api(self):
        self.client.force_login(self.other)
        response = self.client.get(
            reverse('obtener_mensajes', args=[self.question.idPregunta])
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('mensajes', response.json())

    def test_owner_and_technician_can_read_messages_api(self):
        tecnico = self.create_user('tecnico', 'tecnico@example.com', tecnico=True)
        for usuario in (self.owner, tecnico):
            with self.subTest(usuario=usuario.usuario):
                self.client.force_login(usuario)
                response = self.client.get(
                    reverse('obtener_mensajes', args=[self.question.idPregunta])
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.json()['mensajes']), 1)

    def test_admin_and_technician_can_view_conversations(self):
        for username, email, role in (
            ('admin', 'admin@example.com', {'admin': True}),
            ('tech', 'tech@example.com', {'tecnico': True}),
        ):
            with self.subTest(role=username):
                user = self.create_user(username, email, **role)
                self.client.force_login(user)
                response = self.client.get(
                    reverse('respuestas', args=[user.id, self.question.idPregunta])
                )
                self.assertEqual(response.status_code, 200)

    def test_reply_uses_url_question_not_tampered_hidden_question(self):
        another_question = Preguntas.objects.create(
            Titulo='Otra consulta',
            Pregunta='No hay audio',
            Fecha_creacion=timezone.now(),
            Usuario=self.other,
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('respuestas', args=[self.owner.id, self.question.idPregunta]),
            {
                'Respuesta': 'Prueba reiniciar el juego.',
                'id_Pregunta': another_question.idPregunta,
                'Usuario': self.other.id,
                'FechaHora': timezone.now().isoformat(),
            },
        )

        self.assertRedirects(
            response,
            f'/Respuesta/{self.owner.id}/{self.question.idPregunta}/',
        )
        respuesta = Respuesta.objects.get()
        self.assertEqual(respuesta.id_Pregunta_id, self.question.idPregunta)
        self.assertEqual(respuesta.Usuario_id, self.owner.id)

    def test_logout_requires_post(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse('Logout'))

        self.assertEqual(response.status_code, 405)
        self.assertTrue(self.client.session.get('_auth_user_id'))

    def test_inactive_users_cannot_log_in(self):
        self.owner.activo = False
        self.owner.save()

        response = self.client.post(
            reverse('Login'),
            {'Usuario': self.owner.usuario, 'password': 'test-password-123'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse('_auth_user_id' in self.client.session)
        self.assertTrue(response.context['form'].non_field_errors())

    def test_ticket_category_is_saved(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('inicio', args=[self.owner.id]),
            {
                'Titulo': 'Sin sonido',
                'Pregunta': 'Mi computador no reproduce audio',
                'categoria': 'Problemas técnicos',
                'Usuario': self.other.id,  # La vista impide suplantar al dueño.
                'Fecha_creacion': timezone.now().isoformat(),
            },
        )
        self.assertRedirects(response, f'/Inicio/{self.owner.id}/')
        nueva = Preguntas.objects.get(Titulo='Sin sonido')
        self.assertEqual(nueva.categoria, 'Problemas técnicos')
        self.assertEqual(nueva.Usuario_id, self.owner.id)

    def test_technician_can_filter_and_change_ticket_state(self):
        tecnico = self.create_user('tecnico2', 'tecnico2@example.com', tecnico=True)
        self.question.categoria = 'Redes'
        self.question.save()
        self.client.force_login(tecnico)

        cambio = self.client.post(
            reverse('actualizar_estado', args=[self.question.idPregunta]),
            {'estado': 'En proceso'},
        )
        self.assertRedirects(cambio, '/Preguntas/')
        self.question.refresh_from_db()
        self.assertEqual(self.question.estado, 'En proceso')

        listado = self.client.get(reverse('listado_preguntas'), {
            'categoria': 'Redes', 'estado': 'En proceso', 'q': 'Consulta'
        })
        self.assertEqual(list(listado.context['Preguntas']), [self.question])

    def test_client_cannot_change_ticket_state(self):
        self.client.force_login(self.other)
        response = self.client.post(
            reverse('actualizar_estado', args=[self.question.idPregunta]),
            {'estado': 'Cerrada'},
        )
        self.assertRedirects(response, f'/Inicio/{self.other.id}/')
        self.question.refresh_from_db()
        self.assertEqual(self.question.estado, 'Abierto')

    def test_register_form_validates_rut_check_digit(self):
        datos = {
            'usuario': 'nuevo', 'correo': 'nuevo@example.com',
            'rut': '12.345.678-5', 'password': 'clave-segura-123',
            'password_2': 'clave-segura-123',
        }
        formulario = RegisterForm(datos)
        self.assertTrue(formulario.is_valid(), formulario.errors)
        self.assertEqual(formulario.cleaned_data['rut'], '12345678-5')

        datos['rut'] = '12.345.678-9'
        formulario = RegisterForm(datos)
        self.assertFalse(formulario.is_valid())
        self.assertIn('rut', formulario.errors)

    def test_cliente_no_publica_en_ticket_ajeno_con_id_suplantado(self):
        self.client.force_login(self.other)
        respuesta = self.client.post(
            reverse(
                'respuestas', args=[self.owner.pk, self.question.pk]
            ),
            {'Respuesta': 'Mensaje no autorizado'},
        )
        self.assertRedirects(
            respuesta, reverse('inicio', args=[self.other.pk])
        )
        self.assertFalse(Respuesta.objects.exists())

    def test_crear_ticket_solo_necesita_campos_editables(self):
        self.client.force_login(self.owner)
        respuesta = self.client.post(
            reverse('inicio', args=[self.owner.pk]),
            {
                'Titulo': 'Ticket sin campos ocultos',
                'Pregunta': 'Descripción del problema',
                'categoria': 'Otros',
            },
        )
        self.assertRedirects(
            respuesta, reverse('inicio', args=[self.owner.pk])
        )
        ticket = Preguntas.objects.get(Titulo='Ticket sin campos ocultos')
        self.assertEqual(ticket.Usuario_id, self.owner.pk)
        self.assertIsNotNone(ticket.Fecha_creacion)

    def test_respuesta_ignora_relaciones_y_fecha_invalidas_del_cliente(self):
        self.client.force_login(self.owner)
        respuesta = self.client.post(
            reverse('respuestas', args=[999999, self.question.pk]),
            {
                'Respuesta': 'Mensaje válido',
                'id_Pregunta': 'ticket-inexistente',
                'Usuario': 'usuario-inexistente',
                'FechaHora': 'fecha-invalida',
            },
        )
        self.assertRedirects(
            respuesta,
            reverse('respuestas', args=[self.owner.pk, self.question.pk]),
        )
        mensaje = Respuesta.objects.get()
        self.assertEqual(mensaje.Usuario_id, self.owner.pk)
        self.assertEqual(mensaje.id_Pregunta_id, self.question.pk)
        self.assertIsNotNone(mensaje.FechaHora)

    def test_panel_propio_no_expone_tickets_ajenos(self):
        self.client.force_login(self.other)
        respuesta = self.client.get(
            reverse('inicio', args=[self.other.pk])
        )
        self.assertEqual(list(respuesta.context['Preguntas']), [])
        for identificador in (self.owner.pk, 999999):
            with self.subTest(identificador=identificador):
                respuesta = self.client.get(
                    reverse('inicio', args=[identificador])
                )
                self.assertRedirects(
                    respuesta, reverse('inicio', args=[self.other.pk])
                )

    def test_registro_publico_ignora_permisos_manipulados(self):
        respuesta = self.client.post(reverse('Register'), {
            'usuario': 'cliente_nuevo',
            'correo': 'cliente_nuevo@example.com',
            'rut': '12.345.678-5',
            'password': 'clave-segura-123',
            'password_2': 'clave-segura-123',
            'admin': 'on',
            'tecnico': 'on',
            'activo': 'False',
            'is_staff': 'on',
            'is_superuser': 'on',
        })
        usuario = Usuario.objects.get(usuario='cliente_nuevo')
        self.assertRedirects(
            respuesta, reverse('catalogo:inicio')
        )
        self.assertFalse(usuario.admin)
        self.assertFalse(usuario.tecnico)
        self.assertTrue(usuario.activo)
        self.assertTrue(usuario.check_password('clave-segura-123'))

    def test_sesion_previa_de_cuenta_desactivada_no_accede_al_soporte(self):
        self.owner.admin = True
        self.owner.tecnico = True
        self.owner.save(update_fields=['admin', 'tecnico'])
        self.client.force_login(self.owner)
        Usuario.objects.filter(pk=self.owner.pk).update(activo=False)
        rutas = [
            reverse('index'),
            reverse('inicio', args=[self.owner.pk]),
            reverse('respuestas', args=[self.owner.pk, self.question.pk]),
            reverse('obtener_mensajes', args=[self.question.pk]),
            reverse('administracion'),
            reverse('listado_preguntas'),
            reverse('escritorio_tecnico'),
            reverse('gestion_usuarios'),
            reverse('analytics_ia'),
            reverse('modificar_pregunta', args=[self.question.pk]),
        ]
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)
                self.assertEqual(respuesta.status_code, 302)
                self.assertTrue(
                    respuesta.url.startswith(reverse('Login') + '?next=')
                )
        operaciones = [
            (reverse('inicio', args=[self.owner.pk]), {
                'Titulo': 'Ticket no autorizado',
                'Pregunta': 'No debe guardarse',
                'categoria': 'Otros',
            }),
            (reverse('respuestas', args=[self.owner.pk, self.question.pk]), {
                'Respuesta': 'No debe guardarse',
            }),
            (reverse('actualizar_estado', args=[self.question.pk]), {
                'estado': 'Cerrada',
            }),
            (reverse('consultar_ia'), {'consulta': 'No debe enviarse'}),
            (reverse('eliminar_usuario', args=[self.other.pk]), {}),
            (reverse('borrar_pregunta', args=[
                self.owner.pk, self.question.pk
            ]), {}),
            (reverse('gestion_usuarios'), {
                'Userid': self.other.pk, 'admin': 'on',
            }),
        ]
        with patch('online.views.responder_con_gemini') as asistente:
            for ruta, datos in operaciones:
                with self.subTest(ruta=ruta):
                    respuesta = self.client.post(ruta, datos)
                    self.assertEqual(respuesta.status_code, 302)
                    self.assertTrue(respuesta.url.startswith(reverse('Login')))
            asistente.assert_not_called()
        self.question.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.question.estado, 'Abierto')
        self.assertEqual(Preguntas.objects.count(), 1)
        self.assertFalse(Respuesta.objects.exists())
        self.assertTrue(self.other.activo)
        self.assertFalse(self.other.admin)
        respuesta = self.client.get(reverse('admin:index'))
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta.url.startswith(reverse('admin:login')))

    def test_login_conserva_destino_interno_y_rechaza_destino_externo(self):
        destino = reverse('respuestas', args=[
            self.owner.pk, self.question.pk
        ])
        for siguiente_url, esperado in (
            (destino, destino),
            ('https://ejemplo.com/robar-sesion', reverse('catalogo:inicio')),
        ):
            with self.subTest(destino=siguiente_url):
                self.client.logout()
                respuesta = self.client.post(
                    reverse('Login'),
                    {
                        'Usuario': self.owner.usuario,
                        'password': 'test-password-123',
                    },
                    QUERY_STRING='next=' + siguiente_url,
                )
                self.assertRedirects(respuesta, esperado)

    def test_inicio_requiere_sesion_y_redireccion_configurada_existe(self):
        respuesta = self.client.get(reverse('index'))
        self.assertRedirects(respuesta, reverse('Login') + '?next=/')
        self.assertEqual(
            resolve(reverse(settings.LOGIN_REDIRECT_URL)).view_name,
            'catalogo:inicio'
        )

    def test_superusuario_conserva_las_tres_casillas(self):
        usuario = Usuario.objects.create_superuser(
            usuario='superusuario',
            correo='superusuario@example.com',
            password='clave-segura-123',
        )
        self.assertTrue(usuario.admin)
        self.assertTrue(usuario.tecnico)
        self.assertTrue(usuario.activo)


class DjangoAdminTests(TestCase):
    def setUp(self):
        self.administrador = Usuario.objects.create_user(
            correo='administrador@example.com',
            usuario='administrador',
            password='clave-segura-123',
            admin=True,
        )
        self.client.force_login(self.administrador)

    def test_modelos_aparecen_en_django_admin(self):
        respuesta = self.client.get(reverse('admin:index'))
        self.assertEqual(respuesta.status_code, 200)
        for modelo in ('usuario', 'preguntas', 'respuesta'):
            with self.subTest(modelo=modelo):
                ruta = reverse(f'admin:online_{modelo}_changelist')
                self.assertContains(respuesta, ruta)
                self.assertEqual(self.client.get(ruta).status_code, 200)

    def test_crear_usuario_desde_admin_guarda_hash(self):
        respuesta = self.client.post(reverse('admin:online_usuario_add'), {
            'usuario': 'nuevo_admin',
            'correo': 'nuevo_admin@example.com',
            'password': 'clave-nueva-123',
            'password_2': 'clave-nueva-123',
            '_save': 'Guardar',
        })
        self.assertEqual(respuesta.status_code, 302)
        nuevo = Usuario.objects.get(usuario='nuevo_admin')
        self.assertTrue(nuevo.check_password('clave-nueva-123'))
        self.assertNotEqual(nuevo.password, 'clave-nueva-123')

    def test_administrador_no_puede_desactivarse_o_eliminarse(self):
        administrador_modelo = admin.site._registry[Usuario]
        solicitud = RequestFactory().get('/admin/online/usuario/')
        solicitud.user = self.administrador
        campos = administrador_modelo.get_readonly_fields(solicitud, self.administrador)
        self.assertIn('activo', campos)
        self.assertIn('admin', campos)
        self.assertFalse(
            administrador_modelo.has_delete_permission(solicitud, self.administrador)
        )

    def crear_historial(self):
        usuario = Usuario.objects.create_user(
            usuario='cliente_historial',
            correo='historial@example.com',
            password='clave-segura-123',
        )
        ticket = Preguntas.objects.create(
            Titulo='Ticket conservado',
            Pregunta='Consulta inicial',
            Fecha_creacion=timezone.now(),
            Usuario=usuario,
        )
        mensaje = Respuesta.objects.create(
            Respuesta='Mensaje conservado',
            id_Pregunta=ticket,
            Usuario=usuario,
            FechaHora=timezone.now(),
        )
        return usuario, ticket, mensaje

    def test_admin_bloquea_borrado_individual_y_masivo_del_historial(self):
        usuario, ticket, mensaje = self.crear_historial()
        solicitud = RequestFactory().get('/admin/')
        solicitud.user = self.administrador
        for objeto in (usuario, ticket, mensaje):
            nombre_modelo = objeto._meta.model_name
            with self.subTest(modelo=nombre_modelo):
                configuracion = admin.site._registry[type(objeto)]
                self.assertFalse(
                    configuracion.has_delete_permission(solicitud, objeto)
                )
                self.assertNotIn(
                    'delete_selected', configuracion.get_actions(solicitud)
                )
                ruta = reverse(
                    f'admin:online_{nombre_modelo}_delete', args=[objeto.pk]
                )
                self.assertEqual(self.client.get(ruta).status_code, 403)
                respuesta = self.client.post(ruta, {'post': 'yes'})
                self.assertEqual(respuesta.status_code, 403)
                self.client.post(
                    reverse(f'admin:online_{nombre_modelo}_changelist'),
                    {
                        'action': 'delete_selected',
                        '_selected_action': [str(objeto.pk)],
                        'post': 'yes',
                        'index': '0',
                    },
                )
        usuario.refresh_from_db()
        ticket.refresh_from_db()
        mensaje.refresh_from_db()
        self.assertTrue(usuario.activo)
        self.assertEqual(ticket.Usuario_id, usuario.pk)
        self.assertEqual(mensaje.id_Pregunta_id, ticket.pk)
        self.assertEqual(mensaje.Usuario_id, usuario.pk)

    def test_admin_conserva_propietario_y_fecha_al_editar_ticket(self):
        usuario, ticket, mensaje = self.crear_historial()
        fecha_original = ticket.Fecha_creacion
        respuesta = self.client.post(
            reverse('admin:online_preguntas_change', args=[ticket.pk]),
            {
                'Titulo': 'Título corregido',
                'Pregunta': 'Descripción corregida',
                'categoria': 'Problemas técnicos',
                'estado': 'En proceso',
                'Usuario': self.administrador.pk,
                'Fecha_creacion_0': '2000-01-01',
                'Fecha_creacion_1': '00:00:00',
                '_save': 'Guardar',
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        ticket.refresh_from_db()
        mensaje.refresh_from_db()
        self.assertEqual(ticket.Titulo, 'Título corregido')
        self.assertEqual(ticket.Usuario_id, usuario.pk)
        self.assertEqual(ticket.Fecha_creacion, fecha_original)
        self.assertEqual(mensaje.id_Pregunta_id, ticket.pk)

    def test_admin_no_reasigna_mensaje_ni_modifica_autor_o_fecha(self):
        usuario, ticket, mensaje = self.crear_historial()
        fecha_original = mensaje.FechaHora
        otro_ticket = Preguntas.objects.create(
            Titulo='Otra consulta',
            Pregunta='Consulta diferente',
            Fecha_creacion=timezone.now(),
            Usuario=self.administrador,
        )
        respuesta = self.client.post(
            reverse('admin:online_respuesta_change', args=[mensaje.pk]),
            {
                'Respuesta': 'Texto corregido',
                'id_Pregunta': otro_ticket.pk,
                'Usuario': self.administrador.pk,
                'FechaHora_0': '2000-01-01',
                'FechaHora_1': '00:00:00',
                '_save': 'Guardar',
            },
        )
        self.assertEqual(respuesta.status_code, 302)
        mensaje.refresh_from_db()
        self.assertEqual(mensaje.Respuesta, 'Texto corregido')
        self.assertEqual(mensaje.id_Pregunta_id, ticket.pk)
        self.assertEqual(mensaje.Usuario_id, usuario.pk)
        self.assertEqual(mensaje.FechaHora, fecha_original)

    def test_admin_puede_crear_ticket_y_mensaje_con_autoria_del_servidor(self):
        usuario, ticket, mensaje = self.crear_historial()
        respuesta = self.client.post(reverse('admin:online_preguntas_add'), {
            'Titulo': 'Ticket desde Django Admin',
            'Pregunta': 'Nueva consulta',
            'categoria': 'Otros',
            'estado': 'Abierto',
            'Usuario': usuario.pk,
            '_save': 'Guardar',
        })
        self.assertEqual(respuesta.status_code, 302)
        nuevo_ticket = Preguntas.objects.get(
            Titulo='Ticket desde Django Admin'
        )
        self.assertEqual(nuevo_ticket.Usuario_id, self.administrador.pk)
        self.assertIsNotNone(nuevo_ticket.Fecha_creacion)
        respuesta = self.client.post(reverse('admin:online_respuesta_add'), {
            'Respuesta': 'Respuesta desde Django Admin',
            'id_Pregunta': ticket.pk,
            'Usuario': usuario.pk,
            '_save': 'Guardar',
        })
        self.assertEqual(respuesta.status_code, 302)
        nueva_respuesta = Respuesta.objects.get(
            Respuesta='Respuesta desde Django Admin'
        )
        self.assertEqual(nueva_respuesta.Usuario_id, self.administrador.pk)
        self.assertEqual(nueva_respuesta.id_Pregunta_id, ticket.pk)
        self.assertIsNotNone(nueva_respuesta.FechaHora)

    def test_admin_gestiona_permisos_y_desactiva_sin_borrar(self):
        usuario, ticket, mensaje = self.crear_historial()
        ruta = reverse('admin:online_usuario_change', args=[usuario.pk])
        datos = {
            'usuario': usuario.usuario,
            'correo': usuario.correo,
            'activo': 'on',
            'admin': 'on',
            'tecnico': 'on',
            '_save': 'Guardar',
        }
        self.assertEqual(self.client.post(ruta, datos).status_code, 302)
        usuario.refresh_from_db()
        self.assertTrue(usuario.admin)
        self.assertTrue(usuario.tecnico)
        self.assertTrue(usuario.activo)
        datos.pop('activo')
        self.assertEqual(self.client.post(ruta, datos).status_code, 302)
        usuario.refresh_from_db()
        ticket.refresh_from_db()
        mensaje.refresh_from_db()
        self.assertFalse(usuario.activo)
        self.assertTrue(usuario.admin)
        self.assertTrue(usuario.tecnico)
        self.assertEqual(ticket.Usuario_id, usuario.pk)
        self.assertEqual(mensaje.Usuario_id, usuario.pk)


class PruebasIntegracionEntel(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cliente = Usuario.objects.create_user(
            'cliente-entel@example.com', 'cliente-entel', 'clave-segura-123'
        )
        cls.otro_cliente = Usuario.objects.create_user(
            'otro-entel@example.com', 'otro-entel', 'clave-segura-123'
        )
        cls.tecnico = Usuario.objects.create_user(
            'tecnico-entel@example.com', 'tecnico-entel', 'clave-segura-123',
            tecnico=True,
        )
        cls.administrador = Usuario.objects.create_user(
            'admin-entel@example.com', 'admin-entel', 'clave-segura-123',
            admin=True,
        )
        cls.ambos_permisos = Usuario.objects.create_user(
            'ambos-entel@example.com', 'ambos-entel', 'clave-segura-123',
            admin=True, tecnico=True,
        )
        cls.contenido = Contenido.objects.create(
            titulo='Película de integración', tipo='pelicula',
            genero='comedia',
            anio=2003, sinopsis='Información pública del catálogo académico.',
        )

    def setUp(self):
        self.client.force_login(self.cliente)
        self.ruta_ayuda = reverse('ayuda_contenido', args=[self.contenido.pk])
        self.datos_ticket = {
            'Titulo': 'Consulta sobre la película',
            'Pregunta': 'Necesito orientación de un ejecutivo.',
            'categoria': 'Películas y series',
        }

    def test_ticket_desde_ficha_vincula_contenido_y_autoria_del_servidor(self):
        datos = dict(self.datos_ticket, Usuario=self.otro_cliente.pk,
                     Fecha_creacion='2000-01-01', estado='Cerrada')
        respuesta = self.client.post(self.ruta_ayuda, datos)
        ticket = Preguntas.objects.get()
        self.assertRedirects(respuesta, reverse('respuestas', args=[
            self.cliente.pk, ticket.pk
        ]))
        self.assertEqual(ticket.contenido, self.contenido)
        self.assertEqual(ticket.Usuario, self.cliente)
        self.assertEqual(ticket.estado, 'Abierto')
        self.assertEqual(ticket.Fecha_creacion.date(), timezone.now().date())

    def test_ticket_general_conserva_relacion_vacia(self):
        self.client.post(reverse('centro_ayuda'), self.datos_ticket)
        self.assertIsNone(Preguntas.objects.get().contenido_id)

    def test_ruta_anterior_sigue_creando_tickets_generales(self):
        self.client.post(reverse('inicio', args=[self.cliente.pk]),
                         self.datos_ticket)
        self.assertIsNone(Preguntas.objects.get().contenido_id)

    def test_rechaza_referencias_manipuladas_en_formularios(self):
        for ruta in (
            self.ruta_ayuda, reverse('centro_ayuda'),
            reverse('inicio', args=[self.cliente.pk]),
        ):
            for campo in ('contenido', 'contenido_id'):
                with self.subTest(ruta=ruta, campo=campo):
                    respuesta = self.client.post(
                        ruta, dict(self.datos_ticket, **{campo: uuid.uuid4()})
                    )
                    self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(Preguntas.objects.exists())

    def test_identificadores_invalidos_o_inexistentes_no_crean_ticket(self):
        for identificador in ('no-es-uuid', str(uuid.uuid4())):
            respuesta = self.client.post(
                '/AyudaContenido/' + identificador + '/', self.datos_ticket
            )
            self.assertEqual(respuesta.status_code, 404)
        self.assertFalse(Preguntas.objects.exists())

    def test_inactivo_no_admite_ayuda_nueva(self):
        self.contenido.activo = False
        self.contenido.save(update_fields=['activo'])
        self.assertEqual(self.client.get(self.ruta_ayuda).status_code, 404)
        self.assertEqual(self.client.post(
            self.ruta_ayuda, self.datos_ticket
        ).status_code, 404)
        self.assertFalse(Preguntas.objects.exists())

    def test_centro_ayuda_ofrece_vias_independientes_y_contexto(self):
        respuesta = self.client.get(self.ruta_ayuda)
        self.assertContains(respuesta, 'Crear ticket')
        self.assertContains(respuesta, 'Abrir asistente virtual')
        self.assertContains(respuesta, self.contenido.titulo)
        self.assertContains(respuesta, reverse('consultar_ia_contenido', args=[
            self.contenido.pk
        ]))

    def test_ayuda_exige_sesion(self):
        self.client.logout()
        for ruta in (self.ruta_ayuda, reverse('centro_ayuda')):
            self.assertEqual(self.client.get(ruta).status_code, 302)
            self.assertEqual(self.client.post(
                ruta, self.datos_ticket
            ).status_code, 302)

    def test_creacion_de_tickets_exige_csrf(self):
        navegador = Client(enforce_csrf_checks=True)
        navegador.force_login(self.cliente)
        self.assertEqual(navegador.post(
            self.ruta_ayuda, self.datos_ticket
        ).status_code, 403)
        self.assertFalse(Preguntas.objects.exists())

    def test_todas_las_categorias_nuevas_se_pueden_utilizar(self):
        esperadas = [
            'Cuenta y acceso', 'Películas y series',
            'Problemas técnicos', 'Otros',
        ]
        self.assertEqual(list(dict(Preguntas.CATEGORIAS)), esperadas)
        for categoria in esperadas:
            datos = dict(self.datos_ticket, categoria=categoria)
            formulario = PreguntasForm(datos)
            self.assertTrue(formulario.is_valid(), formulario.errors)
            self.client.post(reverse('centro_ayuda'), datos)
        self.assertEqual(Preguntas.objects.count(), 4)

    def test_tickets_nuevos_rechazan_categorias_antiguas_y_desconocidas(self):
        categorias = ('Hardware', 'Software', 'Redes', 'Otro', 'Inventada')
        for categoria in categorias:
            with self.subTest(categoria=categoria):
                respuesta = self.client.post(reverse('centro_ayuda'), dict(
                    self.datos_ticket, categoria=categoria
                ))
                self.assertIn(
                    'categoria', respuesta.context['formulario'].errors
                )
        self.assertFalse(Preguntas.objects.exists())

    def test_categoria_historica_se_conserva_al_consultar_y_editar(self):
        ticket = Preguntas.objects.create(
            Titulo='Consulta anterior', Pregunta='Texto anterior',
            Usuario=self.cliente, Fecha_creacion=timezone.now(),
            categoria='Hardware',
        )
        self.assertIsNone(ticket.contenido_id)
        self.client.force_login(self.tecnico)
        respuesta = self.client.get(reverse('listado_preguntas'), {
            'categoria': 'Hardware',
        })
        self.assertIn(ticket, respuesta.context['Preguntas'])
        self.assertContains(respuesta, 'Hardware (histórica)')
        self.client.force_login(self.administrador)
        self.assertRedirects(self.client.post(reverse(
            'modificar_pregunta', args=[ticket.pk]
        ), {
            'Titulo': 'Consulta antigua corregida',
            'Pregunta': 'Texto conservado', 'categoria': 'Hardware',
        }), reverse('administracion'))
        ticket.refresh_from_db()
        self.assertEqual(ticket.categoria, 'Hardware')
        self.assertIsNone(ticket.contenido_id)

    def test_estados_se_conservan_exactamente(self):
        self.assertEqual(list(dict(Preguntas.ESTADOS)), [
            'Abierto', 'En proceso', 'Cerrada'
        ])

    def test_flujo_cliente_ejecutivo_respuesta_historial_y_privacidad(self):
        self.client.post(self.ruta_ayuda, self.datos_ticket)
        ticket = Preguntas.objects.get()
        ruta = reverse('respuestas', args=[self.cliente.pk, ticket.pk])
        ruta_ficha = reverse('catalogo:ficha_desde_ticket', args=[ticket.pk])
        self.client.force_login(self.tecnico)
        respuesta = self.client.get(reverse('escritorio_tecnico'))
        self.assertIn(ticket, respuesta.context['Preguntas'])
        self.assertContains(respuesta, ruta_ficha)
        self.assertContains(self.client.get(ruta), ruta_ficha)
        self.assertContains(self.client.get(ruta_ficha), self.contenido.titulo)
        self.client.post(ruta, {'Respuesta': 'Orientación del ejecutivo.'})
        self.client.force_login(self.cliente)
        mensajes = self.client.get(reverse(
            'obtener_mensajes', args=[ticket.pk]
        ))
        self.assertEqual(len(mensajes.json()['mensajes']), 2)
        self.assertEqual(mensajes.json()['mensajes'][1]['mensaje'],
                         'Orientación del ejecutivo.')
        self.client.post(ruta, {'Respuesta': 'Gracias por la ayuda.'})
        self.assertEqual(Respuesta.objects.count(), 2)
        self.client.force_login(self.otro_cliente)
        self.assertEqual(self.client.get(ruta_ficha).status_code, 403)
        self.assertEqual(self.client.get(reverse(
            'obtener_mensajes', args=[ticket.pk]
        )).status_code, 403)
        self.client.post(ruta, {'Respuesta': 'Mensaje ajeno.'})
        self.assertEqual(Respuesta.objects.count(), 2)

    def test_login_respeta_destinos_segun_casillas_independientes(self):
        for usuario, nombre_ruta in (
            (self.cliente, 'catalogo:inicio'),
            (self.tecnico, 'escritorio_tecnico'),
            (self.administrador, 'administracion'),
            (self.ambos_permisos, 'administracion'),
        ):
            with self.subTest(usuario=usuario.usuario):
                self.client.logout()
                respuesta = self.client.post(reverse('Login'), {
                    'Usuario': usuario.usuario, 'password': 'clave-segura-123',
                })
                self.assertRedirects(respuesta, reverse(nombre_ruta))

    def test_inicio_raiz_respeta_casillas(self):
        for usuario, destino in (
            (self.cliente, 'catalogo:inicio'),
            (self.tecnico, 'escritorio_tecnico'),
            (self.administrador, 'administracion'),
            (self.ambos_permisos, 'administracion'),
        ):
            self.client.force_login(usuario)
            self.assertRedirects(self.client.get(reverse('index')),
                                 reverse(destino))

    def test_registro_lleva_al_catalogo_sin_privilegios(self):
        self.client.logout()
        respuesta = self.client.post(reverse('Register'), {
            'usuario': 'registro-entel', 'correo': 'registro@example.com',
            'rut': '12.345.678-5', 'password': 'clave-segura-123',
            'password_2': 'clave-segura-123',
            'admin': 'on', 'tecnico': 'on',
        })
        self.assertRedirects(respuesta, reverse('catalogo:inicio'))
        usuario = Usuario.objects.get(usuario='registro-entel')
        self.assertTrue(usuario.activo)
        self.assertFalse(usuario.admin)
        self.assertFalse(usuario.tecnico)

    def test_navegacion_integrada_apunta_a_rutas_existentes(self):
        respuesta = self.client.get(reverse('catalogo:inicio'))
        for destino in ('catalogo:inicio', 'catalogo:peliculas',
                        'catalogo:series', 'catalogo:listado', 'centro_ayuda'):
            ruta = reverse(destino)
            self.assertContains(respuesta, ruta)
            self.assertEqual(self.client.get(ruta).status_code, 200)
        self.assertContains(
            respuesta, reverse('inicio', args=[self.cliente.pk])
        )
        self.assertContains(respuesta, 'id="abrir-asistente"')
        self.assertNotContains(respuesta, '>Gemini</a>')

    @patch('online.views.responder_con_gemini', side_effect=TimeoutError())
    def test_fallo_gemini_no_impide_ticket_humano(self, asistente):
        respuesta = self.client.post(reverse('consultar_ia'), {
            'consulta': 'Necesito ayuda.',
        })
        self.assertEqual(respuesta.status_code, 503)
        self.client.post(self.ruta_ayuda, self.datos_ticket)
        self.assertEqual(Preguntas.objects.count(), 1)
        asistente.assert_called_once()

    @patch('online.views.responder_con_gemini')
    def test_consulta_contextual_valida_contenido_en_servidor(self, asistente):
        asistente.return_value = 'Respuesta simulada.'
        ruta = reverse('consultar_ia_contenido', args=[self.contenido.pk])
        respuesta = self.client.post(ruta, {'consulta': '¿De qué trata?'})
        self.assertEqual(respuesta.status_code, 200)
        asistente.assert_called_once_with('¿De qué trata?',
                                          contenido=self.contenido)
        self.assertFalse(Preguntas.objects.exists())

    @patch('online.views.responder_con_gemini')
    def test_gemini_rechaza_contextos_manipulados_inactivos_o_inexistentes(
        self, asistente
    ):
        respuesta = self.client.post(reverse('consultar_ia'), {
            'consulta': 'Hola', 'contenido_id': self.contenido.pk,
        })
        self.assertEqual(respuesta.status_code, 403)
        for identificador in (uuid.uuid4(), 'incorrecto'):
            ruta = '/ConsultarIA/' + str(identificador) + '/'
            self.assertEqual(self.client.post(ruta, {
                'consulta': 'Hola',
            }).status_code, 404)
        self.contenido.activo = False
        self.contenido.save(update_fields=['activo'])
        ruta = reverse('consultar_ia_contenido', args=[self.contenido.pk])
        self.assertEqual(self.client.post(ruta, {
            'consulta': 'Hola',
        }).status_code, 404)
        asistente.assert_not_called()

    @override_settings(GEMINI_API_KEY='clave-simulada')
    @patch('online.gemini_chat.urlopen')
    def test_gemini_recibe_catalogo_sin_historial_ni_perfiles(self, abrir):
        self.client.post(self.ruta_ayuda, self.datos_ticket)
        self.cliente.rut = '12345678-5'
        self.cliente.save(update_fields=['rut'])
        self.contenido.activo = False
        self.contenido.titulo = 'Obra inactiva secreta'
        self.contenido.save(update_fields=['activo', 'titulo'])
        activo = Contenido.objects.create(
            titulo='Serie pública', tipo='serie', genero='drama', anio=2022,
            sinopsis='Una sinopsis pública.',
        )
        conexion = MagicMock()
        conexion.read.return_value = json.dumps({
            'candidates': [{'content': {
                'parts': [{'text': 'Consulta la ficha.'}]
            }}]
        }).encode('utf-8')
        abrir.return_value.__enter__.return_value = conexion
        respuesta = self.client.post(reverse('consultar_ia_contenido', args=[
            activo.pk
        ]), {'consulta': '¿Qué hay en el catálogo?'})
        self.assertEqual(respuesta.json()['respuesta'], 'Consulta la ficha.')
        solicitud = abrir.call_args.args[0]
        enviado = json.loads(solicitud.data)
        instrucciones = enviado['systemInstruction']['parts'][0]['text']
        self.assertIn('Serie pública', instrucciones)
        self.assertIn(str(activo.pk), instrucciones)
        self.assertIn('No afirmes disponibilidad comercial', instrucciones)
        for privado in (
            self.datos_ticket['Pregunta'], self.cliente.correo,
            self.cliente.rut, self.cliente.password, 'Obra inactiva secreta',
        ):
            self.assertNotIn(privado, instrucciones)
        self.assertEqual(abrir.call_args.kwargs['timeout'], 20)
        self.assertIn('gemini-3.5-flash-lite', solicitud.full_url)
        self.assertNotIn('clave-simulada', solicitud.full_url)

    @override_settings(GEMINI_API_KEY='clave-simulada')
    @patch('online.gemini_chat.urlopen')
    def test_gemini_acota_datos_y_conserva_contexto_seleccionado(self, abrir):
        Contenido.objects.bulk_create([
            Contenido(
                titulo=f'Aventura {numero:02}', tipo='pelicula',
                genero='aventura', anio=2000, sinopsis='Texto.' * 100,
            ) for numero in range(31)
        ])
        self.contenido.titulo = 'ZZZ selección contextual'
        self.contenido.save(update_fields=['titulo'])
        conexion = MagicMock()
        conexion.read.return_value = json.dumps({
            'candidates': [{'content': {'parts': [{'text': 'Orientación.'}]}}]
        }).encode('utf-8')
        abrir.return_value.__enter__.return_value = conexion
        respuesta = self.client.post(reverse(
            'consultar_ia_contenido', args=[self.contenido.pk]
        ), {'consulta': 'Consulta de demostración.'})
        self.assertEqual(respuesta.status_code, 200)
        solicitud = abrir.call_args.args[0]
        instrucciones = json.loads(solicitud.data)[
            'systemInstruction'
        ]['parts'][0]['text']
        contexto = json.loads(instrucciones.split('\n', 1)[1])
        self.assertEqual(contexto['contenido_seleccionado'],
                         str(self.contenido.pk))
        self.assertEqual(len(contexto['contenidos']), 31)
        self.assertIn(str(self.contenido.pk), [
            elemento['id'] for elemento in contexto['contenidos']
        ])
        self.assertTrue(all(len(elemento['sinopsis']) <= 200
                            for elemento in contexto['contenidos']))

    @patch('online.gemini_chat.urlopen')
    def test_edicion_administrativa_no_requiere_openai_ni_gemini(self, abrir):
        self.client.post(self.ruta_ayuda, self.datos_ticket)
        ticket = Preguntas.objects.get()
        self.client.force_login(self.administrador)
        ruta = reverse('modificar_pregunta', args=[ticket.pk])
        self.assertEqual(self.client.get(ruta).status_code, 200)
        self.assertRedirects(self.client.post(ruta, dict(
            self.datos_ticket, Titulo='Título corregido', contenido='otra-obra'
        )), reverse('administracion'))
        ticket.refresh_from_db()
        self.assertEqual(ticket.Titulo, 'Título corregido')
        self.assertEqual(ticket.contenido, self.contenido)
        abrir.assert_not_called()


class AnalizadorPresentacion(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elementos = []

    def handle_starttag(self, tag, attrs):
        self.elementos.append((tag, dict(attrs)))


class PruebasPresentacionFinal(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cliente = Usuario.objects.create_user(
            'presentacion@example.com', 'presentacion', 'clave-segura-123'
        )
        cls.tecnico = Usuario.objects.create_user(
            'atencion-ui@example.com', 'atencion-ui', 'clave-segura-123',
            tecnico=True,
        )
        cls.administrador = Usuario.objects.create_user(
            'gestion-ui@example.com', 'gestion-ui', 'clave-segura-123',
            admin=True,
        )
        cls.contenido = Contenido.objects.create(
            titulo='Contenido contextual', tipo='pelicula', genero='drama',
            anio=2020, sinopsis='Sinopsis de presentación.',
        )
        cls.ticket = Preguntas.objects.create(
            Titulo='Ticket de presentación', Pregunta='Consulta del cliente.',
            Usuario=cls.cliente, Fecha_creacion=timezone.now(),
            contenido=cls.contenido,
        )

    def setUp(self):
        self.client.force_login(self.cliente)

    def analizar(self, respuesta):
        analizador = AnalizadorPresentacion()
        analizador.feed(respuesta.content.decode('utf-8'))
        return analizador.elementos

    def elemento_por_id(self, respuesta, identificador):
        return next(
            atributos for _, atributos in self.analizar(respuesta)
            if atributos.get('id') == identificador
        )

    def rutas_cliente(self):
        return [
            reverse('catalogo:' + nombre)
            for nombre in ('inicio', 'peliculas', 'series', 'listado')
        ] + [
            reverse('catalogo:detalle', args=[self.contenido.pk]),
            reverse('centro_ayuda'),
            reverse('ayuda_contenido', args=[self.contenido.pk]),
            reverse('inicio', args=[self.cliente.pk]),
            reverse('respuestas', args=[self.cliente.pk, self.ticket.pk]),
        ]

    def test_burbuja_unica_en_todas_las_pantallas_del_cliente(self):
        for ruta in self.rutas_cliente():
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)
                self.assertContains(respuesta, 'id="abrir-asistente"', count=1)
                self.assertContains(
                    respuesta, 'id="formulario-asistente"', count=1
                )

    def test_ventana_comienza_cerrada_con_estado_accesible(self):
        respuesta = self.client.get(reverse('catalogo:inicio'))
        ventana = self.elemento_por_id(respuesta, 'ventana-asistente')
        boton = self.elemento_por_id(respuesta, 'abrir-asistente')
        self.assertIn('hidden', ventana)
        self.assertEqual(ventana['role'], 'dialog')
        self.assertEqual(boton['aria-expanded'], 'false')
        self.assertEqual(boton['aria-controls'], 'ventana-asistente')
        self.assertContains(respuesta, '¿En qué puedo ayudarte?')

    def test_pantallas_clientes_no_muestran_proveedor_ni_tema_anterior(self):
        for ruta in self.rutas_cliente():
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)
                for texto in ('Gemini', 'CallCenterGamer', 'videojuegos'):
                    self.assertNotContains(respuesta, texto)

    def test_visitantes_no_reciben_burbuja(self):
        self.client.logout()
        for nombre in ('Login', 'Register'):
            respuesta = self.client.get(reverse(nombre))
            self.assertNotContains(respuesta, 'id="abrir-asistente"')
            self.assertNotContains(respuesta, 'CallCenterGamer')

    def test_personal_no_recibe_el_asistente_de_cliente(self):
        for usuario in (self.tecnico, self.administrador):
            self.client.force_login(usuario)
            respuesta = self.client.get(reverse('catalogo:inicio'))
            self.assertNotContains(respuesta, 'id="abrir-asistente"')

    def test_ficha_y_ayuda_conservan_endpoint_contextual(self):
        esperado = reverse('consultar_ia_contenido', args=[self.contenido.pk])
        for nombre in ('catalogo:detalle', 'ayuda_contenido'):
            respuesta = self.client.get(reverse(nombre, args=[
                self.contenido.pk
            ]))
            formulario = self.elemento_por_id(
                respuesta, 'formulario-asistente'
            )
            self.assertEqual(formulario['action'], esperado)
            self.assertEqual(formulario['method'], 'post')
            self.assertContains(respuesta, 'Consulta sobre')

    def test_paginas_generales_usan_endpoint_general(self):
        for ruta in (reverse('catalogo:inicio'), reverse('centro_ayuda'),
                     reverse('inicio', args=[self.cliente.pk])):
            respuesta = self.client.get(ruta)
            formulario = self.elemento_por_id(
                respuesta, 'formulario-asistente'
            )
            self.assertEqual(formulario['action'], reverse('consultar_ia'))

    def test_ficha_historica_no_envia_contexto_inactivo(self):
        self.contenido.activo = False
        self.contenido.save(update_fields=['activo'])
        respuesta = self.client.get(reverse(
            'catalogo:ficha_desde_ticket', args=[self.ticket.pk]
        ))
        formulario = self.elemento_por_id(respuesta, 'formulario-asistente')
        self.assertEqual(formulario['action'], reverse('consultar_ia'))
        self.assertNotContains(respuesta, reverse(
            'consultar_ia_contenido', args=[self.contenido.pk]
        ))

    def test_centro_ayuda_no_duplica_el_formulario_de_conversacion(self):
        respuesta = self.client.get(reverse('centro_ayuda'))
        self.assertContains(respuesta, 'data-abrir-asistente')
        self.assertNotContains(respuesta, 'formulario-gemini')
        entradas = [
            atributos for _, atributos in self.analizar(respuesta)
            if atributos.get('name') == 'consulta'
        ]
        self.assertEqual(len(entradas), 1)

    def test_burbuja_ofrece_atencion_humana_con_contexto(self):
        respuesta = self.client.get(reverse(
            'catalogo:detalle', args=[self.contenido.pk]
        ))
        self.assertContains(respuesta, reverse(
            'ayuda_contenido', args=[self.contenido.pk]
        ) + '#crear-ticket')

    def test_formulario_tiene_limite_y_controles_de_cierre_y_envio(self):
        respuesta = self.client.get(reverse('catalogo:inicio'))
        entrada = self.elemento_por_id(respuesta, 'consulta-asistente')
        self.assertEqual(entrada['maxlength'], '1000')
        self.assertIn('required', entrada)
        self.assertEqual(
            self.elemento_por_id(respuesta, 'cerrar-asistente')['type'],
            'button',
        )
        self.assertContains(respuesta, 'No compartas contraseñas')

    def test_recursos_de_presentacion_son_locales(self):
        for ruta in self.rutas_cliente():
            respuesta = self.client.get(ruta)
            for etiqueta, atributos in self.analizar(respuesta):
                if etiqueta == 'script' or (
                    etiqueta == 'link' and atributos.get('rel') == 'stylesheet'
                ):
                    direccion = atributos.get('src') or atributos.get('href')
                    self.assertTrue(
                        direccion.startswith('/static/'), direccion
                    )

    def test_asistente_conserva_proteccion_csrf(self):
        navegador = Client(enforce_csrf_checks=True)
        navegador.force_login(self.cliente)
        navegador.get(reverse('catalogo:inicio'))
        respuesta = navegador.post(reverse('consultar_ia'), {
            'consulta': 'Una consulta sin token.',
        })
        self.assertEqual(respuesta.status_code, 403)

    @patch('online.views.responder_con_gemini')
    def test_formulario_usa_token_y_backend_existente(self, asistente):
        asistente.return_value = 'Respuesta simulada del asistente.'
        navegador = Client(enforce_csrf_checks=True)
        navegador.force_login(self.cliente)
        navegador.get(reverse('catalogo:inicio'))
        token = navegador.cookies['csrftoken'].value
        respuesta = navegador.post(reverse('consultar_ia'), {
            'consulta': '¿Cómo busco una película?',
            'csrfmiddlewaretoken': token,
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()['respuesta'],
                         'Respuesta simulada del asistente.')
        asistente.assert_called_once_with(
            '¿Cómo busco una película?', contenido=None
        )

    def test_sesion_desactivada_no_recibe_presentacion_protegida(self):
        Usuario.objects.filter(pk=self.cliente.pk).update(activo=False)
        respuesta = self.client.get(reverse('catalogo:inicio'))
        self.assertEqual(respuesta.status_code, 302)
        self.assertNotContains(respuesta, 'id="abrir-asistente"',
                               status_code=302)

    def test_paneles_conservan_navegacion_y_tema_entel(self):
        self.client.force_login(self.administrador)
        for nombre in ('administracion', 'gestion_usuarios', 'analytics_ia',
                       'escritorio_tecnico', 'catalogo:gestion'):
            respuesta = self.client.get(reverse(nombre))
            self.assertContains(respuesta, 'Entel TV')
            self.assertNotContains(respuesta, 'CallCenterGamer')
            self.assertNotContains(respuesta, 'https://cdn.')


class GeminiChatTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            usuario='jugador',
            correo='jugador@example.com',
            password='clave-segura-123',
        )
        self.url = reverse('consultar_ia')

    def test_requiere_inicio_de_sesion(self):
        respuesta = self.client.post(self.url, {'consulta': 'Hola'})
        self.assertEqual(respuesta.status_code, 302)

    def test_no_acepta_metodo_get(self):
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(self.url).status_code, 405)

    @patch('online.views.responder_con_gemini')
    def test_valida_consulta_vacia_y_larga(self, consultar):
        self.client.force_login(self.usuario)
        for texto in ('', '   ', 'x' * 1001):
            with self.subTest(consulta=texto[:12]):
                respuesta = self.client.post(self.url, {'consulta': texto})
                self.assertEqual(respuesta.status_code, 400)
        consultar.assert_not_called()

    @override_settings(GEMINI_API_KEY='')
    def test_avisa_si_falta_la_clave(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(self.url, {'consulta': 'Mi juego no abre'})
        self.assertEqual(respuesta.status_code, 503)
        self.assertIn('configurado', respuesta.json()['error'])

    @override_settings(GEMINI_API_KEY='clave-de-prueba')
    @patch('online.gemini_chat.urlopen')
    def test_envia_solo_el_mensaje_escrito_y_devuelve_respuesta(self, abrir_url):
        Preguntas.objects.create(
            Titulo='Ticket privado',
            Pregunta='Contenido privado de un ticket guardado',
            Fecha_creacion=timezone.now(),
            Usuario=self.usuario,
        )
        conexion = MagicMock()
        conexion.read.return_value = json.dumps({
            'candidates': [{'content': {'parts': [{'text': 'Revisa tus controladores.'}]}}]
        }).encode('utf-8')
        abrir_url.return_value.__enter__.return_value = conexion

        self.client.force_login(self.usuario)
        respuesta = self.client.post(self.url, {'consulta': 'Mi juego no abre'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()['respuesta'], 'Revisa tus controladores.')

        solicitud = abrir_url.call_args.args[0]
        enviado = json.loads(solicitud.data.decode('utf-8'))
        self.assertEqual(enviado['contents'], [
            {'role': 'user', 'parts': [{'text': 'Mi juego no abre'}]}
        ])
        self.assertNotIn('Contenido privado', json.dumps(enviado))
        self.assertEqual(solicitud.get_method(), 'POST')

    @override_settings(GEMINI_API_KEY='clave-de-prueba')
    @patch('online.gemini_chat.urlopen', side_effect=TimeoutError())
    def test_falla_de_conexion_sin_mostrar_error_interno(self, abrir_url):
        self.client.force_login(self.usuario)
        respuesta = self.client.post(self.url, {'consulta': 'Mi juego no abre'})
        self.assertEqual(respuesta.status_code, 503)
        self.assertNotIn('TimeoutError', str(respuesta.json()))
