const cajaConversacion = document.getElementById('chat-box');

if (cajaConversacion) {
    const estadoConversacion = document.getElementById('estado-conversacion');
    let ultimoConteoMensajes = -1;
    let cargandoMensajes = false;

    async function cargarMensajes() {
        if (cargandoMensajes) return;
        cargandoMensajes = true;
        try {
            const respuesta = await fetch(cajaConversacion.dataset.mensajesUrl);
            if (!respuesta.ok || respuesta.redirected) {
                throw new Error('No se pudo actualizar la conversación.');
            }
            const datos = await respuesta.json();
            if (!Array.isArray(datos.mensajes)) throw new Error('Sin mensajes.');
            estadoConversacion.textContent = '';
            if (datos.mensajes.length !== ultimoConteoMensajes) {
                const estabaAlFinal = cajaConversacion.scrollHeight
                    - cajaConversacion.scrollTop <= cajaConversacion.clientHeight + 50;
                const fragmento = document.createDocumentFragment();
                datos.mensajes.forEach(mensaje => {
                    const lado = mensaje.es_mio ? 'right' : 'left';
                    const fila = document.createElement('div');
                    fila.className = 'message ' + lado;
                    const burbuja = document.createElement('div');
                    burbuja.className = 'bubble ' + lado;
                    const autor = document.createElement('span');
                    autor.className = 'sender';
                    autor.textContent = mensaje.usuario;
                    if (mensaje.es_tecnico) {
                        const etiqueta = document.createElement('span');
                        etiqueta.className = 'tag-tecnico';
                        etiqueta.textContent = 'Soporte';
                        autor.appendChild(etiqueta);
                    }
                    const texto = document.createElement('div');
                    texto.className = 'texto-mensaje';
                    texto.textContent = mensaje.mensaje;
                    const fecha = document.createElement('span');
                    fecha.className = 'time';
                    fecha.textContent = mensaje.fecha;
                    burbuja.append(autor, texto, fecha);
                    fila.appendChild(burbuja);
                    fragmento.appendChild(fila);
                });
                cajaConversacion.replaceChildren(fragmento);
                if (estabaAlFinal || ultimoConteoMensajes === -1) {
                    cajaConversacion.scrollTop = cajaConversacion.scrollHeight;
                }
                ultimoConteoMensajes = datos.mensajes.length;
            }
        } catch (error) {
            estadoConversacion.textContent = 'No se pudo actualizar el historial. Se intentará nuevamente.';
        } finally {
            cargandoMensajes = false;
        }
    }

    cargarMensajes();
    setInterval(cargarMensajes, 2000);
}
