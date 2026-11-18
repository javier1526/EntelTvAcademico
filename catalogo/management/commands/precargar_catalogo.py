import json
import uuid
from pathlib import Path

from django.contrib.staticfiles import finders
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalogo.models import Contenido


class Command(BaseCommand):
    help = 'Precarga 20 películas y 10 series sin reemplazar datos existentes.'

    def handle(self, *args, **options):
        ruta_datos = (
            Path(__file__).resolve().parents[2] / 'datos_iniciales.json'
        )
        datos = json.loads(ruta_datos.read_text(encoding='utf-8'))
        if (
            len(datos) != 30
            or sum(dato['tipo'] == 'pelicula' for dato in datos) != 20
            or sum(dato['tipo'] == 'serie' for dato in datos) != 10
            or len({dato['clave'] for dato in datos}) != 30
        ):
            raise CommandError(
                'La selección debe contener 20 películas y 10 series.'
            )

        preparados = []
        for dato in datos:
            identificador = uuid.uuid5(
                uuid.NAMESPACE_URL, 'entel-tv-demo/' + dato['clave']
            )
            campos = {campo: dato[campo] for campo in (
                'titulo', 'tipo', 'genero', 'anio', 'sinopsis',
            )}
            candidato = Contenido(id=identificador, **campos)
            candidato.full_clean(validate_unique=False)
            ruta_portada = finders.find(
                'catalogo/portadas/' + dato['clave'] + '.svg'
            )
            if not ruta_portada:
                raise CommandError('Falta una portada local: ' + dato['clave'])
            preparados.append((candidato, campos, Path(ruta_portada)))

        creados = 0
        conservados = 0
        with transaction.atomic():
            for candidato, campos, ruta_portada in preparados:
                contenido, creado = Contenido.objects.get_or_create(
                    pk=candidato.pk, defaults=campos
                )
                if not creado:
                    conservados += 1
                    continue
                # Solo se copian portadas para los registros recién creados.
                destino = default_storage.save(
                    'catalogo/demo/' + ruta_portada.name,
                    ContentFile(ruta_portada.read_bytes()),
                )
                contenido.imagen = destino
                contenido.save(update_fields=['imagen'])
                creados += 1
        self.stdout.write(self.style.SUCCESS(
            f'Creados: {creados}. Conservados sin cambios: {conservados}.'
        ))
