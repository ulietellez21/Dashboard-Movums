# Guía de Configuración del Dominio movums.mx

## ✅ CONFIGURACIÓN COMPLETADA EN EL SERVIDOR

He configurado el servidor para aceptar el dominio `movums.mx`. Ahora solo necesitas configurar el DNS.

---

## 📋 Paso 1: Configuración DNS en el Host del Dominio

**IMPORTANTE**: En el panel de control de tu proveedor de dominio (donde compraste `movums.mx`), necesitas configurar los registros DNS:

### Opción A: Registro A (Recomendado)
```
Tipo: A
Nombre: @ (o en blanco, o movums.mx)
Valor: 206.189.223.176
TTL: 3600 (o el valor por defecto)
```

### Opción B: Con www también
```
Tipo: A
Nombre: @ (o en blanco)
Valor: 206.189.223.176

Tipo: A
Nombre: www
Valor: 206.189.223.176
```

**O usando CNAME para www:**
```
Tipo: A
Nombre: @
Valor: 206.189.223.176

Tipo: CNAME
Nombre: www
Valor: movums.mx
```

---

## 📋 Paso 2: Verificar que el DNS está propagado

Después de configurar el DNS, espera unos minutos (puede tardar hasta 48 horas, pero generalmente es rápido) y verifica:

```bash
# Desde tu máquina local
nslookup movums.mx
# O
dig movums.mx

# Debe mostrar: 206.189.223.176
```

También puedes usar herramientas en línea:
- https://www.whatsmydns.net/#A/movums.mx
- https://dnschecker.org/#A/movums.mx

---

## ✅ Configuración del Servidor (YA COMPLETADA)

### 1. Nginx configurado
- ✅ Archivo: `/etc/nginx/sites-available/agencia`
- ✅ `server_name` actualizado: `movums.mx www.movums.mx 206.189.223.176`
- ✅ Nginx recargado

### 2. Django configurado
- ✅ `ALLOWED_HOSTS` actualizado: `['localhost', '127.0.0.1', '0.0.0.0', '206.189.223.176', 'movums.mx', 'www.movums.mx']`
- ✅ Gunicorn reiniciado

---

## 🔒 Paso 3: Configurar SSL/HTTPS (Opcional pero Recomendado)

Una vez que el dominio funcione, es recomendable configurar SSL con Let's Encrypt:

```bash
# Instalar Certbot
sudo apt update
sudo apt install certbot python3-certbot-nginx -y

# Obtener certificado SSL
sudo certbot --nginx -d movums.mx -d www.movums.mx

# El certificado se renovará automáticamente
```

Esto configurará HTTPS automáticamente y redirigirá HTTP a HTTPS.

---

## 🧪 Verificación

Una vez configurado el DNS, prueba acceder a:
- http://movums.mx
- http://www.movums.mx

Si configuraste SSL:
- https://movums.mx
- https://www.movums.mx

---

## 📝 Notas

- El DNS puede tardar en propagarse (desde minutos hasta 48 horas)
- Si el dominio no funciona inmediatamente, espera un poco y verifica el DNS
- Una vez que el DNS apunte correctamente, el sitio debería funcionar automáticamente
- Considera configurar SSL/HTTPS para mayor seguridad

---

## 🔧 Comandos Útiles

### Verificar configuración Nginx
```bash
sudo nginx -t
sudo systemctl status nginx
```

### Ver logs de Nginx
```bash
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Reiniciar servicios
```bash
sudo systemctl reload nginx
sudo systemctl restart gunicorn  # Si usas systemd
# O
pkill -HUP gunicorn  # Si usas Gunicorn directo
```
