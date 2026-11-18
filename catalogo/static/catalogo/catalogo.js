document.querySelectorAll('[data-controles]').forEach((controles) => {
    const carrusel = document.getElementById(controles.dataset.controles);
    if (!carrusel || !carrusel.querySelector('.tarjeta-contenido')) return;
    controles.hidden = false;
    controles.querySelectorAll('button').forEach((boton) => {
        boton.addEventListener('click', () => {
            const reducirMovimiento = window.matchMedia(
                '(prefers-reduced-motion: reduce)'
            ).matches;
            carrusel.scrollBy({
                left: carrusel.clientWidth * 0.8
                    * Number(boton.dataset.direccion),
                behavior: reducirMovimiento ? 'instant' : 'smooth',
            });
        });
    });
});
