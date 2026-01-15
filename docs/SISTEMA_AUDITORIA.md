# Sistema de Auditoría e Historial de Movimientos

## Descripción

Sistema completo de auditoría que registra automáticamente todos los movimientos importantes del sistema en formato de texto con fecha y hora. Permite rastrear todas las acciones realizadas por usuarios en el sistema.

## Características

- ✅ Registro automático de eventos mediante señales de Django
- ✅ Registro manual mediante servicio centralizado
- ✅ Almacenamiento en base de datos con fecha, hora, usuario y descripción
- ✅ Filtros avanzados para búsqueda
- ✅ Vista web para visualizar el historial
- ✅ Integración con modelos principales (Ventas, Cotizaciones, Abonos, Clientes, Usuarios)

## Componentes

### 1. Modelo `HistorialMovimiento`

Almacena todos los eventos con:
- Fecha y hora exacta
- Tipo de evento
- Usuario que realizó la acción
- Descripción en formato de texto
- Nivel (INFO, WARNING, ERROR, CRITICAL)
- Objeto relacionado (genérico)
- Datos adicionales (JSON)
- Dirección IP

### 2. Servicio `AuditoriaService`

Proporciona métodos para registrar eventos:

```python
from auditoria.services import AuditoriaService

# Registro genérico
AuditoriaService.registrar_evento(
    tipo_evento='VENTA_CREADA',
    descripcion='Venta creada...',
    usuario=request.user,
    objeto=venta
)

# Métodos específicos
AuditoriaService.registrar_venta_creada(venta, usuario)
AuditoriaService.registrar_abono_registrado(abono, usuario)
AuditoriaService.registrar_cliente_creado(cliente, usuario)
```

### 3. Señales Automáticas

Las siguientes acciones se registran automáticamente:
- Creación/edición de ventas
- Creación/confirmación de abonos
- Creación de cotizaciones
- Creación de clientes
- Creación de usuarios
- Login/Logout de usuarios

### 4. Vista Web

Accesible en `/auditoria/historial/` (solo para JEFE y CONTADOR)

Características:
- Filtros por tipo de evento, nivel, fecha, usuario
- Búsqueda de texto
- Paginación
- Estadísticas rápidas

## Tipos de Eventos Registrados

- `VENTA_CREADA` - Venta creada
- `VENTA_EDITADA` - Venta editada
- `COTIZACION_CREADA` - Cotización creada
- `ABONO_REGISTRADO` - Abono registrado
- `ABONO_CONFIRMADO` - Abono confirmado
- `CLIENTE_CREADO` - Cliente creado
- `USUARIO_CREADO` - Usuario creado
- `USUARIO_LOGIN` - Usuario inició sesión
- `USUARIO_LOGOUT` - Usuario cerró sesión
- `KILOMETROS_ACUMULADOS` - Kilómetros acumulados
- `KILOMETROS_REDIMIDOS` - Kilómetros redimidos
- Y más...

## Uso Manual

Para registrar eventos manualmente en vistas:

```python
from auditoria.services import AuditoriaService

def mi_vista(request):
    # ... lógica ...
    
    # Registrar evento
    AuditoriaService.registrar_evento(
        tipo_evento='OTRO',
        descripcion='Descripción del evento',
        usuario=request.user,
        objeto=objeto_relacionado,
        ip_address=get_client_ip(request)
    )
```

## Migración

Para crear las tablas en la base de datos:

```bash
python manage.py makemigrations auditoria
python manage.py migrate auditoria
```

## Acceso

- URL: `/auditoria/historial/`
- Permisos: Solo JEFE y CONTADOR
- Admin: Disponible en Django Admin

## Próximos Pasos

1. Ejecutar migraciones
2. Agregar enlaces al historial en el dashboard
3. Integrar registro manual en vistas específicas que lo requieran
4. Configurar limpieza automática de registros antiguos (opcional)










