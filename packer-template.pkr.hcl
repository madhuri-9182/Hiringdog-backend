packer {
  required_plugins {
    googlecompute = {
      source  = "github.com/hashicorp/googlecompute"
      version = ">= 1.0.0"
    }
  }
}

variable "project_id" {
  type = string
}

variable "image_name" {
  type = string
}

variable "app_version" {
  type    = string
  default = "dev"
}

source "googlecompute" "ubuntu" {
  project_id          = var.project_id
  machine_type        = "e2-medium"
  source_image_family = "ubuntu-2404-lts-amd64"
  zone                = "asia-south1-b"
  disk_size           = 20
  ssh_username        = "packer"
  image_name          = var.image_name
  image_family        = "hiringdog-app"
}

build {
  sources = ["source.googlecompute.ubuntu"]
  
  # Upload the tar archive
  provisioner "file" {
    source      = "app.tar.gz"
    destination = "/tmp/app.tar.gz"
  }
  
  provisioner "shell" {
    environment_vars = [
      "DEBIAN_FRONTEND=noninteractive"
    ]
    inline = [
      # Update system
      "sudo apt-get update -y",
      "sudo apt-get upgrade -y",
      
      # Install Python, pip, and other dependencies
      "sudo apt-get install -y python3 python3-pip python3-venv python3-full curl nginx",
      "sudo apt-get install -y pkg-config python3-dev default-libmysqlclient-dev build-essential",
      
      # Create app directory and extract code
      "sudo mkdir -p /opt/hiringdog",
      "cd /opt/hiringdog",
      "sudo tar -xzf /tmp/app.tar.gz",
      "sudo chown -R www-data:www-data /opt/hiringdog",
      
      # Create virtual environment
      "sudo -u www-data python3 -m venv /opt/hiringdog/venv",
      
      # Install Python dependencies in virtual environment
      "if [ -f /opt/hiringdog/requirements.txt ]; then",
      "  sudo -u www-data /opt/hiringdog/venv/bin/pip install -r /opt/hiringdog/requirements.txt",
      "else",
      "  echo 'No requirements.txt found'",
      "fi",
       
      # Create necessary directories for Django
      "sudo mkdir -p /opt/hiringdog/staticfiles",
      "sudo mkdir -p /opt/hiringdog/media",
      "sudo mkdir -p /opt/hiringdog/logs",
      "sudo mkdir -p /opt/hiringdog/secrets",
      "sudo mkdir -p /var/log/hiringdog",
      "sudo chown -R www-data:www-data /opt/hiringdog/staticfiles",
      "sudo chown -R www-data:www-data /opt/hiringdog/media",
      "sudo chown -R www-data:www-data /opt/hiringdog/logs",
      "sudo chown -R www-data:www-data /opt/hiringdog/secrets",
      "sudo chown -R www-data:www-data /var/log/hiringdog",


      # Run Django migrations and collect static files
      "cd /opt/hiringdog",
      "sudo -u www-data /opt/hiringdog/venv/bin/python manage.py migrate --noinput || true",
      "sudo -u www-data /opt/hiringdog/venv/bin/python manage.py collectstatic --noinput || true",

      
     # Create Gunicorn systemd service for Django
      "sudo tee /etc/systemd/system/gunicorn.service > /dev/null <<EOF",
      "[Unit]",
      "Description=Gunicorn instance to serve Hiringdog Django App",
      "After=network.target",
      "",
      "[Service]",
      "User=www-data",
      "Group=www-data",
      "WorkingDirectory=/opt/hiringdog",

      "Environment=PATH=/opt/hiringdog/venv/bin",
      "EnvironmentFile=/opt/hiringdog/secrets/hiringdog.env",
      "Environment=PYTHONUNBUFFERED=1",

      "ExecStart=/opt/hiringdog/venv/bin/gunicorn --workers 2 --pid /run/gunicorn/gunicorn.pid --bind 127.0.0.1:8000 hiringdogbackend.wsgi:application",
      "ExecReload=/bin/kill -s USR2 \\$MAINPID",
      "ExecStop=/bin/kill -s TERM \\$MAINPID",
      "Restart=always",
      "RestartSec=10",
      "RuntimeDirectory=gunicorn",
      "RuntimeDirectoryMode=0755",

      # Logging (systemd manages rotation)
      "StandardOutput=append:/var/log/hiringdog/gunicorn.log",
      "StandardError=append:/var/log/hiringdog/gunicorn_error.log",
      # Resource tuning
      "LimitNOFILE=4096",
      "",
      
      "[Install]",
      "WantedBy=multi-user.target",
      "EOF",
      
      # Enable Gunicorn service
      "sudo systemctl enable gunicorn",
      
      # Configure Nginx
      "sudo tee /etc/nginx/sites-available/hiringdogbackend > /dev/null <<EOF",
      
      "server {",
      "    listen 80 default_server;",
      "    listen [::]:80 default_server;",
      "    server_name _;",
      "",

      "    location / {",
      "        proxy_pass http://127.0.0.1:8000;",
      "        proxy_set_header Host \\$host;",
      "        proxy_set_header X-Real-IP \\$remote_addr;",
      "        proxy_set_header X-Forwarded-For \\$proxy_add_x_forwarded_for;",
      "        proxy_set_header X-Forwarded-Proto \\$scheme;",
      "    }",
      "",
      "    location /health {",
      "        return 200 'healthy';",
      "        add_header Content-Type text/plain;",
      "    }",
           # Logs
      "    error_log /var/log/nginx/hiringdogbackend_error.log;",
      "    access_log /var/log/nginx/hiringdogbackend_access.log;",
      "}",
      "EOF",
      
      # Enable Nginx site
      "sudo ln -sf /etc/nginx/sites-available/hiringdogbackend /etc/nginx/sites-enabled/",
      "sudo rm -f /etc/nginx/sites-enabled/default",
      
      # Test Nginx config
      "sudo nginx -t",
      
      # Enable Nginx
      "sudo systemctl enable nginx",
      
      # Clean up
      "sudo apt-get autoremove -y",
      "sudo apt-get autoclean",
      "rm -f /tmp/app.tar.gz"
    ]
  }
}