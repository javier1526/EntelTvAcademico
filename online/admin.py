from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils import timezone

from administracion.forms import UserAdminChangeForm, UserAdminCreationForm
from .models import Preguntas, Respuesta, Usuario


admin.site.site_header = 'Entel TV académico'
admin.site.site_title = 'Administración Entel TV'
admin.site.index_title = 'Usuarios, permisos y registros'


@admin.register(Usuario)
class UsuarioAdmin(BaseUserAdmin):
    """Administración del usuario personalizado y sus permisos."""

    form = UserAdminChangeForm
    add_form = UserAdminCreationForm
    list_display = ('usuario', 'correo', 'activo', 'admin', 'tecnico')
    list_filter = ('activo', 'admin', 'tecnico')
    search_fields = ('usuario', 'correo', 'rut', 'nombre', 'apellido')
    ordering = ('usuario',)
    filter_horizontal = ()
    readonly_fields = ('last_login',)

    fieldsets = (
        (None, {'fields': ('usuario', 'correo', 'password')}),
        ('Datos personales', {
            'fields': ('nombre', 'apellido', 'rut', 'fecha_nacimiento'),
        }),
        ('Permisos', {'fields': ('activo', 'admin', 'tecnico')}),
        ('Acceso', {'fields': ('last_login',)}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('usuario', 'correo', 'password', 'password_2'),
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        campos = super().get_readonly_fields(request, obj)
        if obj and obj.pk == request.user.pk:
            return (*campos, 'activo', 'admin')
        return campos

    def has_delete_permission(self, request, obj=None):
        # Las cuentas se desactivan para conservar su historial.
        return False

    def get_actions(self, request):
        acciones = super().get_actions(request)
        acciones.pop('delete_selected', None)
        return acciones


@admin.register(Preguntas)
class PreguntasAdmin(admin.ModelAdmin):
    list_display = (
        'idPregunta', 'Titulo', 'Usuario', 'categoria', 'estado',
        'Fecha_creacion',
    )
    list_filter = ('categoria', 'estado')
    search_fields = ('Titulo', 'Pregunta', 'Usuario__usuario')
    ordering = ('-Fecha_creacion',)
    readonly_fields = ('Usuario', 'Fecha_creacion', 'contenido')

    def get_form(self, request, obj=None, **kwargs):
        formulario = super().get_form(request, obj, **kwargs)
        opciones = list(Preguntas.CATEGORIAS)
        if obj and obj.categoria not in dict(opciones):
            opciones.append((obj.categoria, f'{obj.categoria} (histórica)'))
        formulario.base_fields['categoria'].choices = opciones
        return formulario

    def save_model(self, request, obj, form, change):
        if not change:
            obj.Usuario = request.user
            obj.Fecha_creacion = timezone.now()
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Respuesta)
class RespuestaAdmin(admin.ModelAdmin):
    list_display = ('idRespuesta', 'id_Pregunta', 'Usuario', 'FechaHora')
    search_fields = ('Respuesta', 'Usuario__usuario', 'id_Pregunta__Titulo')
    ordering = ('-FechaHora',)

    def get_readonly_fields(self, request, obj=None):
        campos = ('Usuario', 'FechaHora')
        if obj is not None:
            return (*campos, 'id_Pregunta')
        return campos

    def save_model(self, request, obj, form, change):
        if not change:
            obj.Usuario = request.user
            obj.FechaHora = timezone.now()
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        return False
