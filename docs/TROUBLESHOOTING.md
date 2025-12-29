# Solución a Problemas de Bloqueo/Pantalla Gris en Modales

Si experimentas que al intentar abrir un modal (ej. Confirmar Eliminación) la pantalla se pone oscura ("opaca") y no puedes dar clic a nada ("bloqueada"), esto se debe a un problema conocido de **Contexto de Apilamiento (Stacking Context)** en CSS.

## 🛑 El Problema Ténico
1. El Dashboard utiliza animaciones de entrada (`transform`, `opacity`) en el contenedor principal `#main-content`.
2. Cualquier elemento HTML con propiedades de transformación crea su propia "capa" (Stacking Context) aislada.
3. El fondo oscuro de Bootstrap (`.modal-backdrop`) se adjunta automáticamente al `<body>` (fuera de esa capa).
4. El Modal, al estar dentro de `#main-content`, queda atrapado en una capa inferior al fondo oscuro, volviéndose inaccesible.

## ✅ La Solución Definitiva
**Nunca** coloques el código HTML de un modal dentro de bloques animados como `{% block content %}`.

En su lugar, utiliza siempre el bloque dedicado que existe en `base.html` para este propósito, que renderiza el contenido fuera de las áreas animadas:

```html
<!-- INCORRECTO: Dentro del contenido -->
{% block content %}
   ... contenido ...
   <div class="modal">...</div> <!-- ESTO CAUSA EL BLOQUEO -->
{% endblock %}

<!-- CORRECTO: En su propio bloque superior -->
{% block modals %}
   <div class="modal">...</div> <!-- ESTO FUNCIONA PERFECTO -->
{% endblock %}
```

Esta solución coloca el modal físicamente en el DOM al mismo nivel que el `<body>`, por encima de cualquier animación y del fondo oscuro.
