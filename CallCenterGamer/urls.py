"""CallCenterGamer URL Configuration"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from administracion.views import (
    AnalyticsIA, BorrarPregunta, EliminarUsuario, GestionUsuarios, IndexAdmin,
    ModificarPregunta, escritorioTecnico,
)
from online.views import (
    Index, Inicio, ListadoPreguntas, LoginView, RegisterView, ViewRespuestas,
    actualizarEstado, centro_ayuda, consultar_ia, logout_view, obtenerMensajes,
)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('Catalogo/', include('catalogo.urls')),
    path('', Index, name='index'),
    path('Administracion/', IndexAdmin, name='administracion'),
    path('Preguntas/', ListadoPreguntas, name='listado_preguntas'),
    path('AnalyticsIA/', AnalyticsIA, name='analytics_ia'),
    path('Login/', LoginView.as_view(), name='Login'),
    path('Register/', RegisterView.as_view(), name='Register'),
    path('Inicio/<int:id>/', Inicio, name='inicio'),
    path('ActualizarEstado/<int:idPregunta>/', actualizarEstado,
         name='actualizar_estado'),
    path('ConsultarIA/', consultar_ia, name='consultar_ia'),
    path('CentroAyuda/', centro_ayuda, name='centro_ayuda'),
    path('AyudaContenido/<uuid:identificador>/', centro_ayuda,
         name='ayuda_contenido'),
    path('ConsultarIA/<uuid:identificador>/', consultar_ia,
         name='consultar_ia_contenido'),
    path('EscritorioTecnico/', escritorioTecnico, name='escritorio_tecnico'),

    # Usar vista personalizada para logout
    path('Logout/', logout_view, name='Logout'),

    path('Respuesta/<int:idUser>/<int:idPregunta>/', ViewRespuestas,
         name='respuestas'),
    path(
        'BorrarPregunta/<int:idUser>/<int:idPregunta>/', BorrarPregunta,
        name='borrar_pregunta',
    ),
    path('GestionUsuarios/', GestionUsuarios, name='gestion_usuarios'),
    path('EliminarUsuario/<int:idUser>/', EliminarUsuario,
         name='eliminar_usuario'),
    path('ModificarPregunta/<int:idPregunta>/', ModificarPregunta,
         name='modificar_pregunta'),
    path('ObtenerMensajes/<int:idPregunta>/', obtenerMensajes,
         name='obtener_mensajes'),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL, document_root=settings.MEDIA_ROOT
    )
