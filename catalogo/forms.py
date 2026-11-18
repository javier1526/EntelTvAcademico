from django import forms
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone

from .models import Contenido, Resena


class FormularioResena(forms.ModelForm):
    class Meta:
        model = Resena
        fields = ['calificacion', 'comentario']
        widgets = {
            'calificacion': forms.Select(
                choices=[(numero, f'{numero} de 5') for numero in range(1, 6)],
                attrs={'class': 'form-select'},
            ),
            'comentario': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3, 'maxlength': 1000,
            }),
        }

    def __init__(self, *args, usuario, contenido, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.usuario = usuario
        self.instance.contenido = contenido

    def clean(self):
        datos = super().clean()
        if not self.instance.contenido.activo:
            raise forms.ValidationError('Contenido no disponible.')
        repetidas = Resena.objects.filter(
            usuario=self.instance.usuario, contenido=self.instance.contenido
        ).exclude(pk=self.instance.pk)
        if repetidas.exists():
            raise forms.ValidationError(
                'Ya publicaste una reseña de este título.'
            )
        return datos


class FormularioContenido(forms.ModelForm):
    class Meta:
        model = Contenido
        fields = [
            'titulo', 'tipo', 'genero', 'anio', 'sinopsis', 'imagen', 'activo',
        ]
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'form-control'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'genero': forms.Select(attrs={'class': 'form-select'}),
            'anio': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 1888,
            }),
            'sinopsis': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 5,
            }),
            'imagen': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/png,image/jpeg,image/webp',
            }),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        help_texts = {
            'imagen': 'PNG, JPEG o WebP, hasta 5 MB. La portada es opcional.',
            'activo': 'Los contenidos inactivos se retiran del catálogo.',
        }

    def clean_imagen(self):
        imagen = self.cleaned_data.get('imagen')
        if isinstance(imagen, UploadedFile):
            if imagen.size > 5 * 1024 * 1024:
                raise forms.ValidationError('La imagen no puede superar 5 MB.')
            if imagen.image.format not in {'PNG', 'JPEG', 'WEBP'}:
                raise forms.ValidationError(
                    'Utiliza una imagen PNG, JPEG o WebP.'
                )
        return imagen


class FormularioFiltros(forms.Form):
    ORDENES = [
        ('titulo', 'Título: A a Z'),
        ('-titulo', 'Título: Z a A'),
        ('anio', 'Año: menor a mayor'),
        ('-anio', 'Año: mayor a menor'),
    ]
    q = forms.CharField(
        label='Buscar por título', required=False, max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 'placeholder': '¿Qué quieres descubrir?',
        }),
    )
    tipo = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos los tipos'), *Contenido.Tipo.choices],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    genero = forms.ChoiceField(
        label='Género', required=False,
        choices=[('', 'Todos los géneros'), *Contenido.Genero.choices],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    anio = forms.IntegerField(
        label='Año', required=False, min_value=1888,
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 'placeholder': 'Todos',
        }),
    )
    orden = forms.ChoiceField(
        label='Ordenar', required=False, choices=ORDENES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, tipo_fijo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['anio'].widget.attrs['max'] = timezone.now().year
        if tipo_fijo:
            self.fields['tipo'].initial = tipo_fijo
            self.fields['tipo'].disabled = True

    def clean_anio(self):
        anio = self.cleaned_data.get('anio')
        if anio and anio > timezone.now().year:
            raise forms.ValidationError('Utiliza un año hasta el actual.')
        return anio
