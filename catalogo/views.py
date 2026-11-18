from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from online.models import Preguntas

from .forms import FormularioContenido, FormularioFiltros, FormularioResena
from .models import Contenido, Resena


def _exigir_administrador(request):
    if not (request.user.activo and request.user.admin):
        raise PermissionDenied(
            'Solo un administrador puede gestionar contenidos.'
        )


@login_required
def inicio_catalogo(request):
    contenidos = Contenido.objects.filter(activo=True)
    return render(request, 'catalogo/inicio.html', {
        'destacado': contenidos.order_by('-anio', 'titulo').first(),
        'peliculas': contenidos.filter(tipo=Contenido.Tipo.PELICULA)[:20],
        'series': contenidos.filter(tipo=Contenido.Tipo.SERIE)[:10],
    })


@login_required
def listar_contenidos(request, tipo_fijo=None):
    contenidos = Contenido.objects.filter(activo=True)
    formulario = FormularioFiltros(request.GET, tipo_fijo=tipo_fijo)
    titulos = {'pelicula': 'Películas', 'serie': 'Series'}
    if formulario.is_valid():
        filtros = formulario.cleaned_data
        if filtros['q']:
            contenidos = contenidos.filter(titulo__icontains=filtros['q'])
        for campo in ('tipo', 'genero', 'anio'):
            if filtros[campo]:
                contenidos = contenidos.filter(**{campo: filtros[campo]})
        ordenes = {
            'titulo': [Lower('titulo').asc(), 'anio', 'id'],
            '-titulo': [Lower('titulo').desc(), 'anio', 'id'],
            'anio': ['anio', Lower('titulo').asc(), 'id'],
            '-anio': ['-anio', Lower('titulo').asc(), 'id'],
        }
        contenidos = contenidos.order_by(
            *ordenes[filtros['orden'] or 'titulo']
        )
    else:
        contenidos = contenidos.none()
    return render(request, 'catalogo/listado.html', {
        'contenidos': contenidos,
        'formulario': formulario,
        'titulo_pagina': titulos.get(tipo_fijo, 'Todo el catálogo'),
    })


@login_required
def detalle_contenido(request, identificador):
    contenido = get_object_or_404(
        Contenido, pk=identificador, activo=True
    )
    return _mostrar_ficha(request, contenido)


def _mostrar_ficha(request, contenido, formulario=None, ticket=None):
    resenas = contenido.resenas.select_related('usuario')
    propia_resena = resenas.filter(usuario=request.user).first()
    if contenido.activo and not propia_resena and formulario is None:
        formulario = FormularioResena(
            usuario=request.user, contenido=contenido
        )
    resumen = resenas.aggregate(
        promedio=Avg('calificacion'), cantidad=Count('pk')
    )
    return render(request, 'catalogo/detalle.html', {
        'contenido': contenido, 'resenas': resenas,
        'propia_resena': propia_resena, 'formulario_resena': formulario,
        'promedio': resumen['promedio'],
        'cantidad_resenas': resumen['cantidad'],
        'solo_lectura': not contenido.activo, 'ticket': ticket,
    })


@login_required
def ficha_desde_ticket(request, identificador_ticket):
    ticket = get_object_or_404(
        Preguntas.objects.select_related('contenido'), pk=identificador_ticket,
        contenido__isnull=False,
    )
    if not (
        ticket.Usuario_id == request.user.pk
        or request.user.admin or request.user.tecnico
    ):
        raise PermissionDenied('No tienes acceso a este ticket.')
    return _mostrar_ficha(request, ticket.contenido, ticket=ticket)


@login_required
@require_POST
def crear_resena(request, identificador):
    contenido = get_object_or_404(Contenido, pk=identificador, activo=True)
    formulario = FormularioResena(
        request.POST, usuario=request.user, contenido=contenido
    )
    if formulario.is_valid():
        try:
            # La restricción también protege dos envíos simultáneos.
            with transaction.atomic():
                formulario.save()
        except IntegrityError:
            if not Resena.objects.filter(
                usuario=request.user, contenido=contenido
            ).exists():
                raise
            formulario.add_error(
                None, 'Ya publicaste una reseña de este título.'
            )
        else:
            messages.success(request, 'Reseña publicada.')
            return redirect('catalogo:detalle', identificador=contenido.pk)
    return _mostrar_ficha(request, contenido, formulario=formulario)


@login_required
def editar_resena(request, identificador):
    resena = get_object_or_404(
        Resena.objects.select_related('contenido'), pk=identificador,
        usuario=request.user, contenido__activo=True,
    )
    formulario = FormularioResena(
        request.POST if request.method == 'POST' else None,
        instance=resena, usuario=request.user, contenido=resena.contenido,
    )
    if request.method == 'POST' and formulario.is_valid():
        formulario.save()
        messages.success(request, 'Reseña actualizada.')
        return redirect('catalogo:detalle', identificador=resena.contenido_id)
    return render(request, 'catalogo/resena_formulario.html', {
        'formulario': formulario, 'contenido': resena.contenido,
    })


@login_required
@require_POST
def eliminar_resena(request, identificador):
    resena = get_object_or_404(
        Resena, pk=identificador, usuario=request.user, contenido__activo=True
    )
    identificador_contenido = resena.contenido_id
    resena.delete()
    messages.success(request, 'Reseña eliminada.')
    return redirect('catalogo:detalle', identificador=identificador_contenido)


@login_required
def gestionar_contenidos(request):
    _exigir_administrador(request)
    estado = request.GET.get('estado', '')
    contenidos = Contenido.objects.all()
    if estado in {'activo', 'inactivo'}:
        contenidos = contenidos.filter(activo=estado == 'activo')
    return render(request, 'catalogo/gestion.html', {
        'contenidos': contenidos, 'estado': estado,
    })


@login_required
def agregar_contenido(request):
    _exigir_administrador(request)
    formulario = FormularioContenido()
    if request.method == 'POST':
        formulario = FormularioContenido(request.POST, request.FILES)
        if formulario.is_valid():
            formulario.save()
            messages.success(request, 'Contenido agregado correctamente.')
            return redirect('catalogo:gestion')
    return render(request, 'catalogo/formulario.html', {
        'formulario': formulario, 'titulo_pagina': 'Agregar contenido',
    })


@login_required
def editar_contenido(request, identificador):
    _exigir_administrador(request)
    contenido = get_object_or_404(Contenido, pk=identificador)
    formulario = FormularioContenido(instance=contenido)
    if request.method == 'POST':
        formulario = FormularioContenido(
            request.POST, request.FILES, instance=contenido
        )
        if formulario.is_valid():
            formulario.save()
            messages.success(
                request, 'Contenido actualizado correctamente.'
            )
            return redirect('catalogo:gestion')
    return render(request, 'catalogo/formulario.html', {
        'formulario': formulario, 'titulo_pagina': 'Editar contenido',
    })


@login_required
@require_POST
def desactivar_contenido(request, identificador):
    _exigir_administrador(request)
    contenido = get_object_or_404(Contenido, pk=identificador)
    contenido.activo = False
    contenido.save(update_fields=['activo'])
    messages.success(
        request, 'Contenido desactivado. El registro se conserva.'
    )
    return redirect('catalogo:gestion')


@login_required
@require_POST
def reactivar_contenido(request, identificador):
    _exigir_administrador(request)
    contenido = get_object_or_404(Contenido, pk=identificador)
    contenido.activo = True
    contenido.save(update_fields=['activo'])
    messages.success(request, 'Contenido reactivado correctamente.')
    return redirect('catalogo:gestion')
