from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from online.forms import PreguntasForm
from online.models import Preguntas, Usuario


@login_required
def IndexAdmin(request):
    """
    Panel de administración con estadísticas locales.
    """
    if not (request.user.admin or request.user.tecnico):
        messages.error(
            request, "No tienes permisos para acceder a esta página."
        )
        return redirect('/Inicio/' + str(request.user.id) + '/')

    ListaPreguntas = Preguntas.objects.all().order_by('-Fecha_creacion')
    tendencias_ia = []
    estadisticas_ia = {}
    alertas_ia = []

    try:
        preguntas_recientes = ListaPreguntas.filter(
            Fecha_creacion__gte=timezone.now() - timedelta(days=7)
        )[:10]
        preguntas_semana = ListaPreguntas.filter(
            Fecha_creacion__gte=timezone.now() - timedelta(days=7)
        ).count()

        for pregunta in preguntas_recientes:
            tendencias_ia.append({
                'id': pregunta.idPregunta,
                'titulo': pregunta.Titulo,
                'categoria': pregunta.categoria,
                'usuario': pregunta.Usuario.usuario,
                'fecha': pregunta.Fecha_creacion
            })

        total_preguntas = ListaPreguntas.count()
        preguntas_sin_respuesta = ListaPreguntas.filter(
            respuesta__isnull=True
        ).count()
        if total_preguntas > 0:
            estadisticas_ia = {
                'total_preguntas': total_preguntas,
                'preguntas_sin_respuesta': preguntas_sin_respuesta,
                'porcentaje_resueltas': (
                    (total_preguntas - preguntas_sin_respuesta)
                    / total_preguntas
                ) * 100,
                'tendencia_semanal': preguntas_semana
            }
            if preguntas_sin_respuesta > 5:
                alertas_ia.append({
                    'tipo': 'warning',
                    'mensaje': (
                        f'Hay {preguntas_sin_respuesta} preguntas '
                        'sin respuesta'
                    ),
                    'prioridad': 'alta'
                })
            if preguntas_semana > 20:
                alertas_ia.append({
                    'tipo': 'info',
                    'mensaje': 'Alta actividad esta semana',
                    'prioridad': 'media'
                })
    except Exception as e:
        print(f"Error en análisis de IA: {e}")
        estadisticas_ia = {
            'total_preguntas': ListaPreguntas.count(),
            'preguntas_sin_respuesta': ListaPreguntas.filter(
                respuesta__isnull=True
            ).count(),
            'error_ia': True
        }

    return render(request, "indexAdmin.html", {
        "Preguntas": ListaPreguntas,
        "tendencias_ia": tendencias_ia,
        "estadisticas_ia": estadisticas_ia,
        "alertas_ia": alertas_ia
    })

@login_required
@require_POST
def BorrarPregunta(request, idUser, idPregunta):
    """Conserva la ruta antigua sin permitir el borrado del historial."""
    if not request.user.admin:
        if request.user.tecnico:
            return redirect("/Administracion/")
        return redirect("/Inicio/" + str(request.user.id) + '/')

    messages.error(
        request,
        'Los tickets no se eliminan para conservar su historial. '
        'Puedes actualizar su estado desde el listado de preguntas.',
    )
    return redirect('administracion')


@login_required
def GestionUsuarios(request):
    if not request.user.admin:
        messages.error(request, "No tienes permisos de administrador.")
        return redirect('/Inicio/' + str(request.user.id) + '/')

    Usuarios = Usuario.objects.all()

    # Resumen de actividad calculado con los registros locales.
    analisis_usuarios = []

    try:
        for usuario in Usuarios:
            preguntas_usuario = Preguntas.objects.filter(Usuario=usuario)
            total_preguntas = preguntas_usuario.count()

            # Las categorías ya están guardadas en la base de datos.
            categorias_usuario = []
            for pregunta in preguntas_usuario[:5]:
                categorias_usuario.append(pregunta.categoria)

            # Encontrar categoría más común
            categoria_principal = "sin preguntas"
            if categorias_usuario:
                categoria_principal = max(
                    set(categorias_usuario), key=categorias_usuario.count
                )

            analisis_usuarios.append({
                'usuario_id': usuario.id,
                'total_preguntas': total_preguntas,
                'categoria_principal': categoria_principal,
                'actividad_reciente': (
                    usuario.last_login is not None
                    and usuario.last_login
                    >= timezone.now() - timedelta(days=7)
                )
            })

    except Exception as e:
        print(f"Error en análisis de usuarios con IA: {e}")

    if request.method == "POST":
        user_id = request.POST.get('Userid')

        activo = request.POST.get('activo') == 'on'
        admin = request.POST.get('admin') == 'on'
        tecnico = request.POST.get('tecnico') == 'on'

        try:
            userchange = Usuario.objects.get(id=user_id)

            # Evitar que el administrador pierda acceso a su propia cuenta.
            if userchange.id == request.user.id and (not activo or not admin):
                messages.error(
                    request, 'No puedes desactivar tu cuenta ni quitarte '
                    'el rol de administrador.'
                )
                return redirect('/GestionUsuarios/')

            # Siempre debe quedar al menos un administrador activo.
            if (
                userchange.admin and userchange.activo
                and (not admin or not activo)
            ):
                total_admins = Usuario.objects.filter(
                    admin=True, activo=True
                ).count()
                if total_admins <= 1:
                    messages.error(
                        request, 'No puedes desactivar o cambiar el rol '
                        'del último administrador activo.'
                    )
                    return redirect('/GestionUsuarios/')

            userchange.admin = admin
            userchange.activo = activo
            userchange.tecnico = tecnico
            userchange.save()

            messages.success(
                request,
                f"Usuario {userchange.usuario} actualizado correctamente.",
            )
            return redirect('/GestionUsuarios/')

        except (Usuario.DoesNotExist, ValueError, TypeError):
            messages.error(request, "El usuario no existe.")

    # ... (el return render final) ...
    return render(request, "GestionUsuarios.html", {
        "Usuarios": Usuarios,
        "analisis_usuarios": analisis_usuarios
    })


@login_required
@require_POST
def EliminarUsuario(request, idUser):
    """Desactiva la cuenta sin borrar sus tickets ni sus mensajes."""
    if not request.user.admin:
        messages.error(
            request, "No tienes permisos para realizar esta acción."
        )
        return redirect('inicio', id=request.user.pk)

    try:
        usuario = Usuario.objects.get(pk=idUser)
    except Usuario.DoesNotExist:
        messages.error(request, 'El usuario no existe.')
        return redirect('gestion_usuarios')

    if usuario.pk == request.user.pk:
        messages.error(request, 'No puedes desactivar tu propia cuenta.')
        return redirect('gestion_usuarios')

    if usuario.admin and usuario.activo:
        administradores_activos = Usuario.objects.filter(
            admin=True, activo=True
        ).count()
        if administradores_activos <= 1:
            messages.error(
                request, 'No puedes desactivar al último administrador activo.'
            )
            return redirect('gestion_usuarios')

    usuario.activo = False
    usuario.save(update_fields=['activo'])
    messages.success(
        request,
        f'Usuario {usuario.usuario} desactivado. Su historial se conserva.',
    )
    return redirect('gestion_usuarios')


@login_required
def ModificarPregunta(request, idPregunta):
    if not request.user.admin:
        messages.error(request, "No tienes permisos de administrador.")
        return redirect('inicio', id=request.user.pk)

    try:
        pregunta = Preguntas.objects.get(pk=idPregunta)
    except Preguntas.DoesNotExist:
        messages.error(request, "La pregunta no existe.")
        return redirect('administracion')

    formulario = PreguntasForm(
        request.POST if request.method == 'POST' else None, instance=pregunta
    )
    if request.method == 'POST':
        if formulario.is_valid():
            formulario.save()
            messages.success(request, "Pregunta modificada correctamente.")
            return redirect('administracion')
        messages.error(request, "Error en el formulario. Verifica los datos.")
    return render(request, "ModificarPregunta.html", {
        "form": formulario, "pregunta": pregunta,
    })


# Estadísticas locales de atención.
@login_required
def AnalyticsIA(request):
    """
    Resumen de estadísticas de atención.
    """
    if not request.user.admin:
        messages.error(request, "No tienes permisos de administrador.")
        return redirect('/Inicio/' + str(request.user.id) + '/')

    from django.db.models import Count

    # 1. Estadísticas generales
    total_preguntas = Preguntas.objects.count()
    preguntas_abiertas = Preguntas.objects.filter(estado='Abierto').count()
    preguntas_proceso = Preguntas.objects.filter(estado='En proceso').count()
    preguntas_cerradas = Preguntas.objects.filter(estado='Cerrada').count()

    # Calcular porcentaje de resolución
    porcentaje_resueltas = 0
    if total_preguntas > 0:
        porcentaje_resueltas = round(
            (preguntas_cerradas / total_preguntas) * 100, 1
        )

    # 2. Preguntas por categoría
    categorias_data = (
        Preguntas.objects.values('categoria')
        .annotate(total=Count('categoria')).order_by('-total')
    )

    # 3. Usuarios más activos (que hacen más preguntas)
    usuarios_activos = (
        Usuario.objects.annotate(num_preguntas=Count('preguntas'))
        .filter(num_preguntas__gt=0).order_by('-num_preguntas')[:5]
    )

    return render(request, "analytics_ia.html", {
        "total_preguntas": total_preguntas,
        "preguntas_abiertas": preguntas_abiertas,
        "preguntas_proceso": preguntas_proceso,
        "preguntas_cerradas": preguntas_cerradas,
        "porcentaje_resueltas": porcentaje_resueltas,
        "categorias_data": categorias_data,
        "usuarios_activos": usuarios_activos,
    })

@login_required
def escritorioTecnico(request):
    if not (request.user.admin or request.user.tecnico):
        messages.error(request, 'No tienes permisos para atender tickets.')
        return redirect('inicio', id=request.user.pk)

    # Filtramos solo los tickets que están Abiertos o En Proceso o cerrado
    ListaPreguntas = Preguntas.objects.filter(
        estado__in=['Abierto', 'En proceso']
    ).select_related('contenido', 'Usuario').order_by('-Fecha_creacion')

    return render(request, "escritorio_tecnico.html", {
        "Preguntas": ListaPreguntas
    })
