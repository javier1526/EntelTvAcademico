from django import forms

from online.models import Preguntas, Respuesta, Usuario


class RegisterForm(forms.ModelForm):
    password = forms.CharField(
        label='',
        widget=forms.PasswordInput(attrs={'placeholder': 'Contraseña', 'class': 'form-control'})
    )
    password_2 = forms.CharField(
        label='',
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirmar contraseña', 'class': 'form-control'})
    )

    class Meta:
        model = Usuario
        fields = ['usuario', 'correo', 'rut']
        widgets = {
            'correo': forms.EmailInput(attrs={'placeholder': 'Ingrese su correo', 'class': 'form-control'}),
            'usuario': forms.TextInput(attrs={'placeholder': 'Ingrese su usuario', 'class': 'form-control'}),
            'rut': forms.TextInput(attrs={'placeholder': 'Ingrese su rut', 'class': 'form-control'})
        }

    def clean_correo(self):
        correo = self.cleaned_data.get('correo')
        if Usuario.objects.filter(correo=correo).exists():
            raise forms.ValidationError("El correo ya está en uso")
        return correo

    def clean_rut(self):
        rut = (self.cleaned_data.get('rut') or '').strip().upper()
        if not rut:
            return None

        rut = rut.replace('.', '').replace('-', '')
        if len(rut) < 2:
            raise forms.ValidationError('Ingresa un RUT válido.')
        cuerpo, verificador = rut[:-1], rut[-1]
        if not cuerpo.isdigit() or not (1 <= len(cuerpo) <= 8) or int(cuerpo) == 0:
            raise forms.ValidationError('Ingresa un RUT válido.')

        suma = sum(int(digito) * (2 + i % 6) for i, digito in enumerate(reversed(cuerpo)))
        resto = (11 - suma % 11) % 11
        esperado = 'K' if resto == 10 else str(resto)
        if verificador != esperado:
            raise forms.ValidationError('El dígito verificador del RUT es incorrecto.')

        return f'{int(cuerpo)}-{verificador}'

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_2 = cleaned_data.get("password_2")
        usuario = cleaned_data.get("usuario")

        if usuario and len(usuario) > 20:
            self.add_error("usuario", "El nombre de usuario es demasiado largo!")
        if not usuario:
            self.add_error("usuario", "Debe ingresar un nombre de usuario!")
        if password and len(password) < 8:
            self.add_error("password", "La contraseña debe tener al menos 8 caracteres")
        if password and password_2 and password != password_2:
            self.add_error("password_2", "Las contraseñas no coinciden")
        return cleaned_data

    def save(self, commit=True):
        usuario = super().save(commit=False)
        # El registro público siempre crea una cuenta de cliente activa.
        usuario.admin = False
        usuario.tecnico = False
        usuario.activo = True
        usuario.set_password(self.cleaned_data["password"])
        if commit:
            usuario.save()
        return usuario


class LoginForm(forms.Form):
    Usuario = forms.CharField(
        label='',
        max_length=63,
        widget=forms.TextInput(attrs={'placeholder': 'Ingrese su usuario'})
    )
    password = forms.CharField(
        label='',
        max_length=63,
        widget=forms.PasswordInput(attrs={'placeholder': 'Ingrese su contraseña'})
    )
    remember_me = forms.BooleanField(
        label='Recordar contraseña',
        required=False
    )


class PreguntasForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        opciones = list(Preguntas.CATEGORIAS)
        categoria_actual = self.instance.categoria
        if self.instance.pk and categoria_actual not in dict(opciones):
            opciones.append((
                categoria_actual, f'{categoria_actual} (histórica)'
            ))
        self.fields['categoria'].choices = opciones

    class Meta:
        model = Preguntas
        fields = ['Titulo', 'Pregunta', 'categoria']
        widgets = {
            'Titulo': forms.TextInput(attrs={
                'placeholder': 'Título de la pregunta',
                'class': 'form-control'
            }),
            'Pregunta': forms.Textarea(attrs={
                'placeholder': 'Escriba su pregunta aquí...',
                'class': 'form-control',
                'rows': 5
            }),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
        }


class RespuestaForm(forms.ModelForm):
    class Meta:
        model = Respuesta
        fields = ['Respuesta']
        widgets = {
            'Respuesta': forms.TextInput(
                attrs={'placeholder': 'Escribe un mensaje...'}
            ),
        }
