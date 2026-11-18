import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.templatetags.static import static
from django.utils import timezone


def validar_anio_estreno(anio):
    if anio > timezone.now().year:
        raise ValidationError('El año no puede ser posterior al año actual.')


class Contenido(models.Model):
    class Tipo(models.TextChoices):
        PELICULA = 'pelicula', 'Película'
        SERIE = 'serie', 'Serie'

    class Genero(models.TextChoices):
        ACCION = 'accion', 'Acción'
        ANIMACION = 'animacion', 'Animación'
        AVENTURA = 'aventura', 'Aventura'
        CIENCIA_FICCION = 'ciencia_ficcion', 'Ciencia ficción'
        COMEDIA = 'comedia', 'Comedia'
        DOCUMENTAL = 'documental', 'Documental'
        DRAMA = 'drama', 'Drama'
        FANTASIA = 'fantasia', 'Fantasía'
        ROMANCE = 'romance', 'Romance'
        SUSPENSO = 'suspenso', 'Suspenso'

    # La precarga usa UUID estables para reconocer incluso títulos editados.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    titulo = models.CharField('Título', max_length=200)
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    genero = models.CharField(
        'Género principal', max_length=20, choices=Genero.choices
    )
    anio = models.PositiveSmallIntegerField(
        'Año de estreno',
        validators=[MinValueValidator(1888), validar_anio_estreno],
    )
    sinopsis = models.TextField(max_length=1200)
    imagen = models.ImageField(
        'Portada', upload_to='catalogo/%Y/%m/', blank=True
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'contenido'
        verbose_name_plural = 'contenidos'
        ordering = ['titulo', 'id']

    def clean(self):
        super().clean()
        self.titulo = self.titulo.strip()
        self.sinopsis = self.sinopsis.strip()
        errores = {}
        if not self.titulo:
            errores['titulo'] = 'Escribe un título.'
        if not self.sinopsis:
            errores['sinopsis'] = 'Escribe una sinopsis.'
        if errores:
            raise ValidationError(errores)

    @property
    def url_imagen(self):
        if self.imagen and self.imagen.storage.exists(self.imagen.name):
            return self.imagen.url
        return static('catalogo/img/portada-no-disponible.svg')

    def __str__(self):
        return f'{self.titulo} ({self.anio})'


class Resena(models.Model):
    contenido = models.ForeignKey(
        Contenido, on_delete=models.PROTECT, related_name='resenas'
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='resenas',
    )
    calificacion = models.PositiveSmallIntegerField(
        'Calificación', validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comentario = models.TextField(max_length=1000)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'reseña'
        verbose_name_plural = 'reseñas'
        ordering = ['-fecha_creacion', '-pk']
        constraints = [
            models.UniqueConstraint(
                fields=['contenido', 'usuario'],
                name='resena_unica_por_usuario',
            ),
            models.CheckConstraint(
                condition=models.Q(calificacion__gte=1, calificacion__lte=5),
                name='resena_calificacion_1_a_5',
            ),
        ]

    def clean(self):
        super().clean()
        self.comentario = self.comentario.strip()
        if not self.comentario:
            raise ValidationError({'comentario': 'Escribe un comentario.'})

    def __str__(self):
        return f'{self.usuario} - {self.contenido}: {self.calificacion}/5'
