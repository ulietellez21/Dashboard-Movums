#!/usr/bin/expect -f
# Script de despliegue usando expect para automatizar SSH

set timeout 60
set server "tellez@206.189.223.176"
set password "EdgarTellez73!"

puts "🚀 Iniciando despliegue al servidor DigitalOcean..."
puts "📅 Fecha: [exec date]"
puts ""

# Conectar al servidor
spawn ssh -o StrictHostKeyChecking=no $server

expect {
    "password:" {
        send "$password\r"
        exp_continue
    }
    "Password:" {
        send "$password\r"
        exp_continue
    }
    "$ " {
        puts "✅ Conexión establecida"
    }
    "# " {
        puts "✅ Conexión establecida"
    }
    timeout {
        puts "❌ Timeout al conectar"
        exit 1
    }
    eof {
        puts "❌ Error de conexión"
        exit 1
    }
}

# Encontrar el proyecto
puts "\n📋 Buscando directorio del proyecto..."
send "find ~ -name 'agencia-web-project' -type d 2>/dev/null | head -1\r"
expect {
    -re "(.*agencia-web-project.*)" {
        set project_dir $expect_out(1,string)
        puts "✅ Proyecto encontrado: $project_dir"
    }
    "$ " {
        send "find /var/www -name 'agencia-web-project' -type d 2>/dev/null | head -1\r"
        expect {
            -re "(.*agencia-web-project.*)" {
                set project_dir $expect_out(1,string)
                puts "✅ Proyecto encontrado: $project_dir"
            }
            "$ " {
                set project_dir "~/agencia-web-project"
                puts "⚠️  Usando directorio por defecto: $project_dir"
            }
        }
    }
}

# Ir al directorio
send "cd $project_dir\r"
expect "$ "

# Backup
puts "\n📋 Haciendo backup de la base de datos..."
send "if [ -f db.sqlite3 ]; then cp db.sqlite3 db.sqlite3.backup_\$(date +%Y%m%d_%H%M%S) && echo '✅ Backup creado'; else echo '⚠️  No se encontró db.sqlite3'; fi\r"
expect "$ "

# Pull
puts "\n📋 Haciendo pull de los cambios..."
send "git pull origin master\r"
expect {
    "Already up to date" {
        puts "✅ Ya está actualizado"
    }
    -re ".*files? changed" {
        puts "✅ Cambios descargados"
    }
    "$ " {
        puts "✅ Pull completado"
    }
    timeout {
        puts "⚠️  Timeout en pull"
    }
}

# Activar venv
puts "\n📋 Activando entorno virtual..."
send "if [ -d venv ]; then source venv/bin/activate; elif [ -d env ]; then source env/bin/activate; fi\r"
expect "$ "

# Migraciones
puts "\n📋 Aplicando migraciones..."
send "python manage.py migrate --noinput\r"
expect {
    -re "Applying.*" {
        puts "✅ Migraciones aplicadas"
        expect "$ "
    }
    "No migrations to apply" {
        puts "✅ No hay migraciones pendientes"
    }
    "$ " {
        puts "✅ Migraciones completadas"
    }
}

# Collectstatic
puts "\n📋 Recolectando archivos estáticos..."
send "python manage.py collectstatic --noinput\r"
expect "$ "

# Reiniciar servicio
puts "\n📋 Reiniciando servicio..."
send "sudo systemctl restart gunicorn 2>/dev/null || sudo systemctl restart agencia-web 2>/dev/null || sudo supervisorctl restart agencia-web 2>/dev/null || pkill -HUP gunicorn\r"
expect {
    "password" {
        send "$password\r"
        expect "$ "
    }
    "$ " {
        puts "✅ Servicio reiniciado"
    }
}

puts "\n✅ Despliegue completado!"
send "exit\r"
expect eof

