from django.urls import path

from . import views

app_name = 'catalogo'

urlpatterns = [
    path('', views.inicio_catalogo, name='inicio'),
    path('contenidos/', views.listar_contenidos, name='listado'),
    path('peliculas/', views.listar_contenidos,
         {'tipo_fijo': 'pelicula'}, name='peliculas'),
    path('series/', views.listar_contenidos,
         {'tipo_fijo': 'serie'}, name='series'),
    path('contenido/<uuid:identificador>/', views.detalle_contenido,
         name='detalle'),
    path('desde-ticket/<int:identificador_ticket>/', views.ficha_desde_ticket,
         name='ficha_desde_ticket'),
    path('contenido/<uuid:identificador>/resena/', views.crear_resena,
         name='crear_resena'),
    path('resena/<int:identificador>/editar/', views.editar_resena,
         name='editar_resena'),
    path('resena/<int:identificador>/eliminar/', views.eliminar_resena,
         name='eliminar_resena'),
    path('gestion/', views.gestionar_contenidos, name='gestion'),
    path('gestion/agregar/', views.agregar_contenido, name='agregar'),
    path('gestion/<uuid:identificador>/editar/', views.editar_contenido,
         name='editar'),
    path('gestion/<uuid:identificador>/desactivar/',
         views.desactivar_contenido, name='desactivar'),
    path('gestion/<uuid:identificador>/reactivar/', views.reactivar_contenido,
         name='reactivar'),
]
