from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from online.models import Preguntas, Respuesta, Usuario


class AdministrationAccessTests(TestCase):
    def setUp(self):
        self.admin = self.create_user('admin', 'admin@example.com', admin=True)
        self.owner = self.create_user('owner', 'owner@example.com')
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

    def test_non_admin_cannot_delete_question_by_spoofing_admin_id(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('borrar_pregunta', args=[self.admin.id, self.question.idPregunta])
        )

        self.assertRedirects(response, f'/Inicio/{self.owner.id}/')
        self.assertTrue(Preguntas.objects.filter(pk=self.question.pk).exists())

    def test_administrador_no_puede_borrar_ticket_ni_conversacion(self):
        mensaje = Respuesta.objects.create(
            Respuesta='Respuesta conservada',
            id_Pregunta=self.question,
            Usuario=self.admin,
            FechaHora=timezone.now(),
        )
        self.client.force_login(self.admin)

        get_response = self.client.get(
            reverse('borrar_pregunta', args=[self.owner.id, self.question.idPregunta])
        )
        self.assertEqual(get_response.status_code, 405)
        self.assertTrue(Preguntas.objects.filter(pk=self.question.pk).exists())

        post_response = self.client.post(
            reverse('borrar_pregunta', args=[self.owner.id, self.question.idPregunta])
        )
        self.assertRedirects(post_response, '/Administracion/')
        self.assertTrue(Preguntas.objects.filter(pk=self.question.pk).exists())
        self.assertTrue(Respuesta.objects.filter(pk=mensaje.pk).exists())

    def test_desactivar_usuario_requiere_post_y_protege_cuenta_propia(self):
        self.client.force_login(self.admin)

        get_response = self.client.get(
            reverse('eliminar_usuario', args=[self.owner.id])
        )
        self.assertEqual(get_response.status_code, 405)
        self.assertTrue(Usuario.objects.filter(pk=self.owner.pk).exists())

        post_response = self.client.post(
            reverse('eliminar_usuario', args=[self.admin.id])
        )
        self.assertRedirects(post_response, '/GestionUsuarios/')
        self.assertTrue(Usuario.objects.filter(pk=self.admin.pk).exists())
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.activo)

    def test_desactivacion_conserva_usuario_permisos_ticket_y_mensaje(self):
        self.owner.tecnico = True
        self.owner.save(update_fields=['tecnico'])
        mensaje = Respuesta.objects.create(
            Respuesta='Mensaje del cliente',
            id_Pregunta=self.question,
            Usuario=self.owner,
            FechaHora=timezone.now(),
        )
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('eliminar_usuario', args=[self.owner.id])
        )

        self.assertRedirects(response, '/GestionUsuarios/')
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.activo)
        self.assertTrue(self.owner.tecnico)
        self.assertFalse(self.owner.admin)
        self.question.refresh_from_db()
        mensaje.refresh_from_db()
        self.assertEqual(self.question.Usuario_id, self.owner.pk)
        self.assertEqual(mensaje.Usuario_id, self.owner.pk)
        self.assertEqual(mensaje.id_Pregunta_id, self.question.pk)

    def test_cliente_y_tecnico_no_pueden_desactivar_usuarios(self):
        tecnico = self.create_user(
            'tecnico', 'tecnico@example.com', tecnico=True
        )
        for usuario in (self.owner, tecnico):
            with self.subTest(usuario=usuario.usuario):
                self.client.force_login(usuario)
                respuesta = self.client.post(
                    reverse('eliminar_usuario', args=[self.admin.pk])
                )
                self.assertRedirects(
                    respuesta, reverse('inicio', args=[usuario.pk])
                )
                self.admin.refresh_from_db()
                self.assertTrue(self.admin.activo)

    def test_cliente_y_tecnico_no_pueden_editar_tickets(self):
        tecnico = self.create_user(
            'atencion', 'atencion@example.com', tecnico=True
        )
        for usuario in (self.owner, tecnico):
            with self.subTest(usuario=usuario.usuario):
                self.client.force_login(usuario)
                respuesta = self.client.post(
                    reverse('modificar_pregunta', args=[self.question.pk]),
                    {'Titulo': 'Cambio no autorizado'},
                )
                self.assertRedirects(
                    respuesta, reverse('inicio', args=[usuario.pk])
                )
                self.question.refresh_from_db()
                self.assertEqual(self.question.Titulo, 'Consulta')

    def test_edicion_ignora_propietario_fecha_y_estado_manipulados(self):
        fecha_original = self.question.Fecha_creacion
        self.client.force_login(self.admin)
        respuesta = self.client.post(
            reverse('modificar_pregunta', args=[self.question.pk]),
            {
                'Titulo': 'Consulta corregida',
                'Pregunta': 'Descripción corregida',
                'categoria': 'Problemas técnicos',
                'Usuario': self.admin.pk,
                'Fecha_creacion': '2000-01-01T00:00:00Z',
                'estado': 'Cerrada',
            },
        )
        self.assertRedirects(respuesta, reverse('administracion'))
        self.question.refresh_from_db()
        self.assertEqual(self.question.Titulo, 'Consulta corregida')
        self.assertEqual(self.question.Pregunta, 'Descripción corregida')
        self.assertEqual(self.question.categoria, 'Problemas técnicos')
        self.assertEqual(self.question.Usuario_id, self.owner.pk)
        self.assertEqual(self.question.Fecha_creacion, fecha_original)
        self.assertEqual(self.question.estado, 'Abierto')

    def test_bandeja_compartida_admite_admin_tecnico_y_ambos_permisos(self):
        tecnico = self.create_user(
            'soporte', 'soporte@example.com', tecnico=True
        )
        administrador_tecnico = self.create_user(
            'ambos', 'ambos@example.com', admin=True, tecnico=True
        )
        for usuario in (self.admin, tecnico, administrador_tecnico):
            with self.subTest(usuario=usuario.usuario):
                self.client.force_login(usuario)
                respuesta = self.client.get(reverse('escritorio_tecnico'))
                self.assertEqual(respuesta.status_code, 200)
                self.assertIn(self.question, respuesta.context['Preguntas'])

    def test_cliente_no_accede_a_paneles_del_personal(self):
        self.client.force_login(self.owner)
        for nombre_ruta in (
            'administracion', 'listado_preguntas', 'escritorio_tecnico',
            'gestion_usuarios', 'analytics_ia',
        ):
            with self.subTest(ruta=nombre_ruta):
                respuesta = self.client.get(reverse(nombre_ruta))
                self.assertRedirects(
                    respuesta, reverse('inicio', args=[self.owner.pk])
                )

    def test_analytics_route_is_available_to_admin(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse('analytics_ia'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_preguntas'], 1)
        self.assertEqual(response.context['preguntas_abiertas'], 1)
        self.assertEqual(response.context['porcentaje_resueltas'], 0)

    def test_technician_cannot_access_analytics(self):
        technician = self.create_user(
            'tech',
            'tech@example.com',
            tecnico=True,
        )
        self.client.force_login(technician)

        response = self.client.get(reverse('analytics_ia'))

        self.assertRedirects(response, f'/Inicio/{technician.id}/')

    def test_admin_cannot_remove_own_permissions(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('gestion_usuarios'), {
            'Userid': self.admin.id,
            'activo': 'on',
            # Se intenta quitar admin.
        })
        self.assertRedirects(response, '/GestionUsuarios/')
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.admin)
        self.assertTrue(self.admin.activo)

    def test_admin_cannot_deactivate_self(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('gestion_usuarios'), {
            'Userid': self.admin.id,
            'admin': 'on',
            # Se intenta desactivar la cuenta.
        })
        self.assertRedirects(response, '/GestionUsuarios/')
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.admin)
        self.assertTrue(self.admin.activo)

    def test_admin_can_deactivate_another_admin_if_one_remains(self):
        otro_admin = self.create_user('admin2', 'admin2@example.com', admin=True)
        self.client.force_login(self.admin)
        response = self.client.post(reverse('gestion_usuarios'), {
            'Userid': otro_admin.id,
            'admin': 'on',
            # El campo activo no se envía.
        })
        self.assertRedirects(response, '/GestionUsuarios/')
        otro_admin.refresh_from_db()
        self.assertFalse(otro_admin.activo)
        self.assertTrue(self.admin.activo)
