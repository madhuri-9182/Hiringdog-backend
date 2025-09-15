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
      "sudo apt install -y python3 python3-pip python3-venv python3-full curl nginx",
      "sudo apt install -y pkg-config python3-dev default-libmysqlclient-dev build-essential",
      
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
      "  echo 'No requirements.txt found, installing common dependencies'",
      "  sudo -u www-data /opt/hiringdog/venv/bin/pip install gunicorn flask",
      "fi",
      
      # Create proper Django WSGI file (only if wsgi.py doesn't exist in the project structure)
      "if [ ! -f /opt/hiringdog/hiringdogbackend/wsgi.py ]; then",
      "  echo 'WSGI file not found in expected location. Creating a generic one.'",
      "  sudo tee /opt/hiringdog/wsgi.py > /dev/null <<EOF",
      "import os",
      "import sys",
      "from django.core.wsgi import get_wsgi_application",
      "",
      "# Add the project directory to Python path",
      "sys.path.insert(0, '/opt/hiringdog')",
      "",
      "# Set the Django settings module",
      "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hiringdogbackend.settings')",
      "",
      "application = get_wsgi_application()",
      "EOF",
      "  sudo chown www-data:www-data /opt/hiringdog/wsgi.py",
      "else",
      "  echo 'Using existing WSGI file from Django project'",
      "fi",

       
      # Run Django migrations and collect static files
      "cd /opt/hiringdog",
      "sudo -u www-data /opt/hiringdog/venv/bin/python manage.py migrate --noinput || true",
      "sudo -u www-data /opt/hiringdog/venv/bin/python manage.py collectstatic --noinput || true",
      
      
     # Create Gunicorn systemd service for Django
      "sudo tee /etc/systemd/system/hiringdog.service > /dev/null <<EOF",
      "[Unit]",
      "Description=Gunicorn instance to serve Hiringdog Django App",
      "After=network.target",
      "",
      "[Service]",
      "User=www-data",
      "Group=www-data",
      "WorkingDirectory=/opt/hiringdog",
      "Environment=PATH=/opt/hiringdog/venv/bin",
      "Environment=DJANGO_SETTINGS_MODULE=hiringdogbackend.settings",
      "ExecStart=/opt/hiringdog/venv/bin/gunicorn --workers 3 --bind unix:/opt/hiringdog/hiringdog.sock hiringdogbackend.wsgi:application",
      "Restart=always",
      "",
      "[Install]",
      "WantedBy=multi-user.target",
      "EOF",
      
      # Enable Gunicorn service
      "sudo systemctl enable hiringdog",
      
      # Configure Nginx
      "sudo tee /etc/nginx/sites-available/hiringdog > /dev/null <<EOF",
      "server {",
      "    listen 80;",
      "    server_name _;",
      "",
      "    location / {",
      "        proxy_pass http://unix:/opt/hiringdog/hiringdog.sock;",
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
      "}",
      "EOF",
      
      # Enable Nginx site
      "sudo ln -sf /etc/nginx/sites-available/hiringdog /etc/nginx/sites-enabled/",
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