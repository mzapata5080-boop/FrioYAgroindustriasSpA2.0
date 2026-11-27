// Para un despliegue, asigna window.FYAG_API_BASE antes de cargar este archivo.
const host = window.location.hostname;
const backendHost = host.includes(':') ? `[${host.replace(/^\[|\]$/g, '')}]` : host;
window.API_BASE = (window.FYAG_API_BASE || `${window.location.protocol}//${backendHost}:8000/api`).replace(/\/$/, '');
