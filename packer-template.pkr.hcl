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

source "googlecompute" "debian" {
  project_id          = var.project_id
  machine_type        = "e2-medium"
  source_image_family = "debian-11"
  zone                = "asia-south1-b"
  disk_size           = 20
  ssh_username        = "packer"
  image_name          = var.image_name
  image_family        = "hiringdog-app"
}

build {
  sources = ["source.googlecompute.debian"]

  provisioner "shell" {
    inline = [
      # Update system
      "sudo apt-get update -y",
      "sudo apt-get upgrade -y",

      # Install Python, pip, venv
      "sudo apt-get install -y python3 python3-pip python3-venv",

      # Install Gunicorn
      "pip3 install gunicorn",

      # Install Nginx
      "sudo apt-get install -y nginx",

      # Copy app (assuming your repo contains it)
      "mkdir -p /opt/hiringdog",
      "cp -r /home/packer/* /opt/hiringdog",

      # Systemd service for Gunicorn
      "echo '[Unit]\nDescription=Gunicorn instance to serve Hiringdog\nAfter=network.target\n\n[Service]\nUser=www-data\nGroup=www-data\nWorkingDirectory=/opt/hiringdog\nExecStart=/usr/bin/gunicorn --workers 3 --bind unix:/opt/hiringdog/hiringdog.sock wsgi:app\n\n[Install]\nWantedBy=multi-user.target' | sudo tee /etc/systemd/system/hiringdog.service",

      "sudo systemctl enable hiringdog",
      "sudo systemctl restart hiringdog",

      # Configure Nginx
      "echo 'server {\n    listen 80;\n    server_name _;\n\n    location / {\n        proxy_pass http://unix:/opt/hiringdog/hiringdog.sock;\n        proxy_set_header Host $host;\n        proxy_set_header X-Real-IP $remote_addr;\n        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n        proxy_set_header X-Forwarded-Proto $scheme;\n    }\n\n    location /health {\n        return 200 \"healthy\";\n    }\n}' | sudo tee /etc/nginx/sites-available/hiringdog",

      "sudo ln -s /etc/nginx/sites-available/hiringdog /etc/nginx/sites-enabled",
      "sudo rm -f /etc/nginx/sites-enabled/default",
      "sudo systemctl restart nginx"
    ]
  }
}
