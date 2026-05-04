document.addEventListener('DOMContentLoaded', function () {
    const lightbox = document.getElementById('lightbox');
    const lbImg = document.getElementById('lbImg');
    const lbClose = document.getElementById('lbClose');

    if (!lightbox || !lbImg || !lbClose) return;

    function abrirLightbox(src) {
        if (!src) return;
        lbImg.src = src;
        lightbox.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    function cerrarLightbox() {
        lightbox.classList.remove('active');
        document.body.style.overflow = '';
        // Opcional: limpiar src para liberar memoria
        // lbImg.src = '';
    }

    // 1. Clic en el avatar (solo si es una imagen real)
    const avatarImg = document.querySelector('#avatarWrap img');
    if (avatarImg) {
        avatarImg.addEventListener('click', function (e) {
            e.stopPropagation();
            abrirLightbox(this.src);
        });
    }

    // 2. Clic en la foto grande de la sección
    const fotoGrande = document.getElementById('fotoPerfilGrande');
    if (fotoGrande) {
        fotoGrande.addEventListener('click', function () {
            abrirLightbox(this.src);
        });
    }

    // 3. Cerrar con el botón
    lbClose.addEventListener('click', cerrarLightbox);

    // 4. Cerrar haciendo clic en el fondo
    lightbox.addEventListener('click', function (e) {
        if (e.target === lightbox) cerrarLightbox();
    });

    // 5. Cerrar con tecla ESC
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && lightbox.classList.contains('active')) {
            cerrarLightbox();
        }
    });
});