const botonAsistente = document.getElementById('abrir-asistente');
const ventanaAsistente = document.getElementById('ventana-asistente');
const formularioAsistente = document.getElementById('formulario-asistente');

if (botonAsistente && ventanaAsistente && formularioAsistente) {
    const entrada = document.getElementById('consulta-asistente');
    const mensajes = document.getElementById('mensajes-asistente');
    const botonCerrar = document.getElementById('cerrar-asistente');
    const botonEnviar = formularioAsistente.querySelector('[type=submit]');
    let consultaPendiente = false;

    function abrirAsistente() {
        ventanaAsistente.hidden = false;
        botonAsistente.setAttribute('aria-expanded', 'true');
        entrada.focus();
        mensajes.scrollTop = mensajes.scrollHeight;
    }

    function cerrarAsistente() {
        ventanaAsistente.hidden = true;
        botonAsistente.setAttribute('aria-expanded', 'false');
        botonAsistente.focus();
    }

    function agregarMensaje(texto, clase) {
        const mensaje = document.createElement('p');
        mensaje.className = clase;
        mensaje.textContent = texto;
        mensajes.appendChild(mensaje);
        mensajes.scrollTop = mensajes.scrollHeight;
        return mensaje;
    }

    botonAsistente.addEventListener('click', () => {
        if (ventanaAsistente.hidden) abrirAsistente();
        else cerrarAsistente();
    });
    botonCerrar.addEventListener('click', cerrarAsistente);
    document.querySelectorAll('[data-abrir-asistente]').forEach(boton => {
        boton.addEventListener('click', abrirAsistente);
    });
    ventanaAsistente.addEventListener('keydown', evento => {
        if (evento.key === 'Escape') cerrarAsistente();
    });

    formularioAsistente.addEventListener('submit', async evento => {
        evento.preventDefault();
        const consulta = entrada.value.trim();
        if (!consulta || consultaPendiente) return;
        consultaPendiente = true;
        botonEnviar.disabled = true;
        agregarMensaje(consulta, 'mensaje-usuario');
        entrada.value = '';
        const esperando = agregarMensaje('Consultando...', 'mensaje-asistente');
        const controlador = new AbortController();
        const espera = setTimeout(() => controlador.abort(), 25000);
        try {
            const datos = new FormData(formularioAsistente);
            datos.set('consulta', consulta);
            const respuesta = await fetch(formularioAsistente.action, {
                method: 'POST', body: datos, signal: controlador.signal,
                headers: {
                    'X-CSRFToken': formularioAsistente.elements.csrfmiddlewaretoken.value,
                },
            });
            if (respuesta.redirected) {
                throw new Error('Tu sesión terminó. Vuelve a iniciar sesión.');
            }
            const contenido = await respuesta.json();
            esperando.textContent = respuesta.ok
                ? contenido.respuesta
                : contenido.error || 'El asistente no está disponible. Puedes crear un ticket.';
        } catch (error) {
            esperando.textContent = error.message.startsWith('Tu sesión')
                ? error.message
                : 'El asistente no está disponible. Puedes crear un ticket directamente con un ejecutivo.';
        } finally {
            clearTimeout(espera);
            consultaPendiente = false;
            botonEnviar.disabled = false;
            mensajes.scrollTop = mensajes.scrollHeight;
        }
    });
}
