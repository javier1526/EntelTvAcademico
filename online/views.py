from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, FormView

from catalogo.models import Contenido
from online.forms import LoginForm, PreguntasForm, RegisterForm, RespuestaForm
from online.gemini_chat import GeminiSinClaveError, responder_con_gemini
from online.models import Preguntas, Respuesta


@login_required
def Index(request):
    if request.user.admin:
        return redirect('administracion')
    if request.user.tecnico:
        return redirect('escritorio_tecnico')
    return redirect('catalogo:inicio')


@require_POST
def logout_view(request):
    logout(request)
    return redirect('Login')


@login_required
def Inicio(request, id):
    if request.user.pk != id:
        return redirect('inicio', id=request.user.pk)

    preguntas = Preguntas.objects.filter(Usuario=request.user)
    form = PreguntasForm()

    if request.method == 'POST':
        form = PreguntasForm(request.POST)
        _validar_referencia_contenido(request)
        if form.is_valid():
            pregunta = form.save(commit=False)
            pregunta.Usuario = request.user
            pregunta.Fecha_creacion = timezone.now()
            pregunta.save()
            return redirect('inicio', id=request.user.pk)

    return render(request, 'inicio.html', {
        'Preguntas': preguntas,
        'form': form,
        'id': request.user.pk,
    })


def _validar_referencia_contenido(request):
    # El contenido procede de la ruta validada, nunca de campos del cliente.
    if any(campo in request.POST for campo in ('contenido', 'contenido_id')):
        raise PermissionDenied('La referencia al contenido no es válida.')


@login_required
def centro_ayuda(request, identificador=None):
    contenido = None
    if identificador is not None:
        contenido = get_object_or_404(Contenido, pk=identificador, activo=True)
    formulario = PreguntasForm(
        request.POST if request.method == 'POST' else None
    )
    if request.method == 'POST':
        _validar_referencia_contenido(request)
        if formulario.is_valid():
            pregunta = formulario.save(commit=False)
            pregunta.Usuario = request.user
            pregunta.Fecha_creacion = timezone.now()
            pregunta.contenido = contenido
            pregunta.save()
            return redirect(
                'respuestas', idUser=request.user.pk, idPregunta=pregunta.pk
            )
    return render(request, 'centro_ayuda.html', {
        'formulario': formulario, 'contenido': contenido,
    })


@login_required
def ViewRespuestas(request, idUser, idPregunta):
    try:
        pregunta = Preguntas.objects.get(idPregunta=idPregunta)
        if not (
            request.user.id == pregunta.Usuario_id
            or request.user.admin
            or request.user.tecnico
        ):
            return redirect('/Inicio/' + str(request.user.id) + '/')

        respuestas = Respuesta.objects.filter(
            id_Pregunta=pregunta
        ).order_by('FechaHora')
        form = RespuestaForm()

        if request.method == "POST":
            form = RespuestaForm(request.POST)
            if form.is_valid():
                respuesta = form.save(commit=False)
                respuesta.id_Pregunta = pregunta
                respuesta.Usuario = request.user
                respuesta.FechaHora = timezone.now()
                respuesta.save()
                return redirect(
                    'respuestas',
                    idUser=pregunta.Usuario_id,
                    idPregunta=pregunta.pk,
                )

        return render(request, "Respuestas.html", {
            "Pregunta": pregunta,
            "form": form,
            "Respuestas": respuestas
        })
    except Preguntas.DoesNotExist:
        return redirect('/')


class RegisterView(CreateView):
    form_class = RegisterForm
    template_name = 'register.html'
    success_url = '/'

    def form_valid(self, form):
        request = self.request
        usuario = form.save()
        login(request, usuario)
        return redirect('catalogo:inicio')


class LoginView(FormView):
    form_class = LoginForm
    template_name = 'login.html'
    success_url = '/'

    def form_valid(self, form):
        request = self.request
        usuario = form.cleaned_data.get("Usuario")
        password = form.cleaned_data.get("password")
        recordar_sesion = form.cleaned_data.get('remember_me', False)

        usuario_autenticado = authenticate(
            request, username=usuario, password=password
        )

        if usuario_autenticado is not None and usuario_autenticado.activo:
            login(request, usuario_autenticado)
            if not recordar_sesion:
                request.session.set_expiry(0)

            siguiente_url = request.GET.get('next')
            if siguiente_url and url_has_allowed_host_and_scheme(
                siguiente_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(siguiente_url)

            if usuario_autenticado.admin:
                return redirect('administracion')
            if usuario_autenticado.tecnico:
                return redirect('escritorio_tecnico')
            return redirect('catalogo:inicio')

        form.add_error(None, "Usuario o contraseña incorrectos.")
        return super().form_invalid(form)


# Vista de listado de preguntas con busqueda y filtros
@login_required
def ListadoPreguntas(request):
    if not (request.user.admin or request.user.tecnico):
        return redirect('/Inicio/' + str(request.user.id) + '/')
    
    query=request.GET.get('q','')
    categoria=request.GET.get('categoria', '')
    estado=request.GET.get('estado','')

    preguntas=Preguntas.objects.all().order_by('-Fecha_creacion')

    if query:
        preguntas=preguntas.filter(Titulo__icontains=query)
    if categoria:
        preguntas=preguntas.filter(categoria=categoria)
    if estado:
        preguntas=preguntas.filter(estado=estado)

    return render(request, "listado_preguntas.html",{
        "Preguntas":preguntas,
        "query":query,
        "categoria":categoria,
        "estado":estado,
        "categorias": (
            Preguntas.CATEGORIAS + Preguntas.CATEGORIAS_HISTORICAS
        ),
        "estados":Preguntas.ESTADOS,
    })

# Actualizar estado rápido desde el listado
@login_required
def actualizarEstado(request, idPregunta):
    if not (request.user.admin or request.user.tecnico):
        return redirect('/Inicio/' + str(request.user.id) + '/')
    
    if request.method == 'POST':
        pregunta = get_object_or_404(Preguntas, idPregunta=idPregunta)
        nuevo_estado = request.POST.get('estado')
        
        estados_validos = [estado[0] for estado in Preguntas.ESTADOS]
        if nuevo_estado in estados_validos:
            pregunta.estado = nuevo_estado
            pregunta.save()

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'success', 'nuevo_estado': nuevo_estado})
            
    return redirect('/Preguntas/')

# Obtener mensajes para el chat en tiempo real
@login_required
def obtenerMensajes(request, idPregunta):
    try:
        pregunta = Preguntas.objects.get(idPregunta=idPregunta)
        if not (
            request.user.id == pregunta.Usuario_id
            or request.user.admin
            or request.user.tecnico
        ):
            return JsonResponse({'error': 'No tienes permiso para ver este ticket'}, status=403)

        respuestas = Respuesta.objects.filter(id_Pregunta=pregunta).order_by('FechaHora')
        
        lista_mensajes = []
        
        # Agregamos la pregunta inicial (CONVERTIMOS LA HORA A LOCAL)
        lista_mensajes.append({
            'id': f"preg_{pregunta.idPregunta}",
            'usuario': pregunta.Usuario.usuario,
            'es_mio': pregunta.Usuario.id == request.user.id,
            'es_tecnico': pregunta.Usuario.tecnico or pregunta.Usuario.admin,
            'mensaje': pregunta.Pregunta,
            'fecha': timezone.localtime(pregunta.Fecha_creacion).strftime('%d-%m-%Y %H:%M')
        })
        
        # Agregamos las respuestas (CONVERTIMOS LA HORA A LOCAL)
        for r in respuestas:
            lista_mensajes.append({
                'id': f"resp_{r.idRespuesta}",
                'usuario': r.Usuario.usuario,
                'es_mio': r.Usuario.id == request.user.id,
                'es_tecnico': r.Usuario.tecnico or r.Usuario.admin,
                'mensaje': r.Respuesta,
                'fecha': timezone.localtime(r.FechaHora).strftime('%d-%m-%Y %H:%M')
            })
            
        return JsonResponse({'mensajes': lista_mensajes})
    except Preguntas.DoesNotExist:
        return JsonResponse({'error': 'No existe'}, status=404)

# Asistente virtual con Gemini
@login_required
@require_POST
def consultar_ia(request, identificador=None):
    _validar_referencia_contenido(request)
    contenido = None
    if identificador is not None:
        contenido = get_object_or_404(Contenido, pk=identificador, activo=True)
    consulta_original = request.POST.get('consulta', '').strip()
    if not consulta_original:
        return JsonResponse({'error': 'Debes escribir una consulta'}, status=400)
    if len(consulta_original) > 1000:
        return JsonResponse({'error': 'La consulta no puede superar los 1000 caracteres'}, status=400)

    try:
        respuesta = responder_con_gemini(consulta_original, contenido=contenido)
    except GeminiSinClaveError:
        return JsonResponse({
            'error': 'El asistente no está configurado. Consulta con el administrador.'
        }, status=503)
    except ValueError:
        return JsonResponse({
            'error': 'No pude generar una respuesta. Intenta de nuevo o crea un ticket.'
        }, status=502)
    except Exception:
        return JsonResponse({
            'error': 'No pude conectarme con el asistente. Intenta más tarde o crea un ticket.'
        }, status=503)

    return JsonResponse({'respuesta': respuesta})
