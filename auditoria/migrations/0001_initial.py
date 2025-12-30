# Generated manually for auditoria app

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='HistorialMovimiento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_hora', models.DateTimeField(db_index=True, default=django.utils.timezone.now, help_text='Fecha y hora exacta del evento', verbose_name='Fecha y Hora')),
                ('tipo_evento', models.CharField(choices=[('VENTA_CREADA', 'Venta Creada'), ('VENTA_EDITADA', 'Venta Editada'), ('VENTA_ELIMINADA', 'Venta Eliminada'), ('COTIZACION_CREADA', 'Cotización Creada'), ('COTIZACION_EDITADA', 'Cotización Editada'), ('COTIZACION_ELIMINADA', 'Cotización Eliminada'), ('COTIZACION_CONVERTIDA', 'Cotización Convertida a Venta'), ('ABONO_REGISTRADO', 'Abono Registrado'), ('ABONO_CONFIRMADO', 'Abono Confirmado'), ('ABONO_ELIMINADO', 'Abono Eliminado'), ('CLIENTE_CREADO', 'Cliente Creado'), ('CLIENTE_EDITADO', 'Cliente Editado'), ('CLIENTE_ELIMINADO', 'Cliente Eliminado'), ('USUARIO_CREADO', 'Usuario Creado'), ('USUARIO_EDITADO', 'Usuario Editado'), ('USUARIO_ELIMINADO', 'Usuario Eliminado'), ('USUARIO_LOGIN', 'Usuario Inició Sesión'), ('USUARIO_LOGOUT', 'Usuario Cerró Sesión'), ('KILOMETROS_ACUMULADOS', 'Kilómetros Acumulados'), ('KILOMETROS_REDIMIDOS', 'Kilómetros Redimidos'), ('PROMOCION_APLICADA', 'Promoción Aplicada'), ('PROMOCION_CREADA', 'Promoción Creada'), ('PROMOCION_EDITADA', 'Promoción Editada'), ('PROMOCION_ELIMINADA', 'Promoción Eliminada'), ('CONFIRMACION_SUBIDA', 'Confirmación Subida'), ('CONFIRMACION_ELIMINADA', 'Confirmación Eliminada'), ('LOGISTICA_ACTUALIZADA', 'Logística Actualizada'), ('OTRO', 'Otro Evento')], db_index=True, max_length=50, verbose_name='Tipo de Evento')),
                ('nivel', models.CharField(choices=[('INFO', 'Informativo'), ('WARNING', 'Advertencia'), ('ERROR', 'Error'), ('CRITICAL', 'Crítico')], db_index=True, default='INFO', max_length=10, verbose_name='Nivel')),
                ('descripcion', models.TextField(help_text='Descripción detallada del evento en formato de texto', verbose_name='Descripción')),
                ('datos_adicionales', models.JSONField(blank=True, help_text='Información adicional en formato JSON (opcional)', null=True, verbose_name='Datos Adicionales')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, verbose_name='Dirección IP')),
                ('object_id', models.PositiveIntegerField(blank=True, null=True, verbose_name='ID del Objeto')),
                ('content_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='contenttypes.contenttype', verbose_name='Tipo de Objeto')),
                ('usuario', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='movimientos_realizados', to=settings.AUTH_USER_MODEL, verbose_name='Usuario')),
            ],
            options={
                'verbose_name': 'Historial de Movimiento',
                'verbose_name_plural': 'Historial de Movimientos',
                'ordering': ['-fecha_hora'],
            },
        ),
        migrations.AddIndex(
            model_name='historialmovimiento',
            index=models.Index(fields=['-fecha_hora'], name='auditoria_h_fecha_h_8a1b2c_idx'),
        ),
        migrations.AddIndex(
            model_name='historialmovimiento',
            index=models.Index(fields=['tipo_evento'], name='auditoria_h_tipo_ev_9d3e4f_idx'),
        ),
        migrations.AddIndex(
            model_name='historialmovimiento',
            index=models.Index(fields=['usuario'], name='auditoria_h_usuario_1a2b3c_idx'),
        ),
        migrations.AddIndex(
            model_name='historialmovimiento',
            index=models.Index(fields=['nivel'], name='auditoria_h_nivel_4d5e6f_idx'),
        ),
    ]

