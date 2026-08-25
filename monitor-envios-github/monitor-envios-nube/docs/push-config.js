/* Clave pública VAPID de este monitor.
 *
 * Es pública a propósito: identifica al servidor que puede empujar avisos a tus
 * suscripciones, y el navegador la necesita para suscribirse. La PRIVADA que le
 * hace pareja NO está aquí: vive en el Secret VAPID_PRIVADA del repositorio.
 *
 * Si algún día regeneras el par (python -m monitor.webpush --generar-claves),
 * cambia esta línea Y vuelve a activar los avisos en cada dispositivo: las
 * suscripciones viejas quedan atadas a la clave vieja y dejan de valer.
 */
window.VAPID_PUBLICA = 'BCNjrgw_WqPd6cVRlg-RQR-AF7J9hv73a9fruKOV9DWmai3eZQyiK9S0WO-upZnBTWfPMucbwuW8FFuR-XA28yk';
