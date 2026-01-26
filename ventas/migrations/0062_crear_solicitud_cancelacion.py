# Generated manually for SolicitudCancelacion

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0061_crear_modelos_comisiones'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SolicitudCancelacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('motivo', models.TextField(help_text='Razón por la cual se solicita la cancelación de la venta', verbose_name='Motivo de la Cancelación')),
                ('estado', models.CharField(choices=[('PENDIENTE', 'Pendiente de Aprobación'), ('APROBADA', 'Aprobada'), ('RECHAZADA', 'Rechazada'), ('CANCELADA', 'Cancelada Definitivamente')], default='PENDIENTE', max_length=20, verbose_name='Estado')),
                ('fecha_solicitud', models.DateTimeField(auto_now_add=True, verbose_name='Fecha de Solicitud')),
                ('fecha_aprobacion', models.DateTimeField(blank=True, null=True, verbose_name='Fecha de Aprobación')),
                ('fecha_cancelacion_definitiva', models.DateTimeField(blank=True, null=True, verbose_name='Fecha de Cancelación Definitiva')),
                ('motivo_rechazo', models.TextField(blank=True, help_text='Razón por la cual se rechazó la solicitud de cancelación', verbose_name='Motivo de Rechazo')),
                ('aprobado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cancelaciones_aprobadas', to=settings.AUTH_USER_MODEL, verbose_name='Aprobado Por')),
                ('solicitado_por', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='solicitudes_cancelacion', to=settings.AUTH_USER_MODEL, verbose_name='Solicitado Por')),
                ('venta', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='solicitud_cancelacion', to='ventas.ventaviaje', verbose_name='Venta')),
            ],
            options={
                'verbose_name': 'Solicitud de Cancelación',
                'verbose_name_plural': 'Solicitudes de Cancelación',
                'ordering': ['-fecha_solicitud'],
                'indexes': [
                    models.Index(fields=['venta', 'estado'], name='ventas_solic_venta_i_123abc_idx'),
                    models.Index(fields=['estado', 'fecha_solicitud'], name='ventas_solic_estado__456def_idx'),
                    models.Index(fields=['solicitado_por'], name='ventas_solic_solicit_789ghi_idx'),
                ],
            },
        ),
        migrations.AddField(
            model_name='comisionventa',
            name='cancelada',
            field=models.BooleanField(default=False, help_text='Indica si la comisión fue cancelada debido a la cancelación de la venta', verbose_name='Cancelada'),
        ),
        migrations.AddField(
            model_name='comisionventa',
            name='fecha_cancelacion',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Fecha de Cancelación'),
        ),
        migrations.AddIndex(
            model_name='comisionventa',
            index=models.Index(fields=['cancelada'], name='ventas_comi_cancelada_idx'),
        ),
        migrations.AddField(
            model_name='notificacion',
            name='solicitud_cancelacion',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='notificaciones', to='ventas.solicitudcancelacion', verbose_name='Solicitud de Cancelación Relacionada'),
        ),
        migrations.AlterField(
            model_name='notificacion',
            name='tipo',
            field=models.CharField(choices=[('ABONO', 'Abono Registrado'), ('LIQUIDACION', 'Venta Liquidada'), ('APERTURA', 'Apertura Registrada'), ('LOGISTICA', 'Cambio en Logística'), ('PAGO_PENDIENTE', 'Pago Pendiente de Confirmación'), ('PAGO_CONFIRMADO', 'Pago Confirmado por Contador'), ('CANCELACION', 'Venta Cancelada'), ('SOLICITUD_ABONO_PROVEEDOR', 'Solicitud de Abono a Proveedor'), ('ABONO_PROVEEDOR_APROBADO', 'Abono a Proveedor Aprobado'), ('ABONO_PROVEEDOR_COMPLETADO', 'Abono a Proveedor Completado'), ('ABONO_PROVEEDOR_CANCELADO', 'Abono a Proveedor Cancelado'), ('SOLICITUD_CANCELACION', 'Solicitud de Cancelación'), ('CANCELACION_APROBADA', 'Cancelación Aprobada'), ('CANCELACION_RECHAZADA', 'Cancelación Rechazada'), ('CANCELACION_DEFINITIVA', 'Cancelación Definitiva')], max_length=35, verbose_name='Tipo de Notificación'),
        ),
    ]
