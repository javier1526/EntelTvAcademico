from django.contrib import admin

from .models import Contenido, Resena


@admin.register(Contenido)
class ContenidoAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'tipo', 'genero', 'anio', 'activo')
    list_filter = ('tipo', 'genero', 'activo')
    search_fields = ('titulo',)

    # El mantenimiento se realiza en el panel propio del catálogo.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Resena)
class ResenaAdmin(admin.ModelAdmin):
    list_display = ('contenido', 'usuario', 'calificacion', 'fecha_creacion')
    search_fields = ('contenido__titulo', 'usuario__usuario')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
